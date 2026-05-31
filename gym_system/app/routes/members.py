from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DateField, TextAreaField, BooleanField, FloatField
from wtforms.validators import DataRequired, Email, Optional, NumberRange
from app.utils.helpers import apply_branch_filter, check_entity_access

from app import db
from app.models.company import Brand, Branch
from app.models.member import Member
from app.models.blocked_member import BlockedMember
from app.models.subscription import Subscription
from app.models.health import HealthReport
from app.models.complaint import Complaint
from app.models.user import User, Role
from app.utils.decorators import members_required
from app.utils.helpers import save_uploaded_file, pagination_args
import secrets


class BlockMemberForm(FlaskForm):
    """Block member form"""
    reason = SelectField('سبب الحظر', choices=[
        ('behavior', 'سلوك سيء'),
        ('violence', 'عنف أو تحرش'),
        ('theft', 'سرقة'),
        ('damage', 'إتلاف ممتلكات'),
        ('fraud', 'احتيال'),
        ('rules', 'مخالفة القوانين'),
        ('other', 'أخرى')
    ], validators=[DataRequired()])
    details = TextAreaField('تفاصيل إضافية', validators=[DataRequired()])

members_bp = Blueprint('members', __name__)


class MemberForm(FlaskForm):
    """Member form"""
    name = StringField('الاسم', validators=[DataRequired()])
    phone = StringField('رقم الهاتف', validators=[DataRequired()])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email()])
    gender = SelectField('الجنس', choices=[('', 'اختر'), ('male', 'ذكر'), ('female', 'أنثى')])
    birth_date = DateField('تاريخ الميلاد', validators=[Optional()])
    national_id = StringField('رقم الهوية')
    address = TextAreaField('العنوان')
    emergency_contact = StringField('جهة اتصال للطوارئ')
    emergency_phone = StringField('هاتف الطوارئ')
    # Health measurements
    height_cm = FloatField('الطول (سم)', validators=[Optional(), NumberRange(min=50, max=250)])
    weight_kg = FloatField('الوزن (كجم)', validators=[Optional(), NumberRange(min=20, max=300)])
    notes = TextAreaField('ملاحظات')
    is_active = BooleanField('نشط', default=True)


