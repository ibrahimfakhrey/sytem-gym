#!/usr/bin/env python
"""GYM-62 — class management schema: courses, sessions, enrollments.

Run from gym_system/ root::

    cd ~/sytem-gym/gym_system
    python3 migrations_manual/add_gym62_classes.py

Then reload the web app from the PythonAnywhere Web tab. Idempotent — safe
to re-run; columns are only added when missing, tables only created if
they don't exist, backfill only touches rows where the target field is null.

What this script does
---------------------
* ``gym_classes.start_date``               DATE
* ``gym_classes.end_date``                 DATE
* ``gym_classes.weekday_mask``             INTEGER DEFAULT 0
* ``gym_classes.price``                    NUMERIC(10,2) DEFAULT 0
* ``gym_classes.trainer_fee_per_session``  NUMERIC(10,2) DEFAULT 0
* ``gym_classes.status``                   VARCHAR(20) DEFAULT 'active'
* ``class_bookings.session_id``            INTEGER
* ``class_bookings.enrollment_id``         INTEGER
* CREATE TABLE ``class_sessions``
* CREATE TABLE ``class_enrollments``
* Backfill legacy ``gym_classes`` rows:
    - ``weekday_mask = 1 << day_of_week``  (when null/0)
    - ``start_date  = date(created_at)``   (when null)
    - ``end_date    = created_at + 365d``  (when null)
    - ``status      = 'active'``           (when null)

The boot-time guard in ``app/__init__.py`` performs the same operations on
first request; this script exists for ops who prefer to run schema
migrations explicitly before reloading, and to print a clear result table.
"""
from __future__ import annotations

import os
import sys

# Make ``app`` importable when this file runs from anywhere.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


# (table, column, "ALTER TABLE ... ADD COLUMN ..." DDL)
_ADDITIONS = [
    ('gym_classes',    'start_date',              'ALTER TABLE gym_classes ADD COLUMN start_date DATE'),
    ('gym_classes',    'end_date',                'ALTER TABLE gym_classes ADD COLUMN end_date DATE'),
    ('gym_classes',    'weekday_mask',            'ALTER TABLE gym_classes ADD COLUMN weekday_mask INTEGER DEFAULT 0'),
    ('gym_classes',    'price',                   'ALTER TABLE gym_classes ADD COLUMN price NUMERIC(10,2) DEFAULT 0'),
    ('gym_classes',    'trainer_fee_per_session', 'ALTER TABLE gym_classes ADD COLUMN trainer_fee_per_session NUMERIC(10,2) DEFAULT 0'),
    ('gym_classes',    'status',                  "ALTER TABLE gym_classes ADD COLUMN status VARCHAR(20) DEFAULT 'active'"),
    ('class_bookings', 'session_id',              'ALTER TABLE class_bookings ADD COLUMN session_id INTEGER'),
    ('class_bookings', 'enrollment_id',           'ALTER TABLE class_bookings ADD COLUMN enrollment_id INTEGER'),
]

_NEW_TABLES = [
    ('class_sessions', """
        CREATE TABLE IF NOT EXISTS class_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            session_date DATE NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            status VARCHAR(20) DEFAULT 'scheduled' NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(class_id) REFERENCES gym_classes(id)
        )
    """),
    ('class_sessions_index', """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_class_sessions_class_date
            ON class_sessions(class_id, session_date)
    """),
    ('class_enrollments', """
        CREATE TABLE IF NOT EXISTS class_enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            subscription_id INTEGER,
            invoice_id INTEGER,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            sessions_total INTEGER DEFAULT 0,
            total_amount NUMERIC(10,2) DEFAULT 0,
            paid_amount NUMERIC(10,2) DEFAULT 0,
            refund_amount NUMERIC(10,2) DEFAULT 0,
            status VARCHAR(20) DEFAULT 'active' NOT NULL,
            notes TEXT,
            created_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            cancelled_at DATETIME,
            FOREIGN KEY(class_id) REFERENCES gym_classes(id),
            FOREIGN KEY(member_id) REFERENCES members(id),
            FOREIGN KEY(subscription_id) REFERENCES subscriptions(id),
            FOREIGN KEY(invoice_id) REFERENCES invoices(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """),
]

