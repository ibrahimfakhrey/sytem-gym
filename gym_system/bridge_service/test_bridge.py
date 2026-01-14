#!/usr/bin/env python3
"""
Test script to verify the bridge connection works.
Run this from your development machine to test the API.
"""

import requests
from datetime import datetime

# Configuration - matches config.json
API_URL = "https://gymsystem.pythonanywhere.com"
API_KEY = "fingerprint-api-key"
BRAND_ID = 1

def test_health():
    """Test 1: Health check"""
    print("\n[TEST 1] Health Check")
    print("-" * 40)

    try:
        response = requests.get(
            f"{API_URL}/api/fingerprint/health",
            headers={"X-API-Key": API_KEY},
            timeout=10
        )

        if response.status_code == 200:
            print(f"✅ PASSED - API is reachable")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ FAILED - {e}")
        return False


def test_sync_attendance():
    """Test 2: Sync attendance (simulated)"""
    print("\n[TEST 2] Attendance Sync")
    print("-" * 40)

    # Simulate attendance record
    test_data = {
        "brand_id": BRAND_ID,
        "records": [
            {
                "fingerprint_id": 1,  # Test fingerprint ID
                "timestamp": datetime.now().isoformat(),
                "log_id": 99999
            }
        ]
    }

    try:
        response = requests.post(
            f"{API_URL}/api/fingerprint/attendance",
            headers={
                "X-API-Key": API_KEY,
                "Content-Type": "application/json"
            },
            json=test_data,
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ PASSED - API accepted request")
            print(f"   Synced: {result.get('synced', 0)}")
            print(f"   Errors: {result.get('errors', [])}")

            if result.get('errors'):
                print(f"\n   ℹ️  'Member not found' is expected if no member")
                print(f"      has fingerprint_id=1 assigned yet")
            return True
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ FAILED - {e}")
        return False


def test_pending_enrollments():
    """Test 3: Get pending enrollments"""
    print("\n[TEST 3] Pending Enrollments")
    print("-" * 40)

    try:
        response = requests.get(
            f"{API_URL}/api/fingerprint/members/pending",
            headers={"X-API-Key": API_KEY},
            params={"brand_id": BRAND_ID},
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            members = result.get('members', [])
            print(f"✅ PASSED - Got response")
            print(f"   Pending members: {len(members)}")

            for m in members[:5]:  # Show first 5
                print(f"   - {m.get('name')} (ID: {m.get('fingerprint_id')})")
            return True
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ FAILED - {e}")
        return False


def test_sync_status():
    """Test 4: Sync status"""
    print("\n[TEST 4] Sync Status")
    print("-" * 40)

    try:
        response = requests.get(
            f"{API_URL}/api/fingerprint/sync-status",
            headers={"X-API-Key": API_KEY},
            params={"brand_id": BRAND_ID},
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ PASSED - Got sync status")
            print(f"   Status: {result.get('status')}")
            print(f"   Message: {result.get('message')}")
            print(f"   Last sync: {result.get('last_sync')}")
            return True
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ FAILED - {e}")
        return False


def main():
    print("=" * 50)
    print("  FINGERPRINT BRIDGE - CONNECTION TEST")
    print("=" * 50)
    print(f"\n  API URL: {API_URL}")
    print(f"  Brand ID: {BRAND_ID}")

    results = []
    results.append(("Health Check", test_health()))
    results.append(("Attendance Sync", test_sync_attendance()))
    results.append(("Pending Enrollments", test_pending_enrollments()))
    results.append(("Sync Status", test_sync_status()))

    # Summary
    print("\n" + "=" * 50)
    print("  SUMMARY")
    print("=" * 50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")

    print(f"\n  Result: {passed}/{total} tests passed")

    if passed == total:
        print("\n  🎉 All tests passed! Bridge is ready to use.")
    else:
        print("\n  ⚠️  Some tests failed. Check errors above.")

    print("=" * 50)


if __name__ == "__main__":
    main()
