"""
WTForms for the gym management system.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, BooleanField, SelectField,
    TextAreaField, IntegerField, DecimalField, DateField
)
from wtforms.validators import DataRequired, Email, Optional, Length, NumberRange


class LoginForm(FlaskForm):
    """Login form"""
    email = StringField('البريد الإلكتروني', validators=[DataRequired()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    remember_me = BooleanField('تذكرني')


class ChangePasswordForm(FlaskForm):
    """Change password form"""
    current_password = PasswordField('كلمة المرور الحالية', validators=[DataRequired()])
    new_password = PasswordField('كلمة المرور الجديدة', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('تأكيد كلمة المرور', validators=[DataRequired()])


class BrandForm(FlaskForm):
    """Brand creation/edit form"""
    name = StringField('اسم البراند (عربي)', validators=[DataRequired(), Length(max=100)])
    name_en = StringField('اسم البراند (إنجليزي)', validators=[Optional(), Length(max=100)])
    description = TextAreaField('الوصف', validators=[Optional()])
    uses_fingerprint = BooleanField('تفعيل نظام البصمة')
    fingerprint_ip = StringField('عنوان IP للبصمة', validators=[Optional()])
    fingerprint_port = IntegerField('منفذ البصمة', validators=[Optional()], default=5005)
    is_active = BooleanField('نشط', default=True)


class UserForm(FlaskForm):
    """User creation/edit form"""
    name = StringField('الاسم', validators=[DataRequired(), Length(max=100)])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    phone = StringField('رقم الهاتف', validators=[Optional(), Length(max=20)])
    password = PasswordField('كلمة المرور', validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField('تأكيد كلمة المرور', validators=[Optional()])
    role_id = SelectField('الدور', coerce=int, validators=[DataRequired()])
    brand_id = SelectField('البراند', coerce=int, validators=[Optional()])
    is_active = BooleanField('نشط', default=True)


class PlanForm(FlaskForm):
    """Subscription plan form"""
    name = StringField('اسم الخطة', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('الوصف', validators=[Optional()])
    duration_days = IntegerField('المدة (بالأيام)', validators=[DataRequired(), NumberRange(min=1)])
    price = DecimalField('السعر', validators=[DataRequired(), NumberRange(min=0)])
    max_freezes = IntegerField('عدد مرات التجميد', validators=[Optional()], default=0)
    max_freeze_days = IntegerField('أقصى أيام تجميد', validators=[Optional()], default=0)
    brand_id = SelectField('البراند', coerce=int, validators=[DataRequired()])
    is_active = BooleanField('نشطة', default=True)


class MemberForm(FlaskForm):
    """Member form"""
    name = StringField('الاسم الكامل', validators=[DataRequired(), Length(max=100)])
    phone = StringField('رقم الهاتف', validators=[DataRequired(), Length(max=20)])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email()])
    birth_date = DateField('تاريخ الميلاد', validators=[Optional()])
    gender = SelectField('الجنس', choices=[('', '-'), ('male', 'ذكر'), ('female', 'أنثى')])
    national_id = StringField('رقم الهوية', validators=[Optional(), Length(max=20)])
    address = StringField('العنوان', validators=[Optional(), Length(max=255)])
    emergency_contact_name = StringField('اسم الطوارئ', validators=[Optional(), Length(max=100)])
    emergency_contact_phone = StringField('هاتف الطوارئ', validators=[Optional(), Length(max=20)])
    health_notes = TextAreaField('ملاحظات صحية', validators=[Optional()])


class SubscriptionForm(FlaskForm):
    """Subscription creation form"""
    plan_id = SelectField('خطة الاشتراك', coerce=int, validators=[DataRequired()])
    start_date = DateField('تاريخ البدء', validators=[DataRequired()])
    discount = DecimalField('الخصم', validators=[Optional()], default=0)
    amount_paid = DecimalField('المبلغ المدفوع', validators=[DataRequired(), NumberRange(min=0)])
    notes = TextAreaField('ملاحظات', validators=[Optional()])


class FreezeForm(FlaskForm):
    """Subscription freeze form"""
    start_date = DateField('تاريخ بدء التجميد', validators=[DataRequired()])
    days = IntegerField('عدد أيام التجميد', validators=[DataRequired(), NumberRange(min=1)])
    reason = TextAreaField('سبب التجميد', validators=[Optional()])


class ExpenseForm(FlaskForm):
    """Expense form"""
    description = StringField('الوصف', validators=[DataRequired(), Length(max=255)])
    amount = DecimalField('المبلغ', validators=[DataRequired(), NumberRange(min=0)])
    date = DateField('التاريخ', validators=[DataRequired()])
    category_id = SelectField('التصنيف', coerce=int, validators=[Optional()])
    notes = TextAreaField('ملاحظات', validators=[Optional()])


class SalaryForm(FlaskForm):
    """Salary form"""
    user_id = SelectField('الموظف', coerce=int, validators=[DataRequired()])
    month = SelectField('الشهر', coerce=int, choices=[(i, str(i)) for i in range(1, 13)])
    year = SelectField('السنة', coerce=int, validators=[DataRequired()])
    base_salary = DecimalField('الراتب الأساسي', validators=[DataRequired(), NumberRange(min=0)])
    allowances = DecimalField('البدلات', validators=[Optional()], default=0)
    deductions = DecimalField('الخصومات', validators=[Optional()], default=0)
    notes = TextAreaField('ملاحظات', validators=[Optional()])
