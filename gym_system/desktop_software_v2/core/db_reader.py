"""
DB Reader — read members from backup.mdb and attendance from att2000.mdb.

Uses pyodbc + Microsoft Access ODBC driver (Windows x64 only).
"""
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

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


class DBReader:
    """
    Reads from two .mdb files:
      - members_path: backup.mdb (Employee table)
      - attendance_path: att2000.mdb (CHECKINOUT table)
    """

    def __init__(self, members_path: str, attendance_path: str = None,
                 password: str = None):
        self.members_path = members_path
        self.attendance_path = attendance_path
        self.password = password

    # ── Connection helper with retry (handles file locks) ──
    def _connect(self, path: str, attempts: int = 3, delay: float = 2.0):
        if pyodbc is None:
            raise RuntimeError('pyodbc not installed')
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f'Database file not found: {path}')

        last_err = None
        for i in range(attempts):
            try:
                return pyodbc.connect(_conn_str(path, self.password), timeout=10)
            except pyodbc.Error as e:
                last_err = e
                msg = str(e).lower()
                if 'locked' in msg or 'in use' in msg or 'cannot open' in msg:
                    time.sleep(delay)
                    continue
                raise
        raise last_err or RuntimeError('Could not connect after retries')

    # ── Read members from backup.mdb / Employee table ──
    def read_all_members(self) -> List[Dict]:
        """Return ALL members from Employee table as list of dicts."""
        conn = self._connect(self.members_path)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT emp_id, card_id, emp_name, phone_code, sex, birth_date,
                       hire_date, end_date, email, address, depart_id, memo
                FROM Employee
            """)
            rows = []
            for row in cur.fetchall():
                rows.append({
                    'emp_id': str(row[0]).strip() if row[0] is not None else '',
                    'card_id': str(row[1]).strip() if row[1] is not None else '',
                    'emp_name': (row[2] or '').strip(),
                    'phone': (row[3] or '').strip(),
                    'sex': str(row[4]).strip() if row[4] is not None else '',
                    'birth_date': row[5].isoformat() if row[5] else None,
                    'hire_date': row[6].isoformat() if row[6] else None,
                    'end_date': row[7].isoformat() if row[7] else None,
                    'email': (row[8] or '').strip() or None,
                    'address': (row[9] or '').strip() or None,
                    'depart_id': str(row[10]).strip() if row[10] is not None else '',
                    'memo': (row[11] or '').strip() or None,
                })
            return rows
        finally:
            conn.close()

    def members_changed_since(self, last_check: datetime) -> List[Dict]:
        """
        Return members added since last_check. backup.mdb Employee table
        doesn't have a created_at column, so we use a snapshot diff approach
        externally. For now, return all members and let caller diff against id_mapping.
        """
        return self.read_all_members()

    # ── Read attendance from att2000.mdb / CHECKINOUT ──
    def read_attendance(self, since_dt: datetime = None,
                        since_log_id: int = 0,
                        limit: int = None) -> List[Dict]:
        """
        Read CHECKINOUT records. Returns list of {'userid', 'checktime', 'checktype', 'device_log_id'}.

        If since_log_id > 0, only return records with USERID-time-based ID > that.
        ZKTeco CHECKINOUT doesn't have a standard auto-increment ID column on every device,
        so we filter by CHECKTIME > since_dt instead.
        """
        if not self.attendance_path:
            return []

        conn = self._connect(self.attendance_path)
        try:
            cur = conn.cursor()
            # Try to detect if there's an auto-increment column
            sql = "SELECT USERID, CHECKTIME, CHECKTYPE FROM CHECKINOUT"
            params = []
            if since_dt:
                sql += " WHERE CHECKTIME > ?"
                params.append(since_dt)
            sql += " ORDER BY CHECKTIME ASC"
            if limit:
                # MS Access uses TOP N at the start; rewrite:
                top_sql = sql.replace("SELECT", f"SELECT TOP {int(limit)}", 1)
                sql = top_sql

            cur.execute(sql, params)

            rows = []
            for i, row in enumerate(cur.fetchall(), start=1):
                userid = row[0]
                checktime = row[1]
                checktype = row[2] if row[2] is not None else 0

                if userid is None or checktime is None:
                    continue

                # Synthetic device_log_id: epoch seconds (stable enough for dedup)
                device_log_id = int(checktime.timestamp()) if hasattr(checktime, 'timestamp') else 0

                rows.append({
                    'userid': int(userid),
                    'checktime': checktime.isoformat() if hasattr(checktime, 'isoformat') else str(checktime),
                    'checktype': int(checktype),
                    'device_log_id': device_log_id,
                })
            return rows
        finally:
            conn.close()

    def read_recent_attendance(self, days: int = 30) -> List[Dict]:
        """For first-time sync — last N days of attendance."""
        since = datetime.now() - timedelta(days=days)
        return self.read_attendance(since_dt=since)

    # ── Connection test ──
    def test_members_db(self) -> tuple:
        """Returns (success, message)"""
        try:
            conn = self._connect(self.members_path, attempts=1)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM Employee")
            count = cur.fetchone()[0]
            conn.close()
            return True, f'تم الاتصال — {count} عضو'
        except Exception as e:
            return False, str(e)

    def test_attendance_db(self) -> tuple:
        try:
            if not self.attendance_path:
                return False, 'مسار الملف فارغ'
            conn = self._connect(self.attendance_path, attempts=1)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM CHECKINOUT")
            count = cur.fetchone()[0]
            conn.close()
            return True, f'تم الاتصال — {count} سجل بصمة'
        except Exception as e:
            return False, str(e)
