from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, TextAreaField, DateField, SelectField
from wtforms.validators import DataRequired, Optional
from datetime import date, datetime

from app import db
from app.models.company import Brand
from app.models.finance import Income, Expense, Salary, Refund, ExpenseCategory
from app.utils.decorators import finance_required, brand_manager_required
from app.utils.helpers import pagination_args, save_uploaded_file

finance_bp = Blueprint('finance', __name__)


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
    else:
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
    else:
        query = Expense.query.filter_by(brand_id=current_user.brand_id)

    query = query.filter(Expense.date >= from_date, Expense.date <= to_date)

    # Status filter
    if status:
        query = query.filter(Expense.status == status)

    # Calculate totals
    base_filter = [Expense.date >= from_date, Expense.date <= to_date]
    if current_user.brand_id:
        base_filter.append(Expense.brand_id == current_user.brand_id)

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

    return render_template('finance/expenses.html',
                          expenses=expenses,
                          brands=brands,
                          total=total,
                          approved_total=approved_total,
                          pending_count=pending_count,
                          status=status,
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
            category_name=form.category_name.data,
            amount=form.amount.data,
            description=form.description.data,
            date=form.date.data,
            created_by=current_user.id
        )

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
