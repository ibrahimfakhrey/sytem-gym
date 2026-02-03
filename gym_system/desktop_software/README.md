# Gym Management System - Desktop Software
# نظام إدارة الجيم - برنامج سطح المكتب

## Quick Start (Windows) - البدء السريع

### Option 1: Run the Build Script
1. Double-click `build_windows.bat`
2. Wait for the build to complete
3. Find the installer at: `dist\installer\GymSystem_Setup_1.0.0.exe`

### Option 2: Manual Build
```cmd
pip install -r requirements.txt
pyinstaller GymSystem.spec
```

---

## Requirements - المتطلبات

- Windows 10/11
- Python 3.9+
- Microsoft Access Database Engine (for .mdb files)
  Download: https://www.microsoft.com/en-us/download/details.aspx?id=54920

---

## Installation - التثبيت

1. Run `GymSystem_Setup_1.0.0.exe`
2. Click "Next" through the wizard
3. Choose installation location (default: C:\Program Files\GymSystem)
4. Check "Create desktop shortcut"
5. Click "Install"
6. Click "Finish"

---

## Features - المميزات

- 🔄 Auto-sync with web app every 30 seconds
- 👥 View and manage gym members
- ➕ Add new members to fingerprint system
- 🚫 Block/Unblock members
- 📋 Execute commands from web app
- 🔍 Auto-detect .mdb database files

---

## First Run - التشغيل الأول

1. Open the app from desktop shortcut
2. Go to Settings (الإعدادات)
3. Click "Auto-detect database" or browse manually
4. Enter your API key (from web app)
5. Save settings
6. Sync will start automatically

---

## Support - الدعم

Web App: https://gymsystem.pythonanywhere.com
