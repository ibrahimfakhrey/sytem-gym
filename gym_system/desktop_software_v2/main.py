"""
Gym System Bridge v2 — entry point.

Run: python main.py
"""
import sys
import threading

import config as cfg
from ui.window import MainWindow
from core.sync_engine import SyncEngine
from core.file_finder import search as find_dbs


class Controller:
    """
    Single controller bridges UI and sync engine.
    Pages call methods on this; sync engine fires callbacks back to status page.
    """

    def __init__(self):
        self.config = cfg.load()
        self.window = None
        self.sync_engine = None

    # ── Lifecycle ──
    def run(self):
        self.window = MainWindow(controller=self)
        self.window.create_pages()

        if not self.config.get('is_registered'):
            # Pre-fill setup with any existing config
            self.window.pages['setup'].load_config(self.config)
            self.window.show('setup')
        else:
            self._enter_running_state()

        self.window.protocol('WM_DELETE_WINDOW', self._on_close)
        self.window.mainloop()

    def _on_close(self):
        if self.sync_engine:
            self.sync_engine.stop()
        self.window.destroy()
        sys.exit(0)

    # ── Pages call these ──
    def complete_registration(self, registration_data: dict):
        """Called from setup page after successful health check."""
        self.config.update(registration_data)
        cfg.save(self.config)
        self._enter_running_state()

    def save_settings(self, updates: dict):
        """Called from settings page."""
        self.config.update(updates)
        cfg.save(self.config)

        # Restart sync engine with new config
        if self.sync_engine:
            self.sync_engine.stop()
            self._start_sync_engine()

    def show_status(self):
        self.window.show('status')

    def show_settings(self):
        self.window.pages['settings'].load_config(self.config)
        self.window.show('settings')

    def sync_now(self):
        if not self.sync_engine:
            self.window.pages['status'].add_log('المزامنة غير جاهزة', 'warning')
            return

        self.window.pages['status'].add_log('جاري المزامنة...', 'info')
        threading.Thread(target=self.sync_engine.sync_once, daemon=True).start()

    # ── Internal ──
    def _enter_running_state(self):
        """Called after registration. Auto-detect DBs, start sync, show status."""
        # Set title
        self.window.set_title_for_branch(
            self.config.get('branch_name'),
            self.config.get('brand_name'),
        )

        # Show status page
        status = self.window.pages['status']
        status.update_branch_info(
            self.config.get('branch_name', ''),
            self.config.get('brand_name', ''),
        )
        self.window.show('status')

        # Auto-detect DB paths if not set
        if not self.config.get('db_path_members') or not self.config.get('db_path_attendance'):
            status.add_log('🔍 بحث تلقائي عن قواعد البيانات...', 'info')
            threading.Thread(target=self._auto_detect, daemon=True).start()
        else:
            self._start_sync_engine()

    def _auto_detect(self):
        try:
            members, device = find_dbs()
        except Exception as e:
            self.window.after(0, lambda: self.window.pages['status'].add_log(
                f'فشل البحث: {e}', 'error'))
            return

        if members:
            self.config['db_path_members'] = members
        if device:
            self.config['db_path_attendance'] = device

        cfg.save(self.config)

        msg_lvl = ('success' if (members and device) else
                   'warning' if (members or device) else 'error')
        msg = (
            f'✓ تم العثور على ملفي قاعدة البيانات' if (members and device) else
            f'⚠ تم العثور على ملف واحد فقط — افتح الإعدادات لتحديد الباقي' if (members or device) else
            '✗ لم يتم العثور على ملفات — افتح الإعدادات لتحديدها يدوياً'
        )
        self.window.after(0, lambda: self.window.pages['status'].add_log(msg, msg_lvl))

        if members and device:
            self.window.after(100, self._start_sync_engine)
        else:
            # Update status — DB not connected
            self.window.after(0, lambda: self.window.pages['status'].update_db_status(
                False, 'لم يتم تحديد الملفات'))

    def _start_sync_engine(self):
        if self.sync_engine:
            self.sync_engine.stop()

        self.sync_engine = SyncEngine(
            config=self.config,
            on_status=self._on_sync_status,
            on_stats=self._on_sync_stats,
            on_config_save=self._on_config_save,
        )
        self.sync_engine.start()

        status = self.window.pages['status']
        status.update_server_status(True, 'متصل')
        status.update_db_status(True, 'متصلة')
        status.update_sync_status(True, 'نشطة')
        status.add_log('بدأت المزامنة التلقائية', 'success')

    # ── Sync engine callbacks ──
    def _on_sync_status(self, msg, level):
        if not self.window:
            return
        self.window.after(0, lambda: self.window.pages['status'].add_log(msg, level))

    def _on_sync_stats(self, stats):
        if not self.window:
            return
        self.window.after(0, lambda: self.window.pages['status'].update_stats(stats))

    def _on_config_save(self, config):
        cfg.save(config)


def main():
    print('\n' + '=' * 50)
    print('  Gym Bridge v2.0')
    print('=' * 50 + '\n')
    Controller().run()


if __name__ == '__main__':
    main()
