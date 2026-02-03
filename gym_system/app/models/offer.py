from datetime import datetime, date
from app import db
from decimal import Decimal


class PromotionalOffer(db.Model):
    """Promotional offers/campaigns (العروض)"""
    __tablename__ = 'promotional_offers'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    # Offer info
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    code = db.Column(db.String(20))  # Optional promo code

    # Discount type: 'percentage' or 'fixed_amount'
    discount_type = db.Column(db.String(20), nullable=False)
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)

    # Validity
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    # Usage limits
    max_uses = db.Column(db.Integer)  # NULL = unlimited
    current_uses = db.Column(db.Integer, default=0)

    # Restrictions
    min_subscription_amount = db.Column(db.Numeric(10, 2))  # Minimum purchase
    applicable_service_type_id = db.Column(db.Integer, db.ForeignKey('service_types.id'))  # Specific service only
    applicable_plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'))  # Specific plan only

    # Status
    is_active = db.Column(db.Boolean, default=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    applicable_service_type = db.relationship('ServiceType', backref='offers')
    applicable_plan = db.relationship('Plan', backref='offers')

    def __repr__(self):
        return f'<PromotionalOffer {self.name}>'

    @property
    def is_valid(self):
        """Check if offer is currently valid"""
        if not self.is_active:
            return False
        today = date.today()
        if today < self.start_date or today > self.end_date:
            return False
        if self.max_uses and self.current_uses >= self.max_uses:
            return False
        return True

    @property
    def status(self):
        """Get offer status"""
        if not self.is_active:
            return 'inactive'
        today = date.today()
        if today < self.start_date:
            return 'upcoming'
        if today > self.end_date:
            return 'expired'
        if self.max_uses and self.current_uses >= self.max_uses:
            return 'exhausted'
        return 'active'

    @property
    def status_arabic(self):
        """Get status in Arabic"""
        status_map = {
            'active': 'نشط',
            'inactive': 'غير نشط',
            'upcoming': 'قادم',
            'expired': 'منتهي',
            'exhausted': 'مستنفد'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """Get CSS class for status"""
        status_classes = {
            'active': 'success',
            'inactive': 'secondary',
            'upcoming': 'info',
            'expired': 'warning',
            'exhausted': 'danger'
        }
        return status_classes.get(self.status, 'secondary')

    @property
    def discount_display(self):
        """Get discount display text"""
        if self.discount_type == 'percentage':
            return f'{self.discount_value}%'
        return f'{self.discount_value} ر.س'

    @property
    def remaining_uses(self):
        """Get remaining uses"""
        if not self.max_uses:
            return None  # Unlimited
        return max(0, self.max_uses - self.current_uses)

    def calculate_discount(self, original_amount):
        """
        Calculate the discount amount for a given original price
        Returns the discount amount (not the final price)
        """
        original = Decimal(str(original_amount))

        if self.min_subscription_amount and original < self.min_subscription_amount:
            return Decimal('0')

        if self.discount_type == 'percentage':
            discount = original * (self.discount_value / 100)
        else:  # fixed_amount
            discount = min(self.discount_value, original)

        return discount.quantize(Decimal('0.01'))

    def can_apply(self, subscription_amount, service_type_id=None, plan_id=None):
        """
        Check if offer can be applied to a subscription
        Returns (can_apply, message)
        """
        if not self.is_valid:
            return False, 'العرض غير صالح حالياً'

        # Check minimum amount
        if self.min_subscription_amount and subscription_amount < float(self.min_subscription_amount):
            return False, f'الحد الأدنى للعرض هو {self.min_subscription_amount} ر.س'

        # Check service type restriction
        if self.applicable_service_type_id and service_type_id != self.applicable_service_type_id:
            return False, 'العرض خاص بنوع خدمة محدد'

        # Check plan restriction
        if self.applicable_plan_id and plan_id != self.applicable_plan_id:
            return False, 'العرض خاص بباقة محددة'

        return True, 'يمكن تطبيق العرض'

    def apply(self):
        """Increment usage count when offer is applied"""
        self.current_uses += 1
        db.session.commit()

    @classmethod
    def get_active_offers(cls, brand_id, service_type_id=None, plan_id=None):
        """Get all currently active offers"""
        today = date.today()
        query = cls.query.filter(
            cls.brand_id == brand_id,
            cls.is_active == True,
            cls.start_date <= today,
            cls.end_date >= today
        ).filter(
            db.or_(cls.max_uses == None, cls.current_uses < cls.max_uses)
        )

        # Filter by service type if specified
        if service_type_id:
            query = query.filter(
                db.or_(
                    cls.applicable_service_type_id == None,
                    cls.applicable_service_type_id == service_type_id
                )
            )

        # Filter by plan if specified
        if plan_id:
            query = query.filter(
                db.or_(
                    cls.applicable_plan_id == None,
                    cls.applicable_plan_id == plan_id
                )
            )

        return query.all()

    @classmethod
    def get_by_code(cls, code, brand_id):
        """Get offer by promo code"""
        return cls.query.filter_by(
            code=code.upper(),
            brand_id=brand_id
        ).first()

    @classmethod
    def get_offer_stats(cls, offer_id):
        """Get statistics for a specific offer"""
        from .subscription import Subscription

        offer = cls.query.get(offer_id)
        if not offer:
            return None

        # Get subscriptions using this offer
        subs_with_offer = Subscription.query.filter_by(offer_id=offer_id)

        total_uses = subs_with_offer.count()
        total_discount_given = sum(float(s.offer_discount or 0) for s in subs_with_offer)
        total_revenue = sum(float(s.paid_amount or 0) for s in subs_with_offer)

        return {
            'offer': offer,
            'total_uses': total_uses,
            'total_discount_given': total_discount_given,
            'total_revenue': total_revenue,
            'average_discount': total_discount_given / total_uses if total_uses > 0 else 0
        }

    @classmethod
    def get_effectiveness_report(cls, brand_id, start_date=None, end_date=None):
        """Get effectiveness report for all offers"""
        from .subscription import Subscription
        from sqlalchemy import func

        query = cls.query.filter_by(brand_id=brand_id)

        if start_date:
            query = query.filter(cls.start_date >= start_date)
        if end_date:
            query = query.filter(cls.end_date <= end_date)

        offers = query.all()
        report = []

        for offer in offers:
            stats = cls.get_offer_stats(offer.id)
            if stats:
                report.append(stats)

        return report
