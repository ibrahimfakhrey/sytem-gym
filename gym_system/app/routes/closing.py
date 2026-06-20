from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import DecimalField, TextAreaField, DateField
from wtforms.validators import DataRequired, Optional
from datetime import date, datetime

from app import db
from app.models.company import Brand
from app.models.schedule import DailyClosing
from app.models.subscription import Subscription, SubscriptionPayment
from app.models.finance import Income
from app.utils.decorators import members_required, finance_required
from app.utils.helpers import pagination_args, apply_branch_filter, check_entity_access
from app.models.company import Branch

closing_bp = Blueprint('closing', __name__)


class DailyClosingForm(FlaskForm):
    """Daily Closing form"""
    actual_cash = DecimalField('المبلغ النقدي الفعلي', validators=[DataRequired()])
    notes = TextAreaField('ملاحظات')


@closing_bp.route('/accountant-review')
@login_required
@finance_required
def accountant_review():
    """Enhanced daily closing review for accountants"""
    # Get date to review (default: today)
    review_date_str = request.args.get('date', date.today().isoformat())
    try:
        review_date = date.fromisoformat(review_date_str)
    except:
        review_date = date.today()

    # Base query for brands
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()
    else:
        brands = [current_user.brand] if current_user.brand else []

    # Collect closing status for each brand
    brand_status = []
    total_sales = 0
    total_cash_diff = 0
    unclosed_count = 0

    for brand in brands:
        # Get closing for this brand
        closing = DailyClosing.query.filter_by(
            brand_id=brand.id,
            closing_date=review_date
        ).first()

        # Calculate stats for the day
        stats = calculate_daily_stats(brand.id, review_date)

        if closing:
            cash_diff = float(closing.cash_difference or 0)
            total_cash_diff += cash_diff
            total_sales += float(closing.total_sales or 0)

            brand_status.append({
                'brand': brand,
                'closing': closing,
                'status': 'closed',
                'cash_difference': cash_diff,
                'total_sales': float(closing.total_sales or 0),
                'has_difference': abs(cash_diff) > 0,
                'large_difference': abs(cash_diff) > 100
            })
        else:
            unclosed_count += 1
            total_sales += stats['total_sales']

            brand_status.append({
                'brand': brand,
                'closing': None,
                'status': 'unclosed',
                'stats': stats,
                'total_sales': stats['total_sales']
            })

    # Summary statistics
    summary = {
        'total_brands': len(brands),
        'closed_count': len(brands) - unclosed_count,
        'unclosed_count': unclosed_count,
        'total_sales': total_sales,
        'total_cash_diff': total_cash_diff,
        'has_issues': unclosed_count > 0 or abs(total_cash_diff) > 100
    }

    return render_template('closing/accountant_review.html',
                          brand_status=brand_status,
                          summary=summary,
                          review_date=review_date,
                          can_view_all=current_user.can_view_all_brands)


