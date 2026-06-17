"""GYM-23: walk-in / day-pass tickets.

DayPassPrice — owner-managed catalogue: how much each activity costs as a
single-day visit. One row per (brand, service_type).

DayPass — one ticket issued by the receptionist for a walk-in. Independent
of the fingerprint system; just a manual record + a price snapshot. Auto-posts
an Income row at creation so revenue rolls up into finance.
"""
from datetime import datetime, date
from app import db


class DayPassPrice(db.Model):
    __tablename__ = 'day_pass_prices'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_types.id'), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    service_type = db.relationship('ServiceType')

    __table_args__ = (
        db.UniqueConstraint('brand_id', 'service_type_id', name='uq_day_pass_price'),
    )

    def __repr__(self):
        return f'<DayPassPrice brand={self.brand_id} svc={self.service_type_id} {self.price}>'


class DayPass(db.Model):
    __tablename__ = 'day_passes'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_types.id'), nullable=False)

    # Walk-in customer (not a registered member)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_phone = db.Column(db.String(40))
    customer_age = db.Column(db.Integer)

    # When the pass is valid
    pass_date = db.Column(db.Date, nullable=False, default=date.today)
    valid_from = db.Column(db.Time)
    valid_until = db.Column(db.Time)

    # Money
    price = db.Column(db.Numeric(10, 2), nullable=False)  # snapshot at issue time
    # GYM-33 — receptionist-applied discount in ر.س. Stored separately so we
    # can show both "السعر الأصلي" and "بعد الخصم" on the printable ticket.
    discount = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    payment_method = db.Column(db.String(20), default='cash')

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    service_type = db.relationship('ServiceType')
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<DayPass {self.id} {self.customer_name} {self.pass_date}>'

    @property
    def time_range_text(self):
        if not (self.valid_from and self.valid_until):
            return '—'
        return f"{self.valid_from.strftime('%H:%M')} → {self.valid_until.strftime('%H:%M')}"
