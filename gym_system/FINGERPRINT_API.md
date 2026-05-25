# Fingerprint API (`/fp/*`)

Single-tenant HTTP API the desktop fingerprint client uses to keep the gym in sync with the cloud database, and that the web UI control panel uses to monitor and control the device.

- **Base URL:** `https://gymsystem.pythonanywhere.com`
- **Base path:** `/fp` → full prefix `https://gymsystem.pythonanywhere.com/fp`
- **Locked tenant:** this deployment serves **`brand_id = 8`, `branch_id = 9`** (branch code `BR-8-9`) only. The server hard-rejects any other pair.
- **Auth:** none
- **CSRF:** disabled on the whole blueprint
- **Encoding:** request and response bodies are JSON (`Content-Type: application/json`)
- **Timezone:** access decisions use Asia/Riyadh (UTC+3, no DST). All timestamps from the device should be ISO 8601 strings interpreted as local Riyadh time

### Endpoint quick reference

| Method | Full URL |
|---|---|
| POST | `https://gymsystem.pythonanywhere.com/fp/heartbeat` |
| POST | `https://gymsystem.pythonanywhere.com/fp/scan` |
| POST | `https://gymsystem.pythonanywhere.com/fp/sync` |
| POST | `https://gymsystem.pythonanywhere.com/fp/full-sync` |
| GET  | `https://gymsystem.pythonanywhere.com/fp/access-list?brand_id=&branch_id=` |
| GET  | `https://gymsystem.pythonanywhere.com/fp/to-stop?brand_id=&branch_id=` *(allowed=false subset)* |
| GET  | `https://gymsystem.pythonanywhere.com/fp/to-allow?brand_id=&branch_id=` *(allowed=true subset)* |
| GET  | `https://gymsystem.pythonanywhere.com/fp/status?brand_id=&branch_id=` |
| GET  | `https://gymsystem.pythonanywhere.com/fp/scans/recent?brand_id=&branch_id=&limit=` |
| POST | `https://gymsystem.pythonanywhere.com/fp/stop` *(per-fingerprint stop)* |
| POST | `https://gymsystem.pythonanywhere.com/fp/allow` *(per-fingerprint allow)* |
| POST | `https://gymsystem.pythonanywhere.com/fp/members/<member_id>/block` |
| POST | `https://gymsystem.pythonanywhere.com/fp/members/<member_id>/unblock` |
| GET  | `https://gymsystem.pythonanywhere.com/fp/control/<brand_id>` *(HTML)* |
| GET  | `https://gymsystem.pythonanywhere.com/fp/control/<brand_id>/<branch_id>` *(HTML)* |

---

## Common conventions

### Request inputs

`brand_id` and `branch_id` are **optional** — this deployment is locked to a single branch.

| Field | Type | Where | Behaviour |
|---|---|---|---|
| `brand_id`  | int | body (POST) / query (GET) | omit → defaults to `8`. If sent, must equal `8`. |
| `branch_id` | int | body (POST) / query (GET) | omit → defaults to `9`. If sent, must equal `9`. |

If you send anything other than `(8, 9)` the server returns:

```json
{ "success": false, "error": "invalid brand_id/branch_id" }
```
with status `400`. Sending `{}` (no IDs at all) is fine and works on the locked branch.

### Response envelope

Every successful response includes `"success": true`. Errors include `"success": false` plus an `error` string.

### Timestamps

- **Outgoing** (responses): ISO 8601 with timezone, e.g. `"2026-05-19T08:03:12+03:00"`
- **Incoming** (request bodies): ISO 8601 without timezone (treated as local Riyadh time), e.g. `"2026-05-19T08:03:12"`

### `emp_id` convention

`emp_id` is the key the desktop uses to identify a person in `backup.mdb`. The server computes it as:

```
emp_id = member.member_import_id   # the original emp_id from backup.mdb, if known
       | str(member.fingerprint_id).zfill(8)   # 8-digit zero-padded fallback
```

