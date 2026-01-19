"""
Test database connection - Run this to debug connection issues
"""
import sys
import os

print("=" * 50)
print("  Database Connection Test")
print("=" * 50)
print()

# Check Python architecture
print(f"Python version: {sys.version}")
print(f"Python architecture: {8 * sys.maxsize.bit_length()} bit")
print()

# Check pyodbc
try:
    import pyodbc
    print(f"pyodbc version: {pyodbc.version}")
    print()

    # List all ODBC drivers
    drivers = pyodbc.drivers()
    print(f"Available ODBC Drivers ({len(drivers)}):")
    for d in drivers:
        print(f"  - {d}")
    print()

    # Check for Access drivers
    access_drivers = [d for d in drivers if 'access' in d.lower() or 'mdb' in d.lower()]
    if access_drivers:
        print(f"Access drivers found: {access_drivers}")
    else:
        print("WARNING: No Microsoft Access driver found!")
        print("Download from: https://www.microsoft.com/en-us/download/details.aspx?id=54920")
        print()

except ImportError:
    print("ERROR: pyodbc not installed!")
    print("Run: pip install pyodbc")
    sys.exit(1)

print()
print("-" * 50)
print()

# Ask for database path
db_path = input("Enter path to .mdb file (or press Enter to search): ").strip()

if not db_path:
    # Search for .mdb files
    print("Searching for .mdb files...")
    for root, dirs, files in os.walk("C:\\"):
        # Skip system folders
        dirs[:] = [d for d in dirs if d.lower() not in ['windows', '$recycle.bin', 'programdata']]
        for f in files:
            if f.lower().endswith('.mdb'):
                path = os.path.join(root, f)
                print(f"  Found: {path}")
                if not db_path:
                    db_path = path
        if db_path:
            break

if not db_path:
    print("No .mdb file found!")
    input("Press Enter to exit...")
    sys.exit(1)

print()
print(f"Testing connection to: {db_path}")
print()

# Try to connect with different passwords
driver = "Microsoft Access Driver (*.mdb, *.accdb)"
passwords = ["", "123", "aas", "admin", "attendance", "1234", "12345", "password", "abc", "111"]

print(f"Trying driver: {driver}")
print("Trying common passwords...")
print()

connected = False
for pwd in passwords:
    try:
        if pwd:
            conn_str = f"DRIVER={{{driver}}};DBQ={db_path};PWD={pwd};"
        else:
            conn_str = f"DRIVER={{{driver}}};DBQ={db_path};"

        conn = pyodbc.connect(conn_str)
        print(f"SUCCESS! Password: {'(empty)' if not pwd else pwd}")

        # Try to read data
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Employee")
        count = cursor.fetchone()[0]
        print(f"Employee count: {count}")

        # Show first few employees
        cursor.execute("SELECT TOP 5 emp_id, emp_name FROM Employee")
        print("Sample data:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")

        conn.close()
        print()
        print("=" * 50)
        print("  CONNECTION SUCCESSFUL!")
        print(f"  Use this password in settings: {pwd if pwd else '(leave empty)'}")
        print("=" * 50)
        connected = True
        break

    except Exception as e:
        if "password" in str(e).lower():
            print(f"  Password '{pwd}' - wrong")
        else:
            print(f"  Error: {e}")

if not connected:
    print()
    print("Could not find the correct password!")
    print("Please check with your AAS software for the database password.")

input("\nPress Enter to exit...")
