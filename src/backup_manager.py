"""
Cerasus Hub -- Database Backup Manager
Automated and manual backup/restore of the SQLite database.
"""

import os
import shutil
import glob
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import threading
import time

from src.config import DB_FILE, BACKUP_DIR
from src import audit


# ---------------------------------------------------------------------------
# Core backup functions
# ---------------------------------------------------------------------------

def ensure_backup_dir():
    """Create the data/backups/ directory if it doesn't exist."""
    os.makedirs(BACKUP_DIR, exist_ok=True)


def create_backup(reason: str = "scheduled") -> str:
    """
    Copy the current cerasus_hub.db to data/backups/ with a timestamped name.
    Returns the backup file path, or empty string on failure.
    """
    if not os.path.exists(DB_FILE):
        return ""

    ensure_backup_dir()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_reason = reason.replace(" ", "_").replace("/", "_")[:30]
    backup_name = f"cerasus_hub_{timestamp}_{safe_reason}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    try:
        shutil.copy2(DB_FILE, backup_path)
    except Exception as e:
        print(f"[Backup] Failed to create backup: {e}")
        return ""

    # Log to audit
    try:
        audit.log_event(
            module_name="backup",
            event_type="backup_created",
            username="system",
            details=f"Backup created: {backup_name} (reason: {reason})",
            action="create",
        )
    except Exception:
        pass

    return backup_path


def rotate_backups(keep_daily: int = 7, keep_weekly: int = 4) -> int:
    """
    Rotate old backups:
    - Keep the most recent *keep_daily* daily backups.
    - Keep one backup per week for the last *keep_weekly* weeks.
    - Delete everything else.
    Returns count of deleted files.
    """
    ensure_backup_dir()
    pattern = os.path.join(BACKUP_DIR, "cerasus_hub_*.db")
    all_backups = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    if not all_backups:
        return 0

    keep = set()

    # 1. Keep the most recent keep_daily backups (regardless of date)
    for path in all_backups[:keep_daily]:
        keep.add(path)

    # 2. Keep one per week for the last keep_weekly weeks
    now = datetime.now()
    weekly_buckets = defaultdict(list)
    for path in all_backups:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            # Week number relative to now (0 = this week, 1 = last week, etc.)
            delta_days = (now - mtime).days
            week_num = delta_days // 7
            if week_num < keep_weekly:
                weekly_buckets[week_num].append(path)
        except Exception:
            continue

    for week_num, paths in weekly_buckets.items():
        # Keep the most recent backup from each week
        if paths:
            keep.add(paths[0])  # already sorted by mtime desc

    # Delete everything not in the keep set
    deleted = 0
    for path in all_backups:
        if path not in keep:
            try:
                os.remove(path)
                deleted += 1
            except Exception:
                pass

    if deleted:
        try:
            audit.log_event(
                module_name="backup",
                event_type="backup_rotation",
                username="system",
                details=f"Rotated backups: {deleted} old backup(s) deleted",
                action="rotate",
            )
        except Exception:
            pass

    return deleted


def get_backup_list() -> list:
    """
    Return a list of available backups with metadata.
    Each dict: {filename, path, size_mb, created_at, reason}
    """
    ensure_backup_dir()
    pattern = os.path.join(BACKUP_DIR, "cerasus_hub_*.db")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    result = []
    for path in files:
        filename = os.path.basename(path)
        try:
            size_bytes = os.path.getsize(path)
            mtime = os.path.getmtime(path)
            created_dt = datetime.fromtimestamp(mtime)
        except Exception:
            continue

        # Extract reason from filename: cerasus_hub_YYYYMMDD_HHMMSS_{reason}.db
        parts = filename.replace(".db", "").split("_")
        # parts: ['cerasus', 'hub', 'YYYYMMDD', 'HHMMSS', ...reason parts...]
        reason = "_".join(parts[4:]) if len(parts) > 4 else "unknown"

        result.append({
            "filename": filename,
            "path": path,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "created_at": created_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason,
        })

    return result


def restore_backup(backup_path: str) -> bool:
    """
    Restore a backup by copying it over the main database.
    DANGEROUS -- caller must confirm with the user before invoking.
    Returns True on success, False on failure.
    """
    if not os.path.exists(backup_path):
        return False

    # Create a pre-restore safety backup first
    safety = create_backup(reason="pre-restore")

    try:
        shutil.copy2(backup_path, DB_FILE)
    except Exception as e:
        print(f"[Backup] Restore failed: {e}")
        return False

    try:
        audit.log_event(
            module_name="backup",
            event_type="backup_restored",
            username="system",
            details=f"Database restored from: {os.path.basename(backup_path)}",
            action="restore",
        )
    except Exception:
        pass

    return True


def get_last_backup_time() -> str:
    """Return the timestamp of the most recent backup, or empty string if none."""
    backups = get_backup_list()
    if backups:
        return backups[0]["created_at"]
    return ""


# ---------------------------------------------------------------------------
# Background scheduler
# ---------------------------------------------------------------------------

class BackupScheduler(threading.Thread):
    """
    Background daemon thread that creates periodic database backups.
    - On startup: creates a backup if the last one was >24h ago.
    - Then sleeps and runs again at the configured interval.
    - Runs rotate_backups() after each backup.
    """

    def __init__(self, interval_hours=4):
        super().__init__(daemon=True, name="BackupScheduler")
        self._interval = interval_hours * 3600
        self._stop_event = threading.Event()

    def run(self):
        # Check if a backup is needed on startup
        if self._should_backup():
            self._do_backup()

        # Then loop at the configured interval
        while not self._stop_event.wait(self._interval):
            self._do_backup()

    def _should_backup(self) -> bool:
        """Return True if no backup exists or the newest is older than 24h."""
        backups = get_backup_list()
        if not backups:
            return True
        try:
            last_dt = datetime.strptime(backups[0]["created_at"], "%Y-%m-%d %H:%M:%S")
            return (datetime.now() - last_dt) > timedelta(hours=24)
        except Exception:
            return True

    def _do_backup(self):
        path = create_backup("scheduled")
        if path:
            rotate_backups()

    def stop(self):
        self._stop_event.set()
