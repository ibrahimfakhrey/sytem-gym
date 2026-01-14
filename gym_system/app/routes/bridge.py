from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from app import db
from app.models.fingerprint import BridgeStatus, FingerprintSyncLog
from app.models.company import Brand

bridge_bp = Blueprint('bridge', __name__)


@bridge_bp.route('/')
@login_required
def index():
    """Bridge status dashboard"""
    # Get brand_id based on user role
    if current_user.role.is_owner:
        brands = Brand.query.filter_by(uses_fingerprint=True).all()
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id and brands:
            brand_id = brands[0].id
    else:
        brand_id = current_user.brand_id
        brands = [current_user.brand] if current_user.brand else []

    # Get bridge statuses
    bridges = []
    sync_logs = []
    if brand_id:
        bridges = BridgeStatus.query.filter_by(brand_id=brand_id).order_by(
            BridgeStatus.last_heartbeat.desc()
        ).all()

        sync_logs = FingerprintSyncLog.query.filter_by(brand_id=brand_id).order_by(
            FingerprintSyncLog.synced_at.desc()
        ).limit(20).all()

    return render_template(
        'bridge/index.html',
        bridges=bridges,
        sync_logs=sync_logs,
        brands=brands,
        selected_brand_id=brand_id
    )


@bridge_bp.route('/api/refresh')
@login_required
def refresh_status():
    """AJAX endpoint to refresh bridge status"""
    brand_id = request.args.get('brand_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id required'}), 400

    bridges = BridgeStatus.query.filter_by(brand_id=brand_id).all()

    return jsonify({
        'bridges': [
            {
                'id': b.id,
                'computer_name': b.computer_name,
                'ip_address': b.ip_address,
                'database_path': b.database_path,
                'database_found': b.database_found,
                'status': b.status_text,
                'status_class': b.status_class,
                'last_heartbeat': b.last_heartbeat.strftime('%Y-%m-%d %H:%M:%S') if b.last_heartbeat else '-',
                'total_syncs': b.total_syncs or 0,
                'last_error': b.last_error
            }
            for b in bridges
        ]
    })
