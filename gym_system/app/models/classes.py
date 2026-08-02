from datetime import datetime, date, time, timedelta
from app import db


class GymClass(db.Model):
    """Class/session definitions for swimming, karate, etc."""
    __tablename__ = 'gym_classes'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_types.id'), nullable=False)

    # Class info
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    trainer_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Schedule - for recurring classes
    day_of_week = db.Column(db.Integer)  # 0=Saturday, 1=Sunday, ..., 6=Friday (Arabic week). Kept for legacy read compat; new code uses weekday_mask.
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    # GYM-62 course schedule
    start_date = db.Column(db.Date)  # course start
    end_date = db.Column(db.Date)    # course end
    weekday_mask = db.Column(db.Integer, default=0)  # bitmask, bit i = (1 << i) on Arabic-week 0=Sat..6=Fri

    # Capacity
    capacity = db.Column(db.Integer, default=20)

    # GYM-62 pricing / cost
    price = db.Column(db.Numeric(10, 2), default=0)
    trainer_fee_per_session = db.Column(db.Numeric(10, 2), default=0)

    # Settings
    is_recurring = db.Column(db.Boolean, default=True)  # Repeats weekly
    is_active = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default='active')  # GYM-62: active|ended|cancelled

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    bookings = db.relationship('ClassBooking', backref='gym_class', lazy='dynamic')
    trainer = db.relationship('User', backref='classes_taught')
    service_type = db.relationship('ServiceType', backref='gym_classes')
    brand = db.relationship('Brand', foreign_keys=[brand_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])

    def __repr__(self):
        return f'<GymClass {self.name}>'

    @property
    def day_name_arabic(self):
        """Get day name in Arabic"""
        days = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة']
        if self.day_of_week is not None and 0 <= self.day_of_week <= 6:
            return days[self.day_of_week]
        return 'غير محدد'

    @property
    def time_range(self):
        """Get time range as string"""
        if self.start_time and self.end_time:
            return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"
        return 'غير محدد'

    @property
    def duration_minutes(self):
        """Get class duration in minutes"""
        if self.start_time and self.end_time:
            start = datetime.combine(date.today(), self.start_time)
            end = datetime.combine(date.today(), self.end_time)
            return int((end - start).total_seconds() / 60)
        return 0

    def get_bookings_for_date(self, booking_date):
        """Get all bookings for a specific date"""
        return self.bookings.filter_by(booking_date=booking_date).all()

    def get_available_spots(self, booking_date):
        """Get available spots for a specific date"""
        booked = self.bookings.filter(
            ClassBooking.booking_date == booking_date,
            ClassBooking.status.in_(['booked', 'attended'])
        ).count()
        return max(0, self.capacity - booked)

    @property
    def today_available_spots(self):
        """Get available spots for today"""
        return self.get_available_spots(date.today())

    @property
    def today_booked_count(self):
        """Get booked count for today"""
        return self.bookings.filter(
            ClassBooking.booking_date == date.today(),
            ClassBooking.status.in_(['booked', 'attended'])
        ).count()

    def is_full(self, booking_date):
        """Check if class is full for a specific date"""
        return self.get_available_spots(booking_date) <= 0

    def can_book(self, member_id, booking_date):
        """Check if a member can book this class"""
        # Check if already booked
        existing = self.bookings.filter(
            ClassBooking.member_id == member_id,
            ClassBooking.booking_date == booking_date,
            ClassBooking.status.in_(['booked', 'attended'])
        ).first()
        if existing:
            return False, 'العضو مسجل بالفعل في هذا الكلاس'

        # Check capacity
        if self.is_full(booking_date):
            return False, 'الكلاس ممتلئ'

        return True, 'يمكن الحجز'

    @classmethod
    def get_schedule_for_day(cls, brand_id, day_of_week, branch_id=None):
        """Get all classes for a specific day"""
        query = cls.query.filter_by(
            brand_id=brand_id,
            day_of_week=day_of_week,
            is_active=True
        )
        if branch_id:
            query = query.filter_by(branch_id=branch_id)
        return query.order_by(cls.start_time).all()

    @classmethod
    def get_today_classes(cls, brand_id, branch_id=None):
        """Get all classes for today"""
        # Saturday = 0 in our Arabic week system
        today_weekday = (date.today().weekday() + 2) % 7  # Convert Python weekday to Arabic
        return cls.get_schedule_for_day(brand_id, today_weekday, branch_id)

    # GYM-62 helpers

    def weekdays_list(self):
        """Return the Arabic-week weekday indices this class meets on."""
        if self.weekday_mask:
            return [i for i in range(7) if self.weekday_mask & (1 << i)]
        # Legacy fallback: single day_of_week
        return [self.day_of_week] if self.day_of_week is not None else []

    def generate_sessions(self):
        """Create ClassSession rows for every matching weekday in [start_date, end_date].
        Idempotent — skips existing (class_id, session_date) pairs. Returns count created."""
        if not (self.start_date and self.end_date and self.start_time and self.end_time):
            return 0
        weekdays = set(self.weekdays_list())
        if not weekdays:
            return 0
        existing = {s.session_date for s in ClassSession.query.filter_by(class_id=self.id).all()}
        created = 0
        d = self.start_date
        while d <= self.end_date:
            # Python weekday() Mon=0..Sun=6 → Arabic Sat=0..Fri=6
            arabic_dow = (d.weekday() + 2) % 7
            if arabic_dow in weekdays and d not in existing:
                db.session.add(ClassSession(
                    class_id=self.id,
                    session_date=d,
                    start_time=self.start_time,
                    end_time=self.end_time,
                    status='scheduled',
                ))
                created += 1
            d += timedelta(days=1)
        return created


