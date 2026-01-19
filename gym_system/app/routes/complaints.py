"""Complaints routes"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerField
from wtforms.validators import DataRequired, Optional, Email, Length
from datetime import datetime

from app import db, csrf
from app.models import Brand, Branch, Member, Complaint, ComplaintCategory

complaints_bp = Blueprint('complaints', __name__, url_prefix='/complaints')


class ComplaintForm(FlaskForm):
    """Form for creating complaint by staff"""
    category_id = SelectField('التصنيف', coerce=int, validators=[DataRequired()])
    member_id = IntegerField('العضو (اختياري)', validators=[Optional()])
    customer_name = StringField('اسم العميل', validators=[Optional(), Length(max=100)])
    customer_phone = StringField('رقم الهاتف', validators=[Optional(), Length(max=20)])
    subject = StringField('الموضوع', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('تفاصيل الشكوى', validators=[DataRequired()])
    priority = SelectField('الأولوية', choices=[
        ('low', 'منخفضة'),
        ('normal', 'عادية'),
        ('high', 'عالية'),
        ('urgent', 'عاجلة')
    ], default='normal')


class PublicComplaintForm(FlaskForm):
    """Form for public complaint submission"""
    category_id = SelectField('التصنيف', coerce=int, validators=[DataRequired()])
    customer_name = StringField('الاسم', validators=[DataRequired(), Length(max=100)])
    customer_phone = StringField('رقم الهاتف', validators=[DataRequired(), Length(max=20)])
    customer_email = StringField('البريد الإلكتروني', validators=[Optional(), Email()])
    subject = StringField('الموضوع', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('تفاصيل الشكوى', validators=[DataRequired()])


class ResolveForm(FlaskForm):
    """Form for resolving complaint"""
    resolution = TextAreaField('الحل', validators=[DataRequired()])


@complaints_bp.route('/')
@login_required
def index():
    """List complaints"""
    # Check permissions
    if not (current_user.role and current_user.role.can_view_complaints):
        flash('ليس لديك صلاحية لعرض الشكاوى', 'danger')
        return redirect(url_for('dashboard.index'))

    # Filters
    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', type=int)

    query = Complaint.query

    if not current_user.is_owner:
        query = query.filter_by(brand_id=current_user.brand_id)

    if status_filter:
        query = query.filter_by(status=status_filter)
    if category_filter:
        query = query.filter_by(category_id=category_filter)

    complaints = query.order_by(Complaint.created_at.desc()).all()
    categories = ComplaintCategory.query.filter_by(is_active=True).all()

    # Stats
    pending_count = Complaint.query.filter_by(status='pending')
    if not current_user.is_owner:
        pending_count = pending_count.filter_by(brand_id=current_user.brand_id)
    pending_count = pending_count.count()

    # Get brands for owner dropdown
    brands = Brand.query.filter_by(is_active=True).all() if current_user.is_owner else []

    return render_template('complaints/index.html',
                         complaints=complaints,
                         categories=categories,
                         pending_count=pending_count,
                         status_filter=status_filter,
                         category_filter=category_filter,
                         brands=brands)


@complaints_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create complaint by staff"""
    if not (current_user.role and current_user.role.can_view_complaints):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    form = ComplaintForm()
    categories = ComplaintCategory.query.filter_by(is_active=True).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]

    # Get brand_id
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            flash('يرجى اختيار البراند', 'warning')
            return redirect(url_for('admin.brands_list'))
        brand = Brand.query.get_or_404(brand_id)
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand

    if form.validate_on_submit():
        complaint = Complaint(
            brand_id=brand_id,
            category_id=form.category_id.data,
            member_id=form.member_id.data if form.member_id.data else None,
            customer_name=form.customer_name.data,
            customer_phone=form.customer_phone.data,
            subject=form.subject.data,
            description=form.description.data,
            priority=form.priority.data,
            submitted_by='receptionist',
            created_by=current_user.id
        )
        db.session.add(complaint)
        db.session.commit()

        flash('تم تسجيل الشكوى بنجاح', 'success')
        return redirect(url_for('complaints.view', complaint_id=complaint.id))

    return render_template('complaints/form.html', form=form, brand=brand)


@complaints_bp.route('/<int:complaint_id>')
@login_required
def view(complaint_id):
    """View complaint details"""
    complaint = Complaint.query.get_or_404(complaint_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != complaint.brand_id:
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('complaints.index'))

    resolve_form = ResolveForm()

    return render_template('complaints/view.html', complaint=complaint, resolve_form=resolve_form)


