from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email
import sys

from app import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__)


class LoginForm(FlaskForm):
    """Login form"""
    email = StringField('البريد الإلكتروني', validators=[DataRequired()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    remember_me = BooleanField('تذكرني')
    submit = SubmitField('تسجيل الدخول')


class ChangePasswordForm(FlaskForm):
    """Change password form"""
    current_password = PasswordField('كلمة المرور الحالية', validators=[DataRequired()])
    new_password = PasswordField('كلمة المرور الجديدة', validators=[DataRequired()])
    confirm_password = PasswordField('تأكيد كلمة المرور', validators=[DataRequired()])
    submit = SubmitField('تغيير كلمة المرور')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()

    # DEBUG: Log POST request
    if request.method == 'POST':
        print("=" * 60, file=sys.stderr)
        print("🔍 LOGIN ATTEMPT DEBUG", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"Email submitted: {form.email.data}", file=sys.stderr)
        print(f"Password submitted: {'*' * len(form.password.data) if form.password.data else 'None'}", file=sys.stderr)
        print(f"Form validated: {form.validate()}", file=sys.stderr)
        print(f"Form errors: {form.errors}", file=sys.stderr)
        print(f"CSRF token in form: {'csrf_token' in request.form}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.stderr.flush()

    if form.validate_on_submit():
        email_lower = form.email.data.lower()
        print(f"✅ Form validated. Looking for user: {email_lower}")

        user = User.query.filter_by(email=email_lower).first()

        print(f"User found: {user is not None}")
        if user:
            print(f"  User name: {user.name}")
            print(f"  User email: {user.email}")
            print(f"  User active: {user.is_active}")
            print(f"  User role: {user.role.name_en}")
            password_valid = user.check_password(form.password.data)
            print(f"  Password valid: {password_valid}")

        if user is None or not user.check_password(form.password.data):
            print("❌ Login failed: Invalid credentials")
            flash('البريد الإلكتروني أو كلمة المرور غير صحيحة', 'danger')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            print("❌ Login failed: User inactive")
            flash('هذا الحساب معطل، يرجى التواصل مع الإدارة', 'warning')
            return redirect(url_for('auth.login'))

        print("✅ Login successful!")
        login_user(user, remember=form.remember_me.data)
        user.update_last_login()

        flash(f'مرحباً {user.name}', 'success')

        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)

        return redirect(url_for('dashboard.index'))

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout"""
    logout_user()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password page"""
    form = ChangePasswordForm()

    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('كلمة المرور الحالية غير صحيحة', 'danger')
            return redirect(url_for('auth.change_password'))

        if form.new_password.data != form.confirm_password.data:
            flash('كلمة المرور الجديدة غير متطابقة', 'danger')
            return redirect(url_for('auth.change_password'))

        if len(form.new_password.data) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
            return redirect(url_for('auth.change_password'))

        current_user.set_password(form.new_password.data)
        db.session.commit()

        flash('تم تغيير كلمة المرور بنجاح', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('auth/change_password.html', form=form)
