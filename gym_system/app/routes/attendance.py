from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import date, datetime

from app import db, csrf
from app.models.company import Brand
from app.models.member import Member
from app.models.attendance import MemberAttendance, EmployeeAttendance
from app.utils.helpers import pagination_args, apply_branch_filter, check_entity_access

attendance_bp = Blueprint('attendance', __name__)


@attendance_bp.route('/')
@login_required
def index():
    """Attendance check-in page"""
    if not current_user.can_manage_attendance:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    brand = current_user.brand if current_user.brand_id else None

    # Get today's attendance
    today = date.today()
    today_query = apply_branch_filter(MemberAttendance.query, MemberAttendance)
    today_attendance = today_query.filter(
        db.func.date(MemberAttendance.check_in) == today
    ).order_by(MemberAttendance.check_in.desc()).all()

    return render_template('attendance/index.html',
                          brand=brand,
                          today_attendance=today_attendance)


@attendance_bp.route('/check-in', methods=['POST'])
@login_required
@csrf.exempt
def check_in():
    """Process check-in"""
    # Handle JSON request
    if request.is_json:
        data = request.get_json()
        member_id = data.get('member_id')
    else:
        member_id = request.form.get('member_id', type=int)

    if not member_id:
        if request.is_json:
            return jsonify({'success': False, 'message': 'يرجى اختيار العضو'})
        flash('يرجى اختيار العضو', 'danger')
        return redirect(url_for('attendance.index'))

    member = Member.query.get_or_404(member_id)

    if not current_user.can_access_brand(member.brand_id):
        if request.is_json:
            return jsonify({'success': False, 'message': 'ليس لديك صلاحية'})
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('attendance.index'))

    # Validate attendance
    can_check_in, message = member.can_check_in()

    if not can_check_in:
        # BLOCK attendance - do NOT record!
        if request.is_json:
            return jsonify({'success': False, 'message': message, 'blocked': True})
        flash(f'❌ غير مسموح بالدخول: {message}', 'danger')
        return redirect(url_for('attendance.index'))

    # Record attendance
    attendance = MemberAttendance(
        member_id=member.id,
        subscription_id=member.active_subscription.id,
        brand_id=member.brand_id,
        branch_id=member.branch_id or current_user.branch_id,  # Set branch
        check_in=datetime.now(),
        source='manual'
    )
    db.session.add(attendance)
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'member_name': member.name})
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

    # Base query — honor GYM-12 owner branch picker
    from app.utils.helpers import resolve_owner_branch_filter
    query = apply_branch_filter(MemberAttendance.query, MemberAttendance,
                                branch_filter_id=resolve_owner_branch_filter())

    # Date filter
    query = query.filter(db.func.date(MemberAttendance.check_in) == filter_date)

    # Pagination
    attendances = query.order_by(MemberAttendance.check_in.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Stats for the filtered date (template expects stats.total/fingerprint/manual)
    stats_query = apply_branch_filter(MemberAttendance.query, MemberAttendance) \
        .filter(db.func.date(MemberAttendance.check_in) == filter_date)
    total = stats_query.count()
    fingerprint = stats_query.filter(MemberAttendance.source == 'fingerprint').count()
    manual = total - fingerprint
    stats = {'total': total, 'fingerprint': fingerprint, 'manual': manual}

    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('attendance/history.html',
                          attendances=attendances,
                          stats=stats,
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
    query = apply_branch_filter(EmployeeAttendance.query, EmployeeAttendance)

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
@csrf.exempt
def search_member():
    """Search member for check-in (AJAX)"""
    q = request.args.get('q', '')

    if len(q) < 2:
        return jsonify({'results': []})

    # Build base query - search by name or phone
    query = Member.query.filter(
        Member.is_active == True,
        db.or_(
            Member.name.ilike(f'%{q}%'),
            Member.phone.ilike(f'%{q}%')
        )
    )

    # Filter by brand if user is not owner
    if not current_user.can_view_all_brands:
        query = query.filter(Member.brand_id == current_user.brand_id)

    members = query.limit(10).all()

    results = []
    for m in members:
        can_check_in, message = m.can_check_in()
        results.append({
            'id': m.id,
            'name': m.name,
            'phone': m.phone,
            'status': m.subscription_status,
            'status_text': m.subscription_status,
            'status_class': m.subscription_status_class,
            'can_check_in': can_check_in,
            'message': message,
            'days_remaining': m.days_remaining
        })

    return jsonify({'results': results})
