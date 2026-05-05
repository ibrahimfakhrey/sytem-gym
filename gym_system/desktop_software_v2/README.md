# Gym Bridge v2

Lightweight desktop bridge for the Gym Management System.

## What it does

- Reads members from `backup.mdb` (Employee table)
- Reads fingerprint scans from `att2000.mdb` (CHECKINOUT table)
- Sends them to the cloud (PythonAnywhere) via JSON
- Receives access decisions from the cloud and writes `end_date` to `backup.mdb`
- The fingerprint device denies entry when `end_date` is in the past — that's how blocking works

## Architecture

```
Desktop App (this)  ⇄  Cloud (https://gymsystem.pythonanywhere.com/api/v2/)
        │
        ▼
  backup.mdb (members)        att2000.mdb (scans)
        │
        ▼
  ZKTeco fingerprint device — allows/denies entry by end_date
```

All decisions live in the cloud. Desktop is a "dumb pipe."

## Quick install (Windows x64)

```cmd
pip install -r requirements.txt
python main.py
```

On first launch, enter your branch code (e.g. `BR-3-1`) — that's it.

## Files

- `main.py` — entry point, controller
- `config.py` — JSON config at `~/.gym_bridge_v2/config.json`
- `core/api.py` — HTTP client (5 endpoints)
- `core/db_reader.py` — read members + scans from .mdb
- `core/db_writer.py` — write end_date back to backup.mdb
- `core/file_finder.py` — auto-detect .mdb paths
- `core/sync_engine.py` — orchestrates sync loop (every 60s by default)
- `ui/window.py` — main window
- `ui/pages/setup.py` — first-launch single-field setup
- `ui/pages/status.py` — live status + manual sync
- `ui/pages/settings.py` — DB paths, sync interval

## Time zones

All gym-time decisions use `Asia/Riyadh` (UTC+3). Class windows are computed
in KSA local time on the server, regardless of where the desktop or
PythonAnywhere are physically located.
