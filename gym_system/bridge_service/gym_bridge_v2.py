#!/usr/bin/env python3
"""
Gym Fingerprint Bridge Service v2
Connects ZKTeco fingerprint devices to the cloud gym management system.

Features:
- Reads CHECKINOUT from att2000.mdb (attendance logs)
- Writes end_date in backup.mdb (access control)
- Class-based time-window access control
- Employee shift-aware lateness detection
- Device command execution (block/unblock members)
- Auto-detects correct .mdb files by schema validation
- Multi-brand support (one bridge per gym)

Requirements: pyodbc, requests
Run: python gym_bridge_v2.py
"""

import os
import sys
import json
import time
import socket
import platform
import logging
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path
from threading import Thread, Lock

try:
    import pyodbc
except ImportError:
    print("ERROR: pyodbc is required. Install with: pip install pyodbc")
    print("Also ensure Microsoft Access ODBC driver is installed.")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: pip install requests")
    sys.exit(1)

# ─── Configuration ───────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
LAST_SYNC_FILE = SCRIPT_DIR / "last_sync.txt"
CACHE_FILE = SCRIPT_DIR / "schedule_cache.json"
LOG_FILE = SCRIPT_DIR / "bridge_v2.log"
QUEUE_FILE = SCRIPT_DIR / "offline_queue.json"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ODBC connection string template
MDB_CONN_STR = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;"


# ─── MDB Manager ────────────────────────────────────────────────────────────

