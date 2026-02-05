from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import SelectField, DateField, TextAreaField, HiddenField, TimeField, IntegerField, StringField
from wtforms.validators import DataRequired, Optional, NumberRange
from datetime import date, datetime, timedelta

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.schedule import ClassSession, Booking
from app.models.service import ServiceType
from app.utils.decorators import members_required
from app.utils.helpers import pagination_args

bookings_bp = Blueprint('bookings', __name__)


class ClassSessionForm(FlaskForm):
    """Class/Session form"""
    name = StringField('اسم الحصة', validators=[DataRequired()])
    service_type_id = SelectField('نوع الخدمة', coerce=int, validators=[DataRequired()])
    day_of_week = SelectField('اليوم', choices=[
        (0, 'السبت'),
        (1, 'الأحد'),
        (2, 'الإثنين'),
        (3, 'الثلاثاء'),
        (4, 'الأربعاء'),
        (5, 'الخميس'),
        (6, 'الجمعة')
    ], coerce=int, validators=[DataRequired()])
    start_time = TimeField('وقت البداية', validators=[DataRequired()])
    end_time = TimeField('وقت النهاية', validators=[DataRequired()])
    capacity = IntegerField('الطاقة الاستيعابية', validators=[DataRequired(), NumberRange(min=1, max=100)])
    trainer_id = SelectField('المدرب', coerce=int, validators=[Optional()])


class BookingForm(FlaskForm):
    """Booking form"""
    member_id = HiddenField('ID العضو')
    class_session_id = SelectField('الحصة', coerce=int, validators=[DataRequired()])
    session_date = DateField('التاريخ', default=date.today, validators=[DataRequired()])
    notes = TextAreaField('ملاحظات')


# ==================== Class/Session Management ====================

@bookings_bp.route('/sessions')
@login_required
@members_required
def sessions_list():
    """List all class sessions"""
    page, per_page = pagination_args(request)
    session_type = request.args.get('type', '')

    # Base query - filter by brand access
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = ClassSession.query.filter_by(brand_id=brand_id)
        else:
            query = ClassSession.query
    else:
        query = ClassSession.query.filter_by(brand_id=current_user.brand_id)

    # Type filter
    if session_type:
        query = query.filter_by(session_type=session_type)

    # Active only
    query = query.filter_by(is_active=True)

    # Pagination
    sessions = query.order_by(
        ClassSession.day_of_week,
        ClassSession.start_time
    ).paginate(page=page, per_page=per_page, error_out=False)

    # Get brands for filter (owner only)
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('bookings/sessions_list.html',
                          sessions=sessions,
                          brands=brands,
                          session_type=session_type)


@bookings_bp.route('/sessions/create', methods=['GET', 'POST'])
@login_required
@members_required
def create_session():
    """Create new class/session"""
    # Allow: admins, brand managers, and receptionists
    can_create = (
        current_user.can_manage_users or 
        current_user.is_brand_manager or 
        (current_user.role and current_user.role.name == 'موظف استقبال')
    )
    if not can_create:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('bookings.sessions_list'))

    form = ClassSessionForm()

    # Get service types for dropdown
    if current_user.can_view_all_brands:
        service_types = ServiceType.query.filter_by(is_active=True).all()
    else:
        service_types = ServiceType.query.filter_by(
            brand_id=current_user.brand_id,
            is_active=True
        ).all()
    form.service_type_id.choices = [(s.id, s.name) for s in service_types]

    # Get trainers for dropdown - always set default choice first
    form.trainer_id.choices = [(0, 'بدون مدرب')]
    
    from app.models.user import User, Role
    trainer_role = Role.query.filter_by(name_en='coach').first()
    if trainer_role:
        if current_user.can_view_all_brands:
            trainers = User.query.filter_by(role_id=trainer_role.id, is_active=True).all()
        else:
            trainers = User.query.filter_by(
                role_id=trainer_role.id,
                brand_id=current_user.brand_id,
                is_active=True
            ).all()
        form.trainer_id.choices += [(t.id, t.name) for t in trainers]

    if form.validate_on_submit():
        session = ClassSession(
            brand_id=current_user.brand_id,
            branch_id=current_user.branch_id,
            service_type_id=form.service_type_id.data,
            name=form.name.data,
            day_of_week=form.day_of_week.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            capacity=form.capacity.data,
            trainer_id=form.trainer_id.data if form.trainer_id.data != 0 else None
        )
        db.session.add(session)
        db.session.commit()

        flash('تم إنشاء الحصة بنجاح', 'success')
        return redirect(url_for('bookings.sessions_list'))

    return render_template('bookings/session_form.html', form=form)


