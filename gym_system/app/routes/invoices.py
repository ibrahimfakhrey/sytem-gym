from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models.finance import Invoice
from app.models.company import Brand
from app.utils.decorators import members_required
from app.utils.helpers import pagination_args, apply_branch_filter, check_entity_access

invoices_bp = Blueprint('invoices', __name__)


@invoices_bp.route('/')
@login_required
@members_required
def index():
    """List all invoices"""
    page, per_page = pagination_args(request)

    # Base query
    query = apply_branch_filter(Invoice.query, Invoice)

    # Search by invoice number or member name
    search = request.args.get('search', '').strip()
    if search:
        query = query.filter(
            db.or_(
                Invoice.invoice_number.like(f'%{search}%'),
                Invoice.member_name.like(f'%{search}%')
            )
        )

    # Payment method filter
    payment_method = request.args.get('payment_method', '')
    if payment_method:
        query = query.filter_by(payment_method=payment_method)

    # Date range filter (optional)
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')

    if from_date:
        from datetime import datetime
        from_datetime = datetime.strptime(from_date, '%Y-%m-%d')
        query = query.filter(Invoice.invoice_date >= from_datetime)

    if to_date:
        from datetime import datetime
        to_datetime = datetime.strptime(to_date, '%Y-%m-%d')
        # Add one day to include the entire day
        to_datetime = to_datetime.replace(hour=23, minute=59, second=59)
        query = query.filter(Invoice.invoice_date <= to_datetime)

    # Pagination
    invoices = query.order_by(Invoice.invoice_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get brands for filter
    brands = None
    if current_user.can_view_all_brands:
        brands = Brand.query.filter_by(is_active=True).all()

    return render_template('invoices/index.html',
                          invoices=invoices,
                          brands=brands,
                          search=search,
                          payment_method=payment_method,
                          from_date=from_date,
                          to_date=to_date)


@invoices_bp.route('/<int:invoice_id>')
@login_required
@members_required
def view(invoice_id):
    """View invoice details"""
    invoice = Invoice.query.get_or_404(invoice_id)

    if not check_entity_access(invoice):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('invoices.index'))

    return render_template('invoices/view.html', invoice=invoice)


@invoices_bp.route('/<int:invoice_id>/edit-date', methods=['POST'])
@login_required
@members_required
def edit_date(invoice_id):
    """GYM-61 — owner/admin only: edit the invoice_date (issue date).

    Writes an EditAuditLog row with old/new value + user. The invoice row
    itself is otherwise immutable via the UI; this is the single supported
    correction path."""
    from datetime import datetime
    from app.models.approvals import EditAuditLog
    invoice = Invoice.query.get_or_404(invoice_id)
    if not check_entity_access(invoice):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('invoices.index'))
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('تعديل تاريخ الفاتورة مقتصر على المدير.', 'danger')
        return redirect(url_for('invoices.view', invoice_id=invoice.id))

    raw = (request.form.get('invoice_date') or '').strip()
    if not raw:
        flash('التاريخ مطلوب', 'danger')
        return redirect(url_for('invoices.view', invoice_id=invoice.id))
    try:
        new_dt = datetime.fromisoformat(raw)
    except ValueError:
        flash('تنسيق التاريخ غير صالح', 'danger')
        return redirect(url_for('invoices.view', invoice_id=invoice.id))

    if new_dt != invoice.invoice_date:
        db.session.add(EditAuditLog(
            entity_type='invoice',
            entity_id=invoice.id,
            field_name='invoice_date',
            old_value=invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            new_value=new_dt.isoformat(),
            brand_id=invoice.brand_id,
            changed_by=current_user.id,
            note='GYM-61 direct manager edit',
        ))
        invoice.invoice_date = new_dt
        db.session.commit()
        flash('تم تحديث تاريخ الفاتورة وسُجّل التعديل.', 'success')
    return redirect(url_for('invoices.view', invoice_id=invoice.id))
