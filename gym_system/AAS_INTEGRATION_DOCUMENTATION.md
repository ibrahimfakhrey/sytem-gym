# Gym System + AAS Fingerprint Integration Documentation

## Overview

This document summarizes the technical findings for integrating the gym web system with AAS (Attendance Access System) fingerprint devices.

**Goal**: Sync attendance data from local fingerprint devices to the cloud web system at `https://gymsystem.pythonanywhere.com`

---

## System Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│  Fingerprint    │────▶│  Windows PC      │────▶│  Cloud Server      │
│  Devices        │     │  (Bridge Service)│     │  (PythonAnywhere)  │
│  192.168.1.224  │     │                  │     │                    │
│  192.168.1.225  │     │  tmkq.mdb        │     │  PostgreSQL        │
│  Port: 5005     │     │  (MS Access)     │     │                    │
└─────────────────┘     └──────────────────┘     └────────────────────┘
```

---

## Database Structure

### Location
```
/Database/
├── Attendancear/
│   └── tmkq.mdb (1.9 MB)
└── AttendanceF/
    └── tmkq.mdb (1.8 MB)
```

### Key Tables

#### 1. Employee Table (Members)
Stores all registered members and employees.

| Column | Type | Description |
|--------|------|-------------|
| `emp_id` | Text (12) | Primary key - Employee/Member ID |
| `card_id` | Text (16) | Card ID for fingerprint device |
| `emp_name` | Text | Name (supports Arabic) |
| `phone_code` | Text | Phone number |
| `hire_date` | DateTime | Registration date |
| `end_date` | DateTime | **Membership expiry - Controls door access!** |
| `dept_id` | Text | Department ID |
| `position_id` | Text | Position ID |
| `sex` | Text | Gender |
| `address` | Text | Address |
| `email` | Text | Email address |

#### 2. TimeRecords Table (Attendance Logs)
Stores all fingerprint scan events.

| Column | Type | Description |
|--------|------|-------------|
| `clock_id` | Long Integer | Device ID |
| `card_id` | Text (16) | Card/fingerprint ID |
| `emp_id` | Text (12) | Links to Employee table |
| `sign_time` | DateTime | Check-in/out timestamp |
| `mark` | Long Integer | Record type |
| `flag` | Long Integer | Status flag |

#### 3. tblEnroll Table (Fingerprint Data)
Stores enrolled fingerprint templates.

| Column | Type | Description |
|--------|------|-------------|
| `emp_id` | Text (12) | Employee ID |
| `clock_id` | Long Integer | Device ID |
| `finger_id` | Long Integer | Finger index (0-9) |
| `fp_data` | OLE Object | Fingerprint template data |
| `enroll_time` | DateTime | Enrollment timestamp |
| `fp_type` | Long Integer | Fingerprint type |

#### 4. DoorRightList Table (Access Permissions)
Stores door access rights.

| Column | Type | Description |
|--------|------|-------------|
| `PeoNo` | Text (10) | Person number (employee ID) |
| `DoorNo` | Text (10) | Door number |
| `DoorName` | Text (20) | Door name |
| `TimeZone1-3` | Long Integer | Time zone assignments |
| `IsValid` | - | Validity flag (not confirmed by manual) |

---

## Access Control Mechanism

Based on the official AAS Manual (62 pages), access control is managed through:

### 1. Leave Date (`end_date` field)
> "On the leave date, this employee loses permission to unlock doors"

This is the **confirmed method** to control member access:
- Set `end_date` to membership expiry date
- When membership expires, the door will not open for that member

### 2. Time Zones
Define when access is allowed (daily/weekly templates):
- Can be set per user or per group
- Allows scheduling access by time of day

### 3. User Time Zone Assignments
Links users to specific time zone permissions.

---

## Current Data

### Attendancear Database
| Member | emp_id | Phone | Fingerprints | Attendance Records |
|--------|--------|-------|--------------|-------------------|
| محمد (Mohamed) | 00000001 | 0506083930 | 0 | 0 |

### AttendanceF Database
| Member | emp_id | Phone | Fingerprints | Attendance Records |
|--------|--------|-------|--------------|-------------------|
| اسراء ابو سالم (Israa Abu Salem) | 00000010 | 0557924991 | 0 | 0 |

---

## Bridge Service

### Location
```
/bridge_service/gym_bridge.py
```

### Current Status
- Cloud connection: OK
- Database found: Yes (5 .mdb files)
- Sync count: 0

### Known Issue
The bridge service currently tries to read `.mdb` files as SQLite, but Microsoft Access databases require `pyodbc`:

```python
# Current code (doesn't work for .mdb):
import sqlite3
conn = sqlite3.connect(db_path)

# Required fix:
import pyodbc
conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + db_path
conn = pyodbc.connect(conn_str)
```

### Required Fix
To properly read Microsoft Access databases on Windows:

1. Install pyodbc: `pip install pyodbc`
2. Update `read_adb_database()` function to use pyodbc
3. Use the correct table names: `Employee`, `TimeRecords`

---

## Integration Flow

### For Members (Gym Entry)
```
1. Member scans fingerprint at door
2. AAS checks TimeRecords and end_date
3. If end_date > today AND Time Zone allows → Door opens
4. If end_date <= today → Door stays locked
5. Bridge service syncs TimeRecords to cloud
6. Web system updates attendance dashboard
```

### For Employees (Work Hours)
```
1. Employee scans fingerprint (clock in/out)
2. TimeRecords stores sign_time
3. Bridge service syncs to cloud
4. Web system calculates work hours for salary
```

---

## Web Dashboard Status

Currently showing:
- **Status**: متصل (Connected)
- **Computer**: DESKTOP-U0RKJ6M
- **IP Address**: 192.168.0.163
- **Database Path**: Found
- **Sync Count**: 0 (no attendance records yet)

---

## To-Do

1. [ ] Update bridge service to use pyodbc for .mdb files
2. [ ] Enroll fingerprints for existing members
3. [ ] Test attendance sync flow
4. [ ] Implement membership payment → `end_date` update logic
5. [ ] Test door access control with expired membership

---

## Device Configuration

| Device | IP Address | Port |
|--------|------------|------|
| Device 1 | 192.168.1.224 | 5005 |
| Device 2 | 192.168.1.225 | 5005 |

---

## Files Reference

| File | Purpose |
|------|---------|
| `tmkq.mdb` | Main AAS database (MS Access) |
| `gym_bridge.py` | Bridge service Python script |
| `config.json` | Bridge configuration (API keys, URLs) |
| `run_bridge.bat` | Windows batch file to run bridge |
| `AAS Manual 6.6.pdf` | Official AAS documentation |

---

*Document created: January 2026*
