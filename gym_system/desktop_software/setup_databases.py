"""
First-run database setup for the Gym System desktop app.

For each .mdb file the file_finder discovers, this helper:
  1. Skips it if it has no password (encryption flag at offset 0x62 is zero).
  2. Tries a short list of known passwords first ("Timmy", blank, a couple of
     AAS-Attendancear defaults). If one works, records it in the user config so
     the desktop will pass it to pyodbc on every connection.
  3. If none of the known passwords work, calls remove_mdb_password() to strip
     the password from the file in-place. A timestamped .backup copy is created
     next to the original first, so it's reversible.

Idempotent: the helper records its outcome per file in
~/.gym_bridge/db_setup.json and skips files it has already processed.

Runs from START_HERE.bat after dependencies install, before the GUI launches.
Safe to re-run by hand at any time.
"""

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Make our own modules importable when invoked from anywhere
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from config import load_config, save_config

# AAS / ZKTeco install passwords worth trying before stripping.
# Order matters — the first one that works wins.
PASSWORDS_TO_TRY = [
    'Timmy',  # user-suggested
    '',       # no password
    'tmkj',   # common AAS default
    'aas',
    'AAS',
    'admin',
    'Admin',
    'computer',
    'ZK',
    'zkteco',
]

STATE_FILE = Path.home() / '.gym_bridge' / 'db_setup.json'


# ─── helpers ───────────────────────────────────────────────────────


def _has_password(path: str) -> bool:
    """The Jet4 password flag lives at offset 0x62; non-zero means a password is set."""
    try:
        with open(path, 'rb') as f:
            f.seek(0x62)
            flag = f.read(1)
        return bool(flag and flag[0])
    except Exception:
        return False


def _detect_schema(path: str) -> str:
    """'device' (att2000.mdb / CHECKINOUT) | 'backup' (Attendancear / Employee) | 'unknown'."""
    try:
        from core.database import DeviceDatabaseManager
        return DeviceDatabaseManager.detect_schema(path)
    except Exception:
        return 'unknown'


def _try_password(path: str, password: str) -> bool:
    """Return True if pyodbc can open the .mdb with this password."""
    try:
        import pyodbc
    except ImportError:
        return False
    try:
        if password:
            conn_str = (
                'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                f'DBQ={path};PWD={password};'
            )
        else:
            conn_str = (
                'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                f'DBQ={path};'
            )
        conn = pyodbc.connect(conn_str, timeout=5)
        try:
            cur = conn.cursor()
            cur.tables().fetchone()  # one round-trip to confirm
        finally:
            conn.close()
        return True
    except Exception:
        return False


def _backup_file(path: str) -> str:
    """Create a timestamped .backup-YYYYMMDDHHMMSS copy next to the file."""
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    dest = f'{path}.backup-{stamp}'
    shutil.copy2(path, dest)
    return dest


def _strip_password(path: str) -> bool:
    """Run remove_mdb_password.remove_mdb_password() on the file in place."""
    try:
        from remove_mdb_password import remove_mdb_password as _rm
    except ImportError:
        print('   [error] remove_mdb_password.py not found alongside this script.')
        return False
    return bool(_rm(path))


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'processed': {}}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')


# ─── main routine ─────────────────────────────────────────────────


