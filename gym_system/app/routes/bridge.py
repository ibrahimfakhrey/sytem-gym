from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import IntegerField, BooleanField
from wtforms.validators import DataRequired, NumberRange, Optional
from datetime import datetime, timedelta

from app import db
from app.models.fingerprint import BridgeStatus, FingerprintSyncLog, BridgeSettings
from app.models.company import Brand, Branch

bridge_bp = Blueprint('bridge', __name__)


def _accessible_brands():
    """Brands the current user can manage bridge settings for."""
    if current_user.is_owner:
        return Brand.query.filter_by(is_active=True).order_by(Brand.name).all()
    if current_user.brand:
        return [current_user.brand]
    return []


def _branches_for_brand(brand_id):
    """Branches in this brand the user can see. Branch-scoped users only see their own branch."""
    q = Branch.query.filter_by(brand_id=brand_id, is_active=True)
    if not (current_user.is_owner or current_user.is_brand_manager) and current_user.branch_id:
        q = q.filter(Branch.id == current_user.branch_id)
    return q.order_by(Branch.name).all()


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

    brands = _accessible_brands()
    brand_id = request.args.get('brand_id', type=int)
    if not brand_id and brands:
        brand_id = brands[0].id

    branches = _branches_for_brand(brand_id) if brand_id else []
    branch_id = request.args.get('branch_id', type=int)
    if branch_id and not any(b.id == branch_id for b in branches):
        branch_id = None  # asked-for branch not visible to this user

    bridges = []
    sync_logs = []
    if brand_id:
        bridge_q = BridgeStatus.query.filter_by(brand_id=brand_id)
        log_q = FingerprintSyncLog.query.filter_by(brand_id=brand_id)
        if branch_id:
            bridge_q = bridge_q.filter_by(branch_id=branch_id)
            log_q = log_q.filter_by(branch_id=branch_id)

        bridges = bridge_q.order_by(BridgeStatus.last_heartbeat.desc()).all()
        sync_logs = log_q.order_by(FingerprintSyncLog.synced_at.desc()).limit(20).all()

    return render_template(
        'bridge/index.html',
        bridges=bridges,
        sync_logs=sync_logs,
        brands=brands,
        branches=branches,
        selected_brand_id=brand_id,
        selected_branch_id=branch_id,
    )


@bridge_bp.route('/api/refresh')
@login_required
def refresh_status():
    """AJAX endpoint to refresh bridge status"""
    brand_id = request.args.get('brand_id', type=int)
    branch_id = request.args.get('branch_id', type=int)

    if not brand_id:
        return jsonify({'error': 'brand_id required'}), 400

    q = BridgeStatus.query.filter_by(brand_id=brand_id)
    if branch_id:
        q = q.filter_by(branch_id=branch_id)
    bridges = q.all()

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
    """Bridge settings page — per-branch configuration of access window, sync intervals, feature flags."""
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    brands = _accessible_brands()
    brand_id = request.args.get('brand_id', type=int)
    if not brand_id and brands:
        brand_id = brands[0].id

    brand = Brand.query.get(brand_id) if brand_id else None
    if not brand:
        flash('لم يتم العثور على البراند', 'warning')
        return redirect(url_for('dashboard.index'))

    branches = _branches_for_brand(brand_id)
    if not branches:
        flash('لا يوجد فروع لهذا البراند. أنشئ فرعاً أولاً من إدارة الفروع.', 'warning')
        return redirect(url_for('admin.branches_list', brand_id=brand_id))

    branch_id = request.args.get('branch_id', type=int)
    # Default: user's own branch if scoped, otherwise first branch
    if not branch_id or not any(b.id == branch_id for b in branches):
        branch_id = current_user.branch_id if current_user.branch_id and any(
            b.id == current_user.branch_id for b in branches
        ) else branches[0].id
    branch = next((b for b in branches if b.id == branch_id), branches[0])

    # Per-branch settings
    bridge_settings = BridgeSettings.get_or_create(brand_id, branch_id)
    form = BridgeSettingsForm(obj=bridge_settings)

    if form.validate_on_submit():
        form.populate_obj(bridge_settings)
        db.session.commit()
        flash(f'تم حفظ إعدادات جسر فرع {branch.name} بنجاح', 'success')
        return redirect(url_for('bridge.settings', brand_id=brand_id, branch_id=branch_id))

    # Latest bridge status for this specific branch
    bridge_status = BridgeStatus.query.filter_by(
        brand_id=brand_id, branch_id=branch_id
    ).order_by(BridgeStatus.last_heartbeat.desc()).first()

    return render_template('bridge/settings.html',
                           form=form,
                           brand=brand,
                           brands=brands,
                           branch=branch,
                           branches=branches,
                           bridge_settings=bridge_settings,
                           bridge_status=bridge_status)
