#!/usr/bin/env python3
"""
Fingerprint Bridge Service

This service runs locally at the gym and syncs attendance data
from the AAS fingerprint device to the cloud-based gym system.

Requirements:
- Python 3.8+
- requests
- schedule

Install:
    pip install requests schedule

Configuration:
    Set environment variables or edit config below
"""

import os
import time
import logging
import socket
import struct
import requests
from datetime import datetime, timedelta
from threading import Thread

# Configuration
CONFIG = {
    'API_URL': os.getenv('GYM_API_URL', 'https://your-gym-system.railway.app'),
    'API_KEY': os.getenv('GYM_API_KEY', 'your-api-key-here'),
    'FINGERPRINT_IP': os.getenv('FINGERPRINT_IP', '192.168.1.224'),
    'FINGERPRINT_PORT': int(os.getenv('FINGERPRINT_PORT', 5005)),
    'SYNC_INTERVAL': int(os.getenv('SYNC_INTERVAL', 30)),  # seconds
    'LOG_FILE': os.getenv('LOG_FILE', 'bridge.log'),
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG['LOG_FILE']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AASDevice:
    """
    Communication with AAS fingerprint device.
    Implements basic TCP/IP protocol for reading attendance logs.
    """

    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.socket = None
        self.last_log_id = 0

    def connect(self):
        """Connect to the fingerprint device"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.ip, self.port))
            logger.info(f"Connected to fingerprint device at {self.ip}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to device: {e}")
            return False

    def disconnect(self):
        """Disconnect from the device"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

    def get_attendance_logs(self, from_id=0):
        """
        Fetch attendance logs from the device.

        Note: This is a simplified implementation. The actual protocol
        depends on your specific AAS device model. You may need to adjust
        the commands and parsing based on your device's documentation.

        Returns list of dicts with:
            - fingerprint_id: int
            - timestamp: datetime
            - log_id: int
        """
        logs = []

        if not self.connect():
            return logs

        try:
            # This is a placeholder command - adjust for your specific device
            # Common AAS devices use a binary protocol

            # Example command to read attendance logs (adjust as needed)
            # Most devices require authentication first

            # Read logs command (this varies by device)
            # The actual implementation depends on your AAS device model

            # For demonstration, we'll simulate reading from device
            # In production, replace this with actual device communication

            logger.info("Reading attendance logs from device...")

            # Placeholder: In real implementation, parse device response
            # logs = self._parse_device_response(response)

        except Exception as e:
            logger.error(f"Error reading logs: {e}")
        finally:
            self.disconnect()

        return logs

    def _send_command(self, command):
        """Send a command to the device and receive response"""
        try:
            self.socket.send(command)
            response = self.socket.recv(4096)
            return response
        except Exception as e:
            logger.error(f"Command error: {e}")
            return None


class BridgeService:
    """
    Main bridge service that syncs fingerprint data to the cloud.
    """

    def __init__(self):
        self.api_url = CONFIG['API_URL']
        self.api_key = CONFIG['API_KEY']
        self.device = AASDevice(CONFIG['FINGERPRINT_IP'], CONFIG['FINGERPRINT_PORT'])
        self.last_sync_time = None
        self.last_log_id = self._load_last_log_id()

    def _load_last_log_id(self):
        """Load the last synced log ID from file"""
        try:
            with open('last_log_id.txt', 'r') as f:
                return int(f.read().strip())
        except:
            return 0

    def _save_last_log_id(self, log_id):
        """Save the last synced log ID to file"""
        try:
            with open('last_log_id.txt', 'w') as f:
                f.write(str(log_id))
        except Exception as e:
            logger.error(f"Failed to save last log ID: {e}")

    def check_api_health(self):
        """Check if the cloud API is reachable"""
        try:
            response = requests.get(
                f"{self.api_url}/api/fingerprint/health",
                headers={'X-API-Key': self.api_key},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"API health check failed: {e}")
            return False

    def sync_attendance(self):
        """
        Main sync function - reads logs from device and sends to cloud.
        """
        logger.info("Starting attendance sync...")

        # Check API health first
        if not self.check_api_health():
            logger.warning("API not reachable, skipping sync")
            return

        # Get new logs from device
        logs = self.device.get_attendance_logs(from_id=self.last_log_id)

        if not logs:
            logger.info("No new attendance logs")
            return

        logger.info(f"Found {len(logs)} new attendance records")

        # Send to cloud
        success_count = 0
        for log in logs:
            try:
                response = requests.post(
                    f"{self.api_url}/api/fingerprint/attendance",
                    headers={
                        'X-API-Key': self.api_key,
                        'Content-Type': 'application/json'
                    },
                    json={
                        'fingerprint_id': log['fingerprint_id'],
                        'timestamp': log['timestamp'].isoformat(),
                        'device_log_id': log['log_id']
                    },
                    timeout=10
                )

                if response.status_code == 200:
                    success_count += 1
                    if log['log_id'] > self.last_log_id:
                        self.last_log_id = log['log_id']
                else:
                    logger.warning(f"Failed to sync log {log['log_id']}: {response.text}")

            except Exception as e:
                logger.error(f"Error syncing log {log['log_id']}: {e}")

        # Save last log ID
        self._save_last_log_id(self.last_log_id)

        logger.info(f"Synced {success_count}/{len(logs)} attendance records")
        self.last_sync_time = datetime.now()

    def get_pending_enrollments(self):
        """Get list of members pending fingerprint enrollment"""
        try:
            response = requests.get(
                f"{self.api_url}/api/fingerprint/members/pending",
                headers={'X-API-Key': self.api_key},
                timeout=10
            )

            if response.status_code == 200:
                members = response.json().get('members', [])
                if members:
                    logger.info(f"Pending enrollments: {len(members)}")
                    for m in members:
                        logger.info(f"  - {m['name']} (ID: {m['fingerprint_id']})")
                return members
        except Exception as e:
            logger.error(f"Failed to get pending enrollments: {e}")

        return []

    def mark_enrolled(self, fingerprint_id):
        """Mark a member as enrolled in the cloud system"""
        try:
            response = requests.post(
                f"{self.api_url}/api/fingerprint/members/enrolled",
                headers={
                    'X-API-Key': self.api_key,
                    'Content-Type': 'application/json'
                },
                json={'fingerprint_id': fingerprint_id},
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"Marked fingerprint {fingerprint_id} as enrolled")
                return True
            else:
                logger.warning(f"Failed to mark enrollment: {response.text}")
        except Exception as e:
            logger.error(f"Error marking enrollment: {e}")

        return False

    def run(self):
        """Main run loop"""
        logger.info("=" * 50)
        logger.info("Fingerprint Bridge Service Started")
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Device: {CONFIG['FINGERPRINT_IP']}:{CONFIG['FINGERPRINT_PORT']}")
        logger.info(f"Sync Interval: {CONFIG['SYNC_INTERVAL']} seconds")
        logger.info("=" * 50)

        # Initial health check
        if self.check_api_health():
            logger.info("API connection: OK")
        else:
            logger.warning("API connection: FAILED - will retry")

        # Main loop
        while True:
            try:
                self.sync_attendance()
                self.get_pending_enrollments()
            except Exception as e:
                logger.error(f"Sync error: {e}")

            time.sleep(CONFIG['SYNC_INTERVAL'])


def main():
    """Entry point"""
    service = BridgeService()
    service.run()


if __name__ == '__main__':
    main()
