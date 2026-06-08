#!/usr/bin/env python
"""GYM-23: day-pass tables (walk-in tickets).

Creates two tables if they don't already exist:

* day_pass_prices  — owner's per-activity price catalogue
                     (one row per brand + service_type)
* day_passes       — issued tickets (price snapshot, customer info,
                     valid_from/until, payment method, created_by)

Boot-time `db.create_all()` in app/__init__.py already does the same thing
when the web app starts. This script is for ops who prefer to run the
migration explicitly before reloading the web app on PythonAnywhere.

Usage on PythonAnywhere (Bash console)::

    cd ~/sytem-gym/gym_system
    python3 migrations_manual/add_day_passes.py

Then reload the web app from the Web tab.
"""
import os
import sys

# Make `app` importable when run as `python3 path/to/this/file.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _table_exists(conn, table):
    """SQLite-friendly table-existence check with a portable fallback."""
    try:
        row = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None
    except Exception:
        pass
    try:
        from sqlalchemy import text
        row = conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
        ), {"t": table}).first()
        return row is not None
    except Exception:
        return False


# DDL kept SQLite-friendly. Postgres tolerates this form too (INTEGER PRIMARY
# KEY AUTOINCREMENT works in both via SQLite's emulation; Postgres ignores
# AUTOINCREMENT and uses the sequence on SERIAL/IDENTITY columns — adjust if
# you're on Postgres and want a true serial column).
DDL_DAY_PASS_PRICES = """
CREATE TABLE IF NOT EXISTS day_pass_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL,
    service_type_id INTEGER NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(brand_id) REFERENCES brands(id),
    FOREIGN KEY(service_type_id) REFERENCES service_types(id),
    CONSTRAINT uq_day_pass_price UNIQUE (brand_id, service_type_id)
)
"""

DDL_DAY_PASSES = """
CREATE TABLE IF NOT EXISTS day_passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL,
    branch_id INTEGER,
    service_type_id INTEGER NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    customer_phone VARCHAR(40),
    customer_age INTEGER,
    pass_date DATE NOT NULL,
    valid_from TIME,
    valid_until TIME,
    price NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(20) DEFAULT 'cash',
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    FOREIGN KEY(brand_id) REFERENCES brands(id),
    FOREIGN KEY(branch_id) REFERENCES branches(id),
    FOREIGN KEY(service_type_id) REFERENCES service_types(id),
    FOREIGN KEY(created_by) REFERENCES users(id)
)
"""


def run_migration():
    from app import create_app, db

    app = create_app()
    with app.app_context():
        print('Starting migration: GYM-23 day-pass tables')

        with db.engine.connect() as conn:
            for name, ddl in (
                ('day_pass_prices', DDL_DAY_PASS_PRICES),
                ('day_passes',      DDL_DAY_PASSES),
            ):
                if _table_exists(conn, name):
                    print(f'  ⏭  {name} already exists')
                else:
                    conn.exec_driver_sql(ddl)
                    print(f'  ✅ created {name}')

            conn.commit()

        print('\n✅ Migration completed.')


if __name__ == '__main__':
    run_migration()
