import os
import uuid
from datetime import datetime, date, timezone, timedelta
from flask import current_app
from werkzeug.utils import secure_filename


# ─── GYM-44 — local-time rendering helpers ───────────────────────────────
# DB stays in UTC (default=datetime.utcnow on every timestamp column). The
# filters below convert at render time to Asia/Riyadh + 12-hour with ص/م,
# so existing rows + new rows look identical and we don't need to migrate
# historical timestamps.
try:
    from zoneinfo import ZoneInfo
    _RIYADH = ZoneInfo('Asia/Riyadh')
except ImportError:
    # Python < 3.9 fallback. KSA doesn't observe DST so +03:00 is correct.
    _RIYADH = timezone(timedelta(hours=3))


def to_local(dt):
    """UTC (or naive == UTC) datetime → Asia/Riyadh. None passes through.

    NB: This function assumes ``dt`` is a ``datetime``. Bare ``date`` and
    ``time`` objects don't need conversion (a date has no time, a time
    has no date), so the Jinja filters below short-circuit for those
    types BEFORE calling this. Don't call to_local() on a bare date/time.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_RIYADH)


def _fmt_12h(hour, minute):
    mer = 'م' if hour >= 12 else 'ص'
    h12 = hour % 12 or 12
    return f"{h12:02d}:{minute:02d} {mer}"


def local_dt(dt):
    """Jinja filter: 'YYYY-MM-DD hh:MM ص/م'."""
    if dt is None:
        return '—'
    # Bare `date` (no time-of-day) — just render the date; no timezone shift.
    if not isinstance(dt, datetime):
        try:
            return dt.strftime('%Y-%m-%d')
        except AttributeError:
            return '—'
    d = to_local(dt)
    return f"{d.strftime('%Y-%m-%d')} {_fmt_12h(d.hour, d.minute)}"


def local_time(dt):
    """Jinja filter: 'hh:MM ص/م' (no date)."""
    if dt is None:
        return '—'
    # Bare `time` (no date) — no timezone to apply, format as-is.
    if not isinstance(dt, datetime):
        try:
            return _fmt_12h(dt.hour, dt.minute)
        except AttributeError:
            return '—'
    d = to_local(dt)
    return _fmt_12h(d.hour, d.minute)


def local_date(dt):
    """Jinja filter: 'YYYY-MM-DD'. Bare date → format directly (no tz shift)."""
    if dt is None:
        return '—'
    if not isinstance(dt, datetime):
        try:
            return dt.strftime('%Y-%m-%d')
        except AttributeError:
            return '—'
    d = to_local(dt)
    return d.strftime('%Y-%m-%d')


def allowed_file(filename, allowed=None):
    """Check if file extension is allowed.

    `allowed` overrides the default config-driven allow-list. Used by callers
    that need to accept non-image types (e.g. complaint attachments allowing
    PDFs).
    """
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    if allowed is not None:
        return ext in allowed
    return ext in current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})


def save_uploaded_file(file, folder='uploads', allowed=None):
    """
    Save uploaded file with unique name

    Args:
        file: FileStorage object
        folder: subfolder name (logos, members, receipts)
        allowed: optional set of allowed extensions; overrides config default

    Returns:
        Relative path to saved file or None
    """
    if not file or file.filename == '':
        return None

    if not allowed_file(file.filename, allowed=allowed):
        return None

    # Generate unique filename
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"

    # Full path
    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(upload_folder, exist_ok=True)

    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    # Return relative path for storage
    return f"uploads/{folder}/{filename}"


def delete_uploaded_file(filepath):
    """Delete uploaded file"""
    if not filepath:
        return

    full_path = os.path.join(current_app.static_folder, filepath)
    if os.path.exists(full_path):
        os.remove(full_path)


def format_currency(amount, currency='ر.س'):
    """Format amount as currency"""
    if amount is None:
        return f"0 {currency}"
    return f"{float(amount):,.2f} {currency}"


def format_date(d, format='%Y-%m-%d'):
    """Format date"""
    if not d:
        return '-'
    if isinstance(d, str):
        return d
    return d.strftime(format)


def format_datetime(dt, format='%Y-%m-%d %H:%M'):
    """Format datetime"""
    if not dt:
        return '-'
    if isinstance(dt, str):
        return dt
    return dt.strftime(format)


def get_date_range(period='month'):
    """
    Get date range for period

    Args:
        period: 'today', 'week', 'month', 'year'

    Returns:
        (start_date, end_date)
    """
    from datetime import timedelta

    today = date.today()

    if period == 'today':
        return today, today

    elif period == 'week':
        start = today - timedelta(days=today.weekday())
        return start, today

    elif period == 'month':
        start = today.replace(day=1)
        return start, today

    elif period == 'year':
        start = today.replace(month=1, day=1)
        return start, today

    return today, today


def get_month_name(month):
    """Get Arabic month name"""
    months = {
        1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
        5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
        9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
    }
    return months.get(month, str(month))


def calculate_age(birth_date):
    """Calculate age from birth date"""
    if not birth_date:
        return None

    today = date.today()
    age = today.year - birth_date.year

    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1

    return age


def pagination_args(request, default_per_page=20):
    """Get pagination arguments from request"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', default_per_page, type=int)
    return page, per_page


