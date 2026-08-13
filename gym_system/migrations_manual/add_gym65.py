#!/usr/bin/env python
"""GYM-65 — split payments: subscription_payments.invoice_id.

Run from gym_system/ root::

    cd ~/sytem-gym/gym_system
    python3 migrations_manual/add_gym65.py

Then reload the web app from the PythonAnywhere Web tab. Idempotent —
safe to re-run; column only added when missing.

What this script does
---------------------
* ``subscription_payments.invoice_id`` INTEGER (nullable FK to invoices.id)

This lets a single Invoice have multiple SubscriptionPayment rows, one
per method — the storage model behind the "تقسيم الدفعة" UI.

The boot-time guard in ``app/__init__.py`` performs the same ALTER on
first request; this script exists for ops who prefer explicit migrations.

GYM-66 (duplicate phone numbers) and GYM-67 (plan flag authoritative)
require NO schema changes and are omitted here — GYM-66 is a code-only
policy change, GYM-67 explicitly avoids a backfill (see the commit
message for why).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def _existing_columns(conn, table: str) -> set[str]:
    """Return the column names of ``table``. Works on SQLite + Postgres."""
    try:
        rows = conn.exec_driver_sql(
            f"PRAGMA table_info({table})"
        ).fetchall()
        cols = {r[1] for r in rows}
        if cols:
            return cols
    except Exception:
        pass
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
        print('=== GYM-65 split-payments schema migration ===\n')
        with db.engine.connect() as conn:
            cols = _existing_columns(conn, 'subscription_payments')
            if not cols:
                print('  ?  subscription_payments table not found — nothing to do')
                return
            if 'invoice_id' in cols:
                print('  -  subscription_payments.invoice_id already present')
            else:
                try:
                    conn.exec_driver_sql(
                        'ALTER TABLE subscription_payments ADD COLUMN invoice_id INTEGER'
                    )
                    print('  +  added subscription_payments.invoice_id')
                except Exception as e:
                    print(f'  !  FAILED to add invoice_id: {e}')

            try:
                conn.commit()
            except Exception:
                pass

        print('\n✓  Done. Reload the PythonAnywhere web app.\n')


if __name__ == '__main__':
    run_migration()