### `end_date` convention

`end_date` is the value the desktop writes into the `Employee.end_date` column of `backup.mdb`. The ZKTeco device uses it to decide whether to open the gate.

| Meaning | Value |
|---|---|
| Block immediately | `2020-01-01` |
| Always allow (staff) | `2099-12-31` |
| Regular subscription | the subscription's actual end date |
| Class-window allow today only | today's date |

---

## Endpoints

### 1. `POST https://gymsystem.pythonanywhere.com/fp/heartbeat`

The bridge process pings this every 30–60 seconds so the web UI can show "online / offline / late" status for the gym computer.

**Request body**

```json
{
  "brand_id": 1,
  "branch_id": 2,
  "computer_name": "GYM-PC-01",
  "ip": "192.168.1.50",
  "os_info": "Windows 10",
  "db_found": true,
  "db_path": "C:/AAS/Data/backup.mdb",
  "error": null
}
```

All fields beyond `brand_id` / `branch_id` are optional — pass what you have.

**Response**

```json
{
  "success": true,
  "server_time": "2026-05-19T08:03:12+03:00"
}
```

**Side effects**

- Upserts a `bridge_status` row for `(brand_id, branch_id)`.
- `last_heartbeat` is set to "now". The web panel uses heartbeat age to compute `online`/`متأخر`/`offline`:
  - < 2 min ⇒ online
  - < 10 min ⇒ late
  - ≥ 10 min ⇒ offline

---

### 2. `POST https://gymsystem.pythonanywhere.com/fp/scan`

A single fingerprint scan, pushed in real time. The server resolves the person (employee vs. member vs. unknown), writes attendance rows, and **returns the verdict for the desktop to display on the device's screen**.

**Request body**

```json
{
  "brand_id": 1,
  "branch_id": 2,
  "fingerprint_id": 123,
  "timestamp": "2026-05-19T08:03:12",
  "device_log_id": 8821
}
```

| Field | Required | Notes |
|---|---|---|
| `fingerprint_id` | yes | the ZKTeco user ID |
| `timestamp` | no | defaults to server "now" if omitted |
| `device_log_id` | no | the `TimeRecords.id` from the device — used for dedup |

**Response (member, allowed)**

```json
{
  "success": true,
  "person_type": "member",
  "person_id": 42,
  "person_name": "أحمد علي",
  "fingerprint_id": 123,
  "action": "check_in",
  "allowed": true,
  "reason": "اشتراك نشط"
}
```

**Response (member, denied — outside class window)**

```json
{
  "success": true,
  "person_type": "member",
  "person_id": 42,
  "person_name": "أحمد علي",
  "fingerprint_id": 123,
  "action": "denied",
  "allowed": false,
  "reason": "خارج وقت الكلاس"
}
```

**Response (employee — second scan of the day = check-out)**

```json
{
  "success": true,
  "person_type": "employee",
  "person_id": 17,
  "person_name": "سارة محمود",
  "fingerprint_id": 5,
  "action": "check_out",
  "allowed": true,
  "reason": "موظف"
}
```

**Response (unknown fingerprint)**

```json
{
  "success": true,
  "person_type": "unknown",
  "person_id": null,
  "person_name": null,
  "fingerprint_id": 999,
  "action": "denied",
  "allowed": false,
  "reason": "بصمة غير معروفة"
}
```

**Field reference**

| Field | Values |
|---|---|
| `person_type` | `"employee"` \| `"member"` \| `"unknown"` |
| `action` | `"check_in"` \| `"check_out"` \| `"denied"` \| `"duplicate"` |
| `allowed` | boolean — true means the gate should open |
| `reason` | Arabic label for the device screen |

**Side effects**

