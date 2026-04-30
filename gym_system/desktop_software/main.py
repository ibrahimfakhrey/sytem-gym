"""
Gym Management System - Desktop Software
Main entry point
"""

import sys
import threading
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, '.')

from config import load_config, save_config, APP_NAME, APP_VERSION
from core import FileFinder, DatabaseManager, DeviceDatabaseManager, APIClient, SyncManager
from ui import MainWindow


class AppController:
    """Main application controller"""

    def __init__(self):
        self.config = load_config()
        self.window = None
        self.file_finder = FileFinder()
        self.db_manager = None
        self.device_db_manager = None  # For att2000.mdb (ZKTeco CHECKINOUT)
        self.api_client = None
        self.sync_manager = None

        self.auto_sync_enabled = True
        self.is_syncing = False

    def initialize(self):
        """Initialize the application"""
        # Create main window
        self.window = MainWindow(app_controller=self)

        # Check if registered
        if not self.config.get('is_registered'):
            # Show setup page and wait for registration
            self.window.load_settings(self.config)
            if 'setup' in self.window.pages:
                self.window.pages['setup'].load_config(self.config)
            self.window.show_page('setup')
            return  # Don't continue init until registered

        # Initialize API client with branch info
        api_url = self.config.get('api_url', 'https://gymsystem.pythonanywhere.com')
        api_key = self.config.get('api_key', '')
        brand_id = self.config.get('brand_id', 1)

        self.api_client = APIClient(
            base_url=api_url,
            api_key=api_key,
            brand_id=brand_id
        )

        # Set window title with branch name
        branch_name = self.config.get('branch_name', '')
        brand_name = self.config.get('brand_name', '')
        if branch_name:
            self.window.title(f"نظام الجيم - {branch_name} | {brand_name}")

        # Try to connect to database
        db_path = self.config.get('db_path')
        if db_path:
            self._connect_database(db_path)
        else:
            # Auto-detect database
            self._auto_detect_database()

        # Try to connect to ZKTeco device database (att2000.mdb)
        att2000_path = self.config.get('att2000_db_path')
        if att2000_path:
            self._connect_device_database(att2000_path)
        else:
            self._auto_detect_device_database()

        # Initialize sync manager
        if self.db_manager and self.api_client:
            self.sync_manager = SyncManager(
                database_manager=self.db_manager,
                api_client=self.api_client,
                device_db_manager=self.device_db_manager
            )
            # Configure access control from settings
            self.sync_manager.access_control_enabled = self.config.get('access_control_enabled', False)
            self.sync_manager.class_access_window_minutes = self.config.get('class_access_window_minutes', 15)
            # Set callbacks for live feed and schedule
            self.sync_manager.on_attendance_event = self._on_attendance_event
            self.sync_manager.on_schedule_update = self._on_schedule_update

        # Load settings into UI
        self.window.load_settings(self.config)

        # Update initial status
        self._update_connection_status()

        # Start auto-sync if enabled
        if self.config.get('auto_start_sync', True) and self.sync_manager:
            interval = self.config.get('sync_interval', 30)
            self.start_auto_sync(interval)

        # Load initial data
        self._load_initial_data()

    def _connect_database(self, db_path: str, password: str = None) -> bool:
        """Connect to database"""
        try:
            # Get password from config if not provided
            if password is None:
                password = self.config.get('database_password') or self.config.get('db_password', '')

            self.db_manager = DatabaseManager(db_path, password=password)
            if self.db_manager.connect():
                self.window.add_activity(f"تم الاتصال بقاعدة البيانات", "success")
                return True
            else:
                self.window.add_activity("فشل الاتصال بقاعدة البيانات - تحقق من كلمة المرور", "error")
                return False
        except Exception as e:
            self.window.add_activity(f"خطأ: {str(e)}", "error")
            return False

    def _auto_detect_database(self):
        """Auto-detect database files"""
        self.window.add_activity("جاري البحث عن قاعدة البيانات...", "info")

        def search_thread():
            results = self.file_finder.search_for_mdb()
            if results:
                # Use first non-backup result
                for result in results:
                    if not result.get('is_backup'):
                        db_path = result['path']
                        self.window.after(0, lambda: self._on_database_found(db_path))
                        return

                # If all are backups, use first one
                db_path = results[0]['path']
                self.window.after(0, lambda: self._on_database_found(db_path))
            else:
                self.window.after(0, lambda: self.window.add_activity(
                    "لم يتم العثور على قاعدة البيانات", "warning"
                ))

        thread = threading.Thread(target=search_thread, daemon=True)
        thread.start()

    def _on_database_found(self, db_path: str):
        """Handle database found"""
        self.window.add_activity(f"تم العثور على قاعدة البيانات", "success")
        if self._connect_database(db_path):
            self.config['db_path'] = db_path
            save_config(self.config)

            # Initialize sync manager
            if self.api_client:
                self.sync_manager = SyncManager(
                    database_manager=self.db_manager,
                    api_client=self.api_client,
                    device_db_manager=self.device_db_manager
                )
                self.sync_manager.access_control_enabled = self.config.get('access_control_enabled', False)
                self.sync_manager.class_access_window_minutes = self.config.get('class_access_window_minutes', 15)
                self.sync_manager.on_attendance_event = self._on_attendance_event
                self.sync_manager.on_schedule_update = self._on_schedule_update

            self._update_connection_status()
            self._load_initial_data()

    def _connect_device_database(self, db_path: str) -> bool:
        """Connect to ZKTeco device database (att2000.mdb)"""
        try:
            self.device_db_manager = DeviceDatabaseManager(db_path)
            if self.device_db_manager.is_connected():
                count = self.device_db_manager.get_record_count()
                self.window.add_activity(f"تم الاتصال بقاعدة بيانات البصمة ({count} سجل)", "success")
                return True
            else:
                self.window.add_activity("فشل الاتصال بقاعدة بيانات البصمة", "warning")
                self.device_db_manager = None
                return False
        except Exception as e:
            self.window.add_activity(f"خطأ في قاعدة بيانات البصمة: {e}", "error")
            self.device_db_manager = None
            return False

    def _auto_detect_device_database(self):
        """Auto-detect att2000.mdb among found .mdb files"""
        def detect_thread():
            results = self.file_finder.search_for_mdb()
            for result in results:
                db_path = result['path']
                try:
                    schema_type = DeviceDatabaseManager.detect_schema(db_path)
                    if schema_type == 'device':
                        self.window.after(0, lambda p=db_path: self._on_device_db_found(p))
                        return
                except Exception:
                    continue

        threading.Thread(target=detect_thread, daemon=True).start()

    def _on_device_db_found(self, db_path: str):
        """Handle ZKTeco device database found"""
        if self._connect_device_database(db_path):
            self.config['att2000_db_path'] = db_path
            save_config(self.config)
            # Update sync manager with device DB
            if self.sync_manager:
                self.sync_manager.device_db = self.device_db_manager

    def _on_attendance_event(self, event: dict):
        """Handle attendance event from sync manager (called from sync thread)"""
        if self.window:
            self.window.after(0, lambda: self._dispatch_attendance_event(event))

    def _dispatch_attendance_event(self, event: dict):
        """Dispatch attendance event to UI (main thread)"""
        if hasattr(self.window, 'add_attendance_event'):
            self.window.add_attendance_event(event)

    def _on_schedule_update(self, schedule: dict):
        """Handle schedule update from sync manager (called from sync thread)"""
        if self.window:
            self.window.after(0, lambda: self._dispatch_schedule_update(schedule))

    def _dispatch_schedule_update(self, schedule: dict):
        """Dispatch schedule update to UI (main thread)"""
        if hasattr(self.window, 'update_class_schedule'):
            self.window.update_class_schedule(schedule)

    def _update_connection_status(self):
        """Update connection status in UI"""
        # Database status
        db_connected = self.db_manager is not None and self.db_manager.is_connected
        db_path = self.config.get('db_path')
        self.window.update_database_status(db_connected, db_path)

        # API status (test connection)
        if self.api_client:
            threading.Thread(target=self._check_api_status, daemon=True).start()

    def _check_api_status(self):
        """Check API connection status"""
        try:
            result = self.api_client.test_connection()
            connected = result.get('success', False)
            self.window.after(0, lambda: self.window.update_api_status(
                connected, self.config.get('api_url')
            ))
        except:
            self.window.after(0, lambda: self.window.update_api_status(False))

    def _load_initial_data(self):
        """Load initial data"""
        if self.db_manager and self.db_manager.is_connected:
            # Load members
            members = self.db_manager.get_all_employees()
            self.window.set_members(members)

            # Update stats
            total = len(members)
            active = sum(1 for m in members if not self._is_blocked(m))
            blocked = total - active

            self.window.update_dashboard_stats({
                'total_members': total,
                'active_members': active,
                'blocked_members': blocked
            })

    def _is_blocked(self, member: dict) -> bool:
        """Check if member is blocked"""
        if member.get('end_date'):
            try:
                end_date = datetime.strptime(member['end_date'], '%Y-%m-%d')
                return end_date < datetime.now()
            except:
                pass
        return False

    # =====================
    # Sync Methods
    # =====================

    def start_auto_sync(self, interval: int = 30):
        """Start auto sync"""
        if self.sync_manager:
            self.auto_sync_enabled = True
            self._schedule_sync(interval)
            self.window.add_activity(f"تم بدء المزامنة التلقائية كل {interval} ثانية", "sync")

    def _schedule_sync(self, interval: int):
        """Schedule next sync"""
        if self.auto_sync_enabled and self.window:
            self.window.after(interval * 1000, lambda: self._do_sync(interval))

    def _do_sync(self, interval: int):
        """Perform sync"""
        if not self.auto_sync_enabled:
            return

        if not self.is_syncing:
            self.sync_now()

        # Schedule next sync
        self._schedule_sync(interval)

    def sync_now(self):
        """Trigger manual sync"""
        if self.is_syncing:
            return

        if not self.sync_manager:
            self.window.add_activity("لم يتم إعداد المزامنة بعد", "warning")
            return

        self.is_syncing = True
        self.window.update_sync_progress("جاري المزامنة...", 0)

        def sync_thread():
            try:
                result = self.sync_manager.sync()

                # Update UI on main thread
                self.window.after(0, lambda: self._on_sync_complete(result))
            except Exception as e:
                self.window.after(0, lambda: self._on_sync_error(str(e)))

        thread = threading.Thread(target=sync_thread, daemon=True)
        thread.start()

    def _on_sync_complete(self, result: dict):
        """Handle sync complete"""
        self.is_syncing = False

        if result.get('success'):
            time_str = datetime.now().strftime('%H:%M:%S')
            self.window.set_sync_complete(time_str)
            self.window.add_activity("تمت المزامنة بنجاح", "success")
            self.window.add_sync_log("مزامنة ناجحة", "success")

            # Update dashboard stats
            self.window.update_dashboard_stats({
                'last_sync': time_str
            })

            # Refresh data
            self._load_initial_data()

            # Update commands if any were executed
            if result.get('commands_executed', 0) > 0:
                self.window.add_activity(
                    f"تم تنفيذ {result['commands_executed']} أوامر",
                    "success"
                )
        else:
            error = result.get('error', 'خطأ غير معروف')
            self.window.set_error_status(error)
            self.window.add_activity(f"فشلت المزامنة: {error}", "error")
            self.window.add_sync_log(f"فشل: {error}", "error")

    def _on_sync_error(self, error: str):
        """Handle sync error"""
        self.is_syncing = False
        self.window.set_error_status(error)
        self.window.add_activity(f"خطأ في المزامنة: {error}", "error")
        self.window.add_sync_log(f"خطأ: {error}", "error")

    def toggle_auto_sync(self, enabled: bool):
        """Toggle auto sync"""
        self.auto_sync_enabled = enabled
        if enabled:
            interval = self.config.get('sync_interval', 30)
            self.start_auto_sync(interval)
        else:
            self.window.add_activity("تم إيقاف المزامنة التلقائية", "warning")

    # =====================
    # Member Methods
    # =====================

    def add_member(self, data: dict) -> tuple:
        """Add a new member to database"""
        if not self.db_manager or not self.db_manager.is_connected:
            return False, "قاعدة البيانات غير متصلة"

        try:
            success = self.db_manager.add_employee(data)
            if success:
                self.window.add_activity(f"تم إضافة العضو: {data.get('emp_name')}", "add")
                self._load_initial_data()
                return True, "تم إضافة العضو بنجاح"
            else:
                return False, "فشل إضافة العضو"
        except Exception as e:
            return False, str(e)

    def get_members(self) -> list:
        """Get all members from database"""
        if not self.db_manager or not self.db_manager.is_connected:
            return []

        return self.db_manager.get_all_employees()

    def block_member(self, emp_id: str) -> tuple:
        """Block a member"""
        if not self.db_manager or not self.db_manager.is_connected:
            return False, "قاعدة البيانات غير متصلة"

        try:
            success = self.db_manager.block_employee(emp_id)
            if success:
                self.window.add_activity(f"تم حظر العضو: {emp_id}", "block")
                return True, "تم حظر العضو"
            else:
                return False, "فشل حظر العضو"
        except Exception as e:
            return False, str(e)

    def unblock_member(self, emp_id: str) -> tuple:
        """Unblock a member"""
        if not self.db_manager or not self.db_manager.is_connected:
            return False, "قاعدة البيانات غير متصلة"

        try:
            # Set end date to 1 year from now
            from datetime import timedelta
            end_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
            success = self.db_manager.unblock_employee(emp_id, end_date)
            if success:
                self.window.add_activity(f"تم إلغاء حظر العضو: {emp_id}", "unblock")
                return True, "تم إلغاء حظر العضو"
            else:
                return False, "فشل إلغاء حظر العضو"
        except Exception as e:
            return False, str(e)

    # =====================
    # Commands Methods
    # =====================

    def get_pending_commands(self) -> list:
        """Get pending commands from API"""
        if not self.api_client:
            return []

        try:
            result = self.api_client.get_pending_commands()
            return result.get('commands', [])
        except:
            return []

    def execute_command(self, command: dict) -> bool:
        """Execute a single command"""
        if not self.sync_manager:
            return False

        try:
            result = self.sync_manager._execute_command(command)
            if result:
                self.window.add_activity(
                    f"تم تنفيذ الأمر: {command.get('command_type')}",
                    "success"
                )
            return result
        except Exception as e:
            self.window.add_activity(f"فشل تنفيذ الأمر: {str(e)}", "error")
            return False

    # =====================
    # Registration Methods
    # =====================

    def complete_registration(self, reg_data: dict):
        """Called after successful branch registration from setup page"""
        # Save registration data to config
        self.config.update(reg_data)

        # Also save settings from server
        settings = reg_data.get('settings', {})
        if settings:
            self.config['access_control_enabled'] = settings.get('class_access_control_enabled', False)
            self.config['class_access_window_minutes'] = settings.get('class_access_window_minutes', 15)
            self.config['employee_shift_tracking_enabled'] = settings.get('employee_shift_tracking_enabled', False)

        save_config(self.config)

        # Re-initialize the full app now that we're registered
        self.window.add_activity(f"تم تسجيل الفرع: {reg_data.get('branch_name')}", "success")

        # Initialize API client
        self.api_client = APIClient(
            base_url=self.config.get('api_url', ''),
            api_key=self.config.get('api_key', ''),
            brand_id=self.config.get('brand_id', 1)
        )

        # Set window title
        self.window.title(f"نظام الجيم - {reg_data.get('branch_name', '')} | {reg_data.get('brand_name', '')}")

        # Continue initialization — connect databases, start sync
        db_path = self.config.get('db_path') or self.config.get('database_path')
        if db_path:
            self._connect_database(db_path)
        else:
            self._auto_detect_database()

        att2000_path = self.config.get('att2000_db_path')
        if att2000_path:
            self._connect_device_database(att2000_path)
        else:
            self._auto_detect_device_database()

        # Init sync manager
        if self.db_manager and self.api_client:
            self.sync_manager = SyncManager(
                database_manager=self.db_manager,
                api_client=self.api_client,
                device_db_manager=self.device_db_manager
            )
            self.sync_manager.access_control_enabled = self.config.get('access_control_enabled', False)
            self.sync_manager.on_attendance_event = self._on_attendance_event
            self.sync_manager.on_schedule_update = self._on_schedule_update

        self._update_connection_status()
        self._load_initial_data()

        # Show dashboard
        self.window.show_page('home')

        # Start auto-sync
        if self.config.get('auto_start', True) and self.sync_manager:
            interval = self.config.get('sync_interval', 30)
            self.start_auto_sync(interval)

    # =====================
    # Settings Methods
    # =====================

    def find_database(self) -> str:
        """Find database file"""
        results = self.file_finder.search_for_mdb()
        if results:
            for result in results:
                if not result.get('is_backup'):
                    return result['path']
            return results[0]['path']
        return None

    def save_settings(self, settings: dict) -> bool:
        """Save application settings"""
        try:
            # Map UI settings to config keys
            config_update = {
                'api_url': settings.get('api_url'),
                'api_key': settings.get('api_key'),
                'brand_id': settings.get('brand_id'),
                'database_path': settings.get('db_path'),
                'database_password': settings.get('db_password', ''),
                'att2000_db_path': settings.get('att2000_db_path'),
                'sync_interval': settings.get('sync_interval'),
                'auto_start': settings.get('auto_start_sync'),
                'access_control_enabled': settings.get('access_control_enabled'),
                'class_access_window_minutes': settings.get('class_access_window_minutes'),
                'employee_shift_tracking_enabled': settings.get('employee_shift_tracking_enabled')
            }
            # Remove None values
            config_update = {k: v for k, v in config_update.items() if v is not None}

            self.config.update(config_update)
            save_config(self.config)

            # Update API client
            if self.api_client:
                self.api_client.base_url = settings.get('api_url', self.api_client.base_url)
                self.api_client.api_key = settings.get('api_key', self.api_client.api_key)
                self.api_client.brand_id = int(settings.get('brand_id', self.api_client.brand_id))

            # Reconnect database if path or password changed
            new_db_path = settings.get('db_path')
            new_db_password = settings.get('db_password', '')
            old_db_path = self.config.get('database_path')
            old_db_password = self.config.get('database_password', '')

            if new_db_path and (new_db_path != old_db_path or new_db_password != old_db_password):
                self._connect_database(new_db_path, new_db_password)
                self._update_connection_status()
                self._load_initial_data()

            # Reconnect device database if path changed
            new_att2000 = settings.get('att2000_db_path')
            old_att2000 = self.config.get('att2000_db_path', '')
            if new_att2000 and new_att2000 != old_att2000:
                self._connect_device_database(new_att2000)
                if self.sync_manager:
                    self.sync_manager.device_db = self.device_db_manager

            # Update access control settings on sync manager
            if self.sync_manager:
                self.sync_manager.access_control_enabled = self.config.get('access_control_enabled', False)
                self.sync_manager.class_access_window_minutes = self.config.get('class_access_window_minutes', 15)

            self.window.add_activity("تم حفظ الإعدادات", "success")
            return True
        except Exception as e:
            self.window.add_activity(f"فشل حفظ الإعدادات: {str(e)}", "error")
            return False

    def run(self):
        """Run the application"""
        self.initialize()
        self.window.mainloop()


def main():
    """Main entry point"""
    print(f"\n{'='*50}")
    print(f"  {APP_NAME} v{APP_VERSION}")
    print(f"  نظام إدارة الجيم")
    print(f"{'='*50}\n")

    app = AppController()
    app.run()


if __name__ == "__main__":
    main()
