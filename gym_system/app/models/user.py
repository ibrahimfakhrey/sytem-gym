from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager


class Role(db.Model):
    """Role model - User roles"""
    __tablename__ = 'roles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # Arabic name
    name_en = db.Column(db.String(50), unique=True, nullable=False)  # English name for logic
    description = db.Column(db.Text)

    # Permission flags
    is_owner = db.Column(db.Boolean, default=False)
    can_view_all_brands = db.Column(db.Boolean, default=False)
    can_manage_members = db.Column(db.Boolean, default=False)
    can_manage_subscriptions = db.Column(db.Boolean, default=False)
    can_view_finance = db.Column(db.Boolean, default=False)
    can_manage_finance = db.Column(db.Boolean, default=False)
    can_view_reports = db.Column(db.Boolean, default=False)
    can_manage_attendance = db.Column(db.Boolean, default=False)

    # New permission flags
    can_view_complaints = db.Column(db.Boolean, default=False)
    can_manage_complaints = db.Column(db.Boolean, default=False)
    can_view_daily_closing = db.Column(db.Boolean, default=False)
    can_manage_daily_closing = db.Column(db.Boolean, default=False)
    can_manage_classes = db.Column(db.Boolean, default=False)
    can_approve_expenses = db.Column(db.Boolean, default=False)
    can_manage_offers = db.Column(db.Boolean, default=False)
    can_manage_gift_cards = db.Column(db.Boolean, default=False)

    # Relationships
    users = db.relationship('User', backref='role', lazy='dynamic')

    def __repr__(self):
        return f'<Role {self.name_en}>'

    @property
    def is_admin(self):
        return self.is_owner

    @property
    def is_brand_manager(self):
        """Brand owner (was brand_manager, now name_en='owner')"""
        return self.name_en == 'owner'

    @property
    def is_branch_manager(self):
        return self.name_en == 'branch_manager'

    @property
    def is_finance_admin(self):
        return self.name_en == 'finance_admin'

    @property
    def can_manage_brands(self):
        return self.is_owner

    @property
    def can_manage_users(self):
        return self.name_en in ['admin', 'owner', 'branch_manager']

    @property
    def can_export_reports(self):
        return self.can_view_reports

    @property
    def badge_class(self):
        """CSS badge class for role"""
        class_map = {
            'admin': 'primary',
            'owner': 'success',
            'branch_manager': 'info',
            'branch_receptionist': 'info',
            'branch_finance': 'warning',
            'finance_admin': 'secondary',
            'employee': 'dark'
        }
        return class_map.get(self.name_en, 'secondary')

    @property
    def role_level(self):
        """Role hierarchy level (higher = more power). Used to prevent editing users above you."""
        levels = {
            'admin': 100,
            'finance_admin': 90,
            'owner': 80,
            'branch_manager': 60,
            'brand_finance': 50,
            'branch_finance': 40,
            'branch_receptionist': 30,
            'employee': 10,
        }
        return levels.get(self.name_en, 0)


class User(UserMixin, db.Model):
    """User model - System users"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=True)  # NULL for owner/finance_admin
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)

    # Fingerprint ID for staff attendance sync
    fingerprint_id = db.Column(db.Integer)

    # Staff type
    is_trainer = db.Column(db.Boolean, default=False)
    department = db.Column(db.String(50))  # reception, training, cleaning, management, etc.

    # Salary info
    salary_type = db.Column(db.String(10))  # 'fixed' or 'daily'
    salary_amount = db.Column(db.Numeric(10, 2))

    is_active = db.Column(db.Boolean, default=True)
    # GYM-43 — soft-delete. is_active stays user-facing ("معطل/نشط"); is_deleted
    # is a separate, finer-grained flag that hides the user from lists and
    # blocks login but keeps their FK relationships intact.
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Relationships
    created_members = db.relationship('Member', backref='created_by_user',
                                      foreign_keys='Member.created_by', lazy='dynamic')
    created_subscriptions = db.relationship('Subscription', backref='created_by_user',
                                           foreign_keys='Subscription.created_by', lazy='dynamic')
    employee_attendance = db.relationship('EmployeeAttendance', backref='user', lazy='dynamic')
    salaries = db.relationship('Salary', backref='user', lazy='dynamic',
                               foreign_keys='Salary.user_id')

    def __repr__(self):
        return f'<User {self.email}>'

    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        """Check password"""
        return check_password_hash(self.password_hash, password)

    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()
        db.session.commit()

    # Permission shortcuts
    @property
    def is_owner(self):
        return self.role.is_owner if self.role else False

    @property
    def is_brand_manager(self):
        return self.role.is_brand_manager if self.role else False

    @property
    def is_branch_manager(self):
        return self.role.is_branch_manager if self.role else False

    @property
    def can_view_all_brands(self):
        return self.role.can_view_all_brands if self.role else False

    @property
    def can_manage_brands(self):
        return self.role.can_manage_brands if self.role else False

    @property
    def can_manage_users(self):
        return self.role.can_manage_users if self.role else False

    @property
    def can_manage_members(self):
        return self.role.can_manage_members if self.role else False

    @property
    def can_manage_subscriptions(self):
        return self.role.can_manage_subscriptions if self.role else False

    @property
    def can_manage_finance(self):
        return self.role.can_manage_finance if self.role else False

    @property
    def can_view_reports(self):
        return self.role.can_view_reports if self.role else False

    @property
    def can_export_reports(self):
        return self.role.can_export_reports if self.role else False

    @property
    def can_manage_attendance(self):
        return self.role.can_manage_attendance if self.role else False

    @property
    def can_view_complaints(self):
        return self.role.can_view_complaints if self.role else False

    @property
    def can_manage_classes(self):
        return self.role.can_manage_classes if self.role else False

    @property
    def can_view_daily_closing(self):
        return self.role.can_view_daily_closing if self.role else False

    def can_access_brand(self, brand_id):
        """Check if user can access a specific brand"""
        if self.can_view_all_brands:
            return True
        return self.brand_id == brand_id

    def can_access_branch(self, branch_id):
        """Check if user can access a specific branch"""
        if self.is_owner or self.can_view_all_brands:
            return True
        if self.role and self.role.name_en == 'owner':
            # Brand owner can access all branches of their brand
            from .company import Branch
            branch = Branch.query.get(branch_id)
            return branch and branch.brand_id == self.brand_id
        return self.branch_id == branch_id

    def get_accessible_brands(self):
        """Get brands this user can access"""
        from .company import Brand
        if self.can_view_all_brands:
            return Brand.query.filter_by(is_active=True).all()
        elif self.brand_id:
            return [self.brand]
        return []


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login. GYM-43 — soft-deleted users get logged out
    on their next request because their session ID won't resolve."""
    u = User.query.get(int(user_id))
    if u is None or u.is_deleted:
        return None
    return u
