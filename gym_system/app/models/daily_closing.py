from datetime import datetime, date
from app import db
from decimal import Decimal


class DailyClosing(db.Model):
    """Daily closing/end-of-day reconciliation (الإقفال اليومي)"""
    __tablename__ = 'daily_closings'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)

    # Date
    closing_date = db.Column(db.Date, nullable=False)

    # Subscription counts
    new_subscriptions_count = db.Column(db.Integer, default=0)
    renewals_count = db.Column(db.Integer, default=0)

    # Revenue breakdown by payment method
    total_sales = db.Column(db.Numeric(10, 2), default=0)
    cash_amount = db.Column(db.Numeric(10, 2), default=0)
    card_amount = db.Column(db.Numeric(10, 2), default=0)  # شبكة
    transfer_amount = db.Column(db.Numeric(10, 2), default=0)  # حوالة

    # Cash reconciliation
    expected_cash = db.Column(db.Numeric(10, 2), default=0)  # What system says
    actual_cash_submitted = db.Column(db.Numeric(10, 2))  # What receptionist counted
    cash_difference = db.Column(db.Numeric(10, 2), default=0)  # Difference

    # Expenses for the day
    total_expenses = db.Column(db.Numeric(10, 2), default=0)

    # Notes
    notes = db.Column(db.Text)
    difference_explanation = db.Column(db.Text)  # Explanation for cash difference

    # Status: pending, submitted, verified, rejected
    status = db.Column(db.String(20), default='pending')

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)
    verified_at = db.Column(db.DateTime)

    # Staff assignments
    submitted_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    submitter = db.relationship('User', foreign_keys=[submitted_by], backref='daily_closings_submitted')
    verifier = db.relationship('User', foreign_keys=[verified_by], backref='daily_closings_verified')

    # Unique constraint: one closing per branch per day
    __table_args__ = (
        db.UniqueConstraint('brand_id', 'branch_id', 'closing_date', name='unique_daily_closing'),
    )

    def __repr__(self):
        return f'<DailyClosing {self.closing_date} - Branch {self.branch_id}>'

    @property
    def status_arabic(self):
        """Get status in Arabic"""
        status_map = {
            'pending': 'قيد الإعداد',
            'submitted': 'تم التسليم',
            'verified': 'تم التحقق',
            'rejected': 'مرفوض'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """Get CSS class for status"""
        status_classes = {
            'pending': 'warning',
            'submitted': 'info',
            'verified': 'success',
            'rejected': 'danger'
        }
        return status_classes.get(self.status, 'secondary')

    @property
    def has_cash_difference(self):
        """Check if there's a cash difference"""
        return self.cash_difference and float(self.cash_difference) != 0

    @property
    def cash_difference_class(self):
        """Get CSS class for cash difference"""
        if not self.has_cash_difference:
            return 'success'
        diff = float(self.cash_difference)
        if abs(diff) <= 10:  # Small difference
            return 'warning'
        return 'danger'  # Large difference

    @property
    def net_income(self):
        """Calculate net income (sales - expenses)"""
        return float(self.total_sales or 0) - float(self.total_expenses or 0)

    def calculate_from_transactions(self):
        """
        Calculate closing values from actual transactions for the day
        This should be called when creating or updating the closing
        """
        from .finance import Income
        from .subscription import Subscription, SubscriptionPayment

        # Get subscriptions created on this date
        new_subs = Subscription.query.filter(
            Subscription.brand_id == self.brand_id,
            db.func.date(Subscription.created_at) == self.closing_date
        )
        if self.branch_id:
            new_subs = new_subs.filter_by(branch_id=self.branch_id)

        self.new_subscriptions_count = new_subs.count()

        # Get renewals (subscriptions with same member having previous subscription)
        # This is simplified - you might want a more accurate calculation
        self.renewals_count = 0  # TODO: Implement renewal detection

        # Get payments by method
        payments = SubscriptionPayment.query.filter(
            SubscriptionPayment.brand_id == self.brand_id,
            db.func.date(SubscriptionPayment.payment_date) == self.closing_date
        )

        self.cash_amount = sum(float(p.amount) for p in payments if p.payment_method == 'cash') or 0
        self.card_amount = sum(float(p.amount) for p in payments if p.payment_method == 'card') or 0
        self.transfer_amount = sum(float(p.amount) for p in payments if p.payment_method == 'transfer') or 0

        self.total_sales = self.cash_amount + self.card_amount + self.transfer_amount
        self.expected_cash = self.cash_amount

    def submit(self, actual_cash, notes=None, explanation=None, user_id=None):
        """Submit the daily closing with actual cash count"""
        self.actual_cash_submitted = Decimal(str(actual_cash))
        self.cash_difference = self.actual_cash_submitted - Decimal(str(self.expected_cash or 0))
        self.notes = notes
        self.difference_explanation = explanation
        self.status = 'submitted'
        self.submitted_at = datetime.utcnow()
        self.submitted_by = user_id
        db.session.commit()

    def verify(self, user_id, approve=True):
        """Verify/reject the daily closing"""
        if approve:
            self.status = 'verified'
        else:
            self.status = 'rejected'
        self.verified_at = datetime.utcnow()
        self.verified_by = user_id
        db.session.commit()

    @classmethod
    def get_or_create(cls, brand_id, closing_date, branch_id=None):
        """Get existing closing or create a new one"""
        closing = cls.query.filter_by(
            brand_id=brand_id,
            branch_id=branch_id,
            closing_date=closing_date
        ).first()

        if not closing:
            closing = cls(
                brand_id=brand_id,
                branch_id=branch_id,
                closing_date=closing_date
            )
            db.session.add(closing)
            closing.calculate_from_transactions()
            db.session.commit()

        return closing

    @classmethod
    def get_pending_verifications(cls, brand_id=None):
        """Get all closings pending verification"""
        query = cls.query.filter_by(status='submitted')
        if brand_id:
            query = query.filter_by(brand_id=brand_id)
        return query.order_by(cls.closing_date.desc()).all()

    @classmethod
    def get_with_differences(cls, brand_id=None, min_difference=0):
        """Get closings with cash differences"""
        from sqlalchemy import func
        query = cls.query.filter(
            func.abs(cls.cash_difference) > min_difference
        )
        if brand_id:
            query = query.filter_by(brand_id=brand_id)
        return query.order_by(cls.closing_date.desc()).all()

    @classmethod
    def get_summary(cls, brand_id, start_date, end_date, branch_id=None):
        """Get summary for a date range"""
        from sqlalchemy import func

        query = cls.query.filter(
            cls.brand_id == brand_id,
            cls.closing_date >= start_date,
            cls.closing_date <= end_date,
            cls.status.in_(['submitted', 'verified'])
        )
        if branch_id:
            query = query.filter_by(branch_id=branch_id)

        result = db.session.query(
            func.sum(cls.total_sales),
            func.sum(cls.cash_amount),
            func.sum(cls.card_amount),
            func.sum(cls.transfer_amount),
            func.sum(cls.cash_difference),
            func.sum(cls.new_subscriptions_count),
            func.sum(cls.renewals_count)
        ).filter(
            cls.brand_id == brand_id,
            cls.closing_date >= start_date,
            cls.closing_date <= end_date,
            cls.status.in_(['submitted', 'verified'])
        )
        if branch_id:
            result = result.filter(cls.branch_id == branch_id)

        row = result.first()

        return {
            'total_sales': float(row[0] or 0),
            'cash_amount': float(row[1] or 0),
            'card_amount': float(row[2] or 0),
            'transfer_amount': float(row[3] or 0),
            'total_difference': float(row[4] or 0),
            'new_subscriptions': int(row[5] or 0),
            'renewals': int(row[6] or 0)
        }
