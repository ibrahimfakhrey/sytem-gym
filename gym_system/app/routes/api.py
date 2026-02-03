from flask import Blueprint, request, jsonify, current_app
from functools import wraps
from datetime import datetime, date, timedelta
import json

from app import db
from app.models.company import Brand, Branch
from app.models.member import Member
from app.models.user import User, Role
from app.models.subscription import Subscription, Plan
from app.models.attendance import MemberAttendance, EmployeeAttendance
from app.models.fingerprint import FingerprintSyncLog, BridgeStatus, DeviceCommand
from app.models.service import ServiceType
from app.models.health import HealthReport
from app.models.complaint import Complaint, ComplaintCategory
from app.models.classes import GymClass, ClassBooking
from app.models.daily_closing import DailyClosing
from app.models.giftcard import GiftCard
from app.models.offer import PromotionalOffer

api_bp = Blueprint('api', __name__)


def require_api_key(f):
    """Decorator to require API key for fingerprint sync"""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        expected_key = current_app.config.get('FINGERPRINT_API_KEY')

        if not api_key or api_key != expected_key:
            return jsonify({'error': 'Invalid API key'}), 401

        return f(*args, **kwargs)
    return decorated


@api_bp.route('/fingerprint/health')
@require_api_key
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat()
    })


@api_bp.route('/fingerprint/attendance', methods=['POST'])
@require_api_key
def sync_attendance():
    """
    Sync attendance from fingerprint device
    Automatically detects if fingerprint belongs to staff (User) or member (Member)

    Request body:
    {
        "brand_id": 1,
        "records": [
            {
                "fingerprint_id": 123,
                "timestamp": "2024-01-15T09:30:00",
                "log_id": 456
            }
        ]
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    brand_id = data.get('brand_id')
    records = data.get('records', [])

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    # Verify brand exists and uses fingerprint
    brand = Brand.query.get(brand_id)
    if not brand or not brand.uses_fingerprint:
        return jsonify({'error': 'Invalid brand or fingerprint not enabled'}), 400

    synced = 0
    staff_synced = 0
    member_synced = 0
    errors = []
    blocked_entries = []

    for record in records:
        try:
            fingerprint_id = record.get('fingerprint_id')
            timestamp_str = record.get('timestamp')
            log_id = record.get('log_id')

            if not fingerprint_id or not timestamp_str:
                errors.append(f"Missing data in record: {record}")
                continue

            # Parse timestamp
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except:
                errors.append(f"Invalid timestamp: {timestamp_str}")
                continue

            # First check if fingerprint belongs to staff (User)
            staff_user = User.query.filter_by(
                brand_id=brand_id,
                fingerprint_id=fingerprint_id,
                is_active=True
            ).first()

            if staff_user:
                # This is a staff member - create EmployeeAttendance
                # Check for duplicate
                if log_id:
                    existing = EmployeeAttendance.query.filter_by(
                        user_id=staff_user.id,
                        fingerprint_log_id=log_id
                    ).first()
                    if existing:
                        continue

                attendance = EmployeeAttendance(
                    user_id=staff_user.id,
                    brand_id=brand_id,
                    check_in=timestamp,
                    source='fingerprint',
                    fingerprint_log_id=log_id
                )
                db.session.add(attendance)
                staff_synced += 1
                synced += 1
                continue

            # Check if fingerprint belongs to member
            member = Member.query.filter_by(
                brand_id=brand_id,
                fingerprint_id=fingerprint_id
            ).first()

            if not member:
                errors.append(f"No staff or member found for fingerprint_id: {fingerprint_id}")
                continue

            # Check for duplicate log_id
            if log_id:
                existing = MemberAttendance.query.filter_by(
                    fingerprint_log_id=log_id
                ).first()
                if existing:
                    continue  # Skip duplicate

            # Get active subscription
            subscription = Subscription.query.filter(
                Subscription.member_id == member.id,
                Subscription.status == 'active',
                Subscription.end_date >= date.today()
            ).first()

            # Check subscription status
            has_warning = False
            warning_message = None
            is_blocked = False

            if not subscription:
                has_warning = True
                is_blocked = True
                # Check if expired or frozen
                last_sub = Subscription.query.filter_by(
                    member_id=member.id
                ).order_by(Subscription.end_date.desc()).first()

                if last_sub and last_sub.status == 'frozen':
                    warning_message = 'الاشتراك مجمد'
                elif last_sub and last_sub.end_date < date.today():
                    warning_message = 'الاشتراك منتهي'
                else:
                    warning_message = 'لا يوجد اشتراك نشط'

                blocked_entries.append({
                    'member_id': member.id,
                    'member_name': member.name,
                    'fingerprint_id': fingerprint_id,
                    'reason': warning_message
                })
            else:
                # Check if subscription requires class booking
                plan = subscription.plan
                if plan and plan.requires_class_booking:
                    # Check if member has a booking for today
                    today_booking = ClassBooking.query.filter(
                        ClassBooking.member_id == member.id,
                        ClassBooking.booking_date == date.today(),
                        ClassBooking.status.in_(['booked', 'attended'])
                    ).first()

                    if not today_booking:
                        has_warning = True
                        warning_message = 'يجب حجز كلاس قبل الدخول'
                        # Note: We still allow entry but with warning

            # Create attendance record
            attendance = MemberAttendance(
                member_id=member.id,
                subscription_id=subscription.id if subscription else None,
                brand_id=brand_id,
                check_in=timestamp,
                source='fingerprint',
                fingerprint_log_id=log_id,
                has_warning=has_warning,
                warning_message=warning_message
            )
            db.session.add(attendance)
            member_synced += 1
            synced += 1

        except Exception as e:
            errors.append(str(e))

    # Commit all records
    if synced > 0:
        db.session.commit()

    # Log sync
    sync_log = FingerprintSyncLog(
        brand_id=brand_id,
        sync_type='attendance',
        records_synced=synced,
        last_sync_id=records[-1].get('log_id') if records else None,
        status='success' if not errors else ('partial' if synced > 0 else 'failed'),
        error_message='\n'.join(errors[:10]) if errors else None
    )
    db.session.add(sync_log)
    db.session.commit()

    return jsonify({
        'success': True,
        'synced': synced,
        'staff_synced': staff_synced,
        'member_synced': member_synced,
        'blocked_entries': blocked_entries,
        'errors': errors[:10]
    })


@api_bp.route('/fingerprint/members/pending')
@require_api_key
def get_pending_enrollments():
    """
    Get members pending fingerprint enrollment
    """
    brand_id = request.args.get('brand_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    members = Member.query.filter_by(
        brand_id=brand_id,
        fingerprint_enrolled=False,
        is_active=True
    ).all()

    return jsonify({
        'members': [
            {
                'id': m.id,
                'fingerprint_id': m.fingerprint_id,
                'name': m.name,
                'phone': m.phone
            }
            for m in members
        ]
    })


@api_bp.route('/fingerprint/members/enrolled', methods=['POST'])
@require_api_key
def mark_enrolled():
    """
    Mark member as enrolled (fingerprint registered)

    Request body:
    {
        "member_id": 1,
        "fingerprint_id": 123
    }
    """
    data = request.get_json()

    member_id = data.get('member_id')
    fingerprint_id = data.get('fingerprint_id')

    if not member_id:
        return jsonify({'error': 'member_id is required'}), 400

    member = Member.query.get(member_id)

    if not member:
        return jsonify({'error': 'Member not found'}), 404

    member.fingerprint_enrolled = True
    member.fingerprint_enrolled_at = datetime.utcnow()

    if fingerprint_id:
        member.fingerprint_id = fingerprint_id

    db.session.commit()

    # Log
    sync_log = FingerprintSyncLog(
        brand_id=member.brand_id,
        sync_type='enrollment',
        records_synced=1,
        status='success'
    )
    db.session.add(sync_log)
    db.session.commit()

    return jsonify({
        'success': True,
        'member_id': member.id,
        'fingerprint_id': member.fingerprint_id
    })


@api_bp.route('/fingerprint/sync-status')
@require_api_key
def sync_status():
    """Get sync status for brand"""
    brand_id = request.args.get('brand_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    status = FingerprintSyncLog.get_sync_status(brand_id)
    last_sync = FingerprintSyncLog.get_last_sync(brand_id)

    return jsonify({
        'status': status['status'],
        'message': status['message'],
        'last_sync': last_sync.synced_at.isoformat() if last_sync else None,
        'last_sync_records': last_sync.records_synced if last_sync else 0
    })


@api_bp.route('/fingerprint/bridge/heartbeat', methods=['POST'])
@require_api_key
def bridge_heartbeat():
    """
    Receive heartbeat from bridge service

    Request body:
    {
        "brand_id": 1,
        "computer_name": "GYM-PC-01",
        "ip_address": "192.168.1.100",
        "os_info": "Windows 10",
        "database_path": "C:\\AAS\\Data\\AAS.adb",
        "database_found": true,
        "error": null
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    brand_id = data.get('brand_id')
    computer_name = data.get('computer_name', 'Unknown')

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    # Get or create bridge status
    bridge = BridgeStatus.get_or_create(brand_id, computer_name)

    # Update info
    bridge.ip_address = data.get('ip_address')
    bridge.os_info = data.get('os_info')
    bridge.database_path = data.get('database_path')
    bridge.database_found = data.get('database_found', False)
    bridge.last_heartbeat = datetime.utcnow()
    bridge.is_online = True

    if data.get('error'):
        bridge.last_error = data.get('error')

    if data.get('sync_count'):
        bridge.total_syncs = (bridge.total_syncs or 0) + data.get('sync_count')

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Heartbeat received',
        'server_time': datetime.utcnow().isoformat()
    })


