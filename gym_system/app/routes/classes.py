"""Classes/Booking routes"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerField, TimeField, BooleanField, DateField, DecimalField
from wtforms.validators import DataRequired, Optional, NumberRange
from datetime import datetime, date, timedelta

from app import db
from app.models import Brand, Branch, Member, User, ServiceType, GymClass, ClassBooking
from app.models.classes import ClassSession, ClassEnrollment
from app.utils.helpers import apply_branch_filter, check_entity_access

classes_bp = Blueprint('classes', __name__, url_prefix='/classes')

ARABIC_WEEKDAYS = [
    (0, 'السبت'), (1, 'الأحد'), (2, 'الاثنين'), (3, 'الثلاثاء'),
    (4, 'الأربعاء'), (5, 'الخميس'), (6, 'الجمعة'),
]


class GymClassForm(FlaskForm):
    """Form for creating/editing gym classes"""
    name = StringField('اسم الكلاس', validators=[DataRequired()])
    branch_id = SelectField('الفرع', coerce=int, validators=[Optional()])
    service_type_id = SelectField('نوع الخدمة', coerce=int, validators=[DataRequired()])
    trainer_id = SelectField('المدرب', coerce=int, validators=[Optional()])
    description = TextAreaField('الوصف', validators=[Optional()])
    # GYM-62: multi-day schedule. `day_of_week` is kept as a hidden legacy mirror
    # (populated from min(weekdays)) — new code reads weekday_mask via the model.
    day_of_week = SelectField('اليوم', coerce=int, choices=ARABIC_WEEKDAYS, validators=[Optional()])
    start_time = TimeField('وقت البداية', validators=[DataRequired()])
    end_time = TimeField('وقت النهاية', validators=[DataRequired()])
    start_date = DateField('تاريخ بداية الكلاس', validators=[DataRequired()])
    end_date = DateField('تاريخ نهاية الكلاس', validators=[DataRequired()])
    capacity = IntegerField('السعة', validators=[DataRequired(), NumberRange(min=1, max=500)], default=20)
    price = DecimalField('سعر الاشتراك', validators=[Optional(), NumberRange(min=0)], default=0, places=2)
    trainer_fee_per_session = DecimalField('تكلفة الحصة للمدرب', validators=[Optional(), NumberRange(min=0)], default=0, places=2)
    status = SelectField('حالة الكلاس', choices=[
        ('active', 'نشط'), ('ended', 'منتهي'), ('cancelled', 'ملغي'),
    ], default='active')
    is_active = BooleanField('نشط', default=True)


def _parse_weekdays_from_request():
    """Read the 7 weekday checkboxes from the raw form (not on the WTForm).
    Returns (mask, list_of_ints). If nothing selected, returns (0, [])."""
    raw = request.form.getlist('weekdays')
    days = sorted({int(d) for d in raw if str(d).isdigit() and 0 <= int(d) <= 6})
    mask = 0
    for d in days:
        mask |= (1 << d)
    return mask, days


@classes_bp.route('/')
@login_required
def index():
    """View class schedule"""
    if not (current_user.role and current_user.role.can_manage_classes):
        flash('ليس لديك صلاحية لعرض الكلاسات', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get filters
    day_filter = request.args.get('day', type=int)
    service_filter = request.args.get('service', type=int)

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        brands = Brand.query.filter_by(is_active=True).all()
        if brand_id:
            brand = Brand.query.get(brand_id)
        else:
            brand = brands[0] if brands else None
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand
        brands = []

    if not brand:
        flash('يرجى اختيار براند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Build query
    query = apply_branch_filter(GymClass.query.filter_by(brand_id=brand.id), GymClass)
    if day_filter is not None:
        query = query.filter_by(day_of_week=day_filter)
    if service_filter:
        query = query.filter_by(service_type_id=service_filter)

    classes = query.order_by(GymClass.day_of_week, GymClass.start_time).all()
    service_types = ServiceType.query.filter_by(brand_id=brand.id, is_active=True).all()

    # Group classes by day — a multi-day class (GYM-62) appears under every
    # weekday it meets, driven by weekday_mask; falls back to day_of_week for
    # legacy rows.
    schedule = {i: [] for i in range(7)}
    for cls in classes:
        for dow in cls.weekdays_list():
            if 0 <= dow <= 6:
                schedule[dow].append(cls)

    return render_template('classes/index.html',
                         classes=classes,
                         schedule=schedule,
                         service_types=service_types,
                         brand=brand,
                         brands=brands,
                         day_filter=day_filter,
                         service_filter=service_filter)


# ─── GYM-53 — consolidated month calendar (sidebar landing) ───────────────

@classes_bp.route('/calendar')
@login_required
def calendar():
    """Monthly calendar view — the new sidebar landing for الكلاسات.

    Each day cell shows how many classes are scheduled that weekday +
    how many bookings exist for that specific date. Optional ?date=YYYY-MM-DD
    param populates a "sessions on this day" panel below the grid so the
    receptionist can drill down without a second page load.
    """
    from calendar import monthrange
    from app.models.classes import GymClass, ClassBooking

    # Permission — same as either الكلاسات or الحصص والحجوزات used to require.
    can_view = (
        (current_user.role and current_user.role.can_manage_classes)
        or current_user.can_manage_members
        or (current_user.role and current_user.role.name_en == 'branch_receptionist')
    )
    if not can_view:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Month picker — default to today's month in Riyadh.
    from app.utils.helpers import to_local
    now_local = to_local(datetime.utcnow())
    default_month = f'{now_local.year}-{now_local.month:02d}'
    raw_month = request.args.get('month', default_month)
    try:
        y, m = raw_month.split('-')
        year, month = int(y), int(m)
    except (ValueError, TypeError):
        year, month = now_local.year, now_local.month

    # Compute prev / next month for the pager.
    prev_month_dt = date(year, month, 1) - timedelta(days=1)
    next_month_dt = date(year, month, 28) + timedelta(days=10)
    prev_month = f'{prev_month_dt.year}-{prev_month_dt.month:02d}'
    next_month = f'{next_month_dt.year}-{next_month_dt.month:02d}'

    # Brand scope — same as classes.index.
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        brands = Brand.query.filter_by(is_active=True).all()
        brand = Brand.query.get(brand_id) if brand_id else (brands[0] if brands else None)
    else:
        brands = []
        brand = current_user.brand
    if not brand:
        flash('يرجى اختيار براند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Classes for this brand keyed by day_of_week (0..6).
    gym_classes = apply_branch_filter(
        GymClass.query.filter_by(brand_id=brand.id, is_active=True), GymClass
    ).all()
    classes_by_dow: dict[int, list] = {i: [] for i in range(7)}
    for gc in gym_classes:
        if gc.day_of_week is not None:
            classes_by_dow.setdefault(gc.day_of_week, []).append(gc)

    # Bookings in the whole month — one query, group in Python.
    _, days_in_month = monthrange(year, month)
    first_day = date(year, month, 1)
    last_day = date(year, month, days_in_month)
    bookings_in_month = apply_branch_filter(
        ClassBooking.query.filter(
            ClassBooking.booking_date >= first_day,
            ClassBooking.booking_date <= last_day,
        ), ClassBooking
    ).all()
    bookings_by_date: dict[date, int] = {}
    for b in bookings_in_month:
        bookings_by_date[b.booking_date] = bookings_by_date.get(b.booking_date, 0) + 1

    # Build the grid. Arabic week starts on Saturday: dow 0=Sat..6=Fri, but
    # Python's date.weekday() is 0=Mon..6=Sun. Map to Arabic week.
    def to_arabic_dow(d):  # 0=Sat..6=Fri
        py_dow = d.weekday()   # 0=Mon..6=Sun
        return (py_dow + 2) % 7  # Sat=0, Sun=1, ..., Fri=6

    # Pad the grid: leading blanks so the first day of the month lines up.
    first_dow = to_arabic_dow(first_day)
    cells = []
    for _ in range(first_dow):
        cells.append(None)
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        cells.append({
            'date': d,
            'day': day,
            'class_count': len(classes_by_dow.get(to_arabic_dow(d), [])),
            'booking_count': bookings_by_date.get(d, 0),
            'is_today': d == now_local.date(),
        })
    # Pad trailing to complete the last row (multiple of 7).
    while len(cells) % 7:
        cells.append(None)
    weeks = [cells[i:i + 7] for i in range(0, len(cells), 7)]

    # Drill-down: when ?date=X, render the day's sessions + bookings below.
    day_focus = None
    day_classes = []
    day_bookings = []
    raw_date = request.args.get('date')
    if raw_date:
        try:
            day_focus = date.fromisoformat(raw_date)
            day_classes = classes_by_dow.get(to_arabic_dow(day_focus), [])
            day_bookings = [b for b in bookings_in_month
                            if b.booking_date == day_focus]
        except ValueError:
            day_focus = None

    return render_template(
        'classes/calendar_month.html',
        year=year, month=month,
        prev_month=prev_month, next_month=next_month,
        weeks=weeks,
        brand=brand, brands=brands,
        day_focus=day_focus,
        day_classes=day_classes,
        day_bookings=day_bookings,
        month_label={
            1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل', 5: 'مايو', 6: 'يونيو',
            7: 'يوليو', 8: 'أغسطس', 9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر',
        }.get(month, ''),
    )


@classes_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new class"""
    if not (current_user.role and current_user.role.can_manage_classes):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    form = GymClassForm()
    
    # Get all brands for owner
    brands = []
    if current_user.is_owner:
        brands = Brand.query.filter_by(is_active=True).all()

    # Get brand from form or URL
    if current_user.is_owner:
        # Check form first (POST), then URL (GET)
        brand_id = request.form.get('brand_id', type=int) or request.args.get('brand_id', type=int)
        if not brand_id and brands:
            brand_id = brands[0].id  # Default to first brand
        brand = Brand.query.get(brand_id) if brand_id else None
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand

    if not brand:
        flash('يرجى اختيار البراند', 'warning')
        return redirect(url_for('classes.index'))

    # Populate choices
    # Branches for this brand (owner can select any branch)
    branches = Branch.query.filter_by(brand_id=brand_id, is_active=True).all()
    form.branch_id.choices = [(0, '-- جميع الفروع --')] + [(b.id, b.name) for b in branches]
    
    service_types = ServiceType.query.filter_by(brand_id=brand_id, is_active=True).all()
    form.service_type_id.choices = [(st.id, st.name) for st in service_types]

    trainers = User.query.filter_by(brand_id=brand_id, is_trainer=True, is_active=True).all()
    form.trainer_id.choices = [(0, '-- بدون مدرب --')] + [(t.id, t.name) for t in trainers]

    if form.validate_on_submit():
        weekday_mask, weekdays = _parse_weekdays_from_request()
        if not weekdays:
            flash('اختر يوم واحد على الأقل من أيام الأسبوع', 'danger')
            return render_template('classes/form.html', form=form, brand=brand,
                                   brands=brands, branches=branches,
                                   weekday_choices=ARABIC_WEEKDAYS, selected_weekdays=[])
        if form.end_date.data < form.start_date.data:
            flash('تاريخ النهاية يجب أن يكون بعد تاريخ البداية', 'danger')
            return render_template('classes/form.html', form=form, brand=brand,
                                   brands=brands, branches=branches,
                                   weekday_choices=ARABIC_WEEKDAYS, selected_weekdays=weekdays)

        gym_class = GymClass(
            brand_id=brand_id,
            branch_id=form.branch_id.data if form.branch_id.data else None,
            name=form.name.data,
            service_type_id=form.service_type_id.data,
            trainer_id=form.trainer_id.data if form.trainer_id.data else None,
            description=form.description.data,
            day_of_week=weekdays[0],  # legacy mirror
            weekday_mask=weekday_mask,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            capacity=form.capacity.data,
            price=form.price.data or 0,
            trainer_fee_per_session=form.trainer_fee_per_session.data or 0,
            status=form.status.data or 'active',
            is_active=form.is_active.data,
        )
        db.session.add(gym_class)
        db.session.flush()
        n_sessions = gym_class.generate_sessions()
        db.session.commit()

        flash(f'تم إنشاء الكلاس بنجاح — {n_sessions} حصة مجدولة', 'success')
        return redirect(url_for('classes.index', brand_id=brand_id))

    return render_template('classes/form.html', form=form, brand=brand,
                           brands=brands, branches=branches,
                           weekday_choices=ARABIC_WEEKDAYS, selected_weekdays=[])