@members_bp.route('/')
@login_required
@members_required
def index():
    """List members"""
    page, per_page = pagination_args(request)
    search = request.args.get('search', '')
    status = request.args.get('status', '')

    # Base query with brand/branch filtering
    query = apply_branch_filter(Member.query, Member)

    # Search filter — name / phone / email always, plus fingerprint_id and
    # member_import_id when the input is numeric.
    if search:
        clauses = [
            Member.name.ilike(f'%{search}%'),
            Member.phone.ilike(f'%{search}%'),
            Member.email.ilike(f'%{search}%'),
            Member.member_import_id.ilike(f'%{search}%'),
        ]
        if search.strip().isdigit():
            clauses.append(Member.fingerprint_id == int(search.strip()))
        query = query.filter(db.or_(*clauses))

    # Status filter
    if status == 'active':
        # Members with active subscription
        from app.models.subscription import Subscription
        from datetime import date
        active_member_ids = db.session.query(Subscription.member_id).filter(
            Subscription.status == 'active',
            Subscription.end_date >= date.today()
        ).distinct()
        query = query.filter(Member.id.in_(active_member_ids))
    elif status == 'expired':
        # Members with expired subscription
        from app.models.subscription import Subscription
        from datetime import date
        expired_member_ids = db.session.query(Subscription.member_id).filter(
            db.or_(
                Subscription.status == 'expired',
                Subscription.end_date < date.today()
            )
        ).distinct()
        active_member_ids = db.session.query(Subscription.member_id).filter(
            Subscription.status == 'active',
            Subscription.end_date >= date.today()
        ).distinct()
        query = query.filter(Member.id.in_(expired_member_ids), ~Member.id.in_(active_member_ids))
    elif status == 'frozen':
        # Members with frozen subscription
        from app.models.subscription import Subscription
        frozen_member_ids = db.session.query(Subscription.member_id).filter(
            Subscription.status == 'frozen'
        ).distinct()
        query = query.filter(Member.id.in_(frozen_member_ids))
    elif status == 'no_subscription':
        # Members without any subscription
        from app.models.subscription import Subscription
        members_with_subs = db.session.query(Subscription.member_id).distinct()
        query = query.filter(~Member.id.in_(members_with_subs))
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    # Pagination
    members = query.order_by(Member.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter (owner only)
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('members/index.html',
                          members=members,
                          brands=brands,
                          search=search,
                          status=status)


@members_bp.route('/create', methods=['GET', 'POST'])
@login_required
@members_required
def create():
    """Create new member"""
    from app.models.company import Branch
    form = MemberForm()

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            flash('يرجى اختيار البراند أولاً', 'warning')
            return redirect(url_for('admin.brands_list'))
        brand = Brand.query.get_or_404(brand_id)
    else:
        brand = current_user.brand
        brand_id = brand.id

    # Get branches for branch selection dropdown
    branches = Branch.query.filter_by(brand_id=brand_id, is_active=True).all()

    if form.validate_on_submit():
        # Check if phone or national_id is blocked
        blocked = BlockedMember.is_blocked(
            brand_id=brand_id,
            phone=form.phone.data,
            national_id=form.national_id.data if form.national_id.data else None
        )
        if blocked:
            flash(f'⛔ هذا الشخص محظور من الجيم! السبب: {blocked.reason}', 'danger')
            flash(f'تاريخ الحظر: {blocked.blocked_at.strftime("%Y-%m-%d")}', 'warning')
            return render_template('members/form.html', form=form, brand=brand, branches=branches)
        
        # Check phone uniqueness in brand
        existing = Member.query.filter_by(
            brand_id=brand_id,
            phone=form.phone.data
        ).first()
        if existing:
            flash('رقم الهاتف مسجل مسبقاً في هذا البراند', 'danger')
            return render_template('members/form.html', form=form, brand=brand, branches=branches)

        # Get branch_id from form
        branch_id_val = request.form.get('branch_id', type=int)
        if not branch_id_val and current_user.branch_id:
            branch_id_val = current_user.branch_id
        if not branch_id_val and branches:
            flash('يرجى اختيار الفرع', 'danger')
            return render_template('members/form.html', form=form, brand=brand, branches=branches)

        member = Member(
            brand_id=brand_id,
            branch_id=branch_id_val,
            name=form.name.data,
            phone=form.phone.data,
            email=form.email.data,
            gender=form.gender.data if form.gender.data else None,
            birth_date=form.birth_date.data,
            national_id=form.national_id.data,
            address=form.address.data,
            emergency_contact=form.emergency_contact.data,
            emergency_phone=form.emergency_phone.data,
            height_cm=form.height_cm.data,
            weight_kg=form.weight_kg.data,
            notes=form.notes.data,
            is_active=form.is_active.data,
            created_by=current_user.id
        )

        # Generate fingerprint_id if branch uses fingerprint
        member_branch = Branch.query.get(branch_id_val) if branch_id_val else None
        if member_branch and member_branch.uses_fingerprint:
            max_fp = db.session.query(db.func.max(Member.fingerprint_id)).filter_by(
                brand_id=brand_id
            ).scalar()
            member.fingerprint_id = (max_fp or 0) + 1

        # Handle photo upload
        if 'photo' in request.files:
            photo_file = request.files['photo']
            if photo_file.filename:
                photo_path = save_uploaded_file(photo_file, 'members')
                if photo_path:
                    member.photo = photo_path

        db.session.add(member)
        db.session.commit()

        flash('تم إضافة العضو بنجاح', 'success')

        # Redirect to create subscription
        return redirect(url_for('subscriptions.create', member_id=member.id))

    return render_template('members/form.html', form=form, brand=brand, branches=branches)


@members_bp.route('/<int:member_id>')
@login_required
@members_required
def view(member_id):
    """View member details"""
    member = Member.query.get_or_404(member_id)

    if not check_entity_access(member):
        flash('ليس لديك صلاحية لعرض هذا العضو', 'danger')
        return redirect(url_for('members.index'))

    # Get subscriptions
    subscriptions = member.subscriptions.all()

    # Get attendance
    attendance = member.attendance.limit(20).all()

    # Get health reports
    health_reports = HealthReport.query.filter_by(
        member_id=member_id
    ).order_by(HealthReport.created_at.desc()).limit(5).all()

    # Get latest health report
    latest_health = health_reports[0] if health_reports else None

    # Get complaints related to this member
    complaints = Complaint.query.filter_by(
        member_id=member_id
    ).order_by(Complaint.created_at.desc()).limit(5).all()

    return render_template('members/view.html',
                          member=member,
                          subscriptions=subscriptions,
                          attendance=attendance,
                          health_reports=health_reports,
                          latest_health=latest_health,
                          complaints=complaints)


@members_bp.route('/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
@members_required
def edit(member_id):
    """Edit member"""
    from app.models.company import Branch
    member = Member.query.get_or_404(member_id)

    if not check_entity_access(member):
        flash('ليس لديك صلاحية لتعديل هذا العضو', 'danger')
        return redirect(url_for('members.index'))

    branches = Branch.query.filter_by(brand_id=member.brand_id, is_active=True).all()
    form = MemberForm(obj=member)

    if form.validate_on_submit():
        # Check phone uniqueness
        existing = Member.query.filter(
            Member.brand_id == member.brand_id,
            Member.phone == form.phone.data,
            Member.id != member_id
        ).first()
        if existing:
            flash('رقم الهاتف مسجل مسبقاً', 'danger')
            return render_template('members/form.html', form=form, member=member, brand=member.brand, branches=branches)

        member.name = form.name.data
        member.phone = form.phone.data
        member.email = form.email.data
        member.gender = form.gender.data if form.gender.data else None
        member.birth_date = form.birth_date.data
        member.national_id = form.national_id.data
        member.address = form.address.data
        member.emergency_contact = form.emergency_contact.data
        member.emergency_phone = form.emergency_phone.data
        member.height_cm = form.height_cm.data
        member.weight_kg = form.weight_kg.data
        member.notes = form.notes.data
        member.is_active = form.is_active.data

        # Handle photo upload
        if 'photo' in request.files:
            photo_file = request.files['photo']
            if photo_file.filename:
                photo_path = save_uploaded_file(photo_file, 'members')
                if photo_path:
                    member.photo = photo_path

        db.session.commit()
        flash('تم تحديث بيانات العضو بنجاح', 'success')
        return redirect(url_for('members.view', member_id=member_id))

    return render_template('members/form.html', form=form, member=member, brand=member.brand, branches=branches)


@members_bp.route('/search')
@login_required
@members_required
def search():
    """Search members (AJAX)"""
    q = request.args.get('q', '')

    if len(q) < 2:
        return {'results': []}

    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = Member.query.filter_by(brand_id=brand_id)
        else:
            query = Member.query
    else:
        query = Member.query.filter_by(brand_id=current_user.brand_id)

    members = query.filter(
        db.or_(
            Member.name.ilike(f'%{q}%'),
            Member.phone.ilike(f'%{q}%')
        )
    ).limit(10).all()

    results = [{
        'id': m.id,
        'name': m.name,
        'phone': m.phone,
        'status': m.subscription_status,
        'status_class': m.subscription_status_class
    } for m in members]

    return {'results': results}


@members_bp.route('/<int:member_id>/block', methods=['GET', 'POST'])
@login_required
@members_required
def block(member_id):
    """Block/ban a member permanently"""
    member = Member.query.get_or_404(member_id)

    if not current_user.can_access_brand(member.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('members.index'))

    form = BlockMemberForm()

    if form.validate_on_submit():
        reason_labels = {
            'behavior': 'سلوك سيء',
            'violence': 'عنف أو تحرش',
            'theft': 'سرقة',
            'damage': 'إتلاف ممتلكات',
            'fraud': 'احتيال',
            'rules': 'مخالفة القوانين',
            'other': 'أخرى'
        }
        full_reason = f"{reason_labels.get(form.reason.data, form.reason.data)}: {form.details.data}"
        
        # Create blocked member record
        blocked = BlockedMember.block_member(member, full_reason, current_user.id)
        db.session.add(blocked)
        
        # Deactivate the member
        member.is_active = False
        
        # Cancel any active subscriptions
        from app.models.subscription import Subscription
        active_subs = Subscription.query.filter_by(
            member_id=member.id,
            status='active'
        ).all()
        for sub in active_subs:
            sub.status = 'cancelled'
        
        db.session.commit()
        
        flash(f'⛔ تم حظر العضو {member.name} بشكل دائم', 'warning')
        return redirect(url_for('members.index'))

    return render_template('members/block.html', form=form, member=member)


@members_bp.route('/blocked')
@login_required
@members_required
def blocked_list():
    """List blocked members"""
    page, per_page = pagination_args(request)
    
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = BlockedMember.query.filter_by(brand_id=brand_id, is_active=True)
        else:
            query = BlockedMember.query.filter_by(is_active=True)
    else:
        query = BlockedMember.query.filter_by(brand_id=current_user.brand_id, is_active=True)
    
    blocked_members = query.order_by(BlockedMember.blocked_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()
    
    return render_template('members/blocked_list.html',
                          blocked_members=blocked_members,
                          brands=brands)


def _can_convert_employees(user):
    """Owner / branch_manager / admin can convert members to employees."""
    return user.role and user.role.name_en in ('admin', 'owner', 'branch_manager')


@members_bp.route('/<int:member_id>/convert-to-employee', methods=['GET', 'POST'])
@login_required
@members_required
def convert_to_employee(member_id):
    """
    Promote a Member to a User (employee). Re-uses the same fingerprint_id so
    their gate scans flow into BOTH MemberAttendance (entry log) and
    EmployeeAttendance (work shift, late deductions).
    """
    member = Member.query.get_or_404(member_id)

    # Permissions
    if not _can_convert_employees(current_user):
        flash('ليس لديك صلاحية لتحويل الأعضاء إلى موظفين', 'danger')
        return redirect(url_for('members.view', member_id=member_id))
    if not current_user.can_access_brand(member.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('members.view', member_id=member_id))

    # Already converted?
    if member.is_staff and member.staff_user_id:
        flash('هذا العضو موظف بالفعل', 'info')
        return redirect(url_for('members.view', member_id=member_id))

    # Branches accessible to current user (within member's brand)
    if current_user.role.name_en == 'admin':
        branches = Branch.query.filter_by(brand_id=member.brand_id, is_active=True).all()
    elif current_user.role.name_en == 'owner':
        branches = Branch.query.filter_by(brand_id=current_user.brand_id, is_active=True).all()
    else:  # branch_manager
        branches = Branch.query.filter_by(id=current_user.branch_id, is_active=True).all()

    # Roles available (employee, branch_receptionist, branch_finance — not admin/owner)
    role_names = ['employee', 'branch_receptionist', 'branch_finance']
    roles = Role.query.filter(Role.name_en.in_(role_names)).all()

    if request.method == 'POST':
        branch_id = request.form.get('branch_id', type=int)
        role_id = request.form.get('role_id', type=int)
        department = (request.form.get('department') or '').strip() or None
        is_trainer = request.form.get('is_trainer') == 'on'
        email = (request.form.get('email') or '').strip().lower()
        custom_password = (request.form.get('password') or '').strip()

        # Validate
        if not branch_id or branch_id not in [b.id for b in branches]:
            flash('يرجى اختيار فرع صحيح', 'danger')
            return render_template('members/convert_to_employee.html',
                                   member=member, branches=branches, roles=roles)
        if not role_id or role_id not in [r.id for r in roles]:
            flash('يرجى اختيار دور صحيح', 'danger')
            return render_template('members/convert_to_employee.html',
                                   member=member, branches=branches, roles=roles)

        # Auto-generate email if blank
        if not email:
            slug = (member.member_import_id or str(member.id)).strip('0') or str(member.id)
            email = f'emp_{slug}_{member.brand_id}@gym.local'

        # Email uniqueness
        if User.query.filter_by(email=email).first():
            flash(f'البريد {email} مستخدم بالفعل', 'danger')
            return render_template('members/convert_to_employee.html',
                                   member=member, branches=branches, roles=roles)

        # Random password if none provided (employee won't log in)
        password = custom_password or secrets.token_urlsafe(16)

        # Create User with same fingerprint_id
        new_user = User(
            name=member.name,
            email=email,
            role_id=role_id,
            brand_id=member.brand_id,
            branch_id=branch_id,
            fingerprint_id=member.fingerprint_id,
            is_trainer=is_trainer,
            department=department,
            is_active=True,
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush()  # get id

        # Link member ↔ user
        member.is_staff = True
        member.staff_user_id = new_user.id
        member.branch_id = branch_id  # also set member's branch to match employee
        db.session.commit()

        # Backfill EmployeeAttendance from existing fingerprint scans (last 60 days)
        try:
            from app.routes.fingerprint import backfill_employee_attendance_from_member_scans
            backfill_employee_attendance_from_member_scans(new_user, branch_id, days=60)
            db.session.commit()
        except Exception:
            db.session.rollback()  # backfill is best-effort; conversion already saved

        msg = f'✅ تم تحويل {member.name} إلى موظف. البريد: {email}'
        if not custom_password:
            msg += ' (لم يتم تعيين كلمة مرور — لا يستطيع تسجيل الدخول للموقع)'
        flash(msg, 'success')

        return redirect(url_for('members.view', member_id=member_id))

    return render_template('members/convert_to_employee.html',
                           member=member, branches=branches, roles=roles)


@members_bp.route('/<int:member_id>/toggle-access', methods=['POST'])
@login_required
@members_required
def toggle_access(member_id):
    """
    Toggle Member.is_active — temporarily suspend / resume gate access.

    The desktop bridge polls /api/v2/access-state every 60 sec; setting
    is_active=False causes the cloud to return end_date=2020-01-01 for this
    member, which the desktop writes to tmkq.mdb so the device denies entry.
    """
    member = Member.query.get_or_404(member_id)
    if not current_user.can_access_brand(member.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('members.view', member_id=member_id))

    member.is_active = not member.is_active
    db.session.commit()

    if member.is_active:
        flash(f'✅ تم استئناف وصول {member.name} للجيم. سيُسمح له بالدخول خلال دقيقة.', 'success')
    else:
        flash(f'⛔ تم إيقاف وصول {member.name} للجيم. سيُمنع من الدخول خلال دقيقة.', 'warning')

    return redirect(url_for('members.view', member_id=member_id))


@members_bp.route('/<int:member_id>/delete', methods=['POST'])
@login_required
@members_required
def delete(member_id):
    """
    Hard delete a member and everything related to them.

    Removes: subscriptions (+ freezes, payments), invoices, refunds, attendance,
    class bookings, health reports, complaints, renewal rejections, device
    commands, blocked-member records, and the photo file. Income rows and
    fingerprint access logs are kept for audit, but FKs are nulled.
    """
    member = Member.query.get_or_404(member_id)

    if not current_user.can_access_brand(member.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('members.view', member_id=member_id))

    # Only owner / admin / branch_manager may hard-delete
    role_name = current_user.role.name_en if current_user.role else None
    if not (current_user.is_owner or role_name in ['admin', 'owner', 'branch_manager']):
        flash('فقط المدير يمكنه الحذف النهائي', 'danger')
        return redirect(url_for('members.view', member_id=member_id))

    # Local imports to avoid circular references
    from app.models.attendance import MemberAttendance
    from app.models.classes import ClassBooking
    from app.models.subscription import (
        SubscriptionFreeze, SubscriptionPayment, RenewalRejection
    )
    from app.models.finance import Refund, Invoice, Income
    from app.models.giftcard import GiftCard
    from app.models.fingerprint import DeviceCommand, FingerprintAccessLog
    from app.utils.helpers import delete_uploaded_file

    member_name = member.name
    photo_path = member.photo
    sub_ids = [s.id for s in Subscription.query.filter_by(member_id=member.id).all()]

    # 1. Children that reference the subscriptions
    if sub_ids:
        SubscriptionFreeze.query.filter(SubscriptionFreeze.subscription_id.in_(sub_ids)).delete(synchronize_session=False)
        # Preserve income (financial ledger) but unlink subscription/payment
        payment_ids = [p.id for p in SubscriptionPayment.query.filter(SubscriptionPayment.subscription_id.in_(sub_ids)).all()]
        if payment_ids:
            Income.query.filter(Income.payment_id.in_(payment_ids)).update(
                {Income.payment_id: None}, synchronize_session=False)
        Income.query.filter(Income.subscription_id.in_(sub_ids)).update(
            {Income.subscription_id: None}, synchronize_session=False)
        GiftCard.query.filter(GiftCard.subscription_id.in_(sub_ids)).update(
            {GiftCard.subscription_id: None}, synchronize_session=False)
        Invoice.query.filter(Invoice.subscription_id.in_(sub_ids)).delete(synchronize_session=False)
        Refund.query.filter(Refund.subscription_id.in_(sub_ids)).delete(synchronize_session=False)
        SubscriptionPayment.query.filter(SubscriptionPayment.subscription_id.in_(sub_ids)).delete(synchronize_session=False)

    # 2. Direct member children — delete
    ClassBooking.query.filter_by(member_id=member.id).delete(synchronize_session=False)
    MemberAttendance.query.filter_by(member_id=member.id).delete(synchronize_session=False)
    HealthReport.query.filter_by(member_id=member.id).delete(synchronize_session=False)
    Complaint.query.filter_by(member_id=member.id).delete(synchronize_session=False)
    RenewalRejection.query.filter_by(member_id=member.id).delete(synchronize_session=False)
    DeviceCommand.query.filter_by(member_id=member.id).delete(synchronize_session=False)
    Invoice.query.filter_by(member_id=member.id).delete(synchronize_session=False)
    Refund.query.filter_by(member_id=member.id).delete(synchronize_session=False)

    # 3. Unlink (preserve gift card history)
    GiftCard.query.filter_by(redeemed_by_member_id=member.id).update(
        {GiftCard.redeemed_by_member_id: None}, synchronize_session=False)

    # 4. Preserve audit log rows — name/fingerprint already denormalized
    FingerprintAccessLog.query.filter_by(member_id=member.id).update(
        {FingerprintAccessLog.member_id: None}, synchronize_session=False)

    # 5. Subscriptions themselves
    Subscription.query.filter_by(member_id=member.id).delete(synchronize_session=False)

    # 6. Any blocked-member rows that point back to this member
    BlockedMember.query.filter_by(
        brand_id=member.brand_id, original_member_id=member.id
    ).delete(synchronize_session=False)

    # 7. The member row
    db.session.delete(member)
    db.session.commit()

    # 8. Photo file from disk (after commit so DB roll-back doesn't orphan)
    if photo_path:
        try:
            delete_uploaded_file(photo_path)
        except Exception:
            pass

    flash(f'🗑️ تم حذف العضو {member_name} وجميع بياناته نهائياً.', 'success')
    return redirect(url_for('members.index'))


@members_bp.route('/blocked/<int:blocked_id>/unblock', methods=['POST'])
@login_required
@members_required
def unblock(blocked_id):
    """Unblock a member (admin only)"""
    blocked = BlockedMember.query.get_or_404(blocked_id)
    
    if not current_user.can_access_brand(blocked.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('members.blocked_list'))
    
    # Only owner/admin can unblock
    if not current_user.is_owner and current_user.role.name_en not in ['admin', 'owner', 'branch_manager']:
        flash('فقط المدير يمكنه إلغاء الحظر', 'danger')
        return redirect(url_for('members.blocked_list'))
    
    from datetime import datetime
    blocked.is_active = False
    blocked.unblocked_at = datetime.utcnow()
    blocked.unblocked_by = current_user.id
    blocked.unblock_reason = request.form.get('reason', 'تم إلغاء الحظر')
    
    db.session.commit()
    
    flash(f'✅ تم إلغاء حظر {blocked.name}', 'success')
    return redirect(url_for('members.blocked_list'))
