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
    # GYM-43 — soft-delete for staff users.
    ('users',                 'is_deleted',  'ALTER TABLE users ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0'),
    # GYM-51 — archive-then-delete flow for complaints.
    ('complaints',            'is_archived', 'ALTER TABLE complaints ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0'),
    ('complaints',            'archived_at', 'ALTER TABLE complaints ADD COLUMN archived_at DATETIME'),
    ('complaints',            'archived_by', 'ALTER TABLE complaints ADD COLUMN archived_by INTEGER'),
    # GYM-57 — iqama tracking on users.
    ('users',                 'iqama_number',     'ALTER TABLE users ADD COLUMN iqama_number VARCHAR(30)'),
    ('users',                 'iqama_start_date', 'ALTER TABLE users ADD COLUMN iqama_start_date DATE'),
    ('users',                 'iqama_end_date',   'ALTER TABLE users ADD COLUMN iqama_end_date DATE'),
    # GYM-60 — per-branch display_number on members. Backfill handled by
    # the boot guard the first time it sees the missing column (see
    # app/__init__.py).
    ('members',               'display_number',   'ALTER TABLE members ADD COLUMN display_number INTEGER'),
]

# GYM-55 / 58 / 61 — new tables. Additive: create if not exists.
_NEW_TABLES = [
    ('subscription_freeze_requests', """
        CREATE TABLE IF NOT EXISTS subscription_freeze_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            freeze_start DATE NOT NULL,
            freeze_days INTEGER NOT NULL,
            reason TEXT,
            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            rejection_reason TEXT,
            requested_by INTEGER,
            requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            reviewed_by INTEGER,
            reviewed_at DATETIME,
            FOREIGN KEY(subscription_id) REFERENCES subscriptions(id),
            FOREIGN KEY(requested_by) REFERENCES users(id),
            FOREIGN KEY(reviewed_by) REFERENCES users(id)
        )
    """),
    ('pending_edits', """
        CREATE TABLE IF NOT EXISTS pending_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type VARCHAR(40) NOT NULL,
            entity_id INTEGER NOT NULL,
            action VARCHAR(20) NOT NULL,
            payload_json TEXT,
            summary VARCHAR(280),
            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            rejection_reason TEXT,
            brand_id INTEGER,
            requested_by INTEGER,
            requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            reviewed_by INTEGER,
            reviewed_at DATETIME,
            FOREIGN KEY(brand_id) REFERENCES brands(id),
            FOREIGN KEY(requested_by) REFERENCES users(id),
            FOREIGN KEY(reviewed_by) REFERENCES users(id)
        )
    """),
    ('edit_audit_logs', """
        CREATE TABLE IF NOT EXISTS edit_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type VARCHAR(40) NOT NULL,
            entity_id INTEGER NOT NULL,
            field_name VARCHAR(40) NOT NULL,
            old_value VARCHAR(200),
            new_value VARCHAR(200),
            brand_id INTEGER,
            changed_by INTEGER,
            changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            note VARCHAR(200),
            FOREIGN KEY(brand_id) REFERENCES brands(id),
            FOREIGN KEY(changed_by) REFERENCES users(id)
        )
    """),
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
                    # GYM-60 — one-shot backfill immediately after the
                    # column is created, per branch, ordered by created_at.
                    if table == 'members' and column == 'display_number':
                        try:
                            rows = conn.exec_driver_sql(
                                "SELECT id, branch_id FROM members "
                                "ORDER BY branch_id, created_at, id"
                            ).fetchall()
                            counters = {}
                            for mid, bid in rows:
                                counters[bid] = counters.get(bid, 0) + 1
                                conn.exec_driver_sql(
                                    "UPDATE members SET display_number = ? WHERE id = ?",
                                    (counters[bid], mid),
                                )
                            print(f'     backfilled {len(rows)} members with per-branch numbers')
                        except Exception as bf_err:
                            print(f'     !  backfill FAILED: {bf_err}')
                except Exception as e:
                    print(f'  !  {table:<14}  FAILED to add {column}: {e}')

            # GYM-55 / 58 / 61 — CREATE TABLE IF NOT EXISTS for the new tables.
            print()
            for table, ddl in _NEW_TABLES:
                try:
                    conn.exec_driver_sql(ddl)
                    print(f'  ✓  ensured table {table}')
                except Exception as e:
                    print(f'  !  ensuring {table} FAILED: {e}')

            try:
                conn.commit()
            except Exception:
                pass

        print(f'\nDone. added={added} skipped={skipped} of {len(_ADDITIONS)}')
        print('Reload the PythonAnywhere web app to pick up the schema change.\n')


if __name__ == '__main__':
    run_migration()