- **Employees**: first scan today → `EmployeeAttendance` row with `check_in`, late-minute calc against shift / brand settings, optional `EmployeeDeduction` if late. Second scan → updates `check_out`. Dedup by `device_log_id`.
- **Members**: writes a `MemberAttendance` row with `source='fingerprint'`. If denied, `has_warning=true` and `warning_message` is set. Dedup by `device_log_id`.
- **Members who are also staff** (`is_staff=True`): both rows are written so the scan appears in both the gate log *and* the work shift.

---

### 3. `POST https://gymsystem.pythonanywhere.com/fp/sync`

Batched alternative to `/fp/scan`. Use this when the desktop has been offline and needs to flush a backlog, or for low-bandwidth links where one HTTP call per scan is too chatty.

**Request body**

```json
{
  "brand_id": 1,
  "branch_id": 2,
  "new_members": [
    {
      "emp_id": "00000123",
      "emp_name": "أحمد علي",
      "card_id": "123",
      "phone": "0500000000",
      "sex": "0",
      "birth_date": "1995-04-15"
    }
  ],
  "new_attendance": [
    { "userid": 123, "checktime": "2026-05-19T08:03:12", "device_log_id": 8821 },
    { "userid": 124, "checktime": "2026-05-19T08:05:44", "device_log_id": 8822 }
  ]
}
```

**`new_members` field mapping (from `backup.mdb` Employee table)**

| Source column | Field | Notes |
|---|---|---|
| `emp_id` | `emp_id` | required, becomes `Member.member_import_id` |
| `emp_name` | `emp_name` | falls back to `"Unknown"` |
| `card_id` | `card_id` | int-parsed → `Member.fingerprint_id` |
| `phone` | `phone` | |
| `email` | `email` | optional |
| `address` | `address` | optional |
| `sex` | `sex` | `"0"`/`"M"` → male, `"1"`/`"F"` → female |
| `birth_date` | `birth_date` | `YYYY-MM-DD` |

**`new_attendance` field mapping (from `att2000.mdb` TimeRecords table)**

| Source column | Field |
|---|---|
| `userid` | `userid` (also accepts `fingerprint_id`) |
| `checktime` | `checktime` (also accepts `timestamp`) |
| `id` | `device_log_id` |

**Response**

```json
{
  "success": true,
  "server_time": "2026-05-19T08:03:12+03:00",
  "members_synced": 1,
  "attendance_synced": 2,
  "next_sync_in_seconds": 60
}
```

**Side effects**

- New members are upserted by `(brand_id, member_import_id)` — re-running with the same `emp_id` updates the existing record instead of creating a duplicate.
- Attendance is deduped by `(member_id, check_in)` — same scan pushed twice is silent no-op.
- For every employee scan, `EmployeeAttendance` is recomputed for that `(user_id, date)`.
- One `fingerprint_sync_logs` row is written per call.

---

### 4. `POST https://gymsystem.pythonanywhere.com/fp/full-sync`

First-launch bulk import. Push the entire contents of `backup.mdb` Employee table + the last 30 days of `att2000.mdb` TimeRecords in one call. Subsequent runs should use `/fp/sync` for the delta.

**Request body**

```json
{
  "brand_id": 1,
  "branch_id": 2,
  "members":    [ /* same shape as new_members above */ ],
  "attendance": [ /* same shape as new_attendance above */ ]
}
```

**Response**

```json
{
  "success": true,
  "branch": {
    "id": 2,
    "name": "الفرع الرئيسي",
    "brand_id": 1,
    "brand_name": "جيم ألفا"
  },
  "import_summary": {
    "members_created": 142,
    "members_updated": 3,
    "attendance_imported": 4821,
    "duplicates_skipped": 12,
    "skipped_unknown_fingerprints": 0
  },
  "id_mapping": {
    "00000123": 42,
    "00000124": 43
  },
  "server_time": "2026-05-19T08:03:12+03:00"
}
```

`id_mapping` maps each `emp_id` (mdb side) to the new cloud `member_id` — useful if the desktop wants to cache reverse lookups.

**Side effects**