def apply_branch_filter(query, model, user=None, branch_filter_id=None):
    """
    Apply brand/branch filtering based on current user's role.

    - admin (is_owner) → no filter, sees everything; an optional
      `branch_filter_id` lets admin tools (and the GYM-12 owner picker)
      pin to a specific branch
    - owner (brand-level) → filter by brand_id only, optionally further
      pinned by `branch_filter_id` to *one of their own brand's branches*
    - branch roles (branch_id set) → filter by brand_id AND branch_id

    Includes records with NULL branch_id (legacy data).
    """
    from flask_login import current_user as _current_user
    from app import db

    user = user or _current_user

    if user.is_owner:  # admin sees all
        if branch_filter_id and hasattr(model, 'branch_id'):
            query = query.filter(model.branch_id == branch_filter_id)
        return query

    # Filter by brand
    if hasattr(model, 'brand_id') and user.brand_id:
        query = query.filter(model.brand_id == user.brand_id)

    # Filter by branch for branch-level roles
    if user.branch_id and hasattr(model, 'branch_id'):
        query = query.filter(
            db.or_(model.branch_id == user.branch_id, model.branch_id.is_(None))
        )
        return query

    # Brand-level owner with an explicit "view as branch" override
    if branch_filter_id and hasattr(model, 'branch_id'):
        query = query.filter(model.branch_id == branch_filter_id)

    return query


def resolve_owner_branch_filter():
    """Resolve the GYM-12 'view-as-branch' filter for the current user.

    Returns an integer branch_id if the current user is a brand-level owner
    who has selected one of *their own* branches via ?branch_id= (or had it
    stashed in their session); returns None otherwise. Admins / branch-level
    users get None — admins manage scope via brand picker, branch users are
    already scoped.
    """
    from flask import request, session
    from flask_login import current_user as _current_user

    user = _current_user
    # Only the brand owner role uses this picker. Admins manage scope via
    # the brand dropdown; branch-level users are already scoped; plain
    # employees / coaches don't have a picker at all and must NOT inherit a
    # session value that the owner happened to stash earlier.
    if (user.is_owner or not user.brand_id or user.branch_id
            or not user.is_brand_manager):
        return None

    raw = request.args.get('branch_id', type=int)
    if raw == 0:  # explicit "all branches" reset
        session.pop('owner_branch_filter', None)
        return None
    if raw:
        from app.models.company import Branch
        branch = Branch.query.filter_by(id=raw, brand_id=user.brand_id).first()
        if branch:
            session['owner_branch_filter'] = branch.id
            return branch.id
    return session.get('owner_branch_filter')