@api_bp.route('/fingerprint/bridge/status')
@require_api_key
def get_bridge_status():
    """Get all bridge statuses for a brand"""
    brand_id = request.args.get('brand_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    bridges = BridgeStatus.query.filter_by(brand_id=brand_id).all()

    return jsonify({
        'bridges': [
            {
                'id': b.id,
                'computer_name': b.computer_name,
                'ip_address': b.ip_address,
                'os_info': b.os_info,
                'database_path': b.database_path,
                'database_found': b.database_found,
                'status': b.status_text,
                'status_class': b.status_class,
                'last_heartbeat': b.last_heartbeat.isoformat() if b.last_heartbeat else None,
                'first_seen': b.first_seen.isoformat() if b.first_seen else None,
                'total_syncs': b.total_syncs,
                'last_error': b.last_error
            }
            for b in bridges
        ]
    })


# =============================================================================
# DEVICE COMMANDS API (for software to execute on .mdb)
# =============================================================================

@api_bp.route('/device/commands', methods=['GET'])
@require_api_key
def get_pending_commands():
    """Get pending commands for the desktop software to execute"""
    brand_id = request.args.get('brand_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    commands = DeviceCommand.get_pending_commands(brand_id)

    return jsonify({
        'success': True,
        'commands': [
            {
                'id': cmd.id,
                'command_type': cmd.command_type,
                'target_emp_id': cmd.target_emp_id,
                'member_id': cmd.member_id,
                'command_data': json.loads(cmd.command_data) if cmd.command_data else {},
                'created_at': cmd.created_at.isoformat()
            }
            for cmd in commands
        ]
    })


@api_bp.route('/device/commands/<int:command_id>/complete', methods=['POST'])
@require_api_key
def complete_command(command_id):
    """Mark a command as completed"""
    command = DeviceCommand.query.get(command_id)

    if not command:
        return jsonify({'error': 'Command not found'}), 404

    data = request.get_json() or {}

    if data.get('success', True):
        command.status = 'completed'
    else:
        command.status = 'failed'
        command.error_message = data.get('error_message', 'Unknown error')

    command.executed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True, 'message': 'Command status updated'})