Same as `/fp/sync` but no `fingerprint_sync_logs` row, since this is a one-shot bootstrap rather than a recurring sync.

---

### 5. `GET https://gymsystem.pythonanywhere.com/fp/access-list`

The single most important endpoint for the desktop. **Poll this every ~60 seconds.** It returns the desired `end_date` for every member; the desktop writes those values into `backup.mdb`'s Employee table so the ZKTeco device enforces them at the gate.

**Query string**

```
GET https://gymsystem.pythonanywhere.com/fp/access-list?brand_id=1&branch_id=2
```

**Response**

```json
{
  "success": true,
  "computed_at": "2026-05-19T08:03:12+03:00",
  "access_window_minutes": 15,
  "count": 142,
  "members": [
    {
      "emp_id": "00000123",
      "fingerprint_id": 123,
      "name": "أحمد علي",
      "allowed": true,
      "end_date": "2026-06-30",
      "reason": "اشتراك نشط"
    },
    {
      "emp_id": "00000124",
      "fingerprint_id": 124,
      "name": "خالد فهد",
      "allowed": false,
      "end_date": "2020-01-01",
      "reason": "خارج وقت الكلاس"
    },
    {
      "emp_id": "00000130",
      "fingerprint_id": 130,
      "name": "سارة محمود",
      "allowed": true,
      "end_date": "2099-12-31",
      "reason": "موظف"
    }
  ]
}
```

**Decision logic per member**

The server runs each member through these checks in order:

| Condition | Result |
|---|---|
| `member.is_active = False` | block (`end_date = 2020-01-01`, reason "محظور من قبل الإدارة") |
| `member.is_staff = True` | always allow (`end_date = 2099-12-31`, reason "موظف") |
| no active subscription | block (reason "لا يوجد اشتراك نشط") |
| active subscription, `end_date < today` | block (reason "اشتراك منتهي") |
| active sub, plan does **not** require class booking | allow until `sub.end_date`, reason "اشتراك نشط" |
| active sub, plan **requires** class booking, no booking today | block (reason "لم يحجز كلاس اليوم") |
| has booking today, inside `[class.start − window, class.end]` | allow today only, reason `كلاس <name> - <HH:MM>` |
| has booking today, outside the window | block (reason "خارج وقت الكلاس") |

The `access_window_minutes` is per-branch (from `bridge_settings.class_access_window_minutes`, default 15) — how many minutes before a class starts the member is allowed in.

**Only members with both `fingerprint_id` and `member_import_id` set are included.**

---

### 5a. `GET https://gymsystem.pythonanywhere.com/fp/to-stop`

The subset of `/fp/access-list` where `allowed=false` — the people the desktop should currently DENY at the gate. Useful when the desktop just wants the "deny" bucket and doesn't need to scan the full list.

**Query string**

```
GET https://gymsystem.pythonanywhere.com/fp/to-stop?brand_id=8&branch_id=9
```

(`brand_id` / `branch_id` optional, locked defaults apply.)

**Response**

```json
{
  "success": true,
  "computed_at": "2026-05-19T08:03:12+03:00",
  "count": 38,
  "members": [
    {
      "emp_id": "00000124",
      "fingerprint_id": 124,
      "name": "خالد فهد",
      "allowed": false,
      "end_date": "2020-01-01",
      "reason": "اشتراك منتهي"
    },
    {
      "emp_id": "00000201",
      "fingerprint_id": 201,
      "name": "محمد سعد",
      "allowed": false,
      "end_date": "2020-01-01",
      "reason": "محظور من قبل الإدارة"
    }
  ]
}
```

**How the desktop uses it:** for each row, write `end_date` (always `2020-01-01` for the stop bucket) to `Employee.end_date` in `backup.mdb` keyed by `emp_id`. The device denies entry on the next scan.

Decision logic is identical to `/fp/access-list` — see the table above. The endpoint is purely a convenience filter.

---

