#!/usr/bin/env python
"""GYM-28: create member_merge_logs table.

Records every smart-merge so undo stays a deterministic one-click operation.
Same shape as db.create_all() would produce — boot-time guard in
app/__init__.py also handles this, this script is for ops who like to run
migrations explicitly before reloading the web app.

Usage on PythonAnywhere::

    cd ~/sytem-gym/gym_system
    python3 migrations_manual/add_member_merge_log.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _table_exists(conn, table):
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


DDL = """
CREATE TABLE IF NOT EXISTS member_merge_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL,
    keeper_id INTEGER NOT NULL,
    loser_id INTEGER NOT NULL,
    loser_snapshot_json TEXT,
    moves_json TEXT,
    performed_by INTEGER,
    performed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    undone_at DATETIME,
    undone_by INTEGER,
    FOREIGN KEY(brand_id) REFERENCES brands(id),
    FOREIGN KEY(keeper_id) REFERENCES members(id),
    FOREIGN KEY(loser_id) REFERENCES members(id),
    FOREIGN KEY(performed_by) REFERENCES users(id),
    FOREIGN KEY(undone_by) REFERENCES users(id)
)
"""


def run_migration():
    from app import create_app, db
    app = create_app()
    with app.app_context():
        print('Starting migration: GYM-28 member_merge_logs table')
        with db.engine.connect() as conn:
            if _table_exists(conn, 'member_merge_logs'):
                print('  ⏭  member_merge_logs already exists')
            else:
                conn.exec_driver_sql(DDL)
                print('  ✅ created member_merge_logs')
            conn.commit()
        print('\n✅ Migration completed.')


if __name__ == '__main__':
    run_migration()
