"""
Database Manager - Handle .mdb (MS Access) database operations
"""

import os
from typing import List, Dict, Optional
from datetime import datetime


def recover_mdb_password(file_path: str) -> str:
    """
    Recover password from .mdb file (Access 97-2003).
    The password in old .mdb files is XOR-encoded in the header.
    """
    try:
        with open(file_path, 'rb') as f:
            # Read the header
            header = f.read(256)

        # Access 97/2000/2003 password location and XOR mask
        # Password starts at offset 0x42 (66) and is XOR'd with a known mask

        # XOR mask for Access 2000/2003 (.mdb)
        xor_mask_2000 = [
            0xC7, 0x89, 0x6F, 0x32, 0xBC, 0x19, 0x9E, 0xEC,
            0x17, 0xFB, 0x33, 0x8E, 0x5D, 0x70, 0xBA, 0xD7,
            0x6E, 0xBB, 0x92, 0x47
        ]

        # XOR mask for Access 97
        xor_mask_97 = [
            0x86, 0xFB, 0xEC, 0x37, 0x5D, 0x44, 0x9C, 0xFA,
            0xC6, 0x5E, 0x28, 0xE6, 0x13
        ]

        # Try to detect version and extract password
        password = ""

        # Check Jet version at offset 0x14
        jet_version = header[0x14] if len(header) > 0x14 else 0

        if jet_version == 0:  # Access 97
            xor_mask = xor_mask_97
            pwd_offset = 0x42
            pwd_len = 13
        else:  # Access 2000/2003
            xor_mask = xor_mask_2000
            pwd_offset = 0x42
            pwd_len = 20

        # Extract password bytes
        pwd_bytes = header[pwd_offset:pwd_offset + pwd_len]

        # XOR decode
        decoded = []
        for i, byte in enumerate(pwd_bytes):
            if i < len(xor_mask):
                decoded_byte = byte ^ xor_mask[i]
                if decoded_byte == 0:
                    break
                decoded.append(decoded_byte)

        if decoded:
            # Try to decode as string
            try:
                # Access uses Unicode (UTF-16LE) for passwords in 2000+
                password = bytes(decoded).decode('utf-16-le', errors='ignore').rstrip('\x00')
                if not password:
                    password = bytes(decoded).decode('latin-1', errors='ignore').rstrip('\x00')
            except:
                password = ''.join(chr(b) for b in decoded if 32 <= b < 127)

        return password.strip() if password else ""

    except Exception as e:
        print(f"Password recovery error: {e}")
        return ""