### 5b. `GET https://gymsystem.pythonanywhere.com/fp/to-allow`

Mirror of `/fp/to-stop` — the subset where `allowed=true`. The people the desktop should currently ALLOW at the gate.

**Query string**

```
GET https://gymsystem.pythonanywhere.com/fp/to-allow?brand_id=8&branch_id=9
```

**Response**

```json
{
  "success": true,
  "computed_at": "2026-05-19T08:03:12+03:00",
  "count": 104,
  "members": [
    {
      "emp_id": "00000123",
      "fingerprint_id": 123,
      "name": "أحمد علي",
      "allowed": true,
      "end_date": "2026-06-30",
      "reason": "اشتراك نشط"
    },
    {
      "emp_id": "00000130",
      "fingerprint_id": 130,
      "name": "سارة محمود",
      "allowed": true,
      "end_date": "2099-12-31",
      "reason": "موظف"
    },
    {
      "emp_id": "00000150",
      "fingerprint_id": 150,
      "name": "نورة عبدالله",
      "allowed": true,
      "end_date": "2026-05-19",
      "reason": "كلاس يوغا - 08:30"
    }
  ]
}
```

**How the desktop uses it:** for each row, write `end_date` (varies — subscription end date, today for class members, or `2099-12-31` for staff) to `Employee.end_date` in `backup.mdb` keyed by `emp_id`.

---

### How to choose between the three list endpoints

| Endpoint | Returns | Use when |
|---|---|---|
| `/fp/access-list` | everyone | the desktop wants one round-trip with the full picture and will split locally |
| `/fp/to-stop` | only `allowed=false` | the desktop only cares about who to block right now |
| `/fp/to-allow` | only `allowed=true` | the desktop only cares about who to allow right now |

The three endpoints use **identical** decision logic and timestamp ranges — calling `to-stop` + `to-allow` separately gives you the same total set as `access-list`, just in two HTTP calls instead of one.

---

### 6. `GET https://gymsystem.pythonanywhere.com/fp/status`

Used by the web control panel JavaScript (polled every 10 seconds) to render the status cards.

**Query string**

```
GET https://gymsystem.pythonanywhere.com/fp/status?brand_id=1&branch_id=2
```

**Response**

```json
{
  "success": true,
  "bridge": {
    "computer_name": "GYM-PC-01",
    "ip_address": "192.168.1.50",
    "database_found": true,
    "database_path": "C:/AAS/Data/backup.mdb",
    "last_heartbeat": "2026-05-19T08:02:48",
    "status_text": "متصل",
    "status_class": "success",
    "total_syncs": 1284,
    "last_error": null
  },
  "last_sync": {
    "at": "2026-05-19T08:02:32",
    "records": 3,
    "status": "success"
  },
  "today": {
    "member_scans": 41,
    "employee_scans": 8
  }
}
```

`bridge` is `null` when the desktop has never sent a heartbeat for this branch. `last_sync` is `null` when no `/fp/sync` calls have ever landed.

---

### 7. `GET https://gymsystem.pythonanywhere.com/fp/scans/recent`

Live feed of today's scans for the control panel's right-hand "آخر الدخولات اليوم" table. Polled every 5 seconds by the panel JS.

**Query string**

```
GET https://gymsystem.pythonanywhere.com/fp/scans/recent?brand_id=1&branch_id=2&limit=30
```

`limit` defaults to 20, max 100.

**Response**

```json
{
  "success": true,
  "scans": [
    {
      "id": 8821,
      "person_type": "member",
      "person_name": "أحمد علي",
      "fingerprint_id": 123,
      "check_in": "2026-05-19T08:03:12",
      "action": "check_in",
      "allowed": true,
      "warning": null
    },
    {
      "id": 8820,
      "person_type": "employee",
      "person_name": "سارة محمود",
      "fingerprint_id": 5,
      "check_in": "2026-05-19T07:58:01",
      "action": "check_in",
      "allowed": true,
      "warning": null
    },
    {
      "id": 8819,
      "person_type": "member",
      "person_name": "خالد أحمد",
      "fingerprint_id": 88,
      "check_in": "2026-05-19T07:55:30",
      "action": "denied",
      "allowed": false,
      "warning": "اشتراك منتهي"
    }
  ]
}
```

