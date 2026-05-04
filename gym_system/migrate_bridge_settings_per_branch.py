"""
Migrate bridge_settings table from UNIQUE(brand_id) to UNIQUE(brand_id, branch_id)
so each branch can have its own row.

Idempotent: safe to run multiple times.

Honors DATABASE_URL when set (for PythonAnywhere / production), otherwise falls
back to the local instance path. Only sqlite is supported (the project's
production setup is sqlite via DATABASE_URL=sqlite:///...).
"""
import os
import sqlite3
import sys


def _resolve_db_path() -> str:
    url = os.environ.get('DATABASE_URL', '').strip()
    if url:
        if url.startswith('sqlite:///'):
            return url[len('sqlite:///'):]
        if url.startswith('sqlite:'):
            return url[len('sqlite:'):]
        print(f'DATABASE_URL is not sqlite ({url}); this migration only handles sqlite.',
              file=sys.stderr)
        sys.exit(1)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'gym_system.db')


DB_PATH = _resolve_db_path()


def needs_migration(con):
    cur = con.cursor()
    cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='bridge_settings'"
    )
    row = cur.fetchone()
    if not row:
        print('bridge_settings table does not exist — nothing to do.')
        return False
    sql = row[0] or ''
    # Old schema declared `UNIQUE (brand_id)` as a standalone table-level constraint.
    return 'UNIQUE (brand_id)' in sql and 'UNIQUE (brand_id, branch_id)' not in sql


def migrate():
    con = sqlite3.connect(DB_PATH)
    con.execute('PRAGMA foreign_keys = OFF')
    try:
        if not needs_migration(con):
            print('Schema already correct. No migration needed.')
            return

        cur = con.cursor()
        cur.execute('BEGIN')

        cur.execute('ALTER TABLE bridge_settings RENAME TO bridge_settings_old')

        cur.execute(
            """
            CREATE TABLE bridge_settings (
                id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                branch_id INTEGER,
                class_access_window_minutes INTEGER,
                att2000_mdb_path VARCHAR(500),
                backup_mdb_path VARCHAR(500),
                attendance_sync_interval INTEGER,
                access_control_interval INTEGER,
                class_access_control_enabled BOOLEAN,
                employee_shift_tracking_enabled BOOLEAN,
                auto_block_expired BOOLEAN,
                created_at DATETIME,
                updated_at DATETIME,
                PRIMARY KEY (id),
                CONSTRAINT uq_bridge_settings_brand_branch UNIQUE (brand_id, branch_id),
                FOREIGN KEY(brand_id) REFERENCES brands (id),
                FOREIGN KEY(branch_id) REFERENCES branches (id)
            )
            """
        )

        cur.execute(
            """
            INSERT INTO bridge_settings (
                id, brand_id, branch_id, class_access_window_minutes,
                att2000_mdb_path, backup_mdb_path,
                attendance_sync_interval, access_control_interval,
                class_access_control_enabled, employee_shift_tracking_enabled,
                auto_block_expired, created_at, updated_at
            )
            SELECT
                id, brand_id, branch_id, class_access_window_minutes,
                att2000_mdb_path, backup_mdb_path,
                attendance_sync_interval, access_control_interval,
                class_access_control_enabled, employee_shift_tracking_enabled,
                auto_block_expired, created_at, updated_at
            FROM bridge_settings_old
            """
        )

        cur.execute('DROP TABLE bridge_settings_old')

        con.commit()
        print('Migrated bridge_settings: UNIQUE constraint is now (brand_id, branch_id).')

        cur.execute('SELECT COUNT(*) FROM bridge_settings')
        print(f'Rows preserved: {cur.fetchone()[0]}')
    except Exception:
        con.rollback()
        raise
    finally:
        con.execute('PRAGMA foreign_keys = ON')
        con.close()


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print(f'Database not found at {DB_PATH}', file=sys.stderr)
        sys.exit(1)
    migrate()
