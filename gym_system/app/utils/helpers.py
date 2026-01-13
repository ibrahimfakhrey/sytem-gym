import os
import uuid
from datetime import datetime, date
from flask import current_app
from werkzeug.utils import secure_filename


def allowed_file(filename):
    """Check if file extension is allowed"""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})


def save_uploaded_file(file, folder='uploads'):
    """
    Save uploaded file with unique name

    Args:
        file: FileStorage object
        folder: subfolder name (logos, members, receipts)

    Returns:
        Relative path to saved file or None
    """
    if not file or file.filename == '':
        return None

    if not allowed_file(file.filename):
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
