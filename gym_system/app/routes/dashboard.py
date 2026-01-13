from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from datetime import date, timedelta

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.subscription import Subscription
from app.models.attendance import MemberAttendance
from app.models.finance import Income, Expense
from app.models.fingerprint import FingerprintSyncLog

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard - redirects based on role"""
    if current_user.is_owner:
        return redirect(url_for('dashboard.owner'))
    elif current_user.role.name == 'finance_admin':
        return redirect(url_for('dashboard.finance_admin'))
    elif current_user.role.name == 'receptionist':
        return redirect(url_for('dashboard.receptionist'))
    elif current_user.role.name in ['finance', 'brand_manager']:
        return redirect(url_for('dashboard.brand_manager'))
    else:
        return redirect(url_for('dashboard.employee'))


@dashboard_bp.route('/owner')
@login_required
def owner():
    """Owner dashboard - view all brands"""
    if not current_user.is_owner:
        return redirect(url_for('dashboard.index'))

    # Get all active brands
    brands = Brand.query.filter_by(is_active=True).all()

    # Calculate totals
    today = date.today()
    month_start = today.replace(day=1)

    stats = {
        'total_members': 0,
        'active_subscriptions': 0,
        'total_income': 0,
        'total_expenses': 0,
        'today_attendance': 0,
        'brands': []
    }

    for brand in brands:
        brand_stats = get_brand_stats(brand.id, month_start, today)
        stats['total_members'] += brand_stats['members']
        stats['active_subscriptions'] += brand_stats['active_subscriptions']
        stats['total_income'] += brand_stats['income']
        stats['total_expenses'] += brand_stats['expenses']
        stats['today_attendance'] += brand_stats['today_attendance']
        stats['brands'].append({
            'brand': brand,
            'stats': brand_stats
        })

    stats['net_profit'] = stats['total_income'] - stats['total_expenses']

    # Expiring soon subscriptions (all brands)
    expiring_soon = Subscription.query.filter(
        Subscription.status == 'active',
        Subscription.end_date <= today + timedelta(days=7),
        Subscription.end_date >= today
    ).order_by(Subscription.end_date).limit(10).all()

    # Recent subscriptions
    recent_subscriptions = Subscription.query.order_by(
        Subscription.created_at.desc()
    ).limit(10).all()

    return render_template('dashboard/owner.html',
                          stats=stats,
                          brands=brands,
                          expiring_soon=expiring_soon,
                          recent_subscriptions=recent_subscriptions)


@dashboard_bp.route('/brand-manager')
@login_required
def brand_manager():
    """Brand manager/Finance dashboard - single brand"""
    if not current_user.brand_id:
        return redirect(url_for('dashboard.owner'))

    brand = current_user.brand
    today = date.today()
    month_start = today.replace(day=1)

    stats = get_brand_stats(brand.id, month_start, today)

    # Expiring soon
    expiring_soon = Subscription.query.filter(
        Subscription.brand_id == brand.id,
        Subscription.status == 'active',
        Subscription.end_date <= today + timedelta(days=7),
        Subscription.end_date >= today
    ).order_by(Subscription.end_date).limit(10).all()

    # Recent activity
    recent_subscriptions = Subscription.query.filter_by(
        brand_id=brand.id
    ).order_by(Subscription.created_at.desc()).limit(5).all()

    recent_attendance = MemberAttendance.query.filter_by(
        brand_id=brand.id
    ).order_by(MemberAttendance.check_in.desc()).limit(10).all()

    # Fingerprint sync status
    sync_status = None
    if brand.uses_fingerprint:
        sync_status = FingerprintSyncLog.get_sync_status(brand.id)

    return render_template('dashboard/brand_manager.html',
                          brand=brand,
                          stats=stats,
                          expiring_soon=expiring_soon,
                          recent_subscriptions=recent_subscriptions,
                          recent_attendance=recent_attendance,
                          sync_status=sync_status)


@dashboard_bp.route('/receptionist')
@login_required
def receptionist():
    """Receptionist dashboard"""
    if not current_user.brand_id:
        return redirect(url_for('dashboard.index'))

    brand = current_user.brand
    today = date.today()

    # Today's stats
    today_attendance = MemberAttendance.get_today_count(brand.id)

    active_members = Member.query.filter_by(
        brand_id=brand.id,
        is_active=True
    ).count()

    # Expiring today
    expiring_today = Subscription.query.filter(
        Subscription.brand_id == brand.id,
        Subscription.status == 'active',
        Subscription.end_date == today
    ).all()

    # Expiring soon (7 days)
    expiring_soon = Subscription.query.filter(
        Subscription.brand_id == brand.id,
        Subscription.status == 'active',
        Subscription.end_date <= today + timedelta(days=7),
        Subscription.end_date > today
    ).order_by(Subscription.end_date).limit(10).all()

    # Pending fingerprint enrollment
    pending_enrollment = []
    if brand.uses_fingerprint:
        pending_enrollment = Member.query.filter_by(
            brand_id=brand.id,
            is_active=True,
            fingerprint_enrolled=False
        ).limit(10).all()

    return render_template('dashboard/receptionist.html',
                          brand=brand,
                          today_attendance=today_attendance,
                          active_members=active_members,
                          expiring_today=expiring_today,
                          expiring_soon=expiring_soon,
                          pending_enrollment=pending_enrollment)


@dashboard_bp.route('/finance-admin')
@login_required
def finance_admin():
    """Finance admin dashboard - all brands financial view"""
    if current_user.role.name != 'finance_admin' and not current_user.is_owner:
        return redirect(url_for('dashboard.index'))

    brands = Brand.query.filter_by(is_active=True).all()

    today = date.today()
    month_start = today.replace(day=1)

    # Financial stats per brand
    brand_stats = []
    total_income = 0
    total_expenses = 0

    for brand in brands:
        income = Income.get_total_for_period(brand.id, month_start, today)
        expenses = Expense.get_total_for_period(brand.id, month_start, today)
        brand_stats.append({
            'brand': brand,
            'income': income,
            'expenses': expenses,
            'profit': income - expenses
        })
        total_income += income
        total_expenses += expenses

    return render_template('dashboard/finance_admin.html',
                          brands=brands,
                          brand_stats=brand_stats,
                          total_income=total_income,
                          total_expenses=total_expenses,
                          total_profit=total_income - total_expenses)


@dashboard_bp.route('/employee')
@login_required
def employee():
    """Employee/Coach dashboard - personal info only"""
    return render_template('dashboard/employee.html')


def get_brand_stats(brand_id, start_date, end_date):
    """Get statistics for a brand"""
    today = date.today()

    members = Member.query.filter_by(brand_id=brand_id, is_active=True).count()

    active_subscriptions = Subscription.query.filter(
        Subscription.brand_id == brand_id,
        Subscription.status == 'active',
        Subscription.end_date >= today
    ).count()

    income = Income.get_total_for_period(brand_id, start_date, end_date)
    expenses = Expense.get_total_for_period(brand_id, start_date, end_date)

    today_attendance = MemberAttendance.get_today_count(brand_id)

    return {
        'members': members,
        'active_subscriptions': active_subscriptions,
        'income': income,
        'expenses': expenses,
        'profit': income - expenses,
        'today_attendance': today_attendance
    }
