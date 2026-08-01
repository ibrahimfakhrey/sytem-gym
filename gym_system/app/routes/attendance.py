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
    q = (request.args.get('q', '') or '').strip()

    # GYM-42 — return results immediately from the first character so the
    # receptionist sees matches as they type. Also search by fingerprint_id
    # when the input is purely numeric.
    if len(q) < 1:
        return jsonify({'results': []})

    clauses = [Member.name.ilike(f'%{q}%'), Member.phone.ilike(f'%{q}%')]
    if q.isdigit():
        clauses.append(Member.fingerprint_id == int(q))

    # GYM-49 — KSA-phone normalization. The user types `05397745070`, but
    # the phone might be stored as `+966539...`, `9665...`, `00966539...`,
    # or any variant. Strip everything down to the tail (everything after
    # `00966` / `966` / leading `0`) and match `%tail%` so all forms hit.
    digits = ''.join(ch for ch in q if ch.isdigit())
    if digits:
        tail = digits
        if tail.startswith('00966'): tail = tail[5:]
        elif tail.startswith('966'): tail = tail[3:]
        if tail.startswith('0'):     tail = tail.lstrip('0')
        if tail and tail != q:
            clauses.append(Member.phone.ilike(f'%{tail}%'))

    # GYM-49 — drop the is_active==True filter so deactivated members ALSO
    # surface in the dropdown. can_check_in() returns a message that's
    # already rendered in the UI ("blocked"/"no subscription"), so the
    # receptionist sees why the row can't be used.
    query = Member.query.filter(db.or_(*clauses))

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


# ─── GYM-59 — unified fingerprint attendance log ─────────────────────────

