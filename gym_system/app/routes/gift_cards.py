"""Gift Cards routes"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, DateField
from wtforms.validators import DataRequired, Optional
from datetime import datetime, date, timedelta
import secrets

from app import db
from app.models import Brand, GiftCard

gift_cards_bp = Blueprint('gift_cards', __name__, url_prefix='/gift-cards')


class GiftCardForm(FlaskForm):
    """Form for creating gift card"""
    original_amount = DecimalField('المبلغ', validators=[DataRequired()])
    expires_at = DateField('تاريخ الانتهاء', validators=[Optional()])


@gift_cards_bp.route('/')
@login_required
def index():
    """List gift cards"""
    if not (current_user.role and current_user.role.can_manage_gift_cards):
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

    status_filter = request.args.get('status', '')

    query = GiftCard.query.filter_by(brand_id=brand.id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    gift_cards = query.order_by(GiftCard.created_at.desc()).all()

    return render_template('gift_cards/index.html',
                         gift_cards=gift_cards,
                         brand=brand,
                         brands=brands,
                         status_filter=status_filter)


@gift_cards_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new gift card"""
    if not (current_user.role and current_user.role.can_manage_gift_cards):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('gift_cards.index'))

    form = GiftCardForm()

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            flash('يرجى اختيار البراند', 'warning')
            return redirect(url_for('gift_cards.index'))
        brand = Brand.query.get_or_404(brand_id)
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand

    if form.validate_on_submit():
        # Generate unique code
        code = secrets.token_hex(8).upper()
        while GiftCard.query.filter_by(code=code).first():
            code = secrets.token_hex(8).upper()

        gift_card = GiftCard(
            brand_id=brand_id,
            code=code,
            original_amount=form.original_amount.data,
            remaining_amount=form.original_amount.data,
            expires_at=form.expires_at.data,
            created_by=current_user.id
        )
        db.session.add(gift_card)
        db.session.commit()

        flash(f'تم إنشاء كرت الإهداء بنجاح - الكود: {code}', 'success')
        return redirect(url_for('gift_cards.view', gift_card_id=gift_card.id))

    # Default expiry: 1 year from now
    if not form.expires_at.data:
        form.expires_at.data = date.today() + timedelta(days=365)

    return render_template('gift_cards/form.html', form=form, brand=brand)


@gift_cards_bp.route('/<int:gift_card_id>')
@login_required
def view(gift_card_id):
    """View gift card details"""
    gift_card = GiftCard.query.get_or_404(gift_card_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != gift_card.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('gift_cards.index'))

    return render_template('gift_cards/view.html', gift_card=gift_card)


@gift_cards_bp.route('/<int:gift_card_id>/deactivate', methods=['POST'])
@login_required
def deactivate(gift_card_id):
    """Deactivate gift card"""
    if not (current_user.role and current_user.role.can_manage_gift_cards):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('gift_cards.index'))

    gift_card = GiftCard.query.get_or_404(gift_card_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != gift_card.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('gift_cards.index'))

    gift_card.status = 'inactive'
    db.session.commit()
    flash('تم إلغاء تفعيل كرت الإهداء', 'success')

    return redirect(url_for('gift_cards.view', gift_card_id=gift_card.id))


# API for checking gift card
@gift_cards_bp.route('/api/check/<code>')
@login_required
def check_code(code):
    """Check gift card by code"""
    gift_card = GiftCard.query.filter_by(code=code.upper()).first()

    if not gift_card:
        return {'valid': False, 'message': 'كرت غير موجود'}

    if gift_card.status != 'active':
        return {'valid': False, 'message': 'كرت غير نشط'}

    if gift_card.expires_at and gift_card.expires_at < date.today():
        return {'valid': False, 'message': 'كرت منتهي الصلاحية'}

    if float(gift_card.remaining_amount) <= 0:
        return {'valid': False, 'message': 'الرصيد صفر'}

    return {
        'valid': True,
        'id': gift_card.id,
        'remaining_amount': float(gift_card.remaining_amount),
        'expires_at': gift_card.expires_at.strftime('%Y-%m-%d') if gift_card.expires_at else None
    }
