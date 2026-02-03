"""
Home/Dashboard page
"""

import customtkinter as ctk
from ..styles import COLORS, FONTS
from ..components import StatusCard, ActivityLog


class HomePage(ctk.CTkFrame):
    """Main dashboard page"""

    def __init__(self, parent, app=None):
        super().__init__(parent, fg_color=COLORS['background'])
        self.app = app

        self.status_cards = {}
        self.activity_log = None

        self._create_widgets()

    def _create_widgets(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="لوحة التحكم",
            font=FONTS['title'],
            text_color=COLORS['text_primary']
        )
        header.pack(pady=20)

        # Status cards container
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.pack(fill="x", padx=20, pady=10)

        # Configure grid
        for i in range(4):
            cards_frame.columnconfigure(i, weight=1)

        # Status cards
        cards_data = [
            ('total_members', 'إجمالي الأعضاء', '0', '👥', COLORS['accent']),
            ('active_members', 'الأعضاء النشطين', '0', '✅', COLORS['success']),
            ('blocked_members', 'الأعضاء المحظورين', '0', '🚫', COLORS['error']),
            ('last_sync', 'آخر مزامنة', '--:--', '🔄', COLORS['warning']),
        ]

        for idx, (card_id, title, value, icon, color) in enumerate(cards_data):
            card = StatusCard(cards_frame, title=title, value=value, icon=icon, color=color)
            card.grid(row=0, column=3-idx, padx=10, pady=10, sticky="nsew")
            self.status_cards[card_id] = card

        # Activity log
        log_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.activity_log = ActivityLog(log_frame, max_items=15)
        self.activity_log.pack(fill="both", expand=True)

        # Quick actions
        actions_frame = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=10)
        actions_frame.pack(fill="x", padx=20, pady=10)

        actions_label = ctk.CTkLabel(
            actions_frame,
            text="إجراءات سريعة",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary']
        )
        actions_label.pack(pady=10)

        buttons_frame = ctk.CTkFrame(actions_frame, fg_color="transparent")
        buttons_frame.pack(pady=10)

        # Quick action buttons
        sync_btn = ctk.CTkButton(
            buttons_frame,
            text="🔄 مزامنة الآن",
            font=FONTS['button'],
            fg_color=COLORS['primary'],
            hover_color=COLORS['secondary'],
            height=40,
            width=150,
            command=self._on_sync_now
        )
        sync_btn.pack(side="right", padx=10)

        add_btn = ctk.CTkButton(
            buttons_frame,
            text="➕ إضافة عضو",
            font=FONTS['button'],
            fg_color=COLORS['success'],
            hover_color='#388e3c',
            height=40,
            width=150,
            command=self._on_add_member
        )
        add_btn.pack(side="right", padx=10)

    def _on_sync_now(self):
        """Trigger manual sync"""
        if self.app and hasattr(self.app, 'sync_now'):
            self.app.sync_now()

    def _on_add_member(self):
        """Navigate to add member page"""
        if self.app and hasattr(self.app, 'navigate_to'):
            self.app.navigate_to('add_member')

    def update_stats(self, stats: dict):
        """Update dashboard statistics"""
        if 'total_members' in stats:
            self.status_cards['total_members'].set_value(str(stats['total_members']))
        if 'active_members' in stats:
            self.status_cards['active_members'].set_value(str(stats['active_members']))
        if 'blocked_members' in stats:
            self.status_cards['blocked_members'].set_value(str(stats['blocked_members']))
        if 'last_sync' in stats:
            self.status_cards['last_sync'].set_value(stats['last_sync'])

    def add_activity(self, message: str, activity_type: str = 'info'):
        """Add activity to log"""
        if self.activity_log:
            self.activity_log.add_item(message, activity_type)
