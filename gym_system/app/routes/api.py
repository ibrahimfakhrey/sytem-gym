from flask import Blueprint, request, jsonify, current_app
from functools import wraps
from datetime import datetime, date, timedelta
import json

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.user import User, Role
from app.models.subscription import Subscription
from app.models.attendance import MemberAttendance, EmployeeAttendance
from app.models.fingerprint import FingerprintSyncLog, BridgeStatus, DeviceCommand

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

            # Find member by fingerprint_id
            member = Member.query.filter_by(
                brand_id=brand_id,
                fingerprint_id=fingerprint_id
            ).first()

            if not member:
                errors.append(f"Member not found for fingerprint_id: {fingerprint_id}")
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

            if not subscription:
                has_warning = True
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
        error_message='\n'.join(errors[:10]) if errors else None  # Limit error messages
    )
    db.session.add(sync_log)
    db.session.commit()

    return jsonify({
        'success': True,
        'synced': synced,
        'errors': errors[:10]  # Limit errors in response
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
