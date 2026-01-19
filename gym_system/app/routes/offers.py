"""Promotional Offers routes"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DecimalField, IntegerField, DateField, BooleanField
from wtforms.validators import DataRequired, Optional, NumberRange
from datetime import datetime, date

from app import db
from app.models import Brand, PromotionalOffer

offers_bp = Blueprint('offers', __name__, url_prefix='/offers')


class OfferForm(FlaskForm):
    """Form for creating/editing promotional offer"""
    name = StringField('اسم العرض', validators=[DataRequired()])
    description = TextAreaField('الوصف', validators=[Optional()])
    discount_type = SelectField('نوع الخصم', choices=[
        ('percentage', 'نسبة مئوية'),
        ('fixed', 'مبلغ ثابت')
    ], validators=[DataRequired()])
    discount_value = DecimalField('قيمة الخصم', validators=[DataRequired()])
    start_date = DateField('تاريخ البداية', validators=[DataRequired()])
    end_date = DateField('تاريخ النهاية', validators=[DataRequired()])
    max_uses = IntegerField('الحد الأقصى للاستخدام', validators=[Optional(), NumberRange(min=0)])
    is_active = BooleanField('العرض نشط', default=True)


@offers_bp.route('/')
@login_required
def index():
    """List promotional offers"""
    if not (current_user.role and current_user.role.can_manage_offers):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        brands = Brand.query.filter_by(is_active=True).all()
        if brand_id:
            brand = Brand.query.get(brand_id)
        else:
            brand = brands[0] if brands else None
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand
        brands = []

    if not brand:
        flash('يرجى اختيار براند', 'warning')
        return redirect(url_for('dashboard.index'))

    offers = PromotionalOffer.query.filter_by(brand_id=brand.id).order_by(
        PromotionalOffer.created_at.desc()
    ).all()

    # Count active offers
    active_count = PromotionalOffer.query.filter_by(
        brand_id=brand.id, is_active=True
    ).filter(
        PromotionalOffer.end_date >= date.today()
    ).count()

    return render_template('offers/index.html',
                         offers=offers,
                         brand=brand,
                         brands=brands,
                         active_count=active_count)


@offers_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new offer"""
    if not (current_user.role and current_user.role.can_manage_offers):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('offers.index'))

    form = OfferForm()

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            flash('يرجى اختيار البراند', 'warning')
            return redirect(url_for('offers.index'))
        brand = Brand.query.get_or_404(brand_id)
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand

    if form.validate_on_submit():
        offer = PromotionalOffer(
            brand_id=brand_id,
            name=form.name.data,
            description=form.description.data,
            discount_type=form.discount_type.data,
            discount_value=form.discount_value.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            max_uses=form.max_uses.data or 0,
            is_active=form.is_active.data
        )
        db.session.add(offer)
        db.session.commit()

        flash('تم إنشاء العرض بنجاح', 'success')
        return redirect(url_for('offers.index'))

    # Default dates
    if not form.start_date.data:
        form.start_date.data = date.today()

    return render_template('offers/form.html', form=form, brand=brand)


@offers_bp.route('/<int:offer_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(offer_id):
    """Edit offer"""
    if not (current_user.role and current_user.role.can_manage_offers):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('offers.index'))

    offer = PromotionalOffer.query.get_or_404(offer_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != offer.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('offers.index'))

    form = OfferForm(obj=offer)

    if form.validate_on_submit():
        offer.name = form.name.data
        offer.description = form.description.data
        offer.discount_type = form.discount_type.data
        offer.discount_value = form.discount_value.data
        offer.start_date = form.start_date.data
        offer.end_date = form.end_date.data
        offer.max_uses = form.max_uses.data or 0
        offer.is_active = form.is_active.data
        db.session.commit()

        flash('تم تحديث العرض بنجاح', 'success')
        return redirect(url_for('offers.index'))

    return render_template('offers/form.html', form=form, offer=offer, brand=offer.brand)


@offers_bp.route('/<int:offer_id>/delete', methods=['POST'])
@login_required
def delete(offer_id):
    """Delete offer"""
    if not (current_user.role and current_user.role.can_manage_offers):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('offers.index'))

    offer = PromotionalOffer.query.get_or_404(offer_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != offer.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('offers.index'))

    # Check if used
    if offer.current_uses > 0:
        flash('لا يمكن حذف العرض - تم استخدامه', 'danger')
        return redirect(url_for('offers.index'))

    db.session.delete(offer)
    db.session.commit()
    flash('تم حذف العرض', 'success')

    return redirect(url_for('offers.index'))


@offers_bp.route('/<int:offer_id>/toggle', methods=['POST'])
@login_required
def toggle(offer_id):
    """Toggle offer active status"""
    if not (current_user.role and current_user.role.can_manage_offers):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('offers.index'))

    offer = PromotionalOffer.query.get_or_404(offer_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != offer.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('offers.index'))

    offer.is_active = not offer.is_active
    db.session.commit()

    status = 'نشط' if offer.is_active else 'متوقف'
    flash(f'تم تغيير حالة العرض إلى {status}', 'success')

    return redirect(url_for('offers.index'))


# API for checking offer
@offers_bp.route('/api/active')
@login_required
def api_active_offers():
    """Get active offers for subscription form"""
    brand_id = current_user.brand_id if not current_user.is_owner else request.args.get('brand_id', type=int)

    offers = PromotionalOffer.query.filter(
        PromotionalOffer.brand_id == brand_id,
        PromotionalOffer.is_active == True,
        PromotionalOffer.start_date <= date.today(),
        PromotionalOffer.end_date >= date.today()
    ).all()

    return [{
        'id': o.id,
        'name': o.name,
        'discount_type': o.discount_type,
        'discount_value': float(o.discount_value),
        'description': o.description
    } for o in offers if o.max_uses == 0 or o.current_uses < o.max_uses]
