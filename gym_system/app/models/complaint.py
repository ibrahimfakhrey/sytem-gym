from datetime import datetime
from app import db


class Complaint(db.Model):
    """Complaint model - Customer complaints"""
    __tablename__ = 'complaints'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=True)

    # Old schema fields
    category_id = db.Column(db.Integer, nullable=True)  # Foreign key removed - not using categories
    tracking_token = db.Column(db.String(32))
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    customer_email = db.Column(db.String(100))

    subject = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20))  # low, medium, high

    # Status: open, in_progress, resolved, closed
    status = db.Column(db.String(20), default='open')

    # Resolution
    resolution = db.Column(db.Text)
    submitted_by = db.Column(db.String(20))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    brand = db.relationship('Brand', backref='complaints', foreign_keys=[brand_id])
    member = db.relationship('Member', backref='complaints', foreign_keys=[member_id])

    # Aliases for compatibility with new code
    @property
    def complaint_type(self):
        """Map category_id to type string"""
        # Default mapping
        return 'other'

    @property
    def resolution_notes(self):
        return self.resolution

    def __repr__(self):
        return f'<Complaint {self.id} - {self.complaint_type}>'

    @property
    def type_text(self):
        """Complaint type in Arabic"""
        type_map = {
            'equipment': 'جهاز',
            'pool': 'مسبح',
            'cleaning': 'نظافة',
            'service': 'خدمة',
            'other': 'أخرى'
        }
        return type_map.get(self.complaint_type, self.complaint_type)

    @property
    def status_text(self):
        """Status in Arabic"""
        status_map = {
            'open': 'مفتوح',
            'in_progress': 'قيد المعالجة',
            'resolved': 'محلول',
            'closed': 'مغلق'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """CSS class for status"""
        class_map = {
            'open': 'danger',
            'in_progress': 'warning',
            'resolved': 'success',
            'closed': 'secondary'
        }
        return class_map.get(self.status, 'secondary')


class SubscriptionSuspension(db.Model):
    """Subscription suspension records"""
    __tablename__ = 'subscription_stops'

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    # Suspension reason categories: price, time, service, personal, other
    reason_type = db.Column(db.String(20))
    reason_details = db.Column(db.Text)

    stopped_at = db.Column(db.DateTime, default=datetime.utcnow)
    stopped_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    expected_resume_date = db.Column(db.Date)
    resumed_at = db.Column(db.DateTime)
    resumed_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Aliases for compatibility
    @property
    def reason_category(self):
        return self.reason_type

    @property
    def suspended_at(self):
        return self.stopped_at

    @property
    def suspended_by(self):
        return self.stopped_by

    # Relationships
    subscription = db.relationship('Subscription', backref='suspensions', foreign_keys=[subscription_id])

    def __repr__(self):
        return f'<Suspension {self.subscription_id} - {self.reason_category}>'

    @property
    def reason_text(self):
        """Reason in Arabic"""
        reason_map = {
            'price': 'سعر',
            'time': 'وقت',
            'service': 'خدمة',
            'personal': 'سبب شخصي',
            'other': 'أخرى'
        }
        return reason_map.get(self.reason_category, self.reason_category)