Rows are ordered newest first, filtered to today only.

---

### 8. `POST https://gymsystem.pythonanywhere.com/fp/stop`

Stop one specific fingerprint immediately. Looks up the member by `fingerprint_id` in the locked branch, sets `is_active = False`, and returns the per-member row in the same shape as `/fp/access-list` — so the desktop can write `end_date = 2020-01-01` to that one row in `backup.mdb` immediately, without waiting for the next access-list poll.

**Request body**

```json
{ "fingerprint_id": 123 }
```

`brand_id` / `branch_id` are optional (default to the locked pair).

**Response**

```json
{
  "success": true,
  "fingerprint_id": 123,
  "emp_id": "00000123",
  "member_id": 42,
  "name": "أحمد علي",
  "allowed": false,
  "end_date": "2020-01-01",
  "reason": "تم الإيقاف",
  "server_time": "2026-05-19T08:03:12+03:00"
}
```

**Errors**

- `400` `fingerprint_id required` — body missing the field
- `404` `fingerprint not found` — no member in brand 8 has that fingerprint

**Side effects**

`Member.is_active` is set to `False`. The change is also visible on the next `/fp/access-list` poll, so the desktop will keep seeing `end_date = 2020-01-01` for this member until you call `/fp/allow`.

---

### 9. `POST https://gymsystem.pythonanywhere.com/fp/allow`

Mirror of `/fp/stop` — flips `is_active = True` and returns the access-list row.

**Request body**

```json
{ "fingerprint_id": 123 }
```

**Response (member has active subscription)**

```json
{
  "success": true,
  "fingerprint_id": 123,
  "emp_id": "00000123",
  "member_id": 42,
  "name": "أحمد علي",
  "allowed": true,
  "end_date": "2026-06-30",
  "reason": "اشتراك نشط",
  "server_time": "2026-05-19T08:03:12+03:00"
}
```

**Response (member has no active subscription — allow alone is not enough)**

```json
{
  "success": true,
  "fingerprint_id": 123,
  "emp_id": "00000123",
  "member_id": 42,
  "name": "أحمد علي",
  "allowed": false,
  "end_date": "2020-01-01",
  "reason": "لا يوجد اشتراك نشط",
  "server_time": "2026-05-19T08:03:12+03:00"
}
```

`/fp/allow` only flips the manual block flag. The full access decision still runs — if the member has no active subscription, the response will say `allowed: false` and the desktop should keep them blocked. To grant access to someone whose subscription expired, you need a real subscription in the system (handled by the web UI, not this endpoint).

**Errors**

Same as `/fp/stop`.

---

### 10. `POST https://gymsystem.pythonanywhere.com/fp/members/<member_id>/block`

Triggered by the "حظر" button on the control panel — sets `Member.is_active = False`. The desktop picks up the new state on its next `/fp/access-list` poll (within ~60 seconds) and writes `end_date = 2020-01-01` to `backup.mdb` for that member.

**Auth:** requires a logged-in web user with brand access. Not callable by the desktop.

**No request body.**

**Response**

```json
{
  "success": true,
  "is_active": false,
  "message": "سيُمنع من الدخول خلال دقيقة"
}
```

---

### 11. `POST https://gymsystem.pythonanywhere.com/fp/members/<member_id>/unblock`

Mirror of block — sets `Member.is_active = True`. Same auth requirement.

**Response**

```json
{
  "success": true,
  "is_active": true,
  "message": "سيُسمح بالدخول خلال دقيقة"
}
```

---

