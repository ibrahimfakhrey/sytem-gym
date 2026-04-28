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
from app.utils.decorators import members_required
from app.utils.helpers import save_uploaded_file, pagination_args


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

    # Search filter
    if search:
        query = query.filter(
            db.or_(
                Member.name.ilike(f'%{search}%'),
                Member.phone.ilike(f'%{search}%'),
                Member.email.ilike(f'%{search}%')
            )
        )

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
            return render_template('members/form.html', form=form, brand=brand)
        
        # Check phone uniqueness in brand
        existing = Member.query.filter_by(
            brand_id=brand_id,
            phone=form.phone.data
        ).first()
        if existing:
            flash('رقم الهاتف مسجل مسبقاً في هذا البراند', 'danger')
            return render_template('members/form.html', form=form, brand=brand)

        member = Member(
            brand_id=brand_id,
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

        # Generate fingerprint_id if brand uses fingerprint
        if brand.uses_fingerprint:
            # Get max fingerprint_id for this brand and add 1
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

    return render_template('members/form.html', form=form, brand=brand)


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
    member = Member.query.get_or_404(member_id)

    if not current_user.can_access_brand(member.brand_id):
        flash('ليس لديك صلاحية لتعديل هذا العضو', 'danger')
        return redirect(url_for('members.index'))

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
            return render_template('members/form.html', form=form, member=member, brand=member.brand)

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

    return render_template('members/form.html', form=form, member=member, brand=member.brand)


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
