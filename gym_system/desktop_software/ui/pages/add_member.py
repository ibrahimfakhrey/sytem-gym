"""
Add Member page
"""

import customtkinter as ctk
from ..styles import COLORS, FONTS
from datetime import datetime, timedelta


class AddMemberPage(ctk.CTkFrame):
    """Page for adding new members"""

    def __init__(self, parent, app=None):
        super().__init__(parent, fg_color=COLORS['background'])
        self.app = app

        self.form_fields = {}
        self._create_widgets()

    def _create_widgets(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="➕ إضافة عضو جديد",
            font=FONTS['title'],
            text_color=COLORS['text_primary']
        )
        header.pack(pady=20)

        # Form container
        form_frame = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=10)
        form_frame.pack(fill="both", expand=True, padx=40, pady=10)

        # Scrollable form
        scroll_frame = ctk.CTkScrollableFrame(form_frame, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Form fields
        fields = [
            ('emp_id', 'رقم العضوية *', 'text'),
            ('emp_name', 'الاسم الكامل *', 'text'),
            ('phone_code', 'رقم الهاتف', 'text'),
            ('end_date', 'تاريخ انتهاء الاشتراك *', 'date'),
        ]

        for field_id, label, field_type in fields:
            self._create_form_field(scroll_frame, field_id, label, field_type)

        # Member type selection
        type_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        type_frame.pack(fill="x", pady=10)

        type_label = ctk.CTkLabel(
            type_frame,
            text="نوع العضوية:",
            font=FONTS['body'],
            text_color=COLORS['text_primary']
        )
        type_label.pack(side="right", padx=10)

        self.member_type = ctk.StringVar(value="member")

        member_radio = ctk.CTkRadioButton(
            type_frame,
            text="عضو (مشترك)",
            variable=self.member_type,
            value="member",
            font=FONTS['body'],
            text_color=COLORS['text_primary']
        )
        member_radio.pack(side="right", padx=20)

        employee_radio = ctk.CTkRadioButton(
            type_frame,
            text="موظف",
            variable=self.member_type,
            value="employee",
            font=FONTS['body'],
            text_color=COLORS['text_primary']
        )
        employee_radio.pack(side="right", padx=20)

        # Notes field
        notes_label = ctk.CTkLabel(
            scroll_frame,
            text="ملاحظات:",
            font=FONTS['body'],
            text_color=COLORS['text_primary'],
            anchor="e"
        )
        notes_label.pack(fill="x", pady=(20, 5))

        self.notes_field = ctk.CTkTextbox(
            scroll_frame,
            height=80,
            font=FONTS['body'],
            fg_color=COLORS['input_bg'],
            text_color=COLORS['text_primary'],
            border_color=COLORS['border'],
            border_width=1
        )
        self.notes_field.pack(fill="x", pady=5)
        self.form_fields['notes'] = self.notes_field

        # Buttons
        buttons_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=30)

        save_btn = ctk.CTkButton(
            buttons_frame,
            text="💾 حفظ العضو",
            font=FONTS['button'],
            fg_color=COLORS['success'],
            hover_color='#388e3c',
            height=45,
            width=200,
            command=self._on_save
        )
        save_btn.pack(side="right", padx=10)

        clear_btn = ctk.CTkButton(
            buttons_frame,
            text="🔄 مسح النموذج",
            font=FONTS['button'],
            fg_color=COLORS['secondary'],
            hover_color=COLORS['primary'],
            height=45,
            width=150,
            command=self._clear_form
        )
        clear_btn.pack(side="right", padx=10)

        # Status message
        self.status_label = ctk.CTkLabel(
            form_frame,
            text="",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.status_label.pack(pady=10)

    def _create_form_field(self, parent, field_id: str, label: str, field_type: str):
        """Create a form field"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=10)

        lbl = ctk.CTkLabel(
            frame,
            text=label,
            font=FONTS['body'],
            text_color=COLORS['text_primary'],
            anchor="e"
        )
        lbl.pack(fill="x")

        if field_type == 'date':
            # Date input with default value
            default_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            entry = ctk.CTkEntry(
                frame,
                font=FONTS['body'],
                fg_color=COLORS['input_bg'],
                text_color=COLORS['text_primary'],
                border_color=COLORS['border'],
                height=40,
                placeholder_text="YYYY-MM-DD"
            )
            entry.insert(0, default_date)
        else:
            entry = ctk.CTkEntry(
                frame,
                font=FONTS['body'],
                fg_color=COLORS['input_bg'],
                text_color=COLORS['text_primary'],
                border_color=COLORS['border'],
                height=40
            )

        entry.pack(fill="x", pady=5)
        self.form_fields[field_id] = entry

    def _validate_form(self) -> tuple:
        """Validate form fields"""
        errors = []

        # Check required fields
        emp_id = self.form_fields['emp_id'].get().strip()
        emp_name = self.form_fields['emp_name'].get().strip()
        end_date = self.form_fields['end_date'].get().strip()

        if not emp_id:
            errors.append("رقم العضوية مطلوب")
        if not emp_name:
            errors.append("الاسم مطلوب")
        if not end_date:
            errors.append("تاريخ الانتهاء مطلوب")
        else:
            # Validate date format
            try:
                datetime.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                errors.append("صيغة التاريخ غير صحيحة (استخدم YYYY-MM-DD)")

        return len(errors) == 0, errors

    def _on_save(self):
        """Save member"""
        valid, errors = self._validate_form()

        if not valid:
            self.status_label.configure(
                text="❌ " + " | ".join(errors),
                text_color=COLORS['error']
            )
            return

        # Collect form data
        data = {
            'emp_id': self.form_fields['emp_id'].get().strip(),
            'emp_name': self.form_fields['emp_name'].get().strip(),
            'phone_code': self.form_fields['phone_code'].get().strip(),
            'end_date': self.form_fields['end_date'].get().strip(),
            'member_type': self.member_type.get(),
            'notes': self.notes_field.get("1.0", "end-1c").strip()
        }

        # Show saving status
        self.status_label.configure(
            text="⏳ جاري الحفظ...",
            text_color=COLORS['accent']
        )
        self.update()

        # Save through app
        if self.app and hasattr(self.app, 'add_member'):
            success, message = self.app.add_member(data)
            if success:
                self.status_label.configure(
                    text="✅ " + message,
                    text_color=COLORS['success']
                )
                self._clear_form()
            else:
                self.status_label.configure(
                    text="❌ " + message,
                    text_color=COLORS['error']
                )
        else:
            self.status_label.configure(
                text="❌ خطأ في الاتصال بالنظام",
                text_color=COLORS['error']
            )

    def _clear_form(self):
        """Clear all form fields"""
        for field_id, field in self.form_fields.items():
            if isinstance(field, ctk.CTkEntry):
                field.delete(0, 'end')
                if field_id == 'end_date':
                    default_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                    field.insert(0, default_date)
            elif isinstance(field, ctk.CTkTextbox):
                field.delete("1.0", "end")

        self.member_type.set("member")
        self.status_label.configure(text="")