### 12. `GET https://gymsystem.pythonanywhere.com/fp/control/<brand_id>` and `GET https://gymsystem.pythonanywhere.com/fp/control/<brand_id>/<branch_id>`

HTML pages, not API. Owner / brand-manager only (Flask-Login session required).

- **`https://gymsystem.pythonanywhere.com/fp/control/<brand_id>`** — branch picker. Shows every active branch of the brand with a card per branch (name, branch_code, fingerprint IP). Click → branch panel.
- **`https://gymsystem.pythonanywhere.com/fp/control/<brand_id>/<branch_id>`** — the actual control panel. Three status cards across the top (bridge status, last sync, today's scan counts), live scan feed on the left (5-second poll), searchable member list on the right with block/سماح buttons per row.

These are the URLs the fingerprint icon button on `admin/brands/index.html` and `admin/branches/list.html` link to.

---

## End-to-end flow

```
ZKTeco device  ─(att2000.mdb scans)─▶  desktop client (gym PC)
                                              │
   Push every scan (or batch when offline):   │
   POST /fp/scan      ◀──────────────────────┤
   POST /fp/sync      ◀──────────────────────┤
                                              │
   Keepalive every 30s:                       │
   POST /fp/heartbeat ◀──────────────────────┤
                                              │
   Pull desired gate state every 60s:         │
   GET  /fp/access-list ─────────────────────▶│
                                              │
   Desktop writes end_date column ─(backup.mdb)─▶ ZKTeco device
                                                  enforces locally
```

Server side, each scan persists:
- A `MemberAttendance` row (always, even for employees who are also members)
- An `EmployeeAttendance` row for employee scans (first scan = check-in, second = check-out)
- An optional `EmployeeDeduction` row if late and auto-deduction is enabled
- An updated `BridgeStatus` heartbeat
- A `FingerprintSyncLog` audit row per `/fp/sync` call

Operator actions in the web UI (block, unblock, edit subscription, edit class booking) don't send anything to the desktop — they just modify the database. The desktop picks up the change on its next `/fp/access-list` poll.

---

## Database touch points

| Table | What the API touches |
|---|---|
| `members` | `is_active`, `fingerprint_id`, `fingerprint_enrolled`, `member_import_id`, plus normal fields on import |
| `users` | read-only, for resolving fingerprint → employee |
| `member_attendance` | inserts on every scan; `fingerprint_log_id` for dedup |
| `employee_attendance` | inserts/updates on employee scans; `(user_id, date)` is unique |
| `employee_deductions` | inserts on late employee scans (if `EmployeeSettings.auto_deduction_enabled`) |
| `bridge_status` | upserted per `(brand_id, branch_id)` on heartbeat |
| `bridge_settings` | read-only here; managed by `/bridge/settings` UI |
| `fingerprint_sync_logs` | one row per `/fp/sync` call |
| `subscriptions`, `gym_classes`, `class_bookings` | read-only, drive `/fp/access-list` decisions |

---

## Errors and HTTP status codes

| Status | Meaning |
|---|---|
| `200` | Success — check the `success` field in the body |
| `400` | Invalid `brand_id`/`branch_id` pair, or required field missing |
| `403` | Block/unblock attempted without web session permission |
| `404` | Block/unblock target member does not exist, or HTML page brand/branch not found |

The desktop should treat any non-200 from `/fp/access-list` as transient and retry on the next poll cycle — never blank out the local `backup.mdb` based on a failed pull, because the device would lock everyone out.

---

## Source files

- Implementation: `app/routes/fingerprint.py`
- HTML pages: `app/templates/fingerprint/picker.html`, `app/templates/fingerprint/control.html`
- Buttons added to: `app/templates/admin/brands/index.html`, `app/templates/admin/branches/list.html`
- Models referenced: `app/models/fingerprint.py` (BridgeStatus, BridgeSettings, FingerprintSyncLog), `app/models/attendance.py`, `app/models/member.py`, `app/models/user.py`
