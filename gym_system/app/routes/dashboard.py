from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from datetime import date, datetime, timedelta
from sqlalchemy import func

from app import db
from app.models.company import Brand, Branch
from app.models.member import Member
from app.models.subscription import Subscription
from app.models.attendance import MemberAttendance
from app.models.finance import Income, Expense
from app.models.fingerprint import FingerprintSyncLog
from app.models.complaint import Complaint
from app.models.daily_closing import DailyClosing

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

    # === SMART ALERTS ===
    alerts = []

    # 1. Urgent expiring subscriptions (48 hours)
    expiring_48h = Subscription.query.filter(
        Subscription.status == 'active',
        Subscription.end_date <= today + timedelta(days=2),
        Subscription.end_date >= today
    ).count()
    if expiring_48h > 0:
        alerts.append({
            'type': 'warning',
            'icon': 'clock-history',
            'title': f'{expiring_48h} اشتراكات تنتهي خلال 48 ساعة',
            'link': url_for('subscriptions.expiring')
        })

    # 2. Open complaints
    open_complaints = Complaint.query.filter(
        Complaint.status.in_(['pending', 'in_progress'])
    ).count()
    if open_complaints > 0:
        alerts.append({
            'type': 'danger',
            'icon': 'exclamation-triangle',
            'title': f'{open_complaints} شكوى مفتوحة تحتاج متابعة',
            'link': url_for('complaints.index')
        })

    # 3. Pending daily closings (not submitted)
    yesterday = today - timedelta(days=1)
    pending_closings = []
    for brand in brands:
        closing = DailyClosing.query.filter_by(
            brand_id=brand.id,
            closing_date=yesterday
        ).first()
        if not closing:
            pending_closings.append(brand.name)
    if pending_closings:
        alerts.append({
            'type': 'info',
            'icon': 'cash-stack',
            'title': f'{len(pending_closings)} فرع بدون إقفال يومي لأمس',
            'link': url_for('daily_closing.index')
        })

    # 4. Contract/Lease expirations (30 days)
    expiring_contracts = Branch.query.filter(
        Branch.is_active == True,
        Branch.lease_expiry_date <= today + timedelta(days=30),
        Branch.lease_expiry_date >= today
    ).all()
    if expiring_contracts:
        alerts.append({
            'type': 'warning',
            'icon': 'building',
            'title': f'{len(expiring_contracts)} عقد إيجار ينتهي خلال 30 يوم',
            'link': url_for('admin.branches')
        })

    # 5. Pending expense approvals
    pending_expenses = Expense.query.filter_by(status='pending').count()
    if pending_expenses > 0:
        alerts.append({
            'type': 'info',
            'icon': 'receipt',
            'title': f'{pending_expenses} مصروف بانتظار الموافقة',
            'link': url_for('finance.expenses')
        })

    # Expiring soon subscriptions (all brands) - 7 days
    expiring_soon = Subscription.query.filter(
        Subscription.status == 'active',
        Subscription.end_date <= today + timedelta(days=7),
        Subscription.end_date >= today
    ).order_by(Subscription.end_date).limit(10).all()

    # Recent subscriptions
    recent_subscriptions = Subscription.query.order_by(
        Subscription.created_at.desc()
    ).limit(10).all()

    # Recent complaints
    recent_complaints = Complaint.query.order_by(
        Complaint.created_at.desc()
    ).limit(5).all()

    return render_template('dashboard/owner.html',
                          stats=stats,
                          brands=brands,
                          alerts=alerts,
                          expiring_soon=expiring_soon,
                          recent_subscriptions=recent_subscriptions,
                          recent_complaints=recent_complaints)


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

    # === SMART ALERTS ===
    alerts = []

    # 1. Urgent expiring subscriptions (48 hours)
    expiring_48h = Subscription.query.filter(
        Subscription.brand_id == brand.id,
        Subscription.status == 'active',
        Subscription.end_date <= today + timedelta(days=2),
        Subscription.end_date >= today
    ).count()
    if expiring_48h > 0:
        alerts.append({
            'type': 'warning',
            'icon': 'clock-history',
            'title': f'{expiring_48h} اشتراكات تنتهي خلال 48 ساعة',
            'link': url_for('subscriptions.expiring')
        })

    # 2. Open complaints for this brand
    open_complaints = Complaint.query.filter(
        Complaint.brand_id == brand.id,
        Complaint.status.in_(['pending', 'in_progress'])
    ).count()
    if open_complaints > 0:
        alerts.append({
            'type': 'danger',
            'icon': 'exclamation-triangle',
            'title': f'{open_complaints} شكوى مفتوحة',
            'link': url_for('complaints.index')
        })

    # 3. Missing daily closing
    yesterday = today - timedelta(days=1)
    closing = DailyClosing.query.filter_by(
        brand_id=brand.id,
        closing_date=yesterday
    ).first()
    if not closing:
        alerts.append({
            'type': 'info',
            'icon': 'cash-stack',
            'title': 'لم يتم إقفال يوم أمس',
            'link': url_for('daily_closing.create')
        })

    # 4. Pending expense approvals
    pending_expenses = Expense.query.filter_by(
        brand_id=brand.id,
        status='pending'
    ).count()
    if pending_expenses > 0:
        alerts.append({
            'type': 'info',
            'icon': 'receipt',
            'title': f'{pending_expenses} مصروف بانتظار الموافقة',
            'link': url_for('finance.expenses')
        })

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

    # Recent complaints
    recent_complaints = Complaint.query.filter_by(
        brand_id=brand.id
    ).order_by(Complaint.created_at.desc()).limit(5).all()

    # Fingerprint sync status
    sync_status = None
    if brand.uses_fingerprint:
        sync_status = FingerprintSyncLog.get_sync_status(brand.id)

    return render_template('dashboard/brand_manager.html',
                          brand=brand,
                          stats=stats,
                          alerts=alerts,
                          expiring_soon=expiring_soon,
                          recent_subscriptions=recent_subscriptions,
                          recent_attendance=recent_attendance,
                          recent_complaints=recent_complaints,
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

    # Today's new subscriptions
    today_new_subs = Subscription.query.filter(
        Subscription.brand_id == brand.id,
        func.date(Subscription.created_at) == today
    ).count()

    # Today's renewals (subscriptions where member already had a previous sub)
    today_renewals = db.session.query(Subscription).filter(
        Subscription.brand_id == brand.id,
        func.date(Subscription.created_at) == today,
        Subscription.member_id.in_(
            db.session.query(Subscription.member_id).filter(
                Subscription.brand_id == brand.id
            ).group_by(Subscription.member_id).having(func.count(Subscription.id) > 1)
        )
    ).count()

    # === URGENT ALERTS (48 hours) ===
    expiring_48h = Subscription.query.filter(
        Subscription.brand_id == brand.id,
        Subscription.status == 'active',
        Subscription.end_date <= today + timedelta(days=2),
        Subscription.end_date >= today
    ).order_by(Subscription.end_date).all()

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

    # Suspended/stopped subscriptions (need follow-up)
    suspended_subs = Subscription.query.filter(
        Subscription.brand_id == brand.id,
        Subscription.status == 'stopped'
    ).order_by(Subscription.stopped_at.desc()).limit(5).all()

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
                          today_new_subs=today_new_subs,
                          today_renewals=today_renewals,
                          expiring_48h=expiring_48h,
                          expiring_today=expiring_today,
                          expiring_soon=expiring_soon,
                          suspended_subs=suspended_subs,
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

    # Payment method breakdown for the month
    payment_breakdown = db.session.query(
        Income.payment_method,
        func.sum(Income.amount)
    ).filter(
        Income.date >= month_start,
        Income.date <= today
    ).group_by(Income.payment_method).all()

    payment_stats = {
        'cash': 0,
        'card': 0,
        'transfer': 0
    }
    for method, amount in payment_breakdown:
        if method in payment_stats:
            payment_stats[method] = float(amount or 0)

    # Daily closings pending verification
    pending_closings = DailyClosing.query.filter_by(
        status='submitted'
    ).order_by(DailyClosing.closing_date.desc()).limit(10).all()

    # Daily closings with cash differences
    cash_differences = DailyClosing.query.filter(
        DailyClosing.cash_difference != 0
    ).order_by(DailyClosing.closing_date.desc()).limit(5).all()

    # Pending expense approvals
    pending_expenses = Expense.query.filter_by(
        status='pending'
    ).order_by(Expense.created_at.desc()).limit(10).all()

    return render_template('dashboard/finance_admin.html',
                          brands=brands,
                          brand_stats=brand_stats,
                          total_income=total_income,
                          total_expenses=total_expenses,
                          total_profit=total_income - total_expenses,
                          payment_stats=payment_stats,
                          pending_closings=pending_closings,
                          cash_differences=cash_differences,
                          pending_expenses=pending_expenses)


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
