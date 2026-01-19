"""Employee management routes - reports, rewards, deductions"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, TextAreaField, BooleanField, SelectField, IntegerField, TimeField, DateField
from wtforms.validators import DataRequired, Optional, NumberRange
from datetime import datetime, date, timedelta, time
from sqlalchemy import func

from app import db
from app.models import Brand, User, Role
from app.models.attendance import EmployeeAttendance
from app.models.employee import EmployeeSettings, EmployeeReward, EmployeeDeduction
from app.models.finance import Salary

employees_bp = Blueprint('employees', __name__, url_prefix='/employees')


# ============== FORMS ==============

class EmployeeSettingsForm(FlaskForm):
    """Form for employee settings"""
    work_start_time = TimeField('وقت بداية العمل', validators=[DataRequired()])
    work_end_time = TimeField('وقت نهاية العمل', validators=[DataRequired()])
    late_threshold_minutes = IntegerField('فترة السماح (بالدقائق)',
                                          validators=[DataRequired(), NumberRange(min=0, max=60)],
                                          default=15)
    auto_deduction_enabled = BooleanField('تفعيل الخصم التلقائي للتأخير')
    auto_deduction_amount = DecimalField('مبلغ خصم التأخير (لليوم)',
                                         validators=[Optional()], default=0)
    absence_deduction_enabled = BooleanField('تفعيل الخصم التلقائي للغياب')
    absence_deduction_amount = DecimalField('مبلغ خصم الغياب (لليوم)',
                                            validators=[Optional()], default=0)


class RewardForm(FlaskForm):
    """Form for giving employee reward"""
    title = StringField('عنوان المكافأة', validators=[DataRequired()])
    amount = DecimalField('المبلغ', validators=[DataRequired(), NumberRange(min=1)])
    reason = TextAreaField('السبب', validators=[Optional()])
    is_recurring = BooleanField('مكافأة شهرية متكررة')
    recurring_day = IntegerField('يوم الشهر للصرف', validators=[Optional(), NumberRange(min=1, max=28)])
    effective_date = DateField('تاريخ السريان', default=date.today)


class DeductionForm(FlaskForm):
    """Form for giving employee deduction"""
    title = StringField('عنوان الخصم', validators=[DataRequired()])
    amount = DecimalField('المبلغ', validators=[DataRequired(), NumberRange(min=1)])
    reason = TextAreaField('السبب', validators=[DataRequired()])
    deduction_date = DateField('تاريخ الخصم', default=date.today)


class ManualAttendanceForm(FlaskForm):
    """Form for manual attendance entry"""
    user_id = SelectField('الموظف', coerce=int, validators=[DataRequired()])
    date = DateField('التاريخ', validators=[DataRequired()])
    check_in = TimeField('وقت الحضور', validators=[DataRequired()])
    check_out = TimeField('وقت الانصراف', validators=[Optional()])
    status = SelectField('الحالة', choices=[
        ('present', 'حاضر'),
        ('late', 'متأخر'),
        ('leave', 'إجازة')
    ])
    notes = TextAreaField('ملاحظات')


# ============== SETTINGS ROUTES ==============

@employees_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Employee settings - owner only"""
    if not current_user.is_owner:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brand
    brand_id = request.args.get('brand_id', type=int)
    brands = Brand.query.filter_by(is_active=True).all()

    if not brand_id and brands:
        brand_id = brands[0].id

    brand = Brand.query.get(brand_id) if brand_id else None
    if not brand:
        flash('يرجى اختيار براند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Get or create settings
    employee_settings = EmployeeSettings.get_or_create(brand_id)
    form = EmployeeSettingsForm(obj=employee_settings)

    if form.validate_on_submit():
        form.populate_obj(employee_settings)
        db.session.commit()
        flash('تم حفظ الإعدادات بنجاح', 'success')
        return redirect(url_for('employees.settings', brand_id=brand_id))

    return render_template('employees/settings.html',
                          form=form,
                          brand=brand,
                          brands=brands,
                          settings=employee_settings)


# ============== REPORT ROUTES ==============

@employees_bp.route('/report')
@login_required
def report():
    """Employee performance report - owner only"""
    if not current_user.is_owner:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brand
    brand_id = request.args.get('brand_id', type=int)
    brands = Brand.query.filter_by(is_active=True).all()

    if not brand_id and brands:
        brand_id = brands[0].id

    brand = Brand.query.get(brand_id) if brand_id else None

    # Date range (default: last 30 days)
    end_date = date.today()
    start_date = request.args.get('start_date')
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start_date = end_date - timedelta(days=30)

    end_date_param = request.args.get('end_date')
    if end_date_param:
        end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()

    # Get employees (staff) for this brand
    staff_roles = Role.query.filter(Role.name_en != 'owner').all()
    staff_role_ids = [r.id for r in staff_roles]

    employees = User.query.filter(
        User.brand_id == brand_id,
        User.role_id.in_(staff_role_ids),
        User.is_active == True
    ).all()

    # Calculate stats for each employee
    employee_stats = []
    total_days = (end_date - start_date).days + 1

    for emp in employees:
        # Attendance records
        attendance_records = EmployeeAttendance.query.filter(
            EmployeeAttendance.user_id == emp.id,
            EmployeeAttendance.date >= start_date,
            EmployeeAttendance.date <= end_date
        ).all()

        present_days = sum(1 for a in attendance_records if a.status in ['present', 'late'])
        late_days = sum(1 for a in attendance_records if a.status == 'late')
        absent_days = total_days - present_days - sum(1 for a in attendance_records if a.status == 'leave')
        leave_days = sum(1 for a in attendance_records if a.status == 'leave')
        total_late_minutes = sum(a.late_minutes or 0 for a in attendance_records)

        # Rewards in period
        rewards = EmployeeReward.query.filter(
            EmployeeReward.user_id == emp.id,
            EmployeeReward.effective_date >= start_date,
            EmployeeReward.effective_date <= end_date,
            EmployeeReward.is_active == True
        ).all()
        total_rewards = sum(float(r.amount) for r in rewards)

        # Deductions in period
        deductions = EmployeeDeduction.query.filter(
            EmployeeDeduction.user_id == emp.id,
            EmployeeDeduction.deduction_date >= start_date,
            EmployeeDeduction.deduction_date <= end_date
        ).all()
        total_deductions = sum(float(d.amount) for d in deductions)

        # Get latest salary (order by year desc, month desc)
        latest_salary = Salary.query.filter_by(user_id=emp.id).order_by(
            Salary.year.desc(), Salary.month.desc()
        ).first()
        base_salary = float(latest_salary.base_salary) if latest_salary else 0

        employee_stats.append({
            'employee': emp,
            'present_days': present_days,
            'late_days': late_days,
            'absent_days': max(0, absent_days),
            'leave_days': leave_days,
            'total_late_minutes': total_late_minutes,
            'total_rewards': total_rewards,
            'total_deductions': total_deductions,
            'base_salary': base_salary,
            'net_salary': base_salary + total_rewards - total_deductions,
            'attendance_rate': round((present_days / total_days) * 100, 1) if total_days > 0 else 0
        })

    return render_template('employees/report.html',
                          brand=brand,
                          brands=brands,
                          employees=employee_stats,
                          start_date=start_date,
                          end_date=end_date,
                          total_days=total_days)


@employees_bp.route('/<int:user_id>/details')
@login_required
def details(user_id):
    """Employee details with attendance history"""
    if not current_user.is_owner:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    employee = User.query.get_or_404(user_id)

    # Date range
    end_date = date.today()
    start_date = request.args.get('start_date')
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start_date = end_date - timedelta(days=30)

    # Attendance records
    attendance = EmployeeAttendance.query.filter(
        EmployeeAttendance.user_id == user_id,
        EmployeeAttendance.date >= start_date,
        EmployeeAttendance.date <= end_date
    ).order_by(EmployeeAttendance.date.desc()).all()

    # Rewards
    rewards = EmployeeReward.query.filter_by(
        user_id=user_id,
        is_active=True
    ).order_by(EmployeeReward.created_at.desc()).all()

    # Deductions
    deductions = EmployeeDeduction.query.filter_by(
        user_id=user_id
    ).order_by(EmployeeDeduction.deduction_date.desc()).limit(20).all()

    return render_template('employees/details.html',
                          employee=employee,
                          attendance=attendance,
                          rewards=rewards,
                          deductions=deductions,
                          start_date=start_date,
                          end_date=end_date)


# ============== REWARD ROUTES ==============

@employees_bp.route('/<int:user_id>/reward', methods=['GET', 'POST'])
@login_required
def give_reward(user_id):
    """Give reward to employee - owner only"""
    if not current_user.is_owner:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    employee = User.query.get_or_404(user_id)
    form = RewardForm()

    if form.validate_on_submit():
        reward = EmployeeReward(
            user_id=user_id,
            brand_id=employee.brand_id,
            title=form.title.data,
            amount=form.amount.data,
            reason=form.reason.data,
            is_recurring=form.is_recurring.data,
            recurring_day=form.recurring_day.data if form.is_recurring.data else None,
            effective_date=form.effective_date.data,
            created_by=current_user.id
        )
        db.session.add(reward)
        db.session.commit()

        flash(f'تم إضافة مكافأة {form.amount.data} ر.س للموظف {employee.name}', 'success')
        return redirect(url_for('employees.details', user_id=user_id))

    return render_template('employees/reward_form.html',
                          form=form,
                          employee=employee)


@employees_bp.route('/rewards/<int:reward_id>/cancel', methods=['POST'])
@login_required
def cancel_reward(reward_id):
    """Cancel a reward"""
    if not current_user.is_owner:
        return jsonify({'success': False, 'message': 'ليس لديك صلاحية'})

    reward = EmployeeReward.query.get_or_404(reward_id)
    reward.is_active = False
    db.session.commit()

    flash('تم إلغاء المكافأة', 'success')
    return redirect(url_for('employees.details', user_id=reward.user_id))


# ============== DEDUCTION ROUTES ==============

@employees_bp.route('/<int:user_id>/deduction', methods=['GET', 'POST'])
@login_required
def give_deduction(user_id):
    """Give deduction to employee - owner only"""
    if not current_user.is_owner:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    employee = User.query.get_or_404(user_id)
    form = DeductionForm()

    if form.validate_on_submit():
        deduction = EmployeeDeduction(
            user_id=user_id,
            brand_id=employee.brand_id,
            title=form.title.data,
            amount=form.amount.data,
            reason=form.reason.data,
            deduction_type='manual',
            deduction_date=form.deduction_date.data,
            created_by=current_user.id
        )
        db.session.add(deduction)
        db.session.commit()

        flash(f'تم إضافة خصم {form.amount.data} ر.س للموظف {employee.name}', 'warning')
        return redirect(url_for('employees.details', user_id=user_id))

    return render_template('employees/deduction_form.html',
                          form=form,
                          employee=employee)


# ============== ATTENDANCE ROUTES ==============

@employees_bp.route('/attendance', methods=['GET', 'POST'])
@login_required
def attendance():
    """Manual attendance entry"""
    if not current_user.is_owner:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    brand_id = request.args.get('brand_id', type=int)
    brands = Brand.query.filter_by(is_active=True).all()

    if not brand_id and brands:
        brand_id = brands[0].id

    brand = Brand.query.get(brand_id) if brand_id else None

    # Get employees for form
    staff_roles = Role.query.filter(Role.name_en != 'owner').all()
    staff_role_ids = [r.id for r in staff_roles]
    employees = User.query.filter(
        User.brand_id == brand_id,
        User.role_id.in_(staff_role_ids),
        User.is_active == True
    ).all()

    form = ManualAttendanceForm()
    form.user_id.choices = [(e.id, e.name) for e in employees]

    if form.validate_on_submit():
        # Check if attendance already exists
        existing = EmployeeAttendance.query.filter_by(
            user_id=form.user_id.data,
            date=form.date.data
        ).first()

        if existing:
            flash('يوجد سجل حضور لهذا الموظف في هذا اليوم', 'warning')
        else:
            # Get settings for late calculation
            settings = EmployeeSettings.get_or_create(brand_id)
            late_minutes = 0
            status = form.status.data

            if form.check_in.data and settings.work_start_time:
                check_in_mins = form.check_in.data.hour * 60 + form.check_in.data.minute
                start_mins = settings.work_start_time.hour * 60 + settings.work_start_time.minute
                if check_in_mins > start_mins + settings.late_threshold_minutes:
                    late_minutes = check_in_mins - start_mins
                    if status == 'present':
                        status = 'late'

            attendance = EmployeeAttendance(
                user_id=form.user_id.data,
                brand_id=brand_id,
                date=form.date.data,
                check_in=form.check_in.data,
                check_out=form.check_out.data,
                expected_check_in=settings.work_start_time,
                late_minutes=late_minutes,
                status=status,
                source='manual',
                notes=form.notes.data
            )
            db.session.add(attendance)

            # Auto deduction for lateness
            if status == 'late' and settings.auto_deduction_enabled and settings.auto_deduction_amount > 0:
                deduction = EmployeeDeduction(
                    user_id=form.user_id.data,
                    brand_id=brand_id,
                    title='خصم تأخير',
                    amount=settings.auto_deduction_amount,
                    reason=f'تأخير {late_minutes} دقيقة',
                    deduction_type='late',
                    deduction_date=form.date.data,
                    created_by=current_user.id
                )
                db.session.add(deduction)

            db.session.commit()
            flash('تم تسجيل الحضور بنجاح', 'success')
            return redirect(url_for('employees.attendance', brand_id=brand_id))

    # Get recent attendance
    recent_attendance = EmployeeAttendance.query.filter_by(
        brand_id=brand_id
    ).order_by(EmployeeAttendance.date.desc()).limit(50).all()

    return render_template('employees/attendance.html',
                          form=form,
                          brand=brand,
                          brands=brands,
                          employees=employees,
                          recent_attendance=recent_attendance)
