"""
Create Test Database - Creates a test .mdb database with fake data
Run this script on Windows where MS Access drivers are available.
"""

import os
import sys
import shutil
import random
from datetime import datetime, timedelta

# Try to import pyodbc
try:
    import pyodbc
except ImportError:
    print("ERROR: pyodbc is required. Install with: pip install pyodbc")
    sys.exit(1)


# Arabic names for fake data
ARABIC_FIRST_NAMES_MALE = [
    "محمد", "أحمد", "علي", "حسن", "حسين", "عمر", "خالد", "سعيد", "يوسف", "إبراهيم",
    "عبدالله", "عبدالرحمن", "فهد", "سلطان", "ناصر", "فيصل", "تركي", "بندر", "سعود", "نايف",
    "مشاري", "راشد", "ماجد", "وليد", "طارق", "زياد", "هاني", "رامي", "كريم", "ياسر"
]

ARABIC_FIRST_NAMES_FEMALE = [
    "فاطمة", "عائشة", "مريم", "زينب", "نورة", "سارة", "هند", "لمى", "دانة", "ريم",
    "أمل", "منى", "هدى", "سلمى", "ليلى", "جميلة", "خديجة", "رقية", "أسماء", "شيماء"
]

ARABIC_LAST_NAMES = [
    "العلي", "المحمد", "الأحمد", "الحسن", "العمر", "الخالد", "السعيد", "الناصر", "الفهد", "السلطان",
    "الشمري", "العتيبي", "القحطاني", "الدوسري", "المطيري", "الحربي", "الغامدي", "الزهراني", "البلوي", "العنزي",
    "الرشيدي", "السبيعي", "الهاجري", "المري", "الكويتي", "البحريني", "الإماراتي", "القطري", "العماني", "اليمني"
]

PHONE_PREFIXES = ["050", "055", "053", "054", "056", "059", "051", "058"]


def get_connection_string(db_path: str, password: str = None) -> str:
    """Get ODBC connection string"""
    driver = "Microsoft Access Driver (*.mdb, *.accdb)"
    if password:
        return f"DRIVER={{{driver}}};DBQ={db_path};PWD={password};"
    return f"DRIVER={{{driver}}};DBQ={db_path};"


def create_blank_database(db_path: str) -> bool:
    """Create a blank .mdb database using ADOX"""
    try:
        import win32com.client

        # Use ADOX to create a new database
        catalog = win32com.client.Dispatch("ADOX.Catalog")
        conn_str = f"Provider=Microsoft.Jet.OLEDB.4.0;Data Source={db_path};"
        catalog.Create(conn_str)
        print(f"Created blank database: {db_path}")
        return True
    except ImportError:
        print("win32com not available, trying alternative method...")
    except Exception as e:
        print(f"ADOX method failed: {e}")

    # Alternative: Copy from template if available
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_paths = [
        os.path.join(script_dir, "template.mdb"),
        os.path.join(script_dir, "..", "Database", "Attendancear", "BackUpData", "Init.mdb"),
        r"C:\AAS\BackUpData\Init.mdb",
    ]

    for template_path in template_paths:
        if os.path.exists(template_path):
            try:
                shutil.copy(template_path, db_path)
                print(f"Created database from template: {template_path}")
                return True
            except Exception as e:
                print(f"Failed to copy template: {e}")

    print("ERROR: Could not create blank database.")
    print("Please copy a blank .mdb file to the script directory as 'template.mdb'")
    return False


