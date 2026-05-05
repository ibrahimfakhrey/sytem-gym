"""
Theme — colors, fonts, spacing for v2 UI.
"""
import customtkinter as ctk

COLORS = {
    'bg':           '#0f1419',
    'bg_card':      '#1a2332',
    'bg_card_hover':'#243140',
    'border':       '#2a3a4f',
    'text':         '#e3e8ef',
    'text_muted':   '#7d8b9c',
    'primary':      '#3b82f6',
    'success':      '#10b981',
    'warning':      '#f59e0b',
    'error':        '#ef4444',
    'info':         '#06b6d4',
}

FONTS = {
    'h1':       ('Arial', 28, 'bold'),
    'h2':       ('Arial', 20, 'bold'),
    'h3':       ('Arial', 16, 'bold'),
    'body':     ('Arial', 14),
    'small':    ('Arial', 12),
    'mono':     ('Courier New', 12),
    'btn':      ('Arial', 14, 'bold'),
}


def configure():
    """Set CTk global theme."""
    ctk.set_appearance_mode('dark')
    ctk.set_default_color_theme('blue')