class MDBManager:
    """Manages pyodbc connections to .mdb files with auto-detection and retry."""

    def __init__(self):
        self.att2000_path = None  # ZKTeco device DB (CHECKINOUT)
        self.backup_path = None   # Attendancear DB (Employee)
        self._lock = Lock()

    def connect(self, mdb_path):
        """Open a short-lived connection to an .mdb file."""
        conn_str = MDB_CONN_STR % mdb_path
        return pyodbc.connect(conn_str)

    def execute_with_retry(self, mdb_path, sql, params=None, fetch=True, max_retries=3):
        """Execute SQL with retry on lock errors."""
        for attempt in range(max_retries):
            try:
                with self._lock:
                    conn = self.connect(mdb_path)
                    try:
                        cursor = conn.cursor()
                        if params:
                            cursor.execute(sql, params)
                        else:
                            cursor.execute(sql)

                        if fetch:
                            columns = [desc[0] for desc in cursor.description] if cursor.description else []
                            rows = cursor.fetchall()
                            return [dict(zip(columns, row)) for row in rows]
                        else:
                            conn.commit()
                            return cursor.rowcount
                    finally:
                        conn.close()
            except pyodbc.Error as e:
                error_msg = str(e)
                if 'locked' in error_msg.lower() or 'in use' in error_msg.lower():
                    logger.warning(f"Database locked (attempt {attempt + 1}/{max_retries}): {mdb_path}")
                    time.sleep(2)
                else:
                    raise
        raise Exception(f"Database locked after {max_retries} retries: {mdb_path}")

    def detect_databases(self, search_paths=None):
        """
        Auto-detect att2000.mdb and backup.mdb by checking table schemas.
        - att2000.mdb: has CHECKINOUT table with USERID, CHECKTIME
        - backup.mdb: has Employee table with emp_id, end_date
        """
        if search_paths is None:
            search_paths = self._get_default_search_paths()

        found_mdb_files = []
        logger.info("Searching for .mdb database files...")

        for base_path in search_paths:
            if not os.path.exists(base_path):
                continue
            try:
                for root, dirs, files in os.walk(base_path):
                    # Skip system/hidden/backup folders
                    dirs[:] = [d for d in dirs if not d.startswith('.')
                               and d not in ['Windows', 'System32', '$Recycle.Bin',
                                             'node_modules', 'BackUpData']]
                    for f in files:
                        if f.lower().endswith('.mdb'):
                            found_mdb_files.append(os.path.join(root, f))
                    # Limit depth
                    if root.count(os.sep) > 6:
                        dirs.clear()
            except PermissionError:
                continue

        logger.info(f"Found {len(found_mdb_files)} .mdb files")

        # Validate each file's schema
        for mdb_path in found_mdb_files:
            try:
                conn = self.connect(mdb_path)
                try:
                    cursor = conn.cursor()
                    tables = [row.table_name for row in cursor.tables(tableType='TABLE')]

                    # Check for ZKTeco device DB
                    if 'CHECKINOUT' in tables and not self.att2000_path:
                        columns = [row.column_name for row in cursor.columns(table='CHECKINOUT')]
                        if 'USERID' in columns and 'CHECKTIME' in columns:
                            self.att2000_path = mdb_path
                            logger.info(f"  ZKTeco DB (att2000): {mdb_path}")

                    # Check for Attendancear DB
                    if 'Employee' in tables and not self.backup_path:
                        columns = [row.column_name for row in cursor.columns(table='Employee')]
                        if 'emp_id' in columns and 'end_date' in columns:
                            self.backup_path = mdb_path
                            logger.info(f"  Attendancear DB (backup): {mdb_path}")
                finally:
                    conn.close()
            except Exception as e:
                logger.debug(f"  Cannot read {mdb_path}: {e}")

        if not self.att2000_path:
            logger.warning("ZKTeco database (att2000.mdb) NOT found")
        if not self.backup_path:
            logger.warning("Attendancear database (backup.mdb) NOT found")

        return bool(self.att2000_path), bool(self.backup_path)

    def _get_default_search_paths(self):
        """Common paths where gym software stores .mdb files."""
        paths = [
            r"C:\AAS",
            r"C:\Program Files\AAS",
            r"C:\Program Files (x86)\AAS",
            r"D:\AAS",
            r"C:\Attendance",
            r"D:\Attendance",
            r"C:\ZKTeco",
            r"D:\ZKTeco",
        ]
        # Add user directories
        home = os.path.expanduser("~")
        paths.extend([
            os.path.join(home, "Documents"),
            os.path.join(home, "Desktop"),
        ])
        return paths

    def read_checkinout(self, since_time=None):
        """Read CHECKINOUT records from att2000.mdb since a given time."""
        if not self.att2000_path:
            return []

        if since_time:
            sql = "SELECT USERID, CHECKTIME, CHECKTYPE, sn FROM CHECKINOUT WHERE CHECKTIME > ? ORDER BY CHECKTIME"
            return self.execute_with_retry(self.att2000_path, sql, (since_time,))
        else:
            sql = "SELECT USERID, CHECKTIME, CHECKTYPE, sn FROM CHECKINOUT ORDER BY CHECKTIME"
            return self.execute_with_retry(self.att2000_path, sql)

    def update_employee_end_date(self, emp_id, end_date_value):
        """Update end_date for a member in backup.mdb Employee table."""
        if not self.backup_path:
            return 0

        sql = "UPDATE Employee SET end_date = ? WHERE emp_id = ?"
        return self.execute_with_retry(self.backup_path, sql, (end_date_value, emp_id), fetch=False)

    def read_employees(self):
        """Read all Employee records from backup.mdb."""
        if not self.backup_path:
            return []

        sql = "SELECT emp_id, emp_name, phone_code, end_date, memo, f_name, card_id FROM Employee ORDER BY emp_id"
        return self.execute_with_retry(self.backup_path, sql)


# ─── Cloud API Client ────────────────────────────────────────────────────────

