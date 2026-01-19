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
from app.utils.decorators import owner_required, brand_manager_required
from app.utils.helpers import save_uploaded_file, delete_uploaded_file

admin_bp = Blueprint('admin', __name__)


# ============== Forms ==============

class BrandForm(FlaskForm):
    """Brand form"""
    name = StringField('اسم البراند', validators=[DataRequired()])
    name_en = StringField('اسم البراند (إنجليزي)')
    description = StringField('الوصف')
    uses_fingerprint = BooleanField('يستخدم نظام البصمة')
    fingerprint_ip = StringField('IP جهاز البصمة')
    fingerprint_port = IntegerField('Port', default=5005)
    is_active = BooleanField('مفعل', default=True)


class BranchForm(FlaskForm):
    """Branch form"""
    name = StringField('اسم الفرع', validators=[DataRequired()])
    address = StringField('العنوان')
    phone = StringField('الهاتف')
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
            uses_fingerprint=form.uses_fingerprint.data,
            fingerprint_ip=form.fingerprint_ip.data if form.uses_fingerprint.data else None,
            fingerprint_port=form.fingerprint_port.data if form.uses_fingerprint.data else 5005,
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
        brand.uses_fingerprint = form.uses_fingerprint.data
        brand.fingerprint_ip = form.fingerprint_ip.data if form.uses_fingerprint.data else None
        brand.fingerprint_port = form.fingerprint_port.data if form.uses_fingerprint.data else 5005
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
    brand = Brand.query.get_or_404(brand_id)

    if not current_user.can_access_brand(brand_id):
        flash('ليس لديك صلاحية للوصول لهذا البراند', 'danger')
        return redirect(url_for('dashboard.index'))

    branches = Branch.query.filter_by(brand_id=brand_id).all()
    return render_template('admin/branches/list.html', brand=brand, branches=branches)


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
        branch = Branch(
            brand_id=brand_id,
            name=form.name.data,
            address=form.address.data,
            phone=form.phone.data,
            is_active=form.is_active.data
        )
        db.session.add(branch)
        db.session.commit()

        flash('تم إنشاء الفرع بنجاح', 'success')
        return redirect(url_for('admin.branches_list', brand_id=brand_id))

    return render_template('admin/branches/create.html', form=form, brand=brand)


# ============== Users ==============

@admin_bp.route('/users')
@login_required
def users_list():
    """List users"""
    if current_user.is_owner:
        users = User.query.order_by(User.created_at.desc()).all()
    elif current_user.can_manage_users and current_user.brand_id:
        users = User.query.filter_by(brand_id=current_user.brand_id).all()
    else:
        flash('ليس لديك صلاحية لإدارة المستخدمين', 'danger')
        return redirect(url_for('dashboard.index'))

    return render_template('admin/users/index.html', users=users)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@brand_manager_required
def users_create():
    """Create new user"""
    form = UserForm()

    # Populate choices - must be done before validate_on_submit
    roles = Role.query.all()
    form.role_id.choices = [(0, '-- اختر الدور --')] + [(r.id, r.name) for r in roles]

    if current_user.is_owner:
        form.brand_id.choices = [(0, '-- بدون براند --')] + [(b.id, b.name) for b in Brand.query.filter_by(is_active=True).all()]
    else:
        form.brand_id.choices = [(current_user.brand_id, current_user.brand.name)]

    form.branch_id.choices = [(0, '-- بدون فرع --')]

    if form.validate_on_submit():
        # Validate role
        if not form.role_id.data or form.role_id.data == 0:
            flash('يرجى اختيار الدور', 'danger')
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
            is_active=form.is_active.data
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.commit()

        flash('تم إنشاء المستخدم بنجاح', 'success')
        return redirect(url_for('admin.users_list'))

    return render_template('admin/users/form.html', form=form)


# ============== Plans ==============

@admin_bp.route('/plans')
@login_required
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


# ============== Service Types ==============

@admin_bp.route('/service-types')
@login_required
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
