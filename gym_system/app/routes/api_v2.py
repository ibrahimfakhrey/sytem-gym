"""
Bridge API v2 — clean, branch-scoped endpoints for the new desktop software.

Auth: X-Branch-Code header (each gym gets a unique code like BR-3-1).
Time: All gym-time decisions use Asia/Riyadh (UTC+3, no DST).
"""

from datetime import datetime, date, time, timedelta
from functools import wraps

from flask import Blueprint, request, jsonify
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # Python 3.8

from app import db, csrf
from app.models.company import Branch
from app.models.member import Member
from app.models.subscription import Subscription
from app.models.classes import GymClass, ClassBooking
from app.models.attendance import MemberAttendance, EmployeeAttendance
from app.models.user import User
from app.models.employee import EmployeeShift, EmployeeSettings, EmployeeLateRule, EmployeeDeduction
from app.models.fingerprint import BridgeStatus

api_v2_bp = Blueprint('api_v2', __name__, url_prefix='/api/v2')

KSA_TZ = ZoneInfo("Asia/Riyadh")
PAST_DATE = date(2020, 1, 1)        # used to block access via end_date in the past
FAR_FUTURE_DATE = date(2099, 12, 31)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def ksa_now():
    """Current datetime in Asia/Riyadh timezone (timezone-aware)."""
    return datetime.now(KSA_TZ)


def ksa_today():
    """Today's date in Asia/Riyadh timezone."""
    return ksa_now().date()


def parse_iso_dt(s):
    """Parse ISO 8601 string → naive datetime. Returns None on failure."""
    if not s:
        return None
    try:
        # Strip timezone if present, treat as KSA local time
        s = s.replace('Z', '').split('+')[0]
        return datetime.fromisoformat(s)
    except (ValueError, TypeError, AttributeError):
        return None


def parse_iso_date(s):
    """Parse YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS string → date."""
    if not s:
        return None
    try:
        # Take just the date portion (handles "2024-06-13" and "2024-06-13T00:00:00")
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


# ─────────────────────────────────────────────────────────────────────────────
# Auth — X-Branch-Code header maps to a Branch record
# ─────────────────────────────────────────────────────────────────────────────

