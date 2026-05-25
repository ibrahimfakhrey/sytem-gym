# Desktop Integration Guide — Gym Fingerprint Bridge

Everything a desktop app needs to integrate with the cloud's fingerprint API. Read this once, then keep `FINGERPRINT_API.md` open for the per-endpoint details.

- **Cloud base URL:** `https://gymsystem.pythonanywhere.com`
- **Endpoint prefix:** `/fp/`
- **Auth:** none — every call carries `brand_id` and `branch_id` instead
- **Content type:** all bodies and responses are JSON
- **Timezone:** every timestamp is Asia/Riyadh local (UTC+3, no DST)

---

## 1. The mental model

The desktop is the bridge between two databases:

```
┌───────────────────┐         ┌───────────────┐         ┌──────────────────┐
│ ZKTeco device     │         │ Your desktop  │         │ Cloud (Flask)    │
│ tmkq.mdb /        │ ←─ MS ──┤ app (Windows) │ ←─HTTP─→│ gymsystem.python │
│ backup.mdb /      │   Access│               │  JSON   │ anywhere.com     │
│ att2000.mdb       │         │               │         │ /fp/*            │
└───────────────────┘         └───────────────┘         └──────────────────┘
```

There are **four directions of data flow** between the desktop and the cloud:

| # | Direction | Endpoint | Purpose |
|---|---|---|---|
| 1 | desktop → cloud | `POST /fp/heartbeat` | "I'm alive" — every 30s |
| 2 | desktop → cloud | `POST /fp/scan` or `/fp/sync` | "Someone scanned" |
| 3 | cloud → desktop | `GET /fp/access-list` (or `/fp/to-stop` + `/fp/to-allow`) | "Here's who to allow / deny right now" |
| 4 | cloud → desktop | `GET /fp/lookup` | "Tell me about this one fingerprint" |

The device makes the **final gate decision locally** by reading `Employee.end_date` in `backup.mdb`. Your job is to keep that column in sync with what the cloud says.

---

## 2. Provisioning (do once per install)

The cloud already has a brand + branch row for this gym. Get the two IDs from whoever set it up on the web side:

| Field | Where it lives | Example |
|---|---|---|
| `brand_id` | `brands.id` in the cloud DB | `10` |
| `branch_id` | `branches.id` in the cloud DB | `11` |

Optionally also grab `branch.branch_code` (e.g. `BR-10-11`) for the human readable label.

**Store these as your local config** (`config.json`, registry, env vars — whatever fits the app). They never change after install. Every HTTP request includes them.

> Validation: if you send a pair that doesn't exist in the cloud's `branches` table you get `400 invalid brand_id/branch_id`. If you send the wrong gym's IDs you'll be reading/writing the wrong gym's data, so triple-check this at provisioning time.

---

## 3. First run — bootstrap

The very first time the desktop talks to the cloud, push the entire gym into the cloud DB so the cloud has someone to compute access for.

```http
POST https://gymsystem.pythonanywhere.com/fp/full-sync
Content-Type: application/json

{
  "brand_id": 10,
  "branch_id": 11,
  "members": [
    { "emp_id": "00000542", "emp_name": "باسم ابراهيم",
      "card_id": "542",      "phone": "0536069720",
      "sex": "0",            "birth_date": "1990-04-15" },
    { "emp_id": "00000543", "emp_name": "...", "card_id": "543", "phone": "..." }
    /* every row of backup.mdb's Employee table */
  ],
  "attendance": [
    { "userid": 542, "checktime": "2026-05-18T07:55:30", "device_log_id": 9001 }
    /* last 30 days of att2000.mdb's TimeRecords */
  ]
}
```

Response includes `id_mapping` — every `emp_id` mapped to the cloud's `member_id`. Cache it locally if you'll reference cloud `member_id`s later (otherwise ignore it).

| Source `.mdb` column | Cloud field | Notes |
|---|---|---|
| `Employee.emp_id` | `emp_id` | required, becomes the join key |
| `Employee.emp_name` | `emp_name` | falls back to "Unknown" |
| `Employee.card_id` | `card_id` | parsed to int → `fingerprint_id` |
| `Employee.phone` | `phone` | |
| `Employee.email` | `email` | optional |
| `Employee.address` | `address` | optional |
| `Employee.sex` | `sex` | "0"/"M" male, "1"/"F" female |
| `Employee.birth_date` | `birth_date` | `YYYY-MM-DD` |
| `TimeRecords.userid` | `userid` | the ZKTeco fingerprint ID |
| `TimeRecords.checktime` | `checktime` | ISO 8601, no timezone |
| `TimeRecords.id` | `device_log_id` | used for dedup |

