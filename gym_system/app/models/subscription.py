from datetime import datetime, date, timedelta
from app import db


class ServiceType(db.Model):
    """Service Type model - Types of services offered (gym, swimming, karate, etc.)"""
    __tablename__ = 'service_types'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)  # Arabic name
    name_en = db.Column(db.String(100))  # English name
    category = db.Column(db.String(50))  # gym, swimming, martial_arts, fitness, etc.
    description = db.Column(db.Text)

    requires_class_booking = db.Column(db.Boolean, default=False)
    capacity = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ServiceType {self.name}>'


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

    # Session-based settings (for educational programs like swimming lessons)
    sessions_count = db.Column(db.Integer, default=0)  # 0 means unlimited/time-based

    # Freeze settings
    max_freezes = db.Column(db.Integer, default=1)
    max_freeze_days = db.Column(db.Integer, default=14)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    subscriptions = db.relationship('Subscription', backref='plan', lazy='dynamic')
    service_type = db.relationship('ServiceType', backref='plans', foreign_keys=[service_type_id])

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

    @property
    def is_session_based(self):
        """Check if this is a session-based plan"""
        return self.sessions_count > 0

    @property
    def plan_type_text(self):
        """Display plan type (time-based vs session-based)"""
        if self.is_session_based:
            return f'{self.sessions_count} حصة'
        return self.duration_text


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

    # Session tracking (for session-based subscriptions)
    sessions_total = db.Column(db.Integer, default=0)  # Total sessions in subscription
    sessions_consumed = db.Column(db.Integer, default=0)  # Sessions already used

    # Amounts
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    paid_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    remaining_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(10, 2), default=0)

    # Status: active, frozen, expired, cancelled, suspended
    status = db.Column(db.String(20), default='active')

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    freezes = db.relationship('SubscriptionFreeze', backref='subscription', lazy='dynamic')
    payments = db.relationship('SubscriptionPayment', backref='subscription', lazy='dynamic')
    attendance = db.relationship('MemberAttendance', backref='subscription', lazy='dynamic')
    service_type = db.relationship('ServiceType', backref='subscriptions', foreign_keys=[service_type_id])

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
            'suspended': 'موقوف'
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
            'suspended': 'dark'
        }
        return class_map.get(self.status, 'secondary')

    @property
    def is_session_based(self):
        """Check if this is a session-based subscription"""
        return self.sessions_total > 0

    @property
    def sessions_remaining(self):
        """Sessions remaining"""
        if not self.is_session_based:
            return None
        return max(0, self.sessions_total - self.sessions_consumed)

    @property
    def has_sessions_available(self):
        """Check if sessions are available"""
        if not self.is_session_based:
            return True  # Time-based subscriptions don't track sessions
        return self.sessions_remaining > 0

    def consume_session(self):
        """Consume one session (for class bookings or attendance)"""
        if self.is_session_based and self.has_sessions_available:
            self.sessions_consumed += 1
            db.session.commit()
            return True
        return False

    def check_and_update_status(self):
        """Check and update status if needed"""
        # Check if time-based subscription expired
        if self.status == 'active' and self.end_date < date.today():
            self.status = 'expired'
            db.session.commit()
        # Check if session-based subscription exhausted
        elif self.status == 'active' and self.is_session_based and not self.has_sessions_available:
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
