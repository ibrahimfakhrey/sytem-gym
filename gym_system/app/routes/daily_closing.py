"""Daily Closing routes (الإقفال اليومي)"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import DecimalField, TextAreaField
from wtforms.validators import DataRequired, Optional
from datetime import datetime, date, timedelta

from app import db
from app.models import Brand, Branch, DailyClosing

daily_closing_bp = Blueprint('daily_closing', __name__, url_prefix='/daily-closing')


class SubmitClosingForm(FlaskForm):
    """Form for submitting daily closing"""
    actual_cash = DecimalField('النقد الفعلي المسلم', validators=[DataRequired()])
    notes = TextAreaField('ملاحظات', validators=[Optional()])
    difference_explanation = TextAreaField('تفسير الفرق', validators=[Optional()])


@daily_closing_bp.route('/')
@login_required
def index():
    """List daily closings"""
    if not (current_user.role and current_user.role.can_view_daily_closing):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        brands = Brand.query.filter_by(is_active=True).all()
        if brand_id:
            brand = Brand.query.get(brand_id)
        else:
            brand = brands[0] if brands else None
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand
        brands = []

    if not brand:
        flash('يرجى اختيار براند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Get closings
    closings = DailyClosing.query.filter_by(brand_id=brand.id).order_by(
        DailyClosing.closing_date.desc()
    ).limit(30).all()

    # Pending verifications count
    pending_count = DailyClosing.query.filter_by(
        brand_id=brand.id, status='submitted'
    ).count()

    return render_template('daily_closing/index.html',
                         closings=closings,
                         brand=brand,
                         brands=brands,
                         pending_count=pending_count)


@daily_closing_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create or continue today's closing"""
    if not (current_user.role and current_user.role.can_view_daily_closing):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brand
    if current_user.is_owner:
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id:
            flash('يرجى اختيار البراند', 'warning')
            return redirect(url_for('daily_closing.index'))
        brand = Brand.query.get_or_404(brand_id)
    else:
        brand_id = current_user.brand_id
        brand = current_user.brand

    # Get or create today's closing
    today = date.today()
    closing = DailyClosing.get_or_create(brand_id, today)

    # Recalculate from transactions
    closing.calculate_from_transactions()
    db.session.commit()

    form = SubmitClosingForm()

    if form.validate_on_submit():
        closing.submit(
            actual_cash=form.actual_cash.data,
            notes=form.notes.data,
            explanation=form.difference_explanation.data,
            user_id=current_user.id
        )
        flash('تم تسليم الإقفال اليومي بنجاح', 'success')
        return redirect(url_for('daily_closing.view', closing_id=closing.id))

    return render_template('daily_closing/form.html', form=form, closing=closing, brand=brand)


@daily_closing_bp.route('/<int:closing_id>')
@login_required
def view(closing_id):
    """View daily closing details"""
    closing = DailyClosing.query.get_or_404(closing_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != closing.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('daily_closing.index'))

    return render_template('daily_closing/view.html', closing=closing)


@daily_closing_bp.route('/<int:closing_id>/verify', methods=['POST'])
@login_required
def verify(closing_id):
    """Verify daily closing"""
    if not (current_user.role and current_user.role.can_manage_daily_closing):
        flash('ليس لديك صلاحية للتحقق', 'danger')
        return redirect(url_for('daily_closing.index'))

    closing = DailyClosing.query.get_or_404(closing_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != closing.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('daily_closing.index'))

    action = request.form.get('action', 'approve')
    closing.verify(current_user.id, approve=(action == 'approve'))

    if action == 'approve':
        flash('تم التحقق من الإقفال بنجاح', 'success')
    else:
        flash('تم رفض الإقفال', 'warning')

    return redirect(url_for('daily_closing.view', closing_id=closing.id))


@daily_closing_bp.route('/pending')
@login_required
def pending():
    """View pending verifications"""
    if not (current_user.role and current_user.role.can_manage_daily_closing):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('daily_closing.index'))

    if current_user.is_owner:
        closings = DailyClosing.get_pending_verifications()
    else:
        closings = DailyClosing.get_pending_verifications(current_user.brand_id)

    return render_template('daily_closing/pending.html', closings=closings)
