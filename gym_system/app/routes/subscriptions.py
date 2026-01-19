from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, TextAreaField, DateField, StringField, BooleanField, IntegerField
from wtforms.validators import DataRequired, Optional
from datetime import date, timedelta, datetime

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.subscription import Plan, Subscription, SubscriptionFreeze, SubscriptionPayment, RenewalRejection
from app.models.finance import Income
from app.models.service import ServiceType
from app.models.offer import PromotionalOffer
from app.models.giftcard import GiftCard
from app.utils.decorators import members_required
from app.utils.helpers import pagination_args

subscriptions_bp = Blueprint('subscriptions', __name__)


class SubscriptionForm(FlaskForm):
    """Subscription form"""
    plan_id = SelectField('الباقة', coerce=int, validators=[DataRequired()])
    service_type_id = SelectField('نوع الخدمة', coerce=int, validators=[Optional()])
    discount = DecimalField('الخصم', default=0, validators=[Optional()])
    offer_id = SelectField('العرض الترويجي', coerce=int, validators=[Optional()])
    gift_card_code = StringField('كود كرت الإهداء', validators=[Optional()])
    payment_method = SelectField('طريقة الدفع', choices=[
        ('cash', 'نقدي'),
        ('card', 'بطاقة'),
        ('transfer', 'تحويل')
    ], default='cash')
    paid_amount = DecimalField('المبلغ المدفوع', validators=[DataRequired()])
    notes = TextAreaField('ملاحظات')


class RenewalForm(FlaskForm):
    """Renewal form"""
    plan_id = SelectField('خطة الاشتراك', coerce=int, validators=[DataRequired()])
    start_date = DateField('تاريخ البدء', default=date.today, validators=[DataRequired()])
    discount = DecimalField('الخصم', default=0, validators=[Optional()])
    payment_method = SelectField('طريقة الدفع', choices=[
        ('cash', 'نقدي'),
        ('card', 'بطاقة'),
        ('transfer', 'تحويل')
    ], default='cash')
    amount_paid = DecimalField('المبلغ المدفوع', validators=[DataRequired()])
    notes = TextAreaField('ملاحظات')


class FreezeForm(FlaskForm):
    """Freeze form"""
    start_date = DateField('تاريخ بداية التجميد', default=date.today, validators=[DataRequired()])
    days = IntegerField('عدد أيام التجميد', validators=[DataRequired()])
    reason = TextAreaField('السبب')


class StopForm(FlaskForm):
    """Stop subscription form"""
    reason = SelectField('سبب الإيقاف', choices=[
        ('price', 'السعر'),
        ('time', 'الوقت'),
        ('service', 'جودة الخدمة'),
        ('personal', 'ظروف شخصية'),
        ('other', 'أخرى')
    ], validators=[DataRequired()])
    details = TextAreaField('تفاصيل إضافية')


class RejectionForm(FlaskForm):
    """Renewal rejection form"""
    reason = SelectField('سبب رفض التجديد', choices=[
        ('price', 'السعر'),
        ('time', 'الوقت'),
        ('service', 'جودة الخدمة'),
        ('personal', 'ظروف شخصية')
    ], validators=[DataRequired()])
    details = TextAreaField('تفاصيل إضافية')


class PaymentForm(FlaskForm):
    """Payment form"""
    amount = DecimalField('المبلغ', validators=[DataRequired()])
    payment_method = SelectField('طريقة الدفع', choices=[
        ('cash', 'نقدي'),
        ('card', 'بطاقة'),
        ('transfer', 'تحويل')
    ], default='cash')
    notes = TextAreaField('ملاحظات')


