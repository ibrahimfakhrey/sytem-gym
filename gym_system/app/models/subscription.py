from datetime import datetime, date, timedelta
from app import db


class Plan(db.Model):
    """Plan model - Subscription plans"""
    __tablename__ = 'plans'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_types.id'), nullable=True)

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    duration_days = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

    # Freeze settings
    max_freezes = db.Column(db.Integer, default=1)
    max_freeze_days = db.Column(db.Integer, default=14)
    freeze_is_paid = db.Column(db.Boolean, default=False)  # Is freeze a paid feature?
    freeze_daily_rate = db.Column(db.Numeric(10, 2), default=0)  # Daily rate for paid freeze

    # Class booking settings
    requires_class_booking = db.Column(db.Boolean, default=False)  # Must book class to attend

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    subscriptions = db.relationship('Subscription', backref='plan', lazy='dynamic')

    def __repr__(self):
        return f'<Plan {self.name}>'

    @property
    def duration_text(self):
        """Human readable duration"""
        if self.duration_days == 30:
            return 'شهر'
        elif self.duration_days == 90:
            return '3 شهور'
        elif self.duration_days == 180:
            return '6 شهور'
        elif self.duration_days == 365:
            return 'سنة'
        return f'{self.duration_days} يوم'


class Subscription(db.Model):
    """Subscription model - Member subscriptions"""
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_types.id'), nullable=True)

    # Dates
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    original_end_date = db.Column(db.Date, nullable=False)

    # Amounts
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    paid_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    remaining_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(10, 2), default=0)

    # Promotional offer
    offer_id = db.Column(db.Integer, db.ForeignKey('promotional_offers.id'), nullable=True)
    offer_discount = db.Column(db.Numeric(10, 2), default=0)

    # Gift card
    gift_card_id = db.Column(db.Integer, db.ForeignKey('gift_cards.id'), nullable=True)
    gift_card_amount = db.Column(db.Numeric(10, 2), default=0)

    # Status: active, frozen, expired, cancelled, stopped
    status = db.Column(db.String(20), default='active')

    # Stop subscription tracking
    stop_reason = db.Column(db.Text)
    stopped_at = db.Column(db.DateTime)
    stopped_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    service_type = db.relationship('ServiceType', backref='subscriptions', foreign_keys=[service_type_id])
    offer = db.relationship('PromotionalOffer', backref='subscriptions', foreign_keys=[offer_id])
    gift_card = db.relationship('GiftCard', backref='used_for_subscriptions', foreign_keys=[gift_card_id])
    stopper = db.relationship('User', foreign_keys=[stopped_by], backref='stopped_subscriptions')

    # Relationships
    freezes = db.relationship('SubscriptionFreeze', backref='subscription', lazy='dynamic')
    payments = db.relationship('SubscriptionPayment', backref='subscription', lazy='dynamic')
    attendance = db.relationship('MemberAttendance', backref='subscription', lazy='dynamic')

    def __repr__(self):
        return f'<Subscription {self.id} - {self.member.name if self.member else "N/A"}>'

    @property
    def is_active(self):
        """Check if subscription is active"""
        return self.status == 'active' and self.end_date >= date.today()

    @property
    def is_expired(self):
        """Check if subscription is expired"""
        return self.end_date < date.today()

    @property
    def days_remaining(self):
        """Days remaining"""
        if self.end_date >= date.today():
            return (self.end_date - date.today()).days
        return 0

    @property
    def freeze_count(self):
        """Number of times frozen"""
        return self.freezes.count()

    @property
    def can_freeze(self):
        """Check if can freeze"""
        if self.status != 'active':
            return False
        return self.freeze_count < self.plan.max_freezes

    @property
    def total_freeze_days(self):
        """Total days frozen"""
        return sum(f.freeze_days for f in self.freezes.all())

    @property
    def status_text(self):
        """Status in Arabic"""
        status_map = {
            'active': 'نشط',
            'frozen': 'مجمد',
            'expired': 'منتهي',
            'cancelled': 'ملغي',
            'stopped': 'موقوف'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """CSS class for status"""
        class_map = {
            'active': 'success',
            'frozen': 'warning',
            'expired': 'danger',
            'cancelled': 'secondary',
            'stopped': 'dark'
        }
        return class_map.get(self.status, 'secondary')

    def stop(self, reason, user_id):
        """Stop subscription with reason"""
        self.status = 'stopped'
        self.stop_reason = reason
        self.stopped_at = datetime.utcnow()
        self.stopped_by = user_id
        db.session.commit()

    def check_and_update_status(self):
        """Check and update status if needed"""
        if self.status == 'active' and self.end_date < date.today():
            self.status = 'expired'
            db.session.commit()
        return self.status


class SubscriptionFreeze(db.Model):
    """Subscription freeze records"""
    __tablename__ = 'subscription_freezes'

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)

    freeze_start = db.Column(db.Date, nullable=False)
    freeze_end = db.Column(db.Date, nullable=False)
    freeze_days = db.Column(db.Integer, nullable=False)

    # Paid freeze feature
    is_paid = db.Column(db.Boolean, default=False)
    fee_amount = db.Column(db.Numeric(10, 2), default=0)

    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<Freeze {self.freeze_start} - {self.freeze_end}>'


