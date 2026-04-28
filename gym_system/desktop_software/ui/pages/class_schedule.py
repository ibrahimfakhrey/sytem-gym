"""
Class Schedule Page - Today's classes with access windows
"""

import customtkinter as ctk
from datetime import datetime, date, timedelta
import threading


class ClassSchedulePage(ctk.CTkFrame):
    """Today's class schedule with member access windows"""

    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._schedule = None
        self._class_cards = []
        self._create_widgets()
        self._start_auto_refresh()

    def _create_widgets(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(header, text="📅 جدول كلاسات اليوم",
                     font=("Arial", 24, "bold"), anchor="e").pack(side="right")

        refresh_btn = ctk.CTkButton(header, text="🔄 تحديث", width=100,
                                     command=self._refresh,
                                     fg_color="#2a3a4a", hover_color="#3a4a5a")
        refresh_btn.pack(side="left")

        # Date display
        today_str = date.today().strftime('%Y-%m-%d')
        self._date_label = ctk.CTkLabel(header, text=f"التاريخ: {today_str}",
                                         font=("Arial", 12), text_color="#b0bec5")
        self._date_label.pack(side="left", padx=20)

        # Summary strip
        summary_frame = ctk.CTkFrame(self, fg_color="#1a2332", corner_radius=10)
        summary_frame.pack(fill="x", padx=20, pady=(0, 10))

        self._summary_cards = {}
        summary_data = [
            ('classes', 'الكلاسات', '#448aff'),
            ('class_members', 'أعضاء الكلاسات', '#4caf50'),
            ('gym_members', 'أعضاء الجيم', '#ff9800'),
            ('blocked', 'محظورين', '#f44336')
        ]

        for key, label, color in summary_data:
            card = ctk.CTkFrame(summary_frame, fg_color="transparent")
            card.pack(side="right", expand=True, padx=10, pady=8)

            value_label = ctk.CTkLabel(card, text="0",
                                        font=("Arial", 22, "bold"),
                                        text_color=color)
            value_label.pack()
            ctk.CTkLabel(card, text=label, font=("Arial", 10),
                        text_color="#b0bec5").pack()
            self._summary_cards[key] = value_label

        # Classes container
        self._classes_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent")
        self._classes_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Empty state
        self._empty_label = ctk.CTkLabel(
            self._classes_frame,
            text="لا توجد كلاسات اليوم\nسيتم تحميل الجدول عند المزامنة",
            font=("Arial", 14), text_color="#b0bec5", justify="center")
        self._empty_label.pack(pady=50)

    def update_schedule(self, schedule: dict):
        """Update the display with new schedule data"""
        self._schedule = schedule

        # Clear existing cards
        for widget in self._classes_frame.winfo_children():
            widget.destroy()
        self._class_cards.clear()

        classes = schedule.get('classes', [])
        access_window = schedule.get('access_window_minutes', 15)
        summary = schedule.get('summary', {})

        # Update summary
        self._summary_cards['classes'].configure(text=str(summary.get('classes_count', len(classes))))
        self._summary_cards['class_members'].configure(text=str(summary.get('class_members_count', 0)))
        self._summary_cards['gym_members'].configure(text=str(summary.get('gym_members_count', 0)))
        self._summary_cards['blocked'].configure(text=str(summary.get('blocked_count', 0)))

        if not classes:
            ctk.CTkLabel(
                self._classes_frame,
                text="لا توجد كلاسات مجدولة اليوم",
                font=("Arial", 14), text_color="#b0bec5", justify="center"
            ).pack(pady=50)
            return

        # Create class cards
        now = datetime.now()
        for cls in classes:
            self._create_class_card(cls, access_window, now)

    def _create_class_card(self, cls: dict, access_window: int, now: datetime):
        """Create a single class card"""
        start_str = cls.get('start_time', '')
        end_str = cls.get('end_time', '')
        booked = cls.get('booked_members', [])
        today = date.today()

        # Parse times
        try:
            class_start = datetime.strptime(start_str, '%H:%M').replace(
                year=today.year, month=today.month, day=today.day)
            class_end = datetime.strptime(end_str, '%H:%M').replace(
                year=today.year, month=today.month, day=today.day)
            window_start = class_start - timedelta(minutes=access_window)
        except ValueError:
            class_start = class_end = window_start = None

        # Determine status
        if class_start and class_end:
            if now < window_start:
                status = 'upcoming'
                status_text = 'قادم'
                status_color = '#448aff'
                bg_color = '#1a2332'
            elif now <= class_end:
                status = 'active'
                status_text = 'جاري الآن'
                status_color = '#4caf50'
                bg_color = '#153d1a'
            else:
                status = 'ended'
                status_text = 'انتهى'
                status_color = '#757575'
                bg_color = '#1a2332'
        else:
            status = 'unknown'
            status_text = '-'
            status_color = '#757575'
            bg_color = '#1a2332'

        # Card
        card = ctk.CTkFrame(self._classes_frame, fg_color=bg_color, corner_radius=10)
        card.pack(fill="x", padx=5, pady=5)

        # Top row: class info
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(top, text=cls.get('name', ''),
                     font=("Arial", 16, "bold"), anchor="e").pack(side="right")

        # Status badge
        badge = ctk.CTkLabel(top, text=f" {status_text} ",
                              font=("Arial", 11, "bold"),
                              fg_color=status_color, corner_radius=5,
                              text_color="white")
        badge.pack(side="left", padx=5)

        # Details row
        details = ctk.CTkFrame(card, fg_color="transparent")
        details.pack(fill="x", padx=15, pady=(0, 5))

        info_parts = []
        if cls.get('trainer'):
            info_parts.append(f"المدرب: {cls['trainer']}")
        info_parts.append(f"الوقت: {start_str} - {end_str}")
        info_parts.append(f"نافذة الدخول: {window_start.strftime('%H:%M') if window_start else '-'} - {end_str}")
        info_parts.append(f"المحجوزين: {len(booked)}")

        ctk.CTkLabel(details, text="  |  ".join(info_parts),
                     font=("Arial", 11), text_color="#b0bec5",
                     anchor="e").pack(side="right")

        # Booked members (collapsible)
        if booked:
            members_frame = ctk.CTkFrame(card, fg_color="#0d1421", corner_radius=5)
            members_frame.pack(fill="x", padx=15, pady=(0, 10))

            for member in booked[:10]:
                row = ctk.CTkFrame(members_frame, fg_color="transparent", height=25)
                row.pack(fill="x", padx=10, pady=1)
                row.pack_propagate(False)

                # Access indicator
                if status == 'active':
                    indicator = "🟢"
                elif status == 'upcoming':
                    indicator = "🔵"
                else:
                    indicator = "⚪"

                ctk.CTkLabel(row, text=indicator, font=("Arial", 10),
                            width=20).pack(side="right")
                ctk.CTkLabel(row, text=member.get('name', ''),
                            font=("Arial", 11), anchor="e").pack(side="right", padx=5)
                ctk.CTkLabel(row, text=member.get('emp_id', ''),
                            font=("Arial", 9), text_color="#757575").pack(side="left")

            if len(booked) > 10:
                ctk.CTkLabel(members_frame,
                            text=f"و {len(booked) - 10} عضو آخر...",
                            font=("Arial", 10), text_color="#757575").pack(pady=3)

        self._class_cards.append(card)

    def _refresh(self):
        """Refresh class schedule from cloud"""
        if not self.app or not self.app.api_client:
            return

        def fetch():
            schedule = self.app.api_client.get_class_schedule()
            if schedule and schedule.get('success'):
                self.after(0, lambda: self.update_schedule(schedule))

        threading.Thread(target=fetch, daemon=True).start()

    def _start_auto_refresh(self):
        """Start auto-refresh every 60 seconds"""
        self._update_time_badges()
        self.after(60000, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        """Auto-refresh tick"""
        self._refresh()
        self._start_auto_refresh()

    def _update_time_badges(self):
        """Update status badges based on current time (no API call)"""
        # This would rebuild cards if schedule is cached
        if self._schedule:
            now = datetime.now()
            # For simplicity, just refresh the whole display
            # In production, you'd update only the badge labels
