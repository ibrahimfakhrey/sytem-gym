"""GYM-55 + GYM-58 — manager-facing review queues.

Two queues in one blueprint since they share the same "manager approves
a receptionist's request" pattern:

  /admin/freeze-requests   — GYM-55 freeze approvals
  /admin/pending-edits     — GYM-58 generic edit approvals
"""
from datetime import datetime, timedelta, date
import json

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app import db
from app.models import Subscription, SubscriptionFreeze, Member
from app.models.approvals import (
    SubscriptionFreezeRequest, PendingEdit, EditAuditLog,
)
from app.models.fingerprint import DeviceCommand
from app.utils.helpers import check_entity_access, apply_branch_filter

approvals_bp = Blueprint('approvals', __name__, url_prefix='/admin')


def _require_manager():
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('هذه الصفحة مقتصرة على المدير.', 'danger')
        return False
    return True


# ─── GYM-55 — freeze requests ────────────────────────────────────────────

@approvals_bp.route('/freeze-requests')
@login_required
def freeze_requests():
    if not _require_manager():
        return redirect(url_for('dashboard.index'))
    q = SubscriptionFreezeRequest.query
    # Brand scope: brand-owners only see their brand's requests.
    if not current_user.is_owner and current_user.brand_id:
        q = q.join(Subscription).filter(Subscription.brand_id == current_user.brand_id)
    status = request.args.get('status', 'pending')
    if status in ('pending', 'approved', 'rejected'):
        q = q.filter(SubscriptionFreezeRequest.status == status)
    reqs = q.order_by(SubscriptionFreezeRequest.requested_at.desc()).all()
    pending_count = SubscriptionFreezeRequest.query.filter_by(status='pending').count()
    return render_template('approvals/freeze_requests.html',
                           reqs=reqs, status=status, pending_count=pending_count)


@approvals_bp.route('/freeze-requests/<int:req_id>/approve', methods=['POST'])
@login_required
def freeze_approve(req_id):
    if not _require_manager():
        return redirect(url_for('dashboard.index'))
    r = SubscriptionFreezeRequest.query.get_or_404(req_id)
    if r.status != 'pending':
        flash('الطلب تمّت معالجته مسبقاً.', 'warning')
        return redirect(url_for('approvals.freeze_requests'))
    sub = r.subscription
    if not sub:
        flash('الاشتراك المرتبط بالطلب غير موجود.', 'danger')
        return redirect(url_for('approvals.freeze_requests'))
    if not check_entity_access(sub):
        flash('ليس لديك صلاحية على هذا الاشتراك.', 'danger')
        return redirect(url_for('approvals.freeze_requests'))

    # Apply the freeze — mirror the manager-path branch in subscriptions.freeze.
    freeze_end = r.freeze_start + timedelta(days=r.freeze_days)
    db.session.add(SubscriptionFreeze(
        subscription_id=sub.id,
        freeze_start=r.freeze_start,
        freeze_end=freeze_end,
        freeze_days=r.freeze_days,
        reason=r.reason,
        created_by=r.requested_by,  # credit the original requester
    ))
    sub.end_date = sub.end_date + timedelta(days=r.freeze_days)
    sub.status = 'frozen'

    # Block on fingerprint device if applicable.
    m = sub.member
    if m and m.fingerprint_id and m.branch and m.branch.uses_fingerprint:
        db.session.add(DeviceCommand(
            brand_id=sub.brand_id,
            command_type='block_member',
            target_emp_id=m.fingerprint_id,
            member_id=m.id,
            command_data=json.dumps({'end_date': '2020-01-01'}),
            status='pending',
        ))

    r.status = 'approved'
    r.reviewed_by = current_user.id
    r.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f'تمّت الموافقة وتنفيذ التجميد على الاشتراك #{sub.id}.', 'success')
    return redirect(url_for('approvals.freeze_requests'))


@approvals_bp.route('/freeze-requests/<int:req_id>/reject', methods=['POST'])
@login_required
def freeze_reject(req_id):
    if not _require_manager():
        return redirect(url_for('dashboard.index'))
    r = SubscriptionFreezeRequest.query.get_or_404(req_id)
    if r.status != 'pending':
        flash('الطلب تمّت معالجته مسبقاً.', 'warning')
        return redirect(url_for('approvals.freeze_requests'))
    r.status = 'rejected'
    r.rejection_reason = (request.form.get('rejection_reason') or '').strip() or None
    r.reviewed_by = current_user.id
    r.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash('تم رفض الطلب.', 'info')
    return redirect(url_for('approvals.freeze_requests'))


# ─── GYM-58 — generic pending edits ──────────────────────────────────────

def create_pending_edit(*, entity_type, entity_id, action, payload_dict,
                       summary, brand_id):
    """Helper used by edit routes when the actor isn't a manager.

    Stores the intended change as JSON so we can re-apply on approval.
    """
    db.session.add(PendingEdit(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        payload_json=json.dumps(payload_dict, ensure_ascii=False, default=str),
        summary=(summary or '')[:280],
        brand_id=brand_id,
        requested_by=current_user.id,
        status='pending',
    ))
    db.session.commit()


@approvals_bp.route('/pending-edits')
@login_required
def pending_edits():
    if not _require_manager():
        return redirect(url_for('dashboard.index'))
    q = PendingEdit.query
    if not current_user.is_owner and current_user.brand_id:
        q = q.filter(PendingEdit.brand_id == current_user.brand_id)
    status = request.args.get('status', 'pending')
    if status in ('pending', 'approved', 'rejected'):
        q = q.filter(PendingEdit.status == status)
    edits = q.order_by(PendingEdit.requested_at.desc()).all()
    # Decode the JSON payloads for readable display.
    for e in edits:
        try:
            e._payload = json.loads(e.payload_json or '{}')
        except Exception:
            e._payload = {}
    return render_template('approvals/pending_edits.html', edits=edits, status=status)