@attendance_bp.route('/fingerprint')
@login_required
def fingerprint_log():
    """Consolidated view of every fingerprint-sourced attendance row —
    members + employees in one screen with filters, per-entity detail,
    and xlsx export at /attendance/fingerprint/export.xlsx."""
    from datetime import timedelta
    from app.models.user import User

    if not (current_user.is_owner or current_user.is_brand_manager
            or (current_user.role and current_user.role.name_en == 'branch_manager')):
        flash('صفحة سجل البصمة مقتصرة على المدير.', 'danger')
        return redirect(url_for('dashboard.index'))

    page, per_page = pagination_args(request)
    q_name = (request.args.get('q') or '').strip()
    kind = (request.args.get('kind') or '').strip()  # 'member' | 'employee' | ''
    date_from_str = (request.args.get('date_from') or '').strip()
    date_to_str = (request.args.get('date_to') or '').strip()
    branch_id = request.args.get('branch_id', type=int)

    today = date.today()
    try:
        d_from = date.fromisoformat(date_from_str) if date_from_str else today - timedelta(days=30)
        d_to = date.fromisoformat(date_to_str) if date_to_str else today
    except ValueError:
        d_from, d_to = today - timedelta(days=30), today

    # Members side
    mq = MemberAttendance.query.join(Member).filter(
        MemberAttendance.source == 'fingerprint',
        db.func.date(MemberAttendance.check_in) >= d_from,
        db.func.date(MemberAttendance.check_in) <= d_to,
    )
    # Employees side
    eq = EmployeeAttendance.query.join(User).filter(
        EmployeeAttendance.source == 'fingerprint',
        EmployeeAttendance.date >= d_from,
        EmployeeAttendance.date <= d_to,
    )

    if not current_user.is_owner and current_user.brand_id:
        mq = mq.filter(MemberAttendance.brand_id == current_user.brand_id)
        eq = eq.filter(EmployeeAttendance.brand_id == current_user.brand_id)
    if branch_id:
        mq = mq.filter(MemberAttendance.branch_id == branch_id)
        eq = eq.filter(EmployeeAttendance.branch_id == branch_id)
    if q_name:
        mq = mq.filter(Member.name.ilike(f'%{q_name}%'))
        eq = eq.filter(User.name.ilike(f'%{q_name}%'))

    rows = []
    if kind != 'employee':
        for att in mq.order_by(MemberAttendance.check_in.desc()).all():
            rows.append({
                'when': att.check_in,
                'kind': 'member',
                'kind_ar': 'عضو',
                'name': att.member.name if att.member else '—',
                'entity_id': att.member_id,
                'date': att.check_in.date() if att.check_in else None,
                'check_in': att.check_in,
                'check_out': None,
                'branch': att.brand.name if getattr(att, 'brand', None) else '',
                'status_ar': 'حضور',
            })
    if kind != 'member':
        for att in eq.order_by(EmployeeAttendance.date.desc(),
                               EmployeeAttendance.check_in.desc()).all():
            rows.append({
                'when': datetime.combine(att.date, att.check_in) if att.check_in else datetime.combine(att.date, datetime.min.time()),
                'kind': 'employee',
                'kind_ar': 'موظف',
                'name': att.employee.name if att.employee else '—',
                'entity_id': att.user_id,
                'date': att.date,
                'check_in': att.check_in,
                'check_out': att.check_out,
                'branch': att.brand.name if getattr(att, 'brand', None) else '',
                'status_ar': att.status_text,
            })

    rows.sort(key=lambda r: r['when'] or datetime.min, reverse=True)

    # Latest 10 for the auto-refresh strip
    latest = rows[:10]

    # Simple in-memory pagination
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]
    total_pages = max(1, (len(rows) + per_page - 1) // per_page)

    return render_template('attendance/fingerprint_log.html',
        rows=page_rows, latest=latest, total=len(rows),
        page=page, per_page=per_page, total_pages=total_pages,
        q_name=q_name, kind=kind,
        d_from=d_from, d_to=d_to,
        branch_id=branch_id,
    )


@attendance_bp.route('/fingerprint/api/latest')
@login_required
def fingerprint_latest():
    """JSON feed for the auto-refresh strip on /attendance/fingerprint."""
    from datetime import timedelta
    from app.models.user import User
    if not (current_user.is_owner or current_user.is_brand_manager):
        return jsonify({'items': []})
    since = datetime.utcnow() - timedelta(days=2)
    items = []
    mq = MemberAttendance.query.join(Member).filter(
        MemberAttendance.source == 'fingerprint',
        MemberAttendance.check_in >= since,
    )
    if not current_user.is_owner and current_user.brand_id:
        mq = mq.filter(MemberAttendance.brand_id == current_user.brand_id)
    for att in mq.order_by(MemberAttendance.check_in.desc()).limit(20).all():
        items.append({
            'when': att.check_in.isoformat() if att.check_in else None,
            'kind': 'عضو',
            'name': att.member.name if att.member else '—',
        })
    return jsonify({'items': items[:20]})


@attendance_bp.route('/fingerprint/export.xlsx')
@login_required
def fingerprint_export():
    """xlsx export of whatever the current filters return on
    /attendance/fingerprint."""
    from app.routes.finance import _xlsx_response
    from app.utils.helpers import local_dt
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))
    # Simplest — reuse the main handler and pull rows.
    from datetime import timedelta
    from app.models.user import User
    date_from_str = request.args.get('date_from') or ''
    date_to_str = request.args.get('date_to') or ''
    q_name = (request.args.get('q') or '').strip()
    kind = request.args.get('kind') or ''
    today = date.today()
    try:
        d_from = date.fromisoformat(date_from_str) if date_from_str else today - timedelta(days=30)
        d_to = date.fromisoformat(date_to_str) if date_to_str else today
    except ValueError:
        d_from, d_to = today - timedelta(days=30), today
    rows = []
    if kind != 'employee':
        mq = MemberAttendance.query.join(Member).filter(
            MemberAttendance.source == 'fingerprint',
            db.func.date(MemberAttendance.check_in) >= d_from,
            db.func.date(MemberAttendance.check_in) <= d_to,
        )
        if not current_user.is_owner and current_user.brand_id:
            mq = mq.filter(MemberAttendance.brand_id == current_user.brand_id)
        if q_name:
            mq = mq.filter(Member.name.ilike(f'%{q_name}%'))
        for att in mq.order_by(MemberAttendance.check_in.desc()).all():
            rows.append(['عضو',
                         att.member.name if att.member else '',
                         local_dt(att.check_in),
                         '', ''])
    if kind != 'member':
        eq = EmployeeAttendance.query.join(User).filter(
            EmployeeAttendance.source == 'fingerprint',
            EmployeeAttendance.date >= d_from,
            EmployeeAttendance.date <= d_to,
        )
        if not current_user.is_owner and current_user.brand_id:
            eq = eq.filter(EmployeeAttendance.brand_id == current_user.brand_id)
        if q_name:
            eq = eq.filter(User.name.ilike(f'%{q_name}%'))
        for att in eq.order_by(EmployeeAttendance.date.desc()).all():
            rows.append(['موظف',
                         att.employee.name if att.employee else '',
                         att.date.isoformat(),
                         att.check_in.strftime('%H:%M') if att.check_in else '',
                         att.check_out.strftime('%H:%M') if att.check_out else ''])
    return _xlsx_response(
        f'fingerprint-log-{d_from.isoformat()}-to-{d_to.isoformat()}',
        ['النوع', 'الاسم', 'التاريخ / الوقت', 'حضور', 'انصراف'],
        rows,
    )
