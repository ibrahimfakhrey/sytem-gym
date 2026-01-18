"""
Sidebar navigation component
"""

import customtkinter as ctk
from ..styles import COLORS, FONTS


class Sidebar(ctk.CTkFrame):
    """Sidebar navigation"""

    def __init__(self, parent, on_navigate=None):
        super().__init__(parent, fg_color=COLORS['sidebar_bg'], width=200)
        self.on_navigate = on_navigate
        self.current_page = 'home'
        self.buttons = {}

        self.pack_propagate(False)
        self._create_widgets()

    def _create_widgets(self):
        # Logo/Title
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", pady=20, padx=10)

        title = ctk.CTkLabel(
            title_frame,
            text="🏋️ نظام الجيم",
            font=FONTS['heading'],
            text_color=COLORS['text_primary']
        )
        title.pack()

        # Navigation items
        nav_items = [
            ('home', '🏠', 'الرئيسية'),
            ('members', '👥', 'الأعضاء'),
            ('add_member', '➕', 'إضافة عضو'),
            ('sync', '🔄', 'المزامنة'),
            ('commands', '📋', 'الأوامر'),
            ('settings', '⚙️', 'الإعدادات'),
        ]

        for page_id, icon, label in nav_items:
            self._create_nav_button(page_id, icon, label)

    def _create_nav_button(self, page_id: str, icon: str, label: str):
        btn = ctk.CTkButton(
            self,
            text=f"  {icon}  {label}",
            font=FONTS['body'],
            fg_color="transparent" if page_id != self.current_page else COLORS['primary'],
            hover_color=COLORS['hover'],
            text_color=COLORS['text_primary'],
            anchor="e",
            height=45,
            corner_radius=8,
            command=lambda p=page_id: self._on_click(p)
        )
        btn.pack(fill="x", padx=10, pady=2)
        self.buttons[page_id] = btn

    def _on_click(self, page_id: str):
        # Update button styles
        for pid, btn in self.buttons.items():
            if pid == page_id:
                btn.configure(fg_color=COLORS['primary'])
            else:
                btn.configure(fg_color="transparent")

        self.current_page = page_id

        if self.on_navigate:
            self.on_navigate(page_id)

    def set_active(self, page_id: str):
        """Set active page"""
        self._on_click(page_id)
