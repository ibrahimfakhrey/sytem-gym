from datetime import datetime, date
from app import db


class ExpenseCategory(db.Model):
    """Expense categories"""
    __tablename__ = 'expense_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=True)

    # Relationships
    expenses = db.relationship('Expense', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'

    @staticmethod
    def get_default_categories():
        """Get default expense categories"""
        return [
            ('salaries', 'رواتب'),
            ('rent', 'إيجار'),
            ('electricity', 'كهرباء'),
            ('water', 'ماء'),
            ('maintenance', 'صيانة'),
            ('equipment', 'معدات'),
            ('marketing', 'تسويق'),
            ('supplies', 'مستلزمات'),
            ('other', 'أخرى'),
        ]


class Income(db.Model):
    """Income records"""
    __tablename__ = 'income'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('subscription_payments.id'), nullable=True)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_types.id'), nullable=True)

    amount = db.Column(db.Numeric(10, 2), nullable=False)

    # Type: 'subscription', 'renewal', 'freeze_fee', 'gift_card', 'other'
    type = db.Column(db.String(30), nullable=False)

    # Payment method: 'cash', 'card', 'transfer'
    payment_method = db.Column(db.String(20), default='cash')

    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    service_type = db.relationship('ServiceType', backref='income_records')

    def __repr__(self):
        return f'<Income {self.amount} - {self.type}>'

    @property
    def type_text(self):
        """Type in Arabic"""
        type_map = {
            'subscription': 'اشتراك',
            'renewal': 'تجديد',
            'freeze_fee': 'رسوم تجميد',
            'gift_card': 'كرت إهداء',
            'other': 'أخرى'
        }
        return type_map.get(self.type, self.type)

    @property
    def payment_method_text(self):
        """Payment method in Arabic"""
        method_map = {
            'cash': 'نقدي',
            'card': 'شبكة',
            'transfer': 'حوالة'
        }
        return method_map.get(self.payment_method, self.payment_method)

    @classmethod
    def get_by_payment_method(cls, brand_id, start_date, end_date):
        """Get income grouped by payment method"""
        from sqlalchemy import func
        return db.session.query(
            cls.payment_method,
            func.sum(cls.amount).label('total')
        ).filter(
            cls.brand_id == brand_id,
            cls.date >= start_date,
            cls.date <= end_date
        ).group_by(cls.payment_method).all()

    @classmethod
    def get_total_for_period(cls, brand_id, start_date, end_date):
        """Get total income for period"""
        result = db.session.query(db.func.sum(cls.amount)).filter(
            cls.brand_id == brand_id,
            cls.date >= start_date,
            cls.date <= end_date
        ).scalar()
        return float(result) if result else 0.0


class Expense(db.Model):
    """Expense records"""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=True)

    category_name = db.Column(db.String(50), nullable=False)  # Store category name directly too
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text)

    date = db.Column(db.Date, nullable=False, default=date.today)
    receipt_image = db.Column(db.String(255))

    # Approval workflow
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_expenses')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_expenses')

    def __repr__(self):
        return f'<Expense {self.amount} - {self.category_name}>'

    @property
    def status_text(self):
        """Status in Arabic"""
        status_map = {
            'pending': 'قيد الانتظار',
            'approved': 'معتمد',
            'rejected': 'مرفوض'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """CSS class for status"""
        class_map = {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger'
        }
        return class_map.get(self.status, 'secondary')

    def approve(self, user_id):
        """Approve the expense"""
        self.status = 'approved'
        self.approved_by = user_id
        self.approved_at = datetime.utcnow()
        db.session.commit()

    def reject(self, user_id, reason):
        """Reject the expense"""
        self.status = 'rejected'
        self.approved_by = user_id
        self.approved_at = datetime.utcnow()
        self.rejection_reason = reason
        db.session.commit()

    @classmethod
    def get_pending_approvals(cls, brand_id=None):
        """Get all expenses pending approval"""
        query = cls.query.filter_by(status='pending')
        if brand_id:
            query = query.filter_by(brand_id=brand_id)
        return query.order_by(cls.date.desc()).all()

    @classmethod
    def get_total_for_period(cls, brand_id, start_date, end_date):
        """Get total expenses for period"""
        result = db.session.query(db.func.sum(cls.amount)).filter(
            cls.brand_id == brand_id,
            cls.date >= start_date,
            cls.date <= end_date
        ).scalar()
        return float(result) if result else 0.0

    @classmethod
    def get_by_category(cls, brand_id, start_date, end_date):
        """Get expenses grouped by category"""
        return db.session.query(
            cls.category_name,
            db.func.sum(cls.amount).label('total')
        ).filter(
            cls.brand_id == brand_id,
            cls.date >= start_date,
            cls.date <= end_date
        ).group_by(cls.category_name).all()


class Salary(db.Model):
    """Salary records"""
    __tablename__ = 'salaries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)

    base_salary = db.Column(db.Numeric(10, 2), nullable=False)
    deductions = db.Column(db.Numeric(10, 2), default=0)
    bonuses = db.Column(db.Numeric(10, 2), default=0)
    net_salary = db.Column(db.Numeric(10, 2), nullable=False)

    days_worked = db.Column(db.Integer)

    # Status: 'pending', 'approved', 'paid'
    status = db.Column(db.String(20), default='pending')

    paid_date = db.Column(db.Date)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'month', 'year', name='unique_salary'),
    )

    def __repr__(self):
        return f'<Salary {self.user_id} - {self.month}/{self.year}>'

    @property
    def status_text(self):
        """Status in Arabic"""
        status_map = {
            'pending': 'معلق',
            'approved': 'معتمد',
            'paid': 'مدفوع'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """CSS class for status"""
        class_map = {
            'pending': 'warning',
            'approved': 'info',
            'paid': 'success'
        }
        return class_map.get(self.status, 'secondary')

    @property
    def month_name(self):
        """Month name in Arabic"""
        months = {
            1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
            5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
            9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
        }
        return months.get(self.month, str(self.month))


class Refund(db.Model):
    """Refund records"""
    __tablename__ = 'refunds'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.Text, nullable=False)

    refund_date = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    subscription = db.relationship('Subscription', backref='refunds')
    member = db.relationship('Member', backref='refunds')

    def __repr__(self):
        return f'<Refund {self.amount}>'
