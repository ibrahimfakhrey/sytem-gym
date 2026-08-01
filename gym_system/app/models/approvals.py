"""GYM-55 + GYM-58 + GYM-61 — approval + audit tables.

* ``SubscriptionFreezeRequest`` — receptionists submit a freeze intent;
  managers approve or reject. Only on approval does an actual
  ``SubscriptionFreeze`` row + status change apply.
* ``PendingEdit`` — generic queue for any "receptionist wanted to edit
  existing data" attempt. Stored as a JSON payload of the intended change
  so the approver can eyeball it before applying.
* ``EditAuditLog`` — audit trail for GYM-61 direct manager edits to
  invoice / subscription registration dates. Also used by the approval
  flow above when a change is applied so we always have a trail.
"""
from datetime import datetime
from app import db


class SubscriptionFreezeRequest(db.Model):
    """Freeze request awaiting manager approval (GYM-55)."""
    __tablename__ = 'subscription_freeze_requests'

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer,
                                db.ForeignKey('subscriptions.id'), nullable=False)
    freeze_start = db.Column(db.Date, nullable=False)
    freeze_days = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text)

    # Workflow
    status = db.Column(db.String(20), default='pending', nullable=False)
    #   pending → awaiting review
    #   approved → applied (a SubscriptionFreeze row was written)
    #   rejected → not applied; rejection_reason may explain why
    rejection_reason = db.Column(db.Text)

    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)

    # Relationships
    subscription = db.relationship('Subscription', foreign_keys=[subscription_id])
    requester = db.relationship('User', foreign_keys=[requested_by])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

    @property
    def is_pending(self):
        return self.status == 'pending'

    @property
    def freeze_end(self):
        from datetime import timedelta
        return self.freeze_start + timedelta(days=self.freeze_days)


class PendingEdit(db.Model):
    """Generic queue: receptionist wanted to edit existing data; manager
    approves or rejects (GYM-58).

    The intended change is stored as JSON in ``payload_json`` so we can
    handle any entity type without a table per edit-target. The route that
    would have applied the change instead creates a row here; on approval,
    the same route is re-invoked with the payload.
    """
    __tablename__ = 'pending_edits'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(40), nullable=False)  # e.g. 'subscription', 'payment', 'expense'
    entity_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20), nullable=False)  # 'update' | 'delete'
    payload_json = db.Column(db.Text)                  # form fields, JSON
    summary = db.Column(db.String(280))                # human-readable one-liner

    status = db.Column(db.String(20), default='pending', nullable=False)
    rejection_reason = db.Column(db.Text)

    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'))
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)

    requester = db.relationship('User', foreign_keys=[requested_by])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    brand = db.relationship('Brand', foreign_keys=[brand_id])

    @property
    def is_pending(self):
        return self.status == 'pending'


class EditAuditLog(db.Model):
    """Audit trail for sensitive direct edits (GYM-61 + also written by
    the approval flow when a PendingEdit is applied).

    We keep it granular: one row per (entity, field) so a multi-field
    edit produces multiple rows.
    """
    __tablename__ = 'edit_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    field_name = db.Column(db.String(40), nullable=False)
    old_value = db.Column(db.String(200))
    new_value = db.Column(db.String(200))

    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'))
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    note = db.Column(db.String(200))  # optional context, e.g. "via /admin/pending-edits"

    changer = db.relationship('User', foreign_keys=[changed_by])
