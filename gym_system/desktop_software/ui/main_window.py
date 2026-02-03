"""
Main application window
"""

import customtkinter as ctk
from .styles import COLORS, FONTS, configure_theme
from .components import Sidebar, StatusBar
from .pages import (
    HomePage, AddMemberPage, MembersPage,
    SyncPage, CommandsPage, SettingsPage
)


class MainWindow(ctk.CTk):
    """Main application window"""

    def __init__(self, app_controller=None):
        super().__init__()

        self.app_controller = app_controller

        # Configure theme
        configure_theme()

        # Window configuration
        self.title("نظام إدارة الجيم - Gym Management System")
        self.geometry("1200x700")
        self.minsize(900, 600)

        # Set background color
        self.configure(fg_color=COLORS['background'])

        # Page references
        self.pages = {}
        self.current_page = None

        self._create_layout()
        self._create_pages()

        # Show home page by default
        self.show_page('home')

    def _create_layout(self):
        """Create main layout"""
        # Main container
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True)

        # Sidebar
        self.sidebar = Sidebar(self.main_container, on_navigate=self.show_page)
        self.sidebar.pack(side="right", fill="y")

        # Content area
        self.content_container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.content_container.pack(side="right", fill="both", expand=True)

        # Page container
        self.page_container = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.page_container.pack(fill="both", expand=True)

        # Status bar
        self.status_bar = StatusBar(self.content_container)
        self.status_bar.pack(side="bottom", fill="x")

    def _create_pages(self):
        """Create all pages"""
        self.pages['home'] = HomePage(self.page_container, app=self)
        self.pages['members'] = MembersPage(self.page_container, app=self)
        self.pages['add_member'] = AddMemberPage(self.page_container, app=self)
        self.pages['sync'] = SyncPage(self.page_container, app=self)
        self.pages['commands'] = CommandsPage(self.page_container, app=self)
        self.pages['settings'] = SettingsPage(self.page_container, app=self)

    def show_page(self, page_id: str):
        """Show a specific page"""
        # Hide current page
        if self.current_page and self.current_page in self.pages:
            self.pages[self.current_page].pack_forget()

        # Show new page
        if page_id in self.pages:
            self.pages[page_id].pack(fill="both", expand=True)
            self.current_page = page_id
            self.sidebar.set_active(page_id)

    def navigate_to(self, page_id: str):
        """Navigate to a page (alias for show_page)"""
        self.show_page(page_id)

    # =====================
    # App Controller Methods
    # =====================

    def sync_now(self):
        """Trigger manual sync"""
        if self.app_controller:
            self.app_controller.sync_now()

    def toggle_auto_sync(self, enabled: bool):
        """Toggle auto sync"""
        if self.app_controller:
            self.app_controller.toggle_auto_sync(enabled)

    def add_member(self, data: dict) -> tuple:
        """Add a new member"""
        if self.app_controller:
            return self.app_controller.add_member(data)
        return False, "النظام غير متصل"

    def get_members(self) -> list:
        """Get all members"""
        if self.app_controller:
            return self.app_controller.get_members()
        return []

    def block_member(self, emp_id: str) -> tuple:
        """Block a member"""
        if self.app_controller:
            return self.app_controller.block_member(emp_id)
        return False, "النظام غير متصل"

    def unblock_member(self, emp_id: str) -> tuple:
        """Unblock a member"""
        if self.app_controller:
            return self.app_controller.unblock_member(emp_id)
        return False, "النظام غير متصل"

    def get_pending_commands(self) -> list:
        """Get pending commands"""
        if self.app_controller:
            return self.app_controller.get_pending_commands()
        return []

    def execute_command(self, command: dict) -> bool:
        """Execute a command"""
        if self.app_controller:
            return self.app_controller.execute_command(command)
        return False

    def find_database(self) -> str:
        """Find database file"""
        if self.app_controller:
            return self.app_controller.find_database()
        return None

    def save_settings(self, settings: dict) -> bool:
        """Save settings"""
        if self.app_controller:
            return self.app_controller.save_settings(settings)
        return False

    # =====================
    # UI Update Methods
    # =====================

    def update_dashboard_stats(self, stats: dict):
        """Update dashboard statistics"""
        if 'home' in self.pages:
            self.pages['home'].update_stats(stats)

    def add_activity(self, message: str, activity_type: str = 'info'):
        """Add activity to dashboard log"""
        if 'home' in self.pages:
            self.pages['home'].add_activity(message, activity_type)

    def update_sync_status(self, status: str, status_type: str = 'info'):
        """Update status bar"""
        self.status_bar.set_status(status, status_type)

    def update_sync_progress(self, message: str, progress: float):
        """Update sync progress"""
        self.status_bar.set_syncing(message, progress)

    def set_sync_complete(self, last_sync_time: str = None):
        """Set sync complete status"""
        self.status_bar.set_sync_complete(last_sync_time)

    def set_error_status(self, message: str):
        """Set error status"""
        self.status_bar.set_error(message)

    def update_database_status(self, connected: bool, path: str = None):
        """Update database status on sync page"""
        if 'sync' in self.pages:
            self.pages['sync'].update_database_status(connected, path)

    def update_api_status(self, connected: bool, url: str = None):
        """Update API status on sync page"""
        if 'sync' in self.pages:
            self.pages['sync'].update_api_status(connected, url)

    def add_sync_log(self, message: str, log_type: str = 'info'):
        """Add entry to sync log"""
        if 'sync' in self.pages:
            self.pages['sync'].add_log_entry(message, log_type)

    def load_settings(self, settings: dict):
        """Load settings into settings page"""
        if 'settings' in self.pages:
            self.pages['settings'].load_settings(settings)

    def set_members(self, members: list):
        """Set members list"""
        if 'members' in self.pages:
            self.pages['members'].set_members(members)

    def set_commands(self, commands: list):
        """Set commands list"""
        if 'commands' in self.pages:
            self.pages['commands'].set_commands(commands)
