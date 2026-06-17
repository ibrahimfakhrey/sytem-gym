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
from app.utils.helpers import pagination_args, apply_branch_filter, check_entity_access

bookings_bp = Blueprint('bookings', __name__)


class ClassSessionForm(FlaskForm):
    """Class/Session form"""
    name = StringField('اسم الحصة', validators=[DataRequired(message='اسم الحصة مطلوب')])
    service_type_id = SelectField('نوع الخدمة', coerce=int, validators=[DataRequired(message='يرجى اختيار نوع الخدمة')])
    day_of_week = SelectField('اليوم', choices=[
        (-1, '-- اختر اليوم --'),
        (0, 'السبت'),
        (1, 'الأحد'),
        (2, 'الإثنين'),
        (3, 'الثلاثاء'),
        (4, 'الأربعاء'),
        (5, 'الخميس'),
        (6, 'الجمعة')
    ], coerce=int, default=-1, validators=[NumberRange(min=0, max=6, message='يرجى اختيار اليوم')])
    start_time = TimeField('وقت البداية', validators=[DataRequired(message='وقت البداية مطلوب')])
    end_time = TimeField('وقت النهاية', validators=[DataRequired(message='وقت النهاية مطلوب')])
    capacity = IntegerField('الطاقة الاستيعابية', validators=[
        DataRequired(message='الطاقة الاستيعابية مطلوبة'),
        NumberRange(min=1, max=100, message='الطاقة الاستيعابية يجب أن تكون بين 1 و 100')
    ])
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
    service_type_id = request.args.get('type', type=int)

    # Base query - filter by brand/branch access
    query = apply_branch_filter(ClassSession.query, ClassSession)

    # Service-type filter (filter by actual ServiceType FK)
    if service_type_id:
        query = query.filter(ClassSession.service_type_id == service_type_id)

    # Active only
    query = query.filter_by(is_active=True)

    # Pagination
    sessions = query.order_by(
        ClassSession.day_of_week,
        ClassSession.start_time
    ).paginate(page=page, per_page=per_page, error_out=False)

    # Get brands and service types for filters
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()
        service_types = ServiceType.query.filter_by(is_active=True).all()
    elif current_user.brand_id:
        service_types = ServiceType.query.filter_by(
            brand_id=current_user.brand_id, is_active=True
        ).all()
    else:
        service_types = []

    return render_template('bookings/sessions_list.html',
                          sessions=sessions,
                          brands=brands,
                          service_types=service_types,
                          selected_service_type_id=service_type_id)


