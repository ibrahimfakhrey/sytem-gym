"""Health Reports routes"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import FloatField, IntegerField, SelectField
from wtforms.validators import DataRequired, NumberRange, Optional
from datetime import datetime

from app import db
from app.models import Member, HealthReport

health_bp = Blueprint('health', __name__, url_prefix='/health')


class HealthReportForm(FlaskForm):
    """Form for creating health report"""
    height_cm = FloatField('الطول (سم)', validators=[DataRequired(), NumberRange(min=100, max=250)])
    weight_kg = FloatField('الوزن (كجم)', validators=[DataRequired(), NumberRange(min=30, max=300)])
    age = IntegerField('العمر', validators=[DataRequired(), NumberRange(min=10, max=100)])
    gender = SelectField('الجنس', choices=[
        ('male', 'ذكر'),
        ('female', 'أنثى')
    ], validators=[DataRequired()])


@health_bp.route('/members/<int:member_id>/report')
@login_required
def view_report(member_id):
    """View member's latest health report"""
    member = Member.query.get_or_404(member_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != member.brand_id:
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('members.index'))

    # Get latest report
    report = member.health_reports.first()

    return render_template('health/report.html', member=member, report=report)


@health_bp.route('/members/<int:member_id>/report/history')
@login_required
def report_history(member_id):
    """View member's health report history"""
    member = Member.query.get_or_404(member_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != member.brand_id:
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('members.index'))

    reports = member.health_reports.all()

    return render_template('health/history.html', member=member, reports=reports)


@health_bp.route('/members/<int:member_id>/report/create', methods=['GET', 'POST'])
@login_required
def create_report(member_id):
    """Generate health report for member"""
    member = Member.query.get_or_404(member_id)

    # Check access
    if not current_user.is_owner and current_user.brand_id != member.brand_id:
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('members.index'))

    form = HealthReportForm()

    # Pre-fill from member data
    if request.method == 'GET':
        if member.height_cm:
            form.height_cm.data = member.height_cm
        if member.weight_kg:
            form.weight_kg.data = member.weight_kg
        if member.birth_date:
            today = datetime.today()
            age = today.year - member.birth_date.year
            if today.month < member.birth_date.month or \
               (today.month == member.birth_date.month and today.day < member.birth_date.day):
                age -= 1
            form.age.data = age
        form.gender.data = member.gender or 'male'

    if form.validate_on_submit():
        # Update member's measurements
        member.height_cm = form.height_cm.data
        member.weight_kg = form.weight_kg.data

        # Generate report
        report = HealthReport.generate_report(
            member_id=member.id,
            height_cm=form.height_cm.data,
            weight_kg=form.weight_kg.data,
            age=form.age.data,
            gender=form.gender.data,
            created_by=current_user.id
        )

        flash('تم إنشاء التقرير الصحي بنجاح', 'success')
        return redirect(url_for('health.view_report', member_id=member.id))

    return render_template('health/form.html', form=form, member=member)


@health_bp.route('/report/<int:report_id>/print')
@login_required
def print_report(report_id):
    """Print health report"""
    report = HealthReport.query.get_or_404(report_id)
    member = report.member

    # Check access
    if not current_user.is_owner and current_user.brand_id != member.brand_id:
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('members.index'))

    return render_template('health/print.html', report=report, member=member)


@health_bp.route('/report/<int:report_id>/share')
@login_required
def share_report(report_id):
    """Generate WhatsApp share link for report"""
    report = HealthReport.query.get_or_404(report_id)
    member = report.member

    # Check access
    if not current_user.is_owner and current_user.brand_id != member.brand_id:
        return jsonify({'error': 'ليس لديك صلاحية'}), 403

    # Build message
    message = f"""🏋️ التقرير الصحي - {member.name}
📅 التاريخ: {report.created_at.strftime('%Y-%m-%d')}

📏 القياسات:
• الطول: {report.height_cm} سم
• الوزن: {report.weight_kg} كجم
• العمر: {report.age} سنة

📊 النتائج:
• مؤشر كتلة الجسم (BMI): {report.bmi}
• التصنيف: {report.bmi_category}
• الوزن المثالي: {report.ideal_weight} كجم
• الفرق: {abs(report.weight_difference) if report.weight_difference else 0} كجم

🔥 معدل الحرق:
• معدل الأيض الأساسي: {int(report.metabolic_rate)} سعرة
• السعرات اليومية المطلوبة: {int(report.daily_calories)} سعرة

💪 الحالة: {report.status_arabic}
"""

    # Clean phone number
    phone = member.phone
    if phone:
        phone = phone.replace(' ', '').replace('-', '')
        if phone.startswith('0'):
            phone = '966' + phone[1:]
        elif not phone.startswith('966') and not phone.startswith('+'):
            phone = '966' + phone

    whatsapp_url = f"https://wa.me/{phone}?text={message}"

    return jsonify({
        'message': message,
        'whatsapp_url': whatsapp_url,
        'phone': phone
    })


# API endpoint for calculating without saving
@health_bp.route('/api/calculate', methods=['POST'])
@login_required
def api_calculate():
    """Calculate health metrics without saving"""
    data = request.get_json()

    height_cm = data.get('height_cm')
    weight_kg = data.get('weight_kg')
    age = data.get('age')
    gender = data.get('gender', 'male')

    if not all([height_cm, weight_kg, age]):
        return jsonify({'error': 'Missing required fields'}), 400

    bmi = HealthReport.calculate_bmi(weight_kg, height_cm)
    bmr = HealthReport.calculate_bmr(weight_kg, height_cm, age, gender)
    daily_calories = HealthReport.calculate_daily_calories(bmr)
    ideal_weight = HealthReport.calculate_ideal_weight(height_cm, gender)
    weight_difference = round(weight_kg - ideal_weight, 1) if weight_kg and ideal_weight else None
    status, status_message = HealthReport.get_bmi_status(bmi)

    return jsonify({
        'bmi': bmi,
        'bmi_category': status_message.split(' - ')[1] if status_message and ' - ' in status_message else None,
        'metabolic_rate': bmr,
        'daily_calories': daily_calories,
        'ideal_weight': ideal_weight,
        'weight_difference': weight_difference,
        'status': status,
        'status_message': status_message
    })
