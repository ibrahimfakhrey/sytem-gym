# Configuration settings for Gym Bridge Software

import os
import json

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
    'border': '#2a3a4a'
}

# App settings
APP_NAME = "نظام إدارة الجيم"
APP_VERSION = "1.0.0"
SYNC_INTERVAL = 30  # seconds

# Default API settings
DEFAULT_API_URL = "https://gymsystem.pythonanywhere.com"
DEFAULT_BRAND_ID = 1

# Config file path
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".gym_bridge")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def ensure_config_dir():
    """Ensure config directory exists"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)


def load_config():
    """Load configuration from file"""
    ensure_config_dir()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        'api_url': DEFAULT_API_URL,
        'api_key': '',
        'brand_id': DEFAULT_BRAND_ID,
        'database_path': '',
        'backup_database_path': '',
        'sync_interval': SYNC_INTERVAL,
        'auto_start': False,
        'minimize_to_tray': True,
        'first_setup_done': False
    }


def save_config(config):
    """Save configuration to file"""
    ensure_config_dir()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
