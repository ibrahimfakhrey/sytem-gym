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

    # Capacity settings
    gym_capacity = db.Column(db.Integer, default=100)
    pool_capacity = db.Column(db.Integer, default=50)
    current_gym_occupancy = db.Column(db.Integer, default=0)
    current_pool_occupancy = db.Column(db.Integer, default=0)

    # Contract/Lease expiry tracking
    lease_expiry_date = db.Column(db.Date)
    commercial_registration_expiry = db.Column(db.Date)

    # Relationships
    users = db.relationship('User', backref='branch', lazy='dynamic')
    members = db.relationship('Member', backref='branch', lazy='dynamic')

    def __repr__(self):
        return f'<Branch {self.name}>'

    @property
    def gym_occupancy_percent(self):
        """Get gym occupancy as percentage"""
        if self.gym_capacity and self.gym_capacity > 0:
            return round((self.current_gym_occupancy / self.gym_capacity) * 100, 1)
        return 0

    @property
    def pool_occupancy_percent(self):
        """Get pool occupancy as percentage"""
        if self.pool_capacity and self.pool_capacity > 0:
            return round((self.current_pool_occupancy / self.pool_capacity) * 100, 1)
        return 0

    @property
    def is_gym_full(self):
        """Check if gym is at capacity"""
        return self.current_gym_occupancy >= (self.gym_capacity or 0)

    @property
    def is_pool_full(self):
        """Check if pool is at capacity"""
        return self.current_pool_occupancy >= (self.pool_capacity or 0)

    @property
    def lease_days_remaining(self):
        """Days remaining on lease"""
        from datetime import date
        if self.lease_expiry_date:
            return (self.lease_expiry_date - date.today()).days
        return None

    @property
    def registration_days_remaining(self):
        """Days remaining on commercial registration"""
        from datetime import date
        if self.commercial_registration_expiry:
            return (self.commercial_registration_expiry - date.today()).days
        return None

    def check_in_gym(self):
        """Increment gym occupancy"""
        self.current_gym_occupancy = (self.current_gym_occupancy or 0) + 1
        db.session.commit()

    def check_out_gym(self):
        """Decrement gym occupancy"""
        if self.current_gym_occupancy and self.current_gym_occupancy > 0:
            self.current_gym_occupancy -= 1
            db.session.commit()

    def check_in_pool(self):
        """Increment pool occupancy"""
        self.current_pool_occupancy = (self.current_pool_occupancy or 0) + 1
        db.session.commit()

    def check_out_pool(self):
        """Decrement pool occupancy"""
        if self.current_pool_occupancy and self.current_pool_occupancy > 0:
            self.current_pool_occupancy -= 1
            db.session.commit()

    def reset_occupancy(self):
        """Reset all occupancy counts (for end of day)"""
        self.current_gym_occupancy = 0
        self.current_pool_occupancy = 0
        db.session.commit()
