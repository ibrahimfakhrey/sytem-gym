from flask import Blueprint, request, jsonify, current_app
from functools import wraps
from datetime import datetime, date

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.subscription import Subscription
from app.models.attendance import MemberAttendance
from app.models.fingerprint import FingerprintSyncLog, BridgeStatus

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
