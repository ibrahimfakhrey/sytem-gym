"""
Settings page
"""

import customtkinter as ctk
from ..styles import COLORS, FONTS


class SettingsPage(ctk.CTkFrame):
    """Application settings page"""

    def __init__(self, parent, app=None):
        super().__init__(parent, fg_color=COLORS['background'])
        self.app = app

        self._create_widgets()

    def _create_widgets(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="⚙️ الإعدادات",
            font=FONTS['title'],
            text_color=COLORS['text_primary']
        )
        header.pack(pady=20)

        # Scrollable content
        scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=20)

        # API Settings Card
        api_card = ctk.CTkFrame(scroll_frame, fg_color=COLORS['card_bg'], corner_radius=10)
        api_card.pack(fill="x", pady=10)

        api_header = ctk.CTkLabel(
            api_card,
            text="🌐 إعدادات الاتصال",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary']
        )
        api_header.pack(pady=15, padx=15, anchor="e")

        # API URL
        api_url_frame = ctk.CTkFrame(api_card, fg_color="transparent")
        api_url_frame.pack(fill="x", padx=15, pady=5)

        api_url_label = ctk.CTkLabel(
            api_url_frame,
            text="عنوان تطبيق الويب:",
            font=FONTS['body'],
            text_color=COLORS['text_primary']
        )
        api_url_label.pack(anchor="e")

        self.api_url_entry = ctk.CTkEntry(
            api_url_frame,
            font=FONTS['body'],
            fg_color=COLORS['input_bg'],
            text_color=COLORS['text_primary'],
            border_color=COLORS['border'],
            height=40
        )
        self.api_url_entry.pack(fill="x", pady=5)
        self.api_url_entry.insert(0, "https://gymsystem.pythonanywhere.com")

        # API Key
        api_key_frame = ctk.CTkFrame(api_card, fg_color="transparent")
        api_key_frame.pack(fill="x", padx=15, pady=5)

        api_key_label = ctk.CTkLabel(
            api_key_frame,
            text="مفتاح API:",
            font=FONTS['body'],
            text_color=COLORS['text_primary']
        )
        api_key_label.pack(anchor="e")

        self.api_key_entry = ctk.CTkEntry(
            api_key_frame,
            font=FONTS['body'],
            fg_color=COLORS['input_bg'],
            text_color=COLORS['text_primary'],
            border_color=COLORS['border'],
            height=40,
            show="*"
        )
        self.api_key_entry.pack(fill="x", pady=5)

        # Brand ID
        brand_frame = ctk.CTkFrame(api_card, fg_color="transparent")
        brand_frame.pack(fill="x", padx=15, pady=(5, 15))

        brand_label = ctk.CTkLabel(
            brand_frame,
            text="رقم الفرع (Brand ID):",
            font=FONTS['body'],
            text_color=COLORS['text_primary']
        )
        brand_label.pack(anchor="e")

        self.brand_entry = ctk.CTkEntry(
            brand_frame,
            font=FONTS['body'],
            fg_color=COLORS['input_bg'],
            text_color=COLORS['text_primary'],
            border_color=COLORS['border'],
            height=40,
            width=100
        )
        self.brand_entry.pack(anchor="e", pady=5)
        self.brand_entry.insert(0, "1")

        # Database Settings Card
        db_card = ctk.CTkFrame(scroll_frame, fg_color=COLORS['card_bg'], corner_radius=10)
        db_card.pack(fill="x", pady=10)

        db_header = ctk.CTkLabel(
            db_card,
            text="💾 إعدادات قاعدة البيانات",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary']
        )
        db_header.pack(pady=15, padx=15, anchor="e")

        # Database path
        db_path_frame = ctk.CTkFrame(db_card, fg_color="transparent")
        db_path_frame.pack(fill="x", padx=15, pady=5)

        db_path_label = ctk.CTkLabel(
            db_path_frame,
            text="مسار قاعدة البيانات (.mdb):",
            font=FONTS['body'],
            text_color=COLORS['text_primary']
        )
        db_path_label.pack(anchor="e")

        path_input_frame = ctk.CTkFrame(db_path_frame, fg_color="transparent")
        path_input_frame.pack(fill="x", pady=5)

        self.db_path_entry = ctk.CTkEntry(
            path_input_frame,
            font=FONTS['body'],
            fg_color=COLORS['input_bg'],
            text_color=COLORS['text_primary'],
            border_color=COLORS['border'],
            height=40
        )
        self.db_path_entry.pack(side="right", fill="x", expand=True, padx=(10, 0))

        browse_btn = ctk.CTkButton(
            path_input_frame,
            text="📁 استعراض",
            font=FONTS['button'],
            fg_color=COLORS['secondary'],
            hover_color=COLORS['primary'],
            height=40,
            width=100,
            command=self._browse_database
        )
        browse_btn.pack(side="right")

        # Auto-detect button
        detect_btn = ctk.CTkButton(
            db_card,
            text="🔍 البحث التلقائي عن قاعدة البيانات",
            font=FONTS['button'],
            fg_color=COLORS['accent'],
            hover_color=COLORS['primary'],
            height=40,
            command=self._auto_detect_database
        )
        detect_btn.pack(pady=15)

        # Sync Settings Card
        sync_card = ctk.CTkFrame(scroll_frame, fg_color=COLORS['card_bg'], corner_radius=10)
        sync_card.pack(fill="x", pady=10)

        sync_header = ctk.CTkLabel(
            sync_card,
            text="🔄 إعدادات المزامنة",
            font=FONTS['subheading'],
            text_color=COLORS['text_primary']
        )
        sync_header.pack(pady=15, padx=15, anchor="e")

        # Sync interval
        interval_frame = ctk.CTkFrame(sync_card, fg_color="transparent")
        interval_frame.pack(fill="x", padx=15, pady=5)

        interval_label = ctk.CTkLabel(
            interval_frame,
            text="فترة المزامنة (بالثواني):",
            font=FONTS['body'],
            text_color=COLORS['text_primary']
        )
        interval_label.pack(side="right")

        self.interval_entry = ctk.CTkEntry(
            interval_frame,
            font=FONTS['body'],
            fg_color=COLORS['input_bg'],
            text_color=COLORS['text_primary'],
            border_color=COLORS['border'],
            height=40,
            width=80
        )
        self.interval_entry.pack(side="left", padx=15)
        self.interval_entry.insert(0, "30")

        # Auto-start sync
        auto_start_frame = ctk.CTkFrame(sync_card, fg_color="transparent")
        auto_start_frame.pack(fill="x", padx=15, pady=(10, 15))

        self.auto_start_var = ctk.BooleanVar(value=True)
        auto_start_switch = ctk.CTkSwitch(
            auto_start_frame,
            text="بدء المزامنة تلقائياً عند فتح البرنامج",
            font=FONTS['body'],
            text_color=COLORS['text_primary'],
            variable=self.auto_start_var
        )
        auto_start_switch.pack(anchor="e")

        # Save button
        save_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        save_frame.pack(fill="x", pady=20)

        save_btn = ctk.CTkButton(
            save_frame,
            text="💾 حفظ الإعدادات",
            font=FONTS['button'],
            fg_color=COLORS['success'],
            hover_color='#388e3c',
            height=50,
            width=200,
            command=self._save_settings
        )
        save_btn.pack()

        # Status message
        self.status_label = ctk.CTkLabel(
            scroll_frame,
            text="",
            font=FONTS['body'],
            text_color=COLORS['text_secondary']
        )
        self.status_label.pack(pady=10)

    def _browse_database(self):
        """Open file browser for database selection"""
        from tkinter import filedialog

        file_path = filedialog.askopenfilename(
            title="اختر ملف قاعدة البيانات",
            filetypes=[("Access Database", "*.mdb"), ("All Files", "*.*")]
        )

        if file_path:
            self.db_path_entry.delete(0, 'end')
            self.db_path_entry.insert(0, file_path)

    def _auto_detect_database(self):
        """Auto-detect database files"""
        self.status_label.configure(
            text="⏳ جاري البحث عن قاعدة البيانات...",
            text_color=COLORS['accent']
        )
        self.update()

        if self.app and hasattr(self.app, 'find_database'):
            result = self.app.find_database()
            if result:
                self.db_path_entry.delete(0, 'end')
                self.db_path_entry.insert(0, result)
                self.status_label.configure(
                    text="✅ تم العثور على قاعدة البيانات",
                    text_color=COLORS['success']
                )
            else:
                self.status_label.configure(
                    text="❌ لم يتم العثور على قاعدة البيانات",
                    text_color=COLORS['error']
                )

    def _save_settings(self):
        """Save settings"""
        settings = {
            'api_url': self.api_url_entry.get().strip(),
            'api_key': self.api_key_entry.get().strip(),
            'brand_id': self.brand_entry.get().strip(),
            'db_path': self.db_path_entry.get().strip(),
            'sync_interval': int(self.interval_entry.get() or 30),
            'auto_start_sync': self.auto_start_var.get()
        }

        if self.app and hasattr(self.app, 'save_settings'):
            success = self.app.save_settings(settings)
            if success:
                self.status_label.configure(
                    text="✅ تم حفظ الإعدادات بنجاح",
                    text_color=COLORS['success']
                )
            else:
                self.status_label.configure(
                    text="❌ فشل حفظ الإعدادات",
                    text_color=COLORS['error']
                )

    def load_settings(self, settings: dict):
        """Load settings into form"""
        if settings.get('api_url'):
            self.api_url_entry.delete(0, 'end')
            self.api_url_entry.insert(0, settings['api_url'])

        if settings.get('api_key'):
            self.api_key_entry.delete(0, 'end')
            self.api_key_entry.insert(0, settings['api_key'])

        if settings.get('brand_id'):
            self.brand_entry.delete(0, 'end')
            self.brand_entry.insert(0, str(settings['brand_id']))

        if settings.get('db_path'):
            self.db_path_entry.delete(0, 'end')
            self.db_path_entry.insert(0, settings['db_path'])

        if settings.get('sync_interval'):
            self.interval_entry.delete(0, 'end')
            self.interval_entry.insert(0, str(settings['sync_interval']))

        if 'auto_start_sync' in settings:
            self.auto_start_var.set(settings['auto_start_sync'])