**Idempotent.** Run `/fp/full-sync` again with the same data and it just reports `members_updated` instead of `members_created` — won't duplicate rows.

---

## 4. Steady state — the polling loop

Once bootstrapped, run a single loop on the desktop. Recommended cadence:

```
every 30 seconds:
    POST /fp/heartbeat               ← "I'm here"

every 60 seconds:
    1. POST /fp/sync                 ← push new members + new scans
    2. GET  /fp/access-list          ← pull desired gate state
    3. Apply each row's end_date to backup.mdb
```

### Heartbeat

```http
POST /fp/heartbeat
{
  "brand_id": 10, "branch_id": 11,
  "computer_name": "GYM-PC-01",
  "ip": "192.168.0.110",
  "os_info": "Windows 11",
  "db_found": true,
  "db_path": "C:/Attendancear/backup.mdb"
}
```

If you can't reach `backup.mdb`, send `db_found: false` and a `error` field describing why. The cloud's control panel shows this so admins know what's wrong without driving to the gym.

### Sync (push new data up)

```http
POST /fp/sync
{
  "brand_id": 10, "branch_id": 11,
  "new_members": [
    /* rows from Employee table you haven't sent before */
  ],
  "new_attendance": [
    /* rows from TimeRecords you haven't sent before */
  ]
}
```

How to track "haven't sent before":

| Table | Mark a row as sent by |
|---|---|
| `Employee` | comparing `emp_id` against a local "sent" set, or by max `emp_id` seen |
| `TimeRecords` | tracking the max `id` you've sent (it's monotonic) |

The cloud is idempotent (dedups by `emp_id` and by `(member_id, check_in)`), so it's safe to overshoot. If you're not sure whether something was sent, send it.

Empty arrays are fine: `{"brand_id":10,"branch_id":11,"new_members":[],"new_attendance":[]}` is a valid call that just proves the bridge is healthy.

### Access-list (pull desired state down)

```http
GET /fp/access-list?brand_id=10&branch_id=11

→ {
    "count": 4797,
    "members": [
      { "emp_id": "00000542", "fingerprint_id": 542,
        "allowed": false, "end_date": "2020-01-01", "reason": "لا يوجد اشتراك نشط",
        "name": "باسم ابراهيم" },
      ...
    ]
  }
```

For each row, write the returned `end_date` to the matching `Employee.end_date` in `backup.mdb`. That's all the device needs — at the next scan the device locally checks the date and decides.

Two values to recognise:

| `end_date` | Meaning at the device |
|---|---|
| `2020-01-01` | The device's date check fails → entry **denied** |
| anything ≥ today | Entry **allowed** until that date |

If you prefer two narrow lists instead of one wide one, use `GET /fp/to-stop` + `GET /fp/to-allow` — same data, pre-filtered server-side.

---

## 5. Real-time scan (optional but recommended)

