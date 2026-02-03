"""
Sync status page
"""

import customtkinter as ctk
from ..styles import COLORS, FONTS
from datetime import datetime


class SyncPage(ctk.CTkFrame):
    """Page for sync status and controls"""

    def __init__(self, parent, app=None):
        super().__init__(parent, fg_color=COLORS['background'])
        self.app = app

        self._create_widgets()

    def _create_widgets(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="🔄 المزامنة",
            font=FONTS['title'],
            text_color=COLORS['text_primary']
        )
        header.pack(pady=20)

        # Main content frame
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20)

        # Connection status card
        status_card = ctk.CTkFrame(content_frame, fg_color=COLORS['card_bg'], corner_radius=10)
        status_card.pack(fill="x", pady=10)

        status_header = ctk.CTkLabel(
            status_card,
            text="حالة الاتصال",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary']
        )
        status_header.pack(pady=15)

        # Status indicators frame
        indicators_frame = ctk.CTkFrame(status_card, fg_color="transparent")
        indicators_frame.pack(fill="x", padx=20, pady=10)

        # Database status
        db_frame = ctk.CTkFrame(indicators_frame, fg_color=COLORS['input_bg'], corner_radius=8)
        db_frame.pack(fill="x", pady=5)

        self.db_status = ctk.CTkLabel(
            db_frame,
            text="🔴 قاعدة البيانات المحلية: غير متصل",
            font=FONTS['body'],
            text_color=COLORS['error']
        )
        self.db_status.pack(pady=10, padx=15, anchor="e")

        # API status
        api_frame = ctk.CTkFrame(indicators_frame, fg_color=COLORS['input_bg'], corner_radius=8)
        api_frame.pack(fill="x", pady=5)

        self.api_status = ctk.CTkLabel(
            api_frame,
            text="🔴 تطبيق الويب: غير متصل",
            font=FONTS['body'],
            text_color=COLORS['error']
        )
        self.api_status.pack(pady=10, padx=15, anchor="e")

        # Last sync info
        sync_info_frame = ctk.CTkFrame(status_card, fg_color="transparent")
        sync_info_frame.pack(fill="x", padx=20, pady=15)

        self.last_sync_label = ctk.CTkLabel(
            sync_info_frame,
            text="آخر مزامنة: لم تتم بعد",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.last_sync_label.pack(anchor="e")

        self.next_sync_label = ctk.CTkLabel(
            sync_info_frame,
            text="المزامنة التالية: --",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.next_sync_label.pack(anchor="e")

        # Sync controls card
        controls_card = ctk.CTkFrame(content_frame, fg_color=COLORS['card_bg'], corner_radius=10)
        controls_card.pack(fill="x", pady=10)

        controls_header = ctk.CTkLabel(
            controls_card,
            text="التحكم في المزامنة",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary']
        )
        controls_header.pack(pady=15)

        # Control buttons
        buttons_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        buttons_frame.pack(pady=15)

        sync_now_btn = ctk.CTkButton(
            buttons_frame,
            text="🔄 مزامنة الآن",
            font=FONTS['button'],
            fg_color=COLORS['primary'],
            hover_color=COLORS['secondary'],
            height=45,
            width=180,
            command=self._on_sync_now
        )
        sync_now_btn.pack(side="right", padx=10)

        # Auto-sync toggle
        auto_sync_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        auto_sync_frame.pack(fill="x", padx=20, pady=10)

        self.auto_sync_var = ctk.BooleanVar(value=True)
        auto_sync_switch = ctk.CTkSwitch(
            auto_sync_frame,
            text="المزامنة التلقائية (كل 30 ثانية)",
            font=FONTS['body'],
            text_color=COLORS['text_primary'],
            variable=self.auto_sync_var,
            command=self._toggle_auto_sync
        )
        auto_sync_switch.pack(anchor="e")

        # Sync log card
        log_card = ctk.CTkFrame(content_frame, fg_color=COLORS['card_bg'], corner_radius=10)
        log_card.pack(fill="both", expand=True, pady=10)

        log_header = ctk.CTkLabel(
            log_card,
            text="📋 سجل المزامنة",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary']
        )
        log_header.pack(pady=15)

        # Log list
        self.log_frame = ctk.CTkScrollableFrame(
            log_card,
            fg_color="transparent",
            height=200
        )
        self.log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Empty log message
        self.empty_log = ctk.CTkLabel(
            self.log_frame,
            text="لا توجد سجلات مزامنة",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.empty_log.pack(pady=20)

        self.log_items = []

    def _on_sync_now(self):
        """Trigger manual sync"""
        if self.app and hasattr(self.app, 'sync_now'):
            self.app.sync_now()

    def _toggle_auto_sync(self):
        """Toggle auto sync"""
        if self.app and hasattr(self.app, 'toggle_auto_sync'):
            self.app.toggle_auto_sync(self.auto_sync_var.get())

    def update_database_status(self, connected: bool, path: str = None):
        """Update database connection status"""
        if connected:
            text = f"🟢 قاعدة البيانات المحلية: متصل"
            if path:
                text += f"\n     {path}"
            self.db_status.configure(text=text, text_color=COLORS['success'])
        else:
            self.db_status.configure(
                text="🔴 قاعدة البيانات المحلية: غير متصل",
                text_color=COLORS['error']
            )

    def update_api_status(self, connected: bool, url: str = None):
        """Update API connection status"""
        if connected:
            text = f"🟢 تطبيق الويب: متصل"
            if url:
                text += f"\n     {url}"
            self.api_status.configure(text=text, text_color=COLORS['success'])
        else:
            self.api_status.configure(
                text="🔴 تطبيق الويب: غير متصل",
                text_color=COLORS['error']
            )

    def update_sync_times(self, last_sync: str = None, next_sync: str = None):
        """Update sync time labels"""
        if last_sync:
            self.last_sync_label.configure(text=f"آخر مزامنة: {last_sync}")
        if next_sync:
            self.next_sync_label.configure(text=f"المزامنة التالية: {next_sync}")

    def add_log_entry(self, message: str, log_type: str = 'info'):
        """Add entry to sync log"""
        # Remove empty message if exists
        if self.empty_log.winfo_exists() and self.empty_log.winfo_ismapped():
            self.empty_log.pack_forget()

        # Get icon and color
        icons = {
            'success': ('✅', COLORS['success']),
            'error': ('❌', COLORS['error']),
            'warning': ('⚠️', COLORS['warning']),
            'info': ('🔵', COLORS['accent']),
            'sync': ('🔄', COLORS['accent'])
        }
        icon, color = icons.get(log_type, ('🔵', COLORS['accent']))

        # Create log entry
        entry_frame = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        entry_frame.pack(fill="x", pady=2, anchor="e")

        time_str = datetime.now().strftime('%H:%M:%S')

        time_label = ctk.CTkLabel(
            entry_frame,
            text=time_str,
            font=FONTS['small'],
            text_color=COLORS['text_secondary'],
            width=60
        )
        time_label.pack(side="right")

        msg_label = ctk.CTkLabel(
            entry_frame,
            text=f"{icon} {message}",
            font=FONTS['small'],
            text_color=color,
            anchor="e"
        )
        msg_label.pack(side="right", fill="x", expand=True)

        self.log_items.insert(0, entry_frame)

        # Limit log entries
        if len(self.log_items) > 50:
            old = self.log_items.pop()
            old.destroy()

    def clear_log(self):
        """Clear sync log"""
        for item in self.log_items:
            item.destroy()
        self.log_items = []

        self.empty_log = ctk.CTkLabel(
            self.log_frame,
            text="لا توجد سجلات مزامنة",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.empty_log.pack(pady=20)
