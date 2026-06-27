from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SelectField, PasswordField, IntegerField
from wtforms.validators import DataRequired, Email, Optional
from wtforms import DecimalField

from app import db
from app.models.company import Company, Brand, Branch
from app.models.user import User, Role
from app.models.subscription import Plan
from app.models.service import ServiceType
from app.forms import BranchForm
from app.utils.decorators import owner_required, brand_manager_required, branch_manager_required
from app.utils.helpers import save_uploaded_file, delete_uploaded_file

admin_bp = Blueprint('admin', __name__)


# ============== Forms ==============

class BrandForm(FlaskForm):
    """Brand form"""
    name = StringField('اسم البراند', validators=[DataRequired()])
    name_en = StringField('اسم البراند (إنجليزي)')
    description = StringField('الوصف')
    is_active = BooleanField('مفعل', default=True)


class UserForm(FlaskForm):
    """User form"""
    name = StringField('الاسم', validators=[DataRequired()])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    phone = StringField('الهاتف')
    role_id = SelectField('الدور', coerce=int, validators=[Optional()])
    brand_id = SelectField('البراند', coerce=int, validators=[Optional()])
    branch_id = SelectField('الفرع', coerce=int, validators=[Optional()])
    password = PasswordField('كلمة المرور')
    salary_type = SelectField('نوع الراتب', choices=[('', 'اختر'), ('fixed', 'ثابت'), ('daily', 'يومي')], validators=[Optional()])
    salary_amount = DecimalField('مبلغ الراتب', validators=[Optional()])
    is_trainer = BooleanField('مدرب (يمكن إسناد كلاسات له)', default=False)
    is_active = BooleanField('مفعل', default=True)


class PlanForm(FlaskForm):
    """Plan form"""
    name = StringField('اسم الباقة', validators=[DataRequired()])
    description = StringField('الوصف')
    service_type_id = SelectField('نوع الخدمة', coerce=int, validators=[Optional()])
    duration_days = IntegerField('المدة (بالأيام)', validators=[DataRequired()])
    price = DecimalField('السعر', validators=[DataRequired()])
    max_freezes = IntegerField('عدد مرات التجميد', default=1)
    max_freeze_days = IntegerField('أقصى أيام تجميد', default=14)
    freeze_is_paid = BooleanField('التجميد مدفوع')
    freeze_daily_rate = DecimalField('رسوم التجميد اليومية', default=0, validators=[Optional()])
    requires_class_booking = BooleanField('يتطلب حجز كلاس')
    is_active = BooleanField('مفعل', default=True)


class ServiceTypeForm(FlaskForm):
    """Service type form"""
    name = StringField('اسم الخدمة (عربي)', validators=[DataRequired()])
    name_en = StringField('اسم الخدمة (إنجليزي)')
    category = SelectField('التصنيف', choices=[
        ('gym', 'جيم'),
        ('swimming', 'سباحة'),
        ('karate', 'كاراتيه'),
        ('salon', 'صالون'),
        ('package', 'باقة متعددة')
    ])
    description = StringField('الوصف')
    requires_class_booking = BooleanField('يتطلب حجز كلاس')
    capacity = IntegerField('السعة', validators=[Optional()])
    is_active = BooleanField('مفعل', default=True)


# ============== Brands ==============

@admin_bp.route('/brands')
@login_required
@owner_required
def brands_list():
    """List all brands"""
    brands = Brand.query.order_by(Brand.created_at.desc()).all()
    return render_template('admin/brands/index.html', brands=brands)


