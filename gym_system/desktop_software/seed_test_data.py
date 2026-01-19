"""
Seed Test Data - Generate and insert fake data into test .mdb database
Works on Mac using mdbtools or on Windows using pyodbc
"""

import os
import sys
import csv
import random
import subprocess
from datetime import datetime, timedelta

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
    "الشمري", "العتيبي", "القحطاني", "الدوسري", "المطيري", "الحربي", "الغامدي", "الزهراني", "البلوي", "العنزي"
]

PHONE_PREFIXES = ["050", "055", "053", "054", "056", "059"]


def generate_phone():
    """Generate a random Saudi phone number"""
    prefix = random.choice(PHONE_PREFIXES)
    number = ''.join([str(random.randint(0, 9)) for _ in range(7)])
    return f"{prefix}{number}"


def generate_employees(count: int = 50) -> list:
    """Generate fake employee data"""
    employees = []

    for i in range(1, count + 1):
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
        birth_date = datetime.now() - timedelta(days=random.randint(7000, 18000))

        # 20% chance of being blocked
        if random.random() < 0.2:
            end_date = datetime.now() - timedelta(days=random.randint(1, 100))

        emp = {
            'emp_id': str(i).zfill(8),
            'card_id': str(i).zfill(10),
            'emp_name': full_name,
            'depart_id': '00000001',
            'sex': sex,
            'phone_code': generate_phone(),
            'hire_date': hire_date.strftime('%Y-%m-%d %H:%M:%S'),
            'end_date': end_date.strftime('%Y-%m-%d %H:%M:%S'),
            'birth_date': birth_date.strftime('%Y-%m-%d %H:%M:%S'),
            'no_sign': '0',
            'email': f"member{i}@gym.com",
            'address': f"عنوان العضو رقم {i}",
        }
        employees.append(emp)

    return employees


def generate_time_records(employees: list, days: int = 30) -> list:
    """Generate fake attendance records"""
    records = []
    record_id = 1

    for emp in employees:
        # Skip some blocked members
        end_date = datetime.strptime(emp['end_date'], '%Y-%m-%d %H:%M:%S')
        if end_date < datetime.now() and random.random() < 0.5:
            continue

        for day_offset in range(days):
            record_date = datetime.now() - timedelta(days=day_offset)

            # 60% chance of attendance
            if random.random() < 0.6:
                hour = random.randint(6, 22)
                minute = random.randint(0, 59)
                sign_time = record_date.replace(hour=hour, minute=minute, second=0)

                record = {
                    'clock_id': '1',
                    'card_id': emp['card_id'],
                    'emp_id': emp['emp_id'],
                    'sign_time': sign_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'mark': '0',
                    'flag': '0'
                }
                records.append(record)
                record_id += 1

    return records


def generate_departments() -> list:
    """Generate department data"""
    return [
        {'depart_id': '00000001', 'depart_name': 'الأعضاء', 'upper_depart_id': ''},
        {'depart_id': '00000002', 'depart_name': 'المدربين', 'upper_depart_id': ''},
        {'depart_id': '00000003', 'depart_name': 'الإدارة', 'upper_depart_id': ''},
    ]


