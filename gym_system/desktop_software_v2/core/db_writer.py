"""
DB Writer — write end_date updates to backup.mdb to control fingerprint access.

The ZKTeco device denies entry when end_date is in the past.
"""
import os
import time
from datetime import date
from typing import List, Dict, Tuple

try:
    import pyodbc
except ImportError:
    pyodbc = None


def _conn_str(path: str, password: str = None) -> str:
    driver = 'Microsoft Access Driver (*.mdb, *.accdb)'
    base = f'DRIVER={{{driver}}};DBQ={path};'
    if password:
        base += f'PWD={password};'
    return base


class DBWriter:
    def __init__(self, members_path: str, password: str = None):
        self.members_path = members_path
        self.password = password

    def _connect(self, attempts: int = 3, delay: float = 2.0):
        if pyodbc is None:
            raise RuntimeError('pyodbc not installed')
        if not self.members_path or not os.path.exists(self.members_path):
            raise FileNotFoundError(f'Database not found: {self.members_path}')

        last_err = None
        for i in range(attempts):
            try:
                return pyodbc.connect(_conn_str(self.members_path, self.password), timeout=10)
            except pyodbc.Error as e:
                last_err = e
                if 'locked' in str(e).lower() or 'in use' in str(e).lower():
                    time.sleep(delay)
                    continue
                raise
        raise last_err or RuntimeError('Could not connect after retries')

    def apply_access_state(self, members: List[Dict]) -> Tuple[int, int]:
        """
        members: list of {'emp_id': str, 'end_date': 'YYYY-MM-DD' | None, ...}

        Updates Employee.end_date for each. Returns (updated_count, errors).
        Skips members with no emp_id or no end_date.
        """
        if not members:
            return 0, 0

        conn = self._connect()
        updated = 0
        errors = 0
        try:
            cur = conn.cursor()
            for m in members:
                emp_id = (m.get('emp_id') or '').strip()
                end_date_str = m.get('end_date')
                if not emp_id or not end_date_str:
                    continue
                try:
                    end_date = date.fromisoformat(end_date_str)
                    cur.execute(
                        "UPDATE Employee SET end_date = ? WHERE emp_id = ?",
                        end_date, emp_id
                    )
                    updated += 1
                except Exception:
                    errors += 1
                    continue

            conn.commit()
            return updated, errors
        finally:
            conn.close()

    def set_end_date(self, emp_id: str, end_date: date) -> bool:
        """Update single member's end_date."""
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("UPDATE Employee SET end_date = ? WHERE emp_id = ?",
                        end_date, emp_id)
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False
