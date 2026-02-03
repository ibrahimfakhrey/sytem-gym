"""
Commands queue page - shows pending commands from web app
"""

import customtkinter as ctk
from ..styles import COLORS, FONTS
from datetime import datetime


class CommandsPage(ctk.CTkFrame):
    """Page for viewing pending commands from web app"""

    def __init__(self, parent, app=None):
        super().__init__(parent, fg_color=COLORS['background'])
        self.app = app

        self.commands_list = []
        self.command_frames = []

        self._create_widgets()

    def _create_widgets(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=20)

        header = ctk.CTkLabel(
            header_frame,
            text="📋 الأوامر المعلقة",
            font=FONTS['title'],
            text_color=COLORS['text_primary']
        )
        header.pack(side="right")

        # Refresh button
        refresh_btn = ctk.CTkButton(
            header_frame,
            text="🔄 تحديث",
            font=FONTS['button'],
            fg_color=COLORS['primary'],
            hover_color=COLORS['secondary'],
            width=100,
            height=35,
            command=self._refresh_commands
        )
        refresh_btn.pack(side="left")

        # Info card
        info_card = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=10)
        info_card.pack(fill="x", padx=20, pady=10)

        info_label = ctk.CTkLabel(
            info_card,
            text="الأوامر المرسلة من تطبيق الويب تظهر هنا. يتم تنفيذها تلقائياً أثناء المزامنة.",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        info_label.pack(pady=15, padx=15)

        # Commands count
        self.count_label = ctk.CTkLabel(
            self,
            text="الأوامر المعلقة: 0",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary']
        )
        self.count_label.pack(pady=10)

        # Commands list
        list_frame = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=10)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.scroll_frame = ctk.CTkScrollableFrame(
            list_frame,
            fg_color="transparent"
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Empty state
        self.empty_label = ctk.CTkLabel(
            self.scroll_frame,
            text="لا توجد أوامر معلقة",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.empty_label.pack(pady=50)

    def _refresh_commands(self):
        """Refresh commands from API"""
        if self.app and hasattr(self.app, 'get_pending_commands'):
            self.commands_list = self.app.get_pending_commands()
            self._render_commands()

    def _render_commands(self):
        """Render commands list"""
        # Clear existing
        for frame in self.command_frames:
            frame.destroy()
        self.command_frames = []

        if self.commands_list:
            if self.empty_label.winfo_exists():
                self.empty_label.pack_forget()

            for cmd in self.commands_list:
                frame = self._create_command_card(cmd)
                self.command_frames.append(frame)
        else:
            if not self.empty_label.winfo_ismapped():
                self.empty_label.pack(pady=50)

        self.count_label.configure(text=f"الأوامر المعلقة: {len(self.commands_list)}")

    def _create_command_card(self, command: dict):
        """Create a card for a command"""
        card = ctk.CTkFrame(self.scroll_frame, fg_color=COLORS['input_bg'], corner_radius=8)
        card.pack(fill="x", pady=5)

        # Command type icons
        type_icons = {
            'block_member': '🚫',
            'unblock_member': '✅',
            'add_member': '➕',
            'update_member': '✏️',
            'delete_member': '🗑️'
        }

        type_labels = {
            'block_member': 'حظر عضو',
            'unblock_member': 'إلغاء حظر',
            'add_member': 'إضافة عضو',
            'update_member': 'تعديل بيانات',
            'delete_member': 'حذف عضو'
        }

        cmd_type = command.get('command_type', 'unknown')
        icon = type_icons.get(cmd_type, '📋')
        type_label = type_labels.get(cmd_type, cmd_type)

        # Header row
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=10)

        type_lbl = ctk.CTkLabel(
            header_frame,
            text=f"{icon} {type_label}",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary']
        )
        type_lbl.pack(side="right")

        # Status badge
        status = command.get('status', 'pending')
        status_colors = {
            'pending': COLORS['warning'],
            'processing': COLORS['accent'],
            'completed': COLORS['success'],
            'failed': COLORS['error']
        }
        status_labels = {
            'pending': 'معلق',
            'processing': 'جاري التنفيذ',
            'completed': 'مكتمل',
            'failed': 'فشل'
        }

        status_badge = ctk.CTkLabel(
            header_frame,
            text=status_labels.get(status, status),
            font=FONTS['small'],
            text_color=status_colors.get(status, COLORS['text_secondary']),
            fg_color=COLORS['card_bg'],
            corner_radius=5,
            padx=10,
            pady=5
        )
        status_badge.pack(side="left")

        # Details
        details_frame = ctk.CTkFrame(card, fg_color="transparent")
        details_frame.pack(fill="x", padx=15, pady=(0, 10))

        target_emp = command.get('target_emp_id', '--')
        created_at = command.get('created_at', '--')

        details_text = f"رقم العضوية: {target_emp}  |  تاريخ الإنشاء: {created_at}"

        details_lbl = ctk.CTkLabel(
            details_frame,
            text=details_text,
            font=FONTS['small'],
            text_color=COLORS['text_secondary'],
            anchor="e"
        )
        details_lbl.pack(fill="x")

        # Manual execute button (for pending commands)
        if status == 'pending':
            exec_btn = ctk.CTkButton(
                card,
                text="▶️ تنفيذ الآن",
                font=FONTS['small'],
                fg_color=COLORS['primary'],
                hover_color=COLORS['secondary'],
                height=30,
                width=100,
                command=lambda c=command: self._execute_command(c)
            )
            exec_btn.pack(pady=10)

        return card

    def _execute_command(self, command: dict):
        """Execute a single command"""
        if self.app and hasattr(self.app, 'execute_command'):
            success = self.app.execute_command(command)
            if success:
                self._refresh_commands()

    def set_commands(self, commands: list):
        """Set commands list externally"""
        self.commands_list = commands
        self._render_commands()
