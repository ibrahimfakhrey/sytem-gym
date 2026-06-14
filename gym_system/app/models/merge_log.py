"""GYM-28: audit + reversal log for member-duplicate merges.

Every "smart merge" records:

* The keeper id (which Member row remained the canonical one)
* The loser id (the Member row that was deactivated)
* A JSON snapshot of the loser's full pre-merge field values
* A JSON dict of how many rows of each child table were re-pointed from
  loser → keeper (subscriptions, invoices, attendance, …)
* Who clicked the merge button and when

Undo is then a deterministic operation: flip the loser row back to
is_active=True, restore its `name` from the snapshot, and unpoint every
re-pointed FK back to the loser using the counts as a sanity check. The
loser's own data was never deleted, so the undo never needs to "create"
anything.
"""
from datetime import datetime
from app import db


class MemberMergeLog(db.Model):
    __tablename__ = 'member_merge_logs'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    keeper_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    loser_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)

    # JSON snapshot of the loser row at merge time (for undo + audit).
    loser_snapshot_json = db.Column(db.Text)
    # JSON map: {"subscriptions": 3, "invoices": 5, "attendance": 12, ...}
    moves_json = db.Column(db.Text)

    # Audit
    performed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    performed_at = db.Column(db.DateTime, default=datetime.utcnow)
    undone_at = db.Column(db.DateTime)
    undone_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    keeper = db.relationship('Member', foreign_keys=[keeper_id])
    loser = db.relationship('Member', foreign_keys=[loser_id])
    performer = db.relationship('User', foreign_keys=[performed_by])
    undoer = db.relationship('User', foreign_keys=[undone_by])

    @property
    def is_active(self):
        return self.undone_at is None

    def __repr__(self):
        return f'<MemberMergeLog keeper={self.keeper_id} loser={self.loser_id}>'
