#!/usr/bin/env python3
"""Fix: Add branch_code and branch_id columns to production database."""
from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    print("=== Adding missing columns ===")

    columns = [
        ('branches', 'branch_code VARCHAR(20)'),
        ('bridge_status', 'branch_id INTEGER'),
        ('bridge_settings', 'branch_id INTEGER'),
        ('device_commands', 'branch_id INTEGER'),
        ('fingerprint_sync_logs', 'branch_id INTEGER'),
    ]

    for table, col_def in columns:
        col_name = col_def.split()[0]
        try:
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {col_def}'))
            db.session.commit()
            print(f'  Added {table}.{col_name}')
        except Exception as e:
            db.session.rollback()
            print(f'  {table}.{col_name}: already exists')

    print("\n=== Generating branch codes ===")
    db.session.execute(text("UPDATE branches SET branch_code = 'BR-' || brand_id || '-' || id WHERE branch_code IS NULL"))
    db.session.commit()

    print("\n=== Stamping alembic ===")
    try:
        db.session.execute(text("DELETE FROM alembic_version"))
        db.session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('8843c681fd29')"))
        db.session.commit()
        print("  Stamped to 8843c681fd29")
    except Exception as e:
        db.session.rollback()
        print(f"  Stamp: {e}")

    print("\n=== Verification ===")
    from app.models.company import Branch
    for b in Branch.query.all():
        print(f'  {b.branch_code}: {b.name}')
    print("\n=== Done ===")