class CloudAPIClient:
    """REST client for the cloud gym management API."""

    def __init__(self, base_url, api_key, brand_id):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.brand_id = brand_id
        self.session = requests.Session()
        self.session.headers.update({
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        })
        self.timeout = 30

    def health_check(self):
        """Check if the cloud API is reachable."""
        try:
            r = self.session.get(f"{self.base_url}/api/fingerprint/health", timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def send_attendance(self, records):
        """Send attendance records to the cloud."""
        try:
            r = self.session.post(
                f"{self.base_url}/api/fingerprint/attendance",
                json={'brand_id': self.brand_id, 'records': records},
                timeout=self.timeout
            )
            if r.status_code == 200:
                return r.json()
            logger.error(f"Attendance sync failed ({r.status_code}): {r.text[:200]}")
        except requests.ConnectionError:
            logger.error("Cannot connect to cloud API")
        except Exception as e:
            logger.error(f"Attendance sync error: {e}")
        return None

    def get_class_schedule(self, schedule_date=None):
        """Get today's class schedule for access control."""
        params = {'brand_id': self.brand_id}
        if schedule_date:
            params['date'] = schedule_date.isoformat()
        try:
            r = self.session.get(
                f"{self.base_url}/api/bridge/class-schedule",
                params=params, timeout=self.timeout
            )
            if r.status_code == 200:
                return r.json()
            logger.error(f"Class schedule fetch failed ({r.status_code})")
        except Exception as e:
            logger.error(f"Class schedule error: {e}")
        return None

    def get_bridge_settings(self):
        """Get bridge settings from cloud."""
        try:
            r = self.session.get(
                f"{self.base_url}/api/bridge/settings",
                params={'brand_id': self.brand_id}, timeout=self.timeout
            )
            if r.status_code == 200:
                return r.json().get('settings', {})
        except Exception as e:
            logger.error(f"Bridge settings error: {e}")
        return None

    def get_pending_commands(self):
        """Get pending device commands."""
        try:
            r = self.session.get(
                f"{self.base_url}/api/device/commands",
                params={'brand_id': self.brand_id}, timeout=self.timeout
            )
            if r.status_code == 200:
                return r.json().get('commands', [])
        except Exception as e:
            logger.error(f"Commands fetch error: {e}")
        return []

    def complete_command(self, command_id, success=True, error_message=None):
        """Mark a command as completed or failed."""
        try:
            self.session.post(
                f"{self.base_url}/api/device/commands/{command_id}/complete",
                json={'success': success, 'error_message': error_message},
                timeout=self.timeout
            )
        except Exception as e:
            logger.error(f"Command complete error: {e}")

    def send_heartbeat(self, **kwargs):
        """Send heartbeat to cloud."""
        try:
            payload = {
                'brand_id': self.brand_id,
                'computer_name': platform.node() or socket.gethostname(),
                'ip_address': self._get_local_ip(),
                'os_info': f"{platform.system()} {platform.release()}",
                **kwargs
            }
            self.session.post(
                f"{self.base_url}/api/fingerprint/bridge/heartbeat",
                json=payload, timeout=15
            )
        except Exception as e:
            logger.debug(f"Heartbeat error: {e}")

    def update_bridge_paths(self, att2000_path, backup_path):
        """Report detected database paths to cloud."""
        try:
            self.session.post(
                f"{self.base_url}/api/bridge/settings",
                json={
                    'brand_id': self.brand_id,
                    'att2000_mdb_path': att2000_path,
                    'backup_mdb_path': backup_path
                },
                timeout=15
            )
        except Exception:
            pass

    @staticmethod
    def _get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


# ─── Attendance Syncer ───────────────────────────────────────────────────────

class AttendanceSyncer:
    """Reads CHECKINOUT from att2000.mdb and sends to cloud."""

    def __init__(self, mdb_manager, api_client):
        self.mdb = mdb_manager
        self.api = api_client
        self.last_sync_time = self._load_last_sync_time()
        self._offline_queue = self._load_offline_queue()

    def sync(self):
        """Main sync: read new records, send to cloud."""
        if not self.mdb.att2000_path:
            return 0

        try:
            records = self.mdb.read_checkinout(since_time=self.last_sync_time)
        except Exception as e:
            logger.error(f"Error reading CHECKINOUT: {e}")
            return 0

        if not records:
            # Try sending queued records
            self._flush_offline_queue()
            return 0

        logger.info(f"Found {len(records)} new attendance records")

        # Convert to API format
        api_records = []
        latest_time = self.last_sync_time
        for rec in records:
            check_time = rec.get('CHECKTIME')
            if not check_time:
                continue

            if isinstance(check_time, str):
                try:
                    check_time = datetime.strptime(check_time, '%m/%d/%y %H:%M:%S')
                except ValueError:
                    try:
                        check_time = datetime.fromisoformat(check_time)
                    except ValueError:
                        continue

            api_records.append({
                'fingerprint_id': rec['USERID'],
                'timestamp': check_time.isoformat(),
                'log_id': hash(f"{rec['USERID']}-{check_time.isoformat()}")
            })

            if latest_time is None or check_time > latest_time:
                latest_time = check_time

        if not api_records:
            return 0

        # Send to cloud
        result = self.api.send_attendance(api_records)
        if result:
            synced = result.get('synced', 0)
            logger.info(f"Synced {synced} records (staff: {result.get('staff_synced', 0)}, members: {result.get('member_synced', 0)})")

            # Log blocked entries
            for blocked in result.get('blocked_entries', []):
                logger.warning(f"  BLOCKED: {blocked.get('member_name')} - {blocked.get('reason')}")

            self.last_sync_time = latest_time
            self._save_last_sync_time(latest_time)
            return synced
        else:
            # Cloud unreachable - queue records
            self._offline_queue.extend(api_records)
            self._save_offline_queue()
            logger.warning(f"Queued {len(api_records)} records for later (total queue: {len(self._offline_queue)})")
            return 0

    def _flush_offline_queue(self):
        """Send queued records when cloud is available."""
        if not self._offline_queue:
            return

        result = self.api.send_attendance(self._offline_queue)
        if result:
            synced = result.get('synced', 0)
            logger.info(f"Flushed {synced} queued records")
            self._offline_queue.clear()
            self._save_offline_queue()

    def _load_last_sync_time(self):
        try:
            with open(LAST_SYNC_FILE, 'r') as f:
                return datetime.fromisoformat(f.read().strip())
        except Exception:
            return None

    def _save_last_sync_time(self, dt):
        try:
            with open(LAST_SYNC_FILE, 'w') as f:
                f.write(dt.isoformat())
        except Exception as e:
            logger.error(f"Cannot save last sync time: {e}")

    def _load_offline_queue(self):
        try:
            with open(QUEUE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_offline_queue(self):
        try:
            with open(QUEUE_FILE, 'w') as f:
                json.dump(self._offline_queue, f)
        except Exception:
            pass


# ─── Access Controller ───────────────────────────────────────────────────────

class AccessController:
    """Controls member access by writing end_date in backup.mdb based on class schedule."""

    def __init__(self, mdb_manager, api_client):
        self.mdb = mdb_manager
        self.api = api_client
        self._cached_schedule = None
        self._cache_time = None

    def update_access(self):
        """Get class schedule from cloud and update end_date in backup.mdb."""
        if not self.mdb.backup_path:
            return

        # Get schedule (with cache fallback)
        schedule = self.api.get_class_schedule()
        if schedule:
            self._cached_schedule = schedule
            self._cache_time = datetime.now()
            self._save_cache(schedule)
        else:
            # Use cache if cloud is unreachable
            schedule = self._cached_schedule or self._load_cache()
            if not schedule:
                logger.warning("No schedule available (cloud unreachable, no cache)")
                return

        access_window = schedule.get('access_window_minutes', 15)
        now = datetime.now()
        today = date.today()
        yesterday = today - timedelta(days=1)
        updated = 0

        # --- 1. Process class-booked members ---
        for cls in schedule.get('classes', []):
            start_str = cls.get('start_time')
            end_str = cls.get('end_time')
            if not start_str or not end_str:
                continue

            class_start = datetime.strptime(start_str, '%H:%M').replace(
                year=today.year, month=today.month, day=today.day)
            class_end = datetime.strptime(end_str, '%H:%M').replace(
                year=today.year, month=today.month, day=today.day)
            window_start = class_start - timedelta(minutes=access_window)

            for member in cls.get('booked_members', []):
                emp_id = member.get('emp_id')
                if not emp_id:
                    continue

                if window_start <= now <= class_end:
                    # Within access window - ALLOW
                    try:
                        self.mdb.update_employee_end_date(emp_id, today)
                        updated += 1
                    except Exception as e:
                        logger.error(f"Failed to allow {emp_id}: {e}")
                else:
                    # Outside window - BLOCK
                    try:
                        self.mdb.update_employee_end_date(emp_id, yesterday)
                        updated += 1
                    except Exception as e:
                        logger.error(f"Failed to block {emp_id}: {e}")

        # --- 2. Process gym members (no class requirement) ---
        for member in schedule.get('gym_members', []):
            emp_id = member.get('emp_id')
            end_date_str = member.get('subscription_end_date')
            if not emp_id or not end_date_str:
                continue
            try:
                end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                self.mdb.update_employee_end_date(emp_id, end_dt)
                updated += 1
            except Exception as e:
                logger.error(f"Failed to update gym member {emp_id}: {e}")

        # --- 3. Process blocked members ---
        block_date = date(2020, 1, 1)
        for member in schedule.get('blocked_members', []):
            emp_id = member.get('emp_id')
            if not emp_id:
                continue
            try:
                self.mdb.update_employee_end_date(emp_id, block_date)
                updated += 1
            except Exception as e:
                logger.error(f"Failed to block {emp_id}: {e}")

        if updated > 0:
            logger.info(f"Access control: updated {updated} members")

    def _save_cache(self, schedule):
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(schedule, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_cache(self):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None


# ─── Command Executor ────────────────────────────────────────────────────────

class CommandExecutor:
    """Polls and executes device commands from the cloud (block/unblock/update members)."""

    def __init__(self, mdb_manager, api_client):
        self.mdb = mdb_manager
        self.api = api_client

    def execute_pending(self):
        """Fetch and execute all pending commands."""
        if not self.mdb.backup_path:
            return

        commands = self.api.get_pending_commands()
        if not commands:
            return

        logger.info(f"Executing {len(commands)} pending commands")

        for cmd in commands:
            cmd_id = cmd.get('id')
            cmd_type = cmd.get('command_type')
            emp_id = cmd.get('target_emp_id')
            cmd_data = cmd.get('command_data', {})

            try:
                if cmd_type == 'block_member':
                    self.mdb.update_employee_end_date(emp_id, date(2020, 1, 1))
                    logger.info(f"  Blocked member emp_id={emp_id}")

                elif cmd_type == 'unblock_member':
                    end_date_str = cmd_data.get('end_date')
                    if end_date_str:
                        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                        self.mdb.update_employee_end_date(emp_id, end_dt)
                    logger.info(f"  Unblocked member emp_id={emp_id}")

                elif cmd_type == 'update_end_date':
                    end_date_str = cmd_data.get('end_date')
                    if end_date_str:
                        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                        self.mdb.update_employee_end_date(emp_id, end_dt)
                    logger.info(f"  Updated end_date for emp_id={emp_id}")

                elif cmd_type == 'update_member':
                    # Generic field update
                    if cmd_data and emp_id:
                        for field, value in cmd_data.items():
                            sql = f"UPDATE Employee SET [{field}] = ? WHERE emp_id = ?"
                            self.mdb.execute_with_retry(
                                self.mdb.backup_path, sql, (value, emp_id), fetch=False)
                    logger.info(f"  Updated member data emp_id={emp_id}")

                elif cmd_type == 'add_member':
                    if cmd_data:
                        fields = ', '.join(f'[{k}]' for k in cmd_data.keys())
                        placeholders = ', '.join('?' for _ in cmd_data)
                        sql = f"INSERT INTO Employee ({fields}) VALUES ({placeholders})"
                        self.mdb.execute_with_retry(
                            self.mdb.backup_path, sql, tuple(cmd_data.values()), fetch=False)
                    logger.info(f"  Added member emp_id={emp_id}")

                self.api.complete_command(cmd_id, success=True)

            except Exception as e:
                logger.error(f"  Command {cmd_id} ({cmd_type}) failed: {e}")
                self.api.complete_command(cmd_id, success=False, error_message=str(e))


# ─── Main Bridge Service ────────────────────────────────────────────────────

class BridgeService:
    """Main bridge orchestrator."""

    def __init__(self):
        self.config = self._load_config()
        cloud = self.config['cloud_api']
        sync_cfg = self.config.get('sync', {})

        self.api = CloudAPIClient(cloud['url'], cloud['api_key'], cloud['brand_id'])
        self.mdb = MDBManager()

        self.attendance_syncer = AttendanceSyncer(self.mdb, self.api)
        self.access_controller = AccessController(self.mdb, self.api)
        self.command_executor = CommandExecutor(self.mdb, self.api)

        # Intervals
        self.attendance_interval = sync_cfg.get('attendance_interval', 30)
        self.access_control_interval = sync_cfg.get('access_control_interval', 60)
        self.heartbeat_interval = sync_cfg.get('heartbeat_interval', 150)

    def _load_config(self):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {CONFIG_FILE}")
            logger.error("Create config.json from config_template.json")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid config.json: {e}")
            sys.exit(1)

    def setup(self):
        """Initialize: detect databases, check cloud, send initial heartbeat."""
        self._print_banner()

        # Check cloud connectivity
        logger.info("Checking cloud connection...")
        if self.api.health_check():
            logger.info("  Cloud API: CONNECTED")

            # Get settings from cloud (may override local intervals)
            settings = self.api.get_bridge_settings()
            if settings:
                self.attendance_interval = settings.get('attendance_sync_interval', self.attendance_interval)
                self.access_control_interval = settings.get('access_control_interval', self.access_control_interval)
                logger.info(f"  Intervals: attendance={self.attendance_interval}s, access={self.access_control_interval}s")
        else:
            logger.warning("  Cloud API: UNREACHABLE (will retry)")

        # Detect databases
        db_config = self.config.get('databases', {})
        self.mdb.att2000_path = db_config.get('att2000_path') or None
        self.mdb.backup_path = db_config.get('backup_path') or None

        if db_config.get('auto_detect', True) or not (self.mdb.att2000_path and self.mdb.backup_path):
            logger.info("Auto-detecting databases...")
            # Also search configured paths if provided
            extra_paths = []
            if self.mdb.att2000_path and os.path.dirname(self.mdb.att2000_path):
                extra_paths.append(os.path.dirname(self.mdb.att2000_path))
            if self.mdb.backup_path and os.path.dirname(self.mdb.backup_path):
                extra_paths.append(os.path.dirname(self.mdb.backup_path))
            self.mdb.detect_databases(extra_paths + self.mdb._get_default_search_paths() if extra_paths else None)

        # Report paths to cloud
        self.api.update_bridge_paths(self.mdb.att2000_path, self.mdb.backup_path)

        # Initial heartbeat
        self.api.send_heartbeat(
            database_path=self.mdb.att2000_path,
            database_found=bool(self.mdb.att2000_path and self.mdb.backup_path)
        )

        logger.info("")
        logger.info("=" * 50)
        logger.info("  BRIDGE READY - Press Ctrl+C to stop")
        logger.info("=" * 50)
        logger.info("")

    def run(self):
        """Main loop."""
        self.setup()

        last_attendance = 0
        last_access = 0
        last_heartbeat = 0

        while True:
            try:
                now = time.time()

                # Attendance sync
                if now - last_attendance >= self.attendance_interval:
                    try:
                        self.attendance_syncer.sync()
                    except Exception as e:
                        logger.error(f"Attendance sync error: {e}")
                    last_attendance = now

                # Access control
                if now - last_access >= self.access_control_interval:
                    try:
                        self.access_controller.update_access()
                    except Exception as e:
                        logger.error(f"Access control error: {e}")
                    last_access = now

                # Command execution (on every attendance cycle)
                if now - last_attendance < 1:
                    try:
                        self.command_executor.execute_pending()
                    except Exception as e:
                        logger.error(f"Command execution error: {e}")

                # Heartbeat
                if now - last_heartbeat >= self.heartbeat_interval:
                    self.api.send_heartbeat(
                        database_path=self.mdb.att2000_path,
                        database_found=bool(self.mdb.att2000_path and self.mdb.backup_path)
                    )
                    last_heartbeat = now

                # Sleep minimum interval
                time.sleep(min(self.attendance_interval, self.access_control_interval, 10))

            except KeyboardInterrupt:
                logger.info("Stopping bridge service...")
                self.api.send_heartbeat(
                    database_path=self.mdb.att2000_path,
                    database_found=bool(self.mdb.att2000_path and self.mdb.backup_path),
                    error="Service stopped by user"
                )
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                logger.error(traceback.format_exc())
                time.sleep(10)

    def _print_banner(self):
        print()
        print("=" * 55)
        print("   GYM FINGERPRINT BRIDGE SERVICE v2")
        print("=" * 55)
        print(f"   Computer : {platform.node()}")
        print(f"   OS       : {platform.system()} {platform.release()}")
        print(f"   Brand ID : {self.config['cloud_api']['brand_id']}")
        print(f"   Cloud    : {self.config['cloud_api']['url']}")
        print("=" * 55)
        print()


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main():
    service = BridgeService()
    service.run()


if __name__ == '__main__':
    main()