def require_branch_code(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        code = request.headers.get('X-Branch-Code', '').strip()
        if not code:
            return jsonify({'success': False, 'error': 'X-Branch-Code header required'}), 401

        branch = Branch.query.filter_by(branch_code=code).first()
        if not branch:
            return jsonify({'success': False, 'error': 'Invalid branch code'}), 401
        if not branch.is_active:
            return jsonify({'success': False, 'error': 'Branch is inactive'}), 403

        request.branch = branch
        return f(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# 1. Health  (GET /api/v2/health)
# ─────────────────────────────────────────────────────────────────────────────

@api_v2_bp.route('/health', methods=['GET'])
@require_branch_code
def health():
    branch = request.branch
    return jsonify({
        'success': True,
        'status': 'ok',
        'branch_id': branch.id,
        'branch_name': branch.name,
        'brand_id': branch.brand_id,
        'brand_name': branch.brand.name if branch.brand else '',
        'server_time': ksa_now().isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2. Heartbeat  (POST /api/v2/heartbeat)
# ─────────────────────────────────────────────────────────────────────────────

@api_v2_bp.route('/heartbeat', methods=['POST'])
@require_branch_code
def heartbeat():
    data = request.get_json(silent=True) or {}
    branch = request.branch

    bs = BridgeStatus.query.filter_by(branch_id=branch.id).first()
    if not bs:
        bs = BridgeStatus(brand_id=branch.brand_id, branch_id=branch.id)
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

    return jsonify({
        'success': True,
        'server_time': ksa_now().isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 3. Full Sync  (POST /api/v2/full-sync)
#    First-launch upload of entire backup.mdb + last 30 days of att2000.mdb
# ─────────────────────────────────────────────────────────────────────────────

@api_v2_bp.route('/full-sync', methods=['POST'])
@require_branch_code
def full_sync():
    data = request.get_json(silent=True) or {}
    members_data = data.get('members', [])
    attendance_data = data.get('attendance', [])
    branch = request.branch
    brand_id = branch.brand_id

    members_created = 0
    members_updated = 0
    id_mapping = {}

    # ── Members ──
    for m in members_data:
        emp_id = (m.get('emp_id') or '').strip()
        if not emp_id:
            continue

        existing = Member.query.filter_by(
            brand_id=brand_id, member_import_id=emp_id
        ).first()

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
            id_mapping[emp_id] = existing.id
            members_updated += 1
        else:
            sex_raw = (m.get('sex') or '').strip()
            gender = 'male' if sex_raw in ('0', 'M', 'm') else 'female' if sex_raw in ('1', 'F', 'f') else None

            new_member = Member(
                brand_id=brand_id,
                branch_id=branch.id,
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
            id_mapping[emp_id] = new_member.id
            members_created += 1

    db.session.commit()

    # ── Attendance ──
    attendance_created = 0
    duplicates = 0
    skipped_unknown = 0

    for a in attendance_data:
        userid = safe_int(a.get('userid'))
        timestamp = parse_iso_dt(a.get('checktime'))
        device_log_id = safe_int(a.get('device_log_id'))

        if userid is None or timestamp is None:
            continue

        member = Member.query.filter_by(brand_id=brand_id, fingerprint_id=userid).first()
        if not member:
            skipped_unknown += 1
            continue

        # Duplicate check by (member_id + check_in) within 1 min
        existing = MemberAttendance.query.filter(
            MemberAttendance.member_id == member.id,
            MemberAttendance.check_in == timestamp,
        ).first()
        if existing:
            duplicates += 1
            continue

        att = MemberAttendance(
            member_id=member.id,
            brand_id=brand_id,
            branch_id=branch.id,
            check_in=timestamp,
            source='fingerprint',
            fingerprint_log_id=device_log_id,
        )
        db.session.add(att)
        attendance_created += 1

    db.session.commit()

    return jsonify({
        'success': True,
        'branch': {
            'id': branch.id,
            'name': branch.name,
            'brand_id': brand_id,
            'brand_name': branch.brand.name if branch.brand else '',
        },
        'import_summary': {
            'members_created': members_created,
            'members_updated': members_updated,
            'attendance_imported': attendance_created,
            'duplicates_skipped': duplicates,
            'skipped_unknown_fingerprints': skipped_unknown,
        },
        'id_mapping': id_mapping,
        'server_time': ksa_now().isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 4. Regular Sync  (POST /api/v2/sync)
#    Incremental: new members + new attendance scans since last sync
# ─────────────────────────────────────────────────────────────────────────────

@api_v2_bp.route('/sync', methods=['POST'])
@require_branch_code
def sync():
    data = request.get_json(silent=True) or {}
    new_members = data.get('new_members', [])
    new_attendance = data.get('new_attendance', [])
    branch = request.branch
    brand_id = branch.brand_id

    members_synced = 0
    attendance_synced = 0
    employee_attendance_updated = 0

    # ── Process new members ──
    for m in new_members:
        emp_id = (m.get('emp_id') or '').strip()
        if not emp_id:
            continue
        existing = Member.query.filter_by(
            brand_id=brand_id, member_import_id=emp_id
        ).first()
        if existing:
            continue  # already exists, skip

        card_id = m.get('card_id')
        fingerprint_id = safe_int(card_id) if card_id else None
        sex_raw = (m.get('sex') or '').strip()
        gender = 'male' if sex_raw in ('0', 'M', 'm') else 'female' if sex_raw in ('1', 'F', 'f') else None

        new_member = Member(
            brand_id=brand_id,
            branch_id=branch.id,
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
        members_synced += 1

    db.session.commit()

    # ── Process new attendance scans ──
    employee_scans_today = []  # collect employee scans for real-time recompute

    for a in new_attendance:
        userid = safe_int(a.get('userid'))
        timestamp = parse_iso_dt(a.get('checktime'))
        device_log_id = safe_int(a.get('device_log_id'))

        if userid is None or timestamp is None:
            continue

        # 1. Try as member
        member = Member.query.filter_by(brand_id=brand_id, fingerprint_id=userid).first()
        if member:
            existing = MemberAttendance.query.filter_by(
                member_id=member.id, check_in=timestamp
            ).first()
            if not existing:
                att = MemberAttendance(
                    member_id=member.id,
                    brand_id=brand_id,
                    branch_id=branch.id,
                    check_in=timestamp,
                    source='fingerprint',
                    fingerprint_log_id=device_log_id,
                )
                db.session.add(att)
                attendance_synced += 1

        # 2. Try as employee (User with this fingerprint_id)
        user = User.query.filter_by(brand_id=brand_id, fingerprint_id=userid).first()
        if user:
            employee_scans_today.append((user, timestamp))

    db.session.commit()

    # ── Recompute employee attendance for affected users (real-time) ──
    seen_user_dates = set()
    for user, ts in employee_scans_today:
        scan_date = ts.date()
        key = (user.id, scan_date)
        if key in seen_user_dates:
            continue
        seen_user_dates.add(key)
        _recompute_employee_attendance(user, scan_date, branch.id)
        employee_attendance_updated += 1

    db.session.commit()

    return jsonify({
        'success': True,
        'server_time': ksa_now().isoformat(),
        'members_synced': members_synced,
        'attendance_synced': attendance_synced,
        'employee_attendance_updated': employee_attendance_updated,
        'next_sync_in_seconds': 60,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 5. Access State  (GET /api/v2/access-state)
#    Returns the desired end_date for every member based on subscription + classes.
#    Desktop applies these to backup.mdb so the device blocks/allows entry.
# ─────────────────────────────────────────────────────────────────────────────

@api_v2_bp.route('/access-state', methods=['GET'])
@require_branch_code
def access_state():
    branch = request.branch
    brand_id = branch.brand_id
    now = ksa_now()
    today = now.date()

    # Bridge settings — class access window (default 15 min before class)
    from app.models.fingerprint import BridgeSettings
    settings = BridgeSettings.query.filter_by(branch_id=branch.id).first() \
               or BridgeSettings.query.filter_by(brand_id=brand_id, branch_id=None).first()
    window_minutes = settings.class_access_window_minutes if settings else 15

    # Include inactive members too — they need to be blocked at the device.
    # If we only return active ones, the desktop never updates their end_date
    # and a soft-blocked member could still enter.
    members = Member.query.filter(
        Member.brand_id == brand_id,
        Member.fingerprint_id.isnot(None),
        Member.member_import_id.isnot(None),
    ).all()

    out = []
    for m in members:
        if not m.is_active:
            decision = {
                'allowed': False,
                'end_date': PAST_DATE,
                'reason': 'محظور من قبل الإدارة',
            }
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


def _compute_access(member, now, today, window_minutes):
    """Return {'allowed': bool, 'end_date': date, 'reason': str}"""
    # 1. Find active subscription
    sub = Subscription.query.filter(
        Subscription.member_id == member.id,
        Subscription.status == 'active',
    ).order_by(Subscription.end_date.desc()).first()

    if not sub:
        return {'allowed': False, 'end_date': PAST_DATE, 'reason': 'لا يوجد اشتراك نشط'}

    if sub.end_date < today:
        return {'allowed': False, 'end_date': PAST_DATE, 'reason': 'اشتراك منتهي'}

    # 2. Plan requires class booking?
    requires_class = False
    if sub.plan and getattr(sub.plan, 'service_type', None):
        requires_class = bool(getattr(sub.plan.service_type, 'requires_class_booking', False))

    if not requires_class:
        # Regular subscription — allowed all day until end_date
        return {'allowed': True, 'end_date': sub.end_date, 'reason': 'اشتراك نشط'}

    # 3. Class member — must have booking AND be inside class window
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

    # Compute window in KSA time: [start - window_min, end_time]
    start_dt = datetime.combine(today, cls.start_time, tzinfo=KSA_TZ)
    end_dt = datetime.combine(today, cls.end_time, tzinfo=KSA_TZ)
    window_start = start_dt - timedelta(minutes=window_minutes)

    if window_start <= now <= end_dt:
        # Inside window — allow today only
        return {
            'allowed': True,
            'end_date': today,
            'reason': f'كلاس {cls.name} - {cls.start_time.strftime("%H:%M")}',
        }
    else:
        # Outside window — block
        return {
            'allowed': False,
            'end_date': PAST_DATE,
            'reason': 'خارج وقت الكلاس',
        }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Employee Attendance Recompute Helper
# ─────────────────────────────────────────────────────────────────────────────

def _recompute_employee_attendance(user, target_date, branch_id):
    """
    Recompute EmployeeAttendance for (user, date) from MemberAttendance scans
    that match this user's fingerprint. Idempotent.
    """
    if not user.fingerprint_id:
        return

    # Get all scans for this user on this date
    start_dt = datetime.combine(target_date, time.min)
    end_dt = datetime.combine(target_date, time.max)

    # Note: MemberAttendance is keyed by member_id, not fingerprint_id.
    # Employee scans are stored by fingerprint matching User.fingerprint_id.
    # We need a separate query — find MemberAttendance via member.fingerprint_id.
    scans = db.session.query(MemberAttendance).join(
        Member, Member.id == MemberAttendance.member_id
    ).filter(
        Member.fingerprint_id == user.fingerprint_id,
        Member.brand_id == user.brand_id,
        MemberAttendance.check_in >= start_dt,
        MemberAttendance.check_in <= end_dt,
    ).order_by(MemberAttendance.check_in.asc()).all()

    if not scans:
        # Could also delete existing attendance row if it exists, but leave it for now
        return

    first_scan = scans[0].check_in.time()
    last_scan = scans[-1].check_in.time() if len(scans) > 1 else None

    # Get expected check-in from shift
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

    # Calculate late minutes
    late_minutes = 0
    if expected_check_in:
        first_dt = datetime.combine(target_date, first_scan)
        expected_dt = datetime.combine(target_date, expected_check_in)
        if first_dt > expected_dt:
            late_minutes = int((first_dt - expected_dt).total_seconds() / 60)

    status = 'present'
    if late_minutes > late_threshold:
        status = 'late'

    # Upsert EmployeeAttendance
    attendance = EmployeeAttendance.query.filter_by(
        user_id=user.id, date=target_date
    ).first()

    if not attendance:
        attendance = EmployeeAttendance(
            user_id=user.id,
            brand_id=user.brand_id,
            branch_id=branch_id,
            date=target_date,
        )
        db.session.add(attendance)

    attendance.check_in = first_scan
    attendance.check_out = last_scan
    attendance.expected_check_in = expected_check_in
    attendance.late_minutes = late_minutes
    attendance.status = status
    attendance.source = 'fingerprint'

    # Apply tiered late deductions if configured and late
    if status == 'late' and settings and settings.auto_deduction_enabled:
        # Find applicable rule (highest min_late_minutes <= late_minutes)
        rule = EmployeeLateRule.query.filter(
            EmployeeLateRule.brand_id == user.brand_id,
            EmployeeLateRule.min_late_minutes <= late_minutes,
        ).order_by(EmployeeLateRule.min_late_minutes.desc()).first()

        if rule:
            # Avoid duplicate deduction for the same date
            existing_ded = EmployeeDeduction.query.filter_by(
                user_id=user.id,
                deduction_date=target_date,
                deduction_type='late',
            ).first()
            if not existing_ded:
                ded = EmployeeDeduction(
                    user_id=user.id,
                    brand_id=user.brand_id,
                    title=f'تأخير {late_minutes} دقيقة',
                    amount=rule.deduction_amount,
                    reason=f'تأخير عن موعد العمل بمقدار {late_minutes} دقيقة',
                    deduction_type='late',
                    deduction_date=target_date,
                )
                db.session.add(ded)


# ─────────────────────────────────────────────────────────────────────────────
# Register CSRF exemption (set when blueprint registered in app/__init__.py)
# ─────────────────────────────────────────────────────────────────────────────
