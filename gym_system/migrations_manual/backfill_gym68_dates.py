#!/usr/bin/env python
"""GYM-68 follow-up — move the backfilled fp-access-log rows to 2026-07-01.

Run from gym_system/ root::

    cd ~/sytem-gym/gym_system
    python3 migrations_manual/backfill_gym68_dates.py

Idempotent — safe to re-run; only touches the rows created by the GYM-68
boot-guard backfill (identified by ``source='system'`` AND
``notes='backfilled initial log row (GYM-68)'``). Manual stop/allow
actions and the create()-hook rows (source='desktop'/'web') are NOT
touched.

Why
---
The GYM-68 boot-guard inserted ~9,519 log rows all timestamped with
CURRENT_TIMESTAMP at boot time. This script re-dates them to 2026-07-01
so the desktop bridge does not process them as "changes that happened
now" — instead they look like historical enrollments and the bridge
handles them accordingly.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

TARGET_DATE = '2026-07-01 00:00:00'


def run_migration() -> None:
    from app import create_app, db
    app = create_app()
    with app.app_context():
        print('=== GYM-68 backfill date-shift ===')
        print(f'target: {TARGET_DATE}\n')

        with db.engine.connect() as conn:
            # Count first so the operator sees what's about to change
            try:
                count = conn.exec_driver_sql("""
                    SELECT COUNT(*) FROM fingerprint_access_logs
                    WHERE source = 'system'
                      AND notes = 'backfilled initial log row (GYM-68)'
                """).fetchone()[0]
            except Exception as e:
                print(f'!  count query failed: {e}')
                return

            print(f'{count} backfilled rows found.')

            if count == 0:
                print('nothing to do — no matching rows.\n')
                return

            # Update. Uses a driver placeholder so SQLite and Postgres both work.
            try:
                conn.exec_driver_sql(
                    """
                    UPDATE fingerprint_access_logs
                    SET created_at = ?
                    WHERE source = 'system'
                      AND notes = 'backfilled initial log row (GYM-68)'
                    """,
                    (TARGET_DATE,),
                )
                conn.commit()
                print(f'✓  updated {count} rows to created_at = {TARGET_DATE}\n')
            except Exception as e:
                # Fallback for Postgres — %s placeholder
                try:
                    conn.exec_driver_sql(
                        """
                        UPDATE fingerprint_access_logs
                        SET created_at = %s
                        WHERE source = 'system'
                          AND notes = 'backfilled initial log row (GYM-68)'
                        """,
                        (TARGET_DATE,),
                    )
                    conn.commit()
                    print(f'✓  updated {count} rows to created_at = {TARGET_DATE}\n')
                except Exception as e2:
                    print(f'!  update failed: {e2}')


if __name__ == '__main__':
    run_migration()
