"""
Settings Page — DB paths, password, sync interval. Test button.
"""
import customtkinter as ctk
from tkinter import filedialog
import threading

from ..theme import COLORS, FONTS


class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, controller=None, **kwargs):
        super().__init__(parent, fg_color=COLORS['bg'], **kwargs)
        self.controller = controller
        self._build()

    def _build(self):
        # Header
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.pack(fill='x', padx=24, pady=(20, 0))

        ctk.CTkLabel(header, text='⚙ الإعدادات', font=FONTS['h2'],
                     text_color=COLORS['text']).pack(anchor='e')

        # DB paths card
        db_card = ctk.CTkFrame(self, fg_color=COLORS['bg_card'],
                                corner_radius=12, border_width=1,
                                border_color=COLORS['border'])
        db_card.pack(fill='x', padx=24, pady=(20, 0))

        db_inner = ctk.CTkFrame(db_card, fg_color='transparent')
        db_inner.pack(padx=20, pady=16, fill='x')

        ctk.CTkLabel(db_inner, text='📁 قواعد البيانات', font=FONTS['h3'],
                     text_color=COLORS['text']).pack(anchor='e', pady=(0, 12))

        # Members DB
        ctk.CTkLabel(db_inner, text='قاعدة الأعضاء (backup.mdb)',
                     font=FONTS['small'], text_color=COLORS['text_muted']).pack(anchor='e')
        members_row = ctk.CTkFrame(db_inner, fg_color='transparent')
        members_row.pack(fill='x', pady=(4, 12))
        self.members_entry = ctk.CTkEntry(members_row, font=FONTS['small'], height=36)
        self.members_entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        ctk.CTkButton(members_row, text='تصفح', font=FONTS['small'],
                      width=80, height=36,
                      fg_color=COLORS['bg'], hover_color=COLORS['bg_card_hover'],
                      command=lambda: self._browse(self.members_entry)).pack(side='left')

        # Attendance DB
        ctk.CTkLabel(db_inner, text='قاعدة البصمة (att2000.mdb)',
                     font=FONTS['small'], text_color=COLORS['text_muted']).pack(anchor='e')
        att_row = ctk.CTkFrame(db_inner, fg_color='transparent')
        att_row.pack(fill='x', pady=(4, 12))
        self.attendance_entry = ctk.CTkEntry(att_row, font=FONTS['small'], height=36)
        self.attendance_entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        ctk.CTkButton(att_row, text='تصفح', font=FONTS['small'],
                      width=80, height=36,
                      fg_color=COLORS['bg'], hover_color=COLORS['bg_card_hover'],
                      command=lambda: self._browse(self.attendance_entry)).pack(side='left')

        # Password
        ctk.CTkLabel(db_inner, text='كلمة المرور (اختياري)',
                     font=FONTS['small'], text_color=COLORS['text_muted']).pack(anchor='e')
        self.password_entry = ctk.CTkEntry(db_inner, font=FONTS['small'],
                                            height=36, show='*')
        self.password_entry.pack(fill='x', pady=(4, 4))

        # Auto-detect button
        ctk.CTkButton(db_inner, text='🔍 بحث تلقائي عن الملفات',
                      font=FONTS['small'], height=36,
                      fg_color=COLORS['info'], hover_color='#0891b2',
                      command=self._auto_detect).pack(fill='x', pady=(8, 0))

        # Sync settings card
        sync_card = ctk.CTkFrame(self, fg_color=COLORS['bg_card'],
                                  corner_radius=12, border_width=1,
                                  border_color=COLORS['border'])
        sync_card.pack(fill='x', padx=24, pady=(16, 0))

        sync_inner = ctk.CTkFrame(sync_card, fg_color='transparent')
        sync_inner.pack(padx=20, pady=16, fill='x')

        ctk.CTkLabel(sync_inner, text='🔄 المزامنة', font=FONTS['h3'],
                     text_color=COLORS['text']).pack(anchor='e', pady=(0, 12))

        ctk.CTkLabel(sync_inner, text='فترة المزامنة (ثواني)',
                     font=FONTS['small'], text_color=COLORS['text_muted']).pack(anchor='e')
        self.interval_entry = ctk.CTkEntry(sync_inner, font=FONTS['small'], height=36)
        self.interval_entry.pack(fill='x', pady=(4, 12))
        self.interval_entry.insert(0, '60')

        # Test result label
        self.test_label = ctk.CTkLabel(self, text='', font=FONTS['body'],
                                        text_color=COLORS['text_muted'])
        self.test_label.pack(pady=(16, 0))

        # Action buttons
        action_frame = ctk.CTkFrame(self, fg_color='transparent')
        action_frame.pack(fill='x', padx=24, pady=16)

        self.save_btn = ctk.CTkButton(
            action_frame, text='💾 حفظ',
            font=FONTS['btn'], height=44, width=140,
            fg_color=COLORS['success'], hover_color='#059669',
            command=self._on_save,
        )
        self.save_btn.pack(side='right', padx=(0, 8))

        self.test_btn = ctk.CTkButton(
            action_frame, text='🧪 اختبار',
            font=FONTS['btn'], height=44, width=140,
            fg_color=COLORS['info'], hover_color='#0891b2',
            command=self._on_test,
        )
        self.test_btn.pack(side='right', padx=(0, 8))

        self.back_btn = ctk.CTkButton(
            action_frame, text='⬅ رجوع',
            font=FONTS['btn'], height=44, width=120,
            fg_color=COLORS['bg_card'], hover_color=COLORS['bg_card_hover'],
            text_color=COLORS['text'], border_width=1, border_color=COLORS['border'],
            command=self._on_back,
        )
        self.back_btn.pack(side='right')

    def load_config(self, config):
        self.members_entry.delete(0, 'end')
        self.members_entry.insert(0, config.get('db_path_members', ''))
        self.attendance_entry.delete(0, 'end')
        self.attendance_entry.insert(0, config.get('db_path_attendance', ''))
        self.password_entry.delete(0, 'end')
        self.password_entry.insert(0, config.get('db_password', ''))
        self.interval_entry.delete(0, 'end')
        self.interval_entry.insert(0, str(config.get('sync_interval_seconds', 60)))

    def _browse(self, entry):
        path = filedialog.askopenfilename(
            title='اختر ملف قاعدة البيانات',
            filetypes=[('Microsoft Access', '*.mdb *.accdb'), ('All files', '*.*')]
        )
        if path:
            entry.delete(0, 'end')
            entry.insert(0, path)

    def _auto_detect(self):
        self.test_label.configure(text='⏳ جاري البحث...', text_color=COLORS['info'])

        def worker():
            try:
                from core.file_finder import search
                members, device = search()
                self.after(0, lambda: self._on_auto_detect_done(members, device))
            except Exception as e:
                self.after(0, lambda: self.test_label.configure(
                    text=f'فشل البحث: {e}', text_color=COLORS['error']))

        threading.Thread(target=worker, daemon=True).start()

    def _on_auto_detect_done(self, members, device):
        if members:
            self.members_entry.delete(0, 'end')
            self.members_entry.insert(0, members)
        if device:
            self.attendance_entry.delete(0, 'end')
            self.attendance_entry.insert(0, device)

        if members and device:
            self.test_label.configure(text='✓ تم العثور على الملفات',
                                       text_color=COLORS['success'])
        elif members or device:
            self.test_label.configure(text='⚠ تم العثور على ملف واحد فقط',
                                       text_color=COLORS['warning'])
        else:
            self.test_label.configure(text='✗ لم يتم العثور على ملفات',
                                       text_color=COLORS['error'])

    def _on_test(self):
        members_path = self.members_entry.get().strip()
        att_path = self.attendance_entry.get().strip()
        password = self.password_entry.get().strip() or None

        self.test_label.configure(text='⏳ جاري الاختبار...', text_color=COLORS['info'])

        def worker():
            from core.db_reader import DBReader
            r = DBReader(members_path, att_path, password=password)
            ok_m, msg_m = r.test_members_db()
            ok_a, msg_a = r.test_attendance_db() if att_path else (False, 'لم يتم تحديده')

            text = f'الأعضاء: {"✓" if ok_m else "✗"} {msg_m}\nالبصمة: {"✓" if ok_a else "✗"} {msg_a}'
            color = COLORS['success'] if ok_m else COLORS['error']
            self.after(0, lambda: self.test_label.configure(text=text, text_color=color))

        threading.Thread(target=worker, daemon=True).start()

    def _on_save(self):
        if not self.controller:
            return

        try:
            interval = int(self.interval_entry.get().strip())
            interval = max(10, min(3600, interval))
        except ValueError:
            interval = 60

        updates = {
            'db_path_members': self.members_entry.get().strip(),
            'db_path_attendance': self.attendance_entry.get().strip(),
            'db_password': self.password_entry.get().strip(),
            'sync_interval_seconds': interval,
        }
        self.controller.save_settings(updates)
        self.test_label.configure(text='✓ تم الحفظ', text_color=COLORS['success'])

    def _on_back(self):
        if self.controller:
            self.controller.show_status()
