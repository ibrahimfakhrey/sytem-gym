#!/usr/bin/env python3
"""
Comprehensive seed data script for Gym Management System
Creates 3 brands with full data including:
- Staff accounts (all roles)
- Members (50-100 per brand)
- Subscription plans
- Subscriptions with payments
- Financial data (income, expenses, salaries)
- Attendance records (past 30 days)
"""

import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from app import create_app, db
from app.models.user import User, Role
from app.models.company import Company, Brand, Branch
from app.models.member import Member
from app.models.subscription import Plan, Subscription, SubscriptionPayment
from app.models.finance import Income, Expense, Salary
from app.models.attendance import MemberAttendance, EmployeeAttendance
from app.models.service import ServiceType
from app.models.complaint import ComplaintCategory, Complaint

# Arabic names for realistic data
MALE_NAMES = [
    'محمد أحمد', 'عبدالله خالد', 'فهد سعود', 'سلطان ناصر', 'عمر يوسف',
    'خالد إبراهيم', 'أحمد محمود', 'سعد عبدالرحمن', 'ماجد فيصل', 'طارق حسن',
    'يزيد سلمان', 'بدر عادل', 'راشد منصور', 'تركي بندر', 'نواف سامي',
    'عبدالعزيز وليد', 'صالح عثمان', 'ياسر كريم', 'هاني جمال', 'زياد مصطفى',
    'رامي شريف', 'باسم نبيل', 'وائل أشرف', 'حاتم علاء', 'مروان سيف',
    'أنس حازم', 'إياد رامز', 'كريم طاهر', 'سامر ياسين', 'نادر حسام',
    'عماد رشيد', 'جاسم فراس', 'حمد بسام', 'مشاري داود', 'غانم صقر',
    'ثامر عمار', 'لؤي معتز', 'أسامة رائد', 'شادي مهند', 'قصي زاهر'
]

FEMALE_NAMES = [
    'نورة سعد', 'سارة أحمد', 'لمى خالد', 'هند محمد', 'ريم عبدالله',
    'منى فهد', 'أمل سلطان', 'دانة ناصر', 'لينا يوسف', 'رنا إبراهيم',
    'ياسمين محمود', 'هالة عمر', 'سلمى طارق', 'نادية بدر', 'عبير راشد',
    'فاطمة تركي', 'مها نواف', 'ديمة عبدالعزيز', 'غادة صالح', 'نجوى ياسر',
    'سناء هاني', 'رباب زياد', 'إيمان رامي', 'سمر باسم', 'هدى وائل'
]

STAFF_NAMES = {
    'brand_manager': ['أحمد المدير', 'خالد الإداري', 'سعود المشرف'],
    'accountant': ['محمد المحاسب', 'فهد الحسابات', 'عمر المالي'],
    'receptionist': ['سارة الاستقبال', 'نورة الموظفة', 'لمى المكتب'],
    'trainer': ['كابتن أحمد', 'كابتن خالد', 'كابتن محمد'],
    'employee': ['عبدالله العامل', 'سعد الموظف', 'طارق المساعد']
}

EXPENSE_CATEGORIES = ['رواتب', 'إيجار', 'كهرباء', 'ماء', 'صيانة', 'معدات', 'تسويق', 'مستلزمات', 'أخرى']

def generate_phone():
    """Generate random Saudi phone number"""
    return f"05{random.randint(0,9)}{random.randint(10000000, 99999999)}"

def generate_email(name, domain):
    """Generate email from name"""
    clean_name = name.replace(' ', '.').lower()
    # Transliterate Arabic to English-ish
    transliteration = {
        'أ': 'a', 'ا': 'a', 'ب': 'b', 'ت': 't', 'ث': 'th', 'ج': 'j', 'ح': 'h',
        'خ': 'kh', 'د': 'd', 'ذ': 'th', 'ر': 'r', 'ز': 'z', 'س': 's', 'ش': 'sh',
        'ص': 's', 'ض': 'd', 'ط': 't', 'ظ': 'z', 'ع': 'a', 'غ': 'gh', 'ف': 'f',
        'ق': 'q', 'ك': 'k', 'ل': 'l', 'م': 'm', 'ن': 'n', 'ه': 'h', 'و': 'w',
        'ي': 'y', 'ى': 'a', 'ة': 'a', 'ئ': 'e', 'ء': '', 'إ': 'e', 'آ': 'a',
        ' ': '.', '.': '.'
    }
    email_name = ''.join(transliteration.get(c, c) for c in clean_name)
    return f"{email_name}@{domain}.com"