@closing_bp.route('/')
@login_required
@members_required
def index():
    """List all daily closings"""
    page, per_page = pagination_args(request)

    # Base query - filter by brand/branch access
    query = apply_branch_filter(DailyClosing.query, DailyClosing)

    # Pagination
    closings = query.order_by(DailyClosing.closing_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter (owner only)
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('closing/index.html',
                          closings=closings,
                          brands=brands,
                          date=date)


@closing_bp.route('/view/<closing_date>')
@login_required
@members_required
def view_daily_summary(closing_date):
    """View daily summary before closing"""
    try:
        summary_date = date.fromisoformat(closing_date)
    except:
        summary_date = date.today()

    brand_id = current_user.brand_id
    if not brand_id:
        flash('يرجى تحديد البراند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Check if already closed
    existing_closing = DailyClosing.query.filter_by(
        brand_id=brand_id,
        closing_date=summary_date
    ).first()

    if existing_closing:
        # GYM-37 — friendly message + jump to the existing record so the user
        # can see when + by whom it was closed.
        when_str = existing_closing.submitted_at.strftime('%Y-%m-%d %H:%M') if existing_closing.submitted_at else '—'
        flash(f'يوم {summary_date.isoformat()} تم إقفاله سابقاً (في {when_str}).', 'info')
        return redirect(url_for('closing.view_closing', closing_id=existing_closing.id))

    # Calculate statistics
    stats = calculate_daily_stats(brand_id, summary_date)

    return render_template('closing/daily_summary.html',
                          stats=stats,
                          closing_date=summary_date)


@closing_bp.route('/create', methods=['GET', 'POST'])
@login_required
@members_required
def create():
    """Create daily closing"""
    brand_id = current_user.brand_id
    if not brand_id:
        flash('يرجى تحديد البراند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Get closing date from request or use today
    closing_date_str = request.args.get('date', date.today().isoformat())
    try:
        closing_date = date.fromisoformat(closing_date_str)
    except:
        closing_date = date.today()

    # Check if already closed
    existing = DailyClosing.query.filter_by(
        brand_id=brand_id,
        closing_date=closing_date
    ).first()

    if existing:
        # GYM-37 — friendly message: name the day + when it was closed.
        when_str = existing.submitted_at.strftime('%Y-%m-%d %H:%M') if existing.submitted_at else '—'
        flash(f'يوم {closing_date.isoformat()} تم إقفاله سابقاً (في {when_str}).', 'warning')
        return redirect(url_for('closing.view_closing', closing_id=existing.id))

    # Calculate statistics
    stats = calculate_daily_stats(brand_id, closing_date)

    form = DailyClosingForm()

    if form.validate_on_submit():
        actual_cash = float(form.actual_cash.data)
        expected_cash = float(stats['cash_sales'])
        cash_difference = actual_cash - expected_cash

        # Create closing record
        closing = DailyClosing(
            brand_id=brand_id,
            branch_id=current_user.branch_id,
            closing_date=closing_date,
            submitted_by=current_user.id,
            submitted_at=datetime.utcnow(),
            new_subscriptions_count=stats['new_subscriptions_count'],
            renewals_count=stats['renewals_count'],
            total_sales=stats['total_sales'],
            cash_amount=stats['cash_sales'],
            card_amount=stats['card_sales'],
            transfer_amount=stats['transfer_sales'],
            expected_cash=expected_cash,
            actual_cash_submitted=actual_cash,
            cash_difference=cash_difference,
            notes=form.notes.data,
            status='closed'
        )
        db.session.add(closing)
        db.session.commit()

        flash('تم إقفال اليوم بنجاح', 'success')
        return redirect(url_for('closing.view_closing', closing_id=closing.id))

    return render_template('closing/create.html',
                          form=form,
                          stats=stats,
                          closing_date=closing_date)


@closing_bp.route('/<int:closing_id>')
@login_required
@members_required
def view_closing(closing_id):
    """View closing details"""
    closing = DailyClosing.query.get_or_404(closing_id)

    if not check_entity_access(closing):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('closing.index'))

    # GYM-29 — recompute the per-type breakdown from Income for the receipt
    # explanation: "اشتراكات X · تذاكر يومية Y · إيرادات أخرى Z = expected_cash"
    incomes_q = Income.query.filter(
        Income.brand_id == closing.brand_id,
        Income.date == closing.closing_date,
        Income.is_deleted == False,  # GYM-32 — skip soft-deleted
    )
    if closing.branch_id:
        incomes_q = incomes_q.filter(Income.branch_id == closing.branch_id)

    income_by_type: dict[str, float] = {}
    income_cash_by_type: dict[str, float] = {}
    for i in incomes_q.all():
        t = i.type or 'other'
        amount = float(i.amount or 0)
        income_by_type[t] = income_by_type.get(t, 0) + amount
        if i.payment_method == 'cash':
            income_cash_by_type[t] = income_cash_by_type.get(t, 0) + amount

    return render_template('closing/view.html',
                           closing=closing,
                           income_by_type=income_by_type,
                           income_cash_by_type=income_cash_by_type)


def calculate_daily_stats(brand_id, target_date):
    """Calculate daily statistics for closing.

    GYM-29: revenue is sourced from Income (the canonical revenue ledger)
    rather than SubscriptionPayment alone — that way day-pass tickets and
    any future Income-only revenue path is reflected in `expected_cash`,
    and the receptionist's drawer reconciles cleanly. Old subscription
    payments unchanged: every one also produced an Income row, so the
    sums match.
    """
    # New subscriptions (created today) — kept for headcount/stats (GYM-32)
    new_subs = Subscription.query.filter(
        Subscription.brand_id == brand_id,
        db.func.date(Subscription.created_at) == target_date,
        Subscription.is_deleted == False,
    ).all()
    new_subscriptions_count = len([s for s in new_subs if not hasattr(s, 'is_renewal')])
    renewals_count = 0  # TODO: real renewal detection

    incomes = Income.query.filter(
        Income.brand_id == brand_id,
        Income.date == target_date,
        Income.is_deleted == False,  # GYM-32 — skip soft-deleted
    ).all()

    cash_sales     = sum(float(i.amount) for i in incomes if i.payment_method == 'cash')
    card_sales     = sum(float(i.amount) for i in incomes if i.payment_method == 'card')
    transfer_sales = sum(float(i.amount) for i in incomes if i.payment_method == 'transfer')
    total_sales = cash_sales + card_sales + transfer_sales

    # Per-type breakdown so the closing view can show what makes up the day:
    # e.g. {'subscription': 1200, 'day_pass': 150, 'other': 0}.
    by_type: dict[str, float] = {}
    for i in incomes:
        by_type[i.type or 'other'] = by_type.get(i.type or 'other', 0) + float(i.amount or 0)

    # Surface the payments list too — keep the historical key name so the
    # template doesn't break.
    payments = SubscriptionPayment.query.filter(
        SubscriptionPayment.brand_id == brand_id,
        db.func.date(SubscriptionPayment.payment_date) == target_date
    ).all()

    return {
        'new_subscriptions_count': new_subscriptions_count,
        'renewals_count': renewals_count,
        'total_sales': total_sales,
        'cash_sales': cash_sales,
        'card_sales': card_sales,
        'transfer_sales': transfer_sales,
        'payments': payments,
        'incomes': incomes,
        'income_by_type': by_type,
        'new_subscriptions': new_subs,
    }
