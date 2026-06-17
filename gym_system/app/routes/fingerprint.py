"""
Fingerprint / Bridge API — single-brand + single-branch desktop client.

No authentication. Every endpoint takes `brand_id` + `branch_id`.

Contract for the desktop developer:

  Desktop → Web (events):
    POST /fp/scan              one scan, returns the live verdict
    POST /fp/heartbeat         bridge is alive
    POST /fp/sync              batched scans (catch-up after offline)
    POST /fp/full-sync         first-launch bulk import

  Web → Desktop (polled):
    GET  /fp/access-list       per-member end_date + reason

  Web UI helpers (called from the control panel JS):
    GET  /fp/status            bridge online/offline + last sync info
    GET  /fp/scans/recent      live feed of who clocked in/out
    POST /fp/members/<id>/block
    POST /fp/members/<id>/unblock

  HTML pages:
    GET  /fp/control/<brand_id>
    GET  /fp/control/<brand_id>/<branch_id>
"""

from datetime import datetime, date, time, timedelta
from flask import Blueprint, request, jsonify, render_template, abort
from flask_login import login_required, current_user
from sqlalchemy import func

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from app import db, csrf
from app.models.company import Brand, Branch
from app.models.member import Member
from app.models.user import User
from app.models.subscription import Subscription
from app.models.classes import GymClass, ClassBooking
from app.models.attendance import MemberAttendance, EmployeeAttendance
from app.models.employee import EmployeeShift, EmployeeSettings, EmployeeLateRule, EmployeeDeduction
from app.models.fingerprint import BridgeStatus, BridgeSettings, FingerprintSyncLog, FingerprintAccessLog

fingerprint_bp = Blueprint('fingerprint', __name__, url_prefix='/fp')

KSA_TZ = ZoneInfo("Asia/Riyadh")
PAST_DATE = date(2020, 1, 1)
FAR_FUTURE_DATE = date(2099, 12, 31)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def ksa_now():
    return datetime.now(KSA_TZ)


def ksa_today():
    return ksa_now().date()


