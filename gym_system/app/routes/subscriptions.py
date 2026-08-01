from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import SelectField, DecimalField, TextAreaField, DateField, StringField, BooleanField, IntegerField
from wtforms.validators import DataRequired, Optional
from datetime import date, timedelta, datetime
import json

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.subscription import Plan, Subscription, SubscriptionFreeze, SubscriptionPayment, RenewalRejection
from app.models.finance import Income, Invoice
from app.models.service import ServiceType
from app.models.offer import PromotionalOffer
from app.models.giftcard import GiftCard
from app.models.fingerprint import DeviceCommand
from app.utils.decorators import members_required
from app.utils.helpers import pagination_args, apply_branch_filter, check_entity_access, save_uploaded_file, resolve_owner_branch_filter

subscriptions_bp = Blueprint('subscriptions', __name__)


class SubscriptionForm(FlaskForm):
    """Subscription form"""
    service_type_id = SelectField('نوع الخدمة', coerce=int, validators=[Optional()])
    plan_id = SelectField('الباقة', coerce=int, validators=[DataRequired()])
    sessions_count = IntegerField('عدد الحصص', default=8, validators=[Optional()])
    discount = DecimalField('الخصم', default=0, validators=[Optional()])
    offer_id = SelectField('العرض الترويجي', coerce=int, validators=[Optional()])
    gift_card_code = StringField('كود كرت الإهداء', validators=[Optional()])
    payment_method = SelectField('طريقة الدفع', choices=[
        ('cash', 'نقدي'),
        ('card', 'بطاقة'),
        ('transfer', 'تحويل')
    ], validators=[DataRequired()])
    paid_amount = DecimalField('المبلغ المدفوع', validators=[DataRequired()])
    notes = TextAreaField('ملاحظات')
    proof_image = FileField('صورة إثبات الدفع', validators=[
        Optional(),
        FileAllowed(['png', 'jpg', 'jpeg', 'gif'], 'الصور فقط (png/jpg/jpeg/gif)')
    ])


