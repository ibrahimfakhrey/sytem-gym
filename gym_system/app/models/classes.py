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
    day_of_week = db.Column(db.Integer)  # 0=Saturday, 1=Sunday, ..., 6=Friday (Arabic week)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    # Capacity
    capacity = db.Column(db.Integer, default=20)

    # Settings
    is_recurring = db.Column(db.Boolean, default=True)  # Repeats weekly
    is_active = db.Column(db.Boolean, default=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    bookings = db.relationship('ClassBooking', backref='gym_class', lazy='dynamic')
    trainer = db.relationship('User', backref='classes_taught')

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


class ClassBooking(db.Model):
    """Class bookings by members"""
    __tablename__ = 'class_bookings'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('gym_classes.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'))

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