class RenewalRejection(db.Model):
    """Track why members reject renewal"""
    __tablename__ = 'renewal_rejections'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    # Reason: price, time, service, personal
    reason = db.Column(db.String(20), nullable=False)
    details = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    member = db.relationship('Member', backref='renewal_rejections')
    subscription = db.relationship('Subscription', backref='renewal_rejections')

    def __repr__(self):
        return f'<RenewalRejection {self.member_id} - {self.reason}>'

    @property
    def reason_arabic(self):
        """Get reason in Arabic"""
        reason_map = {
            'price': 'السعر',
            'time': 'الوقت',
            'service': 'الخدمة',
            'personal': 'شخصي'
        }
        return reason_map.get(self.reason, self.reason)

    @classmethod
    def get_rejection_stats(cls, brand_id, start_date=None, end_date=None):
        """Get rejection statistics by reason"""
        from sqlalchemy import func
        query = db.session.query(
            cls.reason,
            func.count(cls.id).label('count')
        ).filter(cls.brand_id == brand_id)

        if start_date:
            query = query.filter(cls.created_at >= start_date)
        if end_date:
            query = query.filter(cls.created_at <= end_date)

        return query.group_by(cls.reason).all()


class SubscriptionStop(db.Model):
    """Track subscription stops with detailed info"""
    __tablename__ = 'subscription_stops'

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    # Reason: temporary, permanent, financial, other
    reason_type = db.Column(db.String(20), nullable=False)
    reason_details = db.Column(db.Text)

    stopped_at = db.Column(db.DateTime, default=datetime.utcnow)
    stopped_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # For temporary stops - when to resume
    expected_resume_date = db.Column(db.Date)
    resumed_at = db.Column(db.DateTime)
    resumed_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    subscription = db.relationship('Subscription', backref='stops')
    stopper_user = db.relationship('User', foreign_keys=[stopped_by])
    resumer_user = db.relationship('User', foreign_keys=[resumed_by])

    def __repr__(self):
        return f'<SubscriptionStop {self.subscription_id} - {self.reason_type}>'

    @property
    def reason_type_arabic(self):
        """Get reason type in Arabic"""
        reason_map = {
            'temporary': 'مؤقت',
            'permanent': 'دائم',
            'financial': 'مالي',
            'other': 'أخرى'
        }
        return reason_map.get(self.reason_type, self.reason_type)


class SubscriptionPayment(db.Model):
    """Subscription payment records"""
    __tablename__ = 'subscription_payments'

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(20), default='cash')
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)

    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<Payment {self.amount}>'
