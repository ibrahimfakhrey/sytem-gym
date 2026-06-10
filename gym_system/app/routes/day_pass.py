"""GYM-23 — Day-pass / walk-in tickets.

Two surfaces:

* /day-pass/prices  — owner manages the per-activity day-pass catalogue.
* /day-pass/        — receptionist's daily list (filterable by date).
* /day-pass/create  — quick one-page form to issue a ticket. Picking the
                       activity autofills the price from the catalogue.

Each issued ticket also posts an Income row so finance reports it as
revenue.
"""
from datetime import date, datetime, time
from decimal import Decimal

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user

from app import db
from app.models.day_pass import DayPass, DayPassPrice
from app.models.service import ServiceType
from app.models.finance import Income
from app.models.company import Brand
from app.utils.helpers import apply_branch_filter, check_entity_access

day_pass_bp = Blueprint('day_pass', __name__, url_prefix='/day-pass')


def _owner_brand_id():
    """Resolve the brand whose data we operate on.

    - Admin: explicit ?brand_id= URL param (or first brand if none).
    - Brand-level users: their own brand_id, always.
    """
    if current_user.can_view_all_brands:
        bid = request.args.get('brand_id', type=int) or request.form.get('brand_id', type=int)
        if not bid:
            first = Brand.query.filter_by(is_active=True).first()
            bid = first.id if first else None
        return bid
    return current_user.brand_id


# ─────────────────────────────────────────────────────────────────────────────
# Prices (owner)
# ─────────────────────────────────────────────────────────────────────────────

@day_pass_bp.route('/prices', methods=['GET'])
@login_required
def prices_list():
    """Owner sees the day-pass price catalogue for their brand."""
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('هذه الصفحة للمالك فقط', 'danger')
        return redirect(url_for('day_pass.index'))

    brand_id = _owner_brand_id()
    if not brand_id:
        flash('يرجى اختيار البراند', 'warning')
        return redirect(url_for('dashboard.index'))

    service_types = ServiceType.query.filter_by(brand_id=brand_id, is_active=True).all()
    prices_by_st = {p.service_type_id: p for p in DayPassPrice.query.filter_by(brand_id=brand_id).all()}

    # Make sure every active service type has a price row (created lazily on
    # first open) so the form is always a single POST.
    return render_template('day_pass/prices.html',
                          service_types=service_types,
                          prices_by_st=prices_by_st,
                          brand_id=brand_id)


@day_pass_bp.route('/prices', methods=['POST'])
@login_required
def prices_save():
    """Bulk-save the prices form. One field per service type:
       price_<service_type_id> + active_<service_type_id>.
    """
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('هذه الصفحة للمالك فقط', 'danger')
        return redirect(url_for('day_pass.index'))

    brand_id = _owner_brand_id()
    if not brand_id:
        flash('يرجى اختيار البراند', 'warning')
        return redirect(url_for('day_pass.prices_list'))

    service_types = ServiceType.query.filter_by(brand_id=brand_id, is_active=True).all()
    changed = 0
    for st in service_types:
        raw = (request.form.get(f'price_{st.id}') or '').strip()
        active = bool(request.form.get(f'active_{st.id}'))
        try:
            value = Decimal(raw) if raw else None
        except Exception:
            value = None

        row = DayPassPrice.query.filter_by(brand_id=brand_id, service_type_id=st.id).first()
        if value is None or value <= 0:
            if row:  # leaving the field blank deactivates the catalogue entry
                row.is_active = False
                changed += 1
            continue
        if not row:
            row = DayPassPrice(brand_id=brand_id, service_type_id=st.id, price=value, is_active=active)
            db.session.add(row)
            changed += 1
        elif float(row.price) != float(value) or row.is_active != active:
            row.price = value
            row.is_active = active
            changed += 1
    db.session.commit()
    flash(f'تم حفظ أسعار التذاكر ({changed} تغيير)', 'success')
    return redirect(url_for('day_pass.prices_list', brand_id=brand_id))


# ─────────────────────────────────────────────────────────────────────────────
# Tickets (receptionist + owner)
# ─────────────────────────────────────────────────────────────────────────────

@day_pass_bp.route('/')
@login_required
def index():
    """List of tickets — filterable by date. Brand-scoped via apply_branch_filter.
    Open to any authenticated user; brand+branch filter naturally hides
    things they shouldn't see. Creation is gated separately below.
    """

    pass_date_str = request.args.get('date', date.today().isoformat())
    try:
        pass_date = date.fromisoformat(pass_date_str)
    except ValueError:
        pass_date = date.today()

    from app.utils.helpers import resolve_owner_branch_filter
    q = apply_branch_filter(DayPass.query, DayPass,
                            branch_filter_id=resolve_owner_branch_filter())
    q = q.filter(DayPass.pass_date == pass_date)
    passes = q.order_by(DayPass.created_at.desc()).all()

    daily_total = sum(float(p.price) for p in passes)

    return render_template('day_pass/index.html',
                          passes=passes,
                          pass_date=pass_date,
                          daily_total=daily_total)


