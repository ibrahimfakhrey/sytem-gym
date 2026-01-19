"""
Add fake test data to the .mdb database
Run this on Windows after installing the software
"""

import pyodbc
import random
from datetime import datetime, timedelta
import os

# Arabic names for testing
FIRST_NAMES = [
    "محمد", "أحمد", "علي", "حسن", "حسين", "عمر", "خالد", "سعد", "ياسر", "طارق",
    "فاطمة", "عائشة", "مريم", "زينب", "سارة", "نور", "هدى", "ريم", "لينا", "دانا",
    "يوسف", "إبراهيم", "عبدالله", "عبدالرحمن", "سلطان", "فهد", "ناصر", "بدر", "سالم", "راشد",
    "منى", "هند", "أمل", "رنا", "غادة", "سلمى", "نجلاء", "وفاء", "إيمان", "سمية"
]

LAST_NAMES = [
    "العلي", "المحمد", "الأحمد", "الحسن", "العمري", "الخالد", "السعيد", "الناصر", "الراشد", "السالم",
    "الفهد", "البدر", "اليوسف", "الإبراهيم", "العبدالله", "الرحمن", "السلطان", "الطارق", "الياسر", "الحسين"
]

def generate_phone():
    """Generate random phone number"""
    return f"05{random.randint(10000000, 99999999)}"

def generate_date(start_year=2024, end_year=2027):
    """Generate random date"""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).strftime('%m/%d/%y 00:00:00')

def find_database():
    """Find .mdb database file"""
    # Check test_database folder first (in same directory as script)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_db = os.path.join(script_dir, "test_database", "tmkq.mdb")

    if os.path.exists(test_db):
        print(f"Found test database: {test_db}")
        return test_db

    # Common paths
    paths = [
        r"C:\Attendance\tmkq.mdb",
        r"C:\AAS\Attendance\tmkq.mdb",
        r"C:\Program Files\Attendance\tmkq.mdb",
        r"C:\Program Files (x86)\Attendance\tmkq.mdb",
        r"D:\Attendance\tmkq.mdb",
    ]

    for path in paths:
        if os.path.exists(path):
            return path

    # Ask user
    print("\nلم يتم العثور على قاعدة البيانات تلقائياً")
    print("الرجاء إدخال المسار الكامل لملف tmkq.mdb:")
    path = input("> ").strip()
    if os.path.exists(path):
        return path
    return None

def add_test_data(db_path, count=50):
    """Add test data to database"""

    # Connection string for Access
    conn_str = (
        r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
        f'DBQ={db_path};'
    )

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        print(f"✓ تم الاتصال بقاعدة البيانات: {db_path}")

        # Get existing emp_ids
        cursor.execute("SELECT emp_id FROM Employee")
        existing_ids = set(row[0] for row in cursor.fetchall())
        print(f"  الأعضاء الحاليون: {len(existing_ids)}")

        # Add new employees
        added = 0
        for i in range(count):
            # Generate unique emp_id
            emp_id = f"{random.randint(1, 99999999):08d}"
            while emp_id in existing_ids:
                emp_id = f"{random.randint(1, 99999999):08d}"
            existing_ids.add(emp_id)

            # Generate data
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            full_name = f"{first_name} {last_name}"
            phone = generate_phone()

            # Random end_date (some expired, some active)
            if random.random() < 0.2:  # 20% blocked
                end_date = generate_date(2023, 2024)  # Past date
            else:  # 80% active
                end_date = generate_date(2025, 2027)  # Future date

            hire_date = generate_date(2020, 2024)
            birth_date = generate_date(1980, 2005)

            try:
                cursor.execute("""
                    INSERT INTO Employee (emp_id, emp_name, phone_code, end_date, hire_date, birth_date, depart_id, sex)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (emp_id, full_name, phone, end_date, hire_date, birth_date, "00000001", random.choice(["0", "1"])))
                added += 1

                if added % 10 == 0:
                    print(f"  تم إضافة {added} عضو...")

            except Exception as e:
                print(f"  خطأ في إضافة {full_name}: {e}")

        conn.commit()
        print(f"\n✓ تم إضافة {added} عضو جديد بنجاح!")

        # Show total count
        cursor.execute("SELECT COUNT(*) FROM Employee")
        total = cursor.fetchone()[0]
        print(f"  إجمالي الأعضاء الآن: {total}")

        conn.close()
        return True

    except Exception as e:
        print(f"\n✗ خطأ: {e}")
        print("\nتأكد من:")
        print("  1. تثبيت Microsoft Access Database Engine")
        print("  2. المسار صحيح لملف .mdb")
        print("  3. الملف غير مفتوح في برنامج آخر")
        return False

def main():
    print("=" * 50)
    print("  إضافة بيانات اختبار لقاعدة البيانات")
    print("  Add Test Data to Database")
    print("=" * 50)
    print()

    # Find database
    db_path = find_database()
    if not db_path:
        print("✗ لم يتم العثور على قاعدة البيانات")
        input("\nاضغط Enter للخروج...")
        return

    # Ask for count
    print(f"\nكم عدد الأعضاء الوهميين تريد إضافتهم؟")
    print("(اضغط Enter للقيمة الافتراضية: 50)")
    count_input = input("> ").strip()
    count = int(count_input) if count_input.isdigit() else 50

    print(f"\nجاري إضافة {count} عضو...")
    print("-" * 50)

    success = add_test_data(db_path, count)

    print("-" * 50)
    if success:
        print("\n✓ تم بنجاح!")
        print("  الآن افتح برنامج الجيم وقم بالمزامنة")
    else:
        print("\n✗ فشلت العملية")

    input("\nاضغط Enter للخروج...")

if __name__ == "__main__":
    main()
