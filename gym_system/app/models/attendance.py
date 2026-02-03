from datetime import datetime, date
from app import db


class MemberAttendance(db.Model):
    """Member attendance records"""
    __tablename__ = 'member_attendance'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)

    check_in = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    check_out = db.Column(db.DateTime)

    # Source: 'manual', 'qr', 'fingerprint'
    source = db.Column(db.String(20), default='manual')

    # For fingerprint sync
    fingerprint_log_id = db.Column(db.Integer)

    # Warning flags
    has_warning = db.Column(db.Boolean, default=False)
    warning_message = db.Column(db.String(200))

    notes = db.Column(db.Text)

    # Indexes for faster queries
    __table_args__ = (
        db.Index('idx_member_attendance_date', 'brand_id', 'check_in'),
        db.Index('idx_member_attendance_member', 'member_id', 'check_in'),
    )

    def __repr__(self):
        return f'<MemberAttendance {self.member_id} - {self.check_in}>'

    @property
    def check_in_date(self):
        """Check-in date only"""
        return self.check_in.date()

    @property
    def check_in_time(self):
        """Check-in time formatted"""
        return self.check_in.strftime('%H:%M')

    @property
    def source_text(self):
        """Source in Arabic"""
        source_map = {
            'manual': 'يدوي',
            'qr': 'QR',
            'fingerprint': 'بصمة'
        }
        return source_map.get(self.source, self.source)

    @classmethod
    def get_today_count(cls, brand_id):
        """Get today's attendance count for brand"""
        today = date.today()
        return cls.query.filter(
            cls.brand_id == brand_id,
            db.func.date(cls.check_in) == today
        ).count()

    @classmethod
    def get_date_range_count(cls, brand_id, start_date, end_date):
        """Get attendance count for date range"""
        return cls.query.filter(
            cls.brand_id == brand_id,
            db.func.date(cls.check_in) >= start_date,
            db.func.date(cls.check_in) <= end_date
        ).count()


class EmployeeAttendance(db.Model):
    """Employee attendance records"""
    __tablename__ = 'employee_attendance'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)

    date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.Time)
    check_out = db.Column(db.Time)

    # Fingerprint sync fields
    fingerprint_log_id = db.Column(db.Integer)  # ID from TimeRecords table in .mdb
    source = db.Column(db.String(20), default='manual')  # manual, fingerprint

    # Lateness tracking
    expected_check_in = db.Column(db.Time)  # Expected check-in time for shift
    late_minutes = db.Column(db.Integer, default=0)

    # Status: 'present', 'absent', 'late', 'leave'
    status = db.Column(db.String(20), default='present')

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships - using overlaps to resolve duplicate relationship warnings
    employee = db.relationship('User', backref=db.backref('attendance_records', overlaps='employee_attendance,user'), overlaps='employee_attendance,user')
    brand = db.relationship('Brand', backref=db.backref('employee_attendance_records', overlaps='employee_attendance'), overlaps='employee_attendance')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='unique_employee_attendance'),
    )

    def __repr__(self):
        return f'<EmployeeAttendance {self.user_id} - {self.date}>'

    @property
    def status_text(self):
        """Status in Arabic"""
        status_map = {
            'present': 'حاضر',
            'absent': 'غائب',
            'late': 'متأخر',
            'leave': 'إجازة'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """CSS class for status"""
        class_map = {
            'present': 'success',
            'absent': 'danger',
            'late': 'warning',
            'leave': 'info'
        }
        return class_map.get(self.status, 'secondary')

    @property
    def source_text(self):
        """Source in Arabic"""
        source_map = {
            'manual': 'يدوي',
            'fingerprint': 'بصمة'
        }
        return source_map.get(self.source, self.source)

    @property
    def working_hours(self):
        """Calculate working hours"""
        if self.check_in and self.check_out:
            from datetime import datetime, timedelta
            check_in_dt = datetime.combine(self.date, self.check_in)
            check_out_dt = datetime.combine(self.date, self.check_out)
            diff = check_out_dt - check_in_dt
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            return f'{hours}:{minutes:02d}'
        return '-'
