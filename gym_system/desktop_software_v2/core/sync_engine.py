"""
Sync Engine — orchestrates first sync and incremental sync loops.
"""
import socket
import platform
import threading
from datetime import datetime
from typing import Callable, Optional

from .api import APIv2, APIError
from .db_reader import DBReader
from .db_writer import DBWriter


class SyncEngine:
    """
    State machine:
      1. Heartbeat every cycle
      2. If first_sync_done=False → run full sync
      3. Otherwise → incremental sync + apply access state

    Callbacks:
      on_status(text, level)   level in {'info','success','warning','error'}
      on_stats(stats_dict)     called with dict of counts
    """

    def __init__(self, config: dict,
                 on_status: Callable = None,
                 on_stats: Callable = None,
                 on_config_save: Callable = None):
        self.config = config
        self.on_status = on_status or (lambda *a, **k: None)
        self.on_stats = on_stats or (lambda *a, **k: None)
        self.on_config_save = on_config_save or (lambda c: None)

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.api = APIv2(
            base_url=config.get('api_url', ''),
            branch_code=config.get('branch_code', ''),
        )

        self.reader = DBReader(
            members_path=config.get('db_path_members', ''),
            attendance_path=config.get('db_path_attendance', ''),
            password=config.get('db_password') or None,
        )

        self.writer = DBWriter(
            members_path=config.get('db_path_members', ''),
            password=config.get('db_password') or None,
        )

        self.last_stats = {
            'last_sync': None,
            'members_total': 0,
            'attendance_today': 0,
            'last_sync_status': 'idle',
        }

    # ── Public API ──
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def sync_once(self) -> dict:
        """Run a single sync cycle (used by manual sync button)."""
        with self._lock:
            return self._run_cycle()

    # ── Loop ──
    def _run_loop(self):
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._run_cycle()
            except Exception as e:
                self.on_status(f'خطأ في المزامنة: {e}', 'error')

            interval = self.config.get('sync_interval_seconds', 60)
            self._stop.wait(timeout=max(10, interval))

    # ── One sync cycle ──
    def _run_cycle(self) -> dict:
        # 1. Heartbeat (always)
        try:
            db_found = bool(self.config.get('db_path_members')) and \
                       bool(self.config.get('db_path_attendance'))
            self.api.heartbeat(
                computer_name=socket.gethostname(),
                ip=_get_local_ip(),
                os_info=f'{platform.system()} {platform.release()}',
                db_path=self.config.get('db_path_members', ''),
                db_found=db_found,
            )
        except APIError as e:
            self.on_status(f'فشل الاتصال: {e}', 'warning')
            return {'success': False, 'error': str(e)}

        # 2. First-time full sync
        if not self.config.get('first_sync_done'):
            return self._first_sync()

        # 3. Incremental sync + access state
        return self._incremental_sync()

    def _first_sync(self) -> dict:
        self.on_status('جاري المزامنة الأولى — قد يستغرق دقائق...', 'info')

        # Read all members + recent attendance
        try:
            members = self.reader.read_all_members()
        except Exception as e:
            self.on_status(f'فشل قراءة قاعدة الأعضاء: {e}', 'error')
            return {'success': False, 'error': str(e)}

        try:
            attendance = self.reader.read_recent_attendance(days=30)
        except Exception:
            attendance = []  # tolerate device DB issues

        if not members:
            self.on_status('لا توجد بيانات أعضاء', 'warning')
            return {'success': False, 'error': 'no members'}

        try:
            result = self.api.full_sync(members, attendance)
        except APIError as e:
            self.on_status(f'فشل الرفع: {e}', 'error')
            return {'success': False, 'error': str(e)}

        # Save id_mapping + flag first sync done
        self.config['id_mapping'] = result.get('id_mapping', {})
        self.config['first_sync_done'] = True
        self.config['last_sync'] = result.get('server_time')
        self.on_config_save(self.config)

        summary = result.get('import_summary', {})
        self.on_status(
            f'تم الرفع — أعضاء: {summary.get("members_created", 0)} جديد، '
            f'{summary.get("members_updated", 0)} محدث، حضور: {summary.get("attendance_imported", 0)}',
            'success'
        )

        # Apply initial access state
        self._apply_access_state()

        return {'success': True, 'first_sync': True, **summary}

    def _incremental_sync(self) -> dict:
        # Read new members (ones not in id_mapping)
        try:
            all_members = self.reader.read_all_members()
        except Exception as e:
            self.on_status(f'فشل قراءة قاعدة الأعضاء: {e}', 'error')
            return {'success': False, 'error': str(e)}

        known_emp_ids = set(self.config.get('id_mapping', {}).keys())
        new_members = [m for m in all_members if m.get('emp_id') and m['emp_id'] not in known_emp_ids]

        # Read new attendance scans since last sync
        try:
            last_sync_ts = self.config.get('last_sync')
            since_dt = None
            if last_sync_ts:
                # Strip tz for comparison with naive .mdb datetime
                ts = last_sync_ts.replace('Z', '').split('+')[0]
                since_dt = datetime.fromisoformat(ts)
            new_attendance = self.reader.read_attendance(since_dt=since_dt)
        except Exception:
            new_attendance = []

        # Push to cloud
        try:
            result = self.api.sync(new_members, new_attendance)
        except APIError as e:
            self.on_status(f'فشل المزامنة: {e}', 'error')
            return {'success': False, 'error': str(e)}

        # Update id_mapping for newly-created members
        # (server doesn't return mapping for sync, only full-sync — server-side
        #  members will get their import_id matched on next full read)

        self.config['last_sync'] = result.get('server_time')
        self.on_config_save(self.config)

        # Update stats
        self.last_stats['last_sync'] = result.get('server_time')
        self.last_stats['members_total'] = len(all_members)
        self.last_stats['last_sync_status'] = 'success'
        self.on_stats(self.last_stats)

        sync_text = f'مزامنة — أعضاء جدد: {result.get("members_synced", 0)}، حضور: {result.get("attendance_synced", 0)}'
        self.on_status(sync_text, 'success')

        # Apply access state
        self._apply_access_state()

        return {'success': True, **result}

    def _apply_access_state(self):
        """Pull access state and write end_date updates to backup.mdb."""
        try:
            state = self.api.access_state()
        except APIError as e:
            self.on_status(f'فشل جلب حالة الوصول: {e}', 'warning')
            return

        members = state.get('members', [])
        if not members:
            return

        try:
            updated, errors = self.writer.apply_access_state(members)
            if errors > 0:
                self.on_status(f'تم تطبيق صلاحيات الوصول — {updated} ✓ {errors} ✗', 'warning')
            else:
                self.on_status(f'تم تطبيق صلاحيات الوصول لـ {updated} عضو', 'info')
        except Exception as e:
            self.on_status(f'فشل تطبيق الصلاحيات على قاعدة البيانات: {e}', 'error')


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ''
