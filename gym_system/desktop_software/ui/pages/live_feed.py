"""
Live Attendance Feed Page - Real-time fingerprint scan events
"""

import customtkinter as ctk
from datetime import datetime


class LiveFeedPage(ctk.CTkFrame):
    """Real-time attendance feed from fingerprint device"""

    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._events = []
        self._max_events = 100
        self._stats = {'today': 0, 'blocked': 0, 'late': 0}
        self._create_widgets()

    def _create_widgets(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(header, text="📡 البث المباشر",
                     font=("Arial", 24, "bold"), anchor="e").pack(side="right")

        clear_btn = ctk.CTkButton(header, text="مسح", width=80,
                                   command=self.clear_events,
                                   fg_color="#2a3a4a", hover_color="#3a4a5a")
        clear_btn.pack(side="left")

        # Stats strip
        stats_frame = ctk.CTkFrame(self, fg_color="#1a2332", corner_radius=10)
        stats_frame.pack(fill="x", padx=20, pady=(0, 10))

        self._stat_cards = {}
        stats_data = [
            ('today', 'الحضور اليوم', '#4caf50'),
            ('blocked', 'محظورين', '#f44336'),
            ('late', 'متأخرين', '#ff9800')
        ]

        for key, label, color in stats_data:
            card = ctk.CTkFrame(stats_frame, fg_color="transparent")
            card.pack(side="right", expand=True, padx=15, pady=10)

            value_label = ctk.CTkLabel(card, text="0",
                                        font=("Arial", 28, "bold"),
                                        text_color=color)
            value_label.pack()
            ctk.CTkLabel(card, text=label, font=("Arial", 11),
                        text_color="#b0bec5").pack()
            self._stat_cards[key] = value_label

        # Events list
        events_frame = ctk.CTkFrame(self, fg_color="#1a2332", corner_radius=10)
        events_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        ctk.CTkLabel(events_frame, text="سجل البصمات",
                     font=("Arial", 14, "bold"), anchor="e").pack(
                         fill="x", padx=15, pady=(10, 5))

        self._events_container = ctk.CTkScrollableFrame(
            events_frame, fg_color="transparent")
        self._events_container.pack(fill="both", expand=True, padx=5, pady=(0, 10))

        # Empty state
        self._empty_label = ctk.CTkLabel(
            self._events_container,
            text="لا توجد بيانات بصمة حتى الآن\nسيتم عرض البيانات عند مزامنة البصمة",
            font=("Arial", 14), text_color="#b0bec5", justify="center")
        self._empty_label.pack(pady=50)

    def add_event(self, event: dict):
        """Add a fingerprint scan event to the feed"""
        # Remove empty state label
        if self._empty_label:
            self._empty_label.destroy()
            self._empty_label = None

        status = event.get('status', 'allowed')
        status_text = event.get('status_text', 'مسموح')
        name = event.get('name', '')
        emp_id = event.get('emp_id', '')
        time_str = event.get('time', datetime.now().strftime('%H:%M:%S'))

        # Colors and icons
        if status == 'blocked':
            bg_color = '#3d1515'
            dot_color = '#f44336'
            icon = '🚫'
            self._stats['blocked'] += 1
        elif status == 'late':
            bg_color = '#3d3015'
            dot_color = '#ff9800'
            icon = '⏰'
            self._stats['late'] += 1
        else:
            bg_color = '#153d1a'
            dot_color = '#4caf50'
            icon = '✅'

        self._stats['today'] += 1

        # Create event row
        row = ctk.CTkFrame(self._events_container, fg_color=bg_color,
                           corner_radius=8, height=50)
        row.pack(fill="x", padx=5, pady=2, before=self._events_container.winfo_children()[0]
                 if self._events_container.winfo_children() else None)
        row.pack_propagate(False)

        # Status dot
        ctk.CTkLabel(row, text=icon, font=("Arial", 16), width=30).pack(
            side="right", padx=(10, 5))

        # Name and ID
        info_frame = ctk.CTkFrame(row, fg_color="transparent")
        info_frame.pack(side="right", fill="x", expand=True, padx=5)

        ctk.CTkLabel(info_frame, text=name, font=("Arial", 13, "bold"),
                     anchor="e").pack(side="right")
        ctk.CTkLabel(info_frame, text=f"  ({emp_id})", font=("Arial", 10),
                     text_color="#b0bec5", anchor="e").pack(side="right")

        # Status text
        ctk.CTkLabel(row, text=status_text, font=("Arial", 11),
                     text_color=dot_color, width=100).pack(side="left", padx=5)

        # Time
        ctk.CTkLabel(row, text=time_str, font=("Arial", 11),
                     text_color="#b0bec5", width=70).pack(side="left", padx=(5, 10))

        # Track events
        self._events.append(row)

        # Trim old events
        while len(self._events) > self._max_events:
            old = self._events.pop(0)
            old.destroy()

        # Update stats
        self._update_stats()

    def clear_events(self):
        """Clear all events"""
        for widget in self._events_container.winfo_children():
            widget.destroy()
        self._events.clear()
        self._stats = {'today': 0, 'blocked': 0, 'late': 0}
        self._update_stats()

        # Show empty state again
        self._empty_label = ctk.CTkLabel(
            self._events_container,
            text="لا توجد بيانات بصمة حتى الآن",
            font=("Arial", 14), text_color="#b0bec5", justify="center")
        self._empty_label.pack(pady=50)

    def _update_stats(self):
        """Update stat cards"""
        for key, label in self._stat_cards.items():
            label.configure(text=str(self._stats.get(key, 0)))
