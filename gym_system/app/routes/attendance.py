from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import date, datetime

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.attendance import MemberAttendance, EmployeeAttendance
from app.utils.helpers import pagination_args

attendance_bp = Blueprint('attendance', __name__)


@attendance_bp.route('/')
@login_required
def index():
    """Attendance check-in page"""
    if not current_user.brand_id and not current_user.can_view_all_brands:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    brand = current_user.brand if current_user.brand_id else None

    # Get today's attendance count
    today_count = 0
    if brand:
        today_count = MemberAttendance.get_today_count(brand.id)

    return render_template('attendance/index.html',
                          brand=brand,
                          today_count=today_count)


@attendance_bp.route('/check-in', methods=['POST'])
@login_required
def check_in():
    """Process check-in"""
    member_id = request.form.get('member_id', type=int)

    if not member_id:
        flash('يرجى اختيار العضو', 'danger')
        return redirect(url_for('attendance.index'))

    member = Member.query.get_or_404(member_id)

    if not current_user.can_access_brand(member.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('attendance.index'))

    # Validate attendance
    can_check_in, message = member.can_check_in()

    if not can_check_in:
        # Record with warning
        attendance = MemberAttendance(
            member_id=member.id,
            subscription_id=member.active_subscription.id if member.active_subscription else None,
            brand_id=member.brand_id,
            check_in=datetime.now(),
            source='manual',
            has_warning=True,
            warning_message=message
        )
        db.session.add(attendance)
        db.session.commit()

        flash(f'تحذير: {message}', 'warning')
        return redirect(url_for('attendance.index'))

    # Record attendance
    attendance = MemberAttendance(
        member_id=member.id,
        subscription_id=member.active_subscription.id,
        brand_id=member.brand_id,
        check_in=datetime.now(),
        source='manual'
    )
    db.session.add(attendance)
    db.session.commit()

    flash(f'تم تسجيل حضور {member.name}', 'success')
    return redirect(url_for('attendance.index'))


@attendance_bp.route('/members')
@login_required
def members_list():
    """Member attendance log"""
    page, per_page = pagination_args(request)
    date_filter = request.args.get('date', date.today().isoformat())

    # Parse date
    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
    except:
        filter_date = date.today()

    # Base query
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = MemberAttendance.query.filter_by(brand_id=brand_id)
        else:
            query = MemberAttendance.query
    else:
        query = MemberAttendance.query.filter_by(brand_id=current_user.brand_id)

    # Date filter
    query = query.filter(db.func.date(MemberAttendance.check_in) == filter_date)

    # Pagination
    attendance = query.order_by(MemberAttendance.check_in.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('attendance/history.html',
                          attendance=attendance,
                          brands=brands,
                          date_filter=date_filter)


@attendance_bp.route('/employees')
@login_required
def employees_list():
    """Employee attendance log"""
    if not current_user.can_manage_finance and not current_user.is_owner:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    page, per_page = pagination_args(request)
    date_filter = request.args.get('date', date.today().isoformat())

    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
    except:
        filter_date = date.today()

    # Base query
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = EmployeeAttendance.query.filter_by(brand_id=brand_id)
        else:
            query = EmployeeAttendance.query
    else:
        query = EmployeeAttendance.query.filter_by(brand_id=current_user.brand_id)

    # Date filter
    query = query.filter(EmployeeAttendance.date == filter_date)

    # Pagination
    attendance = query.order_by(EmployeeAttendance.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('attendance/employees.html',
                          attendance=attendance,
                          brands=brands,
                          date_filter=date_filter)


@attendance_bp.route('/api/search')
@login_required
def search_member():
    """Search member for check-in (AJAX)"""
    q = request.args.get('q', '')

    if len(q) < 2:
        return jsonify({'results': []})

    brand_id = current_user.brand_id

    members = Member.query.filter(
        Member.brand_id == brand_id,
        Member.is_active == True,
        db.or_(
            Member.name.ilike(f'%{q}%'),
            Member.phone.ilike(f'%{q}%'),
            Member.fingerprint_id == q if q.isdigit() else False
        )
    ).limit(10).all()

    results = []
    for m in members:
        can_check_in, message = m.can_check_in()
        results.append({
            'id': m.id,
            'name': m.name,
            'phone': m.phone,
            'status': m.subscription_status,
            'status_class': m.subscription_status_class,
            'can_check_in': can_check_in,
            'message': message,
            'days_remaining': m.days_remaining
        })

    return jsonify({'results': results})
