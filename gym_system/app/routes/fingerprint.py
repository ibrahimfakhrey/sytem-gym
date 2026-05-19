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
from app.models.fingerprint import BridgeStatus, BridgeSettings, FingerprintSyncLog

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
    """Return Branch or None. brand_id is required for cross-check."""
    if not brand_id or not branch_id:
        return None
    return Branch.query.filter_by(id=branch_id, brand_id=brand_id).first()


def _emp_id_for(member):
    """Same key the desktop uses to identify a person in backup.mdb."""
    return member.member_import_id or str(member.fingerprint_id).zfill(8)


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
        Subscription.end_date >= date.today()
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

@fingerprint_bp.route('/access-list', methods=['GET'])
@csrf.exempt
def access_list():
    brand_id = safe_int(request.args.get('brand_id'))
    branch_id = safe_int(request.args.get('branch_id'))
    branch = _resolve_branch(brand_id, branch_id)
    if not branch:
        return jsonify({'success': False, 'error': 'invalid brand_id/branch_id'}), 400

    now = ksa_now()
    today = now.date()
    window_minutes = _access_window(branch)

    members = Member.query.filter(
        Member.brand_id == brand_id,
        Member.fingerprint_id.isnot(None),
        Member.member_import_id.isnot(None),
    ).all()

    out = []
    for m in members:
        if not m.is_active:
            decision = {'allowed': False, 'end_date': PAST_DATE, 'reason': 'محظور من قبل الإدارة'}
        elif m.is_staff:
            decision = {'allowed': True, 'end_date': FAR_FUTURE_DATE, 'reason': 'موظف'}
        else:
            decision = _compute_access(m, now, today, window_minutes)
        out.append({
            'emp_id': m.member_import_id,
            'fingerprint_id': m.fingerprint_id,
            'allowed': decision['allowed'],
            'end_date': decision['end_date'].isoformat() if decision['end_date'] else None,
            'reason': decision['reason'],
        })

    return jsonify({
        'success': True,
        'computed_at': now.isoformat(),
        'access_window_minutes': window_minutes,
        'count': len(out),
        'members': out,
    })


def _access_window(branch):
    settings = (BridgeSettings.query.filter_by(branch_id=branch.id).first()
                or BridgeSettings.query.filter_by(brand_id=branch.brand_id, branch_id=None).first())
    return settings.class_access_window_minutes if settings else 15


def _compute_access(member, now, today, window_minutes):
    sub = Subscription.query.filter(
        Subscription.member_id == member.id,
        Subscription.status == 'active',
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
# 7. Member block / unblock — called from the control panel buttons
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