def create_tables(conn) -> bool:
    """Create the required tables"""
    cursor = conn.cursor()

    # Check if Employee table exists
    tables = [t.table_name for t in cursor.tables(tableType='TABLE')]

    if 'Employee' not in tables:
        print("Creating Employee table...")
        cursor.execute("""
            CREATE TABLE Employee (
                emp_id VARCHAR(20) PRIMARY KEY,
                card_id VARCHAR(20),
                emp_name VARCHAR(100),
                phone_code VARCHAR(50),
                sex VARCHAR(10),
                birth_date DATETIME,
                hire_date DATETIME,
                end_date DATETIME,
                email VARCHAR(100),
                address VARCHAR(200),
                depart_id VARCHAR(20),
                memo VARCHAR(500)
            )
        """)
        conn.commit()
        print("Employee table created.")
    else:
        print("Employee table already exists.")

    if 'TimeRecords' not in tables:
        print("Creating TimeRecords table...")
        cursor.execute("""
            CREATE TABLE TimeRecords (
                clock_id COUNTER PRIMARY KEY,
                card_id VARCHAR(20),
                emp_id VARCHAR(20),
                sign_time DATETIME,
                mark VARCHAR(10),
                flag VARCHAR(10)
            )
        """)
        conn.commit()
        print("TimeRecords table created.")
    else:
        print("TimeRecords table already exists.")

    if 'Department' not in tables:
        print("Creating Department table...")
        cursor.execute("""
            CREATE TABLE Department (
                depart_id VARCHAR(20) PRIMARY KEY,
                depart_name VARCHAR(100),
                parent_id VARCHAR(20)
            )
        """)
        conn.commit()
        print("Department table created.")
    else:
        print("Department table already exists.")

    return True


def generate_phone():
    """Generate a random phone number"""
    prefix = random.choice(PHONE_PREFIXES)
    number = ''.join([str(random.randint(0, 9)) for _ in range(7)])
    return f"{prefix}{number}"


def generate_employee(emp_id: int) -> dict:
    """Generate a fake employee"""
    is_male = random.random() > 0.3  # 70% male

    if is_male:
        first_name = random.choice(ARABIC_FIRST_NAMES_MALE)
        sex = "0"  # Male
    else:
        first_name = random.choice(ARABIC_FIRST_NAMES_FEMALE)
        sex = "1"  # Female

    last_name = random.choice(ARABIC_LAST_NAMES)
    full_name = f"{first_name} {last_name}"

    # Generate dates
    hire_date = datetime.now() - timedelta(days=random.randint(30, 1000))
    end_date = datetime.now() + timedelta(days=random.randint(30, 365))
    birth_date = datetime.now() - timedelta(days=random.randint(7000, 18000))  # 19-50 years old

    # 20% chance of being blocked (end_date in past)
    if random.random() < 0.2:
        end_date = datetime.now() - timedelta(days=random.randint(1, 100))

    return {
        'emp_id': str(emp_id).zfill(8),
        'card_id': str(emp_id).zfill(10),
        'emp_name': full_name,
        'phone_code': generate_phone(),
        'sex': sex,
        'birth_date': birth_date,
        'hire_date': hire_date,
        'end_date': end_date,
        'email': f"member{emp_id}@gym.com",
        'address': f"عنوان العضو رقم {emp_id}",
        'depart_id': '00000001',
        'memo': ''
    }


def generate_time_record(emp: dict, record_date: datetime) -> dict:
    """Generate a fake time record"""
    # Random check-in time between 6 AM and 10 PM
    hour = random.randint(6, 22)
    minute = random.randint(0, 59)
    sign_time = record_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    return {
        'card_id': emp['card_id'],
        'emp_id': emp['emp_id'],
        'sign_time': sign_time,
        'mark': '0',
        'flag': '0'
    }


def seed_departments(conn):
    """Seed department data"""
    cursor = conn.cursor()

    departments = [
        ('00000001', 'الأعضاء', None),
        ('00000002', 'المدربين', None),
        ('00000003', 'الإدارة', None),
    ]

    for dept in departments:
        try:
            cursor.execute(
                "INSERT INTO Department (depart_id, depart_name, parent_id) VALUES (?, ?, ?)",
                dept
            )
        except:
            pass  # Ignore if already exists

    conn.commit()
    print(f"Seeded {len(departments)} departments.")


