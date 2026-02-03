from datetime import datetime, date, time
from app import db


class ClassSession(db.Model):
    """Class/Session model - Gym classes and swimming sessions"""
    __tablename__ = 'gym_classes'
    __mapper_args__ = {
        'exclude_properties': ['session_type', 'max_capacity', 'instructor_id', 'created_by']
    }

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)

    # Session details
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_types.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Schedule
    day_of_week = db.Column(db.Integer)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    # Capacity
    capacity = db.Column(db.Integer)

    # Instructor/Coach
    trainer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Status
    is_recurring = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Note: bookings relationship is defined in Booking model

    # Aliases for compatibility with new code
    @property
    def session_type(self):
        """Map service_type_id to session_type string"""
        # For now, return a default. This can be enhanced later.
        return 'gym_class'

    @property
    def max_capacity(self):
        return self.capacity if self.capacity else 20

    @property
    def instructor_id(self):
        return self.trainer_id

    @property
    def created_by(self):
        """No created_by in old schema"""
        return None

    def __repr__(self):
        return f'<ClassSession {self.name}>'

    @property
    def type_text(self):
        """Session type in Arabic"""
        type_map = {
            'gym_class': 'كلاس جيم',
            'swimming_education': 'سباحة - تعليم',
            'swimming_recreation': 'سباحة - ترفيه',
            'karate': 'كاراتيه',
            'other': 'أخرى'
        }
        return type_map.get(self.session_type, self.session_type)

    @property
    def day_text(self):
        """Day in Arabic"""
        days = ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
        return days[self.day_of_week] if 0 <= self.day_of_week <= 6 else ''

    @property
    def time_slot(self):
        """Time slot formatted"""
        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"

    def get_current_bookings_count(self, session_date=None):
        """Get current bookings count for a specific date"""
        if session_date is None:
            session_date = date.today()

        from app.models.schedule import Booking
        return Booking.query.filter_by(
            class_id=self.id,
            booking_date=session_date,
            status='confirmed'
        ).count()

    def has_available_slots(self, session_date=None):
        """Check if session has available slots"""
        current_bookings = self.get_current_bookings_count(session_date)
        return current_bookings < self.max_capacity

    @property
    def available_slots(self):
        """Get available slots for today"""
        current_bookings = self.get_current_bookings_count()
        return self.max_capacity - current_bookings


class Booking(db.Model):
    """Booking model - Member bookings for classes/sessions"""
    __tablename__ = 'class_bookings'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('gym_classes.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=True)

    # Booking date
    booking_date = db.Column(db.Date, nullable=False)

    # Status: confirmed, cancelled, attended, no_show
    status = db.Column(db.String(20), default='confirmed')

    # Check-in tracking
    check_in_time = db.Column(db.DateTime)
    checked_in_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Notes
    notes = db.Column(db.Text)

    # Tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime)

    # Alias for compatibility with new code
    @property
    def class_session_id(self):
        return self.class_id

    @property
    def session_date(self):
        return self.booking_date

    @property
    def brand_id(self):
        """Get brand_id from the associated gym class"""
        if hasattr(self, 'class_session') and self.class_session:
            return self.class_session.brand_id
        return None

    # Relationships
    member = db.relationship('Member', backref='bookings', foreign_keys=[member_id])
    class_session = db.relationship('ClassSession', backref='bookings', foreign_keys=[class_id])

    def __repr__(self):
        return f'<Booking {self.member.name if self.member else "N/A"} - {self.session_date}>'

    @property
    def status_text(self):
        """Status in Arabic"""
        status_map = {
            'confirmed': 'مؤكد',
            'cancelled': 'ملغي',
            'attended': 'حضر',
            'no_show': 'لم يحضر'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """CSS class for status"""
        class_map = {
            'confirmed': 'success',
            'cancelled': 'danger',
            'attended': 'info',
            'no_show': 'warning'
        }
        return class_map.get(self.status, 'secondary')


class DailyClosing(db.Model):
    """Daily Closing model - End of day cash reconciliation"""
    __tablename__ = 'daily_closings'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)

    # Closing date
    closing_date = db.Column(db.Date, nullable=False)

    # Statistics (auto-calculated)
    new_subscriptions_count = db.Column(db.Integer, default=0)
    renewals_count = db.Column(db.Integer, default=0)
    total_sales = db.Column(db.Numeric(10, 2), default=0)

    # Payment methods breakdown
    cash_amount = db.Column(db.Numeric(10, 2), default=0)
    card_amount = db.Column(db.Numeric(10, 2), default=0)
    transfer_amount = db.Column(db.Numeric(10, 2), default=0)

    # Cash reconciliation
    expected_cash = db.Column(db.Numeric(10, 2), default=0)  # From system
    actual_cash_submitted = db.Column(db.Numeric(10, 2), default=0)  # Counted by staff
    cash_difference = db.Column(db.Numeric(10, 2), default=0)  # Difference

    # Expenses
    total_expenses = db.Column(db.Numeric(10, 2), default=0)

    # Notes
    notes = db.Column(db.Text)
    difference_explanation = db.Column(db.Text)

    # Status: open, closed
    status = db.Column(db.String(20), default='closed')

    # Tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)
    verified_at = db.Column(db.DateTime)

    submitted_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    brand = db.relationship('Brand', backref='daily_closings', foreign_keys=[brand_id])
    closed_by_user = db.relationship('User', foreign_keys=[submitted_by], backref='closings_submitted')
    verified_by_user = db.relationship('User', foreign_keys=[verified_by], backref='closings_verified')

    def __repr__(self):
        return f'<DailyClosing {self.closing_date} - {self.brand.name if self.brand else "N/A"}>'

    @property
    def status_text(self):
        """Status in Arabic"""
        return 'مغلق' if self.status == 'closed' else 'مفتوح'

    @property
    def has_discrepancy(self):
        """Check if there's a cash discrepancy"""
        return abs(float(self.cash_difference)) > 0.01

    @property
    def discrepancy_class(self):
        """CSS class for discrepancy"""
        if not self.has_discrepancy:
            return 'success'
        return 'danger' if abs(float(self.cash_difference)) > 100 else 'warning'