@admin_bp.route('/brands/create', methods=['GET', 'POST'])
@login_required
@owner_required
def brands_create():
    """Create new brand"""
    form = BrandForm()

    if form.validate_on_submit():
        # Get or create company
        company = Company.query.first()
        if not company:
            company = Company(name='الشركة الرئيسية')
            db.session.add(company)
            db.session.commit()

        brand = Brand(
            company_id=company.id,
            name=form.name.data,
            is_active=form.is_active.data
        )

        # Handle logo upload
        if 'logo' in request.files:
            logo_file = request.files['logo']
            if logo_file.filename:
                logo_path = save_uploaded_file(logo_file, 'logos')
                if logo_path:
                    brand.logo = logo_path

        db.session.add(brand)
        db.session.commit()

        # Auto-seed default service types for new brand
        from app.models.service import ServiceType
        ServiceType.seed_defaults(brand.id)

        flash(f'تم إنشاء البراند "{brand.name}" بنجاح', 'success')
        return redirect(url_for('admin.brands_list'))

    return render_template('admin/brands/form.html', form=form)


@admin_bp.route('/brands/<int:brand_id>/edit', methods=['GET', 'POST'])
@login_required
@owner_required
def brands_edit(brand_id):
    """Edit brand"""
    brand = Brand.query.get_or_404(brand_id)
    form = BrandForm(obj=brand)

    if form.validate_on_submit():
        brand.name = form.name.data
        brand.is_active = form.is_active.data

        # Handle logo upload
        if 'logo' in request.files:
            logo_file = request.files['logo']
            if logo_file.filename:
                # Delete old logo
                if brand.logo:
                    delete_uploaded_file(brand.logo)
                logo_path = save_uploaded_file(logo_file, 'logos')
                if logo_path:
                    brand.logo = logo_path

        db.session.commit()
        flash('تم تحديث البراند بنجاح', 'success')
        return redirect(url_for('admin.brands_list'))

    return render_template('admin/brands/form.html', form=form, brand=brand)


# ============== Branches ==============

@admin_bp.route('/brands/<int:brand_id>/branches')
@login_required
def branches_list(brand_id):
    """List branches for brand"""
    from datetime import date, timedelta
    
    brand = Brand.query.get_or_404(brand_id)

    if not current_user.can_access_brand(brand_id):
        flash('ليس لديك صلاحية للوصول لهذا البراند', 'danger')
        return redirect(url_for('dashboard.index'))

    branches = Branch.query.filter_by(brand_id=brand_id).all()
    
    # Pass dates for template calculations
    today = date.today()
    warning_date = today + timedelta(days=30)
    
    return render_template('admin/branches/list.html', 
                          brand=brand, 
                          branches=branches,
                          today=today,
                          warning_date=warning_date)


@admin_bp.route('/brands/<int:brand_id>/branches/create', methods=['GET', 'POST'])
@login_required
@brand_manager_required
def branches_create(brand_id):
    """Create new branch"""
    brand = Brand.query.get_or_404(brand_id)

    if not current_user.can_access_brand(brand_id):
        flash('ليس لديك صلاحية للوصول لهذا البراند', 'danger')
        return redirect(url_for('dashboard.index'))

    form = BranchForm()

    if form.validate_on_submit():
        # GYM-19: only admins can write fingerprint hardware fields.
        # Brand owners' POSTs for these fields are ignored.
        admin_writes_fp = current_user.is_owner
        branch = Branch(
            brand_id=brand_id,
            name=form.name.data,
            address=form.address.data,
            phone=form.phone.data,
            gym_capacity=form.gym_capacity.data,
            pool_capacity=form.pool_capacity.data,
            uses_fingerprint=form.uses_fingerprint.data if admin_writes_fp else False,
            fingerprint_ip=(form.fingerprint_ip.data if (admin_writes_fp and form.uses_fingerprint.data) else None),
            fingerprint_port=(form.fingerprint_port.data if (admin_writes_fp and form.uses_fingerprint.data) else 5005),
            lease_expiry_date=form.lease_expiry_date.data,
            commercial_registration_expiry=form.commercial_registration_expiry.data,
            is_active=form.is_active.data
        )
        db.session.add(branch)
        db.session.flush()  # Get the ID before commit

        # Auto-generate branch code
        branch.branch_code = f"BR-{brand_id}-{branch.id}"
        db.session.commit()

        flash(f'تم إنشاء الفرع بنجاح - رمز الفرع: {branch.branch_code}', 'success')
        return redirect(url_for('admin.branches_list', brand_id=brand_id))

    return render_template('admin/branches/create.html', form=form, brand=brand)


