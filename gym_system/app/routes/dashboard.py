from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from datetime import date, datetime, timedelta
from sqlalchemy import func

from app import db
from app.models.company import Brand, Branch
from app.models.member import Member
from app.models.subscription import Subscription
from app.models.attendance import MemberAttendance, EmployeeAttendance
from app.models.finance import Income, Expense
from app.models.fingerprint import FingerprintSyncLog
from app.models.complaint import Complaint
from app.models.daily_closing import DailyClosing
from app.models.user import User
from app.models.classes import GymClass
from app.models.service import ServiceType

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard - redirects based on role"""
    if current_user.is_owner:
        return redirect(url_for('dashboard.owner'))
    elif current_user.role.name == 'مدير مالية':
        return redirect(url_for('dashboard.finance_admin'))
    elif current_user.role.name == 'موظف استقبال':
        return redirect(url_for('dashboard.receptionist'))
    elif current_user.role.name in ['مالية', 'مدير براند']:
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

    # 1. Urgent expiring subscriptions (48 hours) - FUTURE subscriptions only
    expiring_48h = Subscription.query.filter(
        Subscription.status == 'active',
        Subscription.end_date > today,  # Must be in the future, not today
        Subscription.end_date <= today + timedelta(days=2)
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
    expiring_leases = Branch.query.filter(
        Branch.is_active == True,
        Branch.lease_expiry_date <= today + timedelta(days=30),
        Branch.lease_expiry_date >= today
    ).all()
    if expiring_leases:
        branch_names = ', '.join([b.name for b in expiring_leases[:3]])
        if len(expiring_leases) > 3:
            branch_names += f' و {len(expiring_leases) - 3} آخرين'
        # Link to first branch's brand branches list
        first_branch = expiring_leases[0]
        alerts.append({
            'type': 'warning',
            'icon': 'building',
            'title': f'{len(expiring_leases)} عقد إيجار ينتهي خلال 30 يوم - {branch_names}',
            'link': url_for('admin.branches_list', brand_id=first_branch.brand_id) + '?filter=lease_expiring'
        })

    # Commercial registration expirations (30 days)
    expiring_registrations = Branch.query.filter(
        Branch.is_active == True,
        Branch.commercial_registration_expiry <= today + timedelta(days=30),
        Branch.commercial_registration_expiry >= today
    ).all()
    if expiring_registrations:
        branch_names = ', '.join([b.name for b in expiring_registrations[:3]])
        if len(expiring_registrations) > 3:
            branch_names += f' و {len(expiring_registrations) - 3} آخرين'
        first_branch = expiring_registrations[0]
        alerts.append({
            'type': 'danger',
            'icon': 'file-earmark-text',
            'title': f'{len(expiring_registrations)} سجل تجاري ينتهي خلال 30 يوم - {branch_names}',
            'link': url_for('admin.branches_list', brand_id=first_branch.brand_id) + '?filter=registration_expiring'
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

    # 6. Late/Absent employees today
    late_employees = EmployeeAttendance.query.filter(
        EmployeeAttendance.date == today,
        EmployeeAttendance.status == 'late'
    ).all()
    if late_employees:
        total_late_minutes = sum(emp.late_minutes or 0 for emp in late_employees)
        late_names = ', '.join([emp.employee.name for emp in late_employees[:3]])
        if len(late_employees) > 3:
            late_names += f' و {len(late_employees) - 3} آخرين'
        alerts.append({
            'type': 'warning',
            'icon': 'person-exclamation',
            'title': f'{len(late_employees)} موظف متأخر اليوم ({total_late_minutes} دقيقة) - {late_names}',
            'link': url_for('employees.attendance')
        })

    # Absent employees today (expected but didn't show up)
    absent_employees = EmployeeAttendance.query.filter(
        EmployeeAttendance.date == today,
        EmployeeAttendance.status == 'absent'
    ).all()
    if absent_employees:
        absent_names = ', '.join([emp.employee.name for emp in absent_employees[:3]])
        if len(absent_employees) > 3:
            absent_names += f' و {len(absent_employees) - 3} آخرين'
        alerts.append({
            'type': 'danger',
            'icon': 'person-x',
            'title': f'{len(absent_employees)} موظف غائب اليوم - {absent_names}',
            'link': url_for('employees.attendance')
        })

    # 7. Revenue anomaly detection (branch performance drops)
    # Check each brand for significant revenue drops
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=35)  # 5 weeks ago (to calculate 4-week baseline before current week)

    for brand in brands:
        # Current week revenue (last 7 days)
        current_week_revenue = db.session.query(db.func.sum(Income.amount)).filter(
            Income.brand_id == brand.id,
            Income.date >= week_ago,
            Income.date <= today
        ).scalar() or 0

        # Previous 4 weeks average (days 8-35)
        baseline_start = today - timedelta(days=35)
        baseline_end = today - timedelta(days=8)
        baseline_revenue = db.session.query(db.func.sum(Income.amount)).filter(
            Income.brand_id == brand.id,
            Income.date >= baseline_start,
            Income.date <= baseline_end
        ).scalar() or 0

        # Calculate weekly baseline average
        weekly_baseline = baseline_revenue / 4 if baseline_revenue > 0 else 0

        # Check if current week is significantly below baseline (20% drop)
        if weekly_baseline > 0:
            drop_percentage = ((weekly_baseline - current_week_revenue) / weekly_baseline) * 100

            if drop_percentage >= 20:  # 20% or more drop
                alerts.append({
                    'type': 'danger',
                    'icon': 'graph-down-arrow',
                    'title': f'انخفاض الإيرادات في {brand.name} بنسبة {int(drop_percentage)}% هذا الأسبوع',
                    'link': url_for('reports.financial', brand_id=brand.id, period='week')
                })

    # Expiring soon subscriptions (all brands) - 7 days (FUTURE subscriptions only)
    expiring_soon = Subscription.query.filter(
        Subscription.status == 'active',
        Subscription.end_date > today,  # Must be in the future, not today or past
        Subscription.end_date <= today + timedelta(days=7)
    ).order_by(Subscription.end_date).limit(10).all()

    # Recent subscriptions
    recent_subscriptions = Subscription.query.order_by(
        Subscription.created_at.desc()
    ).limit(10).all()

    # Recent complaints
    recent_complaints = Complaint.query.order_by(
        Complaint.created_at.desc()
    ).limit(5).all()
    
    # === SERVICE ANALYTICS ===
    # Top services by subscription count (this month)
    service_analytics = db.session.query(
        ServiceType.id,
        ServiceType.name,
        ServiceType.category,
        func.count(Subscription.id).label('subscription_count'),
        func.sum(Subscription.total_amount).label('revenue')
    ).outerjoin(
        Subscription, 
        db.and_(
            Subscription.service_type_id == ServiceType.id,
            Subscription.created_at >= month_start
        )
    ).filter(
        ServiceType.is_active == True
    ).group_by(
        ServiceType.id, ServiceType.name, ServiceType.category
    ).order_by(func.count(Subscription.id).desc()).all()
    
    # Format service analytics
    top_services = []
    bottom_services = []
    for service in service_analytics:
        service_data = {
            'id': service.id,
            'name': service.name,
            'category': service.category,
            'subscription_count': service.subscription_count or 0,
            'revenue': float(service.revenue or 0)
        }
        if service.subscription_count and service.subscription_count > 0:
            top_services.append(service_data)
    
    # Get bottom services (services with least demand but still active)
    bottom_services = [s for s in top_services if s['subscription_count'] > 0]
    bottom_services = sorted(bottom_services, key=lambda x: x['subscription_count'])[:3]
    top_services = top_services[:5]  # Top 5 services

    return render_template('dashboard/owner.html',
                          stats=stats,
                          brands=brands,
                          alerts=alerts,
                          expiring_soon=expiring_soon,
                          recent_subscriptions=recent_subscriptions,
                          recent_complaints=recent_complaints,
                          top_services=top_services,
                          bottom_services=bottom_services)


@dashboard_bp.route('/branch/<int:branch_id>')
@login_required
def branch_detail(branch_id):
    """Branch detail dashboard for owner"""
    if not current_user.is_owner and not current_user.can_manage_users:
        return redirect(url_for('dashboard.index'))
    
    branch = Branch.query.get_or_404(branch_id)
    brand = branch.brand
    
    today = date.today()
    month_start = today.replace(day=1)
    
    # Branch-specific stats
    stats = {
        'members': Member.query.filter_by(branch_id=branch_id, is_active=True).count(),
        'active_subscriptions': Subscription.query.filter(
            Subscription.branch_id == branch_id,
            Subscription.status == 'active',
            Subscription.end_date >= today
        ).count(),
        'today_attendance': MemberAttendance.query.filter(
            MemberAttendance.branch_id == branch_id,
            func.date(MemberAttendance.check_in) == today
        ).count(),
        'income': db.session.query(func.sum(Income.amount)).filter(
            Income.branch_id == branch_id,
            Income.date >= month_start,
            Income.date <= today
        ).scalar() or 0,
        'expenses': db.session.query(func.sum(Expense.amount)).filter(
            Expense.branch_id == branch_id,
            Expense.date >= month_start,
            Expense.date <= today
        ).scalar() or 0
    }
    stats['profit'] = stats['income'] - stats['expenses']
    
    # Branch employees
    employees = User.query.filter_by(branch_id=branch_id, is_active=True).all()
    
    # Recent subscriptions for this branch
    recent_subscriptions = Subscription.query.filter_by(
        branch_id=branch_id
    ).order_by(Subscription.created_at.desc()).limit(10).all()
    
    # Expiring subscriptions
    expiring_soon = Subscription.query.filter(
        Subscription.branch_id == branch_id,
        Subscription.status == 'active',
        Subscription.end_date > today,
        Subscription.end_date <= today + timedelta(days=7)
    ).order_by(Subscription.end_date).limit(10).all()
    
    # Recent complaints
    recent_complaints = Complaint.query.filter_by(
        branch_id=branch_id
    ).order_by(Complaint.created_at.desc()).limit(5).all()
    
    # Today's sessions
    today_day_of_week = today.weekday()
    today_sessions = GymClass.query.filter(
        GymClass.branch_id == branch_id,
        GymClass.is_active == True,
        GymClass.day_of_week == today_day_of_week
    ).order_by(GymClass.start_time).all()
    
    warning_date = today + timedelta(days=30)
    
    return render_template('dashboard/branch_detail.html',
                          branch=branch,
                          brand=brand,
                          stats=stats,
                          employees=employees,
                          recent_subscriptions=recent_subscriptions,
                          expiring_soon=expiring_soon,
                          recent_complaints=recent_complaints,
                          today_sessions=today_sessions,
                          warning_date=warning_date)


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

    # 1. Urgent expiring subscriptions (48 hours) - FUTURE subscriptions only
    expiring_48h = Subscription.query.filter(
        Subscription.brand_id == brand.id,
        Subscription.status == 'active',
        Subscription.end_date > today,  # Must be in the future, not today
        Subscription.end_date <= today + timedelta(days=2)
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

    # Expiring soon (FUTURE subscriptions only)
    expiring_soon = Subscription.query.filter(
        Subscription.brand_id == brand.id,
        Subscription.status == 'active',
        Subscription.end_date > today,  # Must be in the future, not today or past
        Subscription.end_date <= today + timedelta(days=7)
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

    # Today's stats - Filter by branch if receptionist is assigned to one (include NULL for legacy data)
    if current_user.branch_id:
        today_attendance = MemberAttendance.query.filter(
            MemberAttendance.brand_id == brand.id,
            db.or_(
                MemberAttendance.branch_id == current_user.branch_id,
                MemberAttendance.branch_id.is_(None)
            ),
            db.func.date(MemberAttendance.check_in) == today
        ).count()
    else:
        today_attendance = MemberAttendance.get_today_count(brand.id)

    # Active members - Filter by branch if assigned (include NULL for legacy data)
    if current_user.branch_id:
        active_members = Member.query.filter(
            Member.brand_id == brand.id,
            db.or_(
                Member.branch_id == current_user.branch_id,
                Member.branch_id.is_(None)
            ),
            Member.is_active == True
        ).count()
    else:
        active_members = Member.query.filter_by(
            brand_id=brand.id,
            is_active=True
        ).count()

    # Today's new subscriptions - Filter by branch if assigned (include NULL for legacy data)
    if current_user.branch_id:
        today_new_subs = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            db.or_(
                Subscription.branch_id == current_user.branch_id,
                Subscription.branch_id.is_(None)
            ),
            func.date(Subscription.created_at) == today
        ).count()

        # Today's renewals for this branch (include NULL for legacy data)
        today_renewals = db.session.query(Subscription).filter(
            Subscription.brand_id == brand.id,
            db.or_(
                Subscription.branch_id == current_user.branch_id,
                Subscription.branch_id.is_(None)
            ),
            func.date(Subscription.created_at) == today,
            Subscription.member_id.in_(
                db.session.query(Subscription.member_id).filter(
                    Subscription.brand_id == brand.id
                ).group_by(Subscription.member_id).having(func.count(Subscription.id) > 1)
            )
        ).count()
    else:
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

    # === URGENT ALERTS (48 hours) === - FUTURE subscriptions only - Filter by branch if assigned (include NULL)
    if current_user.branch_id:
        expiring_48h = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            db.or_(
                Subscription.branch_id == current_user.branch_id,
                Subscription.branch_id.is_(None)
            ),
            Subscription.status == 'active',
            Subscription.end_date > today,
            Subscription.end_date <= today + timedelta(days=2)
        ).order_by(Subscription.end_date).all()

        expiring_tomorrow = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            db.or_(
                Subscription.branch_id == current_user.branch_id,
                Subscription.branch_id.is_(None)
            ),
            Subscription.status == 'active',
            Subscription.end_date == today + timedelta(days=1)
        ).all()

        expiring_soon = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            db.or_(
                Subscription.branch_id == current_user.branch_id,
                Subscription.branch_id.is_(None)
            ),
            Subscription.status == 'active',
            Subscription.end_date > today + timedelta(days=2),
            Subscription.end_date <= today + timedelta(days=7)
        ).order_by(Subscription.end_date).limit(10).all()

        suspended_subs = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            db.or_(
                Subscription.branch_id == current_user.branch_id,
                Subscription.branch_id.is_(None)
            ),
            Subscription.status == 'stopped'
        ).order_by(Subscription.stopped_at.desc()).limit(5).all()
    else:
        expiring_48h = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            Subscription.status == 'active',
            Subscription.end_date > today,
            Subscription.end_date <= today + timedelta(days=2)
        ).order_by(Subscription.end_date).all()

        expiring_tomorrow = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            Subscription.status == 'active',
            Subscription.end_date == today + timedelta(days=1)
        ).all()

        expiring_soon = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            Subscription.status == 'active',
            Subscription.end_date > today + timedelta(days=2),
            Subscription.end_date <= today + timedelta(days=7)
        ).order_by(Subscription.end_date).limit(10).all()

        suspended_subs = Subscription.query.filter(
            Subscription.brand_id == brand.id,
            Subscription.status == 'stopped'
        ).order_by(Subscription.stopped_at.desc()).limit(5).all()

    # Pending fingerprint enrollment - Filter by branch if assigned (include NULL)
    pending_enrollment = []
    if brand.uses_fingerprint:
        if current_user.branch_id:
            pending_enrollment = Member.query.filter(
                Member.brand_id == brand.id,
                db.or_(
                    Member.branch_id == current_user.branch_id,
                    Member.branch_id.is_(None)
                ),
                Member.is_active == True,
                Member.fingerprint_enrolled == False
            ).limit(10).all()
        else:
            pending_enrollment = Member.query.filter_by(
                brand_id=brand.id,
                is_active=True,
                fingerprint_enrolled=False
            ).limit(10).all()

    # Pending complaints (own brand only)
    pending_complaints = Complaint.query.filter(
        Complaint.brand_id == brand.id,
        Complaint.status.in_(['pending', 'in_progress'])
    ).order_by(Complaint.created_at.desc()).limit(5).all()

    # Today's sessions
    today_day_of_week = today.weekday()  # 0=Monday, 6=Sunday
    from datetime import datetime
    current_time = datetime.now().time()

    today_sessions = GymClass.query.filter(
        GymClass.brand_id == brand.id,
        GymClass.is_active == True,
        GymClass.day_of_week == today_day_of_week
    ).order_by(GymClass.start_time).all()

    # Enrich sessions with booking info
    for session in today_sessions:
        session.current_bookings = session.get_current_bookings_count(today)
        session.available_slots = session.max_capacity - session.current_bookings
        session.is_past = session.end_time < current_time

    # Check if daily closing done today
    closing_today = DailyClosing.query.filter_by(
        brand_id=brand.id,
        closing_date=today
    ).first()

    return render_template('dashboard/receptionist.html',
                          brand=brand,
                          today_attendance=today_attendance,
                          active_members=active_members,
                          today_new_subs=today_new_subs,
                          today_renewals=today_renewals,
                          expiring_48h=expiring_48h,
                          expiring_tomorrow=expiring_tomorrow,
                          expiring_soon=expiring_soon,
                          suspended_subs=suspended_subs,
                          pending_enrollment=pending_enrollment,
                          pending_complaints=pending_complaints,
                          today_sessions=today_sessions,
                          closing_today=closing_today)


@dashboard_bp.route('/finance-admin')
@login_required
def finance_admin():
    """Finance admin dashboard - all brands financial view"""
    if current_user.role.name != 'مدير مالية' and not current_user.is_owner:
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

    # Count employees for this brand
    employee_count = User.query.filter_by(brand_id=brand_id, is_active=True).count()

    # Service demand analytics - Revenue by service type
    from app.models.service import ServiceType
    service_performance = db.session.query(
        ServiceType.name,
        func.sum(Income.amount).label('revenue'),
        func.count(Subscription.id).label('subscription_count')
    ).join(Income, Income.service_type_id == ServiceType.id
    ).join(Subscription, Subscription.id == Income.subscription_id
    ).filter(
        Income.brand_id == brand_id,
        Income.date >= start_date,
        Income.date <= end_date
    ).group_by(ServiceType.id, ServiceType.name
    ).order_by(func.sum(Income.amount).desc()).all()

    # Payment method distribution
    payment_distribution = db.session.query(
        Income.payment_method,
        func.sum(Income.amount).label('amount')
    ).filter(
        Income.brand_id == brand_id,
        Income.date >= start_date,
        Income.date <= end_date
    ).group_by(Income.payment_method).all()

    # Gift card analytics
    from app.models.giftcard import GiftCard
    gift_cards_sold = GiftCard.query.filter(
        GiftCard.brand_id == brand_id,
        func.date(GiftCard.created_at) >= start_date,
        func.date(GiftCard.created_at) <= end_date
    ).count()

    gift_card_revenue = db.session.query(func.sum(GiftCard.original_amount)).filter(
        GiftCard.brand_id == brand_id,
        func.date(GiftCard.created_at) >= start_date,
        func.date(GiftCard.created_at) <= end_date
    ).scalar() or 0

    gift_cards_redeemed = GiftCard.query.filter(
        GiftCard.brand_id == brand_id,
        GiftCard.status == 'redeemed',
        func.date(GiftCard.redeemed_at) >= start_date,
        func.date(GiftCard.redeemed_at) <= end_date
    ).count()

    outstanding_liability = db.session.query(func.sum(GiftCard.remaining_amount)).filter(
        GiftCard.brand_id == brand_id,
        GiftCard.status.in_(['active', 'partially_used'])
    ).scalar() or 0

    return {
        'members': members,
        'active_subscriptions': active_subscriptions,
        'income': income,
        'expenses': expenses,
        'profit': income - expenses,
        'today_attendance': today_attendance,
        'employee_count': employee_count,
        'service_performance': service_performance,
        'payment_distribution': payment_distribution,
        'gift_cards': {
            'sold': gift_cards_sold,
            'revenue': float(gift_card_revenue),
            'redeemed': gift_cards_redeemed,
            'redemption_rate': round((gift_cards_redeemed / gift_cards_sold * 100) if gift_cards_sold > 0 else 0, 1),
            'outstanding_liability': float(outstanding_liability)
        }
    }
