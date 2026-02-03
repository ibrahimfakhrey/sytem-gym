"""
Card components for dashboard
"""

import customtkinter as ctk
from ..styles import COLORS, FONTS
from datetime import datetime


class StatusCard(ctk.CTkFrame):
    """Status card for dashboard"""

    def __init__(self, parent, title: str, value: str, icon: str = "📊",
                 color: str = None):
        super().__init__(parent, fg_color=COLORS['card_bg'], corner_radius=10)

        self.title = title
        self.value = value
        self.icon = icon
        self.color = color or COLORS['accent']

        self._create_widgets()

    def _create_widgets(self):
        # Icon
        icon_label = ctk.CTkLabel(
            self,
            text=self.icon,
            font=('Arial', 32)
        )
        icon_label.pack(pady=(15, 5))

        # Value
        self.value_label = ctk.CTkLabel(
            self,
            text=self.value,
            font=FONTS['heading'],
            text_color=self.color
        )
        self.value_label.pack()

        # Title
        title_label = ctk.CTkLabel(
            self,
            text=self.title,
            font=FONTS['small'],
            text_color=COLORS['text_secondary']
        )
        title_label.pack(pady=(0, 15))

    def set_value(self, value: str):
        """Update card value"""
        self.value = value
        self.value_label.configure(text=value)

    def set_color(self, color: str):
        """Update value color"""
        self.color = color
        self.value_label.configure(text_color=color)


class ActivityLog(ctk.CTkFrame):
    """Activity log component"""

    def __init__(self, parent, max_items: int = 10):
        super().__init__(parent, fg_color=COLORS['card_bg'], corner_radius=10)

        self.max_items = max_items
        self.items = []

        self._create_widgets()

    def _create_widgets(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="📋 آخر النشاطات",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary'],
            anchor="e"
        )
        header.pack(fill="x", padx=15, pady=10)

        # Scrollable frame for items
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            height=200
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Empty state
        self.empty_label = ctk.CTkLabel(
            self.scroll_frame,
            text="لا توجد نشاطات",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.empty_label.pack(pady=20)

    def add_item(self, message: str, item_type: str = 'info'):
        """Add new activity item"""
        # Remove empty label if exists
        if self.empty_label.winfo_exists():
            self.empty_label.destroy()

        # Get icon based on type
        icons = {
            'success': '✅',
            'error': '❌',
            'warning': '⚠️',
            'info': '🔵',
            'sync': '🔄',
            'add': '➕',
            'block': '🚫',
            'unblock': '✅'
        }
        icon = icons.get(item_type, '🔵')

        # Time
        time_str = datetime.now().strftime('%H:%M')

        # Create item frame
        item_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        item_frame.pack(fill="x", pady=2)

        # Time label
        time_label = ctk.CTkLabel(
            item_frame,
            text=time_str,
            font=FONTS['small'],
            text_color=COLORS['text_secondary'],
            width=50
        )
        time_label.pack(side="right", padx=5)

        # Message
        msg_label = ctk.CTkLabel(
            item_frame,
            text=f"{icon} {message}",
            font=FONTS['small'],
            text_color=COLORS['text_primary'],
            anchor="e"
        )
        msg_label.pack(side="right", fill="x", expand=True)

        # Store and limit items
        self.items.insert(0, item_frame)

        if len(self.items) > self.max_items:
            old_item = self.items.pop()
            old_item.destroy()

    def clear(self):
        """Clear all items"""
        for item in self.items:
            item.destroy()
        self.items = []

        self.empty_label = ctk.CTkLabel(
            self.scroll_frame,
            text="لا توجد نشاطات",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.empty_label.pack(pady=20)
