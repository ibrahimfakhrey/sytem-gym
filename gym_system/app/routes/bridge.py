from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import IntegerField, BooleanField
from wtforms.validators import DataRequired, NumberRange, Optional
from datetime import datetime, timedelta

from app import db
from app.models.fingerprint import BridgeStatus, FingerprintSyncLog, BridgeSettings
from app.models.company import Brand

bridge_bp = Blueprint('bridge', __name__)


# ============== FORMS ==============

class BridgeSettingsForm(FlaskForm):
    """Form for bridge settings"""
    class_access_window_minutes = IntegerField('نافذة دخول الكلاس (بالدقائق)',
                                                validators=[DataRequired(), NumberRange(min=1, max=120)],
                                                default=15)
    attendance_sync_interval = IntegerField('فاصل مزامنة الحضور (بالثواني)',
                                            validators=[DataRequired(), NumberRange(min=10, max=300)],
                                            default=30)
    access_control_interval = IntegerField('فاصل تحديث صلاحيات الدخول (بالثواني)',
                                           validators=[DataRequired(), NumberRange(min=10, max=300)],
                                           default=60)
    class_access_control_enabled = BooleanField('تفعيل التحكم بدخول الكلاسات')
    employee_shift_tracking_enabled = BooleanField('تفعيل تتبع مناوبات الموظفين')
    auto_block_expired = BooleanField('حظر تلقائي عند انتهاء الاشتراك')


@bridge_bp.route('/')
@login_required
def index():
    """Bridge status dashboard - admin and owner only"""
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

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


@bridge_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Bridge settings page - configure access windows and sync intervals"""
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brands — admin sees all, owner sees their own
    if current_user.is_owner:
        brands = Brand.query.filter_by(is_active=True).all()
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id and brands:
            brand_id = brands[0].id
    else:
        brand_id = current_user.brand_id
        brands = [current_user.brand] if current_user.brand else []

    brand = Brand.query.get(brand_id) if brand_id else None
    if not brand:
        flash('لم يتم العثور على البراند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Get or create settings
    bridge_settings = BridgeSettings.get_or_create(brand_id)

    form = BridgeSettingsForm(obj=bridge_settings)

    if form.validate_on_submit():
        form.populate_obj(bridge_settings)
        db.session.commit()
        flash('تم حفظ إعدادات الجسر بنجاح', 'success')
        return redirect(url_for('bridge.settings', brand_id=brand_id))

    # Get bridge status for this brand
    bridge_status = BridgeStatus.query.filter_by(brand_id=brand_id).order_by(
        BridgeStatus.last_heartbeat.desc()
    ).first()

    return render_template('bridge/settings.html',
                           form=form,
                           brand=brand,
                           brands=brands,
                           bridge_settings=bridge_settings,
                           bridge_status=bridge_status)
