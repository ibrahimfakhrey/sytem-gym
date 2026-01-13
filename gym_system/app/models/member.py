from datetime import datetime, date
from app import db


class Member(db.Model):
    """Member model - Gym members/clients"""
    __tablename__ = 'members'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)

    # Basic info
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    gender = db.Column(db.String(10))  # 'male' or 'female'
    birth_date = db.Column(db.Date)
    national_id = db.Column(db.String(20))
    address = db.Column(db.Text)

    # Emergency contact
    emergency_contact = db.Column(db.String(100))
    emergency_phone = db.Column(db.String(20))

    # Photo
    photo = db.Column(db.String(255))

    # Fingerprint data
    fingerprint_id = db.Column(db.Integer)
    fingerprint_enrolled = db.Column(db.Boolean, default=False)
    fingerprint_enrolled_at = db.Column(db.DateTime)

    # Status
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    subscriptions = db.relationship('Subscription', backref='member', lazy='dynamic',
                                   order_by='desc(Subscription.created_at)')
    attendance = db.relationship('MemberAttendance', backref='member', lazy='dynamic',
                                order_by='desc(MemberAttendance.check_in)')

    def __repr__(self):
        return f'<Member {self.name}>'

    @property
    def active_subscription(self):
        """Get current active subscription"""
        from .subscription import Subscription
        return Subscription.query.filter(
            Subscription.member_id == self.id,
            Subscription.status == 'active',
            Subscription.end_date >= date.today()
        ).first()

    @property
    def has_active_subscription(self):
        """Check if member has active subscription"""
        return self.active_subscription is not None

    @property
    def subscription_status(self):
        """Get subscription status text"""
        sub = self.active_subscription
        if sub:
            if sub.status == 'frozen':
                return 'مجمد'
            return 'نشط'

        # Check for expired
        last_sub = self.subscriptions.first()
        if last_sub:
            if last_sub.status == 'expired' or last_sub.end_date < date.today():
                return 'منتهي'
            if last_sub.status == 'cancelled':
                return 'ملغي'

        return 'بدون اشتراك'

    @property
    def subscription_status_class(self):
        """Get CSS class for subscription status"""
        status = self.subscription_status
        if status == 'نشط':
            return 'success'
        elif status == 'مجمد':
            return 'warning'
        elif status == 'منتهي':
            return 'danger'
        return 'secondary'

    @property
    def days_remaining(self):
        """Days remaining in subscription"""
        sub = self.active_subscription
        if sub:
            return (sub.end_date - date.today()).days
        return 0

    @property
    def total_attendance_count(self):
        """Total attendance count"""
        return self.attendance.count()

    @property
    def needs_fingerprint_enrollment(self):
        """Check if member needs fingerprint enrollment"""
        if self.brand and self.brand.uses_fingerprint:
            return not self.fingerprint_enrolled
        return False

    def can_check_in(self):
        """Check if member can check in"""
        sub = self.active_subscription
        if not sub:
            return False, 'لا يوجد اشتراك نشط'

        if sub.status == 'frozen':
            return False, 'الاشتراك مجمد'

        if sub.end_date < date.today():
            return False, 'الاشتراك منتهي'

        return True, 'يمكن تسجيل الحضور'
