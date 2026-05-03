"""One-time migration: create employee_late_rules table and backfill from old single-amount config.

Run this once on each environment after pulling the new code:
    python migrate_late_rules.py

It is safe to run multiple times — the table creation is idempotent and the
backfill skips any brand that already has tier rules.
"""
from app import create_app, db
from app.models.employee import EmployeeSettings, EmployeeLateRule


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        print('Tables created (or already existed).')

        backfilled = 0
        for s in EmployeeSettings.query.all():
            if EmployeeLateRule.query.filter_by(brand_id=s.brand_id).count() > 0:
                continue
            if s.auto_deduction_enabled and s.auto_deduction_amount and float(s.auto_deduction_amount) > 0:
                db.session.add(EmployeeLateRule(
                    brand_id=s.brand_id,
                    min_late_minutes=s.late_threshold_minutes or 15,
                    deduction_amount=s.auto_deduction_amount,
                ))
                backfilled += 1
        db.session.commit()
        print(f'Backfilled {backfilled} rule(s).')


if __name__ == '__main__':
    main()
