from datetime import datetime
from app import db


class ServiceType(db.Model):
    """Service types available at the gym (جيم، سباحة، كاراتيه، صالون)"""
    __tablename__ = 'service_types'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    # Service info
    name = db.Column(db.String(100), nullable=False)  # Arabic name: جيم، سباحة تعليم
    name_en = db.Column(db.String(100))  # English name: gym, swimming_teaching
    category = db.Column(db.String(50))  # gym, swimming, karate, salon, package
    description = db.Column(db.Text)

    # Settings
    requires_class_booking = db.Column(db.Boolean, default=False)  # Must book class to enter
    capacity = db.Column(db.Integer)  # Max capacity for this service

    # Status
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    brand = db.relationship('Brand', backref='service_types')
    plans = db.relationship('Plan', backref='service_type', lazy='dynamic')

    def __repr__(self):
        return f'<ServiceType {self.name}>'

    @classmethod
    def get_default_services(cls):
        """Get default service types to seed"""
        return [
            {'name': 'جيم', 'name_en': 'gym', 'category': 'gym', 'requires_class_booking': False},
            {'name': 'سباحة تعليم', 'name_en': 'swimming_teaching', 'category': 'swimming', 'requires_class_booking': True},
            {'name': 'سباحة ترفيه', 'name_en': 'swimming_recreation', 'category': 'swimming', 'requires_class_booking': False},
            {'name': 'كاراتيه', 'name_en': 'karate', 'category': 'karate', 'requires_class_booking': True},
            {'name': 'صالون', 'name_en': 'salon', 'category': 'salon', 'requires_class_booking': True},
        ]

    @classmethod
    def seed_defaults(cls, brand_id):
        """Seed default service types for a brand"""
        for service_data in cls.get_default_services():
            existing = cls.query.filter_by(
                brand_id=brand_id,
                name_en=service_data['name_en']
            ).first()
            if not existing:
                service = cls(brand_id=brand_id, **service_data)
                db.session.add(service)
        db.session.commit()