class RenewalForm(FlaskForm):
    """Renewal form"""
    plan_id = SelectField('خطة الاشتراك', coerce=int, validators=[DataRequired()])
    start_date = DateField('تاريخ البدء', default=date.today, validators=[DataRequired()])
    discount = DecimalField('الخصم', default=0, validators=[Optional()])
    payment_method = SelectField('طريقة الدفع', choices=[
        ('', '-- اختر طريقة الدفع --'),
        ('cash', 'نقدي'),
        ('card', 'بطاقة'),
        ('transfer', 'تحويل')
    ], validators=[DataRequired(message='يرجى اختيار طريقة الدفع')])
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
    expiring = request.args.get('expiring', type=int)
    service_type_id = request.args.get('service_type_id', type=int)
    # GYM-34 — drill-down filters from /reports/staff-performance.
    created_by = request.args.get('created_by', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    # GYM-45 — search by member's fingerprint id.
    fingerprint_id = (request.args.get('fingerprint_id', '') or '').strip()

    # Base query — honor GYM-12 owner branch picker
    query = apply_branch_filter(Subscription.query, Subscription,
                                branch_filter_id=resolve_owner_branch_filter())
    # GYM-32 — hide soft-deleted rows from the list (still in DB for audit)
    query = query.filter(Subscription.is_deleted == False)

    # GYM-34 — created_by + date range filters
    if created_by:
        query = query.filter(Subscription.created_by == created_by)
    if date_from:
        try:
            query = query.filter(Subscription.created_at >= date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import timedelta
            query = query.filter(Subscription.created_at < date.fromisoformat(date_to) + timedelta(days=1))
        except ValueError:
            pass

    # GYM-45 — fingerprint search joins to Member; accepts exact id only.
    if fingerprint_id and fingerprint_id.isdigit():
        query = query.join(Member, Subscription.member_id == Member.id).filter(
            Member.fingerprint_id == int(fingerprint_id)
        )

    # Status filter
    if status:
        query = query.filter_by(status=status)
    
    # Service type filter - filter by service type name (not ID) to work across brands
    if service_type_id:
        # Get the service type name first
        selected_service = ServiceType.query.get(service_type_id)
        if selected_service:
            # Find all service type IDs with the same name across all brands
            matching_service_ids = db.session.query(ServiceType.id).filter(
                ServiceType.name == selected_service.name,
                ServiceType.is_active == True
            ).all()
            matching_ids = [s.id for s in matching_service_ids]
            if matching_ids:
                query = query.filter(Subscription.service_type_id.in_(matching_ids))
    
    # Expiring filter (subscriptions expiring within X days)
    if expiring:
        from datetime import timedelta
        today = date.today()
        query = query.filter(
            Subscription.status == 'active',
            Subscription.end_date >= today,
            Subscription.end_date <= today + timedelta(days=expiring)
        )

    # Pagination
    subscriptions = query.order_by(Subscription.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()
    
    # Get service types for filter (unique by name to avoid duplicates across brands)
    if current_user.can_view_all_brands:
        # Get unique service types by name
        service_types_query = db.session.query(
            ServiceType.id,
            ServiceType.name
        ).filter_by(is_active=True).distinct(ServiceType.name).all()
        service_types = [{'id': st.id, 'name': st.name} for st in service_types_query]
        # Remove duplicates by name
        seen_names = set()
        unique_service_types = []
        for st in service_types:
            if st['name'] not in seen_names:
                seen_names.add(st['name'])
                unique_service_types.append(st)
        service_types = unique_service_types
    else:
        service_types = ServiceType.query.filter_by(brand_id=current_user.brand_id, is_active=True).all()
        service_types = [{'id': st.id, 'name': st.name} for st in service_types]

    return render_template('subscriptions/index.html',
                          subscriptions=subscriptions,
                          brands=brands,
                          service_types=service_types,
                          status=status)


@subscriptions_bp.route('/new')
@login_required
@members_required
def new_select_member():
    """Pick a member to create a new subscription for.

    Shows members eligible for a NEW subscription (no active sub, expired,
    or active sub expiring within `days_window` days). Searchable.
    """
    page, per_page = pagination_args(request)
    search = request.args.get('search', '').strip()
    days_window = request.args.get('days', 7, type=int)
    today = date.today()
    end_window = today + timedelta(days=days_window)

    # Active subscriptions per member (correlated subquery)
    active_sub_subq = db.session.query(Subscription.member_id).filter(
        Subscription.status == 'active',
        Subscription.end_date >= today,
    ).subquery()

    # Active subscriptions expiring soon
    expiring_sub_subq = db.session.query(Subscription.member_id).filter(
        Subscription.status == 'active',
        Subscription.end_date >= today,
        Subscription.end_date <= end_window,
    ).subquery()

    # Base query — apply user's brand/branch scope
    query = apply_branch_filter(Member.query, Member).filter(Member.is_active == True)

    # Eligible: no active sub OR active sub expiring soon
    query = query.filter(
        db.or_(
            Member.id.notin_(db.session.query(active_sub_subq.c.member_id)),
            Member.id.in_(db.session.query(expiring_sub_subq.c.member_id)),
        )
    )

    # Search by name or phone
    if search:
        query = query.filter(
            db.or_(
                Member.name.ilike(f'%{search}%'),
                Member.phone.ilike(f'%{search}%'),
            )
        )

    members = query.order_by(Member.name).paginate(page=page, per_page=per_page, error_out=False)

    # Eager-load active subs for the visible rows in one round-trip to kill the
    # N+1 caused by `member.has_active_subscription` / `member.active_subscription`
    # in the template.
    visible_ids = [m.id for m in members.items]
    active_subs = {}
    if visible_ids:
        for sub in Subscription.query.filter(
            Subscription.member_id.in_(visible_ids),
            Subscription.status == 'active',
            Subscription.end_date >= today,
            Subscription.is_deleted == False,  # GYM-32
        ).all():
            active_subs[sub.member_id] = sub

    return render_template(
        'subscriptions/new_select_member.html',
        members=members,
        search=search,
        days_window=days_window,
        active_subs=active_subs,
        today=today,
    )


@subscriptions_bp.route('/create', methods=['GET', 'POST'])
@login_required
@members_required
def create():
    """Create new subscription"""
    member_id = request.args.get('member_id', type=int)
    if not member_id:
        flash('يرجى اختيار العضو أولاً', 'warning')
        return redirect(url_for('subscriptions.new_select_member'))

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

    # Filter plans by service type (include plans with no service_type = general plans)
    if selected_service_type:
        plans = Plan.query.filter(
            Plan.brand_id == member.brand_id,
            Plan.is_active == True,
            db.or_(
                Plan.service_type_id == selected_service_type,
                Plan.service_type_id.is_(None)  # Include general plans
            )
        ).all()
    else:
        # If no service type selected, show all plans for this brand
        plans = Plan.query.filter_by(
            brand_id=member.brand_id,
            is_active=True
        ).all()

    form.plan_id.choices = [(p.id, f'{p.name} - {p.price} ر.س ({p.plan_type_text})') for p in plans]

    # Get service types for this brand (grouped by category)
    service_types = ServiceType.query.filter_by(brand_id=member.brand_id, is_active=True).order_by(ServiceType.category, ServiceType.name).all()
    
    # Build grouped choices for better UX
    service_choices = [(0, '-- اختر نوع الخدمة --')]
    categories_seen = {}
    for st in service_types:
        cat = st.category or 'other'
        if cat not in categories_seen:
            categories_seen[cat] = []
        categories_seen[cat].append((st.id, st.name))
    
    # Add services grouped by category
    category_names = {
        'gym': '🏋️ جيم',
        'swimming': '🏊 سباحة',
        'karate': '🥋 كاراتيه',
        'salon': '💇 صالون',
        'package': '📦 باقات',
        'other': '📌 أخرى'
    }
    for cat, services in categories_seen.items():
        if len(services) > 1:
            # Multiple services in category - show category header
            for sid, sname in services:
                service_choices.append((sid, f"{category_names.get(cat, cat)} - {sname}"))
        else:
            # Single service - just show name
            for sid, sname in services:
                service_choices.append((sid, sname))
    
    form.service_type_id.choices = service_choices

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
        # GYM-31 — double-submit dedupe. If a Subscription for this member
        # was created in the last 30 seconds (refresh, double-click, browser
        # back-and-resubmit, network retry), redirect to the existing one
        # instead of creating a twin row.
        from datetime import datetime as _dt, timedelta as _td
        _dup = Subscription.query.filter(
            Subscription.member_id == member.id,
            Subscription.created_at >= _dt.utcnow() - _td(seconds=30),
        ).order_by(Subscription.created_at.desc()).first()
        if _dup:
            flash('تم إنشاء هذا الاشتراك للتو — لم نقم بإنشاء تكرار.', 'info')
            return redirect(url_for('subscriptions.view', subscription_id=_dup.id))

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
            if offer and offer.is_valid:
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
        
        # Validate payment amount doesn't exceed total
        if paid_amount > total_amount:
            flash(f'المبلغ المدفوع ({paid_amount:.0f}) أكبر من الإجمالي المطلوب ({total_amount:.0f})', 'danger')
            return render_template('subscriptions/create.html', form=form, member=member, plans=plans, offers=offers, service_types=service_types)
        
        remaining_amount = max(0, total_amount - paid_amount)

        # Calculate dates. GYM-41 — owner / admin can choose a backdated
        # start_date; everyone else gets today.
        start_date = date.today()
        raw_start = (request.form.get('start_date') or '').strip()
        if raw_start and (current_user.is_owner or current_user.is_brand_manager):
            try:
                picked = date.fromisoformat(raw_start)
                if picked <= date.today():
                    start_date = picked
            except ValueError:
                pass
        end_date = start_date + timedelta(days=plan.duration_days)

        # Activate member when creating subscription
        if not member.is_active:
            member.is_active = True

        # Determine sessions total based on service type
        sessions_total = None
        selected_service_type = ServiceType.query.get(form.service_type_id.data) if form.service_type_id.data else None
        if selected_service_type and selected_service_type.is_session_based:
            # Session-based service: use form sessions_count or default to 8
            sessions_total = form.sessions_count.data or 8
        elif plan.sessions_count:
            # Plan has sessions defined
            sessions_total = plan.sessions_count
        
        # Create subscription
        subscription = Subscription(
            member_id=member.id,
            plan_id=plan.id,
            brand_id=member.brand_id,
            branch_id=member.branch_id or current_user.branch_id,  # Set branch from member or current user
            service_type_id=form.service_type_id.data if form.service_type_id.data else None,
            start_date=start_date,
            end_date=end_date,
            original_end_date=end_date,
            sessions_total=sessions_total,
            sessions_consumed=0,
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

        # Save proof-of-payment image (optional)
        proof_file = form.proof_image.data
        if proof_file and getattr(proof_file, 'filename', ''):
            saved_path = save_uploaded_file(proof_file, folder='subscriptions')
            if saved_path:
                subscription.proof_image = saved_path

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
                branch_id=member.branch_id or current_user.branch_id,  # Fallback to user's branch
                subscription_id=subscription.id,
                service_type_id=subscription.service_type_id,
                amount=paid_amount,
                type='subscription',
                payment_method=form.payment_method.data,
                date=date.today(),
                created_by=current_user.id
            )
            db.session.add(income)

            # Generate invoice
            service_type_name = None
            if subscription.service_type:
                service_type_name = subscription.service_type.name

            # GYM-15 — snapshot branch on the invoice
            branch_for_invoice = subscription.branch or (member.branch if hasattr(member, 'branch') else None)
            invoice = Invoice(
                brand_id=member.brand_id,
                branch_id=getattr(branch_for_invoice, 'id', None),
                branch_name=getattr(branch_for_invoice, 'name', None),
                branch_phone=getattr(branch_for_invoice, 'phone', None),
                branch_address=getattr(branch_for_invoice, 'address', None),
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

        # Send command to fingerprint device to unblock member
        if member.fingerprint_id and member.branch and member.branch.uses_fingerprint:
            unblock_cmd = DeviceCommand(
                brand_id=member.brand_id,
                command_type='unblock_member',
                target_emp_id=member.fingerprint_id,
                member_id=member.id,
                command_data=json.dumps({'end_date': subscription.end_date.isoformat()}),
                status='pending'
            )
            db.session.add(unblock_cmd)
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

    return render_template('subscriptions/create.html', form=form, member=member, plans=plans, offers=offers, service_types=service_types)


@subscriptions_bp.route('/<int:subscription_id>')
@login_required
@members_required
def view(subscription_id):
    """View subscription details"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not check_entity_access(subscription):
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

    if not check_entity_access(subscription):
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
        # GYM-31 — double-submit dedupe for renewals. If a payment was
        # written against this same subscription in the last 30 seconds, we
        # treat the second POST as a duplicate.
        from datetime import datetime as _dt, timedelta as _td
        _dup = SubscriptionPayment.query.filter(
            SubscriptionPayment.subscription_id == subscription.id,
            SubscriptionPayment.payment_date >= _dt.utcnow() - _td(seconds=30),
            SubscriptionPayment.is_deleted == False,  # GYM-38
        ).order_by(SubscriptionPayment.payment_date.desc()).first()
        if _dup:
            flash('تم تجديد الاشتراك للتو — لم نقم بإنشاء تكرار.', 'info')
            return redirect(url_for('subscriptions.view', subscription_id=subscription.id))

        plan = Plan.query.get(form.plan_id.data)
        if not plan:
            flash('الباقة غير موجودة', 'danger')
            return render_template('subscriptions/renew.html', form=form, subscription=subscription, plans=plans)
        
        paid_amount = float(form.amount_paid.data or 0)
        discount = float(form.discount.data or 0)
        plan_price = float(plan.price or 0)
        new_start = form.start_date.data
        new_end = new_start + timedelta(days=plan.duration_days)
        
        # Calculate renewal cost and validate payment
        renewal_cost = plan_price - discount
        
        # Validate: discount cannot exceed price
        if discount > plan_price:
            flash(f'الخصم ({discount:.0f}) أكبر من سعر الباقة ({plan_price:.0f})', 'danger')
            return render_template('subscriptions/renew.html', form=form, subscription=subscription, plans=plans)
        
        # Validate: payment must not exceed renewal cost
        if paid_amount > renewal_cost:
            flash(f'المبلغ المدفوع ({paid_amount:.0f}) أكبر من تكلفة التجديد ({renewal_cost:.0f})', 'danger')
            return render_template('subscriptions/renew.html', form=form, subscription=subscription, plans=plans)
        
        # Validate: full payment required for renewal
        if paid_amount < renewal_cost:
            flash(f'⚠️ يجب دفع المبلغ كاملاً للتجديد. المطلوب: {renewal_cost:.0f} ر.س، المدفوع: {paid_amount:.0f} ر.س', 'danger')
            return render_template('subscriptions/renew.html', form=form, subscription=subscription, plans=plans)

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
            db.session.flush()  # Get payment ID

            # Create income record
            income = Income(
                brand_id=subscription.brand_id,
                branch_id=subscription.member.branch_id or current_user.branch_id,  # Fallback
                subscription_id=subscription.id,
                service_type_id=subscription.service_type_id,
                amount=paid_amount,
                payment_method=form.payment_method.data,
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

        # Send command to fingerprint device to unblock member with new end date
        member = subscription.member
        if member.fingerprint_id and member.branch and member.branch.uses_fingerprint:
            unblock_cmd = DeviceCommand(
                brand_id=subscription.brand_id,
                command_type='unblock_member',
                target_emp_id=member.fingerprint_id,
                member_id=member.id,
                command_data=json.dumps({'end_date': subscription.end_date.isoformat()}),
                status='pending'
            )
            db.session.add(unblock_cmd)
            db.session.commit()

        flash('تم تجديد الاشتراك بنجاح', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    return render_template('subscriptions/renew.html', form=form, subscription=subscription, plans=plans)


@subscriptions_bp.route('/<int:subscription_id>/freeze', methods=['GET', 'POST'])
@login_required
@members_required
def freeze(subscription_id):
    """GYM-55 — freeze goes through manager approval.

    Owner / brand-manager submissions apply the freeze directly (existing
    flow). Anyone else (receptionist etc.) creates a
    ``SubscriptionFreezeRequest`` row instead; the freeze isn't applied
    until the manager approves at /admin/freeze-requests.
    """
    from app.models.approvals import SubscriptionFreezeRequest
    subscription = Subscription.query.get_or_404(subscription_id)

    if not check_entity_access(subscription):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    if not subscription.can_freeze:
        flash('لا يمكن تجميد هذا الاشتراك', 'danger')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    # If there's already a pending request, don't let the receptionist
    # submit a second one — send them to a "طلبك قيد المراجعة" state.
    existing_pending = SubscriptionFreezeRequest.query.filter_by(
        subscription_id=subscription_id, status='pending'
    ).first()
    if existing_pending and not (current_user.is_owner or current_user.is_brand_manager):
        flash('يوجد طلب تجميد قيد المراجعة لهذا الاشتراك بالفعل.', 'info')
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

        # GYM-55 — non-manager: create request only, do NOT apply.
        if not (current_user.is_owner or current_user.is_brand_manager):
            db.session.add(SubscriptionFreezeRequest(
                subscription_id=subscription_id,
                freeze_start=freeze_start,
                freeze_days=freeze_days,
                reason=form.reason.data,
                requested_by=current_user.id,
                status='pending',
            ))
            db.session.commit()
            flash('تم إرسال طلب التجميد للمدير للمراجعة. لن يتم تنفيذ التجميد إلا بعد الموافقة.', 'info')
            return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

        # Manager path — apply directly (existing flow).
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

        # Send command to fingerprint device to block member during freeze
        member = subscription.member
        if member.fingerprint_id and member.branch and member.branch.uses_fingerprint:
            block_cmd = DeviceCommand(
                brand_id=subscription.brand_id,
                command_type='block_member',
                target_emp_id=member.fingerprint_id,
                member_id=member.id,
                command_data=json.dumps({'end_date': '2020-01-01'}),
                status='pending'
            )
            db.session.add(block_cmd)
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

    if not check_entity_access(subscription):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    if subscription.status != 'frozen':
        flash('الاشتراك غير مجمد', 'warning')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    subscription.status = 'active'
    db.session.commit()

    # Send command to fingerprint device to unblock member after unfreeze
    member = subscription.member
    if member.fingerprint_id and member.branch and member.branch.uses_fingerprint:
        unblock_cmd = DeviceCommand(
            brand_id=subscription.brand_id,
            command_type='unblock_member',
            target_emp_id=member.fingerprint_id,
            member_id=member.id,
            command_data=json.dumps({'end_date': subscription.end_date.isoformat()}),
            status='pending'
        )
        db.session.add(unblock_cmd)
        db.session.commit()

    flash('تم إلغاء تجميد الاشتراك', 'success')
    return redirect(url_for('subscriptions.view', subscription_id=subscription_id))


@subscriptions_bp.route('/<int:subscription_id>/payment', methods=['GET', 'POST'])
@login_required
@members_required
def add_payment(subscription_id):
    """Add payment to subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not check_entity_access(subscription):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    form = PaymentForm()

    if form.validate_on_submit():
        # GYM-31 — double-submit dedupe for partial payments.
        from datetime import datetime as _dt, timedelta as _td
        _dup = SubscriptionPayment.query.filter(
            SubscriptionPayment.subscription_id == subscription.id,
            SubscriptionPayment.payment_date >= _dt.utcnow() - _td(seconds=30),
            SubscriptionPayment.is_deleted == False,  # GYM-38
        ).order_by(SubscriptionPayment.payment_date.desc()).first()
        if _dup:
            flash('تم تسجيل الدفعة للتو — لم نقم بإنشاء تكرار.', 'info')
            return redirect(url_for('subscriptions.view', subscription_id=subscription.id))

        amount = float(form.amount.data)

        # Validate payment doesn't exceed remaining amount
        remaining = float(subscription.remaining_amount or 0)
        if remaining <= 0:
            flash('الاشتراك مدفوع بالكامل، لا يوجد مبلغ متبقي', 'warning')
            return redirect(url_for('subscriptions.view', subscription_id=subscription_id))
        
        if amount > remaining:
            flash(f'المبلغ ({amount:.0f}) أكبر من المتبقي ({remaining:.0f})', 'danger')
            return render_template('subscriptions/payment.html', form=form, subscription=subscription)

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
            branch_id=subscription.member.branch_id or current_user.branch_id,  # Fallback
            subscription_id=subscription.id,
            service_type_id=subscription.service_type_id,
            amount=amount,
            type='subscription',
            payment_method=form.payment_method.data,
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
    query = apply_branch_filter(Subscription.query, Subscription)

    # Filter expiring subscriptions (GYM-32: skip soft-deleted)
    query = query.filter(
        Subscription.status == 'active',
        Subscription.end_date >= today,
        Subscription.end_date <= end_date,
        Subscription.is_deleted == False,
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

    if not check_entity_access(subscription):
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

    if not check_entity_access(subscription):
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


@subscriptions_bp.route('/<int:subscription_id>/extend', methods=['POST'])
@login_required
@members_required
def extend(subscription_id):
    """GYM-20: brand owner (or admin) gifts free days to a subscription.

    Hard-capped at 90 days per gift to avoid finger-slip extensions of years.
    The original_end_date is preserved (auditable), the gift is appended to
    notes with the operator's name + date.
    """
    subscription = Subscription.query.get_or_404(subscription_id)
    if not check_entity_access(subscription):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    # Permission gate: only brand owners and admins can gift days
    is_admin = current_user.is_owner
    is_brand_owner = current_user.role and current_user.role.name_en == 'owner'
    if not (is_admin or is_brand_owner):
        flash('فقط مالك البراند يمكنه إضافة أيام مجانية', 'danger')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    try:
        days = int(request.form.get('days', '0'))
    except (TypeError, ValueError):
        days = 0
    if days < 1 or days > 90:
        flash('عدد الأيام يجب أن يكون بين 1 و 90', 'warning')
        return redirect(url_for('subscriptions.view', subscription_id=subscription_id))

    reason = (request.form.get('reason') or '').strip()

    subscription.end_date = subscription.end_date + timedelta(days=days)
    if subscription.status == 'expired' and subscription.end_date >= date.today():
        subscription.status = 'active'

    note_parts = [
        f'+{days} يوم مجاني بواسطة {current_user.name}',
        f'في {date.today().isoformat()}',
    ]
    if reason:
        note_parts.append(f'سبب: {reason}')
    suffix = ' — '.join(note_parts)
    subscription.notes = (subscription.notes + '\n' + suffix) if subscription.notes else suffix

    db.session.commit()
    flash(f'تمت إضافة {days} يوم مجاني. ينتهي الاشتراك الآن في {subscription.end_date.isoformat()}', 'success')
    return redirect(url_for('subscriptions.view', subscription_id=subscription_id))


@subscriptions_bp.route('/<int:subscription_id>/invoice')
@login_required
@members_required
def invoice(subscription_id):
    """Generate invoice/receipt for subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)

    if not check_entity_access(subscription):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    # Get all payments for this subscription
    payments = SubscriptionPayment.query.filter_by(subscription_id=subscription.id).all()

    # Get income records
    income_records = Income.query.filter_by(subscription_id=subscription.id).all()

    return render_template('subscriptions/invoice.html',
                          subscription=subscription,
                          payments=payments,
                          income_records=income_records)


# ─── GYM-32 — safe edit + soft-delete ─────────────────────────────────────

@subscriptions_bp.route('/<int:subscription_id>/edit', methods=['GET', 'POST'])
@login_required
@members_required
def edit(subscription_id):
    """Safe-field edit: notes + end_date only. Money-touching fields are
    intentionally NOT exposed here so the books stay clean. Anything else
    needs a refund + new subscription instead."""
    subscription = Subscription.query.get_or_404(subscription_id)
    if not check_entity_access(subscription):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))
    if subscription.is_deleted:
        flash('الاشتراك محذوف.', 'warning')
        return redirect(url_for('subscriptions.index'))

    if request.method == 'POST':
        new_end_str = (request.form.get('end_date') or '').strip()
        new_start_str = (request.form.get('start_date') or '').strip()
        new_notes = (request.form.get('notes') or '').strip() or None

        # GYM-58 — non-managers CAN'T apply edits directly; they file a
        # PendingEdit that a manager reviews at /admin/pending-edits.
        if not (current_user.is_owner or current_user.is_brand_manager):
            from app.routes.approvals import create_pending_edit
            create_pending_edit(
                entity_type='subscription', entity_id=subscription.id,
                action='update',
                payload_dict={
                    'end_date': new_end_str or None,
                    'start_date': new_start_str or None,
                    'notes': new_notes,
                },
                summary=f'تعديل اشتراك #{subscription.id} — {subscription.member.name if subscription.member else ""}',
                brand_id=subscription.brand_id,
            )
            flash('تم إرسال طلب التعديل للمدير للاعتماد. لن يتم تطبيقه إلا بعد الموافقة.', 'info')
            return redirect(url_for('subscriptions.view', subscription_id=subscription.id))

        # GYM-47 — owner / admin can also move start_date; end_date follows
        # automatically (server-side default: start + plan.duration_days).
        # The form's JS does the same calc client-side so the submitted
        # end_date usually already matches, but the server recomputes when
        # end_date wasn't sent or is older than the new start_date.
        if new_start_str and (current_user.is_owner or current_user.is_brand_manager):
            try:
                new_start = date.fromisoformat(new_start_str)
            except ValueError:
                flash('تاريخ البداية غير صالح', 'danger')
                return redirect(url_for('subscriptions.edit', subscription_id=subscription.id))
            subscription.start_date = new_start
            # Auto-recompute end_date from plan duration when the receptionist
            # didn't explicitly send a new end_date, or sent one < start.
            duration = subscription.plan.duration_days if subscription.plan else None
            if duration and (not new_end_str or
                             date.fromisoformat(new_end_str) < new_start):
                subscription.end_date = new_start + timedelta(days=duration)
                new_end_str = ''  # already applied

        if new_end_str:
            try:
                new_end = date.fromisoformat(new_end_str)
            except ValueError:
                flash('تاريخ النهاية غير صالح', 'danger')
                return redirect(url_for('subscriptions.edit', subscription_id=subscription.id))
            if subscription.start_date and new_end < subscription.start_date:
                flash('تاريخ النهاية أقدم من تاريخ البداية', 'danger')
                return redirect(url_for('subscriptions.edit', subscription_id=subscription.id))
            subscription.end_date = new_end

        # GYM-61 — owner/admin only: adjust subscription registration
        # timestamp (created_at) for backdated corrections. Audit-logged.
        new_created_at_str = (request.form.get('registration_datetime') or '').strip()
        if new_created_at_str and (current_user.is_owner or current_user.is_brand_manager):
            from app.models.approvals import EditAuditLog
            try:
                # HTML datetime-local yields YYYY-MM-DDTHH:MM
                new_created_at = datetime.fromisoformat(new_created_at_str)
            except ValueError:
                flash('تاريخ التسجيل غير صالح', 'danger')
                return redirect(url_for('subscriptions.edit', subscription_id=subscription.id))
            if new_created_at != subscription.created_at:
                db.session.add(EditAuditLog(
                    entity_type='subscription',
                    entity_id=subscription.id,
                    field_name='created_at',
                    old_value=subscription.created_at.isoformat() if subscription.created_at else None,
                    new_value=new_created_at.isoformat(),
                    brand_id=subscription.brand_id,
                    changed_by=current_user.id,
                    note='GYM-61 direct manager edit',
                ))
                subscription.created_at = new_created_at

        subscription.notes = new_notes
        db.session.commit()
        flash('تم تحديث الاشتراك', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription.id))

    return render_template('subscriptions/edit.html', subscription=subscription)


@subscriptions_bp.route('/<int:subscription_id>/delete', methods=['POST'])
@login_required
@members_required
def delete(subscription_id):
    """Soft-delete: flips is_deleted on the subscription AND its linked
    Income rows so the day's revenue total stays correct. Reversible by
    flipping the flags back via a manual DB query."""
    subscription = Subscription.query.get_or_404(subscription_id)
    if not check_entity_access(subscription):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))
    if subscription.is_deleted:
        flash('الاشتراك محذوف مسبقاً.', 'warning')
        return redirect(url_for('subscriptions.index'))

    # GYM-58 — non-managers need approval to delete.
    if not (current_user.is_owner or current_user.is_brand_manager):
        from app.routes.approvals import create_pending_edit
        create_pending_edit(
            entity_type='subscription', entity_id=subscription.id,
            action='delete', payload_dict={},
            summary=f'حذف اشتراك #{subscription.id} — {subscription.member.name if subscription.member else ""}',
            brand_id=subscription.brand_id,
        )
        flash('تم إرسال طلب الحذف للمدير للاعتماد. لن يتم التنفيذ إلا بعد الموافقة.', 'info')
        return redirect(url_for('subscriptions.view', subscription_id=subscription.id))

    subscription.is_deleted = True
    Income.query.filter_by(subscription_id=subscription.id).update(
        {'is_deleted': True}, synchronize_session=False)
    # GYM-38 cascade — also flag the subscription's payment rows so
    # aggregations that look at SubscriptionPayment directly (without joining
    # Subscription) don't keep counting them.
    SubscriptionPayment.query.filter_by(subscription_id=subscription.id).update(
        {'is_deleted': True}, synchronize_session=False)
    db.session.commit()
    flash(f'تم حذف الاشتراك #{subscription.id} وعكس إيراداته.', 'success')
    return redirect(url_for('members.view', member_id=subscription.member_id))


# ─── GYM-38 — edit/delete individual SubscriptionPayment rows ────────────
# Each edit / delete cascades to the matching Income row so the daily
# closing math + reports stay consistent (same principle as GYM-32 on the
# subscription as a whole, but at the payment-row granularity).

@subscriptions_bp.route('/payment/<int:payment_id>/edit', methods=['GET', 'POST'])
@login_required
@members_required
def payment_edit(payment_id):
    payment = SubscriptionPayment.query.get_or_404(payment_id)
    subscription = payment.subscription
    if not subscription or not check_entity_access(subscription):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    if request.method == 'POST':
        try:
            new_amount = float(request.form.get('amount') or payment.amount)
        except ValueError:
            flash('قيمة غير صالحة', 'danger')
            return redirect(url_for('subscriptions.payment_edit', payment_id=payment_id))
        if new_amount <= 0:
            flash('المبلغ يجب أن يكون أكبر من صفر', 'danger')
            return redirect(url_for('subscriptions.payment_edit', payment_id=payment_id))

        new_method = (request.form.get('payment_method') or payment.payment_method or 'cash').strip()
        new_notes = (request.form.get('notes') or '').strip() or None

        # GYM-58 — non-managers need approval.
        if not (current_user.is_owner or current_user.is_brand_manager):
            from app.routes.approvals import create_pending_edit
            create_pending_edit(
                entity_type='payment', entity_id=payment.id,
                action='update',
                payload_dict={
                    'amount': new_amount,
                    'payment_method': new_method,
                    'notes': new_notes,
                },
                summary=f'تعديل دفعة #{payment.id} على اشتراك #{subscription.id}',
                brand_id=subscription.brand_id,
            )
            flash('تم إرسال طلب التعديل للمدير للاعتماد.', 'info')
            return redirect(url_for('subscriptions.view', subscription_id=subscription.id))

        delta = float(new_amount) - float(payment.amount or 0)

        payment.amount = new_amount
        payment.payment_method = new_method
        payment.notes = new_notes

        # Cascade to the linked Income row(s). Income created in the same
        # request as the payment carries the same subscription_id; usually
        # one Income per payment. We match by payment_id when set, else fall
        # back to the most recent non-deleted Income on the subscription.
        income = Income.query.filter_by(payment_id=payment.id, is_deleted=False).first()
        if not income:
            income = (Income.query.filter_by(subscription_id=subscription.id, is_deleted=False)
                                  .order_by(Income.id.desc()).first())
        if income:
            income.amount = new_amount
            income.payment_method = new_method

        # Re-derive subscription.paid_amount + remaining_amount from the
        # surviving payments (single source of truth).
        live_paid = sum(float(p.amount or 0)
                        for p in subscription.payments
                        if not getattr(p, 'is_deleted', False))
        subscription.paid_amount = live_paid
        subscription.remaining_amount = max(0, float(subscription.total_amount or 0) - live_paid)

        db.session.commit()
        flash('تم تحديث الدفعة وعُكست في الإيراد.', 'success')
        return redirect(url_for('subscriptions.view', subscription_id=subscription.id))

    return render_template('subscriptions/payment_edit.html',
                           payment=payment, subscription=subscription)


@subscriptions_bp.route('/payment/<int:payment_id>/delete', methods=['POST'])
@login_required
@members_required
def payment_delete(payment_id):
    payment = SubscriptionPayment.query.get_or_404(payment_id)
    subscription = payment.subscription
    if not subscription or not check_entity_access(subscription):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('subscriptions.index'))

    # GYM-58 — non-managers need approval.
    if not (current_user.is_owner or current_user.is_brand_manager):
        from app.routes.approvals import create_pending_edit
        create_pending_edit(
            entity_type='payment', entity_id=payment.id,
            action='delete', payload_dict={},
            summary=f'حذف دفعة #{payment.id} على اشتراك #{subscription.id}',
            brand_id=subscription.brand_id,
        )
        flash('تم إرسال طلب الحذف للمدير للاعتماد.', 'info')
        return redirect(url_for('subscriptions.view', subscription_id=subscription.id))

    # Soft-delete so the linked Invoice FK (invoices.payment_id NOT NULL)
    # doesn't break, and so the row stays around for audit / un-delete.
    # Cascade to the linked Income row(s) by the same flag.
    inc = Income.query.filter_by(payment_id=payment.id).all()
    if not inc:
        inc = (Income.query.filter_by(subscription_id=subscription.id, is_deleted=False)
                           .order_by(Income.id.desc()).limit(1).all())
    for i in inc:
        i.is_deleted = True

    payment.is_deleted = True
    sub_id = subscription.id

    live_paid = sum(float(p.amount or 0)
                    for p in subscription.payments
                    if p.id != payment.id and not getattr(p, 'is_deleted', False))
    subscription.paid_amount = live_paid
    subscription.remaining_amount = max(0, float(subscription.total_amount or 0) - live_paid)
    db.session.commit()

    flash('تم حذف الدفعة وعكس إيرادها.', 'success')
    return redirect(url_for('subscriptions.view', subscription_id=sub_id))
