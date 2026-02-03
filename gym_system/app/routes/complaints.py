from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import SelectField, TextAreaField, HiddenField
from wtforms.validators import DataRequired
from datetime import datetime

from app import db
from app.models.company import Brand
from app.models.member import Member
from app.models.complaint import Complaint
from app.utils.decorators import members_required
from app.utils.helpers import pagination_args

complaints_bp = Blueprint('complaints', __name__)


class ComplaintForm(FlaskForm):
    """Complaint form"""
    member_id = HiddenField('ID العضو')
    subject = TextAreaField('موضوع الشكوى', validators=[DataRequired()])
    description = TextAreaField('تفاصيل الشكوى', validators=[DataRequired()])


class ResolveComplaintForm(FlaskForm):
    """Resolve complaint form"""
    resolution = TextAreaField('ملاحظات الحل', validators=[DataRequired()])


@complaints_bp.route('/')
@login_required
@members_required
def index():
    """List complaints"""
    page, per_page = pagination_args(request)
    status = request.args.get('status', '')

    # Base query - filter by brand access
    if current_user.can_view_all_brands:
        brand_id = request.args.get('brand_id', type=int)
        if brand_id:
            query = Complaint.query.filter_by(brand_id=brand_id)
        else:
            query = Complaint.query
    else:
        # Reception and brand managers see only their brand
        query = Complaint.query.filter_by(brand_id=current_user.brand_id)

    # Status filter
    if status:
        query = query.filter_by(status=status)

    # Pagination
    complaints = query.order_by(Complaint.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter (owner only)
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('complaints/index.html',
                          complaints=complaints,
                          brands=brands,
                          status=status)


@complaints_bp.route('/create', methods=['GET', 'POST'])
@login_required
@members_required
def create():
    """Create new complaint"""
    member_id = request.args.get('member_id', type=int)

    form = ComplaintForm()

    # If member_id provided, validate access
    member = None
    if member_id:
        member = Member.query.get_or_404(member_id)
        if not current_user.can_access_brand(member.brand_id):
            flash('ليس لديك صلاحية', 'danger')
            return redirect(url_for('complaints.index'))
        form.member_id.data = member_id

    if form.validate_on_submit():
        # Determine brand_id
        if form.member_id.data:
            member = Member.query.get(int(form.member_id.data))
            brand_id = member.brand_id
            branch_id = member.branch_id
        else:
            brand_id = current_user.brand_id
            branch_id = current_user.branch_id

        # Create complaint
        complaint = Complaint(
            brand_id=brand_id,
            branch_id=branch_id,
            member_id=form.member_id.data if form.member_id.data else None,
            subject=form.subject.data,
            description=form.description.data,
            status='open',
            created_by=current_user.id
        )
        db.session.add(complaint)
        db.session.commit()

        flash('تم تسجيل الشكوى بنجاح', 'success')

        if member:
            return redirect(url_for('members.view', member_id=member.id))
        return redirect(url_for('complaints.index'))

    return render_template('complaints/create.html', form=form, member=member)


@complaints_bp.route('/<int:complaint_id>')
@login_required
@members_required
def view(complaint_id):
    """View complaint details"""
    complaint = Complaint.query.get_or_404(complaint_id)

    if not current_user.can_access_brand(complaint.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('complaints.index'))

    return render_template('complaints/view.html', complaint=complaint)


@complaints_bp.route('/<int:complaint_id>/resolve', methods=['GET', 'POST'])
@login_required
@members_required
def resolve(complaint_id):
    """Resolve complaint"""
    complaint = Complaint.query.get_or_404(complaint_id)

    if not current_user.can_access_brand(complaint.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('complaints.index'))

    if complaint.status in ['resolved', 'closed']:
        flash('الشكوى تم حلها بالفعل', 'warning')
        return redirect(url_for('complaints.view', complaint_id=complaint_id))

    form = ResolveComplaintForm()

    if form.validate_on_submit():
        complaint.status = 'resolved'
        complaint.resolution = form.resolution.data
        complaint.resolved_at = datetime.utcnow()
        complaint.resolved_by = current_user.id

        db.session.commit()

        flash('تم حل الشكوى بنجاح', 'success')
        return redirect(url_for('complaints.view', complaint_id=complaint_id))

    return render_template('complaints/resolve.html', form=form, complaint=complaint)


@complaints_bp.route('/<int:complaint_id>/close', methods=['POST'])
@login_required
@members_required
def close(complaint_id):
    """Close complaint"""
    complaint = Complaint.query.get_or_404(complaint_id)

    if not current_user.can_access_brand(complaint.brand_id):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('complaints.index'))

    complaint.status = 'closed'
    db.session.commit()

    flash('تم إغلاق الشكوى', 'success')
    return redirect(url_for('complaints.view', complaint_id=complaint_id))