def _utc_to_ksa_iso(dt):
    """Convert a naive UTC datetime (DB column default) to a KSA-timezone ISO string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KSA_TZ).isoformat()


def parse_iso_dt(s):
    if not s:
        return None
    try:
        s = s.replace('Z', '').split('+')[0]
        return datetime.fromisoformat(s)
    except (ValueError, TypeError, AttributeError):
        return None


def parse_iso_date(s):
    if not s:
        return None
    try:
        date_part = s.split('T')[0].split(' ')[0]
        return datetime.strptime(date_part, '%Y-%m-%d').date()
    except (ValueError, TypeError, AttributeError):
        return None


def safe_int(v, default=None):
    try:
        if v in (None, ''):
            return default
        return int(v)
    except (ValueError, TypeError):
        return default


def _resolve_branch(brand_id, branch_id):
    """
    Validate (brand_id, branch_id) against the branches table.

    Both fields are required and the pair must correspond to a real
    branch row — that's the only check. No single-tenant lock; callers
    can target any brand they have data for.
    """
    if brand_id is None or branch_id is None:
        return None
    return Branch.query.filter_by(id=branch_id, brand_id=brand_id).first()


def _emp_id_for(member):
    """Same key the desktop uses to identify a person in backup.mdb."""
    return member.member_import_id or str(member.fingerprint_id).zfill(8)


def _is_web_session():
    """True if the request is from a logged-in browser session (vs anonymous API call)."""
    try:
        from flask_login import current_user as _u
        return bool(_u and _u.is_authenticated)
    except Exception:
        return False


def _log_fp_access(member, branch, action, source='api', notes=None):
    """
    Append one FingerprintAccessLog row. Picks up the logged-in user if
    there is one (web/form sources); falls back to an anonymous record
    otherwise (api/desktop sources).
    """
    actor_id = None
    actor_name = None
    try:
        from flask_login import current_user as _u
        if _u and _u.is_authenticated:
            actor_id = _u.id
            actor_name = _u.name
    except Exception:
        pass

    ip = None
    try:
        ip = request.remote_addr
    except Exception:
        pass

    log_row = FingerprintAccessLog(
        brand_id=branch.brand_id,
        branch_id=branch.id,
        member_id=member.id,
        member_name=member.name,
        fingerprint_id=member.fingerprint_id,
        member_import_id=member.member_import_id,
        action=action,
        source=source,
        actor_user_id=actor_id,
        actor_name=actor_name,
        ip_address=ip,
        notes=notes,
        created_at=datetime.utcnow(),
    )
    db.session.add(log_row)
    return log_row


# ─────────────────────────────────────────────────────────────────────────────
# 1. Heartbeat
# ─────────────────────────────────────────────────────────────────────────────

@fingerprint_bp.route('/heartbeat', methods=['POST'])
@csrf.exempt
def heartbeat():
    data = request.get_json(silent=True) or {}
    brand_id = safe_int(data.get('brand_id'))
    branch_id = safe_int(data.get('branch_id'))

    branch = _resolve_branch(brand_id, branch_id)
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400

    bs = BridgeStatus.query.filter_by(branch_id=branch.id).first()
    if not bs:
        bs = BridgeStatus(brand_id=brand_id, branch_id=branch_id)
        db.session.add(bs)

    bs.computer_name = data.get('computer_name') or bs.computer_name or 'Unknown'
    bs.ip_address = data.get('ip') or bs.ip_address or ''
    bs.os_info = data.get('os_info') or bs.os_info or ''
    bs.database_path = data.get('db_path') or bs.database_path or ''
    bs.database_found = bool(data.get('db_found', False))
    bs.last_heartbeat = datetime.utcnow()
    bs.is_online = True
    if data.get('error'):
        bs.last_error = data['error']

    db.session.commit()
    return jsonify({'success': True, 'server_time': ksa_now().isoformat()})


# ─────────────────────────────────────────────────────────────────────────────
# 2. Scan — single, real-time, returns the verdict for the desktop to display
# ─────────────────────────────────────────────────────────────────────────────

@fingerprint_bp.route('/scan', methods=['POST'])
@csrf.exempt
def scan():
    data = request.get_json(silent=True) or {}
    brand_id = safe_int(data.get('brand_id'))
    branch_id = safe_int(data.get('branch_id'))
    fingerprint_id = safe_int(data.get('fingerprint_id'))
    timestamp = parse_iso_dt(data.get('timestamp')) or datetime.utcnow()
    device_log_id = safe_int(data.get('device_log_id'))

    branch = _resolve_branch(brand_id, branch_id)
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400
    if fingerprint_id is None:
        return jsonify({'success': False, 'error': 'fingerprint_id required'}), 400

    result = _record_scan(branch, fingerprint_id, timestamp, device_log_id)
    db.session.commit()
    return jsonify({'success': True, **result})


def _record_scan(branch, fingerprint_id, timestamp, device_log_id):
    """
    Resolve fingerprint → employee / member / unknown.
    Writes attendance row(s) and returns a verdict dict for the device:
      { person_type, person_id, person_name, action, allowed, reason }
    """
    brand_id = branch.brand_id

    # 1. Employee match (User by fingerprint within branch, fall back to brand-level)
    user = User.query.filter_by(
        branch_id=branch.id, fingerprint_id=fingerprint_id, is_active=True
    ).first()
    if not user:
        user = User.query.filter_by(
            brand_id=brand_id, branch_id=None,
            fingerprint_id=fingerprint_id, is_active=True
        ).first()

    # 2. Member match within branch
    member = Member.query.filter_by(
        branch_id=branch.id, fingerprint_id=fingerprint_id
    ).first()
    if not member:
        member = Member.query.filter_by(
            brand_id=brand_id, branch_id=None, fingerprint_id=fingerprint_id
        ).first()

    # ── Path A: employee scan ──
    if user:
        action = _record_employee_scan(user, branch, timestamp, device_log_id)
        # If they're also a member (is_staff link), log MemberAttendance too
        if member:
            _record_member_scan_row(member, branch, timestamp, device_log_id, allowed=True, warning=None)
        return {
            'person_type': 'employee',
            'person_id': user.id,
            'person_name': user.name,
            'fingerprint_id': fingerprint_id,
            'action': action,
            'allowed': True,
            'reason': 'موظف',
        }

    # ── Path B: member scan ──
    if member:
        decision = _compute_access(member, ksa_now(), ksa_today(),
                                   _access_window(branch))
        warning = None if decision['allowed'] else decision['reason']
        _record_member_scan_row(member, branch, timestamp, device_log_id,
                                allowed=decision['allowed'], warning=warning)
        return {
            'person_type': 'member',
            'person_id': member.id,
            'person_name': member.name,
            'fingerprint_id': fingerprint_id,
            'action': 'check_in' if decision['allowed'] else 'denied',
            'allowed': decision['allowed'],
            'reason': decision['reason'],
        }

    # ── Path C: unknown ──
    return {
        'person_type': 'unknown',
        'person_id': None,
        'person_name': None,
        'fingerprint_id': fingerprint_id,
        'action': 'denied',
        'allowed': False,
        'reason': 'بصمة غير معروفة',
    }


def _record_member_scan_row(member, branch, timestamp, device_log_id, allowed, warning):
    if device_log_id:
        existing = MemberAttendance.query.filter_by(fingerprint_log_id=device_log_id).first()
        if existing:
            return existing
    sub = Subscription.query.filter(
        Subscription.member_id == member.id,
        Subscription.status == 'active',
        Subscription.end_date >= date.today(),
        Subscription.is_deleted == False,  # GYM-32
    ).first()
    att = MemberAttendance(
        member_id=member.id,
        subscription_id=sub.id if sub else None,
        brand_id=member.brand_id,
        branch_id=branch.id,
        check_in=timestamp,
        source='fingerprint',
        fingerprint_log_id=device_log_id,
        has_warning=not allowed or bool(warning),
        warning_message=warning,
    )
    db.session.add(att)
    return att


def _record_employee_scan(user, branch, timestamp, device_log_id):
    """First scan = check-in, second = check-out. Returns the action label."""
    attendance_date = timestamp.date()

    if device_log_id:
        dup = EmployeeAttendance.query.filter_by(
            user_id=user.id, fingerprint_log_id=device_log_id
        ).first()
        if dup:
            return 'duplicate'

    today_row = EmployeeAttendance.query.filter_by(
        user_id=user.id, date=attendance_date
    ).first()

    if today_row:
        today_row.check_out = timestamp.time()
        if device_log_id:
            today_row.fingerprint_log_id = device_log_id
        return 'check_out'

    shift = EmployeeShift.get_active_shift(user.id, (attendance_date.weekday() + 2) % 7)
    settings = EmployeeSettings.get_or_create(user.brand_id)
    expected_start = shift.work_start_time if shift else settings.work_start_time
    late_threshold = (shift.get_late_threshold(settings) if shift
                      else (settings.late_threshold_minutes or 15))
    status = 'present'
    late_minutes = 0
    if expected_start:
        ci_mins = timestamp.time().hour * 60 + timestamp.time().minute
        st_mins = expected_start.hour * 60 + expected_start.minute
        if ci_mins > st_mins + late_threshold:
            late_minutes = ci_mins - st_mins
            status = 'late'

    db.session.add(EmployeeAttendance(
        user_id=user.id, brand_id=user.brand_id, branch_id=branch.id,
        date=attendance_date, check_in=timestamp.time(),
        expected_check_in=expected_start, late_minutes=late_minutes,
        status=status, source='fingerprint', fingerprint_log_id=device_log_id,
    ))

    if status == 'late' and settings and settings.auto_deduction_enabled:
        tier = EmployeeLateRule.get_deduction_for(user.brand_id, late_minutes)
        amount = tier if tier is not None else (settings.auto_deduction_amount or 0)
        if amount and float(amount) > 0:
            db.session.add(EmployeeDeduction(
                user_id=user.id, brand_id=user.brand_id,
                title='خصم تأخير', amount=amount,
                reason=f'تأخير {late_minutes} دقيقة - بصمة',
                deduction_type='late', deduction_date=attendance_date,
            ))
    return 'check_in'


# ─────────────────────────────────────────────────────────────────────────────
# 3. Batched sync — incremental and first-launch
# ─────────────────────────────────────────────────────────────────────────────

@fingerprint_bp.route('/sync', methods=['POST'])
@csrf.exempt
def sync():
    """Incremental sync: new members + new attendance since last poll."""
    data = request.get_json(silent=True) or {}
    brand_id = safe_int(data.get('brand_id'))
    branch_id = safe_int(data.get('branch_id'))
    branch = _resolve_branch(brand_id, branch_id)
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400

    new_members = data.get('new_members', [])
    new_attendance = data.get('new_attendance', [])

    members_synced = 0
    for m in new_members:
        if _upsert_member_from_mdb(m, brand_id, branch.id, allow_create=True):
            members_synced += 1
    db.session.commit()

    attendance_synced = 0
    affected_users = set()
    for a in new_attendance:
        fingerprint_id = safe_int(a.get('userid') or a.get('fingerprint_id'))
        timestamp = parse_iso_dt(a.get('checktime') or a.get('timestamp'))
        device_log_id = safe_int(a.get('device_log_id'))
        if fingerprint_id is None or timestamp is None:
            continue
        result = _record_scan(branch, fingerprint_id, timestamp, device_log_id)
        attendance_synced += 1
        if result['person_type'] == 'employee':
            affected_users.add((result['person_id'], timestamp.date()))
    db.session.commit()

    # Recompute employee attendance for each (user, date) pair touched
    for user_id, scan_date in affected_users:
        u = User.query.get(user_id)
        if u:
            _recompute_employee_attendance(u, scan_date, branch.id)
    db.session.commit()

    db.session.add(FingerprintSyncLog(
        brand_id=brand_id, branch_id=branch.id, sync_type='attendance',
        records_synced=attendance_synced, status='success',
    ))
    db.session.commit()

    return jsonify({
        'success': True,
        'server_time': ksa_now().isoformat(),
        'members_synced': members_synced,
        'attendance_synced': attendance_synced,
        'next_sync_in_seconds': 60,
    })


@fingerprint_bp.route('/full-sync', methods=['POST'])
@csrf.exempt
def full_sync():
    """First-launch bulk import of backup.mdb employees + last 30d of att2000.mdb."""
    data = request.get_json(silent=True) or {}
    brand_id = safe_int(data.get('brand_id'))
    branch_id = safe_int(data.get('branch_id'))
    branch = _resolve_branch(brand_id, branch_id)
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400

    members_data = data.get('members', [])
    attendance_data = data.get('attendance', [])

    created = 0
    updated = 0
    id_mapping = {}
    for m in members_data:
        outcome, member = _upsert_member_from_mdb(m, brand_id, branch.id, allow_create=True,
                                                   return_status=True)
        if outcome == 'created':
            created += 1
        elif outcome == 'updated':
            updated += 1
        emp_id = (m.get('emp_id') or '').strip()
        if member and emp_id:
            id_mapping[emp_id] = member.id
    db.session.commit()

    attendance_imported = 0
    skipped_unknown = 0
    duplicates = 0
    for a in attendance_data:
        fingerprint_id = safe_int(a.get('userid') or a.get('fingerprint_id'))
        timestamp = parse_iso_dt(a.get('checktime') or a.get('timestamp'))
        device_log_id = safe_int(a.get('device_log_id'))
        if fingerprint_id is None or timestamp is None:
            continue
        member = Member.query.filter_by(brand_id=brand_id, fingerprint_id=fingerprint_id).first()
        if not member:
            skipped_unknown += 1
            continue
        existing = MemberAttendance.query.filter_by(
            member_id=member.id, check_in=timestamp
        ).first()
        if existing:
            duplicates += 1
            continue
        db.session.add(MemberAttendance(
            member_id=member.id, brand_id=brand_id, branch_id=branch.id,
            check_in=timestamp, source='fingerprint', fingerprint_log_id=device_log_id,
        ))
        attendance_imported += 1
    db.session.commit()

    return jsonify({
        'success': True,
        'branch': {'id': branch.id, 'name': branch.name,
                   'brand_id': brand_id,
                   'brand_name': branch.brand.name if branch.brand else ''},
        'import_summary': {
            'members_created': created,
            'members_updated': updated,
            'attendance_imported': attendance_imported,
            'duplicates_skipped': duplicates,
            'skipped_unknown_fingerprints': skipped_unknown,
        },
        'id_mapping': id_mapping,
        'server_time': ksa_now().isoformat(),
    })


def _upsert_member_from_mdb(m, brand_id, branch_id, allow_create=True, return_status=False):
    """Upsert a Member row from a backup.mdb Employee dict. Returns Member or (status, Member)."""
    emp_id = (m.get('emp_id') or '').strip()
    if not emp_id:
        return ('skipped', None) if return_status else None

    existing = Member.query.filter_by(brand_id=brand_id, member_import_id=emp_id).first()
    card_id = m.get('card_id')
    fingerprint_id = safe_int(card_id) if card_id else None

    if existing:
        existing.name = (m.get('emp_name') or existing.name).strip() or existing.name
        existing.phone = (m.get('phone') or existing.phone or '').strip()
        if m.get('email'):
            existing.email = m['email']
        if m.get('address'):
            existing.address = m['address']
        if fingerprint_id and not existing.fingerprint_id:
            existing.fingerprint_id = fingerprint_id
            existing.fingerprint_enrolled = True
        return ('updated', existing) if return_status else existing

    if not allow_create:
        return ('skipped', None) if return_status else None

    sex_raw = (m.get('sex') or '').strip()
    gender = 'male' if sex_raw in ('0', 'M', 'm') else 'female' if sex_raw in ('1', 'F', 'f') else None
    new_member = Member(
        brand_id=brand_id, branch_id=branch_id,
        name=(m.get('emp_name') or 'Unknown').strip()[:100] or 'Unknown',
        phone=(m.get('phone') or '').strip()[:20] or '0',
        email=(m.get('email') or None),
        address=(m.get('address') or None),
        gender=gender,
        birth_date=parse_iso_date(m.get('birth_date')),
        member_import_id=emp_id,
        fingerprint_id=fingerprint_id,
        fingerprint_enrolled=bool(fingerprint_id),
        is_active=True,
    )
    db.session.add(new_member)
    db.session.flush()
    return ('created', new_member) if return_status else new_member


# ─────────────────────────────────────────────────────────────────────────────
# 4. Access list — what the desktop polls every ~60 seconds
# ─────────────────────────────────────────────────────────────────────────────

def _build_access_list(branch):
    """
    Compute the per-member access decision for every enrolled member in
    this branch. Returns (rows, now, window_minutes).

    Each row: { emp_id, fingerprint_id, name, allowed, end_date, reason }.
    """
    brand_id = branch.brand_id
    now = ksa_now()
    today = now.date()
    window_minutes = _access_window(branch)

    members = Member.query.filter(
        Member.brand_id == brand_id,
        Member.fingerprint_id.isnot(None),
        Member.member_import_id.isnot(None),
    ).all()

    # Latest stop/allow timestamp per member, looked up in one query.
    last_change_by_member = {}
    if members:
        member_ids = [m.id for m in members]
        latest = (
            db.session.query(
                FingerprintAccessLog.member_id,
                FingerprintAccessLog.action,
                db.func.max(FingerprintAccessLog.created_at).label('ts'),
            )
            .filter(FingerprintAccessLog.member_id.in_(member_ids))
            .group_by(FingerprintAccessLog.member_id, FingerprintAccessLog.action)
            .all()
        )
        # Keep only the most recent action per member.
        for mid, action, ts in latest:
            prev = last_change_by_member.get(mid)
            if not prev or (ts and ts > prev[1]):
                last_change_by_member[mid] = (action, ts)

    rows = []
    for m in members:
        if not m.is_active:
            decision = {'allowed': False, 'end_date': PAST_DATE, 'reason': 'محظور من قبل الإدارة'}
        elif m.is_staff:
            decision = {'allowed': True, 'end_date': FAR_FUTURE_DATE, 'reason': 'موظف'}
        else:
            decision = _compute_access(m, now, today, window_minutes)

        last = last_change_by_member.get(m.id)
        rows.append({
            'emp_id': m.member_import_id,
            'fingerprint_id': m.fingerprint_id,
            'name': m.name,
            'allowed': decision['allowed'],
            'end_date': decision['end_date'].isoformat() if decision['end_date'] else None,
            'reason': decision['reason'],
            'last_action': last[0] if last else None,
            'last_changed_at': _utc_to_ksa_iso(last[1]) if last else None,
        })

    return rows, now, window_minutes


@fingerprint_bp.route('/access-list', methods=['GET'])
@csrf.exempt
def access_list():
    branch = _resolve_branch(safe_int(request.args.get('brand_id')),
                             safe_int(request.args.get('branch_id')))
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400
    rows, now, window_minutes = _build_access_list(branch)
    return jsonify({
        'success': True,
        'computed_at': now.isoformat(),
        'access_window_minutes': window_minutes,
        'count': len(rows),
        'members': rows,
    })


@fingerprint_bp.route('/to-stop', methods=['GET'])
@csrf.exempt
def to_stop():
    """
    Members the desktop should currently DENY at the gate.

    Identical decision logic to /fp/access-list, just pre-filtered to
    rows where allowed=false. For each row, write end_date=2020-01-01
    to that emp_id in backup.mdb.
    """
    branch = _resolve_branch(safe_int(request.args.get('brand_id')),
                             safe_int(request.args.get('branch_id')))
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400
    rows, now, _ = _build_access_list(branch)
    stop = [r for r in rows if not r['allowed']]
    return jsonify({
        'success': True,
        'computed_at': now.isoformat(),
        'count': len(stop),
        'members': stop,
    })


@fingerprint_bp.route('/to-allow', methods=['GET'])
@csrf.exempt
def to_allow():
    """
    Members the desktop should currently ALLOW at the gate.

    Identical decision logic to /fp/access-list, just pre-filtered to
    rows where allowed=true. For each row, write its end_date value
    to that emp_id in backup.mdb.
    """
    branch = _resolve_branch(safe_int(request.args.get('brand_id')),
                             safe_int(request.args.get('branch_id')))
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400
    rows, now, _ = _build_access_list(branch)
    allow = [r for r in rows if r['allowed']]
    return jsonify({
        'success': True,
        'computed_at': now.isoformat(),
        'count': len(allow),
        'members': allow,
    })


def _access_window(branch):
    settings = (BridgeSettings.query.filter_by(branch_id=branch.id).first()
                or BridgeSettings.query.filter_by(brand_id=branch.brand_id, branch_id=None).first())
    return settings.class_access_window_minutes if settings else 15


def _compute_access(member, now, today, window_minutes):
    sub = Subscription.query.filter(
        Subscription.member_id == member.id,
        Subscription.status == 'active',
        Subscription.is_deleted == False,  # GYM-32 — soft-deleted subs must NOT unlock the door
    ).order_by(Subscription.end_date.desc()).first()

    if not sub:
        return {'allowed': False, 'end_date': PAST_DATE, 'reason': 'لا يوجد اشتراك نشط'}
    if sub.end_date < today:
        return {'allowed': False, 'end_date': PAST_DATE, 'reason': 'اشتراك منتهي'}

    requires_class = False
    if sub.plan and getattr(sub.plan, 'service_type', None):
        requires_class = bool(getattr(sub.plan.service_type, 'requires_class_booking', False))

    if not requires_class:
        return {'allowed': True, 'end_date': sub.end_date, 'reason': 'اشتراك نشط'}

    booking = ClassBooking.query.filter(
        ClassBooking.member_id == member.id,
        ClassBooking.booking_date == today,
        ClassBooking.status.in_(['booked', 'attended']),
    ).first()
    if not booking:
        return {'allowed': False, 'end_date': PAST_DATE, 'reason': 'لم يحجز كلاس اليوم'}

    cls = booking.gym_class
    if not cls:
        return {'allowed': False, 'end_date': PAST_DATE, 'reason': 'كلاس غير موجود'}

    start_dt = datetime.combine(today, cls.start_time, tzinfo=KSA_TZ)
    end_dt = datetime.combine(today, cls.end_time, tzinfo=KSA_TZ)
    window_start = start_dt - timedelta(minutes=window_minutes)

    if window_start <= now <= end_dt:
        return {'allowed': True, 'end_date': today,
                'reason': f'كلاس {cls.name} - {cls.start_time.strftime("%H:%M")}'}
    return {'allowed': False, 'end_date': PAST_DATE, 'reason': 'خارج وقت الكلاس'}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Employee attendance recompute (used by sync + member→employee conversion)
# ─────────────────────────────────────────────────────────────────────────────

def _recompute_employee_attendance(user, target_date, branch_id):
    """Idempotent upsert of EmployeeAttendance from MemberAttendance scans."""
    if not user.fingerprint_id:
        return

    start_dt = datetime.combine(target_date, time.min)
    end_dt = datetime.combine(target_date, time.max)
    scans = db.session.query(MemberAttendance).join(
        Member, Member.id == MemberAttendance.member_id
    ).filter(
        Member.fingerprint_id == user.fingerprint_id,
        Member.brand_id == user.brand_id,
        MemberAttendance.check_in >= start_dt,
        MemberAttendance.check_in <= end_dt,
    ).order_by(MemberAttendance.check_in.asc()).all()

    if not scans:
        return

    first_scan = scans[0].check_in.time()
    last_scan = scans[-1].check_in.time() if len(scans) > 1 else None

    shift = EmployeeShift.query.filter_by(user_id=user.id, is_active=True).first()
    settings = EmployeeSettings.query.filter_by(brand_id=user.brand_id).first()

    expected_check_in = None
    late_threshold = 15
    if shift:
        expected_check_in = shift.work_start_time
        if shift.late_threshold_minutes is not None:
            late_threshold = shift.late_threshold_minutes
    elif settings:
        expected_check_in = settings.work_start_time
        late_threshold = settings.late_threshold_minutes or 15

    late_minutes = 0
    if expected_check_in:
        first_dt = datetime.combine(target_date, first_scan)
        expected_dt = datetime.combine(target_date, expected_check_in)
        if first_dt > expected_dt:
            late_minutes = int((first_dt - expected_dt).total_seconds() / 60)

    status = 'late' if late_minutes > late_threshold else 'present'

    att = EmployeeAttendance.query.filter_by(user_id=user.id, date=target_date).first()
    if not att:
        att = EmployeeAttendance(
            user_id=user.id, brand_id=user.brand_id,
            branch_id=branch_id, date=target_date,
        )
        db.session.add(att)

    att.check_in = first_scan
    att.check_out = last_scan
    att.expected_check_in = expected_check_in
    att.late_minutes = late_minutes
    att.status = status
    att.source = 'fingerprint'

    if status == 'late' and settings and settings.auto_deduction_enabled:
        rule = EmployeeLateRule.query.filter(
            EmployeeLateRule.brand_id == user.brand_id,
            EmployeeLateRule.min_late_minutes <= late_minutes,
        ).order_by(EmployeeLateRule.min_late_minutes.desc()).first()
        if rule:
            existing_ded = EmployeeDeduction.query.filter_by(
                user_id=user.id, deduction_date=target_date, deduction_type='late',
            ).first()
            if not existing_ded:
                db.session.add(EmployeeDeduction(
                    user_id=user.id, brand_id=user.brand_id,
                    title=f'تأخير {late_minutes} دقيقة',
                    amount=rule.deduction_amount,
                    reason=f'تأخير عن موعد العمل بمقدار {late_minutes} دقيقة',
                    deduction_type='late', deduction_date=target_date,
                ))


def backfill_employee_attendance_from_member_scans(user, branch_id, days=60):
    """Replay MemberAttendance history for a freshly-converted employee."""
    if not user.fingerprint_id:
        return 0
    start_dt = datetime.combine(date.today() - timedelta(days=days), time.min)
    rows = db.session.query(
        func.date(MemberAttendance.check_in).label('d')
    ).join(Member, Member.id == MemberAttendance.member_id).filter(
        Member.fingerprint_id == user.fingerprint_id,
        Member.brand_id == user.brand_id,
        MemberAttendance.check_in >= start_dt,
    ).distinct().all()

    processed = 0
    for r in rows:
        d = r.d
        if isinstance(d, str):
            try:
                d = datetime.strptime(d, '%Y-%m-%d').date()
            except ValueError:
                continue
        _recompute_employee_attendance(user, d, branch_id)
        processed += 1
    return processed


# ─────────────────────────────────────────────────────────────────────────────
# 6. UI helpers — called by the control panel JS (open, no auth needed by spec
#    but logged-in user must be able to view their brand)
# ─────────────────────────────────────────────────────────────────────────────

@fingerprint_bp.route('/status', methods=['GET'])
@csrf.exempt
def status():
    brand_id = safe_int(request.args.get('brand_id'))
    branch_id = safe_int(request.args.get('branch_id'))
    branch = _resolve_branch(brand_id, branch_id)
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400

    bs = BridgeStatus.query.filter_by(branch_id=branch.id).first()
    last_sync = FingerprintSyncLog.query.filter_by(
        brand_id=brand_id, branch_id=branch.id
    ).order_by(FingerprintSyncLog.synced_at.desc()).first()

    today = date.today()
    members_today = MemberAttendance.query.filter(
        MemberAttendance.branch_id == branch.id,
        func.date(MemberAttendance.check_in) == today,
    ).count()
    employees_today = EmployeeAttendance.query.filter_by(
        branch_id=branch.id, date=today
    ).count()

    return jsonify({
        'success': True,
        'bridge': None if not bs else {
            'computer_name': bs.computer_name,
            'ip_address': bs.ip_address,
            'database_found': bs.database_found,
            'database_path': bs.database_path,
            'last_heartbeat': bs.last_heartbeat.isoformat() if bs.last_heartbeat else None,
            'status_text': bs.status_text,
            'status_class': bs.status_class,
            'total_syncs': bs.total_syncs or 0,
            'last_error': bs.last_error,
        },
        'last_sync': None if not last_sync else {
            'at': last_sync.synced_at.isoformat(),
            'records': last_sync.records_synced,
            'status': last_sync.status,
        },
        'today': {
            'member_scans': members_today,
            'employee_scans': employees_today,
        },
    })


@fingerprint_bp.route('/scans/recent', methods=['GET'])
@csrf.exempt
def scans_recent():
    brand_id = safe_int(request.args.get('brand_id'))
    branch_id = safe_int(request.args.get('branch_id'))
    limit = min(safe_int(request.args.get('limit'), 20) or 20, 100)
    branch = _resolve_branch(brand_id, branch_id)
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400

    today = date.today()
    rows = MemberAttendance.query.filter(
        MemberAttendance.branch_id == branch.id,
        func.date(MemberAttendance.check_in) == today,
    ).order_by(MemberAttendance.check_in.desc()).limit(limit).all()

    scans = []
    for a in rows:
        m = a.member
        if not m:
            continue
        person_type = 'employee' if m.is_staff else 'member'
        scans.append({
            'id': a.id,
            'person_type': person_type,
            'person_name': m.name,
            'fingerprint_id': m.fingerprint_id,
            'check_in': a.check_in.isoformat(),
            'action': 'denied' if a.has_warning and not _scan_was_allowed(a) else 'check_in',
            'allowed': not a.has_warning,
            'warning': a.warning_message,
        })
    return jsonify({'success': True, 'scans': scans})


def _scan_was_allowed(att):
    """A MemberAttendance with has_warning=True and no warning_message is just informational."""
    return not att.warning_message


# ─────────────────────────────────────────────────────────────────────────────
# 7. Per-fingerprint stop / allow — quick toggle keyed by fingerprint_id.
#    Returns the same shape as one row of /fp/access-list so the desktop
#    can apply the change to backup.mdb immediately, without re-pulling
#    the full access list.
# ─────────────────────────────────────────────────────────────────────────────

@fingerprint_bp.route('/stop', methods=['POST'])
@csrf.exempt
def stop_fingerprint():
    """Stop one fingerprint immediately. Persists is_active=False."""
    data = request.get_json(silent=True) or {}
    fingerprint_id = safe_int(data.get('fingerprint_id'))
    branch = _resolve_branch(safe_int(data.get('brand_id')),
                             safe_int(data.get('branch_id')))
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400
    if fingerprint_id is None:
        return jsonify({'success': False, 'error': 'fingerprint_id required'}), 400

    member = Member.query.filter_by(
        brand_id=branch.brand_id, fingerprint_id=fingerprint_id
    ).first()
    if not member:
        return jsonify({'success': False, 'error': 'fingerprint not found'}), 404

    member.is_active = False
    log_row = _log_fp_access(member, branch, action='stop',
                             source='web' if _is_web_session() else 'api')
    db.session.commit()

    return jsonify({
        'success': True,
        'fingerprint_id': fingerprint_id,
        'emp_id': _emp_id_for(member),
        'member_id': member.id,
        'name': member.name,
        'allowed': False,
        'end_date': PAST_DATE.isoformat(),
        'reason': 'تم الإيقاف',
        'action': 'stop',
        'pressed_at': _utc_to_ksa_iso(log_row.created_at),
        'changed_at': _utc_to_ksa_iso(log_row.created_at),
        'server_time': ksa_now().isoformat(),
    })


@fingerprint_bp.route('/allow', methods=['POST'])
@csrf.exempt
def allow_fingerprint():
    """
    Allow one fingerprint. Persists is_active=True.

    The returned `end_date` is the same value /fp/access-list would compute
    for this member: their subscription end_date for a regular plan, today
    for a class member inside the window, or 2099-12-31 for staff. If they
    have no active subscription, end_date will still be 2020-01-01 — sending
    /fp/allow alone is not enough to grant access to an expired member; you
    also need a valid subscription.
    """
    data = request.get_json(silent=True) or {}
    fingerprint_id = safe_int(data.get('fingerprint_id'))
    branch = _resolve_branch(safe_int(data.get('brand_id')),
                             safe_int(data.get('branch_id')))
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400
    if fingerprint_id is None:
        return jsonify({'success': False, 'error': 'fingerprint_id required'}), 400

    member = Member.query.filter_by(
        brand_id=branch.brand_id, fingerprint_id=fingerprint_id
    ).first()
    if not member:
        return jsonify({'success': False, 'error': 'fingerprint not found'}), 404

    member.is_active = True
    log_row = _log_fp_access(member, branch, action='allow',
                             source='web' if _is_web_session() else 'api')
    db.session.commit()

    if member.is_staff:
        decision = {'allowed': True, 'end_date': FAR_FUTURE_DATE, 'reason': 'موظف'}
    else:
        decision = _compute_access(member, ksa_now(), ksa_today(),
                                   _access_window(branch))

    return jsonify({
        'success': True,
        'fingerprint_id': fingerprint_id,
        'emp_id': _emp_id_for(member),
        'member_id': member.id,
        'name': member.name,
        'allowed': decision['allowed'],
        'end_date': decision['end_date'].isoformat() if decision['end_date'] else None,
        'reason': decision['reason'],
        'action': 'allow',
        'pressed_at': _utc_to_ksa_iso(log_row.created_at),
        'changed_at': _utc_to_ksa_iso(log_row.created_at),
        'server_time': ksa_now().isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 8. Member block / unblock — called from the control panel buttons
# ─────────────────────────────────────────────────────────────────────────────

@fingerprint_bp.route('/members/<int:member_id>/block', methods=['POST'])
@login_required
@csrf.exempt
def block_member(member_id):
    member = Member.query.get_or_404(member_id)
    if not current_user.can_access_brand(member.brand_id):
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    member.is_active = False
    db.session.commit()
    return jsonify({'success': True, 'is_active': False,
                    'message': 'سيُمنع من الدخول خلال دقيقة'})


@fingerprint_bp.route('/members/<int:member_id>/unblock', methods=['POST'])
@login_required
@csrf.exempt
def unblock_member(member_id):
    member = Member.query.get_or_404(member_id)
    if not current_user.can_access_brand(member.brand_id):
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    member.is_active = True
    db.session.commit()
    return jsonify({'success': True, 'is_active': True,
                    'message': 'سيُسمح بالدخول خلال دقيقة'})


# ─────────────────────────────────────────────────────────────────────────────
# 8. HTML pages — brand picker + per-branch control panel
# ─────────────────────────────────────────────────────────────────────────────

@fingerprint_bp.route('/control/<int:brand_id>', methods=['GET'])
@login_required
def control_brand(brand_id):
    brand = Brand.query.get_or_404(brand_id)
    if not current_user.can_access_brand(brand_id):
        abort(403)
    branches = Branch.query.filter_by(brand_id=brand_id, is_active=True).all()
    return render_template('fingerprint/picker.html', brand=brand, branches=branches)


@fingerprint_bp.route('/control/<int:brand_id>/<int:branch_id>', methods=['GET'])
@login_required
def control_branch(brand_id, branch_id):
    branch = _resolve_branch(brand_id, branch_id)
    if not branch:
        abort(404)
    if not current_user.can_access_brand(brand_id):
        abort(403)
    members = Member.query.filter_by(
        brand_id=brand_id, branch_id=branch_id
    ).filter(Member.fingerprint_id.isnot(None)).order_by(Member.name).all()
    return render_template('fingerprint/control.html',
                           brand=branch.brand, branch=branch, members=members)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Lookup — "do you know this fingerprint?" + full decision context
# ─────────────────────────────────────────────────────────────────────────────

@fingerprint_bp.route('/lookup', methods=['GET', 'POST'])
@csrf.exempt
def lookup():
    """
    Look up one fingerprint and return whether we have a record for it
    plus the current access decision.

    Accepts GET (?fingerprint_id=) or POST (JSON body) — same shape either
    way. brand_id/branch_id default to the locked pair.

    Response always has:  success, found, fingerprint_id
    When found also has:  person_type, person_id, name, emp_id, is_staff,
                          is_active, allowed, end_date, reason
    """
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        brand_id = safe_int(data.get('brand_id'))
        branch_id = safe_int(data.get('branch_id'))
        fingerprint_id = safe_int(data.get('fingerprint_id'))
    else:
        brand_id = safe_int(request.args.get('brand_id'))
        branch_id = safe_int(request.args.get('branch_id'))
        fingerprint_id = safe_int(request.args.get('fingerprint_id'))

    branch = _resolve_branch(brand_id, branch_id)
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400
    if fingerprint_id is None:
        return jsonify({'success': False, 'error': 'fingerprint_id required'}), 400

    # 1. Try employee (User with this fingerprint)
    user = User.query.filter_by(
        branch_id=branch.id, fingerprint_id=fingerprint_id, is_active=True
    ).first()
    if not user:
        user = User.query.filter_by(
            brand_id=branch.brand_id, branch_id=None,
            fingerprint_id=fingerprint_id, is_active=True
        ).first()

    if user:
        return jsonify({
            'success': True,
            'found': True,
            'fingerprint_id': fingerprint_id,
            'person_type': 'employee',
            'person_id': user.id,
            'name': user.name,
            'emp_id': str(fingerprint_id).zfill(8),
            'is_staff': True,
            'is_active': user.is_active,
            'allowed': True,
            'end_date': FAR_FUTURE_DATE.isoformat(),
            'reason': 'موظف',
            'server_time': ksa_now().isoformat(),
        })

    # 2. Try member
    member = Member.query.filter_by(
        brand_id=branch.brand_id, fingerprint_id=fingerprint_id
    ).first()

    if not member:
        return jsonify({
            'success': True,
            'found': False,
            'fingerprint_id': fingerprint_id,
            'server_time': ksa_now().isoformat(),
        })

    # 3. Compute the access decision
    if not member.is_active:
        decision = {'allowed': False, 'end_date': PAST_DATE, 'reason': 'محظور من قبل الإدارة'}
    elif member.is_staff:
        decision = {'allowed': True, 'end_date': FAR_FUTURE_DATE, 'reason': 'موظف'}
    else:
        decision = _compute_access(member, ksa_now(), ksa_today(), _access_window(branch))

    return jsonify({
        'success': True,
        'found': True,
        'fingerprint_id': fingerprint_id,
        'person_type': 'member',
        'person_id': member.id,
        'name': member.name,
        'emp_id': _emp_id_for(member),
        'is_staff': member.is_staff,
        'is_active': member.is_active,
        'allowed': decision['allowed'],
        'end_date': decision['end_date'].isoformat() if decision['end_date'] else None,
        'reason': decision['reason'],
        'server_time': ksa_now().isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 10. Audit log — every stop/allow action with who/when/from where
# ─────────────────────────────────────────────────────────────────────────────

@fingerprint_bp.route('/audit', methods=['GET'])
@login_required
def audit_log():
    """
    Audit trail of every fingerprint access toggle.

    Scoping:
      - Admin (can_view_all_brands) sees all brands; can narrow with ?brand_id=
      - Brand-scoped users see only their own brand
    """
    if not (current_user.is_owner or current_user.is_brand_manager):
        abort(403)

    action = request.args.get('action', '').strip()  # '', 'stop', 'allow'
    source = request.args.get('source', '').strip()  # '', 'web', 'api', 'desktop', 'form'
    q_text = (request.args.get('q') or '').strip()
    brand_filter = request.args.get('brand_id', type=int)
    page = request.args.get('page', 1, type=int)

    base_q = FingerprintAccessLog.query
    if current_user.can_view_all_brands:
        if brand_filter:
            base_q = base_q.filter_by(brand_id=brand_filter)
    elif current_user.brand_id:
        base_q = base_q.filter_by(brand_id=current_user.brand_id)
    else:
        # User has neither all-brand access nor a brand — show nothing
        base_q = base_q.filter(db.false())

    q = base_q
    if action in ('stop', 'allow'):
        q = q.filter_by(action=action)
    if source in ('web', 'api', 'desktop', 'form'):
        q = q.filter_by(source=source)
    if q_text:
        like = f'%{q_text}%'
        q = q.filter(
            db.or_(
                FingerprintAccessLog.member_name.ilike(like),
                FingerprintAccessLog.actor_name.ilike(like),
                FingerprintAccessLog.member_import_id.ilike(like),
                db.cast(FingerprintAccessLog.fingerprint_id, db.String).ilike(like),
            )
        )

    logs = q.order_by(FingerprintAccessLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    totals = {
        'all':   base_q.count(),
        'stop':  base_q.filter_by(action='stop').count(),
        'allow': base_q.filter_by(action='allow').count(),
    }

    return render_template('fingerprint/audit.html',
                           logs=logs, totals=totals,
                           action_filter=action, source_filter=source,
                           q_text=q_text, brand_filter=brand_filter)
