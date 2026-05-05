"""
Main Window — single window, switches between Setup / Status / Settings.
"""
import customtkinter as ctk

from .theme import COLORS, configure
from .pages import SetupPage, StatusPage, SettingsPage


class MainWindow(ctk.CTk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller

        configure()

        self.title('نظام إدارة الجيم')
        self.geometry('900x700')
        self.minsize(800, 600)
        self.configure(fg_color=COLORS['bg'])

        # Container
        self.container = ctk.CTkFrame(self, fg_color=COLORS['bg'])
        self.container.pack(fill='both', expand=True)

        self.pages = {}
        self.current_page = None

    def create_pages(self):
        self.pages['setup'] = SetupPage(self.container, controller=self.controller)
        self.pages['status'] = StatusPage(self.container, controller=self.controller)
        self.pages['settings'] = SettingsPage(self.container, controller=self.controller)

    def show(self, page_name):
        if self.current_page:
            self.current_page.pack_forget()
        page = self.pages.get(page_name)
        if not page:
            return
        page.pack(fill='both', expand=True)
        self.current_page = page

    def set_title_for_branch(self, branch_name, brand_name):
        if branch_name and brand_name:
            self.title(f'نظام إدارة الجيم — {branch_name} | {brand_name}')