def seed_brands():
    """Create 3 brands with branches"""
    print("\n=== Creating Brands ===")

    # First, ensure we have a company
    company = Company.query.first()
    if not company:
        company = Company(name='مجموعة الأندية الرياضية', is_active=True)
        db.session.add(company)
        db.session.flush()
        print(f"  Created company: {company.name}")

    brands_data = [
        {
            'name': 'نادي الأبطال الرياضي',
            'slug': 'champions_gym',
            'branches': [
                {'name': 'فرع الرياض - العليا'},
                {'name': 'فرع الرياض - النخيل'}
            ]
        },
        {
            'name': 'نادي اللياقة الذهبي',
            'slug': 'golden_fitness',
            'branches': [
                {'name': 'فرع جدة - الكورنيش'},
                {'name': 'فرع جدة - التحلية'}
            ]
        },
        {
            'name': 'نادي القوة البدنية',
            'slug': 'power_gym',
            'branches': [
                {'name': 'فرع الدمام - الفيصلية'},
            ]
        }
    ]

    brands = []
    for i, brand_data in enumerate(brands_data):
        # Check if brand exists
        brand = Brand.query.filter_by(name=brand_data['name']).first()
        if not brand:
            brand = Brand(
                company_id=company.id,
                name=brand_data['name'],
                is_active=True,
                uses_fingerprint=True
            )
            db.session.add(brand)
            db.session.flush()
            print(f"  Created brand: {brand.name}")
        else:
            print(f"  Brand exists: {brand.name}")

        # Store slug for email generation
        brand.slug = brand_data['slug']

        # Create branches
        for branch_data in brand_data['branches']:
            branch = Branch.query.filter_by(brand_id=brand.id, name=branch_data['name']).first()
            if not branch:
                branch = Branch(
                    brand_id=brand.id,
                    name=branch_data['name'],
                    is_active=True
                )
                db.session.add(branch)
                print(f"    Created branch: {branch.name}")

        brands.append(brand)

    db.session.commit()
    return brands

def seed_service_types(brands):
    """Create service types for each brand"""
    print("\n=== Creating Service Types ===")

    services = [
        ('جيم', 'gym', 'gym'),
        ('سباحة', 'swimming', 'swimming'),
        ('كاراتيه', 'karate', 'martial_arts'),
        ('يوجا', 'yoga', 'fitness'),
        ('كروس فيت', 'crossfit', 'fitness')
    ]

    for brand in brands:
        for name, name_en, category in services:
            existing = ServiceType.query.filter_by(brand_id=brand.id, name=name).first()
            if not existing:
                service = ServiceType(
                    brand_id=brand.id,
                    name=name,
                    name_en=name_en,
                    category=category,
                    is_active=True
                )
                db.session.add(service)
        print(f"  Created services for: {brand.name}")

    db.session.commit()

def seed_complaint_categories():
    """Create global complaint categories"""
    print("\n=== Creating Complaint Categories ===")

    categories = [
        {'name': 'جهاز', 'name_en': 'equipment', 'icon': 'bi-tools'},
        {'name': 'مسبح', 'name_en': 'pool', 'icon': 'bi-water'},
        {'name': 'نظافة', 'name_en': 'cleanliness', 'icon': 'bi-brush'},
        {'name': 'خدمة', 'name_en': 'service', 'icon': 'bi-headset'},
        {'name': 'موظف', 'name_en': 'staff', 'icon': 'bi-person'},
        {'name': 'أخرى', 'name_en': 'other', 'icon': 'bi-three-dots'},
    ]

    for cat_data in categories:
        existing = ComplaintCategory.query.filter_by(name_en=cat_data['name_en']).first()
        if not existing:
            category = ComplaintCategory(
                name=cat_data['name'],
                name_en=cat_data['name_en'],
                icon=cat_data['icon'],
                is_active=True
            )
            db.session.add(category)
            print(f"  Created category: {cat_data['name']}")

    db.session.commit()

