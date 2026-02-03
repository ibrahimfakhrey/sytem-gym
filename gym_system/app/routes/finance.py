from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, TextAreaField, DateField, SelectField
from wtforms.validators import DataRequired, Optional
from datetime import date, datetime

from app import db
from app.models.company import Brand
from app.models.finance import Income, Expense, Salary, Refund, ExpenseCategory
from app.models.daily_closing import DailyClosing
from app.models.subscription import Subscription, SubscriptionPayment
from app.utils.decorators import finance_required, brand_manager_required
from app.utils.helpers import pagination_args, save_uploaded_file

finance_bp = Blueprint('finance', __name__)


@finance_bp.route('/dashboard')
@login_required
@finance_required
def dashboard():
    """Finance dashboard with daily summary"""
    today = date.today()

    # Base query for brand filtering
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
    else:
        brand_id = current_user.brand_id

    # Calculate today's total sales
    sales_query = db.session.query(db.func.sum(Income.amount)).filter(
        Income.date == today
    )
    if brand_id:
        sales_query = sales_query.filter(Income.brand_id == brand_id)
    total_sales = sales_query.scalar() or 0

    # Calculate today's total expenses
    expenses_query = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.date == today
    )
    if brand_id:
        expenses_query = expenses_query.filter(Expense.brand_id == brand_id)
    total_expenses = expenses_query.scalar() or 0

    # Get today's daily closing (if exists)
    closing_query = DailyClosing.query.filter(
        DailyClosing.closing_date == today
    )
    if brand_id:
        closing_query = closing_query.filter(DailyClosing.brand_id == brand_id)
    daily_closing = closing_query.first()

    # Calculate cash difference
    cash_difference = None
    if daily_closing:
        expected_cash = float(daily_closing.cash_amount or 0)
        actual_cash = float(daily_closing.actual_cash_submitted or 0)
        cash_difference = actual_cash - expected_cash

    # Financial alerts
    alerts = []

    # Alert: Day not closed yet
    if not daily_closing and datetime.now().hour >= 22:
        alerts.append({
            'type': 'warning',
            'message': 'لم يتم إقفال اليوم بعد'
        })

    # Alert: Large cash difference
    if cash_difference and abs(cash_difference) > 100:
        alerts.append({
            'type': 'danger',
            'message': f'فرق كبير في الكاش: {cash_difference:,.2f} ر.س'
        })

    # Alert: No sales today
    if total_sales == 0 and datetime.now().hour >= 12:
        alerts.append({
            'type': 'info',
            'message': 'لا توجد مبيعات اليوم حتى الآن'
        })

    # Get recent payments (last 10 today)
    payments_query = SubscriptionPayment.query.filter(
        db.func.date(SubscriptionPayment.payment_date) == today
    )
    if brand_id:
        payments_query = payments_query.join(Subscription).filter(
            Subscription.brand_id == brand_id
        )
    recent_payments = payments_query.order_by(
        SubscriptionPayment.payment_date.desc()
    ).limit(10).all()

    # Get recent expenses (last 5 today)
    expenses_list_query = Expense.query.filter(Expense.date == today)
    if brand_id:
        expenses_list_query = expenses_list_query.filter(Expense.brand_id == brand_id)
    recent_expenses = expenses_list_query.order_by(
        Expense.created_at.desc()
    ).limit(5).all()

    # Get pending expenses count
    pending_expenses_query = Expense.query.filter_by(status='pending')
    if brand_id:
        pending_expenses_query = pending_expenses_query.filter(Expense.brand_id == brand_id)
    pending_expenses_count = pending_expenses_query.count()

    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('finance/dashboard.html',
                          total_sales=total_sales,
                          total_expenses=total_expenses,
                          cash_difference=cash_difference,
                          alerts=alerts,
                          recent_payments=recent_payments,
                          recent_expenses=recent_expenses,
                          daily_closing=daily_closing,
                          brands=brands,
                          pending_expenses_count=pending_expenses_count,
                          today=today)


class ExpenseForm(FlaskForm):
    """Expense form"""
    category_name = SelectField('الفئة', validators=[DataRequired()])
    amount = DecimalField('المبلغ', validators=[DataRequired()])
    description = TextAreaField('الوصف')
    date = DateField('التاريخ', default=date.today, validators=[DataRequired()])


class SalaryForm(FlaskForm):
    """Salary form"""
    base_salary = DecimalField('الراتب الأساسي', validators=[DataRequired()])
    deductions = DecimalField('الخصومات', default=0)
    bonuses = DecimalField('البدلات', default=0)
    notes = TextAreaField('ملاحظات')


