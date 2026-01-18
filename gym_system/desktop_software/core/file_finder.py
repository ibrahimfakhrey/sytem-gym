"""
File Finder - Search for .mdb database files on the computer
"""

import os
import string
from typing import List, Dict, Optional
from datetime import datetime


class FileFinder:
    """Find .mdb database files on the computer"""

    def __init__(self):
        self.found_databases = []

    def get_drives(self) -> List[str]:
        """Get available drives on Windows"""
        drives = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append(drive)
        return drives

    def search_for_mdb(self, callback=None) -> List[Dict]:
        """
        Search for .mdb files on all drives
        callback: function(progress, message) for progress updates
        """
        self.found_databases = []
        drives = self.get_drives()

        # Common paths to search first (faster)
        common_paths = [
            "C:\\AAS",
            "C:\\Program Files\\AAS",
            "C:\\Program Files (x86)\\AAS",
            "D:\\AAS",
            os.path.expanduser("~\\Documents"),
            os.path.expanduser("~\\Desktop"),
        ]

        total_paths = len(common_paths) + len(drives)
        current = 0

        # Search common paths first
        for path in common_paths:
            current += 1
            if callback:
                progress = int((current / total_paths) * 50)
                callback(progress, f"جاري البحث في: {path}")

            if os.path.exists(path):
                self._search_directory(path, max_depth=5)

        # If not found in common paths, search all drives
        if not self.found_databases:
            for drive in drives:
                current += 1
                if callback:
                    progress = 50 + int((current / len(drives)) * 50)
                    callback(progress, f"جاري البحث في: {drive}")

                self._search_directory(drive, max_depth=4)

        if callback:
            callback(100, "اكتمل البحث")

        return self.found_databases

    def _search_directory(self, path: str, max_depth: int = 3, current_depth: int = 0):
        """Recursively search directory for .mdb files"""
        if current_depth > max_depth:
            return

        try:
            for item in os.listdir(path):
                item_path = os.path.join(path, item)

                try:
                    if os.path.isfile(item_path):
                        if item.lower().endswith('.mdb'):
                            # Check if it's the AAS database (tmkq.mdb)
                            if 'tmkq' in item.lower() or 'aas' in item_path.lower():
                                self._add_database(item_path)

                    elif os.path.isdir(item_path):
                        # Skip system directories
                        skip_dirs = ['windows', 'program files', '$recycle.bin',
                                    'system volume information', 'programdata']
                        if item.lower() not in skip_dirs:
                            self._search_directory(item_path, max_depth, current_depth + 1)

                except PermissionError:
                    continue
                except Exception:
                    continue

        except PermissionError:
            pass
        except Exception:
            pass

    def _add_database(self, path: str):
        """Add found database to list"""
        try:
            stat = os.stat(path)
            size = stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime)

            # Determine if it's backup or active
            is_backup = 'backup' in path.lower() or 'bak' in path.lower()

            db_info = {
                'path': path,
                'filename': os.path.basename(path),
                'directory': os.path.dirname(path),
                'size': size,
                'size_formatted': self._format_size(size),
                'modified': modified,
                'modified_formatted': modified.strftime('%Y-%m-%d %H:%M'),
                'is_backup': is_backup,
                'type': 'نسخة احتياطية' if is_backup else 'قاعدة البيانات الرئيسية'
            }

            # Avoid duplicates
            for existing in self.found_databases:
                if existing['path'] == path:
                    return

            self.found_databases.append(db_info)

        except Exception:
            pass

    def _format_size(self, size: int) -> str:
        """Format file size to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def get_active_database(self) -> Optional[Dict]:
        """Get the main (non-backup) database"""
        for db in self.found_databases:
            if not db['is_backup']:
                return db
        return None

    def get_backup_database(self) -> Optional[Dict]:
        """Get the backup database"""
        for db in self.found_databases:
            if db['is_backup']:
                return db
        return None