# Backfill statements — each one is idempotent; safe on re-run.
_BACKFILLS = [
    (
        'gym_classes.weekday_mask ← 1 << day_of_week',
        "UPDATE gym_classes SET weekday_mask = (1 << day_of_week) "
        "WHERE day_of_week IS NOT NULL AND (weekday_mask IS NULL OR weekday_mask = 0)",
    ),
    (
        'gym_classes.start_date ← date(created_at)',
        "UPDATE gym_classes SET start_date = date(created_at) "
        "WHERE start_date IS NULL AND created_at IS NOT NULL",
    ),
    (
        "gym_classes.end_date ← created_at + 365d",
        "UPDATE gym_classes SET end_date = date(created_at, '+365 days') "
        "WHERE end_date IS NULL AND created_at IS NOT NULL",
    ),
    (
        "gym_classes.status ← 'active'",
        "UPDATE gym_classes SET status = 'active' WHERE status IS NULL",
    ),
]


def _existing_columns(conn, table: str) -> set[str]:
    """Return the column names of ``table``. Works on SQLite + Postgres."""
    # SQLite path
    try:
        rows = conn.exec_driver_sql(
            f"PRAGMA table_info({table})"
        ).fetchall()
        cols = {r[1] for r in rows}
        if cols:
            return cols
    except Exception:
        pass
    # Postgres / information_schema path
    try:
        from sqlalchemy import text
        rows = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t"
        ), {"t": table}).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def run_migration() -> None:
    from app import create_app, db
    app = create_app()
    with app.app_context():
        print('=== GYM-62 class management schema migration ===\n')
        added = skipped = failed = 0

        with db.engine.connect() as conn:
            # 1. Add missing columns
            print('[1/3] Adding columns:')
            for table, column, ddl in _ADDITIONS:
                cols = _existing_columns(conn, table)
                if not cols:
                    print(f'  ?  {table:<15}  table not found — skipping {column}')
                    skipped += 1
                    continue
                if column in cols:
                    print(f'  -  {table:<15}  {column} already present')
                    skipped += 1
                    continue
                try:
                    conn.exec_driver_sql(ddl)
                    print(f'  +  {table:<15}  added {column}')
                    added += 1
                except Exception as e:
                    print(f'  !  {table:<15}  FAILED to add {column}: {e}')
                    failed += 1

            # 2. Create new tables (+ index)
            print('\n[2/3] Ensuring new tables:')
            for name, ddl in _NEW_TABLES:
                try:
                    conn.exec_driver_sql(ddl)
                    print(f'  ✓  {name}')
                except Exception as e:
                    print(f'  !  {name} FAILED: {e}')
                    failed += 1

            # 3. Backfill legacy rows
            print('\n[3/3] Backfilling legacy gym_classes rows:')
            for label, stmt in _BACKFILLS:
                try:
                    result = conn.exec_driver_sql(stmt)
                    rc = getattr(result, 'rowcount', None)
                    rc_txt = f'({rc} row{"s" if rc != 1 else ""})' if rc is not None and rc >= 0 else ''
                    print(f'  ✓  {label} {rc_txt}')
                except Exception as e:
                    print(f'  !  {label} FAILED: {e}')
                    failed += 1

            try:
                conn.commit()
            except Exception:
                pass

        print(f'\nDone. columns_added={added} skipped={skipped} failed={failed} '
              f'of {len(_ADDITIONS)}')
        if failed:
            print('⚠  Some statements failed — check the log above.')
            print('   If prod is on a non-SQLite DB, the boot guard also relies on\n'
                  '   the same SQL — you may need to run adapted statements manually.')
        else:
            print('✓  All good. Reload the PythonAnywhere web app to pick up the change.\n')


if __name__ == '__main__':
    run_migration()
