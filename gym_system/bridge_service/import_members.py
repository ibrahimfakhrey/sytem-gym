#!/usr/bin/env python3
"""
One-time Member Import Script
Reads Employee records from backup.mdb and imports them into the web app.

Usage:
    python import_members.py

Requirements: pyodbc, requests
Configure: Edit config.json with cloud API URL, API key, and brand_id
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

try:
    import pyodbc
except ImportError:
    print("ERROR: pyodbc is required. Install with: pip install pyodbc")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: pip install requests")
    sys.exit(1)

# Setup
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(SCRIPT_DIR / "import.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

MDB_CONN_STR = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;"
BATCH_SIZE = 100


def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_backup_mdb(config):
    """Find backup.mdb - use config path or auto-detect."""
    # Check config
    db_path = config.get('databases', {}).get('backup_path', '')
    if db_path and os.path.exists(db_path):
        return db_path

    # Auto-detect
    search_paths = [
        r"C:\AAS", r"D:\AAS",
        r"C:\Program Files\AAS", r"C:\Program Files (x86)\AAS",
        r"C:\Attendance", r"D:\Attendance",
        os.path.expanduser("~\\Documents"),
        os.path.expanduser("~\\Desktop"),
    ]

    for base in search_paths:
        if not os.path.exists(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ['BackUpData', 'Windows', '$Recycle.Bin']]
            for f in files:
                if f.lower().endswith('.mdb'):
                    full_path = os.path.join(root, f)
                    try:
                        conn = pyodbc.connect(MDB_CONN_STR % full_path)
                        cursor = conn.cursor()
                        tables = [r.table_name for r in cursor.tables(tableType='TABLE')]
                        if 'Employee' in tables:
                            cols = [r.column_name for r in cursor.columns(table='Employee')]
                            if 'emp_id' in cols and 'end_date' in cols:
                                conn.close()
                                return full_path
                        conn.close()
                    except Exception:
                        pass
            if root.count(os.sep) > 5:
                dirs.clear()

    return None


def read_employees(mdb_path):
    """Read all Employee records from backup.mdb."""
    conn = pyodbc.connect(MDB_CONN_STR % mdb_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT emp_id, emp_name, phone_code, end_date, memo, f_name, card_id
        FROM Employee
        ORDER BY emp_id
    """)
    columns = [desc[0] for desc in cursor.description]
    rows = []
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        # Clean up values
        for key in record:
            if isinstance(record[key], str):
                record[key] = record[key].strip()
        rows.append(record)
    conn.close()
    return rows


def import_batch(api_url, api_key, brand_id, members):
    """Send a batch of members to the cloud API."""
    try:
        r = requests.post(
            f"{api_url}/api/members/import-batch",
            headers={
                'X-API-Key': api_key,
                'Content-Type': 'application/json'
            },
            json={
                'brand_id': brand_id,
                'members': members
            },
            timeout=60
        )
        if r.status_code == 200:
            return r.json()
        else:
            logger.error(f"API error {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Import error: {e}")
        return None


def main():
    print()
    print("=" * 55)
    print("   MEMBER IMPORT FROM BACKUP.MDB")
    print("=" * 55)
    print()

    # Load config
    config = load_config()
    cloud = config['cloud_api']
    api_url = cloud['url'].rstrip('/')
    api_key = cloud['api_key']
    brand_id = cloud['brand_id']

    logger.info(f"Cloud API: {api_url}")
    logger.info(f"Brand ID: {brand_id}")

    # Find database
    logger.info("Finding backup.mdb...")
    mdb_path = find_backup_mdb(config)
    if not mdb_path:
        logger.error("backup.mdb not found! Configure databases.backup_path in config.json")
        sys.exit(1)
    logger.info(f"Found: {mdb_path}")

    # Check API connectivity
    logger.info("Checking cloud connection...")
    try:
        r = requests.get(
            f"{api_url}/api/fingerprint/health",
            headers={'X-API-Key': api_key},
            timeout=10
        )
        if r.status_code != 200:
            logger.error(f"Cloud API returned {r.status_code}. Check API key.")
            sys.exit(1)
        logger.info("Cloud API: CONNECTED")
    except Exception as e:
        logger.error(f"Cannot reach cloud API: {e}")
        sys.exit(1)

    # Read employees
    logger.info("Reading Employee records from backup.mdb...")
    employees = read_employees(mdb_path)
    logger.info(f"Found {len(employees)} records")

    if not employees:
        logger.info("No records to import.")
        return

    # Confirm
    print(f"\nReady to import {len(employees)} members to brand_id={brand_id}")
    confirm = input("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    # Import in batches
    total_created = 0
    total_skipped = 0
    total_errors = 0

    for i in range(0, len(employees), BATCH_SIZE):
        batch = employees[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(employees) + BATCH_SIZE - 1) // BATCH_SIZE

        # Convert to API format
        api_members = []
        for emp in batch:
            api_members.append({
                'emp_id': emp.get('emp_id', ''),
                'emp_name': emp.get('emp_name', ''),
                'phone_code': emp.get('phone_code', ''),
                'end_date': emp['end_date'].isoformat() if emp.get('end_date') and hasattr(emp['end_date'], 'isoformat') else str(emp.get('end_date', '')),
                'memo': emp.get('memo', ''),
                'f_name': emp.get('f_name', '')
            })

        logger.info(f"Batch {batch_num}/{total_batches} ({len(api_members)} records)...")
        result = import_batch(api_url, api_key, brand_id, api_members)

        if result:
            created = result.get('created', 0)
            skipped = result.get('skipped', 0)
            errors = result.get('errors_count', 0)
            total_created += created
            total_skipped += skipped
            total_errors += errors
            logger.info(f"  Created: {created}, Skipped: {skipped}, Errors: {errors}")

            for err in result.get('errors', []):
                logger.warning(f"  Error: {err}")
        else:
            logger.error(f"  Batch {batch_num} failed!")
            total_errors += len(api_members)

    # Summary
    print()
    print("=" * 55)
    print("   IMPORT COMPLETE")
    print("=" * 55)
    print(f"   Total records : {len(employees)}")
    print(f"   Created       : {total_created}")
    print(f"   Skipped       : {total_skipped}")
    print(f"   Errors        : {total_errors}")
    print("=" * 55)


if __name__ == '__main__':
    main()
