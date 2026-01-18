"""
Members list page
"""

import customtkinter as ctk
from ..styles import COLORS, FONTS
from datetime import datetime


class MembersPage(ctk.CTkFrame):
    """Page for viewing and managing members"""

    def __init__(self, parent, app=None):
        super().__init__(parent, fg_color=COLORS['background'])
        self.app = app

        self.members_list = []
        self.filtered_list = []
        self.member_frames = []

        self._create_widgets()

    def _create_widgets(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=20)

        header = ctk.CTkLabel(
            header_frame,
            text="👥 قائمة الأعضاء",
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
            command=self._refresh_members
        )
        refresh_btn.pack(side="left")

        # Search and filter bar
        filter_frame = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=10)
        filter_frame.pack(fill="x", padx=20, pady=10)

        # Search entry
        search_frame = ctk.CTkFrame(filter_frame, fg_color="transparent")
        search_frame.pack(fill="x", padx=15, pady=10)

        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="🔍 بحث بالاسم أو الرقم...",
            font=FONTS['body'],
            fg_color=COLORS['input_bg'],
            text_color=COLORS['text_primary'],
            border_color=COLORS['border'],
            height=40,
            width=300
        )
        self.search_entry.pack(side="right", padx=5)
        self.search_entry.bind('<KeyRelease>', self._on_search)

        # Filter buttons
        self.filter_var = ctk.StringVar(value="all")

        filters = [
            ('all', 'الكل'),
            ('active', 'النشطين'),
            ('blocked', 'المحظورين'),
            ('employees', 'الموظفين'),
        ]

        for value, label in filters:
            btn = ctk.CTkRadioButton(
                search_frame,
                text=label,
                variable=self.filter_var,
                value=value,
                font=FONTS['body'],
                text_color=COLORS['text_primary'],
                command=self._apply_filter
            )
            btn.pack(side="right", padx=15)

        # Members count
        self.count_label = ctk.CTkLabel(
            filter_frame,
            text="عدد الأعضاء: 0",
            font=FONTS['small'],
            text_color=COLORS['text_secondary']
        )
        self.count_label.pack(pady=5)

        # Members list container
        list_frame = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=10)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Scrollable members list
        self.scroll_frame = ctk.CTkScrollableFrame(
            list_frame,
            fg_color="transparent"
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Table header
        self._create_table_header()

        # Empty state
        self.empty_label = ctk.CTkLabel(
            self.scroll_frame,
            text="لا يوجد أعضاء للعرض\nاضغط على 'تحديث' لتحميل البيانات",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.empty_label.pack(pady=50)

    def _create_table_header(self):
        """Create table header"""
        header = ctk.CTkFrame(self.scroll_frame, fg_color=COLORS['secondary'], corner_radius=5)
        header.pack(fill="x", pady=(0, 5))

        columns = [
            ('الإجراءات', 120),
            ('الحالة', 80),
            ('تاريخ الانتهاء', 100),
            ('الهاتف', 100),
            ('الاسم', 200),
            ('الرقم', 80),
        ]

        for col_name, width in columns:
            lbl = ctk.CTkLabel(
                header,
                text=col_name,
                font=FONTS['subheading'],
                text_color=COLORS['text_primary'],
                width=width
            )
            lbl.pack(side="right", padx=5, pady=8)

    def _create_member_row(self, member: dict):
        """Create a row for a member"""
        row = ctk.CTkFrame(self.scroll_frame, fg_color=COLORS['input_bg'], corner_radius=5)
        row.pack(fill="x", pady=2)

        # Determine status
        is_blocked = False
        status_text = "نشط"
        status_color = COLORS['success']

        if member.get('end_date'):
            try:
                end_date = datetime.strptime(member['end_date'], '%Y-%m-%d')
                if end_date < datetime.now():
                    is_blocked = True
                    status_text = "محظور"
                    status_color = COLORS['error']
            except:
                pass

        # Actions
        actions_frame = ctk.CTkFrame(row, fg_color="transparent", width=120)
        actions_frame.pack(side="right", padx=5, pady=5)
        actions_frame.pack_propagate(False)

        if is_blocked:
            unblock_btn = ctk.CTkButton(
                actions_frame,
                text="✅",
                font=FONTS['small'],
                fg_color=COLORS['success'],
                hover_color='#388e3c',
                width=35,
                height=25,
                command=lambda m=member: self._unblock_member(m)
            )
            unblock_btn.pack(side="right", padx=2)
        else:
            block_btn = ctk.CTkButton(
                actions_frame,
                text="🚫",
                font=FONTS['small'],
                fg_color=COLORS['error'],
                hover_color='#c62828',
                width=35,
                height=25,
                command=lambda m=member: self._block_member(m)
            )
            block_btn.pack(side="right", padx=2)

        # Status
        status_lbl = ctk.CTkLabel(
            row,
            text=status_text,
            font=FONTS['body'],
            text_color=status_color,
            width=80
        )
        status_lbl.pack(side="right", padx=5)

        # End date
        end_date_str = member.get('end_date', '--')
        end_date_lbl = ctk.CTkLabel(
            row,
            text=end_date_str,
            font=FONTS['body'],
            text_color=COLORS['text_primary'],
            width=100
        )
        end_date_lbl.pack(side="right", padx=5)

        # Phone
        phone = member.get('phone_code', '--') or '--'
        phone_lbl = ctk.CTkLabel(
            row,
            text=phone,
            font=FONTS['body'],
            text_color=COLORS['text_primary'],
            width=100
        )
        phone_lbl.pack(side="right", padx=5)

        # Name
        name_lbl = ctk.CTkLabel(
            row,
            text=member.get('emp_name', 'غير معروف'),
            font=FONTS['body'],
            text_color=COLORS['text_primary'],
            width=200,
            anchor="e"
        )
        name_lbl.pack(side="right", padx=5)

        # ID
        id_lbl = ctk.CTkLabel(
            row,
            text=member.get('emp_id', '--'),
            font=FONTS['body'],
            text_color=COLORS['text_secondary'],
            width=80
        )
        id_lbl.pack(side="right", padx=5)

        return row

    def _refresh_members(self):
        """Refresh members list from database"""
        if self.app and hasattr(self.app, 'get_members'):
            self.members_list = self.app.get_members()
            self._apply_filter()

    def _on_search(self, event=None):
        """Handle search input"""
        self._apply_filter()

    def _apply_filter(self):
        """Apply filter and search to members list"""
        search_text = self.search_entry.get().strip().lower()
        filter_value = self.filter_var.get()

        self.filtered_list = []

        for member in self.members_list:
            # Apply search filter
            if search_text:
                name = (member.get('emp_name') or '').lower()
                emp_id = (member.get('emp_id') or '').lower()
                if search_text not in name and search_text not in emp_id:
                    continue

            # Apply status filter
            is_blocked = False
            if member.get('end_date'):
                try:
                    end_date = datetime.strptime(member['end_date'], '%Y-%m-%d')
                    is_blocked = end_date < datetime.now()
                except:
                    pass

            if filter_value == 'active' and is_blocked:
                continue
            elif filter_value == 'blocked' and not is_blocked:
                continue
            elif filter_value == 'employees':
                # For now, show all - can be enhanced with member_type field
                pass

            self.filtered_list.append(member)

        self._render_members()

    def _render_members(self):
        """Render the filtered members list"""
        # Clear existing rows
        for frame in self.member_frames:
            frame.destroy()
        self.member_frames = []

        # Hide/show empty label
        if self.filtered_list:
            if self.empty_label.winfo_exists():
                self.empty_label.pack_forget()

            for member in self.filtered_list:
                row = self._create_member_row(member)
                self.member_frames.append(row)
        else:
            if not self.empty_label.winfo_ismapped():
                self.empty_label.pack(pady=50)

        # Update count
        self.count_label.configure(text=f"عدد الأعضاء: {len(self.filtered_list)}")

    def _block_member(self, member: dict):
        """Block a member"""
        if self.app and hasattr(self.app, 'block_member'):
            success, message = self.app.block_member(member['emp_id'])
            if success:
                self._refresh_members()

    def _unblock_member(self, member: dict):
        """Unblock a member"""
        if self.app and hasattr(self.app, 'unblock_member'):
            success, message = self.app.unblock_member(member['emp_id'])
            if success:
                self._refresh_members()

    def set_members(self, members: list):
        """Set members list externally"""
        self.members_list = members
        self._apply_filter()