@admin_bp.route('/branches/<int:branch_id>/edit', methods=['GET', 'POST'])
@login_required
@brand_manager_required
def branches_edit(branch_id):
    """Edit branch"""
    branch = Branch.query.get_or_404(branch_id)
    brand = branch.brand

    if not current_user.can_access_brand(brand.id):
        flash('ليس لديك صلاحية للوصول لهذا البراند', 'danger')
        return redirect(url_for('dashboard.index'))

    form = BranchForm(obj=branch)

    if form.validate_on_submit():
        # GYM-19: only admins may overwrite fingerprint hardware fields.
        admin_writes_fp = current_user.is_owner
        branch.name = form.name.data
        branch.address = form.address.data
        branch.phone = form.phone.data
        branch.gym_capacity = form.gym_capacity.data
        branch.pool_capacity = form.pool_capacity.data
        if admin_writes_fp:
            branch.uses_fingerprint = form.uses_fingerprint.data
            branch.fingerprint_ip = form.fingerprint_ip.data if form.uses_fingerprint.data else None
            branch.fingerprint_port = form.fingerprint_port.data if form.uses_fingerprint.data else 5005
        branch.lease_expiry_date = form.lease_expiry_date.data
        branch.commercial_registration_expiry = form.commercial_registration_expiry.data
        branch.is_active = form.is_active.data

        db.session.commit()

        flash('تم تحديث الفرع بنجاح', 'success')
        return redirect(url_for('admin.branches_list', brand_id=brand.id))

    return render_template('admin/branches/edit.html', form=form, branch=branch, brand=brand)


# ============== Users ==============

@admin_bp.route('/users')
@login_required
@branch_manager_required
def users_list():
    """List users"""
    # Hide admin and finance_admin from non-admin
    hidden_roles = Role.query.filter(Role.name_en.in_(['admin', 'finance_admin'])).all()
    hidden_role_ids = [r.id for r in hidden_roles]

    if current_user.is_owner:  # admin sees all (GYM-43: hide soft-deleted)
        users = User.query.filter(User.is_deleted == False).order_by(User.created_at.desc()).all()
    elif (current_user.is_brand_manager or current_user.is_branch_manager) and current_user.brand_id:
        # Owner/branch_manager sees brand users (except admin/finance_admin)
        query = User.query.filter(
            User.brand_id == current_user.brand_id,
            User.is_deleted == False,  # GYM-43
            ~User.role_id.in_(hidden_role_ids)
        )
        # Branch manager with branch_id sees only their branch
        if current_user.is_branch_manager and current_user.branch_id:
            query = query.filter(
                db.or_(User.branch_id == current_user.branch_id, User.branch_id.is_(None))
            )
        users = query.all()
    else:
        flash('ليس لديك صلاحية لإدارة المستخدمين', 'danger')
        return redirect(url_for('dashboard.index'))

    return render_template('admin/users/index.html', users=users)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@branch_manager_required
