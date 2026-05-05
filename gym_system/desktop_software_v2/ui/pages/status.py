"""
Status Page — live status, stats, manual sync.
"""
import customtkinter as ctk
from datetime import datetime

from ..theme import COLORS, FONTS


class StatusPage(ctk.CTkFrame):
    def __init__(self, parent, controller=None, **kwargs):
        super().__init__(parent, fg_color=COLORS['bg'], **kwargs)
        self.controller = controller
        self._build()

    def _build(self):
        # Header — branch + brand
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.pack(fill='x', padx=24, pady=(20, 0))

        self.branch_label = ctk.CTkLabel(header, text='', font=FONTS['h2'],
                                          text_color=COLORS['text'])
        self.branch_label.pack(anchor='e')

        self.brand_label = ctk.CTkLabel(header, text='', font=FONTS['body'],
                                         text_color=COLORS['text_muted'])
        self.brand_label.pack(anchor='e', pady=(2, 0))

        # Connection status row
        conn_card = ctk.CTkFrame(self, fg_color=COLORS['bg_card'],
                                 corner_radius=12, border_width=1,
                                 border_color=COLORS['border'])
        conn_card.pack(fill='x', padx=24, pady=(20, 0))

        conn_inner = ctk.CTkFrame(conn_card, fg_color='transparent')
        conn_inner.pack(padx=20, pady=16, fill='x')

        ctk.CTkLabel(conn_inner, text='حالة النظام', font=FONTS['h3'],
                     text_color=COLORS['text']).pack(anchor='e', pady=(0, 12))

        self.server_status = self._make_row(conn_inner, 'السيرفر',
                                             '⏳ جاري التحقق...', 'info')
        self.db_status = self._make_row(conn_inner, 'قاعدة البيانات',
                                         '⏳ جاري التحقق...', 'info')
        self.sync_status = self._make_row(conn_inner, 'المزامنة',
                                           '— لم تبدأ بعد', 'warning')

        # Stats grid
        stats_card = ctk.CTkFrame(self, fg_color=COLORS['bg_card'],
                                   corner_radius=12, border_width=1,
                                   border_color=COLORS['border'])
        stats_card.pack(fill='x', padx=24, pady=(16, 0))

        stats_inner = ctk.CTkFrame(stats_card, fg_color='transparent')
        stats_inner.pack(padx=20, pady=16, fill='x')

        ctk.CTkLabel(stats_inner, text='📊 الإحصائيات', font=FONTS['h3'],
                     text_color=COLORS['text']).pack(anchor='e', pady=(0, 12))

        self.stat_members = self._make_stat(stats_inner, 'إجمالي الأعضاء', '—')
        self.stat_attendance = self._make_stat(stats_inner, 'سجلات اليوم', '—')
        self.stat_last_sync = self._make_stat(stats_inner, 'آخر مزامنة', '—')

        # Activity log
        log_card = ctk.CTkFrame(self, fg_color=COLORS['bg_card'],
                                 corner_radius=12, border_width=1,
                                 border_color=COLORS['border'])
        log_card.pack(fill='both', expand=True, padx=24, pady=(16, 0))

        log_inner = ctk.CTkFrame(log_card, fg_color='transparent')
        log_inner.pack(padx=20, pady=16, fill='both', expand=True)

        ctk.CTkLabel(log_inner, text='📜 سجل النشاط', font=FONTS['h3'],
                     text_color=COLORS['text']).pack(anchor='e', pady=(0, 12))

        self.log_box = ctk.CTkTextbox(
            log_inner, font=FONTS['mono'],
            fg_color=COLORS['bg'], text_color=COLORS['text'],
            height=160, wrap='word',
        )
        self.log_box.pack(fill='both', expand=True)
        self.log_box.configure(state='disabled')

        # Action buttons
        action_frame = ctk.CTkFrame(self, fg_color='transparent')
        action_frame.pack(fill='x', padx=24, pady=16)

        self.sync_btn = ctk.CTkButton(
            action_frame, text='🔄 مزامنة الآن',
            font=FONTS['btn'], height=44, width=160,
            fg_color=COLORS['primary'], hover_color='#2563eb',
            command=self._on_sync,
        )
        self.sync_btn.pack(side='right', padx=(0, 8))

        self.settings_btn = ctk.CTkButton(
            action_frame, text='⚙ الإعدادات',
            font=FONTS['btn'], height=44, width=140,
            fg_color=COLORS['bg_card'], hover_color=COLORS['bg_card_hover'],
            text_color=COLORS['text'], border_width=1, border_color=COLORS['border'],
            command=self._on_settings,
        )
        self.settings_btn.pack(side='right')

    def _make_row(self, parent, label, value, level):
        row = ctk.CTkFrame(parent, fg_color='transparent')
        row.pack(fill='x', pady=4)

        ctk.CTkLabel(row, text=label, font=FONTS['body'],
                     text_color=COLORS['text_muted'], width=140, anchor='e').pack(side='right', padx=(8, 0))
        val = ctk.CTkLabel(row, text=value, font=FONTS['body'],
                            text_color=self._level_color(level), anchor='e')
        val.pack(side='right')
        return val

    def _make_stat(self, parent, label, value):
        row = ctk.CTkFrame(parent, fg_color='transparent')
        row.pack(fill='x', pady=2)
        ctk.CTkLabel(row, text=label, font=FONTS['small'],
                     text_color=COLORS['text_muted'], anchor='e').pack(side='right', padx=(8, 0))
        val = ctk.CTkLabel(row, text=value, font=FONTS['body'],
                            text_color=COLORS['text'], anchor='e')
        val.pack(side='right')
        return val

    def _level_color(self, level):
        return {
            'info': COLORS['info'],
            'success': COLORS['success'],
            'warning': COLORS['warning'],
            'error': COLORS['error'],
        }.get(level, COLORS['text'])

    # ── Public methods (called by controller) ──
    def update_branch_info(self, branch_name, brand_name):
        self.branch_label.configure(text=branch_name or '')
        self.brand_label.configure(text=brand_name or '')

    def update_server_status(self, ok, msg=None):
        if ok:
            self.server_status.configure(text=f'✓ {msg or "متصل"}',
                                          text_color=COLORS['success'])
        else:
            self.server_status.configure(text=f'✗ {msg or "غير متصل"}',
                                          text_color=COLORS['error'])

    def update_db_status(self, ok, msg=None):
        if ok:
            self.db_status.configure(text=f'✓ {msg or "متصلة"}',
                                      text_color=COLORS['success'])
        else:
            self.db_status.configure(text=f'✗ {msg or "غير متصلة"}',
                                      text_color=COLORS['warning'])

    def update_sync_status(self, ok, msg=None):
        if ok:
            self.sync_status.configure(text=f'✓ {msg or "نشطة"}',
                                        text_color=COLORS['success'])
        else:
            self.sync_status.configure(text=f'⏸ {msg or "متوقفة"}',
                                        text_color=COLORS['warning'])

    def update_stats(self, stats: dict):
        if 'members_total' in stats:
            self.stat_members.configure(text=f'{stats["members_total"]:,}')
        if 'attendance_today' in stats:
            self.stat_attendance.configure(text=f'{stats["attendance_today"]:,}')
        if stats.get('last_sync'):
            try:
                ts = stats['last_sync'].replace('Z', '').split('+')[0]
                dt = datetime.fromisoformat(ts)
                self.stat_last_sync.configure(text=dt.strftime('%H:%M:%S'))
            except Exception:
                self.stat_last_sync.configure(text=stats['last_sync'])

    def add_log(self, message, level='info'):
        ts = datetime.now().strftime('%H:%M:%S')
        prefix_map = {'info': 'ℹ', 'success': '✓', 'warning': '⚠', 'error': '✗'}
        prefix = prefix_map.get(level, '•')

        self.log_box.configure(state='normal')
        self.log_box.insert('1.0', f'{ts}  {prefix}  {message}\n')
        # Keep only last ~50 lines
        all_lines = self.log_box.get('1.0', 'end').splitlines()
        if len(all_lines) > 50:
            self.log_box.delete(f'{50}.0', 'end')
        self.log_box.configure(state='disabled')

    def _on_sync(self):
        if self.controller:
            self.controller.sync_now()

    def _on_settings(self):
        if self.controller:
            self.controller.show_settings()