def export_to_csv(data: list, filename: str, fieldnames: list):
    """Export data to CSV file"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
    print(f"Exported {len(data)} records to {filename}")


def generate_sql_inserts(employees: list, time_records: list, departments: list) -> str:
    """Generate SQL INSERT statements"""
    sql_lines = []

    # Departments
    sql_lines.append("-- Departments")
    for dept in departments:
        sql_lines.append(
            f"INSERT INTO Depart (depart_id, depart_name, upper_depart_id) "
            f"VALUES ('{dept['depart_id']}', '{dept['depart_name']}', '{dept['upper_depart_id']}');"
        )

    sql_lines.append("\n-- Employees")
    for emp in employees:
        sql_lines.append(
            f"INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, "
            f"hire_date, end_date, birth_date, no_sign, email, address) VALUES ("
            f"'{emp['emp_id']}', '{emp['card_id']}', '{emp['emp_name']}', '{emp['depart_id']}', "
            f"'{emp['sex']}', '{emp['phone_code']}', #{emp['hire_date']}#, #{emp['end_date']}#, "
            f"#{emp['birth_date']}#, {emp['no_sign']}, '{emp['email']}', '{emp['address']}');"
        )

    sql_lines.append("\n-- Time Records (first 100 only)")
    for record in time_records[:100]:
        sql_lines.append(
            f"INSERT INTO TimeRecords (clock_id, card_id, emp_id, sign_time, mark, flag) VALUES ("
            f"{record['clock_id']}, '{record['card_id']}', '{record['emp_id']}', "
            f"#{record['sign_time']}#, {record['mark']}, {record['flag']});"
        )

    return '\n'.join(sql_lines)


def try_windows_insert(db_path: str, employees: list, time_records: list, departments: list) -> bool:
    """Try to insert data using pyodbc (Windows)"""
    try:
        import pyodbc

        driver = "Microsoft Access Driver (*.mdb, *.accdb)"
        conn_str = f"DRIVER={{{driver}}};DBQ={db_path};"

        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        print("Connected to database. Inserting data...")

        # Insert departments
        for dept in departments:
            try:
                cursor.execute(
                    "INSERT INTO Depart (depart_id, depart_name, upper_depart_id) VALUES (?, ?, ?)",
                    (dept['depart_id'], dept['depart_name'], dept['upper_depart_id'] or None)
                )
            except:
                pass

        # Insert employees
        for emp in employees:
            cursor.execute(
                """INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code,
                   hire_date, end_date, birth_date, no_sign, email, address)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (emp['emp_id'], emp['card_id'], emp['emp_name'], emp['depart_id'],
                 emp['sex'], emp['phone_code'], emp['hire_date'], emp['end_date'],
                 emp['birth_date'], int(emp['no_sign']), emp['email'], emp['address'])
            )

        # Insert time records
        for record in time_records:
            cursor.execute(
                """INSERT INTO TimeRecords (clock_id, card_id, emp_id, sign_time, mark, flag)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (int(record['clock_id']), record['card_id'], record['emp_id'],
                 record['sign_time'], int(record['mark']), int(record['flag']))
            )

        conn.commit()
        conn.close()
        print(f"Successfully inserted {len(employees)} employees and {len(time_records)} time records!")
        return True

    except ImportError:
        print("pyodbc not available (not on Windows)")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    print("=" * 60)
    print("  Test Data Generator for Gym Management System")
    print("=" * 60)
    print()

    # Determine paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_db_dir = os.path.join(script_dir, "test_database")
    db_path = os.path.join(test_db_dir, "test_attendance.mdb")

    # Generate data
    print("Generating fake data...")
    departments = generate_departments()
    employees = generate_employees(50)
    time_records = generate_time_records(employees, 30)

    print(f"  - {len(departments)} departments")
    print(f"  - {len(employees)} employees")
    print(f"  - {len(time_records)} time records")

    # Export to CSV
    print("\nExporting to CSV files...")
    csv_dir = os.path.join(test_db_dir, "csv_data")
    os.makedirs(csv_dir, exist_ok=True)

    export_to_csv(departments, os.path.join(csv_dir, "departments.csv"),
                  ['depart_id', 'depart_name', 'upper_depart_id'])
    export_to_csv(employees, os.path.join(csv_dir, "employees.csv"),
                  ['emp_id', 'card_id', 'emp_name', 'depart_id', 'sex', 'phone_code',
                   'hire_date', 'end_date', 'birth_date', 'no_sign', 'email', 'address'])
    export_to_csv(time_records, os.path.join(csv_dir, "time_records.csv"),
                  ['clock_id', 'card_id', 'emp_id', 'sign_time', 'mark', 'flag'])

    # Generate SQL file
    print("\nGenerating SQL file...")
    sql_content = generate_sql_inserts(employees, time_records, departments)
    sql_path = os.path.join(test_db_dir, "insert_data.sql")
    with open(sql_path, 'w', encoding='utf-8') as f:
        f.write(sql_content)
    print(f"SQL file saved to: {sql_path}")

    # Try Windows insert if database exists
    if os.path.exists(db_path):
        print(f"\nAttempting to insert data into: {db_path}")
        if try_windows_insert(db_path, employees, time_records, departments):
            print("\nData inserted successfully!")
        else:
            print("\nCould not insert data directly.")
            print("Please run this script on Windows, or import the CSV files manually.")
    else:
        print(f"\nDatabase not found at: {db_path}")
        print("Please create the database first using create_test_database.py")

    print("\n" + "=" * 60)
    print("  Files created in test_database folder:")
    print("  - csv_data/employees.csv")
    print("  - csv_data/departments.csv")
    print("  - csv_data/time_records.csv")
    print("  - insert_data.sql")
    print("=" * 60)


if __name__ == "__main__":
    main()