@complaints_bp.route('/<int:complaint_id>/resolve', methods=['POST'])
@login_required
def resolve(complaint_id):
    """Resolve complaint"""
    if not (current_user.role and current_user.role.can_manage_complaints):
        flash('ليس لديك صلاحية لحل الشكاوى', 'danger')
        return redirect(url_for('complaints.index'))

    complaint = Complaint.query.get_or_404(complaint_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != complaint.brand_id:
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('complaints.index'))

    form = ResolveForm()
    if form.validate_on_submit():
        complaint.resolve(form.resolution.data, current_user.id)
        flash('تم حل الشكوى بنجاح', 'success')

    return redirect(url_for('complaints.view', complaint_id=complaint.id))


@complaints_bp.route('/<int:complaint_id>/close', methods=['POST'])
@login_required
def close(complaint_id):
    """Close complaint"""
    if not (current_user.role and current_user.role.can_manage_complaints):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('complaints.index'))

    complaint = Complaint.query.get_or_404(complaint_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != complaint.brand_id:
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('complaints.index'))

    complaint.close()
    flash('تم إغلاق الشكوى', 'success')

    return redirect(url_for('complaints.view', complaint_id=complaint.id))


@complaints_bp.route('/<int:complaint_id>/assign', methods=['POST'])
@login_required
def assign(complaint_id):
    """Assign complaint to staff"""
    if not (current_user.role and current_user.role.can_manage_complaints):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('complaints.index'))

    complaint = Complaint.query.get_or_404(complaint_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != complaint.brand_id:
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('complaints.index'))

    user_id = request.form.get('user_id', type=int)
    if user_id:
        complaint.assigned_to = user_id
        complaint.status = 'in_progress'
        db.session.commit()
        flash('تم تعيين الشكوى بنجاح', 'success')

    return redirect(url_for('complaints.view', complaint_id=complaint.id))


# ========= Public Complaint Submission =========

@complaints_bp.route('/public/<token>')
def public_form(token):
    """Public complaint form (no auth required)"""
    # Validate token format - we use brand tokens for this
    brand = Brand.query.filter_by(api_key=token, is_active=True).first()
    if not brand:
        return render_template('complaints/invalid_link.html'), 404

    form = PublicComplaintForm()
    categories = ComplaintCategory.query.filter_by(is_active=True).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]

    return render_template('complaints/public_form.html', form=form, brand=brand, token=token)


@complaints_bp.route('/public/submit', methods=['POST'])
@csrf.exempt  # Public form, different CSRF handling
def public_submit():
    """Submit public complaint"""
    token = request.form.get('token')
    brand = Brand.query.filter_by(api_key=token, is_active=True).first()
    if not brand:
        return jsonify({'error': 'رابط غير صالح'}), 404

    form = PublicComplaintForm()
    categories = ComplaintCategory.query.filter_by(is_active=True).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]

    if form.validate_on_submit():
        complaint = Complaint(
            brand_id=brand.id,
            category_id=form.category_id.data,
            customer_name=form.customer_name.data,
            customer_phone=form.customer_phone.data,
            customer_email=form.customer_email.data,
            subject=form.subject.data,
            description=form.description.data,
            submitted_by='customer'
        )
        db.session.add(complaint)
        db.session.commit()

        return render_template('complaints/public_success.html',
                             tracking_token=complaint.tracking_token,
                             brand=brand)

    # If validation fails, show form again with errors
    return render_template('complaints/public_form.html', form=form, brand=brand, token=token)


@complaints_bp.route('/track/<tracking_token>')
def track(tracking_token):
    """Track complaint status by token"""
    complaint = Complaint.query.filter_by(tracking_token=tracking_token).first()
    if not complaint:
        return render_template('complaints/not_found.html'), 404

    return render_template('complaints/track.html', complaint=complaint)


# ========= Admin: Seed Categories =========

@complaints_bp.route('/admin/seed-categories', methods=['POST'])
@login_required
def seed_categories():
    """Seed default complaint categories"""
    if not current_user.is_owner:
        flash('هذه العملية متاحة للمالك فقط', 'danger')
        return redirect(url_for('complaints.index'))

    ComplaintCategory.seed_defaults()
    flash('تم إضافة تصنيفات الشكاوى الافتراضية', 'success')
    return redirect(url_for('complaints.index'))
