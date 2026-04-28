from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user


def role_required(*roles):
    """
    Decorator to require specific roles

    Usage:
        @role_required('owner', 'brand_manager')
        def my_view():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login', next=request.url))

            if current_user.role.name_en not in roles:
                flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'danger')
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def owner_required(f):
    """Decorator to require owner role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

        if not current_user.is_owner:
            flash('هذه الصفحة للمالك فقط', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def brand_manager_required(f):
    """Decorator to require brand_manager or owner role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

        if not (current_user.is_owner or current_user.is_brand_manager):
            flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def branch_manager_required(f):
    """Decorator to require branch_manager, brand owner, or admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

        if not (current_user.is_owner or current_user.is_brand_manager or current_user.is_branch_manager):
            flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def brand_required(f):
    """
    Decorator to ensure user can only access their brand's data

    Usage with brand_id in URL:
        @brand_required
        def view_brand(brand_id):
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

        brand_id = kwargs.get('brand_id') or request.args.get('brand_id')

        if brand_id:
            brand_id = int(brand_id)
            if not current_user.can_access_brand(brand_id):
                flash('ليس لديك صلاحية للوصول لهذا البراند', 'danger')
                abort(403)

        return f(*args, **kwargs)
    return decorated_function


def finance_required(f):
    """Decorator to require finance-related roles (view or manage)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

        has_finance = current_user.can_manage_finance
        if not has_finance and current_user.role:
            has_finance = current_user.role.can_view_finance
        if not has_finance:
            flash('ليس لديك صلاحية للوصول للمالية', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def members_required(f):
    """Decorator to require member viewing roles (members or attendance)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

        if not (current_user.can_manage_members or current_user.can_manage_attendance):
            flash('ليس لديك صلاحية لإدارة الأعضاء', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function