# ==================== Booking Management ====================

@bookings_bp.route('/')
@login_required
@members_required
def index():
    """List all bookings"""
    page, per_page = pagination_args(request)
    status = request.args.get('status', '')
    session_date = request.args.get('date', date.today().isoformat())

    try:
        filter_date = date.fromisoformat(session_date)
    except:
        filter_date = date.today()

    # Base query - filter by brand access (join with gym_classes)
    query = Booking.query.join(ClassSession, Booking.class_id == ClassSession.id)

    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = query.filter(ClassSession.brand_id == brand_id)
    else:
        query = query.filter(ClassSession.brand_id == current_user.brand_id)

    # Date filter
    query = query.filter(Booking.booking_date == filter_date)

    # Status filter
    if status:
        query = query.filter_by(status=status)

    # Pagination
    bookings = query.order_by(Booking.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter (owner only)
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('bookings/index.html',
                          bookings=bookings,
                          brands=brands,
                          status=status,
                          session_date=session_date)


@bookings_bp.route('/create', methods=['GET', 'POST'])
@login_required
@members_required
def create():
    """Create new booking"""
    member_id = request.args.get('member_id', type=int)

    form = BookingForm()

    # Populate sessions dropdown
    if current_user.can_view_all_brands:
        sessions = ClassSession.query.filter_by(is_active=True).all()
    else:
        sessions = ClassSession.query.filter_by(
            brand_id=current_user.brand_id,
            is_active=True
        ).all()

    form.class_session_id.choices = [
        (s.id, f'{s.name} - {s.day_name_arabic} {s.time_range}') for s in sessions
    ]

    # If member_id provided, validate access
    member = None
    if member_id:
        member = Member.query.get_or_404(member_id)
        if not current_user.can_access_brand(member.brand_id):
            flash('ليس لديك صلاحية', 'danger')
            return redirect(url_for('bookings.index'))
        form.member_id.data = member_id

    if form.validate_on_submit():
        # Get member
        if form.member_id.data:
            member = Member.query.get(int(form.member_id.data))
        else:
            flash('يرجى اختيار العضو', 'warning')
            return redirect(url_for('members.index'))

        # Get session
        session = ClassSession.query.get(form.class_session_id.data)

        # Check capacity
        if not session.has_available_slots(form.session_date.data):
            flash('الحصة ممتلئة', 'warning')
            return render_template('bookings/create.html', form=form, member=member)

        # Check for duplicate booking
        existing = Booking.query.filter_by(
            member_id=member.id,
            class_id=session.id,
            booking_date=form.session_date.data,
            status='confirmed'
        ).first()

        if existing:
            flash('العضو محجوز بالفعل في هذه الحصة', 'warning')
            return render_template('bookings/create.html', form=form, member=member)

        # Create booking
        booking = Booking(
            member_id=member.id,
            class_id=session.id,
            booking_date=form.session_date.data,
            notes=form.notes.data
        )
        db.session.add(booking)
        db.session.commit()

        flash('تم إنشاء الحجز بنجاح', 'success')

        if member:
            return redirect(url_for('members.view', member_id=member.id))
        return redirect(url_for('bookings.index'))

    return render_template('bookings/create.html', form=form, member=member)


@bookings_bp.route('/<int:booking_id>/cancel', methods=['POST'])
@login_required
@members_required
def cancel(booking_id):
    """Cancel a booking"""
    booking = Booking.query.get_or_404(booking_id)

    if not current_user.can_access_brand(booking.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('bookings.index'))

    if booking.status == 'cancelled':
        flash('الحجز ملغي بالفعل', 'warning')
    else:
        booking.status = 'cancelled'
        booking.cancelled_at = datetime.utcnow()
        booking.cancelled_by = current_user.id
        db.session.commit()
        flash('تم إلغاء الحجز', 'success')

    return redirect(url_for('bookings.index'))