def seed_plans(brands):
    """Create subscription plans for each brand"""
    print("\n=== Creating Subscription Plans ===")

    plans_data = [
        {'name': 'اشتراك شهري', 'duration_days': 30, 'price': 300, 'max_freezes': 1, 'max_freeze_days': 7},
        {'name': 'اشتراك ربع سنوي', 'duration_days': 90, 'price': 750, 'max_freezes': 2, 'max_freeze_days': 14},
        {'name': 'اشتراك نصف سنوي', 'duration_days': 180, 'price': 1400, 'max_freezes': 3, 'max_freeze_days': 21},
        {'name': 'اشتراك سنوي', 'duration_days': 365, 'price': 2500, 'max_freezes': 4, 'max_freeze_days': 30},
        {'name': 'اشتراك VIP شهري', 'duration_days': 30, 'price': 500, 'max_freezes': 2, 'max_freeze_days': 10},
        {'name': 'اشتراك طلابي', 'duration_days': 30, 'price': 200, 'max_freezes': 1, 'max_freeze_days': 5},
    ]

    for brand in brands:
        for plan_data in plans_data:
            existing = Plan.query.filter_by(brand_id=brand.id, name=plan_data['name']).first()
            if not existing:
                plan = Plan(
                    brand_id=brand.id,
                    name=plan_data['name'],
                    duration_days=plan_data['duration_days'],
                    price=plan_data['price'],
                    max_freezes=plan_data['max_freezes'],
                    max_freeze_days=plan_data['max_freeze_days'],
                    is_active=True
                )
                db.session.add(plan)
        print(f"  Created plans for: {brand.name}")

    db.session.commit()

def seed_staff(brands):
    """Create staff accounts for each brand"""
    print("\n=== Creating Staff Accounts ===")

    roles = {r.name_en: r for r in Role.query.all()}
    staff_accounts = []

    for i, brand in enumerate(brands):
        branches = Branch.query.filter_by(brand_id=brand.id).all()
        main_branch = branches[0] if branches else None

        # Brand Manager
        role = roles.get('brand_manager')
        if role:
            name = STAFF_NAMES['brand_manager'][i % len(STAFF_NAMES['brand_manager'])]
            email = f"manager{i+1}@{brand.slug}.com"
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    name=name,
                    email=email,
                    phone=generate_phone(),
                    role_id=role.id,
                    brand_id=brand.id,
                    branch_id=main_branch.id if main_branch else None,
                    is_active=True
                )
                user.set_password('123456')
                db.session.add(user)
                staff_accounts.append({'brand': brand.name, 'role': 'مدير براند', 'email': email, 'password': '123456'})
                print(f"  Created manager for {brand.name}: {email}")

        # Accountant
        role = roles.get('accountant')
        if role:
            name = STAFF_NAMES['accountant'][i % len(STAFF_NAMES['accountant'])]
            email = f"accountant{i+1}@{brand.slug}.com"
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    name=name,
                    email=email,
                    phone=generate_phone(),
                    role_id=role.id,
                    brand_id=brand.id,
                    branch_id=main_branch.id if main_branch else None,
                    is_active=True
                )
                user.set_password('123456')
                db.session.add(user)
                staff_accounts.append({'brand': brand.name, 'role': 'محاسب', 'email': email, 'password': '123456'})
                print(f"  Created accountant for {brand.name}: {email}")

        # Receptionist
        role = roles.get('receptionist')
        if role:
            name = STAFF_NAMES['receptionist'][i % len(STAFF_NAMES['receptionist'])]
            email = f"reception{i+1}@{brand.slug}.com"
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    name=name,
                    email=email,
                    phone=generate_phone(),
                    role_id=role.id,
                    brand_id=brand.id,
                    branch_id=main_branch.id if main_branch else None,
                    is_active=True
                )
                user.set_password('123456')
                db.session.add(user)
                staff_accounts.append({'brand': brand.name, 'role': 'موظف استقبال', 'email': email, 'password': '123456'})
                print(f"  Created receptionist for {brand.name}: {email}")

        # Trainer
        role = roles.get('trainer')
        if role:
            name = STAFF_NAMES['trainer'][i % len(STAFF_NAMES['trainer'])]
            email = f"trainer{i+1}@{brand.slug}.com"
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    name=name,
                    email=email,
                    phone=generate_phone(),
                    role_id=role.id,
                    brand_id=brand.id,
                    branch_id=main_branch.id if main_branch else None,
                    is_active=True,
                    is_trainer=True
                )
                user.set_password('123456')
                db.session.add(user)
                staff_accounts.append({'brand': brand.name, 'role': 'مدرب', 'email': email, 'password': '123456'})
                print(f"  Created trainer for {brand.name}: {email}")

        # Employee
        role = roles.get('employee')
        if role:
            name = STAFF_NAMES['employee'][i % len(STAFF_NAMES['employee'])]
            email = f"employee{i+1}@{brand.slug}.com"
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    name=name,
                    email=email,
                    phone=generate_phone(),
                    role_id=role.id,
                    brand_id=brand.id,
                    branch_id=main_branch.id if main_branch else None,
                    is_active=True
                )
                user.set_password('123456')
                db.session.add(user)
                staff_accounts.append({'brand': brand.name, 'role': 'موظف', 'email': email, 'password': '123456'})
                print(f"  Created employee for {brand.name}: {email}")

    db.session.commit()
    return staff_accounts

