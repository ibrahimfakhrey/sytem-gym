"""
APIv2 client — minimal HTTP wrapper for the 5 cloud endpoints.

All requests use X-Branch-Code header for auth. KSA-time aware.
"""
import requests
from typing import Dict, List, Optional

DEFAULT_TIMEOUT = 30


class APIError(Exception):
    pass


class APIv2:
    def __init__(self, base_url: str, branch_code: str, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip('/')
        self.branch_code = branch_code
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            'X-Branch-Code': self.branch_code,
            'Content-Type': 'application/json',
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v2/{path.lstrip('/')}"

    # ── 1. Health (also serves as registration handshake) ──
    def health(self) -> Dict:
        try:
            r = requests.get(self._url('health'), headers=self._headers(),
                             timeout=self.timeout)
            return self._handle(r)
        except requests.ConnectionError:
            raise APIError('فشل الاتصال بالسيرفر')
        except requests.Timeout:
            raise APIError('انتهت مهلة الاتصال')

    # ── 2. Heartbeat ──
    def heartbeat(self, computer_name: str = '', ip: str = '',
                  os_info: str = '', db_path: str = '',
                  db_found: bool = False, error: str = None) -> Dict:
        payload = {
            'computer_name': computer_name,
            'ip': ip,
            'os_info': os_info,
            'db_path': db_path,
            'db_found': db_found,
        }
        if error:
            payload['error'] = error
        return self._post('heartbeat', payload)

    # ── 3. Full sync (first launch) ──
    def full_sync(self, members: List[Dict], attendance: List[Dict]) -> Dict:
        return self._post('full-sync', {
            'members': members,
            'attendance': attendance,
        }, timeout=300)  # bigger payload, longer timeout

    # ── 4. Incremental sync ──
    def sync(self, new_members: List[Dict], new_attendance: List[Dict]) -> Dict:
        return self._post('sync', {
            'new_members': new_members,
            'new_attendance': new_attendance,
        })

    # ── 5. Access state (block/allow per member) ──
    def access_state(self) -> Dict:
        try:
            r = requests.get(self._url('access-state'), headers=self._headers(),
                             timeout=self.timeout)
            return self._handle(r)
        except requests.ConnectionError:
            raise APIError('فشل الاتصال بالسيرفر')

    # ── Internal ──
    def _post(self, path: str, payload: Dict, timeout: int = None) -> Dict:
        try:
            r = requests.post(self._url(path), headers=self._headers(),
                              json=payload, timeout=timeout or self.timeout)
            return self._handle(r)
        except requests.ConnectionError:
            raise APIError('فشل الاتصال بالسيرفر')
        except requests.Timeout:
            raise APIError('انتهت مهلة الاتصال')

    def _handle(self, response) -> Dict:
        if response.status_code == 401:
            raise APIError('رمز الفرع غير صحيح')
        if response.status_code == 403:
            raise APIError('الفرع غير مفعل')
        if response.status_code >= 500:
            raise APIError(f'خطأ من السيرفر: {response.status_code}')

        try:
            data = response.json()
        except ValueError:
            raise APIError(f'استجابة غير صالحة: {response.status_code}')

        if response.status_code != 200 and not data.get('success'):
            raise APIError(data.get('error', f'HTTP {response.status_code}'))

        return data
