"""
DB Reader — read members and attendance from .mdb file(s).

Supports TWO schemas:

  Schema A (newer, single file — most common today, "tmkq.mdb"):
    Employee     — same as schema B
    tmpTRecords  — has columns: clock_id, card_id, emp_id, KqDate, KqTime,
                                mark, flag, sign_cause, ID (auto-inc)

  Schema B (older, two files):
    Employee in backup.mdb / tmkq.mdb
    CHECKINOUT in att2000.mdb — columns: USERID, CHECKTIME, CHECKTYPE

The reader auto-detects which schema is present.
"""
import os
import time
from datetime import datetime, timedelta, time as _time
from typing import List, Dict, Optional

try:
    import pyodbc
except ImportError:
    pyodbc = None


SCHEMA_NEW = 'new'   # tmpTRecords (single-file or dual)
SCHEMA_OLD = 'old'   # CHECKINOUT (legacy ZKTeco att2000.mdb)


def _conn_str(path: str, password: str = None) -> str:
    driver = 'Microsoft Access Driver (*.mdb, *.accdb)'
    base = f'DRIVER={{{driver}}};DBQ={path};'
    if password:
        base += f'PWD={password};'
    return base


class DBReader:
    """
    Initialize with either:
      DBReader(members_path='path/to/tmkq.mdb')  — single file (auto-detects attendance table)
      DBReader(members_path='backup.mdb', attendance_path='att2000.mdb')  — dual file
    """

    def __init__(self, members_path: str, attendance_path: str = None,
                 password: str = None):
        self.members_path = members_path
        # If no separate attendance file, attendance lives in members file
        self.attendance_path = attendance_path or members_path
        self.password = password
        self._att_schema = None  # cached after detection

    # ──────────────────────────────────────────────────────────────────────
    # Connection
    # ──────────────────────────────────────────────────────────────────────

    def _connect(self, path: str, attempts: int = 3, delay: float = 2.0):
        if pyodbc is None:
            raise RuntimeError('pyodbc not installed')
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f'Database not found: {path}')

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

    # ──────────────────────────────────────────────────────────────────────
    # Schema detection
    # ──────────────────────────────────────────────────────────────────────

    def _detect_attendance_schema(self, conn) -> str:
        """Return 'new' if tmpTRecords exists, 'old' if CHECKINOUT, else raise."""
        if self._att_schema:
            return self._att_schema

        cur = conn.cursor()
        tables = {row.table_name.lower() for row in cur.tables(tableType='TABLE')}

        if 'tmptrecords' in tables:
            self._att_schema = SCHEMA_NEW
        elif 'checkinout' in tables:
            self._att_schema = SCHEMA_OLD
        else:
            # Fallback — try TimeRecords if it has data
            try:
                cur.execute("SELECT COUNT(*) FROM TimeRecords")
                count = cur.fetchone()[0]
                if count > 0:
                    self._att_schema = 'timerecords'
                    return self._att_schema
            except Exception:
                pass
            raise RuntimeError('No attendance table found (looked for tmpTRecords, CHECKINOUT, TimeRecords)')

        return self._att_schema

    # ──────────────────────────────────────────────────────────────────────
    # Members
    # ──────────────────────────────────────────────────────────────────────

    def read_all_members(self) -> List[Dict]:
        """Return all rows from Employee table."""
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
                    'birth_date': row[5].isoformat() if hasattr(row[5], 'isoformat') else None,
                    'hire_date': row[6].isoformat() if hasattr(row[6], 'isoformat') else None,
                    'end_date': row[7].isoformat() if hasattr(row[7], 'isoformat') else None,
                    'email': ((row[8] or '').strip() or None),
                    'address': ((row[9] or '').strip() or None),
                    'depart_id': str(row[10]).strip() if row[10] is not None else '',
                    'memo': ((row[11] or '').strip() or None),
                })
            return rows
        finally:
            conn.close()

    def members_changed_since(self, last_check: datetime) -> List[Dict]:
        """Employee table has no created_at; caller diffs against id_mapping."""
        return self.read_all_members()

    # ──────────────────────────────────────────────────────────────────────
    # Attendance — schema-aware
    # ──────────────────────────────────────────────────────────────────────

    def read_attendance(self, since_id: int = 0, since_dt: datetime = None,
                        limit: int = None) -> List[Dict]:
        """
        Return list of {'userid', 'checktime', 'checktype', 'device_log_id', 'card_id', 'emp_id'}.

        Incremental keys:
          - new schema (tmpTRecords): use since_id (the auto-inc ID column)
          - old schema (CHECKINOUT):  use since_dt (CHECKTIME comparison)
        """
        conn = self._connect(self.attendance_path)
        try:
            schema = self._detect_attendance_schema(conn)
            cur = conn.cursor()

            if schema == SCHEMA_NEW:
                return self._read_new_schema(cur, since_id, limit)
            elif schema == SCHEMA_OLD:
                return self._read_old_schema(cur, since_dt, limit)
            elif schema == 'timerecords':
                return self._read_timerecords(cur, since_dt, limit)
            else:
                return []
        finally:
            conn.close()

    def _read_new_schema(self, cur, since_id: int, limit: Optional[int]) -> List[Dict]:
        """tmpTRecords: ID auto-inc, KqDate (date), KqTime (time-of-day)."""
        sql = """
            SELECT ID, clock_id, card_id, emp_id, KqDate, KqTime, mark, flag
            FROM tmpTRecords
            WHERE ID > ?
            ORDER BY ID ASC
        """
        params = [int(since_id or 0)]
        if limit:
            sql = sql.replace('SELECT', f'SELECT TOP {int(limit)}', 1)

        cur.execute(sql, params)
        rows = []
        for r in cur.fetchall():
            row_id = int(r[0])
            clock_id = int(r[1]) if r[1] is not None else 0
            card_id_str = (str(r[2]) if r[2] is not None else '').strip()
            emp_id_str = (str(r[3]) if r[3] is not None else '').strip()
            kq_date = r[4]    # datetime, only date portion meaningful
            kq_time = r[5]    # datetime, only time portion meaningful
            mark = int(r[6]) if r[6] is not None else 0

            # Combine date + time
            checktime = self._combine_date_time(kq_date, kq_time)
            if not checktime:
                continue

            # Convert card_id (zero-padded string) → int for the server
            try:
                userid = int(card_id_str.lstrip('0') or '0')
            except ValueError:
                userid = 0

            rows.append({
                'userid': userid,
                'card_id': card_id_str,
                'emp_id': emp_id_str,
                'checktime': checktime.isoformat(),
                'checktype': mark,
                'device_log_id': row_id,  # use ID — guaranteed unique
                'clock_id': clock_id,
            })
        return rows

    def _read_old_schema(self, cur, since_dt: Optional[datetime],
                         limit: Optional[int]) -> List[Dict]:
        """CHECKINOUT (legacy ZKTeco)."""
        sql = "SELECT USERID, CHECKTIME, CHECKTYPE FROM CHECKINOUT"
        params = []
        if since_dt:
            sql += " WHERE CHECKTIME > ?"
            params.append(since_dt)
        sql += " ORDER BY CHECKTIME ASC"
        if limit:
            sql = sql.replace('SELECT', f'SELECT TOP {int(limit)}', 1)

        cur.execute(sql, params)
        rows = []
        for r in cur.fetchall():
            userid = r[0]
            checktime = r[1]
            checktype = r[2] if r[2] is not None else 0
            if userid is None or checktime is None:
                continue
            rows.append({
                'userid': int(userid),
                'card_id': str(userid),
                'emp_id': '',
                'checktime': checktime.isoformat() if hasattr(checktime, 'isoformat') else str(checktime),
                'checktype': int(checktype),
                'device_log_id': int(checktime.timestamp()) if hasattr(checktime, 'timestamp') else 0,
                'clock_id': 0,
            })
        return rows

    def _read_timerecords(self, cur, since_dt: Optional[datetime],
                          limit: Optional[int]) -> List[Dict]:
        """TimeRecords table — has sign_time as a single datetime."""
        sql = "SELECT clock_id, card_id, emp_id, sign_time, mark, flag FROM TimeRecords"
        params = []
        if since_dt:
            sql += " WHERE sign_time > ?"
            params.append(since_dt)
        sql += " ORDER BY sign_time ASC"
        if limit:
            sql = sql.replace('SELECT', f'SELECT TOP {int(limit)}', 1)

        cur.execute(sql, params)
        rows = []
        for r in cur.fetchall():
            card_id_str = (str(r[1]) if r[1] is not None else '').strip()
            emp_id_str = (str(r[2]) if r[2] is not None else '').strip()
            sign_time = r[3]
            mark = int(r[4]) if r[4] is not None else 0

            if not sign_time:
                continue
            try:
                userid = int(card_id_str.lstrip('0') or '0')
            except ValueError:
                userid = 0

            rows.append({
                'userid': userid,
                'card_id': card_id_str,
                'emp_id': emp_id_str,
                'checktime': sign_time.isoformat() if hasattr(sign_time, 'isoformat') else str(sign_time),
                'checktype': mark,
                'device_log_id': int(sign_time.timestamp()) if hasattr(sign_time, 'timestamp') else 0,
                'clock_id': int(r[0]) if r[0] is not None else 0,
            })
        return rows

    @staticmethod
    def _combine_date_time(date_dt, time_dt) -> Optional[datetime]:
        """Combine separate date and time-of-day datetimes into one."""
        if not date_dt:
            return None
        # Default time = midnight if missing
        t = time_dt.time() if hasattr(time_dt, 'time') else _time(0, 0)
        return datetime(date_dt.year, date_dt.month, date_dt.day,
                        t.hour, t.minute, t.second)

    # ──────────────────────────────────────────────────────────────────────
    # Convenience
    # ──────────────────────────────────────────────────────────────────────

    def read_recent_attendance(self, days: int = 30) -> List[Dict]:
        """For first-sync: last N days of scans. Uses ID-based limit if new schema."""
        # Try new schema first — read all and filter by date
        conn = self._connect(self.attendance_path)
        try:
            schema = self._detect_attendance_schema(conn)
        finally:
            conn.close()

        cutoff = datetime.now() - timedelta(days=days)
        if schema == SCHEMA_NEW:
            # Read all, filter by date in Python (cheaper than complex SQL on date+time split)
            all_rows = self.read_attendance(since_id=0)
            return [r for r in all_rows if r.get('checktime')
                    and self._parse_iso(r['checktime']) >= cutoff]
        else:
            return self.read_attendance(since_dt=cutoff)

    @staticmethod
    def _parse_iso(s):
        try:
            return datetime.fromisoformat(s.replace('Z', '').split('+')[0])
        except Exception:
            return datetime.min

    def get_max_attendance_id(self) -> int:
        """Return the highest ID in tmpTRecords (for new schema). 0 for old schema."""
        conn = self._connect(self.attendance_path)
        try:
            schema = self._detect_attendance_schema(conn)
            if schema != SCHEMA_NEW:
                return 0
            cur = conn.cursor()
            cur.execute("SELECT MAX(ID) FROM tmpTRecords")
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────────────────────
    # Diagnostics
    # ──────────────────────────────────────────────────────────────────────

    def test_members_db(self) -> tuple:
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
            schema = self._detect_attendance_schema(conn)
            cur = conn.cursor()
            if schema == SCHEMA_NEW:
                cur.execute("SELECT COUNT(*) FROM tmpTRecords")
                count = cur.fetchone()[0]
                conn.close()
                return True, f'تم الاتصال (tmpTRecords) — {count} سجل'
            elif schema == SCHEMA_OLD:
                cur.execute("SELECT COUNT(*) FROM CHECKINOUT")
                count = cur.fetchone()[0]
                conn.close()
                return True, f'تم الاتصال (CHECKINOUT) — {count} سجل'
            elif schema == 'timerecords':
                cur.execute("SELECT COUNT(*) FROM TimeRecords")
                count = cur.fetchone()[0]
                conn.close()
                return True, f'تم الاتصال (TimeRecords) — {count} سجل'
            conn.close()
            return False, 'لم يتم العثور على جدول البصمة'
        except Exception as e:
            return False, str(e)