def seed_members(brands, count_per_brand=75):
    """Create members for each brand"""
    print(f"\n=== Creating Members ({count_per_brand} per brand) ===")

    all_members = []

    for brand in brands:
        branches = Branch.query.filter_by(brand_id=brand.id).all()

        # Mix of male and female members
        male_count = int(count_per_brand * 0.7)
        female_count = count_per_brand - male_count

        fingerprint_id = 1

        # Male members
        for i in range(male_count):
            name = random.choice(MALE_NAMES) + f" {random.randint(1,99)}"
            phone = generate_phone()

            existing = Member.query.filter_by(brand_id=brand.id, phone=phone).first()
            if existing:
                continue

            member = Member(
                brand_id=brand.id,
                branch_id=random.choice(branches).id if branches else None,
                name=name,
                phone=phone,
                gender='male',
                birth_date=date.today() - timedelta(days=random.randint(18*365, 50*365)),
                height_cm=random.randint(160, 190),
                weight_kg=random.randint(60, 100),
                fingerprint_id=fingerprint_id,
                fingerprint_enrolled=random.choice([True, True, True, False]),
                is_active=True,
                created_at=datetime.now() - timedelta(days=random.randint(1, 365))
            )
            db.session.add(member)
            all_members.append(member)
            fingerprint_id += 1

        # Female members
        for i in range(female_count):
            name = random.choice(FEMALE_NAMES) + f" {random.randint(1,99)}"
            phone = generate_phone()

            existing = Member.query.filter_by(brand_id=brand.id, phone=phone).first()
            if existing:
                continue

            member = Member(
                brand_id=brand.id,
                branch_id=random.choice(branches).id if branches else None,
                name=name,
                phone=phone,
                gender='female',
                birth_date=date.today() - timedelta(days=random.randint(18*365, 45*365)),
                height_cm=random.randint(150, 175),
                weight_kg=random.randint(45, 80),
                fingerprint_id=fingerprint_id,
                fingerprint_enrolled=random.choice([True, True, True, False]),
                is_active=True,
                created_at=datetime.now() - timedelta(days=random.randint(1, 365))
            )
            db.session.add(member)
            all_members.append(member)
            fingerprint_id += 1

        print(f"  Created {count_per_brand} members for: {brand.name}")

    db.session.commit()
    return all_members