@api_bp.route('/device/commands/block-member', methods=['POST'])
@require_api_key
def block_member_command():
    """Create command to block a member (set end_date to past)"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    brand_id = data.get('brand_id')
    member_id = data.get('member_id')
    emp_id = data.get('emp_id')

    if not all([brand_id, emp_id]):
        return jsonify({'error': 'brand_id and emp_id are required'}), 400

    command = DeviceCommand(
        brand_id=brand_id,
        command_type='block_member',
        target_emp_id=emp_id,
        member_id=member_id,
        command_data=json.dumps({'end_date': '2020-01-01'}),
        status='pending'
    )
    db.session.add(command)
    db.session.commit()

    return jsonify({'success': True, 'command_id': command.id}), 201


@api_bp.route('/device/commands/unblock-member', methods=['POST'])
@require_api_key
def unblock_member_command():
    """Create command to unblock a member (set end_date to future)"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    brand_id = data.get('brand_id')
    member_id = data.get('member_id')
    emp_id = data.get('emp_id')
    end_date = data.get('end_date')

    if not all([brand_id, emp_id, end_date]):
        return jsonify({'error': 'brand_id, emp_id, and end_date are required'}), 400

    command = DeviceCommand(
        brand_id=brand_id,
        command_type='unblock_member',
        target_emp_id=emp_id,
        member_id=member_id,
        command_data=json.dumps({'end_date': end_date}),
        status='pending'
    )
    db.session.add(command)
    db.session.commit()

    return jsonify({'success': True, 'command_id': command.id}), 201


@api_bp.route('/device/commands/update-member', methods=['POST'])
@require_api_key
def update_member_command():
    """Create command to update member data in .mdb"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    brand_id = data.get('brand_id')
    member_id = data.get('member_id')
    emp_id = data.get('emp_id')
    updates = data.get('updates', {})

    if not all([brand_id, emp_id]):
        return jsonify({'error': 'brand_id and emp_id are required'}), 400

    command = DeviceCommand(
        brand_id=brand_id,
        command_type='update_member',
        target_emp_id=emp_id,
        member_id=member_id,
        command_data=json.dumps(updates),
        status='pending'
    )
    db.session.add(command)
    db.session.commit()

    return jsonify({'success': True, 'command_id': command.id}), 201


@api_bp.route('/device/commands/add-member', methods=['POST'])
@require_api_key
def add_member_command():
    """Create command to add new member to .mdb"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    brand_id = data.get('brand_id')
    member_id = data.get('member_id')
    member_data = data.get('member_data', {})

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    if 'emp_id' not in member_data:
        return jsonify({'error': 'emp_id is required in member_data'}), 400

    command = DeviceCommand(
        brand_id=brand_id,
        command_type='add_member',
        target_emp_id=member_data.get('emp_id'),
        member_id=member_id,
        command_data=json.dumps(member_data),
        status='pending'
    )
    db.session.add(command)
    db.session.commit()

    return jsonify({'success': True, 'command_id': command.id}), 201


# =============================================================================
# SYNC API
# =============================================================================

@api_bp.route('/sync/status', methods=['GET'])
@require_api_key
def get_sync_status():
    """Get overall sync status for desktop software dashboard"""
    brand_id = request.args.get('brand_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    pending_commands = DeviceCommand.query.filter_by(
        brand_id=brand_id,
        status='pending'
    ).count()

    last_sync = FingerprintSyncLog.get_last_sync(brand_id)
    members_count = Member.query.filter_by(brand_id=brand_id, is_active=True).count()
    pending_enrollment = Member.query.filter_by(
        brand_id=brand_id,
        fingerprint_enrolled=False,
        is_active=True
    ).count()
    today_attendance = MemberAttendance.get_today_count(brand_id)

    return jsonify({
        'success': True,
        'status': {
            'connected': True,
            'pending_commands': pending_commands,
            'last_sync': last_sync.synced_at.isoformat() if last_sync else None,
            'members_count': members_count,
            'pending_enrollment': pending_enrollment,
            'today_attendance': today_attendance
        }
    })


@api_bp.route('/sync/heartbeat', methods=['POST'])
@require_api_key
def sync_heartbeat():
    """Heartbeat from desktop software (called every 30 seconds)"""
    data = request.get_json() or {}
    brand_id = data.get('brand_id')

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    pending_commands = DeviceCommand.query.filter_by(
        brand_id=brand_id,
        status='pending'
    ).count()

    return jsonify({
        'success': True,
        'pending_commands': pending_commands,
        'server_time': datetime.utcnow().isoformat()
    })


# =============================================================================
# SERVICE TYPES API
# =============================================================================

