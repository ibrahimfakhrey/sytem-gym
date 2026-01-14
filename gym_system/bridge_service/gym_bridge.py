#!/usr/bin/env python3
"""
Gym Fingerprint Bridge Service
Syncs attendance data from local fingerprint device to cloud.

For gym staff: Just double-click 'run_bridge.bat' to start!
"""

import os
import sys
import json
import time
import socket
import platform
import logging
import requests
from datetime import datetime
from pathlib import Path
from threading import Thread

# Get script directory
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
LAST_SYNC_FILE = SCRIPT_DIR / "last_sync.txt"
LOG_FILE = SCRIPT_DIR / "bridge.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from config.json"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found: {CONFIG_FILE}")
        logger.error("Please create config.json with your settings")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        sys.exit(1)


def get_computer_name():
    """Get this computer's name"""
    return platform.node() or socket.gethostname() or "Unknown"


def get_local_ip():
    """Get local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def get_os_info():
    """Get OS information"""
    return f"{platform.system()} {platform.release()}"


def find_adb_databases():
    """
    Search for .adb (AAS database) files on the system.
    Returns list of found paths.
    """
    found_files = []

    # Common locations to search first (faster)
    priority_paths = [
        r"C:\AAS",
        r"C:\Program Files\AAS",
        r"C:\Program Files (x86)\AAS",
        r"D:\AAS",
        os.path.expanduser("~\\Documents\\AAS"),
        os.path.expanduser("~\\Desktop\\AAS"),
        os.path.expanduser("~"),
    ]

    logger.info("Searching for AAS database files (.adb)...")

    # Search priority paths first
    for base_path in priority_paths:
        if os.path.exists(base_path):
            try:
                for root, dirs, files in os.walk(base_path):
                    # Skip system and hidden folders
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['Windows', 'System32', '$Recycle.Bin']]

                    for file in files:
                        if file.lower().endswith('.adb'):
                            full_path = os.path.join(root, file)
                            found_files.append(full_path)
                            logger.info(f"  Found: {full_path}")
            except PermissionError:
                continue
            except Exception as e:
                logger.debug(f"Error searching {base_path}: {e}")

    # If nothing found in priority paths, search all drives
    if not found_files:
        logger.info("Searching all drives (this may take a while)...")

        # Get all drive letters on Windows
        if platform.system() == "Windows":
            import string
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        else:
            drives = ["/"]

        for drive in drives:
            try:
                for root, dirs, files in os.walk(drive):
                    # Skip system folders
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                        'Windows', 'System32', '$Recycle.Bin', 'ProgramData',
                        'Recovery', 'System Volume Information', 'node_modules'
                    ]]

                    for file in files:
                        if file.lower().endswith('.adb'):
                            full_path = os.path.join(root, file)
                            found_files.append(full_path)
                            logger.info(f"  Found: {full_path}")

                    # Limit depth to avoid very long searches
                    if root.count(os.sep) > 5:
                        dirs.clear()

            except PermissionError:
                continue
            except Exception:
                continue

    if found_files:
        logger.info(f"Found {len(found_files)} database file(s)")
    else:
        logger.warning("No .adb database files found")

    return found_files


def get_last_sync_id():
    """Get the last synced attendance ID"""
    try:
        with open(LAST_SYNC_FILE, 'r') as f:
            return int(f.read().strip())
    except:
        return 0


def save_last_sync_id(sync_id):
    """Save the last synced attendance ID"""
    with open(LAST_SYNC_FILE, 'w') as f:
        f.write(str(sync_id))


def send_heartbeat(config, database_path=None, database_found=False, error=None, sync_count=0):
    """Send heartbeat to cloud server"""
    api_url = config['cloud_api']['url']
    api_key = config['cloud_api']['api_key']
    brand_id = config['cloud_api']['brand_id']

    try:
        response = requests.post(
            f"{api_url}/api/fingerprint/bridge/heartbeat",
            headers={
                'X-API-Key': api_key,
                'Content-Type': 'application/json'
            },
            json={
                'brand_id': brand_id,
                'computer_name': get_computer_name(),
                'ip_address': get_local_ip(),
                'os_info': get_os_info(),
                'database_path': database_path,
                'database_found': database_found,
                'error': error,
                'sync_count': sync_count
            },
            timeout=15
        )

        if response.status_code == 200:
            logger.debug("Heartbeat sent successfully")
            return True
        else:
            logger.warning(f"Heartbeat failed: {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        return False


def check_api_health(config):
    """Check if cloud API is reachable"""
    api_url = config['cloud_api']['url']
    api_key = config['cloud_api']['api_key']

    try:
        response = requests.get(
            f"{api_url}/api/fingerprint/health",
            headers={'X-API-Key': api_key},
            timeout=10
        )
        return response.status_code == 200
    except:
        return False


def send_attendance_to_cloud(config, records):
    """Send attendance records to cloud API"""
    if not records:
        return 0

    api_url = config['cloud_api']['url']
    api_key = config['cloud_api']['api_key']
    brand_id = config['cloud_api']['brand_id']

    try:
        response = requests.post(
            f"{api_url}/api/fingerprint/attendance",
            headers={
                'X-API-Key': api_key,
                'Content-Type': 'application/json'
            },
            json={
                'brand_id': brand_id,
                'records': records
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            synced = result.get('synced', 0)
            logger.info(f"Synced {synced} records to cloud")
            return synced
        else:
            logger.error(f"API error {response.status_code}: {response.text}")
            return 0

    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to cloud API - check internet connection")
        return 0
    except Exception as e:
        logger.error(f"Sync error: {e}")
        return 0


def read_adb_database(db_path, last_id=0):
    """
    Read attendance records from .adb database.
    Note: .adb files may be Microsoft Access or proprietary format.
    """
    records = []

    try:
        # Try to read as SQLite first (some systems use SQLite with .adb extension)
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Common table names in attendance systems
        tables = ['checkinout', 'att_log', 'attendance', 'CHECKINOUT', 'ATT_LOG']

        for table in tables:
            try:
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if cursor.fetchone():
                    cursor.execute(f"""
                        SELECT USERID, CHECKTIME
                        FROM {table}
                        ORDER BY CHECKTIME DESC
                        LIMIT 100
                    """)

                    for row in cursor.fetchall():
                        records.append({
                            'fingerprint_id': row[0],
                            'timestamp': str(row[1]),
                            'log_id': hash(f"{row[0]}-{row[1]}")
                        })
                    break
            except:
                continue

        conn.close()

    except Exception as e:
        logger.debug(f"Could not read as SQLite: {e}")
        # File might be Access format - would need pyodbc
        logger.info("Database may be in Access format - requires additional drivers")

    return records


def print_banner():
    """Print startup banner"""
    print("\n" + "=" * 50)
    print("   GYM FINGERPRINT BRIDGE SERVICE")
    print("=" * 50)
    print(f"   Computer: {get_computer_name()}")
    print(f"   IP: {get_local_ip()}")
    print(f"   OS: {get_os_info()}")
    print("=" * 50)


def main():
    """Main entry point"""
    print_banner()

    # Load config
    config = load_config()
    api_url = config['cloud_api']['url']
    brand_id = config['cloud_api']['brand_id']
    interval = config['sync'].get('interval_seconds', 30)

    logger.info(f"Cloud API: {api_url}")
    logger.info(f"Brand ID: {brand_id}")
    logger.info(f"Sync Interval: {interval} seconds")
    print("=" * 50)

    # Check API connection
    print("\nChecking cloud connection...")
    if check_api_health(config):
        logger.info("Cloud API connection: OK")
    else:
        logger.warning("Cloud API connection: FAILED - will retry")

    # Search for database files
    print("\nSearching for fingerprint database...")
    db_files = find_adb_databases()

    database_path = db_files[0] if db_files else None
    database_found = len(db_files) > 0

    # Send initial heartbeat
    print("\nSending initial heartbeat to server...")
    send_heartbeat(
        config,
        database_path=database_path,
        database_found=database_found
    )

    print("\n" + "=" * 50)
    print("   BRIDGE RUNNING - Press Ctrl+C to stop")
    print("=" * 50 + "\n")

    # Main sync loop
    sync_count = 0
    last_error = None
    heartbeat_counter = 0

    while True:
        try:
            # Send heartbeat every 5 cycles (150 seconds with 30s interval)
            heartbeat_counter += 1
            if heartbeat_counter >= 5:
                send_heartbeat(
                    config,
                    database_path=database_path,
                    database_found=database_found,
                    error=last_error,
                    sync_count=sync_count
                )
                sync_count = 0
                heartbeat_counter = 0
                last_error = None

            # Try to read and sync attendance data
            if database_path:
                last_id = get_last_sync_id()
                records = read_adb_database(database_path, last_id)

                if records:
                    synced = send_attendance_to_cloud(config, records)
                    sync_count += synced

                    if synced > 0 and records:
                        max_id = max(r.get('log_id', 0) for r in records)
                        save_last_sync_id(max_id)

        except KeyboardInterrupt:
            logger.info("\nStopping bridge service...")
            # Send final heartbeat
            send_heartbeat(config, database_path=database_path, database_found=database_found)
            break
        except Exception as e:
            last_error = str(e)
            logger.error(f"Error: {e}")

        time.sleep(interval)


if __name__ == '__main__':
    main()
