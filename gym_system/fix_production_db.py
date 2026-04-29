#!/usr/bin/env python3
"""
Production database fix script.
Run this on PythonAnywhere after git pull if migrations fail.
Usage: python3 fix_production_db.py
"""
from app import create_app, db
from app.models.user import Role
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("=== Fixing production database ===\n")

    # 1. Add fingerprint columns to branches
    columns = [
        ('uses_fingerprint', 'BOOLEAN DEFAULT 0'),
        ('fingerprint_ip', 'VARCHAR(15)'),
        ('fingerprint_port', 'INTEGER DEFAULT 5005'),
    ]
    for col_name, col_type in columns:
        try:
            db.session.execute(text(f'ALTER TABLE branches ADD COLUMN {col_name} {col_type}'))
            db.session.commit()
            print(f'  Added branches.{col_name}')
        except Exception as e:
            db.session.rollback()
            if 'duplicate' in str(e).lower() or 'already exists' in str(e).lower():
                print(f'  branches.{col_name} already exists')
            else:
                print(f'  branches.{col_name}: {e}')

    # 2. Add member_import_id to members
    try:
        db.session.execute(text('ALTER TABLE members ADD COLUMN member_import_id VARCHAR(20)'))
        db.session.commit()
        print(f'  Added members.member_import_id')
    except Exception as e:
        db.session.rollback()
        print(f'  members.member_import_id: already exists or {e}')

    # 3. Create employee_shifts table
    try:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS employee_shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                brand_id INTEGER NOT NULL REFERENCES brands(id),
                work_start_time TIME NOT NULL,
                work_end_time TIME NOT NULL,
                applicable_days VARCHAR(20),
                late_threshold_minutes INTEGER,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME,
                created_by INTEGER REFERENCES users(id)
            )
        '''))
        db.session.commit()
        print(f'  Created employee_shifts table')
    except Exception as e:
        db.session.rollback()
        print(f'  employee_shifts: {e}')

    # 4. Create bridge_settings table
    try:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS bridge_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand_id INTEGER NOT NULL UNIQUE REFERENCES brands(id),
                class_access_window_minutes INTEGER DEFAULT 15,
                att2000_mdb_path VARCHAR(500),
                backup_mdb_path VARCHAR(500),
                attendance_sync_interval INTEGER DEFAULT 30,
                access_control_interval INTEGER DEFAULT 60,
                class_access_control_enabled BOOLEAN DEFAULT 1,
                employee_shift_tracking_enabled BOOLEAN DEFAULT 1,
                auto_block_expired BOOLEAN DEFAULT 1,
                created_at DATETIME,
                updated_at DATETIME
            )
        '''))
        db.session.commit()
        print(f'  Created bridge_settings table')
    except Exception as e:
        db.session.rollback()
        print(f'  bridge_settings: {e}')

    # 5. Copy fingerprint data from brands to branches
    try:
        db.session.execute(text('''
            UPDATE branches SET
                uses_fingerprint = (SELECT uses_fingerprint FROM brands WHERE brands.id = branches.brand_id),
                fingerprint_ip = (SELECT fingerprint_ip FROM brands WHERE brands.id = branches.brand_id),
                fingerprint_port = (SELECT fingerprint_port FROM brands WHERE brands.id = branches.brand_id)
            WHERE uses_fingerprint IS NULL
        '''))
        db.session.commit()
        print(f'  Copied fingerprint data from brands to branches')
    except Exception as e:
        db.session.rollback()
        print(f'  Fingerprint copy: {e}')

    # 6. Role restructuring: rename roles
    role_renames = [
        ('owner', 'admin', 'أدمن'),
        ('brand_manager', 'owner', 'المالك'),
        ('receptionist', 'branch_receptionist', 'استقبال فرع'),
        ('finance', 'branch_finance', 'مالية فرع'),
        ('coach', 'employee', 'موظف'),
    ]
    for old_en, new_en, new_ar in role_renames:
        existing = Role.query.filter_by(name_en=old_en).first()
        already_done = Role.query.filter_by(name_en=new_en).first()
        if existing and not already_done:
            existing.name_en = new_en
            existing.name = new_ar
            db.session.commit()
            print(f'  Renamed role {old_en} -> {new_en} ({new_ar})')
        elif already_done:
            print(f'  Role {new_en} already exists')
        else:
            print(f'  Role {old_en} not found (may already be renamed)')

    # 7. Add new roles if missing
    new_roles = [
        ('branch_manager', 'مدير الفرع', {
            'can_manage_members': True, 'can_manage_subscriptions': True,
            'can_view_finance': True, 'can_manage_finance': True,
            'can_view_reports': True, 'can_manage_attendance': True,
            'can_view_complaints': True, 'can_manage_complaints': True,
            'can_view_daily_closing': True, 'can_manage_daily_closing': True,
            'can_manage_classes': True, 'can_approve_expenses': True,
            'can_manage_offers': True, 'can_manage_gift_cards': True,
        }),
        ('brand_finance', 'مالية براند', {
            'can_view_finance': True, 'can_manage_finance': True,
            'can_view_reports': True,
            'can_view_daily_closing': True, 'can_manage_daily_closing': True,
        }),
    ]
    for name_en, name_ar, perms in new_roles:
        if not Role.query.filter_by(name_en=name_en).first():
            role = Role(name=name_ar, name_en=name_en, description=name_ar, **perms)
            db.session.add(role)
            db.session.commit()
            print(f'  Added role: {name_en} ({name_ar})')
        else:
            print(f'  Role {name_en} already exists')

    # 8. Stamp migration head
    try:
        db.session.execute(text("DELETE FROM alembic_version"))
        db.session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('994ef56af55e')"))
        db.session.commit()
        print(f'  Stamped alembic to 994ef56af55e')
    except Exception as e:
        db.session.rollback()
        print(f'  Alembic stamp: {e}')

    # 9. Verify
    print('\n=== Verification ===')
    roles = Role.query.all()
    print(f'Total roles: {len(roles)}')
    for r in roles:
        print(f'  {r.name_en}: {r.name}')

    from app.models.company import Branch
    b = Branch.query.first()
    if b:
        print(f'\nBranch fingerprint: uses_fingerprint={b.uses_fingerprint}, ip={b.fingerprint_ip}')

    print('\n=== Done ===')
