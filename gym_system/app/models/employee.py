"""Employee management models - rewards, deductions, and settings"""
from datetime import datetime, date, time
from app import db


class EmployeeSettings(db.Model):
    """Employee settings per brand (lateness rules, deduction rules)"""
    __tablename__ = 'employee_settings'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False, unique=True)

    # Work schedule
    work_start_time = db.Column(db.Time, default=time(8, 0))  # Default 8:00 AM
    work_end_time = db.Column(db.Time, default=time(17, 0))  # Default 5:00 PM

    # Lateness rules
    late_threshold_minutes = db.Column(db.Integer, default=15)  # Minutes grace period
    auto_deduction_enabled = db.Column(db.Boolean, default=False)
    auto_deduction_amount = db.Column(db.Numeric(10, 2), default=0)  # Per late day

    # Absence rules
    absence_deduction_enabled = db.Column(db.Boolean, default=False)
    absence_deduction_amount = db.Column(db.Numeric(10, 2), default=0)  # Per absent day

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    brand = db.relationship('Brand', backref=db.backref('employee_settings', uselist=False))

    def __repr__(self):
        return f'<EmployeeSettings brand_id={self.brand_id}>'

    @classmethod
    def get_or_create(cls, brand_id):
        """Get settings for brand, create if not exists"""
        settings = cls.query.filter_by(brand_id=brand_id).first()
        if not settings:
            settings = cls(brand_id=brand_id)
            db.session.add(settings)
            db.session.commit()
        return settings


class EmployeeReward(db.Model):
    """Employee rewards/bonuses"""
    __tablename__ = 'employee_rewards'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    # Reward details
    title = db.Column(db.String(100), nullable=False)  # e.g., "مكافأة حضور", "مكافأة أداء"
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.Text)

    # Recurring settings
    is_recurring = db.Column(db.Boolean, default=False)
    recurring_day = db.Column(db.Integer)  # Day of month (1-28) for recurring rewards

    # Date tracking
    effective_date = db.Column(db.Date, default=date.today)  # When reward takes effect
    end_date = db.Column(db.Date)  # For recurring: when to stop (null = forever)

    # Status
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    employee = db.relationship('User', foreign_keys=[user_id], backref='rewards')
    creator = db.relationship('User', foreign_keys=[created_by])
    brand = db.relationship('Brand', backref='employee_rewards')

    def __repr__(self):
        return f'<EmployeeReward {self.title} - {self.amount}>'

    @property
    def status_text(self):
        """Status in Arabic"""
        if not self.is_active:
            return 'ملغي'
        if self.is_recurring:
            return 'متكرر شهرياً'
        return 'مرة واحدة'

    @property
    def status_class(self):
        """CSS class for status"""
        if not self.is_active:
            return 'secondary'
        if self.is_recurring:
            return 'info'
        return 'success'


class EmployeeDeduction(db.Model):
    """Employee deductions"""
    __tablename__ = 'employee_deductions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    # Deduction details
    title = db.Column(db.String(100), nullable=False)  # e.g., "خصم تأخير", "خصم غياب"
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.Text)

    # Type: 'manual', 'late', 'absence'
    deduction_type = db.Column(db.String(20), default='manual')

    # Date tracking
    deduction_date = db.Column(db.Date, default=date.today)

    # Link to attendance (for auto deductions)
    attendance_id = db.Column(db.Integer, db.ForeignKey('employee_attendance.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    employee = db.relationship('User', foreign_keys=[user_id], backref='deductions')
    creator = db.relationship('User', foreign_keys=[created_by])
    brand = db.relationship('Brand', backref='employee_deductions')
    attendance = db.relationship('EmployeeAttendance', backref='deductions')

    def __repr__(self):
        return f'<EmployeeDeduction {self.title} - {self.amount}>'

    @property
    def type_text(self):
        """Type in Arabic"""
        type_map = {
            'manual': 'يدوي',
            'late': 'تأخير',
            'absence': 'غياب'
        }
        return type_map.get(self.deduction_type, self.deduction_type)

    @property
    def type_class(self):
        """CSS class for type"""
        type_classes = {
            'manual': 'secondary',
            'late': 'warning',
            'absence': 'danger'
        }
        return type_classes.get(self.deduction_type, 'secondary')