def setup_databases() -> int:
    print('=' * 60)
    print('  Gym System - database setup')
    print('=' * 60)
    print()

    # Late import: file_finder pulls FileFinder, which on Windows scans drives.
    from core.file_finder import FileFinder

    print('Searching for .mdb files (this may take a minute on first run)...')
    finder = FileFinder()
    results = finder.search_for_mdb()
    print(f'Found {len(results)} candidate file(s).')
    print()

    if not results:
        print('[warn] No .mdb files were found. The desktop will search again at runtime.')
        return 0

    state = _load_state()
    config = load_config()
    config_changed = False

    for r in results:
        path = r['path']
        size = r.get('size_formatted', '')
        print(f'[{size}]  {path}')

        # Schema check — only act on files we recognise.
        schema = _detect_schema(path)
        print(f'   schema: {schema}')
        if schema not in ('device', 'backup'):
            print('   (not a gym-system database — skipped)')
            print()
            continue

        # Skip if we processed this file before (and it's still in the same state).
        prev = state['processed'].get(path)
        if prev and prev.get('outcome') in ('opened', 'stripped', 'no_password'):
            # Re-verify quickly: if the file is now password-locked again, fall through.
            if _has_password(path) and prev['outcome'] in ('stripped', 'no_password'):
                print('   was previously unlocked but is locked again — re-running.')
            elif prev.get('outcome') == 'opened':
                pw = prev.get('password', '')
                if _try_password(path, pw):
                    print(f'   already configured (password: {"(blank)" if pw == "" else pw!r}).')
                    print()
                    continue
                print('   stored password no longer works — re-running.')
            else:
                print('   already password-free.')
                # Still save the path into config in case it was edited away.
                if schema == 'backup':
                    config_changed |= _set_config(config, 'db_path', path)
                else:
                    config_changed |= _set_config(config, 'att2000_db_path', path)
                print()
                continue

        # Step 1 — already password-free?
        if not _has_password(path):
            print('   no password set — leaving as-is.')
            state['processed'][path] = {'outcome': 'no_password', 'when': datetime.now().isoformat()}
            if schema == 'backup':
                config_changed |= _set_config(config, 'db_path', path)
                config_changed |= _set_config(config, 'database_password', '')
            else:
                config_changed |= _set_config(config, 'att2000_db_path', path)
                config_changed |= _set_config(config, 'att2000_password', '')
            print()
            continue

        # Step 2 — try the known passwords.
        opened_with = None
        for pw in PASSWORDS_TO_TRY:
            if _try_password(path, pw):
                opened_with = pw
                break

        if opened_with is not None:
            label = '(blank)' if opened_with == '' else repr(opened_with)
            print(f'   ✓ opened with password: {label}')
            state['processed'][path] = {
                'outcome': 'opened',
                'password': opened_with,
                'when': datetime.now().isoformat(),
            }
            if schema == 'backup':
                config_changed |= _set_config(config, 'db_path', path)
                config_changed |= _set_config(config, 'database_password', opened_with)
            else:
                config_changed |= _set_config(config, 'att2000_db_path', path)
                config_changed |= _set_config(config, 'att2000_password', opened_with)
            print()
            continue

        # Step 3 — strip the password.
        print('   none of the known passwords worked. Stripping the password from the header...')
        try:
            backup = _backup_file(path)
            print(f'   backup saved to: {backup}')
        except Exception as exc:
            print(f'   [error] could not back up the file: {exc}')
            state['processed'][path] = {'outcome': 'error', 'reason': f'backup failed: {exc}'}
            print()
            continue

        if _strip_password(path):
            # Verify it actually opens with no password now.
            if _try_password(path, ''):
                print('   ✓ password removed successfully.')
                state['processed'][path] = {
                    'outcome': 'stripped',
                    'when': datetime.now().isoformat(),
                }
                if schema == 'backup':
                    config_changed |= _set_config(config, 'db_path', path)
                    config_changed |= _set_config(config, 'database_password', '')
                else:
                    config_changed |= _set_config(config, 'att2000_db_path', path)
                    config_changed |= _set_config(config, 'att2000_password', '')
            else:
                print('   [warn] header was rewritten but pyodbc still cannot open it.')
                print(f'   Restore from {backup} if needed.')
                state['processed'][path] = {'outcome': 'strip_failed_verify', 'when': datetime.now().isoformat()}
        else:
            print('   [error] password removal failed.')
            state['processed'][path] = {'outcome': 'strip_failed', 'when': datetime.now().isoformat()}
        print()

    _save_state(state)
    if config_changed:
        save_config(config)
        print('Config updated at ~/.gym_bridge/config.json')

    print('Done.')
    return 0


def _set_config(config: dict, key: str, value) -> bool:
    """Update config in-place, return True if it actually changed.

    Some keys are aliased in the codebase (e.g., 'db_path' is read by main.py
    but the default config writes 'database_path'). Mirror to both so neither
    code path silently misses the value.
    """
    aliases = {
        'db_path': ('db_path', 'database_path'),
        'database_path': ('db_path', 'database_path'),
    }
    keys = aliases.get(key, (key,))
    changed = False
    for k in keys:
        if config.get(k) != value:
            config[k] = value
            changed = True
    return changed


if __name__ == '__main__':
    sys.exit(setup_databases())
