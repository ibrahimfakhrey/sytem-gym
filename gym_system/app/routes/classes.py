"""Classes/Booking routes"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerField, TimeField, BooleanField
from wtforms.validators import DataRequired, Optional, NumberRange
from datetime import datetime, date, timedelta

from app import db
from app.models import Brand, Branch, Member, User, ServiceType, GymClass, ClassBooking
from app.utils.helpers import apply_branch_filter, check_entity_access

classes_bp = Blueprint('classes', __name__, url_prefix='/classes')


class GymClassForm(FlaskForm):
    """Form for creating/editing gym classes"""
    name = StringField('اسم الكلاس', validators=[DataRequired()])
    branch_id = SelectField('الفرع', coerce=int, validators=[Optional()])
    service_type_id = SelectField('نوع الخدمة', coerce=int, validators=[DataRequired()])
    trainer_id = SelectField('المدرب', coerce=int, validators=[Optional()])
    description = TextAreaField('الوصف', validators=[Optional()])
    day_of_week = SelectField('اليوم', coerce=int, choices=[
        (0, 'السبت'),
        (1, 'الأحد'),
        (2, 'الاثنين'),
        (3, 'الثلاثاء'),
        (4, 'الأربعاء'),
        (5, 'الخميس'),
        (6, 'الجمعة')
    ], validators=[DataRequired()])
    start_time = TimeField('وقت البداية', validators=[DataRequired()])
    end_time = TimeField('وقت النهاية', validators=[DataRequired()])
    capacity = IntegerField('السعة', validators=[DataRequired(), NumberRange(min=1, max=100)], default=20)
    is_active = BooleanField('نشط', default=True)


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

    # Group classes by day
    schedule = {i: [] for i in range(7)}
    for cls in classes:
        if cls.day_of_week is not None:
            schedule[cls.day_of_week].append(cls)

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
        gym_class = GymClass(
            brand_id=brand_id,
            branch_id=form.branch_id.data if form.branch_id.data else None,
            name=form.name.data,
            service_type_id=form.service_type_id.data,
            trainer_id=form.trainer_id.data if form.trainer_id.data else None,
            description=form.description.data,
            day_of_week=form.day_of_week.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            capacity=form.capacity.data,
            is_active=form.is_active.data
        )
        db.session.add(gym_class)
        db.session.commit()

        flash('تم إنشاء الكلاس بنجاح', 'success')
        return redirect(url_for('classes.index', brand_id=brand_id))

    return render_template('classes/form.html', form=form, brand=brand, brands=brands, branches=branches)


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
        gym_class.name = form.name.data
        gym_class.branch_id = form.branch_id.data if form.branch_id.data else None
        gym_class.service_type_id = form.service_type_id.data
        gym_class.trainer_id = form.trainer_id.data if form.trainer_id.data else None
        gym_class.description = form.description.data
        gym_class.day_of_week = form.day_of_week.data
        gym_class.start_time = form.start_time.data
        gym_class.end_time = form.end_time.data
        gym_class.capacity = form.capacity.data
        gym_class.is_active = form.is_active.data
        db.session.commit()

        flash('تم تحديث الكلاس بنجاح', 'success')
        return redirect(url_for('classes.index'))

    return render_template('classes/form.html', form=form, gym_class=gym_class, brand=Brand.query.get(gym_class.brand_id))


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
