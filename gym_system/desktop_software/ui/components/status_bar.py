"""
Status bar component (bottom of window)
"""

import customtkinter as ctk
from ..styles import COLORS, FONTS


class StatusBar(ctk.CTkFrame):
    """Bottom status bar showing sync status"""

    def __init__(self, parent):
        super().__init__(parent, fg_color=COLORS['card_bg'], height=40)
        self.pack_propagate(False)

        self.status_label = None
        self.progress_bar = None
        self.time_label = None

        self._create_widgets()

    def _create_widgets(self):
        # Status icon and text
        self.status_label = ctk.CTkLabel(
            self,
            text="🟢 متصل",
            font=FONTS['small'],
            text_color=COLORS['success']
        )
        self.status_label.pack(side="right", padx=15)

        # Progress bar (hidden by default)
        self.progress_bar = ctk.CTkProgressBar(
            self,
            width=200,
            height=10,
            progress_color=COLORS['accent']
        )
        self.progress_bar.set(0)
        # Don't pack initially

        # Last sync time
        self.time_label = ctk.CTkLabel(
            self,
            text="آخر مزامنة: --:--:--",
            font=FONTS['small'],
            text_color=COLORS['text_secondary']
        )
        self.time_label.pack(side="left", padx=15)

    def set_status(self, status: str, status_type: str = 'success'):
        """Set status text and color"""
        colors = {
            'success': COLORS['success'],
            'warning': COLORS['warning'],
            'error': COLORS['error'],
            'info': COLORS['accent']
        }
        icons = {
            'success': '🟢',
            'warning': '🟡',
            'error': '🔴',
            'info': '🔵'
        }

        color = colors.get(status_type, COLORS['text_primary'])
        icon = icons.get(status_type, '⚪')

        self.status_label.configure(text=f"{icon} {status}", text_color=color)

    def set_syncing(self, message: str, progress: float = 0):
        """Show syncing status with progress"""
        self.status_label.configure(
            text=f"🔄 {message}",
            text_color=COLORS['accent']
        )

        if not self.progress_bar.winfo_ismapped():
            self.progress_bar.pack(side="right", padx=10)

        self.progress_bar.set(progress / 100)

    def set_sync_complete(self, last_sync_time: str = None):
        """Show sync complete status"""
        if self.progress_bar.winfo_ismapped():
            self.progress_bar.pack_forget()

        self.set_status("متصل", "success")

        if last_sync_time:
            self.time_label.configure(text=f"آخر مزامنة: {last_sync_time}")

    def set_error(self, message: str):
        """Show error status"""
        if self.progress_bar.winfo_ismapped():
            self.progress_bar.pack_forget()

        self.set_status(message, "error")

    def set_last_sync(self, time_str: str):
        """Update last sync time"""
        self.time_label.configure(text=f"آخر مزامنة: {time_str}")
