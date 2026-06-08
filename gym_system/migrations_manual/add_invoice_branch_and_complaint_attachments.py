#!/usr/bin/env python
"""GYM-15 + GYM-21 migrations.

- invoices.branch_id / branch_name / branch_phone / branch_address  (snapshot
  of the issuing branch so invoice headers carry the branch name)
- complaint_attachments table

Boot-time guards in app/__init__.py do the same thing so existing dev DBs
pick them up automatically. This script lets ops trigger the same effect
explicitly (e.g. on PythonAnywhere where the web app is reloaded once and
the boot hook only runs at that point).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _column_exists(conn, table, column):
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    if rows:
        return any(r[1] == column for r in rows)
    try:
        from sqlalchemy import text
        row = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ), {"t": table, "c": column}).first()
        return row is not None
    except Exception:
        return False


def run_migration():
    from app import create_app, db
    app = create_app()
    with app.app_context():
        print("Starting migration: GYM-15 invoice branch + GYM-21 complaint attachments")
        with db.engine.connect() as conn:
            for col, ddl in (
                ('branch_id',      'INTEGER'),
                ('branch_name',    'VARCHAR(120)'),
                ('branch_phone',   'VARCHAR(40)'),
                ('branch_address', 'VARCHAR(200)'),
            ):
                if _column_exists(conn, 'invoices', col):
                    print(f'  ⏭  invoices.{col} already exists')
                else:
                    conn.exec_driver_sql(f"ALTER TABLE invoices ADD COLUMN {col} {ddl}")
                    print(f'  ✅ Added invoices.{col}')

            try:
                conn.exec_driver_sql(
                    "CREATE TABLE IF NOT EXISTS complaint_attachments ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "complaint_id INTEGER NOT NULL, "
                    "filename VARCHAR(255) NOT NULL, "
                    "original_name VARCHAR(255), "
                    "uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                    "FOREIGN KEY(complaint_id) REFERENCES complaints(id))"
                )
                print('  ✅ complaint_attachments table ready')
            except Exception as e:
                print(f'  ⚠️  complaint_attachments: {e}')

            conn.commit()
        print("\n✅ Migration completed.")


if __name__ == '__main__':
    run_migration()
