"""
File Finder — auto-detect backup.mdb (members) and att2000.mdb (device) on Windows.
"""
import os
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
    """Heuristic — backup.mdb has 'backup', 'tmkq', or 'employee' in name."""
    name = os.path.basename(path).lower()
    return name in ('backup.mdb', 'tmkq.mdb') or 'backup' in name


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


def search(roots=None, max_depth: int = 4) -> Tuple[Optional[str], Optional[str]]:
    """
    Search for backup.mdb and att2000.mdb. Returns (members_path, device_path).
    """
    if roots is None:
        roots = COMMON_PATHS

    found_members = None
    found_device = None

    for root in roots:
        if not os.path.isdir(root):
            continue
        for cur_path, dirs, files in os.walk(root):
            # Calculate depth
            rel = os.path.relpath(cur_path, root)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth > max_depth:
                dirs[:] = []
                continue

            # Filter dirs
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
