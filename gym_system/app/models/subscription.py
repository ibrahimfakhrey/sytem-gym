from datetime import datetime, date, timedelta
from app import db


class Plan(db.Model):
    """Plan model - Subscription plans"""
    __tablename__ = 'plans'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    duration_days = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

    # Freeze settings
    max_freezes = db.Column(db.Integer, default=1)
    max_freeze_days = db.Column(db.Integer, default=14)

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

    # Dates
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    original_end_date = db.Column(db.Date, nullable=False)

    # Amounts
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    paid_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    remaining_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(10, 2), default=0)

    # Status: active, frozen, expired, cancelled
    status = db.Column(db.String(20), default='active')

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

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
            'cancelled': 'ملغي'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """CSS class for status"""
        class_map = {
            'active': 'success',
            'frozen': 'warning',
            'expired': 'danger',
            'cancelled': 'secondary'
        }
        return class_map.get(self.status, 'secondary')

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

    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<Freeze {self.freeze_start} - {self.freeze_end}>'


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