@bookings_bp.route('/sessions/create', methods=['GET', 'POST'])
@login_required
@members_required
def create_session():
    """Create new class/session"""
    # Allow: admins, brand managers, and receptionists
    can_create = (
        current_user.can_manage_users or 
        current_user.is_brand_manager or 
        (current_user.role and current_user.role.name_en == 'branch_receptionist')
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


# ==================== Class Bookings View ====================

@bookings_bp.route('/class/<int:class_id>')
@login_required
@members_required
def class_bookings(class_id):
    """View bookings for a specific class"""
    gym_class = ClassSession.query.get_or_404(class_id)
    
    # Check access
    if not current_user.can_view_all_brands and gym_class.brand_id != current_user.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('bookings.sessions_list'))
    
    page, per_page = pagination_args(request)
    status = request.args.get('status', '')
    session_date = request.args.get('date', '')
    
    # Base query
    query = Booking.query.filter(Booking.class_id == class_id)
    
    # Date filter
    if session_date:
        try:
            filter_date = date.fromisoformat(session_date)
            query = query.filter(Booking.booking_date == filter_date)
        except:
            pass
    
    # Status filter
    if status:
        query = query.filter(Booking.status == status)
    
    # Get stats
    total_bookings = Booking.query.filter(Booking.class_id == class_id).count()
    attended_count = Booking.query.filter(Booking.class_id == class_id, Booking.status == 'attended').count()
    booked_count = Booking.query.filter(Booking.class_id == class_id, Booking.status == 'booked').count()
    cancelled_count = Booking.query.filter(Booking.class_id == class_id, Booking.status == 'cancelled').count()
    
    # Pagination
    bookings = query.order_by(Booking.booking_date.desc(), Booking.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('bookings/class_bookings.html',
                          gym_class=gym_class,
                          bookings=bookings,
                          status=status,
                          session_date=session_date,
                          total_bookings=total_bookings,
                          attended_count=attended_count,
                          booked_count=booked_count,
                          cancelled_count=cancelled_count)


# ==================== Member Search API ====================

@bookings_bp.route('/api/search-members')
@login_required
@members_required
def search_members_api():
    """Search members for booking.

    Matches /members search coverage (name / phone / email /
    member_import_id, plus fingerprint_id when numeric), scoped to the
    current user's brand+branch via apply_branch_filter. If `class_id`
    is provided, the result is further constrained to that class's
    brand and branch.
    """
    from flask import jsonify
    from app.models.subscription import Subscription
    from app.models.classes import GymClass

    q = (request.args.get('q') or '').strip()
    class_id = request.args.get('class_id', type=int)

    if len(q) < 2:
        return jsonify([])

    try:
        members_query = apply_branch_filter(Member.query, Member)

        # Further scope to a specific class's brand/branch when provided
        if class_id:
            cls = GymClass.query.get(class_id)
            if not cls or not check_entity_access(cls):
                return jsonify([])
            members_query = members_query.filter(Member.brand_id == cls.brand_id)
            if cls.branch_id:
                members_query = members_query.filter(
                    db.or_(Member.branch_id == cls.branch_id, Member.branch_id.is_(None))
                )

        clauses = [
            Member.name.ilike(f'%{q}%'),
            Member.phone.ilike(f'%{q}%'),
            Member.email.ilike(f'%{q}%'),
            Member.member_import_id.ilike(f'%{q}%'),
        ]
        if q.isdigit():
            clauses.append(Member.fingerprint_id == int(q))

        members = members_query.filter(db.or_(*clauses)).limit(15).all()

        results = []
        for m in members:
            has_active = Subscription.query.filter(
                Subscription.member_id == m.id,
                Subscription.status == 'active',
                Subscription.is_deleted == False,  # GYM-32
            ).first() is not None
            results.append({
                'id': m.id,
                'name': m.name,
                'phone': m.phone or '',
                'has_active_subscription': has_active,
            })
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== Booking Management ====================

@bookings_bp.route('/')
@login_required
@members_required
def index():
    """List all bookings"""
    page, per_page = pagination_args(request)
    status = request.args.get('status', '')
    session_date = request.args.get('date', '')
    class_session_id = request.args.get('class_session_id', type=int)

    # Base query - filter by brand access (join with gym_classes)
    query = Booking.query.join(ClassSession, Booking.class_id == ClassSession.id)

    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = query.filter(ClassSession.brand_id == brand_id)
    else:
        query = query.filter(ClassSession.brand_id == current_user.brand_id)

    # Class session filter
    selected_class = None
    if class_session_id:
        query = query.filter(Booking.class_id == class_session_id)
        selected_class = ClassSession.query.get(class_session_id)

    # Date filter (only if provided)
    filter_date = None
    if session_date:
        try:
            filter_date = date.fromisoformat(session_date)
            query = query.filter(Booking.booking_date == filter_date)
        except:
            pass

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
                          session_date=session_date,
                          selected_class=selected_class,
                          class_session_id=class_session_id)


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
            flash('يرجى اختيار العضو أولاً', 'warning')
            return render_template('bookings/create.html', form=form, member=None)

        # Get session
        session = ClassSession.query.get(form.class_session_id.data)

        # Check capacity
        if session.is_full(form.session_date.data):
            flash('الحصة ممتلئة', 'warning')
            return render_template('bookings/create.html', form=form, member=member)

        # Check for duplicate booking — a class_bookings row defaults to
        # status='booked' and becomes 'attended' on check-in. Both states
        # count as an existing booking; only 'cancelled' / 'no_show' free up the slot.
        existing = Booking.query.filter(
            Booking.member_id == member.id,
            Booking.class_id == session.id,
            Booking.booking_date == form.session_date.data,
            Booking.status.in_(['booked', 'attended']),
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

    # Brand/branch lives on the parent class, not on ClassBooking itself.
    if not check_entity_access(booking.gym_class):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('bookings.index'))

    if booking.status == 'cancelled':
        flash('الحجز ملغي بالفعل', 'warning')
    else:
        booking.cancel()  # sets status='cancelled', cancelled_at, and commits
        flash('تم إلغاء الحجز', 'success')

    return redirect(url_for('bookings.index'))