@day_pass_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Any authenticated user can issue a ticket. The ticket records
    `created_by`, which the owner sees on the list page in the المُصدر column.
    """
    from app.models.company import Branch
    brand_id = current_user.brand_id
    if current_user.can_view_all_brands:
        brand_id = request.values.get('brand_id', type=int) or brand_id

    if not brand_id:
        flash('يرجى اختيار البراند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Only the activities that have a positive, active price in the catalogue
    priced = db.session.query(DayPassPrice, ServiceType).join(
        ServiceType, ServiceType.id == DayPassPrice.service_type_id
    ).filter(
        DayPassPrice.brand_id == brand_id,
        DayPassPrice.is_active == True,
        DayPassPrice.price > 0,
        ServiceType.is_active == True,
    ).order_by(ServiceType.name).all()

    activities = [{
        'id': st.id,
        'name': st.name,
        'price': float(p.price),
    } for p, st in priced]

    # Branch selector. The creator's own branch is pre-selected if they have
    # one (and the dropdown is hidden), so receptionists keep the one-click
    # flow. Brand-level users (owner/admin) pick a branch explicitly.
    branches = Branch.query.filter_by(brand_id=brand_id, is_active=True).order_by(Branch.name).all()

    if request.method == 'POST':
        try:
            service_type_id = int(request.form.get('service_type_id') or 0)
        except ValueError:
            service_type_id = 0
        name = (request.form.get('customer_name') or '').strip()
        phone = (request.form.get('customer_phone') or '').strip() or None
        try:
            age = int(request.form.get('customer_age') or 0) or None
        except ValueError:
            age = None
        valid_from_str = request.form.get('valid_from') or ''
        valid_until_str = request.form.get('valid_until') or ''
        payment_method = request.form.get('payment_method') or 'cash'
        notes = (request.form.get('notes') or '').strip() or None

        # Branch is now required so the owner's branch picker can find these
        # tickets. Brand-level users pick from the form; branch users are
        # auto-pinned to their own branch.
        try:
            branch_id = int(request.form.get('branch_id') or 0)
        except ValueError:
            branch_id = 0
        if not branch_id and current_user.branch_id:
            branch_id = current_user.branch_id
        # Validate the branch belongs to this brand.
        if branch_id:
            branch = Branch.query.filter_by(id=branch_id, brand_id=brand_id).first()
            if not branch:
                branch_id = 0

        if not service_type_id or not name or not branch_id:
            if not branch_id:
                flash('اختر الفرع الذي يُصدر التذكرة منه', 'danger')
            else:
                flash('الاسم ونوع النشاط مطلوبان', 'danger')
            return render_template('day_pass/create.html', activities=activities,
                                   branches=branches, brand_id=brand_id)

        price_row = DayPassPrice.query.filter_by(brand_id=brand_id, service_type_id=service_type_id).first()
        if not price_row or not price_row.is_active or float(price_row.price) <= 0:
            flash('لا يوجد سعر نشط لهذا النشاط — اطلب من المالك ضبط السعر أولاً', 'warning')
            return render_template('day_pass/create.html', activities=activities,
                                   branches=branches, brand_id=brand_id)

        def _parse_time(s):
            try:
                return datetime.strptime(s, '%H:%M').time() if s else None
            except ValueError:
                return None

        valid_from = _parse_time(valid_from_str)
        valid_until = _parse_time(valid_until_str)

        dp = DayPass(
            brand_id=brand_id,
            branch_id=branch_id,
            service_type_id=service_type_id,
            customer_name=name[:120],
            customer_phone=phone,
            customer_age=age,
            pass_date=date.today(),
            valid_from=valid_from,
            valid_until=valid_until,
            price=price_row.price,
            payment_method=payment_method,
            notes=notes,
            created_by=current_user.id,
        )
        db.session.add(dp)
        db.session.flush()

        db.session.add(Income(
            brand_id=brand_id,
            branch_id=branch_id,
            service_type_id=service_type_id,
            amount=price_row.price,
            type='day_pass',
            payment_method=payment_method,
            description=f'تذكرة يومية — {name}',
            date=date.today(),
            created_by=current_user.id,
        ))
        db.session.commit()
        flash(f'تم إصدار تذكرة #{dp.id} بقيمة {float(price_row.price):,.0f} ر.س', 'success')
        return redirect(url_for('day_pass.index'))

    return render_template('day_pass/create.html', activities=activities,
                           branches=branches, brand_id=brand_id)


@day_pass_bp.route('/<int:pass_id>/print')
@login_required
def print_pass(pass_id):
    """Printable ticket card (like the gift card) — visible to anyone
    authenticated who can access the brand/branch. WhatsApp share button
    appears if the customer phone is on file.
    """
    dp = DayPass.query.get_or_404(pass_id)
    if not check_entity_access(dp):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('day_pass.index'))
    return render_template('day_pass/print.html', dp=dp)
