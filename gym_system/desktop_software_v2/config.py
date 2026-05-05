"""
Config — single JSON file at ~/.gym_bridge_v2/config.json
"""
import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / '.gym_bridge_v2'
CONFIG_FILE = CONFIG_DIR / 'config.json'

DEFAULTS = {
    # Server
    'api_url': 'https://gymsystem.pythonanywhere.com',

    # Branch (filled after registration)
    'branch_code': '',
    'branch_id': None,
    'brand_id': None,
    'branch_name': '',
    'brand_name': '',
    'is_registered': False,

    # First-time sync
    'first_sync_done': False,
    'last_sync': None,
    'id_mapping': {},  # emp_id -> web member_id

    # Local databases
    'db_path_members': '',     # backup.mdb
    'db_path_attendance': '',  # att2000.mdb
    'db_password': '',

    # Sync settings
    'sync_interval_seconds': 60,
    'auto_start_with_windows': True,
    'minimize_to_tray': True,

    # State (kept across restarts)
    'last_attendance_log_id': 0,  # highest CHECKINOUT row we've uploaded
}


def ensure_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load():
    ensure_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Merge with defaults so new keys appear
            merged = {**DEFAULTS, **data}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULTS)


def save(config):
    ensure_dir()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
