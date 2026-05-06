"""
Setup Page — single field: branch code. Server URL hidden in advanced.
"""
import customtkinter as ctk
import threading

from ..theme import COLORS, FONTS


class SetupPage(ctk.CTkFrame):
    """First-launch setup. Calls controller.complete_registration on success."""

    def __init__(self, parent, controller=None, **kwargs):
        super().__init__(parent, fg_color=COLORS['bg'], **kwargs)
        self.controller = controller
        self._build()

    def _build(self):
        center = ctk.CTkFrame(self, fg_color='transparent')
        center.place(relx=0.5, rely=0.5, anchor='center')

        # Title
        ctk.CTkLabel(center, text='🏋️', font=('Arial', 64)).pack(pady=(0, 8))
        ctk.CTkLabel(center, text='نظام إدارة الجيم',
                     font=FONTS['h1'], text_color=COLORS['text']).pack(pady=(0, 4))
        ctk.CTkLabel(center, text='إعداد الجهاز للمرة الأولى',
                     font=FONTS['body'], text_color=COLORS['text_muted']).pack(pady=(0, 36))

        # Card
        card = ctk.CTkFrame(center, fg_color=COLORS['bg_card'], corner_radius=14,
                            border_width=1, border_color=COLORS['border'])
        card.pack(padx=40)

        inner = ctk.CTkFrame(card, fg_color='transparent')
        inner.pack(padx=36, pady=30)

        ctk.CTkLabel(inner, text='أدخل رمز الفرع',
                     font=FONTS['h3'], text_color=COLORS['text']).pack(pady=(0, 6))
        ctk.CTkLabel(inner, text='تحصل على هذا الرمز من إدارة النظام',
                     font=FONTS['small'], text_color=COLORS['text_muted']).pack(pady=(0, 16))

        self.entry = ctk.CTkEntry(
            inner, placeholder_text='BR-3-1',
            font=('Arial', 20, 'bold'), height=54, width=320,
            justify='center',
        )
        self.entry.pack(pady=(0, 18))
        self.entry.bind('<Return>', lambda e: self._handle_register())

        self.btn = ctk.CTkButton(
            inner, text='تسجيل الجهاز',
            font=FONTS['btn'], height=48, width=280,
            fg_color=COLORS['success'], hover_color='#059669',
            command=self._handle_register,
        )
        self.btn.pack(pady=(0, 12))

        # Status message
        self.status = ctk.CTkLabel(center, text='', font=FONTS['body'],
                                    text_color=COLORS['warning'])
        self.status.pack(pady=(20, 0))

        # Advanced toggle (hidden by default — server URL field)
        self.advanced_btn = ctk.CTkButton(
            center, text='⚙ إعدادات متقدمة',
            font=FONTS['small'], fg_color='transparent',
            text_color=COLORS['text_muted'], hover=False,
            command=self._toggle_advanced,
        )
        self.advanced_btn.pack(pady=(28, 0))

        self.advanced_frame = ctk.CTkFrame(center, fg_color='transparent')
        ctk.CTkLabel(self.advanced_frame, text='عنوان السيرفر',
                     font=FONTS['small'], text_color=COLORS['text_muted']).pack(pady=(8, 4))
        self.url_entry = ctk.CTkEntry(
            self.advanced_frame, font=FONTS['small'], height=32, width=320,
            justify='center',
        )
        self.url_entry.pack()
        self.advanced_visible = False

    def _toggle_advanced(self):
        if self.advanced_visible:
            self.advanced_frame.pack_forget()
            self.advanced_visible = False
        else:
            self.advanced_frame.pack(pady=(8, 0))
            self.advanced_visible = True

    def load_config(self, config):
        if config.get('api_url'):
            self.url_entry.delete(0, 'end')
            self.url_entry.insert(0, config['api_url'])
        if config.get('branch_code'):
            self.entry.delete(0, 'end')
            self.entry.insert(0, config['branch_code'])

    def _handle_register(self):
        code = self.entry.get().strip().upper()
        api_url = (self.url_entry.get().strip() if self.advanced_visible else '') \
                   or 'https://gymsystem.pythonanywhere.com'

        if not code:
            self._set_status('يرجى إدخال رمز الفرع', 'error')
            return

        self._set_status('⏳ جاري الاتصال بالسيرفر...', 'info')
        self.btn.configure(state='disabled')

        def worker():
            try:
                from core.api import APIv2, APIError
                api = APIv2(api_url, code)
                result = api.health()
                if result.get('success'):
                    self.after(0, lambda: self._on_success(result, api_url, code))
                else:
                    err = result.get('error', 'فشل الاتصال')
                    self.after(0, lambda: self._on_error(err))
            except Exception as e:
                self.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, result, api_url, code):
        self._set_status(
            f'✅ تم التسجيل! {result.get("branch_name")} — {result.get("brand_name")}',
            'success'
        )
        self.btn.configure(state='normal')

        if self.controller:
            self.controller.complete_registration({
                'api_url': api_url,
                'branch_code': code,
                'branch_id': result.get('branch_id'),
                'brand_id': result.get('brand_id'),
                'branch_name': result.get('branch_name'),
                'brand_name': result.get('brand_name'),
                'is_registered': True,
            })

    def _on_error(self, msg):
        self._set_status(f'❌ {msg}', 'error')
        self.btn.configure(state='normal')

    def _set_status(self, text, level='info'):
        color_map = {
            'info': COLORS['info'],
            'success': COLORS['success'],
            'warning': COLORS['warning'],
            'error': COLORS['error'],
        }
        self.status.configure(text=text, text_color=color_map.get(level, COLORS['text']))