class DatabaseManager:
    """Manage .mdb database operations using pyodbc"""

    def __init__(self, database_path: str = None, password: str = None):
        self.database_path = database_path
        self.password = password  # User-provided password
        self.connection = None
        self._pyodbc = None

    def _get_pyodbc(self):
        """Lazy import pyodbc"""
        if self._pyodbc is None:
            try:
                import pyodbc
                self._pyodbc = pyodbc
            except ImportError:
                raise ImportError("pyodbc is required. Install with: pip install pyodbc")
        return self._pyodbc

    def _get_connection_string(self) -> str:
        """Get ODBC connection string for Access database"""
        if not self.database_path:
            raise ValueError("Database path not set")

        # Try different drivers
        drivers = [
            "Microsoft Access Driver (*.mdb, *.accdb)",
            "Microsoft Access Driver (*.mdb)",
            "{Microsoft Access Driver (*.mdb, *.accdb)}",
            "{Microsoft Access Driver (*.mdb)}"
        ]

        pyodbc = self._get_pyodbc()
        available_drivers = pyodbc.drivers()

        for driver in drivers:
            clean_driver = driver.strip('{}')
            if clean_driver in available_drivers or driver in available_drivers:
                return f"DRIVER={{{clean_driver}}};DBQ={self.database_path};"

        # If no driver found, try the most common one
        return f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={self.database_path};"

    def connect(self) -> bool:
        """Connect to the database"""
        try:
            pyodbc = self._get_pyodbc()

            # Build password list with priority order:
            # 1. User-provided password
            # 2. Recovered password from file
            # 3. Common passwords
            passwords_to_try = []

            # 1. User-provided password first
            if self.password:
                passwords_to_try.append(self.password)
                print(f"Will try user-provided password first")

            # 2. Try to recover password from file
            if self.database_path:
                recovered_pwd = recover_mdb_password(self.database_path)
                if recovered_pwd and recovered_pwd not in passwords_to_try:
                    passwords_to_try.append(recovered_pwd)
                    print(f"Recovered password from file: {recovered_pwd}")

            # 3. Common passwords for AAS/ZK attendance systems
            common_passwords = [
                "",           # No password
                "123",        # Common default
                "1234",
                "12345",
                "123456",
                "1234567",
                "12345678",
                "aas",        # AAS software
                "AAS",
                "admin",
                "Admin",
                "ADMIN",
                "password",
                "Password",
                "attendance",
                "Attendance",
                "manager",
                "Manager",
                "computer",   # ZKTeco common
                "zzk",        # ZKTeco
                "ZK",
                "zk",
                "zkteco",
                "ZKTeco",
                "soyal",      # Soyal systems
                "168168",     # Chinese systems
                "888888",
                "666666",
                "111111",
                "000000",
                "abc123",
                "root",
                "user",
                "pass",
                "db",
                "database",
                "access",
                "mdb",
            ]

            # Add common passwords that aren't already in the list
            for pwd in common_passwords:
                if pwd not in passwords_to_try:
                    passwords_to_try.append(pwd)

            driver = "Microsoft Access Driver (*.mdb, *.accdb)"

            for pwd in passwords_to_try:
                try:
                    if pwd:
                        conn_str = f"DRIVER={{{driver}}};DBQ={self.database_path};PWD={pwd};"
                    else:
                        conn_str = f"DRIVER={{{driver}}};DBQ={self.database_path};"

                    self.connection = pyodbc.connect(conn_str)
                    print(f"Connected successfully! Password: {'(empty)' if not pwd else pwd}")
                    # Save the working password for future reference
                    self.password = pwd
                    return True
                except Exception as e:
                    error_str = str(e).lower()
                    if "password" not in error_str and "not a valid password" not in error_str:
                        # Different error, not password related
                        print(f"Error: {e}")
                    continue

            print("Could not connect - password not found")
            print("Please set the database password in Settings")
            return False

        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def disconnect(self):
        """Close database connection"""
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
            self.connection = None

    def is_connected(self) -> bool:
        """Check if connected to database"""
        return self.connection is not None

    def get_all_employees(self) -> List[Dict]:
        """Get all employees/members from database"""
        if not self.connection:
            if not self.connect():
                return []

        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT emp_id, card_id, emp_name, phone_code, sex,
                       birth_date, hire_date, end_date, email, address,
                       depart_id, memo
                FROM Employee
                ORDER BY emp_id
            """)

            columns = [column[0] for column in cursor.description]
            employees = []

            for row in cursor.fetchall():
                emp = dict(zip(columns, row))
                # Clean up the data
                emp['emp_name'] = (emp.get('emp_name') or '').strip()
                emp['phone_code'] = (emp.get('phone_code') or '').strip()
                emp['sex'] = 'male' if emp.get('sex') == '0' else 'female'

                # Format dates
                for date_field in ['birth_date', 'hire_date', 'end_date']:
                    if emp.get(date_field):
                        try:
                            emp[date_field] = emp[date_field].strftime('%Y-%m-%d')
                        except:
                            emp[date_field] = None

                employees.append(emp)

            return employees

        except Exception as e:
            print(f"Error getting employees: {e}")
            return []

    def get_employee_by_id(self, emp_id: str) -> Optional[Dict]:
        """Get single employee by ID"""
        if not self.connection:
            if not self.connect():
                return None

        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT emp_id, card_id, emp_name, phone_code, sex,
                       birth_date, hire_date, end_date, email, address,
                       depart_id, memo
                FROM Employee
                WHERE emp_id = ?
            """, (emp_id,))

            row = cursor.fetchone()
            if row:
                columns = [column[0] for column in cursor.description]
                emp = dict(zip(columns, row))
                emp['emp_name'] = (emp.get('emp_name') or '').strip()
                emp['phone_code'] = (emp.get('phone_code') or '').strip()
                return emp
            return None

        except Exception as e:
            print(f"Error getting employee: {e}")
            return None

    def get_next_emp_id(self) -> str:
        """Get next available employee ID"""
        if not self.connection:
            if not self.connect():
                return "00000001"

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT MAX(emp_id) FROM Employee")
            row = cursor.fetchone()

            if row and row[0]:
                max_id = int(row[0])
                return str(max_id + 1).zfill(8)
            return "00000001"

        except Exception as e:
            print(f"Error getting next ID: {e}")
            return "00000001"

    def add_employee(self, data: Dict) -> bool:
        """Add new employee to database"""
        if not self.connection:
            if not self.connect():
                return False

        try:
            cursor = self.connection.cursor()

            emp_id = data.get('emp_id') or self.get_next_emp_id()
            card_id = emp_id.zfill(10)  # Card ID is 10 digits

            cursor.execute("""
                INSERT INTO Employee (emp_id, card_id, emp_name, phone_code, sex,
                                     hire_date, end_date, depart_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                emp_id,
                card_id,
                data.get('emp_name', ''),
                data.get('phone_code', ''),
                '0' if data.get('sex') == 'male' else '1',
                datetime.now().strftime('%Y-%m-%d'),
                data.get('end_date', '2026-12-31'),
                data.get('depart_id', '00000001')
            ))

            self.connection.commit()
            return True

        except Exception as e:
            print(f"Error adding employee: {e}")
            return False

    def update_employee(self, emp_id: str, data: Dict) -> bool:
        """Update employee data"""
        if not self.connection:
            if not self.connect():
                return False

        try:
            cursor = self.connection.cursor()

            # Build dynamic UPDATE query
            updates = []
            values = []

            if 'emp_name' in data:
                updates.append("emp_name = ?")
                values.append(data['emp_name'])

            if 'phone_code' in data:
                updates.append("phone_code = ?")
                values.append(data['phone_code'])

            if 'sex' in data:
                updates.append("sex = ?")
                values.append('0' if data['sex'] == 'male' else '1')

            if 'end_date' in data:
                updates.append("end_date = ?")
                values.append(data['end_date'])

            if 'email' in data:
                updates.append("email = ?")
                values.append(data['email'])

            if not updates:
                return True  # Nothing to update

            values.append(emp_id)

            query = f"UPDATE Employee SET {', '.join(updates)} WHERE emp_id = ?"
            cursor.execute(query, values)
            self.connection.commit()
            return True

        except Exception as e:
            print(f"Error updating employee: {e}")
            return False

    def block_employee(self, emp_id: str) -> bool:
        """Block employee by setting end_date to past"""
        return self.update_employee(emp_id, {'end_date': '2020-01-01'})

    def unblock_employee(self, emp_id: str, end_date: str) -> bool:
        """Unblock employee by setting end_date to future"""
        return self.update_employee(emp_id, {'end_date': end_date})

    def delete_employee(self, emp_id: str) -> bool:
        """Delete employee from database"""
        if not self.connection:
            if not self.connect():
                return False

        try:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM Employee WHERE emp_id = ?", (emp_id,))
            self.connection.commit()
            return True

        except Exception as e:
            print(f"Error deleting employee: {e}")
            return False

    def get_employee_count(self) -> int:
        """Get total number of employees"""
        if not self.connection:
            if not self.connect():
                return 0

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM Employee")
            row = cursor.fetchone()
            return row[0] if row else 0

        except Exception as e:
            print(f"Error counting employees: {e}")
            return 0

    def get_time_records(self, since: datetime = None) -> List[Dict]:
        """Get attendance time records"""
        if not self.connection:
            if not self.connect():
                return []

        try:
            cursor = self.connection.cursor()

            if since:
                cursor.execute("""
                    SELECT clock_id, card_id, emp_id, sign_time, mark, flag
                    FROM TimeRecords
                    WHERE sign_time >= ?
                    ORDER BY sign_time DESC
                """, (since,))
            else:
                cursor.execute("""
                    SELECT clock_id, card_id, emp_id, sign_time, mark, flag
                    FROM TimeRecords
                    ORDER BY sign_time DESC
                    LIMIT 1000
                """)

            columns = [column[0] for column in cursor.description]
            records = []

            for row in cursor.fetchall():
                record = dict(zip(columns, row))
                if record.get('sign_time'):
                    try:
                        record['sign_time'] = record['sign_time'].isoformat()
                    except:
                        pass
                records.append(record)

            return records

        except Exception as e:
            print(f"Error getting time records: {e}")
            return []

    def test_connection(self) -> tuple:
        """Test database connection and return status"""
        try:
            if self.connect():
                count = self.get_employee_count()
                return True, f"متصل - {count} عضو"
            return False, "فشل الاتصال"
        except Exception as e:
            return False, str(e)
