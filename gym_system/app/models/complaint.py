from datetime import datetime
from app import db
import secrets


class ComplaintCategory(db.Model):
    """Complaint categories (جهاز, مسبح, نظافة, خدمة)"""
    __tablename__ = 'complaint_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # Arabic: جهاز, مسبح, نظافة, خدمة
    name_en = db.Column(db.String(50))  # English: equipment, pool, cleanliness, service
    icon = db.Column(db.String(50))  # Bootstrap icon class
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    complaints = db.relationship('Complaint', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<ComplaintCategory {self.name}>'

    @classmethod
    def get_default_categories(cls):
        """Get default complaint categories"""
        return [
            {'name': 'جهاز', 'name_en': 'equipment', 'icon': 'bi-tools'},
            {'name': 'مسبح', 'name_en': 'pool', 'icon': 'bi-water'},
            {'name': 'نظافة', 'name_en': 'cleanliness', 'icon': 'bi-brush'},
            {'name': 'خدمة', 'name_en': 'service', 'icon': 'bi-headset'},
        ]

    @classmethod
    def seed_defaults(cls):
        """Seed default complaint categories"""
        for cat_data in cls.get_default_categories():
            existing = cls.query.filter_by(name_en=cat_data['name_en']).first()
            if not existing:
                category = cls(**cat_data)
                db.session.add(category)
        db.session.commit()


class Complaint(db.Model):
    """Customer complaints"""
    __tablename__ = 'complaints'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('complaint_categories.id'))

    # Public submission token for tracking
    tracking_token = db.Column(db.String(32), unique=True)

    # Customer info (for anonymous complaints)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    customer_email = db.Column(db.String(100))

    # Complaint details
    subject = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent

    # Status: pending, in_progress, resolved, closed
    status = db.Column(db.String(20), default='pending')
    resolution = db.Column(db.Text)

    # Who submitted: 'customer' (via public link) or 'receptionist'
    submitted_by = db.Column(db.String(20), default='receptionist')

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    # Staff assignments
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # Receptionist who created
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))  # Who handles it
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # Who resolved it

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='complaints_created')
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='complaints_assigned')
    resolver = db.relationship('User', foreign_keys=[resolved_by], backref='complaints_resolved')

    def __repr__(self):
        return f'<Complaint {self.id}: {self.subject[:30]}>'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.tracking_token:
            self.tracking_token = secrets.token_hex(16)

    @property
    def status_arabic(self):
        """Get status in Arabic"""
        status_map = {
            'pending': 'قيد الانتظار',
            'in_progress': 'قيد المعالجة',
            'resolved': 'تم الحل',
            'closed': 'مغلق'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """Get CSS class for status"""
        status_classes = {
            'pending': 'warning',
            'in_progress': 'info',
            'resolved': 'success',
            'closed': 'secondary'
        }
        return status_classes.get(self.status, 'secondary')

    @property
    def priority_arabic(self):
        """Get priority in Arabic"""
        priority_map = {
            'low': 'منخفضة',
            'normal': 'عادية',
            'high': 'عالية',
            'urgent': 'عاجلة'
        }
        return priority_map.get(self.priority, self.priority)

    @property
    def priority_class(self):
        """Get CSS class for priority"""
        priority_classes = {
            'low': 'info',
            'normal': 'secondary',
            'high': 'warning',
            'urgent': 'danger'
        }
        return priority_classes.get(self.priority, 'secondary')

    @property
    def customer_display_name(self):
        """Get customer name for display"""
        if self.member:
            return self.member.name
        return self.customer_name or 'غير معروف'

    def resolve(self, resolution_text, resolved_by_user_id):
        """Mark complaint as resolved"""
        self.status = 'resolved'
        self.resolution = resolution_text
        self.resolved_at = datetime.utcnow()
        self.resolved_by = resolved_by_user_id
        db.session.commit()

    def close(self):
        """Close the complaint"""
        self.status = 'closed'
        db.session.commit()

    @classmethod
    def get_open_complaints(cls, brand_id=None, branch_id=None):
        """Get all open (non-closed) complaints"""
        query = cls.query.filter(cls.status.in_(['pending', 'in_progress']))
        if brand_id:
            query = query.filter_by(brand_id=brand_id)
        if branch_id:
            query = query.filter_by(branch_id=branch_id)
        return query.order_by(cls.created_at.desc()).all()

    @classmethod
    def count_by_category(cls, brand_id=None, start_date=None, end_date=None):
        """Count complaints by category"""
        from sqlalchemy import func
        query = db.session.query(
            ComplaintCategory.name,
            func.count(cls.id)
        ).join(cls.category)

        if brand_id:
            query = query.filter(cls.brand_id == brand_id)
        if start_date:
            query = query.filter(cls.created_at >= start_date)
        if end_date:
            query = query.filter(cls.created_at <= end_date)

        return query.group_by(ComplaintCategory.name).all()
