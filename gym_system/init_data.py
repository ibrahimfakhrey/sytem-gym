#!/usr/bin/env python3
"""
Initialize database with default data for testing
"""
import os
os.environ.setdefault('FLASK_APP', 'run.py')

from app import create_app, db
from app.models.user import User, Role
from app.models.company import Company, Brand
from app.models.subscription import Plan
from app.models.finance import ExpenseCategory

app = create_app('development')

with app.app_context():
    # Check if already initialized
    if Role.query.first():
        print("Database already initialized!")
    else:
        print("Initializing database...")

        # Create roles
        roles = [
            Role(name='مالك', name_en='owner', is_owner=True, can_view_all_brands=True,
                 can_manage_members=True, can_manage_subscriptions=True,
                 can_view_finance=True, can_manage_finance=True,
                 can_view_reports=True, can_manage_attendance=True),
            Role(name='مدير براند', name_en='brand_manager', can_view_all_brands=False,
                 can_manage_members=True, can_manage_subscriptions=True,
                 can_view_finance=True, can_manage_finance=True,
                 can_view_reports=True, can_manage_attendance=True),
            Role(name='موظف استقبال', name_en='receptionist', can_view_all_brands=False,
                 can_manage_members=True, can_manage_subscriptions=True,
                 can_view_finance=False, can_manage_finance=False,
                 can_view_reports=False, can_manage_attendance=True),
            Role(name='مالية', name_en='finance', can_view_all_brands=False,
                 can_manage_members=False, can_manage_subscriptions=False,
                 can_view_finance=True, can_manage_finance=True,
                 can_view_reports=True, can_manage_attendance=False),
            Role(name='مدير مالية', name_en='finance_admin', can_view_all_brands=True,
                 can_manage_members=False, can_manage_subscriptions=False,
                 can_view_finance=True, can_manage_finance=False,
                 can_view_reports=True, can_manage_attendance=False),
            Role(name='موظف', name_en='employee', can_view_all_brands=False,
                 can_manage_members=False, can_manage_subscriptions=False,
                 can_view_finance=False, can_manage_finance=False,
                 can_view_reports=False, can_manage_attendance=True),
        ]

        for role in roles:
            db.session.add(role)

        db.session.commit()
        print("Created roles")

        # Create company
        company = Company(name='شركة الجيم')
        db.session.add(company)
        db.session.commit()
        print("Created company")

        # Create default brand
        brand = Brand(
            name='صالة الأبطال',
            company_id=company.id,
            uses_fingerprint=True,
            fingerprint_ip='192.168.1.224',
            fingerprint_port=5005,
            is_active=True
        )
        db.session.add(brand)
        db.session.commit()
        print("Created brand: صالة الأبطال")

        # Create admin user
        owner_role = Role.query.filter_by(name_en='owner').first()
        admin = User(
            name='مدير النظام',
            email='admin@gym.com',
            phone='0500000000',
            role_id=owner_role.id,
            is_active=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Created admin user: admin@gym.com / admin123")

        # Create subscription plans
        plans = [
            Plan(name='اشتراك شهري', duration_days=30, price=300,
                 max_freezes=1, max_freeze_days=7, brand_id=brand.id),
            Plan(name='اشتراك ربع سنوي', duration_days=90, price=750,
                 max_freezes=2, max_freeze_days=14, brand_id=brand.id),
            Plan(name='اشتراك نصف سنوي', duration_days=180, price=1400,
                 max_freezes=3, max_freeze_days=21, brand_id=brand.id),
            Plan(name='اشتراك سنوي', duration_days=365, price=2500,
                 max_freezes=4, max_freeze_days=30, brand_id=brand.id),
        ]

        for plan in plans:
            db.session.add(plan)

        db.session.commit()
        print("Created subscription plans")

        # Create expense categories
        categories = [
            ExpenseCategory(name='إيجار', brand_id=brand.id),
            ExpenseCategory(name='كهرباء', brand_id=brand.id),
            ExpenseCategory(name='ماء', brand_id=brand.id),
            ExpenseCategory(name='صيانة', brand_id=brand.id),
            ExpenseCategory(name='معدات', brand_id=brand.id),
            ExpenseCategory(name='تنظيف', brand_id=brand.id),
            ExpenseCategory(name='أخرى', brand_id=brand.id),
        ]

        for cat in categories:
            db.session.add(cat)

        db.session.commit()
        print("Created expense categories")

        print("\n" + "="*50)
        print("Database initialized successfully!")
        print("="*50)
        print("\nLogin credentials:")
        print("  Email: admin@gym.com")
        print("  Password: admin123")
        print("\nYou can now run: python run.py")