class ClassBooking(db.Model):
    """Class bookings by members"""
    __tablename__ = 'class_bookings'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('gym_classes.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'))
    session_id = db.Column(db.Integer, db.ForeignKey('class_sessions.id'))       # GYM-62
    enrollment_id = db.Column(db.Integer, db.ForeignKey('class_enrollments.id'))  # GYM-62

    # Booking info
    booking_date = db.Column(db.Date, nullable=False)

    # Status: booked, attended, cancelled, no_show
    status = db.Column(db.String(20), default='booked')

    # Check-in tracking
    check_in_time = db.Column(db.DateTime)
    checked_in_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Notes
    notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime)

    # Relationships
    member = db.relationship('Member', backref=db.backref('class_bookings', lazy='dynamic'))

    def __repr__(self):
        return f'<ClassBooking {self.id} for Class {self.class_id}>'

    @property
    def status_arabic(self):
        """Get status in Arabic"""
        status_map = {
            'booked': 'محجوز',
            'attended': 'حضر',
            'cancelled': 'ملغي',
            'no_show': 'لم يحضر'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """Get CSS class for status"""
        status_classes = {
            'booked': 'info',
            'attended': 'success',
            'cancelled': 'secondary',
            'no_show': 'danger'
        }
        return status_classes.get(self.status, 'secondary')

    def check_in(self, checked_in_by_user_id=None):
        """Mark booking as attended"""
        self.status = 'attended'
        self.check_in_time = datetime.utcnow()
        self.checked_in_by = checked_in_by_user_id
        db.session.commit()

    def cancel(self):
        """Cancel the booking"""
        self.status = 'cancelled'
        self.cancelled_at = datetime.utcnow()
        db.session.commit()

    def mark_no_show(self):
        """Mark as no-show"""
        self.status = 'no_show'
        db.session.commit()

    @classmethod
    def book_class(cls, class_id, member_id, booking_date, subscription_id=None):
        """Create a new class booking"""
        gym_class = GymClass.query.get(class_id)
        if not gym_class:
            return None, 'الكلاس غير موجود'

        can_book, message = gym_class.can_book(member_id, booking_date)
        if not can_book:
            return None, message

        booking = cls(
            class_id=class_id,
            member_id=member_id,
            booking_date=booking_date,
            subscription_id=subscription_id
        )
        db.session.add(booking)
        db.session.commit()
        return booking, 'تم الحجز بنجاح'

    @classmethod
    def get_member_bookings(cls, member_id, start_date=None, end_date=None):
        """Get all bookings for a member"""
        query = cls.query.filter_by(member_id=member_id)
        if start_date:
            query = query.filter(cls.booking_date >= start_date)
        if end_date:
            query = query.filter(cls.booking_date <= end_date)
        return query.order_by(cls.booking_date.desc()).all()

    @classmethod
    def has_booking_today(cls, member_id, class_id=None):
        """Check if member has booking for today"""
        today = date.today()
        query = cls.query.filter(
            cls.member_id == member_id,
            cls.booking_date == today,
            cls.status.in_(['booked', 'attended'])
        )
        if class_id:
            query = query.filter_by(class_id=class_id)
        return query.first() is not None


class ClassSession(db.Model):
    """GYM-62: one row per (class, calendar date) inside a course's date range,
    generated when the class is created/edited. Attendance = ClassBooking joined
    back to this row."""
    __tablename__ = 'class_sessions'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('gym_classes.id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default='scheduled', nullable=False)  # scheduled|held|cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('class_id', 'session_date', name='uq_class_session_date'),
    )

    gym_class = db.relationship('GymClass', backref=db.backref('sessions', lazy='dynamic'))
    bookings = db.relationship('ClassBooking', backref='session', lazy='dynamic',
                               foreign_keys='ClassBooking.session_id')

    def __repr__(self):
        return f'<ClassSession {self.class_id} @ {self.session_date}>'

    @property
    def status_arabic(self):
        return {'scheduled': 'مجدول', 'held': 'منفذ', 'cancelled': 'ملغي'}.get(self.status, self.status)


class ClassEnrollment(db.Model):
    """GYM-62: a member's paid enrollment in a class course. Owns its linked
    Subscription + Invoice + pre-generated ClassBooking rows for the enrollment
    window."""
    __tablename__ = 'class_enrollments'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('gym_classes.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'))
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'))

    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    sessions_total = db.Column(db.Integer, default=0)

    total_amount = db.Column(db.Numeric(10, 2), default=0)
    paid_amount = db.Column(db.Numeric(10, 2), default=0)
    refund_amount = db.Column(db.Numeric(10, 2), default=0)

    status = db.Column(db.String(20), default='active', nullable=False)  # active|cancelled|completed|refunded
    notes = db.Column(db.Text)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime)

    gym_class = db.relationship('GymClass', backref=db.backref('enrollments', lazy='dynamic'))
    member = db.relationship('Member', backref=db.backref('class_enrollments', lazy='dynamic'))
    subscription = db.relationship('Subscription', foreign_keys=[subscription_id])
    invoice = db.relationship('Invoice', foreign_keys=[invoice_id])
    bookings = db.relationship('ClassBooking', backref='enrollment', lazy='dynamic',
                               foreign_keys='ClassBooking.enrollment_id')

    def __repr__(self):
        return f'<ClassEnrollment {self.id} member={self.member_id} class={self.class_id}>'

    @property
    def status_arabic(self):
        return {
            'active': 'نشط', 'cancelled': 'ملغي',
            'completed': 'مكتمل', 'refunded': 'مسترد',
        }.get(self.status, self.status)
