from flask import Blueprint, render_template, request, make_response
from flask_login import login_required, current_user
from datetime import date, timedelta
from io import BytesIO

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.subscription import Subscription
from app.models.attendance import MemberAttendance
from app.models.finance import Income, Expense
from app.utils.decorators import role_required
from app.utils.helpers import get_date_range

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
@login_required
def index():
    """Reports dashboard"""
    if not current_user.can_view_reports:
        return redirect(url_for('dashboard.index'))

    return render_template('reports/index.html')


@reports_bp.route('/financial')
@login_required
def financial():
    """Financial report"""
    if not current_user.can_view_reports:
        return redirect(url_for('dashboard.index'))

    # Date range
    period = request.args.get('period', 'month')
    start_date, end_date = get_date_range(period)

    # Custom date range
    if request.args.get('start_date'):
        try:
            start_date = date.fromisoformat(request.args.get('start_date'))
            end_date = date.fromisoformat(request.args.get('end_date'))
        except:
            pass

    # Get brands to report on
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            brands = [Brand.query.get(brand_id)]
        else:
            brands = Brand.query.filter_by(is_active=True).all()
    else:
        brands = [current_user.brand]

    # Calculate stats for each brand
    report_data = []
    totals = {'income': 0, 'expenses': 0, 'profit': 0}

    for brand in brands:
        income = Income.get_total_for_period(brand.id, start_date, end_date)
        expenses = Expense.get_total_for_period(brand.id, start_date, end_date)
        profit = income - expenses

        # Expense breakdown
        expense_breakdown = Expense.get_by_category(brand.id, start_date, end_date)

        report_data.append({
            'brand': brand,
            'income': income,
            'expenses': expenses,
            'profit': profit,
            'expense_breakdown': expense_breakdown
        })

        totals['income'] += income
        totals['expenses'] += expenses
        totals['profit'] += profit

    # All brands for filter
    all_brands = None
    if current_user.can_view_all_brands:
        all_brands = Brand.query.filter_by(is_active=True).all()

    return render_template('reports/financial.html',
                          report_data=report_data,
                          totals=totals,
                          brands=all_brands,
                          start_date=start_date,
                          end_date=end_date,
                          period=period)


@reports_bp.route('/members')
@login_required
def members():
    """Members report"""
    if not current_user.can_view_reports:
        return redirect(url_for('dashboard.index'))

    # Get brands
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            brands = [Brand.query.get(brand_id)]
        else:
            brands = Brand.query.filter_by(is_active=True).all()
    else:
        brands = [current_user.brand]

    report_data = []

    for brand in brands:
        total_members = Member.query.filter_by(brand_id=brand.id).count()
        active_members = Member.query.filter_by(brand_id=brand.id, is_active=True).count()

        # Active subscriptions
        today = date.today()
        active_subs = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            Subscription.status == 'active',
            Subscription.end_date >= today
        ).count()

        # Expiring soon (7 days)
        expiring_soon = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            Subscription.status == 'active',
            Subscription.end_date <= today + timedelta(days=7),
            Subscription.end_date >= today
        ).count()

        # Expired
        expired = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            Subscription.status.in_(['active', 'expired']),
            Subscription.end_date < today
        ).count()

        report_data.append({
            'brand': brand,
            'total_members': total_members,
            'active_members': active_members,
            'active_subscriptions': active_subs,
            'expiring_soon': expiring_soon,
            'expired': expired
        })

    # All brands for filter
    all_brands = None
    if current_user.can_view_all_brands:
        all_brands = Brand.query.filter_by(is_active=True).all()

    return render_template('reports/members.html',
                          report_data=report_data,
                          brands=all_brands)


@reports_bp.route('/attendance')
@login_required
def attendance():
    """Attendance report"""
    if not current_user.can_view_reports:
        return redirect(url_for('dashboard.index'))

    # Date range
    period = request.args.get('period', 'month')
    start_date, end_date = get_date_range(period)

    if request.args.get('start_date'):
        try:
            start_date = date.fromisoformat(request.args.get('start_date'))
            end_date = date.fromisoformat(request.args.get('end_date'))
        except:
            pass

    # Get brands
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            brands = [Brand.query.get(brand_id)]
        else:
            brands = Brand.query.filter_by(is_active=True).all()
    else:
        brands = [current_user.brand]

    report_data = []

    for brand in brands:
        total_attendance = MemberAttendance.get_date_range_count(
            brand.id, start_date, end_date
        )

        # Daily average
        days = (end_date - start_date).days + 1
        daily_avg = total_attendance / days if days > 0 else 0

        # Peak hours (simplified)
        report_data.append({
            'brand': brand,
            'total_attendance': total_attendance,
            'daily_average': round(daily_avg, 1),
            'days': days
        })

    # All brands for filter
    all_brands = None
    if current_user.can_view_all_brands:
        all_brands = Brand.query.filter_by(is_active=True).all()

    return render_template('reports/attendance.html',
                          report_data=report_data,
                          brands=all_brands,
                          start_date=start_date,
                          end_date=end_date,
                          period=period)


@reports_bp.route('/export/<report_type>')
@login_required
def export(report_type):
    """Export report to Excel"""
    if not current_user.can_export_reports:
        return redirect(url_for('reports.index'))

    from app.utils.export import export_financial_report, export_members_report

    # Get date range
    start_date = request.args.get('start_date', date.today().replace(day=1).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())

    try:
        start_date = date.fromisoformat(start_date)
        end_date = date.fromisoformat(end_date)
    except:
        start_date = date.today().replace(day=1)
        end_date = date.today()

    # Get brand
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
    else:
        brand_id = current_user.brand_id

    if report_type == 'financial':
        output = export_financial_report(brand_id, start_date, end_date)
        filename = f'financial_report_{start_date}_{end_date}.xlsx'
    elif report_type == 'members':
        output = export_members_report(brand_id)
        filename = f'members_report_{date.today()}.xlsx'
    else:
        return redirect(url_for('reports.index'))

    response = make_response(output.read())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    return response
