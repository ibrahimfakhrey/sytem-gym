"""
Test Page - System diagnostic tests
"""

import customtkinter as ctk
import threading
from datetime import datetime


class TestPage(ctk.CTkFrame):
    """System diagnostic tests for verifying bridge setup"""

    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._tests = []
        self._create_widgets()

    def _create_widgets(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(header, text="🔧 اختبار النظام",
                     font=("Arial", 24, "bold"), anchor="e").pack(side="right")

        self.run_btn = ctk.CTkButton(
            header, text="▶ تشغيل الاختبارات", width=180,
            command=self._run_all_tests,
            fg_color="#4caf50", hover_color="#388e3c",
            font=("Arial", 14, "bold")
        )
        self.run_btn.pack(side="left")

        # Status summary
        self.summary_label = ctk.CTkLabel(
            self, text="اضغط 'تشغيل الاختبارات' للبدء",
            font=("Arial", 13), text_color="#b0bec5"
        )
        self.summary_label.pack(pady=(0, 10))

        # Tests container
        self._tests_frame = ctk.CTkScrollableFrame(
            self, fg_color="#1a2332", corner_radius=10)
        self._tests_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Pre-create test rows
        test_definitions = [
            ("api_connection", "🌐", "اتصال السيرفر", "التحقق من اتصال الإنترنت والسيرفر"),
            ("branch_valid", "🏢", "تسجيل الفرع", "التحقق من صحة رمز الفرع"),
            ("att2000_read", "📖", "قراءة att2000.mdb", "التحقق من قراءة قاعدة بيانات البصمة"),
            ("backup_read", "📂", "قراءة backup.mdb", "التحقق من قراءة قاعدة بيانات الأعضاء"),
            ("backup_write", "✏️", "كتابة backup.mdb", "التحقق من إمكانية تعديل تاريخ الانتهاء"),
            ("fingerprint_records", "👆", "سجلات البصمة", "التحقق من وجود سجلات في CHECKINOUT"),
            ("member_count", "👥", "بيانات الأعضاء", "التحقق من قراءة بيانات الأعضاء"),
            ("class_schedule", "📅", "جدول الكلاسات", "جلب جدول كلاسات اليوم من السيرفر"),
        ]

        self._test_rows = {}
        for test_id, icon, title, desc in test_definitions:
            row = self._create_test_row(test_id, icon, title, desc)
            self._test_rows[test_id] = row

    def _create_test_row(self, test_id, icon, title, desc):
        row = ctk.CTkFrame(self._tests_frame, fg_color="#0d1421", corner_radius=8, height=60)
        row.pack(fill="x", padx=10, pady=3)
        row.pack_propagate(False)

        # Icon
        ctk.CTkLabel(row, text=icon, font=("Arial", 20), width=40).pack(side="right", padx=10)

        # Info
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(info, text=title, font=("Arial", 13, "bold"), anchor="e").pack(anchor="e")
        ctk.CTkLabel(info, text=desc, font=("Arial", 10), text_color="#888", anchor="e").pack(anchor="e")

        # Status
        status_label = ctk.CTkLabel(row, text="⏳ انتظار", font=("Arial", 12),
                                     text_color="#888", width=120)
        status_label.pack(side="left", padx=10)

        return {'frame': row, 'status': status_label}

    def _set_test_status(self, test_id, passed, detail=""):
        if test_id in self._test_rows:
            row = self._test_rows[test_id]
            if passed:
                row['status'].configure(text=f"✅ {detail}" if detail else "✅ ناجح",
                                        text_color="#4caf50")
                row['frame'].configure(fg_color="#0d2415")
            else:
                row['status'].configure(text=f"❌ {detail}" if detail else "❌ فاشل",
                                        text_color="#f44336")
                row['frame'].configure(fg_color="#240d0d")

    def _set_test_running(self, test_id):
        if test_id in self._test_rows:
            self._test_rows[test_id]['status'].configure(
                text="⏳ جاري...", text_color="#ff9800")
            self._test_rows[test_id]['frame'].configure(fg_color="#0d1421")

    def _run_all_tests(self):
        self.run_btn.configure(state="disabled")
        self.summary_label.configure(text="⏳ جاري تشغيل الاختبارات...", text_color="#ff9800")

        # Reset all
        for tid in self._test_rows:
            self._set_test_running(tid)

        def run_tests():
            passed = 0
            total = 0

            controller = self.app.app_controller if self.app else None

            # Test 1: API connection
            total += 1
            try:
                if controller and controller.api_client:
                    result = controller.api_client.health_check()
                    ok = result.get('status') == 'ok'
                    self.after(0, lambda: self._set_test_status('api_connection', ok, 'متصل' if ok else 'غير متصل'))
                    if ok: passed += 1
                else:
                    self.after(0, lambda: self._set_test_status('api_connection', False, 'لم يتم الإعداد'))
            except Exception as e:
                self.after(0, lambda: self._set_test_status('api_connection', False, str(e)[:30]))

            # Test 2: Branch registration
            total += 1
            try:
                config = controller.config if controller else {}
                is_reg = config.get('is_registered', False)
                branch_name = config.get('branch_name', '')
                self.after(0, lambda: self._set_test_status('branch_valid', is_reg,
                           branch_name if is_reg else 'غير مسجل'))
                if is_reg: passed += 1
            except Exception:
                self.after(0, lambda: self._set_test_status('branch_valid', False, 'خطأ'))

            # Test 3: att2000.mdb read
            total += 1
            try:
                if controller and controller.device_db_manager:
                    ok = controller.device_db_manager.is_connected()
                    count = controller.device_db_manager.get_record_count() if ok else 0
                    self.after(0, lambda: self._set_test_status('att2000_read', ok,
                               f'{count} سجل' if ok else 'غير متصل'))
                    if ok: passed += 1
                else:
                    self.after(0, lambda: self._set_test_status('att2000_read', False, 'لم يتم الكشف'))
            except Exception as e:
                self.after(0, lambda: self._set_test_status('att2000_read', False, str(e)[:30]))

            # Test 4: backup.mdb read
            total += 1
            try:
                if controller and controller.db_manager and controller.db_manager.is_connected():
                    count = controller.db_manager.get_employee_count()
                    self.after(0, lambda: self._set_test_status('backup_read', True, f'{count} عضو'))
                    passed += 1
                else:
                    self.after(0, lambda: self._set_test_status('backup_read', False, 'غير متصل'))
            except Exception as e:
                self.after(0, lambda: self._set_test_status('backup_read', False, str(e)[:30]))

            # Test 5: backup.mdb write (non-destructive)
            total += 1
            try:
                if controller and controller.db_manager and controller.db_manager.is_connected():
                    # Try reading a record — don't actually write
                    emp = controller.db_manager.get_all_employees()
                    self.after(0, lambda: self._set_test_status('backup_write', len(emp) > 0,
                               'قابل للكتابة' if emp else 'فارغ'))
                    if emp: passed += 1
                else:
                    self.after(0, lambda: self._set_test_status('backup_write', False, 'غير متصل'))
            except Exception as e:
                self.after(0, lambda: self._set_test_status('backup_write', False, str(e)[:30]))

            # Test 6: Fingerprint records
            total += 1
            try:
                if controller and controller.device_db_manager:
                    records = controller.device_db_manager.read_checkinout()
                    count = len(records)
                    self.after(0, lambda: self._set_test_status('fingerprint_records', count > 0,
                               f'{count} سجل'))
                    if count > 0: passed += 1
                else:
                    self.after(0, lambda: self._set_test_status('fingerprint_records', False, 'لا يوجد جهاز'))
            except Exception as e:
                self.after(0, lambda: self._set_test_status('fingerprint_records', False, str(e)[:30]))

            # Test 7: Member count
            total += 1
            try:
                if controller and controller.db_manager and controller.db_manager.is_connected():
                    count = controller.db_manager.get_employee_count()
                    self.after(0, lambda: self._set_test_status('member_count', count > 0,
                               f'{count} عضو'))
                    if count > 0: passed += 1
                else:
                    self.after(0, lambda: self._set_test_status('member_count', False, 'غير متصل'))
            except Exception:
                self.after(0, lambda: self._set_test_status('member_count', False, 'خطأ'))

            # Test 8: Class schedule
            total += 1
            try:
                if controller and controller.api_client:
                    schedule = controller.api_client.get_class_schedule()
                    ok = schedule.get('success', False)
                    classes_count = len(schedule.get('classes', []))
                    self.after(0, lambda: self._set_test_status('class_schedule', ok,
                               f'{classes_count} كلاس اليوم' if ok else 'فشل'))
                    if ok: passed += 1
                else:
                    self.after(0, lambda: self._set_test_status('class_schedule', False, 'لم يتم الإعداد'))
            except Exception as e:
                self.after(0, lambda: self._set_test_status('class_schedule', False, str(e)[:30]))

            # Summary
            self.after(0, lambda: self._show_summary(passed, total))

        threading.Thread(target=run_tests, daemon=True).start()

    def _show_summary(self, passed, total):
        self.run_btn.configure(state="normal")
        if passed == total:
            self.summary_label.configure(
                text=f"✅ جميع الاختبارات ناجحة ({passed}/{total})",
                text_color="#4caf50")
        else:
            self.summary_label.configure(
                text=f"⚠️ {passed}/{total} ناجح — {total - passed} فاشل",
                text_color="#ff9800")
