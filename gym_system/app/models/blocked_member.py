from datetime import datetime
from app import db


class BlockedMember(db.Model):
    """Blocked/Banned members - permanently suspended from the gym"""
    __tablename__ = 'blocked_members'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    
    # Member data (copied from member before deletion)
    original_member_id = db.Column(db.Integer)  # Reference to original member ID
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    national_id = db.Column(db.String(20))
    email = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    photo = db.Column(db.String(255))
    
    # Block info
    reason = db.Column(db.Text, nullable=False)  # Why they were blocked
    blocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    blocked_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Unblock info (if ever unblocked)
    is_active = db.Column(db.Boolean, default=True)  # True = still blocked
    unblocked_at = db.Column(db.DateTime)
    unblocked_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    unblock_reason = db.Column(db.Text)
    
    # Relationships
    brand = db.relationship('Brand', backref='blocked_members')
    blocker = db.relationship('User', foreign_keys=[blocked_by], backref='blocked_members')
    unblocker = db.relationship('User', foreign_keys=[unblocked_by])

    def __repr__(self):
        return f'<BlockedMember {self.name} ({self.phone})>'

    @classmethod
    def is_blocked(cls, brand_id, phone=None, national_id=None):
        """Check if a phone or national_id is blocked in this brand.

        GYM-66 — phones can now be shared across family members. If a
        ``national_id`` is provided we treat it as the STRONG identifier
        and match on it exclusively; phone matches are ignored so a
        legitimate new family member sharing a phone with a previously
        blocked person isn't falsely blocked. Only when the caller has no
        national_id (member without one) do we fall back to phone-only.
        """
        if not phone and not national_id:
            return None

        query = cls.query.filter_by(brand_id=brand_id, is_active=True)

        if national_id:
            # Strong identifier — match on national_id only. A blocked
            # person who tries to re-register under a new phone is still
            # blocked; an unrelated new member sharing the same phone but
            # with a different national_id is not.
            return query.filter(cls.national_id == national_id).first()

        # No national_id on the incoming member → fall back to phone.
        return query.filter(cls.phone == phone).first()

    @classmethod
    def block_member(cls, member, reason, blocked_by_user_id):
        """Create a blocked member record from an existing member"""
        blocked = cls(
            brand_id=member.brand_id,
            original_member_id=member.id,
            name=member.name,
            phone=member.phone,
            national_id=member.national_id,
            email=member.email,
            gender=member.gender,
            photo=member.photo,
            reason=reason,
            blocked_by=blocked_by_user_id
        )
        return blocked
