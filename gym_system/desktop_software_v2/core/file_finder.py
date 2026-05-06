"""
File Finder — auto-detect the gym's database.

Strategy (in order):
  1. Look for FPAttend.ini — Attendancear/AAS6.0 config file. It contains:
        [System]
        DataBase=tmkq.mdb
        TmKqDB=tmkq.mdb
     This pinpoints the exact DB path. (Most accurate — used by AAS6.0)

  2. Fall back to scanning for tmkq.mdb / backup.mdb / att2000.mdb in common
     install folders, skipping daily backups.
"""
import os
import configparser
from typing import Optional, Tuple

# Common install paths for ZKTeco / Attendancear / AAS systems
COMMON_PATHS = [
    r'C:\AAS6.0',
    r'C:\AAS',
    r'C:\Program Files (x86)\AAS6.0',
    r'C:\Program Files\AAS6.0',
    r'C:\Program Files (x86)\AAS',
    r'C:\Program Files\AAS',
    r'C:\Program Files (x86)\Attendancear',
    r'C:\Program Files\Attendancear',
    r'C:\Attendancear',
    r'C:\ZKTeco',
    r'C:\Program Files (x86)\ZKTeco',
    r'C:\Program Files\ZKTeco',
    os.path.expanduser('~/Desktop'),
    os.path.expanduser('~/Documents'),
]

SKIP_DIRS = {
    'windows', '$recycle.bin', 'system volume information',
    'programdata', 'appdata', 'node_modules', '.git', 'winsxs',
    'assembly', 'microsoft.net', 'backupdata',
}


def is_member_db(path: str) -> bool:
    """Heuristic — main DB file has 'tmkq', 'backup', or 'employee' in name."""
    name = os.path.basename(path).lower()
    return name in ('tmkq.mdb', 'backup.mdb') or 'backup' in name or 'tmkq' in name


def is_device_db(path: str) -> bool:
    """Heuristic — att2000.mdb is the ZKTeco device file."""
    name = os.path.basename(path).lower()
    return name == 'att2000.mdb' or 'att' in name and name.endswith('.mdb')


def is_daily_backup(path: str) -> bool:
    """Skip files like 1tmkqbak.mdb..31tmkqbak.mdb and BackUpData/ folder."""
    p = path.lower()
    name = os.path.basename(p)
    if 'backupdata' in p:
        return True
    if 'bak' in name and any(name.startswith(str(i)) for i in range(1, 32)):
        return True
    return False


def find_fpattend_ini(roots=None, max_depth: int = 4) -> Optional[str]:
    """Find FPAttend.ini — fastest way to locate the actual DB on AAS6.0."""
    if roots is None:
        roots = COMMON_PATHS

    for root in roots:
        if not os.path.isdir(root):
            continue
        for cur_path, dirs, files in os.walk(root):
            rel = os.path.relpath(cur_path, root)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth > max_depth:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]

            for f in files:
                if f.lower() == 'fpattend.ini':
                    return os.path.join(cur_path, f)
    return None


def parse_fpattend_ini(ini_path: str) -> Optional[str]:
    """Read DataBase= or TmKqDB= from FPAttend.ini → return absolute path to .mdb"""
    try:
        cp = configparser.ConfigParser()
        # configparser doesn't tolerate BOMs well — read manually
        with open(ini_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            cp.read_file(f)

        db_name = None
        if cp.has_section('System'):
            db_name = cp.get('System', 'DataBase', fallback=None) \
                      or cp.get('System', 'TmKqDB', fallback=None)
        if not db_name:
            return None

        # Resolve relative to ini location
        ini_dir = os.path.dirname(ini_path)
        if os.path.isabs(db_name):
            return db_name if os.path.exists(db_name) else None
        candidate = os.path.join(ini_dir, db_name)
        return candidate if os.path.exists(candidate) else None
    except Exception:
        return None


def search(roots=None, max_depth: int = 4) -> Tuple[Optional[str], Optional[str]]:
    """
    Find (members_path, device_path).

    For modern AAS6.0 (single-file): both will point to the same tmkq.mdb.
    For legacy ZKTeco: members → backup.mdb, device → att2000.mdb.
    """
    if roots is None:
        roots = COMMON_PATHS

    # Step 1: Try FPAttend.ini approach (fastest, most accurate)
    ini = find_fpattend_ini(roots, max_depth)
    if ini:
        db_path = parse_fpattend_ini(ini)
        if db_path:
            return db_path, db_path  # single-file mode → same path twice

    # Step 2: Fallback — scan for individual .mdb files
    found_members = None
    found_device = None

    for root in roots:
        if not os.path.isdir(root):
            continue
        for cur_path, dirs, files in os.walk(root):
            rel = os.path.relpath(cur_path, root)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth > max_depth:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]

            for f in files:
                full = os.path.join(cur_path, f)
                if not f.lower().endswith('.mdb'):
                    continue
                if is_daily_backup(full):
                    continue

                if not found_members and is_member_db(full):
                    found_members = full
                if not found_device and is_device_db(full):
                    found_device = full

                if found_members and found_device:
                    return found_members, found_device

    # If we found tmkq.mdb but not att2000.mdb, use tmkq for both (single-file mode)
    if found_members and not found_device:
        return found_members, found_members
    return found_members, found_device


def find_all_mdb(roots=None, max_depth: int = 4) -> list:
    """Return ALL .mdb files found (excluding daily backups). For UI manual selection."""
    if roots is None:
        roots = COMMON_PATHS

    result = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for cur_path, dirs, files in os.walk(root):
            rel = os.path.relpath(cur_path, root)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth > max_depth:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]

            for f in files:
                full = os.path.join(cur_path, f)
                if f.lower().endswith('.mdb') and not is_daily_backup(full):
                    result.append(full)
    return result
