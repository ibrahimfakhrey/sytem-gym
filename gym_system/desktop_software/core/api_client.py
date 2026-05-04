"""
API Client - Communicate with the web app
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime


class APIClient:
    """Handle API communication with the web app"""

    def __init__(self, base_url: str, api_key: str, brand_id: int = 1, branch_id: int = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.brand_id = brand_id
        self.branch_id = branch_id
        self.timeout = 30

    def _scope(self) -> Dict:
        """Brand+branch scoping payload included in every relevant request."""
        scope = {'brand_id': self.brand_id}
        if self.branch_id:
            scope['branch_id'] = self.branch_id
        return scope

    def _get_headers(self) -> Dict:
        """Get request headers with API key"""
        return {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }

    def _make_request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> Dict:
        """Make HTTP request to API"""
        url = f"{self.base_url}/api{endpoint}"

        try:
            if method == 'GET':
                response = requests.get(url, headers=self._get_headers(),
                                       params=params, timeout=self.timeout)
            elif method == 'POST':
                response = requests.post(url, headers=self._get_headers(),
                                        json=data, timeout=self.timeout)
            elif method == 'PUT':
                response = requests.put(url, headers=self._get_headers(),
                                       json=data, timeout=self.timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=self._get_headers(),
                                          timeout=self.timeout)
            else:
                return {'success': False, 'error': f'Unknown method: {method}'}

            if response.status_code == 401:
                return {'success': False, 'error': 'مفتاح API غير صحيح'}

            return response.json()

        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'فشل الاتصال بالسيرفر'}
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'انتهت مهلة الاتصال'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============= Health & Status =============

    def health_check(self) -> Dict:
        """Check if server is healthy"""
        return self._make_request('GET', '/fingerprint/health')

    def get_sync_status(self) -> Dict:
        """Get overall sync status"""
        return self._make_request('GET', '/sync/status', params=self._scope())

    def send_heartbeat(self, computer_name: str = None, ip_address: str = None) -> Dict:
        """Send heartbeat to server"""
        data = {
            **self._scope(),
            'computer_name': computer_name or 'GYM-PC',
            'ip_address': ip_address or '',
            'software_version': '1.0.0'
        }
        return self._make_request('POST', '/sync/heartbeat', data)

    # ============= Members =============

    def get_members(self, updated_since: str = None) -> Dict:
        """Get all members from web app"""
        params = self._scope()
        if updated_since:
            params['updated_since'] = updated_since
        return self._make_request('GET', '/members', params=params)

    def create_member(self, member_data: Dict) -> Dict:
        """Create new member in web app"""
        data = {**self._scope(), **member_data}
        return self._make_request('POST', '/members', data)

    def update_member(self, member_id: int, member_data: Dict) -> Dict:
        """Update member in web app"""
        return self._make_request('PUT', f'/members/{member_id}', member_data)

    # ============= Attendance =============

    def sync_attendance(self, records: List[Dict]) -> Dict:
        """Sync attendance records to web app"""
        data = {**self._scope(), 'records': records}
        return self._make_request('POST', '/fingerprint/attendance', data)

    def mark_enrolled(self, member_id: int, fingerprint_id: int) -> Dict:
        """Mark member as enrolled in fingerprint system"""
        data = {
            'member_id': member_id,
            'fingerprint_id': fingerprint_id
        }
        return self._make_request('POST', '/fingerprint/members/enrolled', data)

    # ============= Device Commands =============

    def get_pending_commands(self) -> Dict:
        """Get pending commands to execute on local database"""
        return self._make_request('GET', '/device/commands', params=self._scope())

    def complete_command(self, command_id: int, success: bool = True,
                        error_message: str = None) -> Dict:
        """Mark command as completed"""
        data = {
            'success': success,
            'error_message': error_message
        }
        return self._make_request('POST', f'/device/commands/{command_id}/complete', data)

    # ============= Bridge Status =============

    def send_bridge_heartbeat(self, computer_name: str, ip_address: str = None,
                             os_info: str = None, database_path: str = None,
                             database_found: bool = False, sync_count: int = 0,
                             error: str = None) -> Dict:
        """Send detailed bridge heartbeat"""
        data = {
            **self._scope(),
            'computer_name': computer_name,
            'ip_address': ip_address or '',
            'os_info': os_info or '',
            'database_path': database_path or '',
            'database_found': database_found,
            'sync_count': sync_count,
            'error': error
        }
        return self._make_request('POST', '/fingerprint/bridge/heartbeat', data)

    # ============= Test Connection =============

    def get_class_schedule(self, schedule_date=None) -> Dict:
        """Get today's class schedule for access control"""
        try:
            params = self._scope()
            if schedule_date:
                params['date'] = schedule_date if isinstance(schedule_date, str) else schedule_date.isoformat()
            response = requests.get(
                f"{self.base_url}/api/bridge/class-schedule",
                headers=self._get_headers(),
                params=params, timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            return {'success': False, 'error': f'HTTP {response.status_code}'}
        except requests.ConnectionError:
            return {'success': False, 'error': 'لا يمكن الاتصال بالسيرفر'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_bridge_settings(self) -> Dict:
        """Get bridge settings from cloud"""
        try:
            response = requests.get(
                f"{self.base_url}/api/bridge/settings",
                headers=self._get_headers(),
                params=self._scope(), timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json().get('settings', {})
            return {}
        except Exception:
            return {}

    def test_connection(self) -> tuple:
        """Test connection to server and return status"""
        try:
            result = self.health_check()
            if result.get('status') == 'ok':
                return True, 'متصل بالسيرفر'
            elif 'error' in result:
                return False, result['error']
            return True, 'متصل'
        except Exception as e:
            return False, str(e)