def seed_subscriptions(brands):
    """Create subscriptions for members"""
    print("\n=== Creating Subscriptions ===")

    for brand in brands:
        members = Member.query.filter_by(brand_id=brand.id, is_active=True).all()
        plans = Plan.query.filter_by(brand_id=brand.id, is_active=True).all()

        if not plans:
            continue

        subscription_count = 0
        for member in members:
            # 80% have active subscription, 10% expired, 10% no subscription
            chance = random.random()
            if chance > 0.9:
                continue  # No subscription

            plan = random.choice(plans)

            if chance > 0.8:
                # Expired subscription
                start_date = date.today() - timedelta(days=plan.duration_days + random.randint(10, 60))
                status = 'expired'
            else:
                # Active subscription
                days_into = random.randint(1, plan.duration_days - 5)
                start_date = date.today() - timedelta(days=days_into)
                status = 'active'

            end_date = start_date + timedelta(days=plan.duration_days)

            # Check existing subscription
            existing = Subscription.query.filter_by(member_id=member.id, status='active').first()
            if existing:
                continue

            discount = random.choice([0, 0, 0, 50, 100, 150])
            total_amount = float(plan.price) - discount
            paid_amount = total_amount if random.random() > 0.1 else total_amount * random.uniform(0.5, 0.9)
            payment_method = random.choice(['cash', 'cash', 'card', 'transfer'])

            subscription = Subscription(
                member_id=member.id,
                plan_id=plan.id,
                brand_id=brand.id,
                start_date=start_date,
                end_date=end_date,
                original_end_date=end_date,
                total_amount=total_amount,
                discount=discount,
                paid_amount=paid_amount,
                remaining_amount=total_amount - paid_amount,
                status=status,
                created_at=datetime.combine(start_date, datetime.min.time())
            )
            db.session.add(subscription)
            db.session.flush()

            # Create payment record
            payment = SubscriptionPayment(
                subscription_id=subscription.id,
                brand_id=brand.id,
                amount=paid_amount,
                payment_method=payment_method,
                payment_date=datetime.combine(start_date, datetime.min.time())
            )
            db.session.add(payment)

            # Create income record
            income = Income(
                brand_id=brand.id,
                subscription_id=subscription.id,
                amount=paid_amount,
                payment_method=payment_method,
                type='subscription',
                date=start_date,
                created_at=datetime.combine(start_date, datetime.min.time())
            )
            db.session.add(income)

            subscription_count += 1

        print(f"  Created {subscription_count} subscriptions for: {brand.name}")

    db.session.commit()

def seed_expenses(brands):
    """Create expense records for each brand"""
    print("\n=== Creating Expenses ===")

    for brand in brands:
        expense_count = 0

        # Monthly expenses for past 6 months
        for months_ago in range(6):
            expense_date = date.today().replace(day=1) - timedelta(days=30 * months_ago)

            # Rent
            expense = Expense(
                brand_id=brand.id,
                category_name='إيجار',
                amount=random.randint(15000, 30000),
                date=expense_date,
                description=f'إيجار شهر {expense_date.strftime("%m/%Y")}',
                status='approved',
                approved_at=datetime.combine(expense_date, datetime.min.time()),
                created_at=datetime.combine(expense_date, datetime.min.time())
            )
            db.session.add(expense)
            expense_count += 1

            # Electricity
            expense = Expense(
                brand_id=brand.id,
                category_name='كهرباء',
                amount=random.randint(2000, 5000),
                date=expense_date + timedelta(days=10),
                description=f'فاتورة كهرباء شهر {expense_date.strftime("%m/%Y")}',
                status='approved',
                approved_at=datetime.combine(expense_date, datetime.min.time()),
                created_at=datetime.combine(expense_date, datetime.min.time())
            )
            db.session.add(expense)
            expense_count += 1

            # Water
            expense = Expense(
                brand_id=brand.id,
                category_name='ماء',
                amount=random.randint(500, 1500),
                date=expense_date + timedelta(days=15),
                description=f'فاتورة مياه شهر {expense_date.strftime("%m/%Y")}',
                status='approved',
                approved_at=datetime.combine(expense_date, datetime.min.time()),
                created_at=datetime.combine(expense_date, datetime.min.time())
            )
            db.session.add(expense)
            expense_count += 1

            # Random maintenance
            if random.random() > 0.5:
                expense = Expense(
                    brand_id=brand.id,
                    category_name='صيانة',
                    amount=random.randint(500, 3000),
                    date=expense_date + timedelta(days=random.randint(1, 25)),
                    description='صيانة أجهزة',
                    status=random.choice(['approved', 'pending']),
                    created_at=datetime.combine(expense_date, datetime.min.time())
                )
                db.session.add(expense)
                expense_count += 1

        print(f"  Created {expense_count} expenses for: {brand.name}")

    db.session.commit()

