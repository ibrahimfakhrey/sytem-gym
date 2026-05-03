"""
Setup Page - Branch code registration on first launch
"""

import customtkinter as ctk
import threading


class SetupPage(ctk.CTkFrame):
    """First-launch setup: enter branch code to register"""

    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._create_widgets()

    def _create_widgets(self):
        # Center container
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.4, anchor="center")

        # Logo/Title
        ctk.CTkLabel(center, text="🏋️", font=("Arial", 60)).pack(pady=(0, 10))
        ctk.CTkLabel(center, text="نظام إدارة الجيم",
                     font=("Arial", 28, "bold")).pack(pady=(0, 5))
        ctk.CTkLabel(center, text="إعداد الجهاز",
                     font=("Arial", 16), text_color="#b0bec5").pack(pady=(0, 30))

        # Branch code input
        input_frame = ctk.CTkFrame(center, fg_color="#1a2332", corner_radius=15)
        input_frame.pack(padx=40, pady=10, fill="x")

        ctk.CTkLabel(input_frame, text="أدخل رمز الفرع",
                     font=("Arial", 14, "bold")).pack(pady=(20, 5))
        ctk.CTkLabel(input_frame, text="الرمز يحصل عليه من إدارة النظام",
                     font=("Arial", 11), text_color="#888").pack(pady=(0, 10))

        self.code_entry = ctk.CTkEntry(
            input_frame, placeholder_text="مثال: BR-3-1",
            font=("Arial", 18), height=50, width=250,
            justify="center"
        )
        self.code_entry.pack(pady=10)

        # API URL input (smaller)
        ctk.CTkLabel(input_frame, text="عنوان السيرفر",
                     font=("Arial", 11), text_color="#888").pack(pady=(10, 2))
        self.api_url_entry = ctk.CTkEntry(
            input_frame, placeholder_text="https://gymsystem.pythonanywhere.com",
            font=("Arial", 12), height=35, width=300,
            justify="center"
        )
        self.api_url_entry.pack(pady=(0, 5))
        self.api_url_entry.insert(0, "https://gymsystem.pythonanywhere.com")

        # API key input
        ctk.CTkLabel(input_frame, text="مفتاح API",
                     font=("Arial", 11), text_color="#888").pack(pady=(5, 2))
        self.api_key_entry = ctk.CTkEntry(
            input_frame, placeholder_text="API Key",
            font=("Arial", 12), height=35, width=300,
            justify="center", show="*"
        )
        self.api_key_entry.pack(pady=(0, 15))

        # Register button
        self.register_btn = ctk.CTkButton(
            input_frame, text="تسجيل الجهاز",
            font=("Arial", 16, "bold"), height=45, width=200,
            command=self._handle_register, fg_color="#4caf50", hover_color="#388e3c"
        )
        self.register_btn.pack(pady=(5, 20))

        # Status message
        self.status_label = ctk.CTkLabel(
            center, text="", font=("Arial", 13), text_color="#ff9800"
        )
        self.status_label.pack(pady=10)

    def _handle_register(self):
        code = self.code_entry.get().strip().upper()
        api_url = self.api_url_entry.get().strip()
        api_key = self.api_key_entry.get().strip()

        if not code:
            self.status_label.configure(text="يرجى إدخال رمز الفرع", text_color="#f44336")
            return
        if not api_url:
            self.status_label.configure(text="يرجى إدخال عنوان السيرفر", text_color="#f44336")
            return
        if not api_key:
            self.status_label.configure(text="يرجى إدخال مفتاح API", text_color="#f44336")
            return

        self.status_label.configure(text="⏳ جاري التسجيل...", text_color="#ff9800")
        self.register_btn.configure(state="disabled")

        def do_register():
            try:
                import requests
                response = requests.post(
                    f"{api_url}/api/bridge/register",
                    headers={'X-API-Key': api_key, 'Content-Type': 'application/json'},
                    json={'branch_code': code},
                    timeout=15
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get('valid'):
                        self.after(0, lambda: self._on_success(data, api_url, api_key))
                    else:
                        self.after(0, lambda: self._on_error(data.get('error', 'رمز غير صحيح')))
                elif response.status_code == 404:
                    self.after(0, lambda: self._on_error("رمز الفرع غير موجود"))
                else:
                    self.after(0, lambda: self._on_error(f"خطأ من السيرفر: {response.status_code}"))

            except requests.ConnectionError:
                self.after(0, lambda: self._on_error("لا يمكن الاتصال بالسيرفر"))
            except Exception as e:
                self.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=do_register, daemon=True).start()

    def _on_success(self, data, api_url, api_key):
        self.status_label.configure(
            text=f"✅ تم التسجيل! {data.get('branch_name')} - {data.get('brand_name')}",
            text_color="#4caf50"
        )
        self.register_btn.configure(state="normal")

        # Save to config via app controller
        if self.app and self.app.app_controller:
            self.app.app_controller.complete_registration({
                'api_url': api_url,
                'api_key': api_key,
                'branch_code': data.get('branch_code'),
                'branch_id': data.get('branch_id'),
                'brand_id': data.get('brand_id'),
                'branch_name': data.get('branch_name'),
                'brand_name': data.get('brand_name'),
                'is_registered': True,
                'settings': data.get('settings', {})
            })

    def _on_error(self, message):
        self.status_label.configure(text=f"❌ {message}", text_color="#f44336")
        self.register_btn.configure(state="normal")

    def load_config(self, config):
        """Pre-fill from existing config"""
        if config.get('api_url'):
            self.api_url_entry.delete(0, "end")
            self.api_url_entry.insert(0, config['api_url'])
        if config.get('api_key'):
            self.api_key_entry.delete(0, "end")
            self.api_key_entry.insert(0, config['api_key'])
        if config.get('branch_code'):
            self.code_entry.delete(0, "end")
            self.code_entry.insert(0, config['branch_code'])