@api_bp.route('/service-types', methods=['GET'])
@require_api_key
def get_service_types():
    """Get all service types for a brand"""
    brand_id = request.args.get('brand_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    service_types = ServiceType.query.filter_by(brand_id=brand_id).all()

    return jsonify({
        'success': True,
        'service_types': [
            {
                'id': st.id,
                'name': st.name,
                'name_en': st.name_en,
                'category': st.category,
                'description': st.description,
                'requires_class_booking': st.requires_class_booking,
                'capacity': st.capacity,
                'is_active': st.is_active
            }
            for st in service_types
        ]
    })


@api_bp.route('/service-types', methods=['POST'])
@require_api_key
def create_service_type():
    """Create a new service type"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required_fields = ['brand_id', 'name']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    service_type = ServiceType(
        brand_id=data['brand_id'],
        name=data['name'],
        name_en=data.get('name_en'),
        category=data.get('category', 'gym'),
        description=data.get('description'),
        requires_class_booking=data.get('requires_class_booking', False),
        capacity=data.get('capacity'),
        is_active=data.get('is_active', True)
    )
    db.session.add(service_type)
    db.session.commit()

    return jsonify({
        'success': True,
        'service_type_id': service_type.id,
        'message': 'تم إنشاء نوع الخدمة بنجاح'
    }), 201


@api_bp.route('/service-types/<int:service_type_id>', methods=['PUT'])
@require_api_key
def update_service_type(service_type_id):
    """Update a service type"""
    service_type = ServiceType.query.get(service_type_id)

    if not service_type:
        return jsonify({'error': 'Service type not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Update fields
    if 'name' in data:
        service_type.name = data['name']
    if 'name_en' in data:
        service_type.name_en = data['name_en']
    if 'category' in data:
        service_type.category = data['category']
    if 'description' in data:
        service_type.description = data['description']
    if 'requires_class_booking' in data:
        service_type.requires_class_booking = data['requires_class_booking']
    if 'capacity' in data:
        service_type.capacity = data['capacity']
    if 'is_active' in data:
        service_type.is_active = data['is_active']

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'تم تحديث نوع الخدمة بنجاح'
    })


@api_bp.route('/service-types/<int:service_type_id>', methods=['DELETE'])
@require_api_key
def delete_service_type(service_type_id):
    """Delete a service type"""
    service_type = ServiceType.query.get(service_type_id)

    if not service_type:
        return jsonify({'error': 'Service type not found'}), 404

    # Check if used by plans
    if service_type.plans.count() > 0:
        return jsonify({'error': 'لا يمكن حذف نوع الخدمة لوجود باقات مرتبطة به'}), 400

    db.session.delete(service_type)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'تم حذف نوع الخدمة بنجاح'
    })


# =============================================================================
# HEALTH REPORTS API
# =============================================================================

@api_bp.route('/members/<int:member_id>/health-report', methods=['GET'])
@require_api_key
def get_member_health_report(member_id):
    """Get health reports for a member"""
    member = Member.query.get(member_id)

    if not member:
        return jsonify({'error': 'Member not found'}), 404

    reports = HealthReport.query.filter_by(member_id=member_id).order_by(HealthReport.created_at.desc()).all()

    return jsonify({
        'success': True,
        'member_id': member_id,
        'member_name': member.name,
        'reports': [
            {
                'id': r.id,
                'height_cm': r.height_cm,
                'weight_kg': r.weight_kg,
                'age': r.age,
                'gender': r.gender,
                'bmi': r.bmi,
                'bmi_category': r.bmi_category,
                'metabolic_rate': r.metabolic_rate,
                'daily_calories': r.daily_calories,
                'ideal_weight': r.ideal_weight,
                'weight_difference': r.weight_difference,
                'status': r.status,
                'status_arabic': r.status_arabic,
                'status_message': r.status_message,
                'created_at': r.created_at.isoformat()
            }
            for r in reports
        ]
    })


@api_bp.route('/members/<int:member_id>/health-report', methods=['POST'])
@require_api_key
def create_member_health_report(member_id):
    """Create a health report for a member"""
    member = Member.query.get(member_id)

    if not member:
        return jsonify({'error': 'Member not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required_fields = ['height_cm', 'weight_kg', 'age', 'gender']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400

    report = HealthReport.generate_report(
        member_id=member_id,
        height_cm=data['height_cm'],
        weight_kg=data['weight_kg'],
        age=data['age'],
        gender=data['gender'],
        created_by=data.get('created_by')
    )

    return jsonify({
        'success': True,
        'report': {
            'id': report.id,
            'bmi': report.bmi,
            'bmi_category': report.bmi_category,
            'metabolic_rate': report.metabolic_rate,
            'daily_calories': report.daily_calories,
            'ideal_weight': report.ideal_weight,
            'weight_difference': report.weight_difference,
            'status': report.status,
            'status_arabic': report.status_arabic,
            'status_message': report.status_message
        }
    }), 201


@api_bp.route('/health-report/calculate', methods=['POST'])
@require_api_key
def calculate_health_metrics():
    """Calculate health metrics without saving (for preview)"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    height_cm = data.get('height_cm')
    weight_kg = data.get('weight_kg')
    age = data.get('age')
    gender = data.get('gender', 'male')

    bmi = HealthReport.calculate_bmi(weight_kg, height_cm)
    bmr = HealthReport.calculate_bmr(weight_kg, height_cm, age, gender)
    daily_calories = HealthReport.calculate_daily_calories(bmr)
    ideal_weight = HealthReport.calculate_ideal_weight(height_cm, gender)
    weight_difference = round(weight_kg - ideal_weight, 1) if weight_kg and ideal_weight else None
    status, status_message = HealthReport.get_bmi_status(bmi)

    return jsonify({
        'success': True,
        'calculations': {
            'bmi': bmi,
            'metabolic_rate': bmr,
            'daily_calories': daily_calories,
            'ideal_weight': ideal_weight,
            'weight_difference': weight_difference,
            'status': status,
            'status_message': status_message
        }
    })


# =============================================================================
# PUBLIC COMPLAINTS API (no auth required for public submission)
# =============================================================================

@api_bp.route('/complaints/submit', methods=['POST'])
def submit_public_complaint():
    """Submit a complaint from public form (no authentication required)"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required_fields = ['brand_id', 'subject', 'description']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    # Verify brand exists
    brand = Brand.query.get(data['brand_id'])
    if not brand:
        return jsonify({'error': 'Invalid brand'}), 400

    complaint = Complaint(
        brand_id=data['brand_id'],
        branch_id=data.get('branch_id'),
        category_id=data.get('category_id'),
        customer_name=data.get('customer_name'),
        customer_phone=data.get('customer_phone'),
        customer_email=data.get('customer_email'),
        subject=data['subject'],
        description=data['description'],
        priority=data.get('priority', 'normal'),
        submitted_by='customer'
    )
    db.session.add(complaint)
    db.session.commit()

    return jsonify({
        'success': True,
        'tracking_token': complaint.tracking_token,
        'message': 'تم استلام شكواك بنجاح. يمكنك متابعة حالتها باستخدام رقم التتبع.'
    }), 201


@api_bp.route('/complaints/track/<tracking_token>', methods=['GET'])
def track_complaint(tracking_token):
    """Track a complaint by its tracking token (public)"""
    complaint = Complaint.query.filter_by(tracking_token=tracking_token).first()

    if not complaint:
        return jsonify({'error': 'Complaint not found'}), 404

    return jsonify({
        'success': True,
        'complaint': {
            'subject': complaint.subject,
            'status': complaint.status,
            'status_arabic': complaint.status_arabic,
            'priority': complaint.priority,
            'priority_arabic': complaint.priority_arabic,
            'created_at': complaint.created_at.isoformat(),
            'resolution': complaint.resolution if complaint.status == 'resolved' else None,
            'resolved_at': complaint.resolved_at.isoformat() if complaint.resolved_at else None
        }
    })


@api_bp.route('/complaints/categories', methods=['GET'])
def get_complaint_categories():
    """Get all complaint categories (public)"""
    categories = ComplaintCategory.query.filter_by(is_active=True).all()

    return jsonify({
        'success': True,
        'categories': [
            {
                'id': c.id,
                'name': c.name,
                'name_en': c.name_en,
                'icon': c.icon
            }
            for c in categories
        ]
    })


# =============================================================================
# CLASSES & BOOKINGS API
# =============================================================================

@api_bp.route('/classes', methods=['GET'])
@require_api_key
def get_classes():
    """Get classes for a brand"""
    brand_id = request.args.get('brand_id', type=int)
    day_of_week = request.args.get('day_of_week', type=int)
    service_type_id = request.args.get('service_type_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    query = GymClass.query.filter_by(brand_id=brand_id, is_active=True)

    if day_of_week is not None:
        query = query.filter_by(day_of_week=day_of_week)
    if service_type_id:
        query = query.filter_by(service_type_id=service_type_id)

    classes = query.order_by(GymClass.day_of_week, GymClass.start_time).all()

    return jsonify({
        'success': True,
        'classes': [
            {
                'id': c.id,
                'name': c.name,
                'description': c.description,
                'service_type_id': c.service_type_id,
                'trainer_id': c.trainer_id,
                'trainer_name': c.trainer.name if c.trainer else None,
                'day_of_week': c.day_of_week,
                'day_name': c.day_name_arabic,
                'start_time': c.start_time.strftime('%H:%M') if c.start_time else None,
                'end_time': c.end_time.strftime('%H:%M') if c.end_time else None,
                'time_range': c.time_range,
                'capacity': c.capacity,
                'is_recurring': c.is_recurring
            }
            for c in classes
        ]
    })


@api_bp.route('/classes', methods=['POST'])
@require_api_key
def create_class():
    """Create a new class"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required_fields = ['brand_id', 'service_type_id', 'name', 'start_time', 'end_time']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    # Parse times
    try:
        start_time = datetime.strptime(data['start_time'], '%H:%M').time()
        end_time = datetime.strptime(data['end_time'], '%H:%M').time()
    except ValueError:
        return jsonify({'error': 'Invalid time format. Use HH:MM'}), 400

    gym_class = GymClass(
        brand_id=data['brand_id'],
        branch_id=data.get('branch_id'),
        service_type_id=data['service_type_id'],
        name=data['name'],
        description=data.get('description'),
        trainer_id=data.get('trainer_id'),
        day_of_week=data.get('day_of_week'),
        start_time=start_time,
        end_time=end_time,
        capacity=data.get('capacity', 20),
        is_recurring=data.get('is_recurring', True),
        is_active=data.get('is_active', True)
    )
    db.session.add(gym_class)
    db.session.commit()

    return jsonify({
        'success': True,
        'class_id': gym_class.id,
        'message': 'تم إنشاء الكلاس بنجاح'
    }), 201


@api_bp.route('/classes/<int:class_id>', methods=['GET'])
@require_api_key
def get_class(class_id):
    """Get class details"""
    gym_class = GymClass.query.get(class_id)

    if not gym_class:
        return jsonify({'error': 'Class not found'}), 404

    booking_date = request.args.get('date')
    if booking_date:
        try:
            booking_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
        except ValueError:
            booking_date = date.today()
    else:
        booking_date = date.today()

    return jsonify({
        'success': True,
        'class': {
            'id': gym_class.id,
            'name': gym_class.name,
            'description': gym_class.description,
            'service_type_id': gym_class.service_type_id,
            'trainer_id': gym_class.trainer_id,
            'trainer_name': gym_class.trainer.name if gym_class.trainer else None,
            'day_of_week': gym_class.day_of_week,
            'day_name': gym_class.day_name_arabic,
            'start_time': gym_class.start_time.strftime('%H:%M') if gym_class.start_time else None,
            'end_time': gym_class.end_time.strftime('%H:%M') if gym_class.end_time else None,
            'capacity': gym_class.capacity,
            'available_spots': gym_class.get_available_spots(booking_date),
            'is_full': gym_class.is_full(booking_date)
        }
    })


@api_bp.route('/classes/<int:class_id>', methods=['PUT'])
@require_api_key
def update_class(class_id):
    """Update a class"""
    gym_class = GymClass.query.get(class_id)

    if not gym_class:
        return jsonify({'error': 'Class not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Update fields
    if 'name' in data:
        gym_class.name = data['name']
    if 'description' in data:
        gym_class.description = data['description']
    if 'trainer_id' in data:
        gym_class.trainer_id = data['trainer_id']
    if 'day_of_week' in data:
        gym_class.day_of_week = data['day_of_week']
    if 'start_time' in data:
        gym_class.start_time = datetime.strptime(data['start_time'], '%H:%M').time()
    if 'end_time' in data:
        gym_class.end_time = datetime.strptime(data['end_time'], '%H:%M').time()
    if 'capacity' in data:
        gym_class.capacity = data['capacity']
    if 'is_active' in data:
        gym_class.is_active = data['is_active']

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'تم تحديث الكلاس بنجاح'
    })


@api_bp.route('/classes/<int:class_id>', methods=['DELETE'])
@require_api_key
def delete_class(class_id):
    """Delete a class"""
    gym_class = GymClass.query.get(class_id)

    if not gym_class:
        return jsonify({'error': 'Class not found'}), 404

    # Soft delete by deactivating
    gym_class.is_active = False
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'تم حذف الكلاس بنجاح'
    })


