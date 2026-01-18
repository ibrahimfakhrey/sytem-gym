"""
Test script to verify all imports work correctly
"""

import sys
print(f"Python version: {sys.version}")
print()

# Test imports
errors = []

print("Testing imports...")
print("-" * 40)

try:
    import customtkinter as ctk
    print("✓ customtkinter")
except ImportError as e:
    errors.append(f"✗ customtkinter: {e}")
    print(f"✗ customtkinter: {e}")

try:
    import requests
    print("✓ requests")
except ImportError as e:
    errors.append(f"✗ requests: {e}")
    print(f"✗ requests: {e}")

try:
    from PIL import Image
    print("✓ PIL (Pillow)")
except ImportError as e:
    errors.append(f"✗ PIL: {e}")
    print(f"✗ PIL: {e}")

# pyodbc may not be available on all systems
try:
    import pyodbc
    print("✓ pyodbc")
except ImportError as e:
    print(f"⚠ pyodbc: {e} (optional on macOS)")

print("-" * 40)
print()

# Test local imports
print("Testing local modules...")
print("-" * 40)

try:
    from config import APP_NAME, APP_VERSION
    print(f"✓ config ({APP_NAME} v{APP_VERSION})")
except Exception as e:
    errors.append(f"✗ config: {e}")
    print(f"✗ config: {e}")

try:
    from ui.styles import COLORS, FONTS, configure_theme
    print("✓ ui.styles")
except Exception as e:
    errors.append(f"✗ ui.styles: {e}")
    print(f"✗ ui.styles: {e}")

try:
    from ui.components import Sidebar, StatusBar, StatusCard, ActivityLog
    print("✓ ui.components")
except Exception as e:
    errors.append(f"✗ ui.components: {e}")
    print(f"✗ ui.components: {e}")

try:
    from ui.pages import HomePage, AddMemberPage, MembersPage, SyncPage, CommandsPage, SettingsPage
    print("✓ ui.pages")
except Exception as e:
    errors.append(f"✗ ui.pages: {e}")
    print(f"✗ ui.pages: {e}")

try:
    from ui.main_window import MainWindow
    print("✓ ui.main_window")
except Exception as e:
    errors.append(f"✗ ui.main_window: {e}")
    print(f"✗ ui.main_window: {e}")

try:
    from core.file_finder import FileFinder
    print("✓ core.file_finder")
except Exception as e:
    errors.append(f"✗ core.file_finder: {e}")
    print(f"✗ core.file_finder: {e}")

try:
    from core.api_client import APIClient
    print("✓ core.api_client")
except Exception as e:
    errors.append(f"✗ core.api_client: {e}")
    print(f"✗ core.api_client: {e}")

try:
    from core.database import DatabaseManager
    print("✓ core.database")
except Exception as e:
    errors.append(f"✗ core.database: {e}")
    print(f"✗ core.database: {e}")

try:
    from core.sync_manager import SyncManager
    print("✓ core.sync_manager")
except Exception as e:
    errors.append(f"✗ core.sync_manager: {e}")
    print(f"✗ core.sync_manager: {e}")

print("-" * 40)
print()

# Summary
if errors:
    print(f"Found {len(errors)} error(s):")
    for err in errors:
        print(f"  {err}")
else:
    print("All imports successful!")
    print("\nYou can now run the application with:")
    print("  python main.py")