def users_create():
    """Create new user"""
    form = UserForm()

    # Populate choices - filter roles based on current user level
    # Hidden roles: admin, finance_admin (only admin can assign these)
    if current_user.is_owner:  # admin sees all
        roles = Role.query.all()
    elif current_user.role.name_en == 'owner':  # brand owner
        roles = Role.query.filter(
            Role.name_en.in_(['branch_manager', 'brand_finance', 'branch_finance', 'branch_receptionist', 'employee'])
        ).all()
    elif current_user.role.name_en == 'branch_manager':  # branch manager
        roles = Role.query.filter(
            Role.name_en.in_(['branch_finance', 'branch_receptionist', 'employee'])
        ).all()
    else:
        roles = []
    form.role_id.choices = [(0, '-- اختر الدور --')] + [(r.id, r.name) for r in roles]

    # Brand choices and branch choices, locked based on current user's level
    if current_user.is_owner:  # admin — sees all brands and all branches
        form.brand_id.choices = [(0, '-- بدون براند --')] + [(b.id, b.name) for b in Brand.query.filter_by(is_active=True).all()]
        all_branches = Branch.query.filter_by(is_active=True).all()
        form.branch_id.choices = [(0, '-- بدون فرع --')] + [(b.id, b.name) for b in all_branches]
    elif current_user.role.name_en == 'owner':  # brand owner — locked to own brand, all branches in brand
        form.brand_id.choices = [(current_user.brand_id, current_user.brand.name)]
        branches = Branch.query.filter_by(brand_id=current_user.brand_id, is_active=True).all()
        form.branch_id.choices = [(0, '-- بدون فرع --')] + [(b.id, b.name) for b in branches]
    else:  # branch manager — locked to own brand and own branch
        form.brand_id.choices = [(current_user.brand_id, current_user.brand.name)]
        if current_user.branch_id:
            form.branch_id.choices = [(current_user.branch_id, current_user.branch.name)]
        else:
            form.branch_id.choices = [(0, '-- بدون فرع --')]

    # Pre-select brand from query parameter (when coming from dashboard)
    if request.method == 'GET':
        preselect_brand_id = request.args.get('brand_id', type=int)
        if preselect_brand_id and current_user.is_owner:
            form.brand_id.data = preselect_brand_id
        # For non-admin, default to current user's brand
        if not current_user.is_owner:
            form.brand_id.data = current_user.brand_id
            # Branch manager: also pre-select their branch
            if current_user.role.name_en == 'branch_manager' and current_user.branch_id:
                form.branch_id.data = current_user.branch_id

    if form.validate_on_submit():
        # Validate role
        if not form.role_id.data or form.role_id.data == 0:
            flash('يرجى اختيار الدور', 'danger')
            return render_template('admin/users/form.html', form=form)

        # Force brand to current user's brand for non-admin (defense in depth)
        if not current_user.is_owner:
            form.brand_id.data = current_user.brand_id
            # Branch manager: force their own branch
            if current_user.role.name_en == 'branch_manager' and current_user.branch_id:
                form.branch_id.data = current_user.branch_id

        # Branch-level roles must have a branch assigned
        selected_role = Role.query.get(form.role_id.data)
        branch_required_roles = ['branch_manager', 'branch_finance', 'branch_receptionist']
        if selected_role and selected_role.name_en in branch_required_roles:
            if not form.branch_id.data or form.branch_id.data == 0:
                flash(f'الدور "{selected_role.name}" يتطلب اختيار فرع', 'danger')
                return render_template('admin/users/form.html', form=form)

        # Validate password
        if not form.password.data or len(form.password.data) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
            return render_template('admin/users/form.html', form=form)

        # Check email uniqueness
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash('البريد الإلكتروني مستخدم مسبقاً', 'danger')
            return render_template('admin/users/form.html', form=form)

        user = User(
            name=form.name.data,
            email=form.email.data.lower(),
            phone=form.phone.data,
            role_id=form.role_id.data,
            brand_id=form.brand_id.data if form.brand_id.data != 0 else None,
            branch_id=form.branch_id.data if form.branch_id.data != 0 else None,
            salary_type=form.salary_type.data if form.salary_type.data else None,
            salary_amount=form.salary_amount.data,
            is_trainer=form.is_trainer.data,
            is_active=form.is_active.data
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.commit()

        flash('تم إنشاء المستخدم بنجاح', 'success')
        return redirect(url_for('admin.users_list'))

    return render_template('admin/users/form.html', form=form)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@branch_manager_required
def users_edit(user_id):
    """Edit user"""
    user = User.query.get_or_404(user_id)

    # Check permissions — can't edit users at or above your level
    if not current_user.is_owner:
        if user.brand_id != current_user.brand_id:
            flash('ليس لديك صلاحية لتعديل هذا المستخدم', 'danger')
            return redirect(url_for('admin.users_list'))
        if user.role and current_user.role and user.role.role_level >= current_user.role.role_level:
            flash('لا يمكنك تعديل مستخدم بنفس مستواك أو أعلى', 'danger')
            return redirect(url_for('admin.users_list'))

    form = UserForm(obj=user)

    # Populate choices - filter roles based on current user level
    if current_user.is_owner:
        roles = Role.query.all()
    elif current_user.role.name_en == 'owner':
        roles = Role.query.filter(
            Role.name_en.in_(['branch_manager', 'brand_finance', 'branch_finance', 'branch_receptionist', 'employee'])
        ).all()
    elif current_user.role.name_en == 'branch_manager':
        roles = Role.query.filter(
            Role.name_en.in_(['branch_finance', 'branch_receptionist', 'employee'])
        ).all()
    else:
        roles = []
    form.role_id.choices = [(0, '-- اختر الدور --')] + [(r.id, r.name) for r in roles]

    # Brand choices and branch choices, locked based on current user's level
    if current_user.is_owner:  # admin — sees all brands and all branches
        form.brand_id.choices = [(0, '-- بدون براند --')] + [(b.id, b.name) for b in Brand.query.filter_by(is_active=True).all()]
        all_branches = Branch.query.filter_by(is_active=True).all()
        form.branch_id.choices = [(0, '-- بدون فرع --')] + [(b.id, b.name) for b in all_branches]
    elif current_user.role.name_en == 'owner':  # brand owner — locked to own brand
        form.brand_id.choices = [(current_user.brand_id, current_user.brand.name)]
        branches = Branch.query.filter_by(brand_id=current_user.brand_id, is_active=True).all()
        form.branch_id.choices = [(0, '-- بدون فرع --')] + [(b.id, b.name) for b in branches]
    else:  # branch manager — locked to own brand and own branch
        form.brand_id.choices = [(current_user.brand_id, current_user.brand.name)]
        if current_user.branch_id:
            form.branch_id.choices = [(current_user.branch_id, current_user.branch.name)]
        else:
            form.branch_id.choices = [(0, '-- بدون فرع --')]

    # Make password optional for edit
    form.password.validators = []

    if form.validate_on_submit():
        # Validate role
        if not form.role_id.data or form.role_id.data == 0:
            flash('يرجى اختيار الدور', 'danger')
            return render_template('admin/users/form.html', form=form, user=user, edit=True)

        # Force brand to current user's brand for non-admin
        if not current_user.is_owner:
            form.brand_id.data = current_user.brand_id
            if current_user.role.name_en == 'branch_manager' and current_user.branch_id:
                form.branch_id.data = current_user.branch_id

        # Branch-level roles must have a branch assigned
        selected_role = Role.query.get(form.role_id.data)
        branch_required_roles = ['branch_manager', 'branch_finance', 'branch_receptionist']
        if selected_role and selected_role.name_en in branch_required_roles:
            if not form.branch_id.data or form.branch_id.data == 0:
                flash(f'الدور "{selected_role.name}" يتطلب اختيار فرع', 'danger')
                return render_template('admin/users/form.html', form=form, user=user, edit=True)

        # Check email uniqueness (exclude current user)
        existing_user = User.query.filter_by(email=form.email.data.lower()).first()
        if existing_user and existing_user.id != user.id:
            flash('البريد الإلكتروني مستخدم مسبقاً', 'danger')
            return render_template('admin/users/form.html', form=form, user=user, edit=True)

        # Update user
        user.name = form.name.data
        user.email = form.email.data.lower()
        user.phone = form.phone.data
        user.role_id = form.role_id.data
        user.brand_id = form.brand_id.data if form.brand_id.data != 0 else None
        user.branch_id = form.branch_id.data if form.branch_id.data != 0 else None
        user.salary_type = form.salary_type.data if form.salary_type.data else None
        user.salary_amount = form.salary_amount.data
        user.is_trainer = form.is_trainer.data
        user.is_active = form.is_active.data

        # Update password only if provided
        if form.password.data and len(form.password.data) >= 6:
            user.set_password(form.password.data)

        db.session.commit()

        flash('تم تحديث المستخدم بنجاح', 'success')
        return redirect(url_for('admin.users_list'))

    return render_template('admin/users/form.html', form=form, user=user, edit=True)


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@branch_manager_required
def users_reset_password(user_id):
    """Reset a user's password — only for users below your role level"""
    user = User.query.get_or_404(user_id)

    # Prevent resetting your own password from this page (use profile instead)
    if user.id == current_user.id:
        flash('لا يمكنك إعادة تعيين كلمة مرورك من هنا، استخدم صفحة الملف الشخصي', 'danger')
        return redirect(url_for('admin.users_list'))

    # Permission check — same rules as edit/delete
    if not current_user.is_owner:
        if user.brand_id != current_user.brand_id:
            flash('ليس لديك صلاحية لإعادة تعيين كلمة مرور هذا المستخدم', 'danger')
            return redirect(url_for('admin.users_list'))
        if user.role and current_user.role and user.role.role_level >= current_user.role.role_level:
            flash('لا يمكنك إعادة تعيين كلمة مرور مستخدم بنفس مستواك أو أعلى', 'danger')
            return redirect(url_for('admin.users_list'))

    new_password = request.form.get('new_password', '').strip()
    if not new_password or len(new_password) < 6:
        flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
        return redirect(url_for('admin.users_list'))

    user.set_password(new_password)
    db.session.commit()
    flash(f'تم إعادة تعيين كلمة المرور للمستخدم {user.name} بنجاح', 'success')
    return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@branch_manager_required
def users_delete(user_id):
    """Delete user"""
    user = User.query.get_or_404(user_id)

    # Prevent self-deletion
    if user.id == current_user.id:
        flash('لا يمكنك حذف حسابك الشخصي', 'danger')
        return redirect(url_for('admin.users_list'))

    # Permission check — mirror users_edit logic
    if not current_user.is_owner:
        if user.brand_id != current_user.brand_id:
            flash('ليس لديك صلاحية لحذف هذا المستخدم', 'danger')
            return redirect(url_for('admin.users_list'))
        if user.role and current_user.role and user.role.role_level >= current_user.role.role_level:
            flash('لا يمكنك حذف مستخدم بنفس مستواك أو أعلى', 'danger')
            return redirect(url_for('admin.users_list'))

    # GYM-43 — soft-delete. Linked records (members created, subscriptions,
    # attendance, salaries) are preserved because the row stays in the DB.
    # is_deleted=True hides the user from lists, blocks login, and excludes
    # them from staff-performance + employee aggregations. Reversible by
    # flipping the flag back via SQL.
    user.is_deleted = True
    user.is_active = False  # also flip the legacy flag so login fails immediately
    db.session.commit()
    flash(f'تم حذف المستخدم "{user.name}". (سجلاته محفوظة، لن يظهر في القوائم ولن يستطيع تسجيل الدخول.)', 'success')
    return redirect(url_for('admin.users_list'))


# ============== Plans ==============

@admin_bp.route('/plans')
@login_required
@brand_manager_required
def plans_list():
    """List plans"""
    brands = []

    if current_user.is_owner:
        plans = Plan.query.order_by(Plan.brand_id, Plan.created_at.desc()).all()
        brands = Brand.query.filter_by(is_active=True).all()
    elif current_user.brand_id:
        plans = Plan.query.filter_by(brand_id=current_user.brand_id).all()
    else:
        plans = []

    return render_template('admin/plans/index.html', plans=plans, brands=brands)


@admin_bp.route('/plans/create', methods=['GET', 'POST'])
@login_required
@brand_manager_required
def plans_create():
    """Create new plan"""
    form = PlanForm()

    # Get brand_id
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            flash('يرجى اختيار البراند أولاً', 'warning')
            return redirect(url_for('admin.brands_list'))
    else:
        brand_id = current_user.brand_id

    brand = Brand.query.get_or_404(brand_id)

    # Populate service type choices
    service_types = ServiceType.query.filter_by(brand_id=brand_id, is_active=True).all()
    form.service_type_id.choices = [(0, '-- بدون نوع خدمة محدد --')] + [(st.id, st.name) for st in service_types]

    if form.validate_on_submit():
        plan = Plan(
            brand_id=brand_id,
            name=form.name.data,
            description=form.description.data,
            service_type_id=form.service_type_id.data if form.service_type_id.data != 0 else None,
            duration_days=form.duration_days.data,
            price=form.price.data,
            max_freezes=form.max_freezes.data,
            max_freeze_days=form.max_freeze_days.data,
            freeze_is_paid=form.freeze_is_paid.data,
            freeze_daily_rate=form.freeze_daily_rate.data or 0,
            requires_class_booking=form.requires_class_booking.data,
            is_active=form.is_active.data
        )
        db.session.add(plan)
        db.session.commit()

        flash('تم إنشاء الباقة بنجاح', 'success')
        return redirect(url_for('admin.plans_list'))

    return render_template('admin/plans/form.html', form=form, brand=brand)


@admin_bp.route('/plans/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
@brand_manager_required
def plans_edit(plan_id):
    """Edit plan"""
    plan = Plan.query.get_or_404(plan_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != plan.brand_id:
        flash('ليس لديك صلاحية لتعديل هذه الباقة', 'danger')
        return redirect(url_for('admin.plans_list'))

    form = PlanForm(obj=plan)

    # Populate service type choices
    service_types = ServiceType.query.filter_by(brand_id=plan.brand_id, is_active=True).all()
    form.service_type_id.choices = [(0, '-- بدون نوع خدمة محدد --')] + [(st.id, st.name) for st in service_types]

    if form.validate_on_submit():
        plan.name = form.name.data
        plan.description = form.description.data
        plan.duration_days = form.duration_days.data
        plan.price = form.price.data
        plan.max_freezes = form.max_freezes.data
        plan.max_freeze_days = form.max_freeze_days.data
        plan.is_active = form.is_active.data

        # New fields
        plan.service_type_id = form.service_type_id.data if form.service_type_id.data else None
        plan.freeze_is_paid = form.freeze_is_paid.data
        plan.freeze_daily_rate = form.freeze_daily_rate.data or 0
        plan.requires_class_booking = form.requires_class_booking.data

        db.session.commit()
        flash('تم تحديث الباقة بنجاح', 'success')
        return redirect(url_for('admin.plans_list'))

    # Set default value for service_type_id if editing
    if request.method == 'GET' and plan.service_type_id:
        form.service_type_id.data = plan.service_type_id

    return render_template('admin/plans/form.html', form=form, plan=plan, brand=plan.brand)


@admin_bp.route('/plans/<int:plan_id>/delete', methods=['POST'])
@login_required
@brand_manager_required
def plans_delete(plan_id):
    """GYM-14: delete a plan. Hard-delete if no subscription ever referenced
    it; soft-delete (is_active=False) otherwise so historical subscriptions
    keep their plan_id intact (the column is NOT NULL).
    """
    plan = Plan.query.get_or_404(plan_id)
    if not current_user.is_owner and current_user.brand_id != plan.brand_id:
        flash('ليس لديك صلاحية لحذف هذه الباقة', 'danger')
        return redirect(url_for('admin.plans_list'))

    used_count = plan.subscriptions.count()
    if used_count == 0:
        db.session.delete(plan)
        db.session.commit()
        flash(f'تم حذف الباقة "{plan.name}" نهائياً', 'success')
    else:
        if not plan.is_active:
            flash('الباقة معطلة بالفعل', 'info')
        else:
            plan.is_active = False
            db.session.commit()
            flash(f'تم تعطيل الباقة "{plan.name}" (تستخدم في {used_count} اشتراك ولا يمكن حذفها نهائياً)', 'warning')
    return redirect(url_for('admin.plans_list'))


# ============== Service Types ==============

@admin_bp.route('/service-types')
@login_required
@brand_manager_required
def service_types_list():
    """List service types"""
    brands = []

    if current_user.is_owner:
        service_types = ServiceType.query.order_by(ServiceType.brand_id, ServiceType.name).all()
        brands = Brand.query.filter_by(is_active=True).all()
    elif current_user.brand_id:
        service_types = ServiceType.query.filter_by(brand_id=current_user.brand_id).all()
    else:
        service_types = []

    return render_template('admin/service_types/index.html', service_types=service_types, brands=brands)


@admin_bp.route('/service-types/create', methods=['GET', 'POST'])
@login_required
@brand_manager_required
def service_types_create():
    """Create new service type"""
    form = ServiceTypeForm()

    # Get brand_id
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            flash('يرجى اختيار البراند أولاً', 'warning')
            return redirect(url_for('admin.brands_list'))
    else:
        brand_id = current_user.brand_id

    brand = Brand.query.get_or_404(brand_id)

    if form.validate_on_submit():
        service_type = ServiceType(
            brand_id=brand_id,
            name=form.name.data,
            name_en=form.name_en.data,
            category=form.category.data,
            description=form.description.data,
            requires_class_booking=form.requires_class_booking.data,
            capacity=form.capacity.data,
            is_active=form.is_active.data
        )
        db.session.add(service_type)
        db.session.commit()

        flash('تم إنشاء نوع الخدمة بنجاح', 'success')
        return redirect(url_for('admin.service_types_list'))

    return render_template('admin/service_types/form.html', form=form, brand=brand)


@admin_bp.route('/service-types/<int:service_type_id>/edit', methods=['GET', 'POST'])
@login_required
@brand_manager_required
def service_types_edit(service_type_id):
    """Edit service type"""
    service_type = ServiceType.query.get_or_404(service_type_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != service_type.brand_id:
        flash('ليس لديك صلاحية لتعديل نوع الخدمة هذا', 'danger')
        return redirect(url_for('admin.service_types_list'))

    form = ServiceTypeForm(obj=service_type)

    if form.validate_on_submit():
        service_type.name = form.name.data
        service_type.name_en = form.name_en.data
        service_type.category = form.category.data
        service_type.description = form.description.data
        service_type.requires_class_booking = form.requires_class_booking.data
        service_type.capacity = form.capacity.data
        service_type.is_active = form.is_active.data

        db.session.commit()
        flash('تم تحديث نوع الخدمة بنجاح', 'success')
        return redirect(url_for('admin.service_types_list'))

    return render_template('admin/service_types/form.html', form=form, service_type=service_type, brand=service_type.brand)


@admin_bp.route('/service-types/<int:service_type_id>/delete', methods=['POST'])
@login_required
@brand_manager_required
def service_types_delete(service_type_id):
    """Delete service type"""
    service_type = ServiceType.query.get_or_404(service_type_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != service_type.brand_id:
        flash('ليس لديك صلاحية لحذف نوع الخدمة هذا', 'danger')
        return redirect(url_for('admin.service_types_list'))

    # Check if used by plans
    if service_type.plans.count() > 0:
        flash('لا يمكن حذف نوع الخدمة لوجود باقات مرتبطة به', 'danger')
        return redirect(url_for('admin.service_types_list'))

    db.session.delete(service_type)
    db.session.commit()
    flash('تم حذف نوع الخدمة بنجاح', 'success')
    return redirect(url_for('admin.service_types_list'))


@admin_bp.route('/service-types/seed/<int:brand_id>', methods=['POST'])
@login_required
@brand_manager_required
def service_types_seed(brand_id):
    """Seed default service types for a brand"""
    brand = Brand.query.get_or_404(brand_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != brand_id:
        flash('ليس لديك صلاحية للوصول لهذا البراند', 'danger')
        return redirect(url_for('admin.service_types_list'))

    ServiceType.seed_defaults(brand_id)
    flash('تم إضافة أنواع الخدمات الافتراضية بنجاح', 'success')
    return redirect(url_for('admin.service_types_list'))


@admin_bp.route('/api/branches/<int:brand_id>')
@login_required
def api_branches(brand_id):
    """API endpoint to get branches for a brand"""
    from flask import jsonify
    branches = Branch.query.filter_by(brand_id=brand_id, is_active=True).all()
    return jsonify([{
        'id': b.id,
        'name': b.name
    } for b in branches])
