"""
Sync Manager - Handle synchronization between local database and web app
"""

import threading
import time
import json
import os
import hashlib
from typing import Dict, List, Callable, Optional
from datetime import datetime, date, timedelta
import socket
import platform
from pathlib import Path


def _stable_log_id(user_id, check_time: datetime) -> int:
    """Deterministic 32-bit log_id derived from (user_id, check_time).
    Survives process restarts (Python's hash() is randomized per-process)."""
    key = f"{user_id}|{check_time.isoformat()}".encode('utf-8')
    return int.from_bytes(hashlib.md5(key).digest()[:4], 'big')

# Persistence directory
BRIDGE_DIR = Path.home() / '.gym_bridge'


class SyncManager:
    """Manage synchronization between local .mdb and web app"""

    def __init__(self, database_manager, api_client, device_db_manager=None):
        self.db = database_manager
        self.api = api_client
        self.device_db = device_db_manager  # For att2000.mdb (CHECKINOUT)

        # Sync state
        self.is_syncing = False
        self.last_sync_time = None
        self.sync_interval = 30  # seconds

        # Auto sync
        self.auto_sync_enabled = False
        self.sync_thread = None
        self.stop_event = threading.Event()

        # Callbacks
        self.on_sync_start = None
        self.on_sync_progress = None
        self.on_sync_complete = None
        self.on_sync_error = None
        self.on_command_executed = None
        self.on_attendance_event = None   # Called for each fingerprint scan
        self.on_schedule_update = None    # Called when class schedule is fetched

        # Stats
        self.total_synced = 0
        self.pending_commands = 0
        self.last_error = None

        # Local cache
        self.local_members_cache = {}
        self._members_name_cache = {}  # emp_id -> name for live feed

        # Attendance sync state
        self.last_attendance_sync_time = self._load_last_attendance_time()
        self._offline_queue = self._load_offline_queue()

        # Access control state
        self.access_control_enabled = False
        self.class_access_window_minutes = 15
        self._cached_schedule = self._load_schedule_cache()

    def get_computer_info(self) -> Dict:
        """Get computer information"""
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
        except:
            hostname = "Unknown"
            ip = "Unknown"

        return {
            'computer_name': hostname,
            'ip_address': ip,
            'os_info': f"{platform.system()} {platform.release()}"
        }

    def start_auto_sync(self, interval: int = 30):
        """Start automatic synchronization"""
        self.sync_interval = interval
        self.auto_sync_enabled = True
        self.stop_event.clear()

        self.sync_thread = threading.Thread(target=self._auto_sync_loop, daemon=True)
        self.sync_thread.start()

    def stop_auto_sync(self):
        """Stop automatic synchronization"""
        self.auto_sync_enabled = False
        self.stop_event.set()
        if self.sync_thread:
            self.sync_thread.join(timeout=5)

    def _auto_sync_loop(self):
        """Background sync loop"""
        while not self.stop_event.is_set():
            try:
                self.sync()
            except Exception as e:
                self.last_error = str(e)
                if self.on_sync_error:
                    self.on_sync_error(str(e))

            # Wait for interval or stop event
            self.stop_event.wait(self.sync_interval)

    def sync(self) -> Dict:
        """Perform full synchronization"""
        if self.is_syncing:
            return {'success': False, 'message': 'المزامنة جارية بالفعل'}

        self.is_syncing = True
        result = {
            'success': True,
            'synced_members': 0,
            'commands_executed': 0,
            'errors': []
        }

        try:
            if self.on_sync_start:
                self.on_sync_start()

            # Step 1: Send heartbeat
            if self.on_sync_progress:
                self.on_sync_progress(10, 'إرسال heartbeat...')

            computer_info = self.get_computer_info()
            self.api.send_bridge_heartbeat(
                computer_name=computer_info['computer_name'],
                ip_address=computer_info['ip_address'],
                os_info=computer_info['os_info'],
                database_path=self.db.database_path if self.db else '',
                database_found=self.db.is_connected() if self.db else False
            )

            # Step 2: Get local members
            if self.on_sync_progress:
                self.on_sync_progress(20, 'قراءة قاعدة البيانات المحلية...')

            local_members = self.db.get_all_employees() if self.db else []

            # Step 3: Sync new members to web
            if self.on_sync_progress:
                self.on_sync_progress(40, 'مزامنة الأعضاء الجدد...')

            synced = self._sync_members_to_web(local_members)
            result['synced_members'] = synced

            # Step 3.5: Sync attendance from att2000.mdb
            if self.device_db and self.device_db.mdb_path:
                if self.on_sync_progress:
                    self.on_sync_progress(45, 'مزامنة بيانات البصمة...')
                try:
                    attendance_result = self._sync_attendance()
                    result['attendance_synced'] = attendance_result
                except Exception as e:
                    result['errors'].append(f'خطأ مزامنة البصمة: {e}')

            # Step 3.7: Access control (write end_date based on class schedule)
            if self.access_control_enabled and self.db:
                if self.on_sync_progress:
                    self.on_sync_progress(55, 'تحديث صلاحيات الدخول...')
                try:
                    self._update_access_control()
                except Exception as e:
                    result['errors'].append(f'خطأ التحكم بالدخول: {e}')

            # Step 4: Get and execute pending commands
            if self.on_sync_progress:
                self.on_sync_progress(70, 'تنفيذ الأوامر المعلقة...')

            commands_result = self._execute_pending_commands()
            result['commands_executed'] = commands_result['executed']
            if commands_result['errors']:
                result['errors'].extend(commands_result['errors'])

            # Step 4.5: Flush offline queue if we have connectivity
            if self._offline_queue:
                try:
                    self._flush_offline_queue()
                except Exception:
                    pass

            # Step 5: Complete
            if self.on_sync_progress:
                self.on_sync_progress(100, 'اكتملت المزامنة')

            self.last_sync_time = datetime.now()
            self.total_synced += result['synced_members']

            if self.on_sync_complete:
                self.on_sync_complete(result)

        except Exception as e:
            result['success'] = False
            result['errors'].append(str(e))
            self.last_error = str(e)

            if self.on_sync_error:
                self.on_sync_error(str(e))

        finally:
            self.is_syncing = False

        return result

    def _sync_members_to_web(self, local_members: List[Dict]) -> int:
        """Sync local members to web app"""
        synced = 0

        for member in local_members:
            emp_id = member.get('emp_id', '').strip()
            if not emp_id:
                continue

            # Check if member exists in cache (already synced)
            cache_key = emp_id
            cached = self.local_members_cache.get(cache_key)

            # Simple check - if cached data matches, skip
            current_hash = f"{member.get('emp_name')}-{member.get('phone_code')}-{member.get('end_date')}"

            if cached == current_hash:
                continue

            # Sync to web
            try:
                member_data = {
                    'name': member.get('emp_name', ''),
                    'phone': member.get('phone_code', ''),
                    'gender': member.get('sex', 'male'),
                    'fingerprint_id': int(emp_id.lstrip('0') or '0')
                }

                result = self.api.create_member(member_data)

                if result.get('success') or result.get('member_id'):
                    self.local_members_cache[cache_key] = current_hash
                    synced += 1

            except Exception as e:
                print(f"Error syncing member {emp_id}: {e}")

        return synced

    def _execute_pending_commands(self) -> Dict:
        """Get and execute pending commands from web app"""
        result = {
            'executed': 0,
            'errors': []
        }

        try:
            # Get pending commands
            response = self.api.get_pending_commands()

            if not response.get('success'):
                return result

            commands = response.get('commands', [])
            self.pending_commands = len(commands)

            for cmd in commands:
                try:
                    success = self._execute_command(cmd)

                    # Report completion to web
                    self.api.complete_command(
                        cmd['id'],
                        success=success,
                        error_message=None if success else 'فشل تنفيذ الأمر'
                    )

                    if success:
                        result['executed'] += 1
                        if self.on_command_executed:
                            self.on_command_executed(cmd)

                except Exception as e:
                    result['errors'].append(f"Command {cmd['id']}: {str(e)}")

        except Exception as e:
            result['errors'].append(str(e))

        return result

    def _execute_command(self, command: Dict) -> bool:
        """Execute a single command on local database"""
        cmd_type = command.get('command_type')
        emp_id = command.get('target_emp_id')
        data = command.get('command_data', {})

        if not self.db:
            return False

        if cmd_type == 'block_member':
            return self.db.block_employee(emp_id)

        elif cmd_type == 'unblock_member':
            end_date = data.get('end_date', '2026-12-31')
            return self.db.unblock_employee(emp_id, end_date)

        elif cmd_type == 'update_member':
            update_data = {}
            if 'emp_name' in data:
                update_data['emp_name'] = data['emp_name']
            if 'phone_code' in data:
                update_data['phone_code'] = data['phone_code']
            if 'end_date' in data:
                update_data['end_date'] = data['end_date']
            return self.db.update_employee(emp_id, update_data)

        elif cmd_type == 'add_member':
            return self.db.add_employee(data)

        elif cmd_type == 'delete_member':
            return self.db.delete_employee(emp_id)

        return False

    def initial_sync(self, callback: Callable = None) -> Dict:
        """Perform initial full sync (first setup)"""
        result = {
            'success': True,
            'total_members': 0,
            'synced': 0,
            'errors': []
        }

        try:
            if callback:
                callback(0, 'بدء المزامنة الأولى...')

            # Get all local members
            local_members = self.db.get_all_employees() if self.db else []
            result['total_members'] = len(local_members)

            if callback:
                callback(20, f'تم العثور على {len(local_members)} عضو')

            # Sync each member
            for i, member in enumerate(local_members):
                progress = 20 + int((i / max(len(local_members), 1)) * 70)

                if callback:
                    callback(progress, f'مزامنة العضو {i+1} من {len(local_members)}...')

                try:
                    emp_id = member.get('emp_id', '').strip()
                    if not emp_id:
                        continue

                    member_data = {
                        'name': member.get('emp_name', ''),
                        'phone': member.get('phone_code', ''),
                        'gender': member.get('sex', 'male'),
                        'fingerprint_id': int(emp_id.lstrip('0') or '0')
                    }

                    api_result = self.api.create_member(member_data)

                    if api_result.get('success') or api_result.get('member_id'):
                        result['synced'] += 1
                        # Update cache
                        cache_key = emp_id
                        current_hash = f"{member.get('emp_name')}-{member.get('phone_code')}-{member.get('end_date')}"
                        self.local_members_cache[cache_key] = current_hash

                except Exception as e:
                    result['errors'].append(str(e))

            if callback:
                callback(100, 'اكتملت المزامنة الأولى')

        except Exception as e:
            result['success'] = False
            result['errors'].append(str(e))

        return result

    # ─── Attendance Sync (att2000.mdb → cloud) ─────────────────────────

    def _sync_attendance(self) -> int:
        """Read CHECKINOUT from att2000.mdb, send to cloud, fire events."""
        records = self.device_db.read_checkinout(since_time=self.last_attendance_sync_time)
        if not records:
            return 0

        # Build name cache from local members if empty
        if not self._members_name_cache and self.db:
            try:
                members = self.db.get_all_employees()
                self._members_name_cache = {
                    m.get('emp_id', '').strip(): m.get('emp_name', '').strip()
                    for m in members
                }
            except Exception:
                pass

        # Convert to API format
        api_records = []
        latest_time = self.last_attendance_sync_time

        for rec in records:
            check_time = rec.get('CHECKTIME')
            if not check_time:
                continue

            if isinstance(check_time, str):
                try:
                    check_time = datetime.fromisoformat(check_time)
                except ValueError:
                    try:
                        check_time = datetime.strptime(check_time, '%m/%d/%y %H:%M:%S')
                    except ValueError:
                        continue

            user_id = rec.get('USERID')
            emp_id_str = str(user_id).zfill(8)

            api_records.append({
                'fingerprint_id': user_id,
                'timestamp': check_time.isoformat(),
                'log_id': _stable_log_id(user_id, check_time)
            })

            # Fire live feed event
            if self.on_attendance_event:
                member_name = self._members_name_cache.get(emp_id_str, f'عضو {user_id}')
                self.on_attendance_event({
                    'emp_id': emp_id_str,
                    'name': member_name,
                    'time': check_time.strftime('%H:%M:%S'),
                    'timestamp': check_time,
                    'check_type': rec.get('CHECKTYPE', ''),
                    'status': 'allowed',  # Will be updated by cloud response
                    'status_text': 'مسموح'
                })

            if latest_time is None or check_time > latest_time:
                latest_time = check_time

        if not api_records:
            return 0

        # Send to cloud
        result = self.api.sync_attendance(api_records)
        if result and result.get('success'):
            synced = result.get('synced', 0)
            self.last_attendance_sync_time = latest_time
            self._save_last_attendance_time(latest_time)

            # Fire blocked events
            for blocked in result.get('blocked_entries', []):
                if self.on_attendance_event:
                    self.on_attendance_event({
                        'emp_id': str(blocked.get('fingerprint_id', '')).zfill(8),
                        'name': blocked.get('member_name', ''),
                        'time': datetime.now().strftime('%H:%M:%S'),
                        'timestamp': datetime.now(),
                        'status': 'blocked',
                        'status_text': blocked.get('reason', 'محظور')
                    })
            return synced
        else:
            # Cloud unreachable — queue
            self._offline_queue.extend(api_records)
            self._save_offline_queue()
            return 0

    def _flush_offline_queue(self):
        """Send queued attendance records when cloud is back."""
        if not self._offline_queue:
            return
        result = self.api.sync_attendance(self._offline_queue)
        if result and result.get('success'):
            self._offline_queue.clear()
            self._save_offline_queue()

    # ─── Access Control (cloud → backup.mdb) ─────────────────────────

    def _update_access_control(self):
        """Fetch class schedule and update end_date in backup.mdb."""
        schedule = self.api.get_class_schedule()
        if schedule and schedule.get('success'):
            self._cached_schedule = schedule
            self._save_schedule_cache(schedule)
        else:
            schedule = self._cached_schedule
            if not schedule:
                return

        # Notify UI
        if self.on_schedule_update:
            self.on_schedule_update(schedule)

        access_window = schedule.get('access_window_minutes', self.class_access_window_minutes)
        now = datetime.now()
        today = date.today()
        yesterday = today - timedelta(days=1)
        block_date = '2020-01-01'

        # Process class-booked members
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
                    self.db.update_employee_end_date(emp_id, today.strftime('%Y-%m-%d'))
                else:
                    self.db.update_employee_end_date(emp_id, yesterday.strftime('%Y-%m-%d'))

        # Process gym members (no class requirement)
        for member in schedule.get('gym_members', []):
            emp_id = member.get('emp_id')
            end_date_str = member.get('subscription_end_date')
            if emp_id and end_date_str:
                self.db.update_employee_end_date(emp_id, end_date_str)

        # Process blocked members
        for member in schedule.get('blocked_members', []):
            emp_id = member.get('emp_id')
            if emp_id:
                self.db.update_employee_end_date(emp_id, block_date)

    # ─── Persistence helpers ─────────────────────────────────────────

    def _load_last_attendance_time(self):
        try:
            path = BRIDGE_DIR / 'last_attendance_sync.txt'
            if path.exists():
                return datetime.fromisoformat(path.read_text().strip())
        except Exception:
            pass
        return None

    def _save_last_attendance_time(self, dt):
        try:
            BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
            (BRIDGE_DIR / 'last_attendance_sync.txt').write_text(dt.isoformat())
        except Exception:
            pass

    def _load_offline_queue(self):
        try:
            path = BRIDGE_DIR / 'offline_queue.json'
            if path.exists():
                return json.loads(path.read_text())
        except Exception:
            pass
        return []

    def _save_offline_queue(self):
        try:
            BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
            (BRIDGE_DIR / 'offline_queue.json').write_text(json.dumps(self._offline_queue))
        except Exception:
            pass

    def _load_schedule_cache(self):
        try:
            path = BRIDGE_DIR / 'schedule_cache.json'
            if path.exists():
                return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
        return None

    def _save_schedule_cache(self, schedule):
        try:
            BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
            (BRIDGE_DIR / 'schedule_cache.json').write_text(
                json.dumps(schedule, ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass

    # ─── Status ──────────────────────────────────────────────────────

    def get_status(self) -> Dict:
        """Get current sync status"""
        return {
            'is_syncing': self.is_syncing,
            'auto_sync_enabled': self.auto_sync_enabled,
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'last_sync_formatted': self.last_sync_time.strftime('%H:%M:%S') if self.last_sync_time else 'لم تتم',
            'total_synced': self.total_synced,
            'pending_commands': self.pending_commands,
            'last_error': self.last_error,
            'sync_interval': self.sync_interval,
            'device_db_connected': bool(self.device_db and self.device_db.mdb_path),
            'access_control_enabled': self.access_control_enabled,
            'offline_queue_size': len(self._offline_queue)
        }
