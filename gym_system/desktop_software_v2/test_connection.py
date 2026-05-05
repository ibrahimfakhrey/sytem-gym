"""
Connection Test Script — verify all 5 v2 endpoints work end-to-end.

Run from anywhere with Python + requests installed:
    python test_connection.py
    python test_connection.py --url https://gymsystem.pythonanywhere.com --code BR-3-1
"""
import sys
import argparse
import json
from datetime import datetime

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

# Default values
DEFAULT_URL = 'https://gymsystem.pythonanywhere.com'
DEFAULT_CODE = 'BR-3-1'

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'


def test_endpoint(name, fn):
    print(f'\n{BOLD}{CYAN}━━━ {name} ━━━{RESET}')
    try:
        result = fn()
        if result.get('success', False) or result.get('status') == 'ok':
            print(f'{GREEN}✓ PASS{RESET}')
        else:
            print(f'{YELLOW}⚠ Response: {result}{RESET}')
        return result
    except Exception as e:
        print(f'{RED}✗ FAIL: {e}{RESET}')
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default=DEFAULT_URL, help='Server URL')
    parser.add_argument('--code', default=DEFAULT_CODE, help='Branch code')
    parser.add_argument('--include-write', action='store_true',
                        help='Also test full-sync (creates a test member). Skip on production.')
    args = parser.parse_args()

    BASE = args.url.rstrip('/')
    HEADERS = {'X-Branch-Code': args.code, 'Content-Type': 'application/json'}

    print(f'\n{BOLD}🔌 Gym Bridge v2 — Connection Test{RESET}')
    print(f'   Server:      {BASE}')
    print(f'   Branch code: {args.code}')
    print(f'   Time:        {datetime.now().isoformat()}')

    # ─── Test 1: Health (auth handshake) ───
    def test_health():
        r = requests.get(f'{BASE}/api/v2/health', headers=HEADERS, timeout=15)
        print(f'   Status: {r.status_code}')
        data = r.json()
        if data.get('success'):
            print(f'   Branch:      {data.get("branch_name")}  (id={data.get("branch_id")})')
            print(f'   Brand:       {data.get("brand_name")}  (id={data.get("brand_id")})')
            print(f'   Server time: {data.get("server_time")}')
        return data

    health = test_endpoint('1. Health', test_health)

    if not health or not health.get('success'):
        print(f'\n{RED}{BOLD}✗ Health check failed — stopping.{RESET}')
        print(f'{YELLOW}  Verify: branch_code "{args.code}" exists on the server,{RESET}')
        print(f'{YELLOW}          and the URL "{BASE}" is reachable.{RESET}')
        sys.exit(1)

    # ─── Test 2: Heartbeat ───
    def test_heartbeat():
        payload = {
            'computer_name': 'TEST-CLIENT',
            'ip': '127.0.0.1',
            'os_info': 'Test Script',
            'db_path': '/test/path',
            'db_found': True,
        }
        r = requests.post(f'{BASE}/api/v2/heartbeat', headers=HEADERS,
                          json=payload, timeout=15)
        print(f'   Status: {r.status_code}')
        data = r.json()
        print(f'   Server time: {data.get("server_time")}')
        return data

    test_endpoint('2. Heartbeat', test_heartbeat)

    # ─── Test 3: Access State (members + decisions) ───
    def test_access_state():
        r = requests.get(f'{BASE}/api/v2/access-state', headers=HEADERS, timeout=30)
        print(f'   Status: {r.status_code}')
        data = r.json()
        count = data.get('count', 0)
        print(f'   Members: {count}')
        print(f'   Window:  {data.get("access_window_minutes")} minutes')

        if count > 0:
            allowed = sum(1 for m in data.get('members', []) if m.get('allowed'))
            blocked = count - allowed
            print(f'   Allowed: {allowed}  Blocked: {blocked}')

            # Show first 3 examples
            for m in data.get('members', [])[:3]:
                icon = '✓' if m.get('allowed') else '✗'
                print(f'      {icon} emp_id={m.get("emp_id")}  end_date={m.get("end_date")}  reason={m.get("reason")}')
        return data

    test_endpoint('3. Access State', test_access_state)

    # ─── Test 4: Incremental Sync (no new data) ───
    def test_sync():
        payload = {'new_members': [], 'new_attendance': []}
        r = requests.post(f'{BASE}/api/v2/sync', headers=HEADERS,
                          json=payload, timeout=30)
        print(f'   Status: {r.status_code}')
        data = r.json()
        print(f'   Members synced:    {data.get("members_synced", 0)}')
        print(f'   Attendance synced: {data.get("attendance_synced", 0)}')
        print(f'   Next sync in:      {data.get("next_sync_in_seconds")} seconds')
        return data

    test_endpoint('4. Sync (empty incremental)', test_sync)

    # ─── Test 5: Full Sync (write — opt-in only) ───
    if args.include_write:
        def test_full_sync():
            payload = {
                'members': [{
                    'emp_id': 'BRIDGE_TEST_DELETE_ME',
                    'card_id': '9999999999',
                    'emp_name': 'BRIDGE TEST — delete me',
                    'phone': '0500000000',
                    'sex': '0',
                }],
                'attendance': []
            }
            r = requests.post(f'{BASE}/api/v2/full-sync', headers=HEADERS,
                              json=payload, timeout=60)
            print(f'   Status: {r.status_code}')
            data = r.json()
            summary = data.get('import_summary', {})
            print(f'   Created: {summary.get("members_created", 0)}')
            print(f'   Updated: {summary.get("members_updated", 0)}')
            return data
        test_endpoint('5. Full Sync (creates test member)', test_full_sync)
    else:
        print(f'\n{BOLD}{CYAN}━━━ 5. Full Sync ━━━{RESET}')
        print(f'{YELLOW}   ⚠ Skipped (write test). Use --include-write to enable.{RESET}')

    # ─── Final summary ───
    print(f'\n{GREEN}{BOLD}━━━ Test complete. ━━━{RESET}\n')


if __name__ == '__main__':
    main()