def _apply_pending_edit(pe):
    """Actually apply a PendingEdit to its target entity. Runs inside an
    open db session; caller commits."""
    payload = json.loads(pe.payload_json or '{}')

    if pe.entity_type == 'subscription' and pe.action == 'update':
        sub = Subscription.query.get(pe.entity_id)
        if not sub:
            return False, 'الاشتراك المرتبط غير موجود'
        for field, val in payload.items():
            if field == 'notes':
                sub.notes = val
            elif field == 'end_date' and val:
                try:
                    sub.end_date = date.fromisoformat(val)
                except ValueError:
                    pass
            elif field == 'start_date' and val:
                try:
                    sub.start_date = date.fromisoformat(val)
                except ValueError:
                    pass
        _audit(pe, sub.brand_id)
        return True, None

    if pe.entity_type == 'subscription' and pe.action == 'delete':
        sub = Subscription.query.get(pe.entity_id)
        if not sub:
            return False, 'الاشتراك غير موجود'
        sub.is_deleted = True
        from app.models import Income, SubscriptionPayment
        Income.query.filter_by(subscription_id=sub.id).update({'is_deleted': True}, synchronize_session=False)
        SubscriptionPayment.query.filter_by(subscription_id=sub.id).update({'is_deleted': True}, synchronize_session=False)
        _audit(pe, sub.brand_id)
        return True, None

    if pe.entity_type == 'payment' and pe.action == 'update':
        from app.models import SubscriptionPayment
        p = SubscriptionPayment.query.get(pe.entity_id)
        if not p:
            return False, 'الدفعة غير موجودة'
        for field, val in payload.items():
            if field == 'amount':
                try: p.amount = float(val)
                except (TypeError, ValueError): pass
            elif field == 'payment_method':
                p.payment_method = val
            elif field == 'notes':
                p.notes = val
        _audit(pe, p.brand_id)
        return True, None

    if pe.entity_type == 'payment' and pe.action == 'delete':
        from app.models import SubscriptionPayment, Income
        p = SubscriptionPayment.query.get(pe.entity_id)
        if not p:
            return False, 'الدفعة غير موجودة'
        p.is_deleted = True
        Income.query.filter_by(payment_id=p.id).update({'is_deleted': True}, synchronize_session=False)
        _audit(pe, p.brand_id)
        return True, None

    if pe.entity_type == 'expense' and pe.action == 'update':
        from app.models import Expense
        e = Expense.query.get(pe.entity_id)
        if not e:
            return False, 'المصروف غير موجود'
        for field, val in payload.items():
            if field == 'amount':
                try: e.amount = float(val)
                except (TypeError, ValueError): pass
            elif field == 'category_name':
                e.category_name = val
            elif field == 'description':
                e.description = val
        _audit(pe, e.brand_id)
        return True, None

    if pe.entity_type == 'expense' and pe.action == 'delete':
        from app.models import Expense
        e = Expense.query.get(pe.entity_id)
        if not e:
            return False, 'المصروف غير موجود'
        e.is_deleted = True
        _audit(pe, e.brand_id)
        return True, None

    return False, f'نوع تعديل غير مدعوم: {pe.entity_type}/{pe.action}'


def _audit(pe, brand_id):
    """Write EditAuditLog entries for each field in a PendingEdit's payload
    after it's applied (so the audit trail shows what actually changed)."""
    payload = json.loads(pe.payload_json or '{}')
    for field, new_value in payload.items():
        db.session.add(EditAuditLog(
            entity_type=pe.entity_type,
            entity_id=pe.entity_id,
            field_name=field,
            old_value=None,  # not captured; the pending queue records intent, not before/after
            new_value=str(new_value) if new_value is not None else None,
            brand_id=brand_id,
            changed_by=current_user.id,
            note=f'GYM-58 approval of PendingEdit #{pe.id}',
        ))


@approvals_bp.route('/pending-edits/<int:pe_id>/approve', methods=['POST'])
@login_required
def edit_approve(pe_id):
    if not _require_manager():
        return redirect(url_for('dashboard.index'))
    pe = PendingEdit.query.get_or_404(pe_id)
    if pe.status != 'pending':
        flash('الطلب تمّت معالجته مسبقاً.', 'warning')
        return redirect(url_for('approvals.pending_edits'))
    ok, err = _apply_pending_edit(pe)
    if not ok:
        flash(f'فشل تنفيذ التعديل: {err}', 'danger')
        return redirect(url_for('approvals.pending_edits'))
    pe.status = 'approved'
    pe.reviewed_by = current_user.id
    pe.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash('تم اعتماد التعديل وتطبيقه.', 'success')
    return redirect(url_for('approvals.pending_edits'))


@approvals_bp.route('/pending-edits/<int:pe_id>/reject', methods=['POST'])
@login_required
def edit_reject(pe_id):
    if not _require_manager():
        return redirect(url_for('dashboard.index'))
    pe = PendingEdit.query.get_or_404(pe_id)
    if pe.status != 'pending':
        flash('الطلب تمّت معالجته مسبقاً.', 'warning')
        return redirect(url_for('approvals.pending_edits'))
    pe.status = 'rejected'
    pe.rejection_reason = (request.form.get('rejection_reason') or '').strip() or None
    pe.reviewed_by = current_user.id
    pe.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash('تم رفض التعديل.', 'info')
    return redirect(url_for('approvals.pending_edits'))
