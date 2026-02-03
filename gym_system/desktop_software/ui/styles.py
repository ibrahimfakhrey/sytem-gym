"""
Styles and theme configuration for the application
"""

# Colors - Dark Blue Professional Theme
COLORS = {
    'primary': '#1a237e',
    'secondary': '#303f9f',
    'accent': '#448aff',
    'background': '#0d1421',
    'card_bg': '#1a2332',
    'sidebar_bg': '#0f1620',
    'text_primary': '#ffffff',
    'text_secondary': '#b0bec5',
    'success': '#4caf50',
    'warning': '#ff9800',
    'error': '#f44336',
    'border': '#2a3a4a',
    'input_bg': '#1e293b',
    'hover': '#2a3a5a'
}

# Fonts
FONTS = {
    'title': ('Arial', 24, 'bold'),
    'heading': ('Arial', 18, 'bold'),
    'subheading': ('Arial', 14, 'bold'),
    'body': ('Arial', 12),
    'small': ('Arial', 10),
    'button': ('Arial', 12, 'bold')
}

# Dimensions
DIMENSIONS = {
    'sidebar_width': 200,
    'card_padding': 15,
    'button_height': 40,
    'input_height': 35,
    'border_radius': 8
}


def configure_theme():
    """Configure customtkinter theme"""
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
