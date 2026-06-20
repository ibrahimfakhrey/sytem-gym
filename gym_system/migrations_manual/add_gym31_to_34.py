#!/usr/bin/env python
"""GYM-31..34 — schema additions for soft-delete, day-pass discount, dedupe.

Run from gym_system/ root::

    cd ~/sytem-gym/gym_system
    python3 migrations_manual/add_gym31_to_34.py

Then reload the web app from the PythonAnywhere Web tab. Idempotent — safe
to re-run; columns are only added when missing.

Columns added by this script
----------------------------
* ``day_passes.discount``        NUMERIC(10,2) NOT NULL DEFAULT 0   (GYM-33)
* ``subscriptions.is_deleted``   BOOLEAN NOT NULL DEFAULT 0          (GYM-32)
* ``expenses.is_deleted``        BOOLEAN NOT NULL DEFAULT 0          (GYM-32)
* ``income.is_deleted``          BOOLEAN NOT NULL DEFAULT 0          (GYM-32)

The boot-time guard in ``app/__init__.py`` performs the same ALTERs on first
request, but ops who like to run schema migrations explicitly before
reloading should use this script.
"""
from __future__ import annotations

import os
import sys

# Make ``app`` importable when this file runs from anywhere.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


# (table, column, "ALTER TABLE ... ADD COLUMN ..." DDL)
_ADDITIONS = [
    ('day_passes',            'discount',   'ALTER TABLE day_passes ADD COLUMN discount NUMERIC(10,2) NOT NULL DEFAULT 0'),
    ('subscriptions',         'is_deleted', 'ALTER TABLE subscriptions ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0'),
    ('expenses',              'is_deleted', 'ALTER TABLE expenses ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0'),
    ('income',                'is_deleted', 'ALTER TABLE income ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0'),
    # GYM-38 — soft-delete per individual subscription_payment row.
    ('subscription_payments', 'is_deleted', 'ALTER TABLE subscription_payments ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0'),
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
        print('=== GYM-31..34 schema migration ===\n')
        added = skipped = 0
        with db.engine.connect() as conn:
            for table, column, ddl in _ADDITIONS:
                cols = _existing_columns(conn, table)
                if not cols:
                    print(f'  ?  {table:<14}  table not found — skipping {column}')
                    skipped += 1
                    continue
                if column in cols:
                    print(f'  -  {table:<14}  {column} already present')
                    skipped += 1
                    continue
                try:
                    conn.exec_driver_sql(ddl)
                    print(f'  +  {table:<14}  added {column}')
                    added += 1
                except Exception as e:
                    print(f'  !  {table:<14}  FAILED to add {column}: {e}')
            try:
                conn.commit()
            except Exception:
                pass

        print(f'\nDone. added={added} skipped={skipped} of {len(_ADDITIONS)}')
        print('Reload the PythonAnywhere web app to pick up the schema change.\n')


if __name__ == '__main__':
    run_migration()
