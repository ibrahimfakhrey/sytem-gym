from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, TextAreaField, DateField
from wtforms.validators import DataRequired, Optional
from datetime import date, timedelta, datetime

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.subscription import Plan, Subscription, SubscriptionFreeze, SubscriptionPayment, ServiceType
from app.models.complaint import SubscriptionSuspension
from app.models.finance import Income, Invoice
from app.utils.decorators import members_required
from app.utils.helpers import pagination_args

subscriptions_bp = Blueprint('subscriptions', __name__)


class SubscriptionForm(FlaskForm):
    """Subscription form"""
    service_type_id = SelectField('نوع الخدمة', coerce=int, validators=[DataRequired()])
    plan_id = SelectField('الباقة', coerce=int, validators=[DataRequired()])
    discount = DecimalField('الخصم', default=0, validators=[Optional()])
    paid_amount = DecimalField('المبلغ المدفوع', validators=[DataRequired()])
    payment_method = SelectField('طريقة الدفع', choices=[('cash', 'نقدي'), ('card', 'بطاقة'), ('transfer', 'تحويل')], validators=[DataRequired()])
    notes = TextAreaField('ملاحظات')


class RenewalForm(FlaskForm):
    """Renewal form"""
    paid_amount = DecimalField('المبلغ المدفوع', validators=[DataRequired()])
    payment_method = SelectField('طريقة الدفع', choices=[('cash', 'نقدي'), ('card', 'بطاقة'), ('transfer', 'تحويل')], validators=[DataRequired()])
    notes = TextAreaField('ملاحظات')


class FreezeForm(FlaskForm):
    """Freeze form"""
    freeze_start = DateField('تاريخ بداية التجميد', validators=[DataRequired()])
    freeze_end = DateField('تاريخ نهاية التجميد', validators=[DataRequired()])
    reason = TextAreaField('السبب')


class PaymentForm(FlaskForm):
    """Payment form"""
    amount = DecimalField('المبلغ', validators=[DataRequired()])
    payment_method = SelectField('طريقة الدفع', choices=[('cash', 'نقدي'), ('card', 'بطاقة'), ('transfer', 'تحويل')], validators=[DataRequired()])
    notes = TextAreaField('ملاحظات')


