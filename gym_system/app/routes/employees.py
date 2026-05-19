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
from app.models.employee import EmployeeSettings, EmployeeShift, EmployeeReward, EmployeeDeduction, EmployeeLateRule
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


class EmployeeShiftForm(FlaskForm):
    """Form for per-employee shift assignment"""
    work_start_time = TimeField('وقت بداية المناوبة', validators=[DataRequired()])
    work_end_time = TimeField('وقت نهاية المناوبة', validators=[DataRequired()])
    day_sat = BooleanField('السبت')
    day_sun = BooleanField('الأحد')
    day_mon = BooleanField('الاثنين')
    day_tue = BooleanField('الثلاثاء')
    day_wed = BooleanField('الأربعاء')
    day_thu = BooleanField('الخميس')
    day_fri = BooleanField('الجمعة')
    late_threshold_minutes = IntegerField('فترة السماح (بالدقائق)',
                                          validators=[Optional(), NumberRange(min=0, max=120)])


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
    """Employee settings - admin, owner, or branch_manager"""
    if not (current_user.is_owner or current_user.is_brand_manager or current_user.is_branch_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brand — admin sees all, owner/branch_manager sees their own
    if current_user.is_owner:
        brands = Brand.query.filter_by(is_active=True).all()
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id and brands:
            brand_id = brands[0].id
    else:
        brand_id = current_user.brand_id
        brands = [current_user.brand] if current_user.brand else []

    brand = Brand.query.get(brand_id) if brand_id else None
    if not brand:
        flash('يرجى اختيار براند', 'warning')
        return redirect(url_for('dashboard.index'))

    # Get or create settings
    employee_settings = EmployeeSettings.get_or_create(brand_id)
    form = EmployeeSettingsForm(obj=employee_settings)

    if form.validate_on_submit():
        form.populate_obj(employee_settings)

        # Only brand owner / admin can edit tiered rules — branch_manager keeps them intact
        can_edit_rules = current_user.is_owner or (current_user.role and current_user.role.name_en == 'owner')

        if can_edit_rules:
            # Replace tiered late rules from the submitted form
            # Inputs are sent as parallel arrays: rule_min_minutes[], rule_amount[]
            mins = request.form.getlist('rule_min_minutes')
            amounts = request.form.getlist('rule_amount')

            # Wipe existing rules for this brand and re-insert valid ones
            EmployeeLateRule.query.filter_by(brand_id=brand_id).delete()
            seen_minutes = set()
            for raw_min, raw_amt in zip(mins, amounts):
                raw_min = (raw_min or '').strip()
                raw_amt = (raw_amt or '').strip()
                if not raw_min or not raw_amt:
                    continue
                try:
                    m = int(raw_min)
                    a = float(raw_amt)
                except ValueError:
                    continue
                if m < 0 or a < 0:
                    continue
                if m in seen_minutes:
                    continue  # skip duplicate threshold
                seen_minutes.add(m)
                db.session.add(EmployeeLateRule(
                    brand_id=brand_id,
                    min_late_minutes=m,
                    deduction_amount=a,
                ))

        db.session.commit()
        flash('تم حفظ الإعدادات بنجاح', 'success')
        return redirect(url_for('employees.settings', brand_id=brand_id))

    late_rules = EmployeeLateRule.query.filter_by(
        brand_id=brand_id
    ).order_by(EmployeeLateRule.min_late_minutes.asc()).all()

    return render_template('employees/settings.html',
                          form=form,
                          brand=brand,
                          brands=brands,
                          settings=employee_settings,
                          late_rules=late_rules)


# ============== REPORT ROUTES ==============

@employees_bp.route('/report')
@login_required
def report():
    """Employee performance report"""
    if not (current_user.is_owner or current_user.is_brand_manager or current_user.is_branch_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brand
    if current_user.is_owner:
        brands = Brand.query.filter_by(is_active=True).all()
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id and brands:
            brand_id = brands[0].id
    else:
        brand_id = current_user.brand_id
        brands = [current_user.brand] if current_user.brand else []

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
    if not (current_user.is_owner or current_user.is_brand_manager or current_user.is_branch_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    employee = User.query.get_or_404(user_id)

    # Check access — owner sees all, others only their brand/branch employees
    if not current_user.is_owner:
        if current_user.brand_id != employee.brand_id:
            flash('ليس لديك صلاحية', 'danger')
            return redirect(url_for('dashboard.index'))
        if current_user.is_branch_manager and current_user.branch_id and employee.branch_id != current_user.branch_id:
            flash('ليس لديك صلاحية', 'danger')
            return redirect(url_for('dashboard.index'))

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
    """Give reward to employee"""
    if not (current_user.is_owner or current_user.is_brand_manager or current_user.is_branch_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    employee = User.query.get_or_404(user_id)
    if not current_user.is_owner and current_user.brand_id != employee.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))
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
    if not (current_user.is_owner or current_user.is_brand_manager or current_user.is_branch_manager):
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
    """Give deduction to employee"""
    if not (current_user.is_owner or current_user.is_brand_manager or current_user.is_branch_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    employee = User.query.get_or_404(user_id)
    if not current_user.is_owner and current_user.brand_id != employee.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))
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


def _can_remove_deductions():
    """Only admin and brand owner can remove deductions or wrong attendance records."""
    return current_user.is_owner or (
        current_user.role and current_user.role.name_en == 'owner'
    )


@employees_bp.route('/deductions/<int:deduction_id>/delete', methods=['POST'])
@login_required
def delete_deduction(deduction_id):
    """Delete a deduction (admin / brand owner only)."""
    if not _can_remove_deductions():
        flash('يقدر يحذف الخصم مالك البراند فقط', 'danger')
        return redirect(url_for('dashboard.index'))

    deduction = EmployeeDeduction.query.get_or_404(deduction_id)
    if not current_user.is_owner and current_user.brand_id != deduction.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    user_id = deduction.user_id
    db.session.delete(deduction)
    db.session.commit()
    flash('تم حذف الخصم', 'success')
    return redirect(url_for('employees.details', user_id=user_id))


@employees_bp.route('/attendance/<int:attendance_id>/delete', methods=['POST'])
@login_required
def delete_attendance(attendance_id):
    """Delete an attendance record + its auto-deductions (admin / brand owner only)."""
    if not _can_remove_deductions():
        flash('يقدر يحذف سجل الحضور مالك البراند فقط', 'danger')
        return redirect(url_for('dashboard.index'))

    att = EmployeeAttendance.query.get_or_404(attendance_id)
    if not current_user.is_owner and current_user.brand_id != att.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    user_id = att.user_id
    # Cascade: remove auto-deductions linked to this attendance record
    EmployeeDeduction.query.filter_by(attendance_id=att.id).delete()
    db.session.delete(att)
    db.session.commit()
    flash('تم حذف سجل الحضور والخصومات المرتبطة به', 'success')
    return redirect(url_for('employees.details', user_id=user_id))


# ============== ATTENDANCE ROUTES ==============

@employees_bp.route('/attendance', methods=['GET', 'POST'])
@login_required
def attendance():
    """Manual attendance entry"""
    if not (current_user.is_owner or current_user.is_brand_manager or current_user.is_branch_manager):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brand — admin sees all, others see their own
    if current_user.is_owner:
        brands = Brand.query.filter_by(is_active=True).all()
        brand_id = request.args.get('brand_id', type=int)
        if not brand_id and brands:
            brand_id = brands[0].id
    else:
        brand_id = current_user.brand_id
        brands = [current_user.brand] if current_user.brand else []

    brand = Brand.query.get(brand_id) if brand_id else None

    # Get employees — scoped by brand, and by branch for branch_manager
    employees_query = User.query.filter(
        User.brand_id == brand_id,
        User.is_active == True
    )
    # Branch manager sees only their branch employees
    if current_user.is_branch_manager and current_user.branch_id:
        employees_query = employees_query.filter(User.branch_id == current_user.branch_id)

    employees = employees_query.all()

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
                threshold = settings.late_threshold_minutes or 0
                if check_in_mins > start_mins + threshold:
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

            # Auto deduction for lateness — tiered first, fallback to flat amount
            if status == 'late' and settings.auto_deduction_enabled:
                tier_amount = EmployeeLateRule.get_deduction_for(brand_id, late_minutes)
                deduction_amount = tier_amount if tier_amount is not None else (settings.auto_deduction_amount or 0)
                if deduction_amount and float(deduction_amount) > 0:
                    deduction = EmployeeDeduction(
                        user_id=form.user_id.data,
                        brand_id=brand_id,
                        title='خصم تأخير',
                        amount=deduction_amount,
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


# ============== EMPLOYEE SHIFTS ==============

@employees_bp.route('/shifts')
@login_required
def shifts():
    """List all employee shifts"""
    if not current_user.is_owner and not current_user.is_brand_manager and not current_user.is_branch_manager:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    # Get brands
    if current_user.is_owner:
        brands = Brand.query.filter_by(is_active=True).all()
    else:
        brands = [current_user.brand] if current_user.brand else []

    brand_id = request.args.get('brand_id', type=int)
    if not brand_id and brands:
        brand_id = brands[0].id

    brand = Brand.query.get(brand_id) if brand_id else None

    # Get employees for this brand
    employees = []
    if brand:
        users = User.query.filter_by(brand_id=brand_id, is_active=True).all()
        for user in users:
            shift = EmployeeShift.query.filter_by(user_id=user.id, is_active=True).first()
            brand_settings = EmployeeSettings.get_or_create(brand_id)
            employees.append({
                'user': user,
                'shift': shift,
                'using_brand_default': shift is None,
                'start_time': shift.work_start_time if shift else brand_settings.work_start_time,
                'end_time': shift.work_end_time if shift else brand_settings.work_end_time,
                'days': shift.days_arabic if shift else 'كل الأيام (افتراضي)',
                'threshold': shift.get_late_threshold(brand_settings) if shift else (brand_settings.late_threshold_minutes or 15)
            })

    return render_template('employees/shifts.html',
                           brand=brand,
                           brands=brands,
                           employees=employees)


@employees_bp.route('/<int:user_id>/shift', methods=['GET', 'POST'])
@login_required
def edit_shift(user_id):
    """Edit shift for a specific employee"""
    if not current_user.is_owner and not current_user.is_brand_manager and not current_user.is_branch_manager:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    user = User.query.get_or_404(user_id)

    # Check brand access
    if not current_user.is_owner and current_user.brand_id != user.brand_id:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    shift = EmployeeShift.query.filter_by(user_id=user_id, is_active=True).first()
    brand_settings = EmployeeSettings.get_or_create(user.brand_id)

    form = EmployeeShiftForm()

    if request.method == 'GET':
        if shift:
            form.work_start_time.data = shift.work_start_time
            form.work_end_time.data = shift.work_end_time
            form.late_threshold_minutes.data = shift.late_threshold_minutes
            # Set day checkboxes
            days = shift.days_list
            form.day_sat.data = 0 in days
            form.day_sun.data = 1 in days
            form.day_mon.data = 2 in days
            form.day_tue.data = 3 in days
            form.day_wed.data = 4 in days
            form.day_thu.data = 5 in days
            form.day_fri.data = 6 in days
        else:
            # Default to brand settings
            form.work_start_time.data = brand_settings.work_start_time
            form.work_end_time.data = brand_settings.work_end_time
            form.late_threshold_minutes.data = brand_settings.late_threshold_minutes
            # All days checked by default
            form.day_sat.data = True
            form.day_sun.data = True
            form.day_mon.data = True
            form.day_tue.data = True
            form.day_wed.data = True
            form.day_thu.data = True
            form.day_fri.data = True

    if form.validate_on_submit():
        # Build applicable_days string
        days = []
        if form.day_sat.data: days.append('0')
        if form.day_sun.data: days.append('1')
        if form.day_mon.data: days.append('2')
        if form.day_tue.data: days.append('3')
        if form.day_wed.data: days.append('4')
        if form.day_thu.data: days.append('5')
        if form.day_fri.data: days.append('6')
        applicable_days = ','.join(days) if len(days) < 7 else None  # None = all days

        if shift:
            shift.work_start_time = form.work_start_time.data
            shift.work_end_time = form.work_end_time.data
            shift.applicable_days = applicable_days
            shift.late_threshold_minutes = form.late_threshold_minutes.data
        else:
            shift = EmployeeShift(
                user_id=user_id,
                brand_id=user.brand_id,
                work_start_time=form.work_start_time.data,
                work_end_time=form.work_end_time.data,
                applicable_days=applicable_days,
                late_threshold_minutes=form.late_threshold_minutes.data,
                created_by=current_user.id
            )
            db.session.add(shift)

        db.session.commit()
        flash(f'تم حفظ مناوبة {user.name} بنجاح', 'success')
        return redirect(url_for('employees.shifts', brand_id=user.brand_id))

    return render_template('employees/shift_form.html',
                           form=form,
                           user=user,
                           shift=shift,
                           brand_settings=brand_settings)


@employees_bp.route('/<int:user_id>/shift/delete', methods=['POST'])
@login_required
def delete_shift(user_id):
    """Remove custom shift (revert to brand default)"""
    if not current_user.is_owner and not current_user.is_brand_manager and not current_user.is_branch_manager:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    shift = EmployeeShift.query.filter_by(user_id=user_id, is_active=True).first()
    if shift:
        shift.is_active = False
        db.session.commit()
        flash('تم إزالة المناوبة المخصصة، سيتم استخدام الإعداد الافتراضي', 'success')

    user = User.query.get(user_id)
    return redirect(url_for('employees.shifts', brand_id=user.brand_id if user else None))


# ============== BULK CONVERT MEMBERS → EMPLOYEES ==============

@employees_bp.route('/from-members', methods=['GET', 'POST'])
@login_required
def from_members():
    """
    Bulk-convert members (synced from tmkq.mdb) into User employees.
    Owner/Branch_manager/Admin only. Each selected member gets a User record
    with the same fingerprint_id. Their gate scans then count as work shifts.
    """
    if not (current_user.role and current_user.role.name_en in ('admin', 'owner', 'branch_manager')):
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('dashboard.index'))

    from app.models.member import Member
    from app.models.company import Branch
    import secrets as _secrets

    # Build branch list based on role
    if current_user.role.name_en == 'admin':
        branches = Branch.query.filter_by(is_active=True).all()
    elif current_user.role.name_en == 'owner':
        branches = Branch.query.filter_by(brand_id=current_user.brand_id, is_active=True).all()
    else:  # branch_manager
        branches = Branch.query.filter_by(id=current_user.branch_id, is_active=True).all()

    role_names = ['employee', 'branch_receptionist', 'branch_finance']
    roles = Role.query.filter(Role.name_en.in_(role_names)).all()

    if request.method == 'POST':
        member_ids = request.form.getlist('member_ids', type=int)
        branch_id = request.form.get('branch_id', type=int)
        role_id = request.form.get('role_id', type=int)
        department = (request.form.get('department') or '').strip() or None
        is_trainer = request.form.get('is_trainer') == 'on'

        if not member_ids:
            flash('يرجى تحديد أعضاء على الأقل واحد', 'warning')
            return redirect(url_for('employees.from_members'))
        if not branch_id or branch_id not in [b.id for b in branches]:
            flash('يرجى اختيار فرع صحيح', 'danger')
            return redirect(url_for('employees.from_members'))
        if not role_id or role_id not in [r.id for r in roles]:
            flash('يرجى اختيار دور صحيح', 'danger')
            return redirect(url_for('employees.from_members'))

        target_branch = Branch.query.get(branch_id)
        target_brand_id = target_branch.brand_id

        converted = 0
        skipped = 0
        new_users_for_backfill = []
        for mid in member_ids:
            member = Member.query.get(mid)
            if not member or member.is_staff or not current_user.can_access_brand(member.brand_id):
                skipped += 1
                continue
            # Cross-brand safety: members must belong to same brand as target branch
            if member.brand_id != target_brand_id:
                skipped += 1
                continue

            slug = (member.member_import_id or str(member.id)).strip('0') or str(member.id)
            email = f'emp_{slug}_{member.brand_id}@gym.local'
            # Avoid email collisions
            if User.query.filter_by(email=email).first():
                email = f'emp_{slug}_{member.brand_id}_{_secrets.token_hex(3)}@gym.local'

            new_user = User(
                name=member.name,
                email=email,
                role_id=role_id,
                brand_id=member.brand_id,
                branch_id=branch_id,
                fingerprint_id=member.fingerprint_id,
                is_trainer=is_trainer,
                department=department,
                is_active=True,
            )
            new_user.set_password(_secrets.token_urlsafe(16))
            db.session.add(new_user)
            db.session.flush()

            member.is_staff = True
            member.staff_user_id = new_user.id
            member.branch_id = branch_id
            converted += 1
            # Track for backfill after commit
            new_users_for_backfill.append(new_user)

        db.session.commit()

        # Backfill EmployeeAttendance from past 60 days of MemberAttendance for each
        try:
            from app.routes.fingerprint import backfill_employee_attendance_from_member_scans
            for nu in new_users_for_backfill:
                backfill_employee_attendance_from_member_scans(nu, nu.branch_id, days=60)
            db.session.commit()
        except Exception:
            db.session.rollback()

        flash(f'تم تحويل {converted} عضو إلى موظفين. تم تجاهل {skipped}.', 'success')
        return redirect(url_for('employees.index') if False else url_for('employees.from_members'))

    # GET — list candidates
    query = Member.query.filter(
        Member.is_staff.is_(False),
        Member.fingerprint_id.isnot(None),
    )
    if current_user.role.name_en == 'admin':
        pass
    elif current_user.role.name_en == 'owner':
        query = query.filter(Member.brand_id == current_user.brand_id)
    else:
        query = query.filter(Member.branch_id == current_user.branch_id)

    # Branch filter — when a branch is picked, only show its members
    selected_branch_id = request.args.get('branch_id', type=int)
    if selected_branch_id and selected_branch_id in [b.id for b in branches]:
        query = query.filter(Member.branch_id == selected_branch_id)
    else:
        selected_branch_id = None

    # Branch_manager always locked to their own branch
    if current_user.role.name_en == 'branch_manager':
        selected_branch_id = current_user.branch_id

    search = (request.args.get('q') or '').strip()
    if search:
        query = query.filter(
            db.or_(
                Member.name.ilike(f'%{search}%'),
                Member.phone.ilike(f'%{search}%'),
                Member.member_import_id.ilike(f'%{search}%'),
            )
        )

    candidates = query.order_by(Member.name).limit(200).all() if selected_branch_id else []

    return render_template('employees/from_members.html',
                           candidates=candidates,
                           branches=branches,
                           roles=roles,
                           search=search,
                           selected_branch_id=selected_branch_id)


@employees_bp.route('/from-members/<int:member_id>/convert', methods=['POST'])
@login_required
def from_member_one(member_id):
    """
    Convert a single member to employee via JSON.
    Accepts: role_id, branch_id, department, is_trainer, base_salary, email, password.
    Returns JSON with success status and message.
    """
    if not (current_user.role and current_user.role.name_en in ('admin', 'owner', 'branch_manager')):
        return jsonify({'success': False, 'message': 'ليس لديك صلاحية'}), 403

    from app.models.member import Member
    from app.models.company import Branch
    import secrets as _secrets

    member = Member.query.get_or_404(member_id)

    if member.is_staff:
        return jsonify({'success': False, 'message': 'هذا العضو موظف بالفعل'}), 400
    if not current_user.can_access_brand(member.brand_id):
        return jsonify({'success': False, 'message': 'ليس لديك صلاحية على هذا العضو'}), 403

    # Allowed branches for current user (within member's brand)
    if current_user.role.name_en == 'admin':
        allowed_branches = Branch.query.filter_by(brand_id=member.brand_id, is_active=True).all()
    elif current_user.role.name_en == 'owner':
        allowed_branches = Branch.query.filter_by(brand_id=current_user.brand_id, is_active=True).all()
    else:
        allowed_branches = Branch.query.filter_by(id=current_user.branch_id, is_active=True).all()
    allowed_branch_ids = {b.id for b in allowed_branches}

    role_names = ['employee', 'branch_receptionist', 'branch_finance']
    allowed_role_ids = {r.id for r in Role.query.filter(Role.name_en.in_(role_names)).all()}

    branch_id = request.form.get('branch_id', type=int)
    role_id = request.form.get('role_id', type=int)
    department = (request.form.get('department') or '').strip() or None
    is_trainer = request.form.get('is_trainer') in ('on', 'true', '1')
    custom_email = (request.form.get('email') or '').strip().lower()
    custom_password = (request.form.get('password') or '').strip()
    base_salary_raw = (request.form.get('base_salary') or '').strip()

    if not branch_id or branch_id not in allowed_branch_ids:
        return jsonify({'success': False, 'message': 'يرجى اختيار فرع صحيح'}), 400
    if not role_id or role_id not in allowed_role_ids:
        return jsonify({'success': False, 'message': 'يرجى اختيار دور صحيح'}), 400

    target_branch = Branch.query.get(branch_id)
    if target_branch.brand_id != member.brand_id:
        return jsonify({'success': False, 'message': 'الفرع لا يطابق براند العضو'}), 400

    base_salary = None
    if base_salary_raw:
        try:
            base_salary = float(base_salary_raw)
            if base_salary < 0:
                raise ValueError()
        except ValueError:
            return jsonify({'success': False, 'message': 'مبلغ الراتب غير صالح'}), 400

    # Email
    if custom_email:
        email = custom_email
    else:
        slug = (member.member_import_id or str(member.id)).strip('0') or str(member.id)
        email = f'emp_{slug}_{member.brand_id}@gym.local'
    if User.query.filter_by(email=email).first():
        if custom_email:
            return jsonify({'success': False, 'message': f'البريد {email} مستخدم بالفعل'}), 400
        email = f'emp_{slug}_{member.brand_id}_{_secrets.token_hex(3)}@gym.local'

    password = custom_password or _secrets.token_urlsafe(16)

    new_user = User(
        name=member.name,
        email=email,
        role_id=role_id,
        brand_id=member.brand_id,
        branch_id=branch_id,
        fingerprint_id=member.fingerprint_id,
        is_trainer=is_trainer,
        department=department,
        is_active=True,
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.flush()

    member.is_staff = True
    member.staff_user_id = new_user.id
    member.branch_id = branch_id

    if base_salary is not None and base_salary > 0:
        today = date.today()
        salary_record = Salary(
            user_id=new_user.id,
            brand_id=member.brand_id,
            month=today.month,
            year=today.year,
            base_salary=base_salary,
            deductions=0,
            bonuses=0,
            net_salary=base_salary,
            status='pending',
        )
        db.session.add(salary_record)

    db.session.commit()

    # Backfill EmployeeAttendance from past 60 days of MemberAttendance scans
    try:
        from app.routes.fingerprint import backfill_employee_attendance_from_member_scans
        backfill_employee_attendance_from_member_scans(new_user, branch_id, days=60)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({
        'success': True,
        'message': f'تم تحويل {member.name} إلى موظف',
        'member_id': member.id,
        'user_id': new_user.id,
        'email': email,
        'has_login': bool(custom_password),
    })