@classes_bp.route('/<int:class_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(class_id):
    """Edit class"""
    if not (current_user.role and current_user.role.can_manage_classes):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    gym_class = GymClass.query.get_or_404(class_id)

    # Check access
    if not check_entity_access(gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    form = GymClassForm(obj=gym_class)

    # Populate choices
    branches = Branch.query.filter_by(brand_id=gym_class.brand_id, is_active=True).all()
    form.branch_id.choices = [(0, '-- جميع الفروع --')] + [(b.id, b.name) for b in branches]
    
    service_types = ServiceType.query.filter_by(brand_id=gym_class.brand_id, is_active=True).all()
    form.service_type_id.choices = [(st.id, st.name) for st in service_types]

    trainers = User.query.filter_by(brand_id=gym_class.brand_id, is_trainer=True, is_active=True).all()
    form.trainer_id.choices = [(0, '-- بدون مدرب --')] + [(t.id, t.name) for t in trainers]

    if form.validate_on_submit():
        weekday_mask, weekdays = _parse_weekdays_from_request()
        if not weekdays:
            flash('اختر يوم واحد على الأقل من أيام الأسبوع', 'danger')
            return render_template('classes/form.html', form=form, gym_class=gym_class,
                                   brand=Brand.query.get(gym_class.brand_id),
                                   weekday_choices=ARABIC_WEEKDAYS,
                                   selected_weekdays=gym_class.weekdays_list())
        if form.end_date.data < form.start_date.data:
            flash('تاريخ النهاية يجب أن يكون بعد تاريخ البداية', 'danger')
            return render_template('classes/form.html', form=form, gym_class=gym_class,
                                   brand=Brand.query.get(gym_class.brand_id),
                                   weekday_choices=ARABIC_WEEKDAYS,
                                   selected_weekdays=weekdays)

        schedule_changed = (
            gym_class.start_date != form.start_date.data
            or gym_class.end_date != form.end_date.data
            or (gym_class.weekday_mask or 0) != weekday_mask
        )

        gym_class.name = form.name.data
        gym_class.branch_id = form.branch_id.data if form.branch_id.data else None
        gym_class.service_type_id = form.service_type_id.data
        gym_class.trainer_id = form.trainer_id.data if form.trainer_id.data else None
        gym_class.description = form.description.data
        gym_class.day_of_week = weekdays[0]
        gym_class.weekday_mask = weekday_mask
        gym_class.start_time = form.start_time.data
        gym_class.end_time = form.end_time.data
        gym_class.start_date = form.start_date.data
        gym_class.end_date = form.end_date.data
        gym_class.capacity = form.capacity.data
        gym_class.price = form.price.data or 0
        gym_class.trainer_fee_per_session = form.trainer_fee_per_session.data or 0
        gym_class.status = form.status.data or 'active'
        gym_class.is_active = form.is_active.data

        n_created = 0
        n_cancelled_sessions = 0
        n_cancelled_bookings = 0
        if schedule_changed:
            today = date.today()
            # New scheduled sessions that match the new mask/range → insert if missing
            n_created = gym_class.generate_sessions()
            # Existing scheduled sessions that no longer fit → cancel (future only)
            new_weekdays = set(gym_class.weekdays_list())
            future_sessions = ClassSession.query.filter(
                ClassSession.class_id == gym_class.id,
                ClassSession.session_date >= today,
                ClassSession.status == 'scheduled',
            ).all()
            for s in future_sessions:
                arabic_dow = (s.session_date.weekday() + 2) % 7
                out_of_range = not (gym_class.start_date <= s.session_date <= gym_class.end_date)
                if out_of_range or arabic_dow not in new_weekdays:
                    s.status = 'cancelled'
                    n_cancelled_sessions += 1
                    for b in ClassBooking.query.filter_by(session_id=s.id).all():
                        if b.status == 'booked':
                            b.status = 'cancelled'
                            b.cancelled_at = datetime.utcnow()
                            n_cancelled_bookings += 1

        db.session.commit()

        msg = 'تم تحديث الكلاس بنجاح'
        if schedule_changed:
            msg += f' — +{n_created} حصة جديدة / {n_cancelled_sessions} حصة ملغاة / {n_cancelled_bookings} حجز ملغى'
        flash(msg, 'success')
        return redirect(url_for('classes.index'))

    return render_template('classes/form.html', form=form, gym_class=gym_class,
                           brand=Brand.query.get(gym_class.brand_id),
                           weekday_choices=ARABIC_WEEKDAYS,
                           selected_weekdays=gym_class.weekdays_list())


@classes_bp.route('/<int:class_id>/delete', methods=['POST'])
@login_required
def delete(class_id):
    """Delete class"""
    if not (current_user.role and current_user.role.can_manage_classes):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    gym_class = GymClass.query.get_or_404(class_id)

    # Check access
    if not check_entity_access(gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    # Refuse if there are upcoming bookings
    future_bookings = gym_class.bookings.filter(
        ClassBooking.booking_date >= date.today(),
        ClassBooking.status == 'booked'
    ).count()
    if future_bookings > 0:
        flash(f'لا يمكن حذف الكلاس - يوجد {future_bookings} حجز مستقبلي', 'danger')
        return redirect(url_for('classes.index'))

    # Historical bookings (past, attended, cancelled, no_show) reference this
    # class with class_id NOT NULL. SQLAlchemy's default behaviour on a dynamic
    # relationship is to set the FK to NULL on the children, which violates
    # the NOT NULL constraint. Wipe them in one bulk DELETE before removing
    # the parent.
    total_bookings = gym_class.bookings.count()
    gym_class.bookings.delete(synchronize_session=False)

    db.session.delete(gym_class)
    db.session.commit()

    if total_bookings:
        flash(f'تم حذف الكلاس و {total_bookings} حجز مرتبط به', 'success')
    else:
        flash('تم حذف الكلاس', 'success')
    return redirect(url_for('classes.index'))


@classes_bp.route('/<int:class_id>/bookings')
@login_required
def bookings(class_id):
    """View class bookings"""
    gym_class = GymClass.query.get_or_404(class_id)

    # Check access
    if not check_entity_access(gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    booking_date = request.args.get('date')
    if booking_date:
        booking_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
    else:
        booking_date = date.today()

    bookings = gym_class.get_bookings_for_date(booking_date)
    available_spots = gym_class.get_available_spots(booking_date)

    return render_template('classes/bookings.html',
                         gym_class=gym_class,
                         bookings=bookings,
                         booking_date=booking_date,
                         available_spots=available_spots)


@classes_bp.route('/<int:class_id>/book', methods=['POST'])
@login_required
def book(class_id):
    """Book a member for a class"""
    gym_class = GymClass.query.get_or_404(class_id)

    # Check access
    if not check_entity_access(gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    member_id = request.form.get('member_id', type=int)
    booking_date_str = request.form.get('booking_date')

    if not member_id or not booking_date_str:
        flash('بيانات غير مكتملة', 'danger')
        return redirect(url_for('classes.bookings', class_id=class_id))

    booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()

    # Check member
    member = Member.query.get(member_id)
    if not member:
        flash('العضو غير موجود', 'danger')
        return redirect(url_for('classes.bookings', class_id=class_id, date=booking_date_str))

    # Create booking
    booking, message = ClassBooking.book_class(class_id, member_id, booking_date)

    if booking:
        flash(message, 'success')
    else:
        flash(message, 'danger')

    return redirect(url_for('classes.bookings', class_id=class_id, date=booking_date_str))


@classes_bp.route('/bookings/<int:booking_id>/checkin', methods=['POST'])
@login_required
def checkin(booking_id):
    """Check in a booking"""
    booking = ClassBooking.query.get_or_404(booking_id)

    # Check access
    if not check_entity_access(booking.gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    booking.check_in(current_user.id)
    flash('تم تسجيل الحضور', 'success')

    return redirect(url_for('classes.bookings',
                          class_id=booking.class_id,
                          date=booking.booking_date.strftime('%Y-%m-%d')))


@classes_bp.route('/bookings/<int:booking_id>/cancel', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """Cancel a booking"""
    booking = ClassBooking.query.get_or_404(booking_id)

    # Check access
    if not check_entity_access(booking.gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    booking.cancel()
    flash('تم إلغاء الحجز', 'success')

    return redirect(url_for('classes.bookings',
                          class_id=booking.class_id,
                          date=booking.booking_date.strftime('%Y-%m-%d')))


    # GYM-53 — the old week-grid /classes/calendar route (which rendered
    # classes/calendar.html) was replaced by the month-grid version defined
    # earlier in this file. Endpoint name kept, template swapped.


# API for member search
@classes_bp.route('/api/search-members')
@login_required
def search_members():
    """Search members for booking.

    Same field coverage as /members search (name / phone / email /
    member_import_id, plus fingerprint_id when numeric).

    If `class_id` is passed, the result is scoped to that class's
    brand AND branch. Otherwise it falls back to the current user's
    brand/branch scope via apply_branch_filter.
    """
    q = (request.args.get('q') or '').strip()
    class_id = request.args.get('class_id', type=int)

    if len(q) < 2:
        return jsonify([])

    members_query = Member.query

    # Scope: prefer the class's brand/branch if provided
    if class_id:
        cls = GymClass.query.get(class_id)
        if not cls or not check_entity_access(cls):
            return jsonify([])
        members_query = members_query.filter(Member.brand_id == cls.brand_id)
        if cls.branch_id:
            members_query = members_query.filter(
                db.or_(Member.branch_id == cls.branch_id, Member.branch_id.is_(None))
            )
    else:
        members_query = apply_branch_filter(members_query, Member)

    clauses = [
        Member.name.ilike(f'%{q}%'),
        Member.phone.ilike(f'%{q}%'),
        Member.email.ilike(f'%{q}%'),
        Member.member_import_id.ilike(f'%{q}%'),
    ]
    if q.isdigit():
        clauses.append(Member.fingerprint_id == int(q))

    members = members_query.filter(db.or_(*clauses)).limit(15).all()

    return jsonify([{
        'id': m.id,
        'name': m.name,
        'phone': m.phone or '',
        'member_import_id': m.member_import_id or '',
    } for m in members])


# ─── GYM-62 — class enrollment (subscribe a member to a class course) ──────

def _get_or_create_class_plan(gym_class):
    """Return a Plan tied to this class so /fp/access-list can find it via
    Subscription.plan.requires_class_booking=True. Idempotent per class."""
    from app.models.subscription import Plan
    name = f'اشتراك كلاس {gym_class.name}'
    plan = Plan.query.filter_by(brand_id=gym_class.brand_id, name=name).first()
    if plan:
        return plan
    duration = 30
    if gym_class.start_date and gym_class.end_date:
        duration = max(1, (gym_class.end_date - gym_class.start_date).days + 1)
    plan = Plan(
        brand_id=gym_class.brand_id,
        service_type_id=gym_class.service_type_id,
        name=name,
        description=f'خطة تلقائية للكلاس {gym_class.name}',
        duration_days=duration,
        price=gym_class.price or 0,
        sessions_count=0,
        requires_class_booking=True,
        is_active=True,
    )
    db.session.add(plan)
    db.session.flush()
    return plan


@classes_bp.route('/<int:class_id>/enroll', methods=['GET', 'POST'])
@login_required
def enroll(class_id):
    """Enroll a member in a class course. Creates: ClassEnrollment +
    auto-provisioned Plan + Subscription + Invoice + Income + one ClassBooking
    per matching future ClassSession in the enrollment window."""
    from app.models.subscription import Plan, Subscription, SubscriptionPayment
    from app.models.finance import Income, Invoice
    from app.models.fingerprint import DeviceCommand
    import json

    if not current_user.can_manage_members:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    gym_class = GymClass.query.get_or_404(class_id)
    if not check_entity_access(gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    if gym_class.status != 'active':
        flash('الكلاس ليس نشطاً — لا يمكن التسجيل فيه', 'warning')
        return redirect(url_for('classes.index'))

    today = date.today()
    if gym_class.end_date and gym_class.end_date < today:
        flash('الكلاس منتهي — لا يمكن التسجيل فيه', 'warning')
        return redirect(url_for('classes.index'))

    # Capacity check
    active_enrolled = ClassEnrollment.query.filter_by(
        class_id=gym_class.id, status='active'
    ).count()
    if gym_class.capacity and active_enrolled >= gym_class.capacity:
        flash(f'الكلاس ممتلئ — {gym_class.capacity} مشترك', 'warning')
        return redirect(url_for('classes.index'))

    if request.method == 'GET':
        return render_template(
            'classes/enroll.html',
            gym_class=gym_class,
            active_enrolled=active_enrolled,
            today=today,
        )

    # POST
    member_id = request.form.get('member_id', type=int)
    if not member_id:
        flash('يرجى اختيار عضو', 'danger')
        return redirect(url_for('classes.enroll', class_id=class_id))
    member = Member.query.get(member_id)
    if not member or member.brand_id != gym_class.brand_id:
        flash('العضو غير موجود أو خارج نطاق البراند', 'danger')
        return redirect(url_for('classes.enroll', class_id=class_id))

    # Duplicate enrollment guard
    existing = ClassEnrollment.query.filter_by(
        class_id=gym_class.id, member_id=member.id, status='active'
    ).first()
    if existing:
        flash('العضو مسجّل مسبقاً في هذا الكلاس', 'warning')
        return redirect(url_for('classes.index'))

    try:
        total_amount = float(request.form.get('total_amount') or gym_class.price or 0)
        paid_amount = float(request.form.get('paid_amount') or 0)
    except (TypeError, ValueError):
        flash('قيمة سعر غير صالحة', 'danger')
        return redirect(url_for('classes.enroll', class_id=class_id))
    if paid_amount < 0 or total_amount < 0 or paid_amount > total_amount:
        flash('المدفوع لا يمكن أن يتجاوز الإجمالي', 'danger')
        return redirect(url_for('classes.enroll', class_id=class_id))

    payment_method = request.form.get('payment_method') or 'cash'
    notes = request.form.get('notes') or None
    enroll_start = today
    enroll_end = gym_class.end_date

    # Future sessions inside enrollment window
    future_sessions = ClassSession.query.filter(
        ClassSession.class_id == gym_class.id,
        ClassSession.session_date >= enroll_start,
        ClassSession.session_date <= enroll_end,
        ClassSession.status == 'scheduled',
    ).order_by(ClassSession.session_date).all()
    sessions_total = len(future_sessions)

    plan = _get_or_create_class_plan(gym_class)

    subscription = Subscription(
        member_id=member.id,
        plan_id=plan.id,
        brand_id=gym_class.brand_id,
        branch_id=gym_class.branch_id or member.branch_id or current_user.branch_id,
        service_type_id=gym_class.service_type_id,
        start_date=enroll_start,
        end_date=enroll_end,
        original_end_date=enroll_end,
        sessions_total=sessions_total,
        sessions_consumed=0,
        total_amount=total_amount,
        paid_amount=paid_amount,
        remaining_amount=total_amount - paid_amount,
        status='active',
        notes=notes,
        created_by=current_user.id,
    )
    db.session.add(subscription)
    db.session.flush()

    enrollment = ClassEnrollment(
        class_id=gym_class.id,
        member_id=member.id,
        subscription_id=subscription.id,
        start_date=enroll_start,
        end_date=enroll_end,
        sessions_total=sessions_total,
        total_amount=total_amount,
        paid_amount=paid_amount,
        status='active',
        notes=notes,
        created_by=current_user.id,
    )
    db.session.add(enrollment)
    db.session.flush()

    # Activate member if inactive
    if not member.is_active:
        member.is_active = True

    invoice = None
    if paid_amount > 0:
        payment = SubscriptionPayment(
            subscription_id=subscription.id,
            brand_id=gym_class.brand_id,
            amount=paid_amount,
            payment_method=payment_method,
            created_by=current_user.id,
        )
        db.session.add(payment)
        db.session.flush()

        income = Income(
            brand_id=gym_class.brand_id,
            branch_id=subscription.branch_id,
            subscription_id=subscription.id,
            service_type_id=gym_class.service_type_id,
            amount=paid_amount,
            type='class_subscription',
            payment_method=payment_method,
            date=today,
            created_by=current_user.id,
        )
        db.session.add(income)

        branch_for_invoice = gym_class.branch or (member.branch if hasattr(member, 'branch') else None)
        invoice = Invoice(
            brand_id=gym_class.brand_id,
            branch_id=getattr(branch_for_invoice, 'id', None),
            branch_name=getattr(branch_for_invoice, 'name', None),
            branch_phone=getattr(branch_for_invoice, 'phone', None),
            branch_address=getattr(branch_for_invoice, 'address', None),
            subscription_id=subscription.id,
            payment_id=payment.id,
            member_id=member.id,
            invoice_number=Invoice.generate_invoice_number(gym_class.brand_id),
            member_name=member.name,
            member_phone=member.phone,
            member_email=member.email,
            plan_name=f'اشتراك كلاس {gym_class.name}',
            service_type_name=(gym_class.service_type.name if gym_class.service_type else None),
            duration_text=f'{sessions_total} حصة',
            original_price=total_amount,
            discount=0,
            subtotal=total_amount,
            tax_rate=0,
            tax_amount=0,
            total_amount=total_amount,
            amount_paid=paid_amount,
            payment_method=payment_method,
            notes=notes,
            created_by=current_user.id,
        )
        db.session.add(invoice)
        db.session.flush()
        enrollment.invoice_id = invoice.id

    # Pre-generate ClassBooking rows so /fp/access-list works unchanged.
    for s in future_sessions:
        db.session.add(ClassBooking(
            class_id=gym_class.id,
            member_id=member.id,
            subscription_id=subscription.id,
            session_id=s.id,
            enrollment_id=enrollment.id,
            booking_date=s.session_date,
            status='booked',
        ))

    db.session.commit()

    # Dispatch unblock to fingerprint device if member is enrolled
    if member.fingerprint_id and member.branch and getattr(member.branch, 'uses_fingerprint', False):
        unblock_cmd = DeviceCommand(
            brand_id=member.brand_id,
            command_type='unblock_member',
            target_emp_id=member.fingerprint_id,
            member_id=member.id,
            command_data=json.dumps({'end_date': subscription.end_date.isoformat()}),
            status='pending',
        )
        db.session.add(unblock_cmd)
        db.session.commit()

    flash(f'تم تسجيل {member.name} في {gym_class.name} — {sessions_total} حصة', 'success')
    return redirect(url_for('members.view', member_id=member.id))


@classes_bp.route('/<int:class_id>/enrollments/<int:enrollment_id>/cancel', methods=['POST'])
@login_required
def cancel_enrollment(class_id, enrollment_id):
    """Cancel a class enrollment. Cancels future bookings, expires the linked
    subscription, and creates a pro-rata Refund row."""
    from app.models.finance import Refund

    if not current_user.can_manage_members:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    enrollment = ClassEnrollment.query.get_or_404(enrollment_id)
    gym_class = enrollment.gym_class
    if not check_entity_access(gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))
    if enrollment.status != 'active':
        flash('التسجيل ليس نشطاً', 'warning')
        return redirect(url_for('members.view', member_id=enrollment.member_id))

    today = date.today()
    # Future bookings → cancel
    future_bookings = ClassBooking.query.filter(
        ClassBooking.enrollment_id == enrollment.id,
        ClassBooking.booking_date >= today,
        ClassBooking.status.in_(['booked', 'attended']),
    ).all()
    future_sessions_count = 0
    for b in future_bookings:
        if b.status == 'booked':
            b.status = 'cancelled'
            b.cancelled_at = datetime.utcnow()
            future_sessions_count += 1

    # Pro-rata refund
    refund_amount = 0
    if enrollment.sessions_total and float(enrollment.paid_amount or 0) > 0:
        refund_amount = round(
            (future_sessions_count / enrollment.sessions_total) * float(enrollment.paid_amount),
            2,
        )
    enrollment.refund_amount = refund_amount
    enrollment.status = 'cancelled'
    enrollment.cancelled_at = datetime.utcnow()

    # Expire subscription immediately so /fp/access-list blocks
    if enrollment.subscription:
        enrollment.subscription.end_date = today - timedelta(days=1)
        enrollment.subscription.status = 'cancelled'

    # Refund row (uses existing Refund model keyed by subscription_id)
    if refund_amount > 0 and enrollment.subscription_id:
        db.session.add(Refund(
            brand_id=gym_class.brand_id,
            subscription_id=enrollment.subscription_id,
            member_id=enrollment.member_id,
            amount=refund_amount,
            reason=f'إلغاء اشتراك كلاس {gym_class.name} — {future_sessions_count}/{enrollment.sessions_total} حصة متبقية',
            refund_date=today,
            created_by=current_user.id,
        ))

    db.session.commit()

    flash(
        f'تم إلغاء التسجيل — {future_sessions_count} حصة ملغاة، استرداد {refund_amount:.2f} ر.س',
        'success',
    )
    return redirect(url_for('members.view', member_id=enrollment.member_id))


@classes_bp.route('/<int:class_id>/dashboard')
@login_required
def dashboard(class_id):
    """GYM-62 — per-class dashboard: enrollment, sessions, revenue/cost/profit,
    per-session attendance and per-member attendance history."""
    from app.models.finance import Refund
    from sqlalchemy import func

    gym_class = GymClass.query.get_or_404(class_id)
    if not check_entity_access(gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    today = date.today()

    enrollments = ClassEnrollment.query.filter_by(class_id=class_id).order_by(
        ClassEnrollment.created_at.desc()
    ).all()
    active_enrollments = [e for e in enrollments if e.status == 'active']
    attendees_count = len(active_enrollments)
    remaining_slots = (gym_class.capacity - attendees_count) if gym_class.capacity else None

    sessions_all = ClassSession.query.filter_by(class_id=class_id).order_by(
        ClassSession.session_date
    ).all()
    sessions_done = sum(1 for s in sessions_all if s.status == 'held')
    sessions_remaining = sum(1 for s in sessions_all
                             if s.status == 'scheduled' and s.session_date >= today)
    sessions_cancelled = sum(1 for s in sessions_all if s.status == 'cancelled')

    # Revenue = total paid − refunds (per enrollment)
    revenue = sum(float(e.paid_amount or 0) for e in enrollments
                  if e.status in ('active', 'completed'))
    refunds_total = sum(float(e.refund_amount or 0) for e in enrollments)
    revenue_net = revenue - refunds_total
    cost = sessions_done * float(gym_class.trainer_fee_per_session or 0)
    profit = revenue_net - cost

    # Per-session breakdown
    session_stats = []
    for s in sessions_all:
        bookings = ClassBooking.query.filter_by(session_id=s.id).all()
        n_attended = sum(1 for b in bookings if b.status == 'attended')
        n_no_show = sum(1 for b in bookings if b.status == 'no_show')
        n_booked = sum(1 for b in bookings if b.status == 'booked')
        n_cancelled = sum(1 for b in bookings if b.status == 'cancelled')
        eligible = n_attended + n_no_show
        pct = (n_attended / eligible * 100) if eligible else None
        session_stats.append({
            'session': s,
            'attended': n_attended,
            'no_show': n_no_show,
            'booked': n_booked,
            'cancelled': n_cancelled,
            'pct': pct,
        })

    # Per-member breakdown
    member_stats = []
    for e in enrollments:
        bks = ClassBooking.query.filter_by(enrollment_id=e.id).all()
        n_attended = sum(1 for b in bks if b.status == 'attended')
        n_no_show = sum(1 for b in bks if b.status == 'no_show')
        n_upcoming = sum(1 for b in bks
                         if b.status == 'booked' and b.booking_date >= today)
        eligible = n_attended + n_no_show
        pct = (n_attended / eligible * 100) if eligible else None
        member_stats.append({
            'enrollment': e, 'member': e.member,
            'attended': n_attended, 'no_show': n_no_show,
            'upcoming': n_upcoming, 'pct': pct,
        })

    return render_template(
        'classes/dashboard.html',
        gym_class=gym_class,
        today=today,
        attendees_count=attendees_count,
        remaining_slots=remaining_slots,
        sessions_done=sessions_done,
        sessions_remaining=sessions_remaining,
        sessions_cancelled=sessions_cancelled,
        sessions_total=len(sessions_all),
        revenue=revenue,
        refunds_total=refunds_total,
        revenue_net=revenue_net,
        cost=cost,
        profit=profit,
        session_stats=session_stats,
        member_stats=member_stats,
    )