@api_bp.route('/classes/<int:class_id>/bookings', methods=['GET'])
@require_api_key
def get_class_bookings(class_id):
    """Get bookings for a class"""
    gym_class = GymClass.query.get(class_id)

    if not gym_class:
        return jsonify({'error': 'Class not found'}), 404

    booking_date = request.args.get('date')
    if booking_date:
        try:
            booking_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
        except ValueError:
            booking_date = date.today()
    else:
        booking_date = date.today()

    bookings = gym_class.get_bookings_for_date(booking_date)

    return jsonify({
        'success': True,
        'class_id': class_id,
        'date': booking_date.isoformat(),
        'capacity': gym_class.capacity,
        'booked': len([b for b in bookings if b.status in ['booked', 'attended']]),
        'available': gym_class.get_available_spots(booking_date),
        'bookings': [
            {
                'id': b.id,
                'member_id': b.member_id,
                'member_name': b.member.name,
                'status': b.status,
                'status_arabic': b.status_arabic,
                'check_in_time': b.check_in_time.isoformat() if b.check_in_time else None
            }
            for b in bookings
        ]
    })


@api_bp.route('/classes/<int:class_id>/bookings', methods=['POST'])
@require_api_key
def create_class_booking(class_id):
    """Book a member for a class"""
    gym_class = GymClass.query.get(class_id)

    if not gym_class:
        return jsonify({'error': 'Class not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    member_id = data.get('member_id')
    booking_date_str = data.get('booking_date')
    subscription_id = data.get('subscription_id')

    if not member_id:
        return jsonify({'error': 'member_id is required'}), 400

    # Parse date
    if booking_date_str:
        try:
            booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    else:
        booking_date = date.today()

    booking, message = ClassBooking.book_class(class_id, member_id, booking_date, subscription_id)

    if not booking:
        return jsonify({'error': message}), 400

    return jsonify({
        'success': True,
        'booking_id': booking.id,
        'message': message
    }), 201


@api_bp.route('/classes/bookings/<int:booking_id>/checkin', methods=['POST'])
@require_api_key
def checkin_class_booking(booking_id):
    """Check-in a class booking"""
    booking = ClassBooking.query.get(booking_id)

    if not booking:
        return jsonify({'error': 'Booking not found'}), 404

    data = request.get_json() or {}
    checked_in_by = data.get('checked_in_by')

    booking.check_in(checked_in_by)

    return jsonify({
        'success': True,
        'message': 'تم تسجيل الحضور بنجاح'
    })


# =============================================================================
# DAILY CLOSING API
# =============================================================================

@api_bp.route('/daily-closing', methods=['GET'])
@require_api_key
def get_daily_closings():
    """Get daily closings for a brand"""
    brand_id = request.args.get('brand_id', type=int)
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    query = DailyClosing.query.filter_by(brand_id=brand_id)

    if status:
        query = query.filter_by(status=status)
    if start_date:
        query = query.filter(DailyClosing.closing_date >= start_date)
    if end_date:
        query = query.filter(DailyClosing.closing_date <= end_date)

    closings = query.order_by(DailyClosing.closing_date.desc()).limit(30).all()

    return jsonify({
        'success': True,
        'closings': [
            {
                'id': c.id,
                'closing_date': c.closing_date.isoformat(),
                'new_subscriptions_count': c.new_subscriptions_count,
                'renewals_count': c.renewals_count,
                'total_sales': float(c.total_sales or 0),
                'cash_amount': float(c.cash_amount or 0),
                'card_amount': float(c.card_amount or 0),
                'transfer_amount': float(c.transfer_amount or 0),
                'expected_cash': float(c.expected_cash or 0),
                'actual_cash_submitted': float(c.actual_cash_submitted) if c.actual_cash_submitted else None,
                'cash_difference': float(c.cash_difference or 0),
                'status': c.status,
                'status_arabic': c.status_arabic
            }
            for c in closings
        ]
    })


@api_bp.route('/daily-closing', methods=['POST'])
@require_api_key
def create_daily_closing():
    """Create or get daily closing for a date"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    brand_id = data.get('brand_id')
    closing_date_str = data.get('closing_date')
    branch_id = data.get('branch_id')

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    # Parse date
    if closing_date_str:
        try:
            closing_date = datetime.strptime(closing_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    else:
        closing_date = date.today()

    closing = DailyClosing.get_or_create(brand_id, closing_date, branch_id)

    return jsonify({
        'success': True,
        'closing': {
            'id': closing.id,
            'closing_date': closing.closing_date.isoformat(),
            'new_subscriptions_count': closing.new_subscriptions_count,
            'renewals_count': closing.renewals_count,
            'total_sales': float(closing.total_sales or 0),
            'cash_amount': float(closing.cash_amount or 0),
            'card_amount': float(closing.card_amount or 0),
            'transfer_amount': float(closing.transfer_amount or 0),
            'expected_cash': float(closing.expected_cash or 0),
            'status': closing.status
        }
    })


@api_bp.route('/daily-closing/<int:closing_id>/submit', methods=['POST'])
@require_api_key
def submit_daily_closing(closing_id):
    """Submit daily closing with actual cash count"""
    closing = DailyClosing.query.get(closing_id)

    if not closing:
        return jsonify({'error': 'Daily closing not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    actual_cash = data.get('actual_cash')
    if actual_cash is None:
        return jsonify({'error': 'actual_cash is required'}), 400

    closing.submit(
        actual_cash=actual_cash,
        notes=data.get('notes'),
        explanation=data.get('difference_explanation'),
        user_id=data.get('submitted_by')
    )

    return jsonify({
        'success': True,
        'cash_difference': float(closing.cash_difference or 0),
        'message': 'تم تسليم الإقفال اليومي بنجاح'
    })


@api_bp.route('/daily-closing/<int:closing_id>/verify', methods=['POST'])
@require_api_key
def verify_daily_closing(closing_id):
    """Verify or reject daily closing"""
    closing = DailyClosing.query.get(closing_id)

    if not closing:
        return jsonify({'error': 'Daily closing not found'}), 404

    if closing.status != 'submitted':
        return jsonify({'error': 'يجب تسليم الإقفال أولاً قبل التحقق'}), 400

    data = request.get_json() or {}
    approve = data.get('approve', True)
    user_id = data.get('verified_by')

    closing.verify(user_id, approve)

    return jsonify({
        'success': True,
        'status': closing.status,
        'message': 'تم التحقق من الإقفال اليومي' if approve else 'تم رفض الإقفال اليومي'
    })


# =============================================================================
# GIFT CARDS API
# =============================================================================

@api_bp.route('/gift-cards', methods=['GET'])
@require_api_key
def get_gift_cards():
    """Get gift cards for a brand"""
    brand_id = request.args.get('brand_id', type=int)
    status = request.args.get('status')

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    query = GiftCard.query.filter_by(brand_id=brand_id)

    if status:
        query = query.filter_by(status=status)

    cards = query.order_by(GiftCard.created_at.desc()).limit(50).all()

    return jsonify({
        'success': True,
        'gift_cards': [
            {
                'id': c.id,
                'code': c.code,
                'original_amount': float(c.original_amount),
                'remaining_amount': float(c.remaining_amount),
                'status': c.status,
                'status_arabic': c.status_arabic,
                'purchaser_name': c.purchaser_name,
                'recipient_name': c.recipient_name,
                'expires_at': c.expires_at.isoformat() if c.expires_at else None,
                'is_valid': c.is_valid,
                'created_at': c.created_at.isoformat()
            }
            for c in cards
        ],
        'stats': GiftCard.get_stats(brand_id)
    })


@api_bp.route('/gift-cards', methods=['POST'])
@require_api_key
def create_gift_card():
    """Create a new gift card"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required_fields = ['brand_id', 'original_amount']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    # Parse expiry date
    expires_at = None
    if data.get('expires_at'):
        try:
            expires_at = datetime.strptime(data['expires_at'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format for expires_at. Use YYYY-MM-DD'}), 400

    card = GiftCard(
        brand_id=data['brand_id'],
        branch_id=data.get('branch_id'),
        original_amount=data['original_amount'],
        purchaser_name=data.get('purchaser_name'),
        purchaser_phone=data.get('purchaser_phone'),
        recipient_name=data.get('recipient_name'),
        recipient_phone=data.get('recipient_phone'),
        message=data.get('message'),
        expires_at=expires_at,
        created_by=data.get('created_by')
    )
    db.session.add(card)
    db.session.commit()

    return jsonify({
        'success': True,
        'gift_card': {
            'id': card.id,
            'code': card.code,
            'original_amount': float(card.original_amount)
        },
        'message': 'تم إنشاء كرت الإهداء بنجاح'
    }), 201


@api_bp.route('/gift-cards/validate/<code>', methods=['GET'])
@require_api_key
def validate_gift_card(code):
    """Validate a gift card by code"""
    card = GiftCard.get_valid_by_code(code)

    if not card:
        return jsonify({
            'success': False,
            'valid': False,
            'message': 'كرت الإهداء غير صالح أو منتهي الصلاحية'
        })

    return jsonify({
        'success': True,
        'valid': True,
        'gift_card': {
            'id': card.id,
            'code': card.code,
            'remaining_amount': float(card.remaining_amount),
            'expires_at': card.expires_at.isoformat() if card.expires_at else None
        }
    })


@api_bp.route('/gift-cards/<int:card_id>/redeem', methods=['POST'])
@require_api_key
def redeem_gift_card(card_id):
    """Redeem a gift card"""
    card = GiftCard.query.get(card_id)

    if not card:
        return jsonify({'error': 'Gift card not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    amount = data.get('amount')
    member_id = data.get('member_id')
    subscription_id = data.get('subscription_id')

    if not amount:
        return jsonify({'error': 'amount is required'}), 400

    success, message, amount_redeemed = card.redeem(amount, member_id, subscription_id)

    if not success:
        return jsonify({'error': message}), 400

    return jsonify({
        'success': True,
        'amount_redeemed': amount_redeemed,
        'remaining_amount': float(card.remaining_amount),
        'message': message
    })


# =============================================================================
# OFFERS API
# =============================================================================

@api_bp.route('/offers', methods=['GET'])
@require_api_key
def get_offers():
    """Get promotional offers for a brand"""
    brand_id = request.args.get('brand_id', type=int)
    active_only = request.args.get('active_only', 'false').lower() == 'true'

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    if active_only:
        offers = PromotionalOffer.get_active_offers(brand_id)
    else:
        offers = PromotionalOffer.query.filter_by(brand_id=brand_id).order_by(PromotionalOffer.created_at.desc()).all()

    return jsonify({
        'success': True,
        'offers': [
            {
                'id': o.id,
                'name': o.name,
                'description': o.description,
                'code': o.code,
                'discount_type': o.discount_type,
                'discount_value': float(o.discount_value),
                'discount_display': o.discount_display,
                'start_date': o.start_date.isoformat(),
                'end_date': o.end_date.isoformat(),
                'max_uses': o.max_uses,
                'current_uses': o.current_uses,
                'remaining_uses': o.remaining_uses,
                'status': o.status,
                'status_arabic': o.status_arabic,
                'is_valid': o.is_valid,
                'is_active': o.is_active
            }
            for o in offers
        ]
    })


@api_bp.route('/offers', methods=['POST'])
@require_api_key
def create_offer():
    """Create a promotional offer"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required_fields = ['brand_id', 'name', 'discount_type', 'discount_value', 'start_date', 'end_date']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    # Parse dates
    try:
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    offer = PromotionalOffer(
        brand_id=data['brand_id'],
        name=data['name'],
        description=data.get('description'),
        code=data.get('code', '').upper() if data.get('code') else None,
        discount_type=data['discount_type'],
        discount_value=data['discount_value'],
        start_date=start_date,
        end_date=end_date,
        max_uses=data.get('max_uses'),
        min_subscription_amount=data.get('min_subscription_amount'),
        applicable_service_type_id=data.get('applicable_service_type_id'),
        applicable_plan_id=data.get('applicable_plan_id'),
        is_active=data.get('is_active', True),
        created_by=data.get('created_by')
    )
    db.session.add(offer)
    db.session.commit()

    return jsonify({
        'success': True,
        'offer_id': offer.id,
        'message': 'تم إنشاء العرض بنجاح'
    }), 201


@api_bp.route('/offers/<int:offer_id>', methods=['PUT'])
@require_api_key
def update_offer(offer_id):
    """Update a promotional offer"""
    offer = PromotionalOffer.query.get(offer_id)

    if not offer:
        return jsonify({'error': 'Offer not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Update fields
    if 'name' in data:
        offer.name = data['name']
    if 'description' in data:
        offer.description = data['description']
    if 'code' in data:
        offer.code = data['code'].upper() if data['code'] else None
    if 'discount_type' in data:
        offer.discount_type = data['discount_type']
    if 'discount_value' in data:
        offer.discount_value = data['discount_value']
    if 'start_date' in data:
        offer.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    if 'end_date' in data:
        offer.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
    if 'max_uses' in data:
        offer.max_uses = data['max_uses']
    if 'is_active' in data:
        offer.is_active = data['is_active']

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'تم تحديث العرض بنجاح'
    })


@api_bp.route('/offers/<int:offer_id>', methods=['DELETE'])
@require_api_key
def delete_offer(offer_id):
    """Delete/deactivate a promotional offer"""
    offer = PromotionalOffer.query.get(offer_id)

    if not offer:
        return jsonify({'error': 'Offer not found'}), 404

    # Soft delete by deactivating
    offer.is_active = False
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'تم حذف العرض بنجاح'
    })


@api_bp.route('/offers/validate', methods=['POST'])
@require_api_key
def validate_offer():
    """Validate an offer for a subscription"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    brand_id = data.get('brand_id')
    offer_id = data.get('offer_id')
    offer_code = data.get('offer_code')
    subscription_amount = data.get('subscription_amount', 0)
    service_type_id = data.get('service_type_id')
    plan_id = data.get('plan_id')

    # Get offer by ID or code
    offer = None
    if offer_id:
        offer = PromotionalOffer.query.get(offer_id)
    elif offer_code and brand_id:
        offer = PromotionalOffer.get_by_code(offer_code, brand_id)

    if not offer:
        return jsonify({
            'success': False,
            'valid': False,
            'message': 'العرض غير موجود'
        })

    can_apply, message = offer.can_apply(subscription_amount, service_type_id, plan_id)

    if not can_apply:
        return jsonify({
            'success': True,
            'valid': False,
            'message': message
        })

    discount_amount = offer.calculate_discount(subscription_amount)

    return jsonify({
        'success': True,
        'valid': True,
        'offer': {
            'id': offer.id,
            'name': offer.name,
            'discount_display': offer.discount_display
        },
        'discount_amount': float(discount_amount),
        'final_amount': float(subscription_amount) - float(discount_amount)
    })


# =============================================================================
# EMPLOYEE SYNC API
# =============================================================================

@api_bp.route('/sync/employees', methods=['GET'])
@require_api_key
def get_employees_for_sync():
    """Get employees for syncing to desktop software"""
    brand_id = request.args.get('brand_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    # Get users (staff) with fingerprint_id for this brand
    users = User.query.filter(
        User.brand_id == brand_id,
        User.is_active == True,
        User.fingerprint_id != None
    ).all()

    return jsonify({
        'success': True,
        'employees': [
            {
                'id': u.id,
                'fingerprint_id': u.fingerprint_id,
                'name': u.name,
                'email': u.email,
                'phone': u.phone,
                'role': u.role.name_en if u.role else None,
                'department': u.department,
                'is_trainer': u.is_trainer
            }
            for u in users
        ]
    })


@api_bp.route('/sync/employee-attendance', methods=['POST'])
@require_api_key
def sync_employee_attendance():
    """Sync employee attendance from fingerprint device"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    brand_id = data.get('brand_id')
    records = data.get('records', [])

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400

    synced = 0
    errors = []

    for record in records:
        try:
            fingerprint_id = record.get('fingerprint_id')
            timestamp_str = record.get('timestamp')
            log_id = record.get('log_id')

            if not fingerprint_id or not timestamp_str:
                errors.append(f"Missing data in record: {record}")
                continue

            # Parse timestamp
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except:
                errors.append(f"Invalid timestamp: {timestamp_str}")
                continue

            # Find employee by fingerprint_id
            user = User.query.filter_by(
                brand_id=brand_id,
                fingerprint_id=fingerprint_id
            ).first()

            if not user:
                errors.append(f"Employee not found for fingerprint_id: {fingerprint_id}")
                continue

            # Check for duplicate
            existing = EmployeeAttendance.query.filter_by(
                user_id=user.id,
                fingerprint_log_id=log_id
            ).first() if log_id else None

            if existing:
                continue  # Skip duplicate

            # Create attendance record
            attendance = EmployeeAttendance(
                user_id=user.id,
                brand_id=brand_id,
                check_in=timestamp,
                source='fingerprint',
                fingerprint_log_id=log_id
            )
            db.session.add(attendance)
            synced += 1

        except Exception as e:
            errors.append(str(e))

    if synced > 0:
        db.session.commit()

    return jsonify({
        'success': True,
        'synced': synced,
        'errors': errors[:10]
    })
