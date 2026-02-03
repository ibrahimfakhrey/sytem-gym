# Build Instructions - Gym Management System

## كيفية إنشاء ملف التثبيت (Windows Installer)

### المتطلبات
1. Windows 10/11
2. Python 3.9 أو أحدث
3. PyInstaller
4. Inno Setup (مجاني) - https://jrsoftware.org/isinfo.php

---

## الخطوة 1: تثبيت المتطلبات

```cmd
pip install pyinstaller customtkinter pyodbc requests Pillow
```

---

## الخطوة 2: إنشاء أيقونة التطبيق

ضع ملف أيقونة بصيغة `.ico` في مجلد `assets`:
- `assets/icon.ico` (256x256 pixels recommended)

يمكنك تحويل صورة PNG إلى ICO من هذا الموقع:
https://convertio.co/png-ico/

---

## الخطوة 3: إنشاء ملف EXE

افتح Command Prompt في مجلد `desktop_software` ونفذ:

```cmd
pyinstaller GymSystem.spec
```

سيتم إنشاء الملف في: `dist/GymSystem.exe`

---

## الخطوة 4: إنشاء ملف التثبيت (Installer)

1. قم بتثبيت Inno Setup من: https://jrsoftware.org/isdl.php

2. افتح ملف `installer/setup.iss` باستخدام Inno Setup

3. اضغط على Build > Compile (أو F9)

4. سيتم إنشاء ملف التثبيت في: `dist/installer/GymSystem_Setup_1.0.0.exe`

---

## الخطوة 5: توزيع البرنامج

أرسل ملف `GymSystem_Setup_1.0.0.exe` للمستخدمين

عند التثبيت:
- سيتم تثبيت البرنامج في `C:\Program Files\GymSystem`
- سيتم إنشاء اختصار على سطح المكتب
- سيتم إنشاء اختصار في قائمة Start

---

## ملاحظات هامة

### بخصوص قاعدة البيانات (.mdb)
- يجب أن يكون Microsoft Access Database Engine مثبتاً
- قم بتحميله من: https://www.microsoft.com/en-us/download/details.aspx?id=54920

### بخصوص الـ Firewall
- قد يحتاج البرنامج إلى إذن للاتصال بالإنترنت
- السماح للبرنامج في Windows Firewall

---

## هيكل الملفات بعد البناء

```
desktop_software/
├── dist/
│   ├── GymSystem.exe           <- الملف التنفيذي
│   └── installer/
│       └── GymSystem_Setup_1.0.0.exe  <- ملف التثبيت
├── build/                      <- ملفات مؤقتة (يمكن حذفها)
└── ...
```

---

## الأوامر السريعة

```cmd
# تثبيت المتطلبات
pip install -r requirements.txt pyinstaller

# بناء EXE
pyinstaller GymSystem.spec

# تنظيف ملفات البناء
rmdir /s /q build
rmdir /s /q __pycache__
```
