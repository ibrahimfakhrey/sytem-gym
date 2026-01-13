from datetime import datetime
from app import db


class Company(db.Model):
    """Company model - Main entity"""
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    brands = db.relationship('Brand', backref='company', lazy='dynamic')

    def __repr__(self):
        return f'<Company {self.name}>'


class Brand(db.Model):
    """Brand model - Gym brands"""
    __tablename__ = 'brands'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    logo = db.Column(db.String(255))

    # Fingerprint settings
    uses_fingerprint = db.Column(db.Boolean, default=False)
    fingerprint_ip = db.Column(db.String(15))
    fingerprint_port = db.Column(db.Integer, default=5005)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    branches = db.relationship('Branch', backref='brand', lazy='dynamic')
    users = db.relationship('User', backref='brand', lazy='dynamic')
    members = db.relationship('Member', backref='brand', lazy='dynamic')
    plans = db.relationship('Plan', backref='brand', lazy='dynamic')
    subscriptions = db.relationship('Subscription', backref='brand', lazy='dynamic')

    def __repr__(self):
        return f'<Brand {self.name}>'

    @property
    def active_members_count(self):
        """Count of active members"""
        return self.members.filter_by(is_active=True).count()

    @property
    def active_subscriptions_count(self):
        """Count of active subscriptions"""
        return self.subscriptions.filter_by(status='active').count()


class Branch(db.Model):
    """Branch model - Branches within each brand"""
    __tablename__ = 'branches'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    users = db.relationship('User', backref='branch', lazy='dynamic')
    members = db.relationship('Member', backref='branch', lazy='dynamic')

    def __repr__(self):
        return f'<Branch {self.name}>'
