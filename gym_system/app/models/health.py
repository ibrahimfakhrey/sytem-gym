from datetime import datetime
from app import db


class HealthReport(db.Model):
    """Member health reports with BMI, calories, ideal weight calculations"""
    __tablename__ = 'health_reports'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)

    # Measurements
    height_cm = db.Column(db.Float)  # Height in centimeters
    weight_kg = db.Column(db.Float)  # Weight in kilograms
    age = db.Column(db.Integer)  # Age in years
    gender = db.Column(db.String(10))  # 'male' or 'female'

    # Calculated values
    bmi = db.Column(db.Float)  # مؤشر كتلة الجسم - Body Mass Index
    metabolic_rate = db.Column(db.Float)  # معدل الحرق - Basal Metabolic Rate (BMR)
    daily_calories = db.Column(db.Float)  # السعرات اليومية - Daily calorie needs
    ideal_weight = db.Column(db.Float)  # الوزن المثالي
    weight_difference = db.Column(db.Float)  # الفرق بين الوزن الحالي والمثالي

    # Status: needs_weight_loss (محتاج تخس), needs_weight_gain (محتاج تزود وزن), excellent (وضعك ممتاز)
    status = db.Column(db.String(30))
    status_message = db.Column(db.String(200))  # Detailed message

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    member = db.relationship('Member', backref=db.backref('health_reports', lazy='dynamic', order_by='desc(HealthReport.created_at)'))

    def __repr__(self):
        return f'<HealthReport {self.id} for Member {self.member_id}>'

    @classmethod
    def calculate_bmi(cls, weight_kg, height_cm):
        """Calculate BMI = weight(kg) / height(m)^2"""
        if not weight_kg or not height_cm or height_cm <= 0:
            return None
        height_m = height_cm / 100
        return round(weight_kg / (height_m ** 2), 1)

    @classmethod
    def calculate_bmr(cls, weight_kg, height_cm, age, gender):
        """
        Calculate Basal Metabolic Rate using Mifflin-St Jeor Equation
        Men: BMR = 10 × weight(kg) + 6.25 × height(cm) - 5 × age + 5
        Women: BMR = 10 × weight(kg) + 6.25 × height(cm) - 5 × age - 161
        """
        if not all([weight_kg, height_cm, age]):
            return None

        base = (10 * weight_kg) + (6.25 * height_cm) - (5 * age)

        if gender == 'male':
            return round(base + 5, 0)
        else:  # female
            return round(base - 161, 0)

    @classmethod
    def calculate_daily_calories(cls, bmr, activity_level='moderate'):
        """
        Calculate daily calorie needs based on activity level
        Sedentary: BMR × 1.2
        Light: BMR × 1.375
        Moderate: BMR × 1.55
        Active: BMR × 1.725
        Very Active: BMR × 1.9
        """
        if not bmr:
            return None

        multipliers = {
            'sedentary': 1.2,
            'light': 1.375,
            'moderate': 1.55,
            'active': 1.725,
            'very_active': 1.9
        }
        return round(bmr * multipliers.get(activity_level, 1.55), 0)

    @classmethod
    def calculate_ideal_weight(cls, height_cm, gender):
        """
        Calculate ideal weight using Devine formula
        Men: 50 + 2.3 × (height(in) - 60)
        Women: 45.5 + 2.3 × (height(in) - 60)
        """
        if not height_cm:
            return None

        height_inches = height_cm / 2.54

        if gender == 'male':
            ideal = 50 + (2.3 * (height_inches - 60))
        else:  # female
            ideal = 45.5 + (2.3 * (height_inches - 60))

        return round(max(ideal, 40), 1)  # Minimum 40kg

    @classmethod
    def get_bmi_status(cls, bmi):
        """Get BMI status and message in Arabic"""
        if not bmi:
            return None, None

        if bmi < 18.5:
            return 'needs_weight_gain', 'محتاج تزود وزن - نقص في الوزن'
        elif bmi < 25:
            return 'excellent', 'وضعك ممتاز - وزن طبيعي'
        elif bmi < 30:
            return 'needs_weight_loss', 'محتاج تخس - زيادة في الوزن'
        else:
            return 'needs_weight_loss', 'محتاج تخس - سمنة'

    @classmethod
    def generate_report(cls, member_id, height_cm, weight_kg, age, gender, created_by=None):
        """Generate a complete health report for a member"""
        # Calculate all values
        bmi = cls.calculate_bmi(weight_kg, height_cm)
        bmr = cls.calculate_bmr(weight_kg, height_cm, age, gender)
        daily_calories = cls.calculate_daily_calories(bmr)
        ideal_weight = cls.calculate_ideal_weight(height_cm, gender)
        weight_difference = round(weight_kg - ideal_weight, 1) if weight_kg and ideal_weight else None
        status, status_message = cls.get_bmi_status(bmi)

        # Create report
        report = cls(
            member_id=member_id,
            height_cm=height_cm,
            weight_kg=weight_kg,
            age=age,
            gender=gender,
            bmi=bmi,
            metabolic_rate=bmr,
            daily_calories=daily_calories,
            ideal_weight=ideal_weight,
            weight_difference=weight_difference,
            status=status,
            status_message=status_message,
            created_by=created_by
        )

        db.session.add(report)
        db.session.commit()
        return report

    @property
    def bmi_category(self):
        """Get BMI category in Arabic"""
        if not self.bmi:
            return 'غير محدد'
        if self.bmi < 18.5:
            return 'نقص في الوزن'
        elif self.bmi < 25:
            return 'وزن طبيعي'
        elif self.bmi < 30:
            return 'زيادة في الوزن'
        else:
            return 'سمنة'

    @property
    def status_arabic(self):
        """Get status in Arabic"""
        status_map = {
            'needs_weight_loss': 'محتاج تخس',
            'needs_weight_gain': 'محتاج تزود وزن',
            'excellent': 'وضعك ممتاز'
        }
        return status_map.get(self.status, 'غير محدد')

    @property
    def status_class(self):
        """Get CSS class for status"""
        status_classes = {
            'needs_weight_loss': 'warning',
            'needs_weight_gain': 'info',
            'excellent': 'success'
        }
        return status_classes.get(self.status, 'secondary')