def seed_employees(conn, count: int = 50):
    """Seed employee/member data"""
    cursor = conn.cursor()
    employees = []

    for i in range(1, count + 1):
        emp = generate_employee(i)
        employees.append(emp)

        try:
            cursor.execute("""
                INSERT INTO Employee (emp_id, card_id, emp_name, phone_code, sex,
                                     birth_date, hire_date, end_date, email, address,
                                     depart_id, memo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                emp['emp_id'],
                emp['card_id'],
                emp['emp_name'],
                emp['phone_code'],
                emp['sex'],
                emp['birth_date'],
                emp['hire_date'],
                emp['end_date'],
                emp['email'],
                emp['address'],
                emp['depart_id'],
                emp['memo']
            ))
        except Exception as e:
            print(f"Error inserting employee {i}: {e}")

    conn.commit()
    print(f"Seeded {count} employees/members.")
    return employees


def seed_time_records(conn, employees: list, days: int = 30):
    """Seed time records (attendance)"""
    cursor = conn.cursor()
    record_count = 0

    for emp in employees:
        # Skip blocked members for recent records
        end_date = emp['end_date']
        if end_date < datetime.now():
            continue

        # Generate 0-2 records per day for the last N days
        for day_offset in range(days):
            record_date = datetime.now() - timedelta(days=day_offset)

            # 60% chance of attendance each day
            if random.random() < 0.6:
                records_today = random.randint(1, 2)
                for _ in range(records_today):
                    record = generate_time_record(emp, record_date)
                    try:
                        cursor.execute("""
                            INSERT INTO TimeRecords (card_id, emp_id, sign_time, mark, flag)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            record['card_id'],
                            record['emp_id'],
                            record['sign_time'],
                            record['mark'],
                            record['flag']
                        ))
                        record_count += 1
                    except Exception as e:
                        pass  # Ignore duplicates

    conn.commit()
    print(f"Seeded {record_count} time records.")


def main():
    """Main function"""
    print("=" * 60)
    print("  Test Database Creator for Gym Management System")
    print("=" * 60)
    print()

    # Determine output path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_db_dir = os.path.join(script_dir, "test_database")

    # Create test_database directory if not exists
    if not os.path.exists(test_db_dir):
        os.makedirs(test_db_dir)

    db_path = os.path.join(test_db_dir, "test_attendance.mdb")

    # Remove existing test database
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing test database.")

    # Create blank database
    print(f"\nCreating database at: {db_path}")
    if not create_blank_database(db_path):
        print("\nAlternative: Creating database using pyodbc...")
        # Try using pyodbc to create
        try:
            conn_str = get_connection_string(db_path)
            # This won't work to create, but let's try
            print("ERROR: Cannot create blank .mdb file programmatically without ADOX.")
            print("\nPlease do one of the following:")
            print("1. Copy a blank .mdb file to this directory as 'template.mdb'")
            print("2. Install pywin32: pip install pywin32")
            print("3. Create a blank database manually in MS Access")
            return
        except:
            pass

    # Connect to database
    print("\nConnecting to database...")
    try:
        conn_str = get_connection_string(db_path)
        conn = pyodbc.connect(conn_str)
        print("Connected successfully!")
    except Exception as e:
        print(f"Connection error: {e}")
        return

    # Create tables
    print("\nCreating tables...")
    create_tables(conn)

    # Seed data
    print("\nSeeding data...")
    seed_departments(conn)
    employees = seed_employees(conn, count=50)
    seed_time_records(conn, employees, days=30)

    # Close connection
    conn.close()

    print("\n" + "=" * 60)
    print("  Database created successfully!")
    print(f"  Location: {db_path}")
    print("  No password required.")
    print("=" * 60)
    print("\nYou can now use this database in the Gym Management System.")
    print("Go to Settings and select this database file.")


if __name__ == "__main__":
    main()