def seed_salaries(brands):
    """Create salary records for staff"""
    print("\n=== Creating Salaries ===")

    for brand in brands:
        staff = User.query.filter_by(brand_id=brand.id, is_active=True).all()
        salary_count = 0

        for user in staff:
            # Base salary based on role
            base_salaries = {
                'brand_manager': 12000,
                'accountant': 8000,
                'receptionist': 5000,
                'trainer': 7000,
                'employee': 4000
            }

            base_salary = base_salaries.get(user.role.name_en, 5000) if user.role else 5000

            # Create salaries for past 3 months
            for months_ago in range(3):
                salary_month = date.today().month - months_ago
                salary_year = date.today().year
                if salary_month <= 0:
                    salary_month += 12
                    salary_year -= 1

                existing = Salary.query.filter_by(
                    user_id=user.id,
                    month=salary_month,
                    year=salary_year
                ).first()

                if existing:
                    continue

                deductions = random.choice([0, 0, 0, 100, 200, 300])
                bonuses = random.choice([0, 0, 500, 1000])

                salary = Salary(
                    user_id=user.id,
                    brand_id=brand.id,
                    month=salary_month,
                    year=salary_year,
                    base_salary=base_salary,
                    deductions=deductions,
                    bonuses=bonuses,
                    net_salary=base_salary - deductions + bonuses,
                    status='paid' if months_ago > 0 else 'pending',
                    created_at=datetime(salary_year, salary_month, 25)
                )
                db.session.add(salary)
                salary_count += 1

        print(f"  Created {salary_count} salary records for: {brand.name}")

    db.session.commit()

def seed_attendance(brands, days=30):
    """Create attendance records for past N days"""
    print(f"\n=== Creating Attendance Records (past {days} days) ===")

    for brand in brands:
        members = Member.query.filter_by(brand_id=brand.id, is_active=True).all()
        active_members = [m for m in members if m.active_subscription]

        attendance_count = 0

        for day_offset in range(days):
            check_date = date.today() - timedelta(days=day_offset)

            # Skip if weekend (Friday)
            if check_date.weekday() == 4:
                continue

            # Random subset of members attend each day (40-70%)
            attending_members = random.sample(
                active_members,
                k=min(len(active_members), int(len(active_members) * random.uniform(0.4, 0.7)))
            )

            for member in attending_members:
                # Random check-in time between 6 AM and 10 PM
                hour = random.randint(6, 22)
                minute = random.randint(0, 59)
                check_in_time = datetime.combine(check_date, datetime.min.time().replace(hour=hour, minute=minute))

                attendance = MemberAttendance(
                    member_id=member.id,
                    subscription_id=member.active_subscription.id if member.active_subscription else None,
                    brand_id=brand.id,
                    check_in=check_in_time,
                    source=random.choice(['fingerprint', 'fingerprint', 'manual', 'qr'])
                )
                db.session.add(attendance)
                attendance_count += 1

        print(f"  Created {attendance_count} attendance records for: {brand.name}")

    db.session.commit()

def main():
    """Main seed function"""
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("       COMPREHENSIVE DATA SEEDING")
        print("=" * 60)

        # 1. Create brands
        brands = seed_brands()

        # 2. Create service types
        seed_service_types(brands)

        # 3. Create complaint categories (global)
        seed_complaint_categories()

        # 4. Create subscription plans
        seed_plans(brands)

        # 5. Create staff accounts
        staff_accounts = seed_staff(brands)

        # 6. Create members
        seed_members(brands, count_per_brand=75)

        # 7. Create subscriptions
        seed_subscriptions(brands)

        # 8. Create expenses
        seed_expenses(brands)

        # 9. Create salaries
        seed_salaries(brands)

        # 10. Create attendance
        seed_attendance(brands, days=30)

        print("\n" + "=" * 60)
        print("       SEEDING COMPLETE!")
        print("=" * 60)

        # Print summary
        print("\n=== SUMMARY ===")
        print(f"Brands: {Brand.query.count()}")
        print(f"Branches: {Branch.query.count()}")
        print(f"Users (Staff): {User.query.count()}")
        print(f"Members: {Member.query.count()}")
        print(f"Plans: {Plan.query.count()}")
        print(f"Subscriptions: {Subscription.query.count()}")
        print(f"Income Records: {Income.query.count()}")
        print(f"Expenses: {Expense.query.count()}")
        print(f"Salaries: {Salary.query.count()}")
        print(f"Attendance Records: {MemberAttendance.query.count()}")

        # Print login credentials
        print("\n" + "=" * 60)
        print("       LOGIN CREDENTIALS")
        print("=" * 60)

        print("\n--- Owner Account ---")
        print("Email: admin@gym.com")
        print("Password: admin123")

        print("\n--- Brand Staff Accounts ---")
        for acc in staff_accounts:
            print(f"\n[{acc['brand']}] - {acc['role']}")
            print(f"  Email: {acc['email']}")
            print(f"  Password: {acc['password']}")

        print("\n" + "=" * 60)

if __name__ == '__main__':
    main()
