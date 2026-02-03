"""
Sync Manager - Handle synchronization between local database and web app
"""

import threading
import time
from typing import Dict, List, Callable, Optional
from datetime import datetime
import socket
import platform


class SyncManager:
    """Manage synchronization between local .mdb and web app"""

    def __init__(self, database_manager, api_client):
        self.db = database_manager
        self.api = api_client

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

        # Stats
        self.total_synced = 0
        self.pending_commands = 0
        self.last_error = None

        # Local cache
        self.local_members_cache = {}

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

            # Step 4: Get and execute pending commands
            if self.on_sync_progress:
                self.on_sync_progress(70, 'تنفيذ الأوامر المعلقة...')

            commands_result = self._execute_pending_commands()
            result['commands_executed'] = commands_result['executed']
            if commands_result['errors']:
                result['errors'].extend(commands_result['errors'])

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
            'sync_interval': self.sync_interval
        }