@subscriptions_bp.route('/')
@login_required
@members_required
def index():
    """List subscriptions"""
    page, per_page = pagination_args(request)
    status = request.args.get('status', '')

    # Base query
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = Subscription.query.filter_by(brand_id=brand_id)
        else:
            query = Subscription.query
    else:
        query = Subscription.query.filter_by(brand_id=current_user.brand_id)

    # Status filter
    if status:
        query = query.filter_by(status=status)

    # Pagination
    subscriptions = query.order_by(Subscription.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('subscriptions/index.html',
                          subscriptions=subscriptions,
                          brands=brands,
                          status=status)


@subscriptions_bp.route('/create', methods=['GET', 'POST'])
@login_required
@members_required
def create():
    """Create new subscription"""
    member_id = request.args.get('member_id', type=int)
    if not member_id:
        flash('يرجى اختيار العضو أولاً', 'warning')
        return redirect(url_for('members.index'))

    member = Member.query.get_or_404(member_id)

    if not current_user.can_access_brand(member.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('members.index'))

    # Check for existing active subscription
    if member.has_active_subscription:
        flash('العضو لديه اشتراك نشط بالفعل', 'warning')
        return redirect(url_for('members.view', member_id=member_id))

    form = SubscriptionForm()

    # Get plans for this brand
    plans = Plan.query.filter_by(brand_id=member.brand_id, is_active=True).all()
    form.plan_id.choices = [(p.id, f'{p.name} - {p.price} ر.س ({p.duration_text})') for p in plans]

    # Get service types for this brand
    service_types = ServiceType.query.filter_by(brand_id=member.brand_id, is_active=True).all()
    form.service_type_id.choices = [(0, '-- بدون تحديد --')] + [(st.id, st.name) for st in service_types]

    # Get active offers for this brand
    today = date.today()
    offers = PromotionalOffer.query.filter(
        PromotionalOffer.brand_id == member.brand_id,
        PromotionalOffer.is_active == True,
        PromotionalOffer.start_date <= today,
        PromotionalOffer.end_date >= today
    ).all()
    form.offer_id.choices = [(0, '-- بدون عرض --')] + [(o.id, f'{o.name} ({o.discount_display})') for o in offers]

    if form.validate_on_submit():
        plan = Plan.query.get(form.plan_id.data)

        # Calculate amounts
        discount = float(form.discount.data or 0)
        offer_discount = 0
        gift_card_amount = 0
        offer = None
        gift_card = None

        # Apply promotional offer
        if form.offer_id.data and form.offer_id.data != 0:
            offer = PromotionalOffer.query.get(form.offer_id.data)
            if offer and offer.can_use:
                if offer.discount_type == 'percentage':
                    offer_discount = float(plan.price) * (float(offer.discount_value) / 100)
                else:
                    offer_discount = float(offer.discount_value)
                offer.current_uses += 1

        # Apply gift card
        if form.gift_card_code.data:
            gift_card = GiftCard.query.filter_by(
                brand_id=member.brand_id,
                code=form.gift_card_code.data.strip().upper(),
                status='active'
            ).first()
            if gift_card and gift_card.remaining_amount > 0:
                gift_card_amount = min(float(gift_card.remaining_amount), float(plan.price) - discount - offer_discount)
                gift_card.remaining_amount = float(gift_card.remaining_amount) - gift_card_amount
                if gift_card.remaining_amount <= 0:
                    gift_card.status = 'redeemed'
                    gift_card.redeemed_at = datetime.utcnow()
                    gift_card.redeemed_by_member_id = member.id

        total_amount = float(plan.price) - discount - offer_discount - gift_card_amount
        paid_amount = float(form.paid_amount.data)
        remaining_amount = max(0, total_amount - paid_amount)

        # Calculate dates
        start_date = date.today()
        end_date = start_date + timedelta(days=plan.duration_days)

        # Create subscription
        subscription = Subscription(
            member_id=member.id,
            plan_id=plan.id,
            brand_id=member.brand_id,
            service_type_id=form.service_type_id.data if form.service_type_id.data else None,
            start_date=start_date,
            end_date=end_date,
            original_end_date=end_date,
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_amount=remaining_amount,
            discount=discount,
            offer_id=offer.id if offer else None,
            offer_discount=offer_discount,
            gift_card_id=gift_card.id if gift_card else None,
            status='active',
            notes=form.notes.data,
            created_by=current_user.id
        )
        db.session.add(subscription)
        db.session.flush()

        # Create payment record
        if paid_amount > 0:
            payment = SubscriptionPayment(
                subscription_id=subscription.id,
                brand_id=member.brand_id,
                amount=paid_amount,
                payment_method=form.payment_method.data,
                created_by=current_user.id
            )
            db.session.add(payment)

            # Create income record
            income = Income(
                brand_id=member.brand_id,
                subscription_id=subscription.id,
                amount=paid_amount,
                type='subscription',
                payment_method=form.payment_method.data,
                date=date.today(),
                created_by=current_user.id
            )
            db.session.add(income)

        db.session.commit()

        flash('تم إنشاء الاشتراك بنجاح', 'success')
        if offer:
            flash(f'تم تطبيق العرض: {offer.name}', 'info')
        if gift_card:
            flash(f'تم خصم {gift_card_amount:.0f} ر.س من كرت الإهداء', 'info')

        # Show fingerprint enrollment reminder
        if member.needs_fingerprint_enrollment:
            flash(f'تذكير: يرجى تسجيل بصمة العضو (رقم البصمة: {member.fingerprint_id})', 'warning')

        return redirect(url_for('members.view', member_id=member_id))

    return render_template('subscriptions/create.html', form=form, member=member, plans=plans, offers=offers)


@subscriptions_bp.route('/<int:subscription_id>')
@login_required
@members_required
def view(subscription_id):
    """View subscription details"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not current_user.can_access_brand(subscription.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    # Update status if needed
    subscription.check_and_update_status()

    return render_template('subscriptions/view.html', subscription=subscription)


@subscriptions_bp.route('/<int:subscription_id>/renew', methods=['GET', 'POST'])
@login_required
@members_required
def renew(subscription_id):
    """Renew subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not current_user.can_access_brand(subscription.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    # Get plans for this brand
    plans = Plan.query.filter_by(brand_id=subscription.brand_id, is_active=True).all()

    form = RenewalForm()
    form.plan_id.choices = [(p.id, f"{p.name} - {p.price} ر.س ({p.duration_days} يوم)") for p in plans]

    # Set default values
    if request.method == 'GET':
        form.plan_id.data = subscription.plan_id
        # Default start date is end of current subscription or today
        if subscription.end_date >= date.today():
            form.start_date.data = subscription.end_date
        else:
            form.start_date.data = date.today()
        form.amount_paid.data = subscription.plan.price

    if form.validate_on_submit():
        plan = Plan.query.get(form.plan_id.data)
        paid_amount = float(form.amount_paid.data)
        discount = float(form.discount.data or 0)
        new_start = form.start_date.data
        new_end = new_start + timedelta(days=plan.duration_days)

        # Update subscription
        subscription.plan_id = plan.id
        subscription.start_date = new_start
        subscription.end_date = new_end
        subscription.original_end_date = new_end
        subscription.total_amount = float(subscription.total_amount or 0) + float(plan.price)
        subscription.paid_amount = float(subscription.paid_amount or 0) + paid_amount
        subscription.remaining_amount = float(subscription.total_amount) - float(subscription.paid_amount)
        subscription.status = 'active'

        # Create payment record
        if paid_amount > 0:
            payment = SubscriptionPayment(
                subscription_id=subscription.id,
                brand_id=subscription.brand_id,
                amount=paid_amount,
                payment_method=form.payment_method.data,
                notes=form.notes.data,
                created_by=current_user.id
            )
            db.session.add(payment)

            # Create income record
            income = Income(
                brand_id=subscription.brand_id,
                subscription_id=subscription.id,
                amount=paid_amount,
                payment_method=form.payment_method.data,
                type='renewal',
                date=date.today(),
                created_by=current_user.id
            )
            db.session.add(income)

        db.session.commit()

        flash('تم تجديد الاشتراك بنجاح', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    return render_template('subscriptions/renew.html', form=form, subscription=subscription, plans=plans)


@subscriptions_bp.route('/<int:subscription_id>/freeze', methods=['GET', 'POST'])
@login_required
@members_required
def freeze(subscription_id):
    """Freeze subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not current_user.can_access_brand(subscription.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    if not subscription.can_freeze:
        flash('لا يمكن تجميد هذا الاشتراك', 'danger')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    form = FreezeForm()

    if form.validate_on_submit():
        freeze_start = form.start_date.data
        freeze_days = form.days.data
        freeze_end = freeze_start + timedelta(days=freeze_days)

        # Validate days
        remaining_days = subscription.plan.max_freeze_days - subscription.total_freeze_days
        if freeze_days > remaining_days:
            flash(f'الحد الأقصى للتجميد المتبقي {remaining_days} يوم', 'danger')
            return render_template('subscriptions/freeze.html', form=form, subscription=subscription)

        # Create freeze record
        freeze_record = SubscriptionFreeze(
            subscription_id=subscription_id,
            freeze_start=freeze_start,
            freeze_end=freeze_end,
            freeze_days=freeze_days,
            reason=form.reason.data,
            created_by=current_user.id
        )
        db.session.add(freeze_record)

        # Update subscription
        subscription.end_date = subscription.end_date + timedelta(days=freeze_days)
        subscription.status = 'frozen'

        db.session.commit()

        flash('تم تجميد الاشتراك بنجاح', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    return render_template('subscriptions/freeze.html', form=form, subscription=subscription)


@subscriptions_bp.route('/<int:subscription_id>/unfreeze', methods=['POST'])
@login_required
@members_required
def unfreeze(subscription_id):
    """Unfreeze subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not current_user.can_access_brand(subscription.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    if subscription.status != 'frozen':
        flash('الاشتراك غير مجمد', 'warning')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    subscription.status = 'active'
    db.session.commit()

    flash('تم إلغاء تجميد الاشتراك', 'success')
    return redirect(url_for('subscriptions.view', subscription_id=subscription_id))


@subscriptions_bp.route('/<int:subscription_id>/payment', methods=['GET', 'POST'])
@login_required
@members_required
def add_payment(subscription_id):
    """Add payment to subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not current_user.can_access_brand(subscription.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    form = PaymentForm()

    if form.validate_on_submit():
        amount = float(form.amount.data)

        # Create payment
        payment = SubscriptionPayment(
            subscription_id=subscription.id,
            brand_id=subscription.brand_id,
            amount=amount,
            payment_method='cash',
            notes=form.notes.data,
            created_by=current_user.id
        )
        db.session.add(payment)

        # Update subscription
        subscription.paid_amount = float(subscription.paid_amount) + amount
        subscription.remaining_amount = float(subscription.total_amount) - float(subscription.paid_amount)

        # Create income
        income = Income(
            brand_id=subscription.brand_id,
            subscription_id=subscription.id,
            amount=amount,
            type='subscription',
            description='سداد دفعة',
            date=date.today(),
            created_by=current_user.id
        )
        db.session.add(income)

        db.session.commit()

        flash('تم تسجيل الدفعة بنجاح', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    return render_template('subscriptions/payment.html', form=form, subscription=subscription)


@subscriptions_bp.route('/expiring')
@login_required
@members_required
def expiring():
    """List expiring subscriptions"""
    page, per_page = pagination_args(request)
    days = request.args.get('days', 7, type=int)
    today = date.today()
    end_date = today + timedelta(days=days)

    # Base query
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = Subscription.query.filter_by(brand_id=brand_id)
        else:
            query = Subscription.query
    else:
        query = Subscription.query.filter_by(brand_id=current_user.brand_id)

    # Filter expiring subscriptions
    query = query.filter(
        Subscription.status == 'active',
        Subscription.end_date >= today,
        Subscription.end_date <= end_date
    ).order_by(Subscription.end_date)

    subscriptions = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('subscriptions/expiring.html',
                          subscriptions=subscriptions,
                          brands=brands,
                          days=days)


@subscriptions_bp.route('/<int:subscription_id>/stop', methods=['GET', 'POST'])
@login_required
@members_required
def stop(subscription_id):
    """Stop subscription with reason"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not current_user.can_access_brand(subscription.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    if subscription.status not in ['active', 'frozen']:
        flash('لا يمكن إيقاف هذا الاشتراك', 'warning')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    form = StopForm()

    if form.validate_on_submit():
        subscription.status = 'stopped'
        subscription.stop_reason = f"{form.reason.data}: {form.details.data}" if form.details.data else form.reason.data
        subscription.stopped_at = datetime.utcnow()
        subscription.stopped_by = current_user.id

        db.session.commit()

        flash('تم إيقاف الاشتراك', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    return render_template('subscriptions/stop.html', form=form, subscription=subscription)


@subscriptions_bp.route('/<int:subscription_id>/reject-renewal', methods=['GET', 'POST'])
@login_required
@members_required
def reject_renewal(subscription_id):
    """Record renewal rejection"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not current_user.can_access_brand(subscription.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    form = RejectionForm()

    if form.validate_on_submit():
        rejection = RenewalRejection(
            member_id=subscription.member_id,
            subscription_id=subscription.id,
            reason=form.reason.data,
            details=form.details.data,
            created_by=current_user.id
        )
        db.session.add(rejection)
        db.session.commit()

        flash('تم تسجيل رفض التجديد', 'info')
        return redirect(url_for('members.view', member_id=subscription.member_id))

    return render_template('subscriptions/reject_renewal.html', form=form, subscription=subscription)