def check_entity_access(entity, user=None):
    """
    Check if the current user can access a specific entity.
    Call after get_or_404 to enforce brand/branch access.

    Returns True if allowed, False if denied.
    """
    from flask_login import current_user as _current_user

    user = user or _current_user

    if user.is_owner:  # admin sees all
        return True

    # Check brand
    if hasattr(entity, 'brand_id') and entity.brand_id:
        if user.brand_id and entity.brand_id != user.brand_id:
            return False

    # Check branch for branch-level roles
    if user.branch_id and hasattr(entity, 'branch_id'):
        if entity.branch_id and entity.branch_id != user.branch_id:
            return False

    return True


# ─── GYM-65 — split payment methods on one invoice ─────────────────────────

def parse_payment_splits(form, paid_amount, default_method):
    """GYM-65 — return a list of (amount, method) tuples for the payment.

    If the request form has `split=1`, parses `paid_cash`, `paid_card`,
    `paid_transfer` and validates that they sum to ``paid_amount``.
    Otherwise returns a single-tuple list ``[(paid_amount, default_method)]``.

    Raises ``ValueError`` with an Arabic message on mismatch — the caller
    should flash it and re-render.
    """
    def _num(key):
        raw = (form.get(key) or '').strip()
        if not raw:
            return 0.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    if str(form.get('split') or '') != '1':
        return [(float(paid_amount or 0), default_method)]

    parts = []
    for key, method in (('paid_cash', 'cash'),
                        ('paid_card', 'card'),
                        ('paid_transfer', 'transfer')):
        amt = _num(key)
        if amt > 0:
            parts.append((amt, method))

    if not parts:
        raise ValueError('التقسيم فارغ — أدخل مبلغاً واحداً على الأقل')

    total = sum(a for a, _ in parts)
    # 1-cent tolerance for float rounding
    if abs(total - float(paid_amount or 0)) > 0.01:
        raise ValueError(
            f'مجموع التقسيم ({total:.2f}) لا يساوي المدفوع ({float(paid_amount or 0):.2f})'
        )
    return parts


def write_split_payments(subscription, splits, income_type, current_user):
    """GYM-65 — write N SubscriptionPayment + N Income rows for one subscription.

    Args:
        subscription: the Subscription row (already flushed, has .id).
        splits: list of (amount, method) tuples from ``parse_payment_splits``.
        income_type: 'subscription' | 'class_subscription' | etc.
        current_user: for ``created_by``.

    Returns the list of created SubscriptionPayment objects. Caller is
    expected to create the Invoice afterwards, use ``payments[0]`` for
    ``invoice.payment_id`` (backward compat), and then back-fill
    ``invoice_id`` on each payment via ``attach_invoice_to_payments``.
    """
    from datetime import date
    from app import db
    from app.models.subscription import SubscriptionPayment
    from app.models.finance import Income

    payments = []
    branch_id = subscription.branch_id or getattr(current_user, 'branch_id', None)
    for amount, method in splits:
        p = SubscriptionPayment(
            subscription_id=subscription.id,
            brand_id=subscription.brand_id,
            amount=amount,
            payment_method=method,
            created_by=current_user.id,
        )
        db.session.add(p)
        payments.append(p)
        inc = Income(
            brand_id=subscription.brand_id,
            branch_id=branch_id,
            subscription_id=subscription.id,
            service_type_id=subscription.service_type_id,
            amount=amount,
            type=income_type,
            payment_method=method,
            date=date.today(),
            created_by=current_user.id,
        )
        db.session.add(inc)
    db.session.flush()
    return payments


def attach_invoice_to_payments(invoice, payments):
    """GYM-65 — back-fill invoice_id on each SubscriptionPayment after the
    Invoice has been created + flushed. Used by every callsite that creates
    a split invoice."""
    for p in payments:
        p.invoice_id = invoice.id


def invoice_method_label(splits):
    """GYM-65 — 'split' when >1 method, else the single method string."""
    return 'split' if len(splits) > 1 else splits[0][1]