@finance_bp.route('/sales-transactions')
@login_required
@finance_required
def sales_transactions():
    """Detailed sales transactions view"""
    page, per_page = pagination_args(request)
    date_from = request.args.get('date_from', date.today().replace(day=1).isoformat())
    date_to = request.args.get('date_to', date.today().isoformat())

    # Parse dates
    try:
        from_date = datetime.fromisoformat(date_from).date()
        to_date = datetime.fromisoformat(date_to).date()
    except:
        from_date = date.today().replace(day=1)
        to_date = date.today()

    # Base query - join with subscription and member to get all details
    query = db.session.query(SubscriptionPayment).join(Subscription).join(
        Subscription.member
    )

    # Brand filter
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = query.filter(Subscription.brand_id == brand_id)
    else:
        query = query.filter(Subscription.brand_id == current_user.brand_id)

    # Date filter
    query = query.filter(
        db.func.date(SubscriptionPayment.payment_date) >= from_date,
        db.func.date(SubscriptionPayment.payment_date) <= to_date
    )

    # Payment method filter
    payment_method = request.args.get('payment_method', '')
    if payment_method:
        query = query.filter(SubscriptionPayment.payment_method == payment_method)

    # Service filter (subscription plan)
    service_id = request.args.get('service_id', type=int)
    if service_id:
        query = query.filter(Subscription.plan_id == service_id)

    # Receptionist filter
    receptionist_id = request.args.get('receptionist_id', type=int)
    if receptionist_id:
        query = query.filter(Subscription.created_by == receptionist_id)

    # Member search
    search = request.args.get('search', '').strip()
    if search:
        from app.models.member import Member
        query = query.filter(Member.name.like(f'%{search}%'))

    # Calculate totals
    total_amount = query.with_entities(
        db.func.sum(SubscriptionPayment.amount)
    ).scalar() or 0

    # Count by payment method
    payment_method_counts = {}
    if current_user.can_view_all_brands and not brand_id:
        base_query = db.session.query(SubscriptionPayment).join(Subscription)
    else:
        base_query = query

    for method in ['cash', 'card', 'transfer']:
        count_query = base_query.filter(
            SubscriptionPayment.payment_method == method,
            db.func.date(SubscriptionPayment.payment_date) >= from_date,
            db.func.date(SubscriptionPayment.payment_date) <= to_date
        )
        if not current_user.can_view_all_brands or brand_id:
            payment_method_counts[method] = count_query.count()
        else:
            payment_method_counts[method] = count_query.count()

    # Pagination
    transactions = query.order_by(SubscriptionPayment.payment_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get filter options
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    # Get subscription plans for service filter
    from app.models.subscription import SubscriptionPlan
    if current_user.can_view_all_brands:
        if brand_id:
            services = SubscriptionPlan.query.filter_by(
                brand_id=brand_id, is_active=True
            ).all()
        else:
            services = SubscriptionPlan.query.filter_by(is_active=True).all()
    else:
        services = SubscriptionPlan.query.filter_by(
            brand_id=current_user.brand_id, is_active=True
        ).all()

    # Get receptionists for filter
    receptionists = User.query.filter(
        User.role.has(name_en='receptionist')
    )
    if not current_user.can_view_all_brands:
        receptionists = receptionists.filter_by(brand_id=current_user.brand_id)
    receptionists = receptionists.all()

    return render_template('finance/sales_transactions.html',
                          transactions=transactions,
                          brands=brands,
                          services=services,
                          receptionists=receptionists,
                          total_amount=total_amount,
                          payment_method_counts=payment_method_counts,
                          date_from=date_from,
                          date_to=date_to,
                          payment_method=payment_method,
                          service_id=service_id,
                          receptionist_id=receptionist_id,
                          search=search)


@finance_bp.route('/income')
@login_required
@finance_required
def income_list():
    """List income records"""
    page, per_page = pagination_args(request)
    date_from = request.args.get('date_from', date.today().replace(day=1).isoformat())
    date_to = request.args.get('date_to', date.today().isoformat())
    payment_method = request.args.get('payment_method', '')

    # Parse dates
    try:
        from_date = date.fromisoformat(date_from)
        to_date = date.fromisoformat(date_to)
    except:
        from_date = date.today().replace(day=1)
        to_date = date.today()

    # Base query
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = Income.query.filter_by(brand_id=brand_id)
        else:
            query = Income.query
    elif current_user.branch_id:
        # Branch accountant - only see their branch
        query = Income.query.filter_by(brand_id=current_user.brand_id, branch_id=current_user.branch_id)
    else:
        # Central accountant - see all branches in brand
        query = Income.query.filter_by(brand_id=current_user.brand_id)

    # Date filter
    query = query.filter(Income.date >= from_date, Income.date <= to_date)

    # Payment method filter
    if payment_method:
        query = query.filter(Income.payment_method == payment_method)

    # Calculate totals by payment method
    base_filter = [Income.date >= from_date, Income.date <= to_date]
    if current_user.brand_id:
        base_filter.append(Income.brand_id == current_user.brand_id)
        # Branch accountant filter
        if current_user.branch_id:
            base_filter.append(Income.branch_id == current_user.branch_id)

    total = db.session.query(db.func.sum(Income.amount)).filter(*base_filter).scalar() or 0

    # Payment breakdown
    payment_breakdown = db.session.query(
        Income.payment_method,
        db.func.sum(Income.amount)
    ).filter(*base_filter).group_by(Income.payment_method).all()

    payment_stats = {'cash': 0, 'card': 0, 'transfer': 0}
    for method, amount in payment_breakdown:
        if method in payment_stats:
            payment_stats[method] = float(amount or 0)

    # Pagination
    income = query.order_by(Income.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('finance/income.html',
                          income=income,
                          brands=brands,
                          total=total,
                          payment_stats=payment_stats,
                          payment_method=payment_method,
                          date_from=date_from,
                          date_to=date_to)


@finance_bp.route('/expenses')
@login_required
@finance_required
def expenses():
    """List expense records"""
    page, per_page = pagination_args(request)
    date_from = request.args.get('date_from', date.today().replace(day=1).isoformat())
    date_to = request.args.get('date_to', date.today().isoformat())
    status = request.args.get('status', '')
    category = request.args.get('category', '')
    user_id = request.args.get('user_id', type=int)
    branch_id_filter = request.args.get('branch_id', type=int)

    try:
        from_date = date.fromisoformat(date_from)
        to_date = date.fromisoformat(date_to)
    except:
        from_date = date.today().replace(day=1)
        to_date = date.today()

    # Base query
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = Expense.query.filter_by(brand_id=brand_id)
        else:
            query = Expense.query
    elif current_user.branch_id:
        # Branch accountant - only see their branch
        query = Expense.query.filter_by(brand_id=current_user.brand_id, branch_id=current_user.branch_id)
    else:
        # Central accountant - see all branches in brand
        query = Expense.query.filter_by(brand_id=current_user.brand_id)

    query = query.filter(Expense.date >= from_date, Expense.date <= to_date)

    # Additional filters
    if status:
        query = query.filter(Expense.status == status)

    if category:
        query = query.filter(Expense.category_name == category)

    if user_id:
        query = query.filter(Expense.created_by == user_id)

    # Branch filter for central accountants
    if branch_id_filter and not current_user.branch_id:
        query = query.filter(Expense.branch_id == branch_id_filter)

    # Calculate totals
    base_filter = [Expense.date >= from_date, Expense.date <= to_date]
    if current_user.brand_id:
        base_filter.append(Expense.brand_id == current_user.brand_id)
        # Branch accountant filter
        if current_user.branch_id:
            base_filter.append(Expense.branch_id == current_user.branch_id)

    total = db.session.query(db.func.sum(Expense.amount)).filter(*base_filter).scalar() or 0
    approved_total = db.session.query(db.func.sum(Expense.amount)).filter(
        *base_filter, Expense.status == 'approved'
    ).scalar() or 0
    pending_count = Expense.query.filter(*base_filter, Expense.status == 'pending').count()

    # Pagination
    expenses = query.order_by(Expense.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    # Branches for filter (central accountants only)
    from app.models.company import Branch
    branches = None
    if current_user.brand_id and not current_user.branch_id:
        branches = Branch.query.filter_by(brand_id=current_user.brand_id, is_active=True).all()

    # Users for filter
    from app.models.user import User
    users = User.query.filter_by(brand_id=current_user.brand_id, is_active=True).all() if current_user.brand_id else []

    # Categories for filter
    categories = ['رواتب', 'إيجار', 'كهرباء', 'ماء', 'صيانة', 'معدات', 'تسويق', 'مستلزمات', 'أخرى']

    return render_template('finance/expenses.html',
                          expenses=expenses,
                          brands=brands,
                          branches=branches,
                          users=users,
                          categories=categories,
                          total=total,
                          approved_total=approved_total,
                          pending_count=pending_count,
                          status=status,
                          category=category,
                          user_id=user_id,
                          branch_id_filter=branch_id_filter,
                          date_from=date_from,
                          date_to=date_to)


@finance_bp.route('/expenses/create', methods=['GET', 'POST'])
@login_required
@finance_required
def expenses_create():
    """Create new expense"""
    form = ExpenseForm()

    # Expense categories
    categories = [
        ('رواتب', 'رواتب'),
        ('إيجار', 'إيجار'),
        ('كهرباء', 'كهرباء'),
        ('ماء', 'ماء'),
        ('صيانة', 'صيانة'),
        ('معدات', 'معدات'),
        ('تسويق', 'تسويق'),
        ('مستلزمات', 'مستلزمات'),
        ('أخرى', 'أخرى'),
    ]
    form.category_name.choices = categories

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            flash('يرجى اختيار البراند', 'warning')
            return redirect(url_for('admin.brands_list'))
        brand = Brand.query.get_or_404(brand_id)
    else:
        brand = current_user.brand
        brand_id = brand.id

    if form.validate_on_submit():
        expense = Expense(
            brand_id=brand_id,
            branch_id=current_user.branch_id,
            category_name=form.category_name.data,
            amount=form.amount.data,
            description=form.description.data,
            date=form.date.data,
            created_by=current_user.id
        )

        # Check if approval is required
        if expense.requires_approval():
            expense.status = 'pending'
            flash_msg = 'تم تسجيل المصروف وهو بانتظار الموافقة'
        else:
            expense.status = 'approved'
            flash_msg = 'تم تسجيل المصروف بنجاح'

        # Handle receipt image
        if 'receipt_image' in request.files:
            receipt_file = request.files['receipt_image']
            if receipt_file.filename:
                receipt_path = save_uploaded_file(receipt_file, 'receipts')
                if receipt_path:
                    expense.receipt_image = receipt_path

        db.session.add(expense)
        db.session.commit()

        flash('تم تسجيل المصروف بنجاح', 'success')
        return redirect(url_for('finance.expenses'))

    return render_template('finance/expense_form.html', form=form, brand=brand)


@finance_bp.route('/expenses/pending')
@login_required
@finance_required
def pending_expenses():
    """View pending expenses for approval"""
    page, per_page = pagination_args(request)

    # Base query for pending expenses
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = Expense.query.filter_by(brand_id=brand_id, status='pending')
        else:
            query = Expense.query.filter_by(status='pending')
    else:
        query = Expense.query.filter_by(brand_id=current_user.brand_id, status='pending')

    # Pagination
    expenses = query.order_by(Expense.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    # Calculate total pending amount
    total_pending = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.status == 'pending'
    )
    if not current_user.can_view_all_brands:
        total_pending = total_pending.filter(Expense.brand_id == current_user.brand_id)
    total_pending = total_pending.scalar() or 0

    return render_template('finance/pending_expenses.html',
                          expenses=expenses,
                          brands=brands,
                          total_pending=total_pending)


@finance_bp.route('/expenses/<int:expense_id>/approve', methods=['POST'])
@login_required
@finance_required
def approve_expense(expense_id):
    """Approve an expense"""
    expense = Expense.query.get_or_404(expense_id)

    if not current_user.can_access_brand(expense.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('finance.pending_expenses'))

    if expense.status != 'pending':
        flash('هذا المصروف تمت معالجته مسبقاً', 'warning')
        return redirect(url_for('finance.pending_expenses'))

    expense.status = 'approved'
    expense.approved_by = current_user.id
    expense.approved_at = datetime.utcnow()
    db.session.commit()

    flash('تم اعتماد المصروف بنجاح', 'success')
    return redirect(url_for('finance.pending_expenses'))


@finance_bp.route('/expenses/<int:expense_id>/reject', methods=['POST'])
@login_required
@finance_required
def reject_expense(expense_id):
    """Reject an expense"""
    expense = Expense.query.get_or_404(expense_id)

    if not current_user.can_access_brand(expense.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('finance.pending_expenses'))

    if expense.status != 'pending':
        flash('هذا المصروف تمت معالجته مسبقاً', 'warning')
        return redirect(url_for('finance.pending_expenses'))

    reason = request.form.get('reason', '')

    expense.status = 'rejected'
    expense.approved_by = current_user.id
    expense.approved_at = datetime.utcnow()
    expense.rejection_reason = reason
    db.session.commit()

    flash('تم رفض المصروف', 'success')
    return redirect(url_for('finance.pending_expenses'))


@finance_bp.route('/salaries')
@login_required
@finance_required
def salaries_list():
    """List salaries with rewards and deductions"""
    from app.models.employee import EmployeeReward, EmployeeDeduction

    month = request.args.get('month', date.today().month, type=int)
    year = request.args.get('year', date.today().year, type=int)

    # Calculate period dates
    from calendar import monthrange
    period_start = date(year, month, 1)
    period_end = date(year, month, monthrange(year, month)[1])

    # Base query
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = Salary.query.filter_by(brand_id=brand_id)
        else:
            query = Salary.query
    else:
        brand_id = current_user.brand_id
        query = Salary.query.filter_by(brand_id=current_user.brand_id)

    query = query.filter_by(month=month, year=year)
    salaries = query.all()

    # Build salary data with rewards/deductions
    salary_data = []
    for salary in salaries:
        # Get rewards for this employee in this period
        rewards = EmployeeReward.query.filter(
            EmployeeReward.user_id == salary.user_id,
            EmployeeReward.is_active == True,
            db.or_(
                # One-time rewards in period
                db.and_(
                    EmployeeReward.is_recurring == False,
                    EmployeeReward.effective_date >= period_start,
                    EmployeeReward.effective_date <= period_end
                ),
                # Recurring rewards
                EmployeeReward.is_recurring == True
            )
        ).all()
        total_rewards = sum(float(r.amount) for r in rewards)

        # Get deductions for this employee in this period
        deductions = EmployeeDeduction.query.filter(
            EmployeeDeduction.user_id == salary.user_id,
            EmployeeDeduction.deduction_date >= period_start,
            EmployeeDeduction.deduction_date <= period_end
        ).all()
        total_deductions = sum(float(d.amount) for d in deductions)

        net_salary = float(salary.base_salary) + total_rewards - total_deductions

        salary_data.append({
            'salary': salary,
            'rewards': rewards,
            'deductions': deductions,
            'total_rewards': total_rewards,
            'total_deductions': total_deductions,
            'net_salary': net_salary
        })

    # Calculate totals
    total_base = sum(float(s['salary'].base_salary) for s in salary_data)
    total_rewards = sum(s['total_rewards'] for s in salary_data)
    total_deductions = sum(s['total_deductions'] for s in salary_data)
    total_net = total_base + total_rewards - total_deductions

    # Brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('finance/salaries.html',
                          salary_data=salary_data,
                          brands=brands,
                          total_base=total_base,
                          total_rewards=total_rewards,
                          total_deductions=total_deductions,
                          total_net=total_net,
                          month=month,
                          year=year)


@finance_bp.route('/refunds')
@login_required
@finance_required
def refunds_list():
    """List refunds"""
    page, per_page = pagination_args(request)

    # Base query
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = Refund.query.filter_by(brand_id=brand_id)
        else:
            query = Refund.query
    else:
        query = Refund.query.filter_by(brand_id=current_user.brand_id)

    # Pagination
    refunds = query.order_by(Refund.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('finance/refunds.html', refunds=refunds)


@finance_bp.route('/expenses/<int:expense_id>')
@login_required
@finance_required
def expense_view(expense_id):
    """View expense details"""
    expense = Expense.query.get_or_404(expense_id)

    if not current_user.can_access_brand(expense.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('finance.expenses'))

    return render_template('finance/expense_view.html', expense=expense)


@finance_bp.route('/expenses/<int:expense_id>/approve', methods=['POST'])
@login_required
@brand_manager_required
def expense_approve(expense_id):
    """Approve expense"""
    expense = Expense.query.get_or_404(expense_id)

    if not current_user.can_access_brand(expense.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('finance.expenses'))

    if expense.status != 'pending':
        flash('هذا المصروف تم معالجته مسبقاً', 'warning')
        return redirect(url_for('finance.expense_view', expense_id=expense_id))

    expense.status = 'approved'
    expense.approved_by = current_user.id
    expense.approved_at = datetime.utcnow()

    db.session.commit()
    flash('تم اعتماد المصروف', 'success')

    return redirect(url_for('finance.expenses', status='pending'))


@finance_bp.route('/expenses/<int:expense_id>/reject', methods=['GET', 'POST'])
@login_required
@brand_manager_required
def expense_reject(expense_id):
    """Reject expense"""
    expense = Expense.query.get_or_404(expense_id)

    if not current_user.can_access_brand(expense.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('finance.expenses'))

    if expense.status != 'pending':
        flash('هذا المصروف تم معالجته مسبقاً', 'warning')
        return redirect(url_for('finance.expense_view', expense_id=expense_id))

    if request.method == 'POST':
        reason = request.form.get('rejection_reason', '')
        expense.status = 'rejected'
        expense.approved_by = current_user.id
        expense.approved_at = datetime.utcnow()
        expense.rejection_reason = reason

        db.session.commit()
        flash('تم رفض المصروف', 'info')

        return redirect(url_for('finance.expenses', status='pending'))

    return render_template('finance/expense_reject.html', expense=expense)
