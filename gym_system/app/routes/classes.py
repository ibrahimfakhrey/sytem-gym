"""Classes/Booking routes"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerField, TimeField, BooleanField
from wtforms.validators import DataRequired, Optional, NumberRange
from datetime import datetime, date, timedelta

from app import db
from app.models import Brand, Branch, Member, User, ServiceType, GymClass, ClassBooking

classes_bp = Blueprint('classes', __name__, url_prefix='/classes')


class GymClassForm(FlaskForm):
    """Form for creating/editing gym classes"""
    name = StringField('اسم الكلاس', validators=[DataRequired()])
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
    query = GymClass.query.filter_by(brand_id=brand.id)
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


@classes_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new class"""
    if not (current_user.role and current_user.role.can_manage_classes):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    form = GymClassForm()

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            flash('يرجى اختيار البراند', 'warning')
            return redirect(url_for('admin.brands_list'))
        brand = Brand.query.get_or_404(brand_id)
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand

    # Populate choices
    service_types = ServiceType.query.filter_by(brand_id=brand_id, is_active=True).all()
    form.service_type_id.choices = [(st.id, st.name) for st in service_types]

    trainers = User.query.filter_by(brand_id=brand_id, is_trainer=True, is_active=True).all()
    form.trainer_id.choices = [(0, '-- بدون مدرب --')] + [(t.id, t.name) for t in trainers]

    if form.validate_on_submit():
        gym_class = GymClass(
            brand_id=brand_id,
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
        return redirect(url_for('classes.index'))

    return render_template('classes/form.html', form=form, brand=brand)


@classes_bp.route('/<int:class_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(class_id):
    """Edit class"""
    if not (current_user.role and current_user.role.can_manage_classes):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    gym_class = GymClass.query.get_or_404(class_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != gym_class.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    form = GymClassForm(obj=gym_class)

    # Populate choices
    service_types = ServiceType.query.filter_by(brand_id=gym_class.brand_id, is_active=True).all()
    form.service_type_id.choices = [(st.id, st.name) for st in service_types]

    trainers = User.query.filter_by(brand_id=gym_class.brand_id, is_trainer=True, is_active=True).all()
    form.trainer_id.choices = [(0, '-- بدون مدرب --')] + [(t.id, t.name) for t in trainers]

    if form.validate_on_submit():
        gym_class.name = form.name.data
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

    return render_template('classes/form.html', form=form, gym_class=gym_class, brand=gym_class.brand)


@classes_bp.route('/<int:class_id>/delete', methods=['POST'])
@login_required
def delete(class_id):
    """Delete class"""
    if not (current_user.role and current_user.role.can_manage_classes):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    gym_class = GymClass.query.get_or_404(class_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != gym_class.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    # Check for future bookings
    future_bookings = gym_class.bookings.filter(
        ClassBooking.booking_date >= date.today(),
        ClassBooking.status == 'booked'
    ).count()

    if future_bookings > 0:
        flash(f'لا يمكن حذف الكلاس - يوجد {future_bookings} حجز مستقبلي', 'danger')
        return redirect(url_for('classes.index'))

    db.session.delete(gym_class)
    db.session.commit()
    flash('تم حذف الكلاس', 'success')
    return redirect(url_for('classes.index'))


@classes_bp.route('/<int:class_id>/bookings')
@login_required
def bookings(class_id):
    """View class bookings"""
    gym_class = GymClass.query.get_or_404(class_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != gym_class.brand_id:
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
    if not current_user.is_owner and current_user.brand_id != gym_class.brand_id:
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
    if not current_user.is_owner and current_user.brand_id != booking.gym_class.brand_id:
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
    if not current_user.is_owner and current_user.brand_id != booking.gym_class.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('classes.index'))

    booking.cancel()
    flash('تم إلغاء الحجز', 'success')

    return redirect(url_for('classes.bookings',
                          class_id=booking.class_id,
                          date=booking.booking_date.strftime('%Y-%m-%d')))


@classes_bp.route('/calendar')
@login_required
def calendar():
    """Calendar view of classes"""
    if not (current_user.role and current_user.role.can_manage_classes):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            brands = Brand.query.filter_by(is_active=True).all()
            brand = brands[0] if brands else None
            brand_id = brand.id if brand else None
        else:
            brand = Brand.query.get(brand_id)
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand

    if not brand:
        flash('يرجى اختيار براند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Get classes for the week
    classes = GymClass.query.filter_by(brand_id=brand_id, is_active=True).all()

    # Build schedule grid
    schedule = {i: [] for i in range(7)}
    for cls in classes:
        if cls.day_of_week is not None:
            schedule[cls.day_of_week].append(cls)

    return render_template('classes/calendar.html', schedule=schedule, brand=brand)


# API for member search
@classes_bp.route('/api/search-members')
@login_required
def search_members():
    """Search members for booking"""
    query = request.args.get('q', '')
    brand_id = current_user.brand_id if not current_user.is_owner else request.args.get('brand_id', type=int)

    if not query or len(query) < 2:
        return jsonify([])

    members = Member.query.filter(
        Member.brand_id == brand_id,
        (Member.name.ilike(f'%{query}%') | Member.phone.ilike(f'%{query}%'))
    ).limit(10).all()

    return jsonify([{
        'id': m.id,
        'name': m.name,
        'phone': m.phone,
        'member_id': m.member_id
    } for m in members])