If you can intercept a scan the moment it happens (file-watching `att2000.mdb` or hooking the device's SDK), push it immediately for a snappy verdict:

```http
POST /fp/scan
{
  "brand_id": 10, "branch_id": 11,
  "fingerprint_id": 542,
  "timestamp": "2026-05-19T08:03:12",
  "device_log_id": 9050
}

→ {
    "person_type": "member",      // "employee" | "member" | "unknown"
    "person_name": "باسم ابراهيم",
    "action": "denied",           // "check_in" | "check_out" | "denied"
    "allowed": false,
    "reason": "لا يوجد اشتراك نشط"
  }
```

Show `person_name` + `reason` on the gym computer's screen so the receptionist knows what happened ("Welcome Ahmed" or "Denied — expired sub").

Real-time scans are also automatically counted by the cloud as attendance — you don't need to also send them via `/fp/sync` for the same `device_log_id` (the dedup key handles it).

---

## 6. The other endpoints

These aren't part of the main loop but handy when you need them.

### Look up one fingerprint
```http
GET /fp/lookup?brand_id=10&branch_id=11&fingerprint_id=542
```
Use when: receptionist scans a finger and wants to know "who is this and why doesn't the gate open?" — returns everything in one call.

### Stop one fingerprint immediately
```http
POST /fp/stop
{ "brand_id": 10, "branch_id": 11, "fingerprint_id": 542 }
```
Sets cloud `is_active=false` and returns the access-list row with `end_date=2020-01-01`. Use when your app has its own "deny this person now" button.

### Allow one fingerprint
```http
POST /fp/allow
{ "brand_id": 10, "branch_id": 11, "fingerprint_id": 542 }
```
Mirror of `/fp/stop`. Note: if the member has no active subscription, the cloud still returns `allowed=false` — flipping the manual flag isn't enough on its own.

---

## 7. Polling cadences — recommended defaults

| Loop | Interval | Why |
|---|---|---|
| `/fp/heartbeat` | 30s | Keeps the cloud's status indicator "online" (turns "late" after 2 min, "offline" after 10) |
| `/fp/sync` | 60s | Cheap enough; new enrollments and scans land quickly |
| `/fp/access-list` | 60s | The gate-state freshness window — within 60s of admin clicking "block", the device blocks |
| `/fp/scan` | per-scan, immediately | Only if you have real-time scan events |

These cadences are baked into the response: `/fp/sync` returns `next_sync_in_seconds: 60`. Honor it if you want — or pick your own.

---

## 8. Error handling

| HTTP | When | What to do |
|---|---|---|
| `200 success: true` | Normal | Process the response |
| `200 success: false` | Validation failure | Read `error`, fix the call, retry |
| `400` | Bad brand/branch pair, missing required field | Don't retry — fix the call |
| `404` | `/fp/stop`/`/fp/allow` on an unknown fingerprint | Skip; this fingerprint isn't in the cloud DB |
| `5xx` or timeout | Cloud or PythonAnywhere transient | Retry with exponential back-off (1s, 2s, 4s, ..., 60s max) |
| Network unreachable | Internet is down | Keep your local queue, retry next cycle |

**Critical rule for `/fp/access-list` failures:** if the call fails, **do not** blank or "reset" the `Employee.end_date` column in `backup.mdb`. Leave the previous values in place. Otherwise the device will deny every member during the outage. The desktop should only *apply* what it receives, never *invalidate* the local cache on a failure.

---

## 9. Idempotency rules — your safety net

The cloud is designed to make retries safe. Use these as guarantees:

| Action | Dedup key | Safe to retry? |
|---|---|---|
| Create a member via `/fp/sync` or `/fp/full-sync` | `(brand_id, emp_id)` | Yes — second call updates instead of duplicates |
| Push a scan via `/fp/scan` or `/fp/sync` | `(member_id, check_in)` and `device_log_id` | Yes — second call is silent no-op |
| Toggle access via `/fp/stop` / `/fp/allow` | `is_active` is set absolutely (not toggled) | Yes — second call is no-op |
| Heartbeat | always upserts the same row | Yes |

You **cannot create duplicates by retrying**. If you lose a response or get a timeout, just resend the same payload.

---

## 10. Worked example — first hour of a deploy

```text
T = 0   install desktop app, set brand_id=10, branch_id=11 in config.json
T = 0   POST /fp/heartbeat                  → 200 success, server_time=...
T = 0   POST /fp/full-sync (4800 members, 30 days of scans)
                                            → 200, members_created=4800
T = 0   GET  /fp/access-list                → 4800 rows, write end_date to backup.mdb

T = 30  POST /fp/heartbeat                  → still online

T = 60  POST /fp/sync (no new members, 3 new scans)
                                            → 200, attendance_synced=3
        GET  /fp/access-list                → 4800 rows, apply changes (likely none)

T = 90  receptionist enrolls a new member with fingerprint 9999 on the device
T = 120 POST /fp/heartbeat                  → still online
T = 120 POST /fp/sync (1 new member, 5 new scans)
                                            → 200, members_synced=1, attendance_synced=5
        GET  /fp/access-list                → 4801 rows now, new emp_id present
        write end_date for emp_id 00009999 (whatever the cloud says)

T = 180 admin clicks "إيقاف" on باسم ابراهيم in the web UI
T = 240 POST /fp/sync                       → 200
        GET  /fp/access-list                → row for emp_id 00000542 now says
                                              end_date=2020-01-01
        desktop writes 2020-01-01 to backup.mdb for emp_id 00000542
        next time باسم scans → device denies entry (because the date check fails)
```

---

## 11. Testing checklist

Run these in order before declaring the integration done.

- [ ] **Heartbeat shows up.** Open `https://gymsystem.pythonanywhere.com/fp/control/<brand_id>/<branch_id>` (admin login required). The "حالة الجسر" card should show your computer name + "متصل" within 30 seconds.
- [ ] **Full sync lands.** After the first `/fp/full-sync`, the access-list call returns the full member count.
- [ ] **Incremental sync.** Add a new fingerprint on the device, call `/fp/sync` next cycle. Confirm the member appears with `GET /fp/lookup?fingerprint_id=<new>` and on the web members list.
- [ ] **Allow/deny round-trip.** Click إيقاف on a member in the web UI. Within 60 seconds, `/fp/access-list` should return `end_date=2020-01-01` for them. Apply it and verify the device denies entry on next scan. Click تفعيل — within 60s the date returns to their subscription date and the device opens the gate.
- [ ] **Unknown fingerprint.** Scan a fingerprint that isn't enrolled. `/fp/scan` should return `person_type: unknown, action: denied`. The desktop should show "بصمة غير معروفة" on screen and not throw.
- [ ] **Network blip.** Disconnect the internet for 5 minutes during business hours. The device should keep working (using the last known `end_date` values). When you reconnect, `/fp/sync` should catch up with all scans that piled up during the outage.
- [ ] **Class-window logic.** For a member on a class-requiring plan, `/fp/access-list` should return `end_date=today` only during the class window (default 15 min before start through end), and `2020-01-01` otherwise. Confirm by scanning the same member 10 min before and 30 min after their class.

---

## 12. Field reference — quick

| Field | Type | Notes |
|---|---|---|
| `brand_id` | int | gym group ID |
| `branch_id` | int | gym location ID |
| `fingerprint_id` | int | ZKTeco user ID (numeric) |
| `emp_id` | string | 8-digit zero-padded version of `fingerprint_id`, or whatever was in `backup.mdb.Employee.emp_id` |
| `device_log_id` | int | `TimeRecords.id` — dedup key for scans |
| `end_date` | `YYYY-MM-DD` | write this to `backup.mdb.Employee.end_date` |
| `allowed` | bool | `true` = open the gate; `false` = deny |
| `reason` | Arabic string | human-readable status, show on screen |
| `person_type` | `member` \| `employee` \| `unknown` | who they are |
| `is_staff` | bool | the member is also linked to a `User` (employee) record |
| `is_active` | bool | the manual access flag — false means admin clicked "إيقاف" |

---

## 13. Where to read more

| File | What's in it |
|---|---|
| `FINGERPRINT_API.md` | Per-endpoint reference: every request/response shape, error code, side effect, decision logic |
| `app/routes/fingerprint.py` | The actual implementation, if you want to verify behaviour |
| `app/models/fingerprint.py` | The tables the API touches |
| `app/templates/fingerprint/control.html` | The web control panel — useful to understand what admins see |
| `app/templates/fingerprint/audit.html` | The audit log — every toggle action with who/when |

---

## 14. Quick sanity-check commands

Anything you can copy into a Windows Command Prompt with curl:

```bash
:: Is the cloud reachable?
curl https://gymsystem.pythonanywhere.com/fp/access-list?brand_id=10&branch_id=11

:: Do we know fingerprint 542?
curl "https://gymsystem.pythonanywhere.com/fp/lookup?brand_id=10&branch_id=11&fingerprint_id=542"

:: Send a heartbeat
curl -X POST https://gymsystem.pythonanywhere.com/fp/heartbeat ^
  -H "Content-Type: application/json" ^
  -d "{\"brand_id\":10,\"branch_id\":11,\"computer_name\":\"TEST\",\"db_found\":true}"
```

If those three return JSON with `"success": true`, the cloud is reachable and you have a valid brand/branch — you're ready to wire up the actual data flow.

---

## 15. Contact / changes

The cloud API is owned by Ibrahim. Any endpoint addition or schema change will be announced via a new commit on `https://github.com/ibrahimfakhrey/sytem-gym`. Subscribe to the repo if you want notifications.

Breaking changes will get a new `/fp/v2/` prefix; the current `/fp/*` namespace will be kept stable.