class SuspendForm(FlaskForm):
    """Suspend subscription form"""
    reason_category = SelectField('سبب الإيقاف', choices=[
        ('price', 'سعر'),
        ('time', 'وقت'),
        ('service', 'خدمة'),
        ('personal', 'سبب شخصي'),
        ('other', 'أخرى')
    ], validators=[DataRequired()])
    reason_details = TextAreaField('تفاصيل السبب')


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

    # Get service types for this brand
    service_types = ServiceType.query.filter_by(brand_id=member.brand_id, is_active=True).all()
    form.service_type_id.choices = [(st.id, st.name) for st in service_types]

    # Get selected service type from form or first service type
    selected_service_type = request.form.get('service_type_id', type=int)
    if not selected_service_type and service_types:
        selected_service_type = service_types[0].id

    # Filter plans by service type
    if selected_service_type:
        plans = Plan.query.filter_by(
            brand_id=member.brand_id,
            service_type_id=selected_service_type,
            is_active=True
        ).all()
    else:
        plans = []

    form.plan_id.choices = [(p.id, f'{p.name} - {p.price} ر.س ({p.plan_type_text})') for p in plans]

    if form.validate_on_submit():
        plan = Plan.query.get(form.plan_id.data)

        # Calculate amounts
        discount = float(form.discount.data or 0)
        total_amount = float(plan.price) - discount
        paid_amount = float(form.paid_amount.data)
        remaining_amount = total_amount - paid_amount

        # Calculate dates
        start_date = date.today()
        end_date = start_date + timedelta(days=plan.duration_days)

        # Create subscription
        subscription = Subscription(
            member_id=member.id,
            plan_id=plan.id,
            brand_id=member.brand_id,
            service_type_id=form.service_type_id.data,
            start_date=start_date,
            end_date=end_date,
            original_end_date=end_date,
            sessions_total=plan.sessions_count,  # Copy from plan
            sessions_consumed=0,
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_amount=remaining_amount,
            discount=discount,
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
            db.session.flush()  # Get payment ID

            # Create income record
            income = Income(
                brand_id=member.brand_id,
                subscription_id=subscription.id,
                amount=paid_amount,
                type='subscription',
                date=date.today(),
                created_by=current_user.id
            )
            db.session.add(income)

            # Generate invoice
            service_type_name = None
            if subscription.service_type:
                service_type_name = subscription.service_type.name

            invoice = Invoice(
                brand_id=member.brand_id,
                subscription_id=subscription.id,
                payment_id=payment.id,
                member_id=member.id,
                invoice_number=Invoice.generate_invoice_number(member.brand_id),
                member_name=member.name,
                member_phone=member.phone,
                member_email=member.email,
                plan_name=plan.name,
                service_type_name=service_type_name,
                duration_text=plan.plan_type_text,
                original_price=plan.price,
                discount=discount,
                subtotal=total_amount,
                tax_rate=0,  # Can be configured later
                tax_amount=0,
                total_amount=total_amount,
                amount_paid=paid_amount,
                payment_method=form.payment_method.data,
                notes=form.notes.data,
                created_by=current_user.id
            )
            db.session.add(invoice)

        db.session.commit()

        flash('تم إنشاء الاشتراك بنجاح', 'success')

        # Show fingerprint enrollment reminder
        if member.needs_fingerprint_enrollment:
            flash(f'تذكير: يرجى تسجيل بصمة العضو (رقم البصمة: {member.fingerprint_id})', 'warning')

        return redirect(url_for('members.view', member_id=member_id))

    return render_template('subscriptions/create.html', form=form, member=member,
                          plans=plans, service_types=service_types,
                          selected_service_type=selected_service_type)


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

    form = RenewalForm()
    plan = subscription.plan

    if form.validate_on_submit():
        paid_amount = float(form.paid_amount.data)

        # Calculate new dates
        if subscription.end_date >= date.today():
            new_start = subscription.end_date
        else:
            new_start = date.today()

        new_end = new_start + timedelta(days=plan.duration_days)

        # Update subscription
        subscription.start_date = new_start
        subscription.end_date = new_end
        subscription.original_end_date = new_end
        subscription.total_amount = float(subscription.total_amount) + float(plan.price)
        subscription.paid_amount = float(subscription.paid_amount) + paid_amount
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
            db.session.flush()  # Get payment ID

            # Create income record
            income = Income(
                brand_id=subscription.brand_id,
                subscription_id=subscription.id,
                amount=paid_amount,
                type='renewal',
                date=date.today(),
                created_by=current_user.id
            )
            db.session.add(income)

            # Generate invoice for renewal
            service_type_name = None
            if subscription.service_type:
                service_type_name = subscription.service_type.name

            invoice = Invoice(
                brand_id=subscription.brand_id,
                subscription_id=subscription.id,
                payment_id=payment.id,
                member_id=subscription.member_id,
                invoice_number=Invoice.generate_invoice_number(subscription.brand_id),
                member_name=subscription.member.name,
                member_phone=subscription.member.phone,
                member_email=subscription.member.email,
                plan_name=plan.name,
                service_type_name=service_type_name,
                duration_text=plan.plan_type_text,
                original_price=plan.price,
                discount=0,
                subtotal=plan.price,
                tax_rate=0,
                tax_amount=0,
                total_amount=plan.price,
                amount_paid=paid_amount,
                payment_method=form.payment_method.data,
                notes=form.notes.data,
                created_by=current_user.id
            )
            db.session.add(invoice)

        db.session.commit()

        flash('تم تجديد الاشتراك بنجاح', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    return render_template('subscriptions/renew.html', form=form, subscription=subscription)


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
        freeze_start = form.freeze_start.data
        freeze_end = form.freeze_end.data

        # Validate dates
        if freeze_end <= freeze_start:
            flash('تاريخ النهاية يجب أن يكون بعد تاريخ البداية', 'danger')
            return render_template('subscriptions/freeze.html', form=form, subscription=subscription)

        freeze_days = (freeze_end - freeze_start).days

        if freeze_days > subscription.plan.max_freeze_days:
            flash(f'الحد الأقصى للتجميد {subscription.plan.max_freeze_days} يوم', 'danger')
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
            payment_method=form.payment_method.data,
            notes=form.notes.data,
            created_by=current_user.id
        )
        db.session.add(payment)
        db.session.flush()  # Get payment ID

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

        # Generate invoice for payment
        service_type_name = None
        if subscription.service_type:
            service_type_name = subscription.service_type.name

        invoice = Invoice(
            brand_id=subscription.brand_id,
            subscription_id=subscription.id,
            payment_id=payment.id,
            member_id=subscription.member_id,
            invoice_number=Invoice.generate_invoice_number(subscription.brand_id),
            member_name=subscription.member.name,
            member_phone=subscription.member.phone,
            member_email=subscription.member.email,
            plan_name=subscription.plan.name,
            service_type_name=service_type_name,
            duration_text='سداد دفعة',
            original_price=amount,
            discount=0,
            subtotal=amount,
            tax_rate=0,
            tax_amount=0,
            total_amount=amount,
            amount_paid=amount,
            payment_method=form.payment_method.data,
            notes=form.notes.data,
            created_by=current_user.id
        )
        db.session.add(invoice)

        db.session.commit()

        flash('تم تسجيل الدفعة بنجاح', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    return render_template('subscriptions/payment.html', form=form, subscription=subscription)


@subscriptions_bp.route('/<int:subscription_id>/suspend', methods=['GET', 'POST'])
@login_required
@members_required
def suspend(subscription_id):
    """Suspend subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not current_user.can_access_brand(subscription.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    if subscription.status in ['suspended', 'expired', 'cancelled']:
        flash('لا يمكن إيقاف هذا الاشتراك', 'warning')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    form = SuspendForm()

    if form.validate_on_submit():
        # Create suspension record
        suspension = SubscriptionSuspension(
            subscription_id=subscription.id,
            brand_id=subscription.brand_id,
            reason_type=form.reason_category.data,
            reason_details=form.reason_details.data,
            stopped_by=current_user.id
        )
        db.session.add(suspension)

        # Update subscription status
        subscription.status = 'suspended'

        db.session.commit()

        flash('تم إيقاف الاشتراك بنجاح', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    return render_template('subscriptions/suspend.html', form=form, subscription=subscription)
