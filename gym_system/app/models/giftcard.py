from datetime import datetime, date
from app import db
import secrets
import string


class GiftCard(db.Model):
    """Gift cards (كروت الإهداء)"""
    __tablename__ = 'gift_cards'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)

    # Card info
    code = db.Column(db.String(20), unique=True, nullable=False)
    original_amount = db.Column(db.Numeric(10, 2), nullable=False)
    remaining_amount = db.Column(db.Numeric(10, 2), nullable=False)

    # Linked subscription when redeemed
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=True)

    # Purchaser info
    purchaser_name = db.Column(db.String(100))
    purchaser_phone = db.Column(db.String(20))

    # Recipient info
    recipient_name = db.Column(db.String(100))
    recipient_phone = db.Column(db.String(20))
    message = db.Column(db.Text)  # Gift message

    # Status: active, partially_used, redeemed, expired, cancelled
    status = db.Column(db.String(20), default='active')

    # Dates
    expires_at = db.Column(db.Date)
    redeemed_at = db.Column(db.DateTime)
    redeemed_by_member_id = db.Column(db.Integer, db.ForeignKey('members.id'))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    redeemer = db.relationship('Member', backref='redeemed_gift_cards')

    def __repr__(self):
        return f'<GiftCard {self.code}>'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.code:
            self.code = self.generate_code()
        if self.remaining_amount is None and self.original_amount:
            self.remaining_amount = self.original_amount

    @staticmethod
    def generate_code():
        """Generate a unique gift card code"""
        chars = string.ascii_uppercase + string.digits
        while True:
            code = 'GC-' + ''.join(secrets.choice(chars) for _ in range(8))
            existing = GiftCard.query.filter_by(code=code).first()
            if not existing:
                return code

    @property
    def is_valid(self):
        """Check if gift card is valid for use"""
        if self.status not in ['active', 'partially_used']:
            return False
        if self.expires_at and self.expires_at < date.today():
            return False
        if float(self.remaining_amount) <= 0:
            return False
        return True

    @property
    def status_arabic(self):
        """Get status in Arabic"""
        status_map = {
            'active': 'نشط',
            'partially_used': 'مستخدم جزئياً',
            'redeemed': 'مستخدم',
            'expired': 'منتهي الصلاحية',
            'cancelled': 'ملغي'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """Get CSS class for status"""
        status_classes = {
            'active': 'success',
            'partially_used': 'info',
            'redeemed': 'secondary',
            'expired': 'warning',
            'cancelled': 'danger'
        }
        return status_classes.get(self.status, 'secondary')

    @property
    def used_amount(self):
        """Get amount used from the gift card"""
        return float(self.original_amount) - float(self.remaining_amount)

    def redeem(self, amount, member_id, subscription_id=None):
        """
        Redeem gift card for a specific amount
        Returns (success, message, amount_redeemed)
        """
        if not self.is_valid:
            return False, 'كرت الإهداء غير صالح للاستخدام', 0

        amount = float(amount)
        remaining = float(self.remaining_amount)

        if amount > remaining:
            amount = remaining  # Use only what's available

        self.remaining_amount = remaining - amount
        self.redeemed_by_member_id = member_id
        self.subscription_id = subscription_id

        if self.remaining_amount <= 0:
            self.status = 'redeemed'
            self.redeemed_at = datetime.utcnow()
        else:
            self.status = 'partially_used'

        db.session.commit()
        return True, f'تم استخدام {amount} ر.س من كرت الإهداء', amount

    def cancel(self):
        """Cancel the gift card"""
        self.status = 'cancelled'
        db.session.commit()

    def check_expiry(self):
        """Check and update expiry status"""
        if self.expires_at and self.expires_at < date.today() and self.status in ['active', 'partially_used']:
            self.status = 'expired'
            db.session.commit()

    @classmethod
    def get_valid_by_code(cls, code):
        """Get a valid gift card by code"""
        card = cls.query.filter_by(code=code.upper()).first()
        if card and card.is_valid:
            return card
        return None

    @classmethod
    def get_total_profit(cls, brand_id=None, start_date=None, end_date=None):
        """
        Calculate total profit from gift cards
        Profit = original_amount - remaining_amount (for redeemed cards)
        """
        from sqlalchemy import func
        query = db.session.query(
            func.sum(cls.original_amount - cls.remaining_amount)
        ).filter(cls.status.in_(['redeemed', 'partially_used']))

        if brand_id:
            query = query.filter(cls.brand_id == brand_id)
        if start_date:
            query = query.filter(cls.created_at >= start_date)
        if end_date:
            query = query.filter(cls.created_at <= end_date)

        result = query.scalar()
        return float(result) if result else 0

    @classmethod
    def get_stats(cls, brand_id=None):
        """Get gift card statistics"""
        from sqlalchemy import func

        query = cls.query
        if brand_id:
            query = query.filter_by(brand_id=brand_id)

        total = query.count()
        active = query.filter(cls.status.in_(['active', 'partially_used'])).count()
        redeemed = query.filter_by(status='redeemed').count()

        total_value = db.session.query(func.sum(cls.original_amount))
        if brand_id:
            total_value = total_value.filter(cls.brand_id == brand_id)
        total_value = total_value.scalar() or 0

        return {
            'total': total,
            'active': active,
            'redeemed': redeemed,
            'total_value': float(total_value),
            'profit': cls.get_total_profit(brand_id)
        }
