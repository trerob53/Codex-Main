"""
Cerasus Hub — Lock Manager
One-editor-at-a-time model using a lock file on the shared drive.
Used by the Operations module for concurrent edit protection.
"""

import json
import os
import getpass
import socket
from datetime import datetime, timezone, timedelta

from src.config import LOCK_FILE, STALE_LOCK_THRESHOLD_MINUTES, ensure_directories


def acquire_lock(username: str) -> bool:
    """Try to acquire the edit lock. Returns True if acquired."""
    ensure_directories()
    info = get_lock_info()
    if info is not None:
        if info["username"] == username and info["computer"] == socket.gethostname():
            _write_lock(username)
            return True
        return False
    _write_lock(username)
    return True


def release_lock(username: str) -> bool:
    """Release the lock. Only the holder can release."""
    info = get_lock_info()
    if info is None:
        return True
    if info["username"] != username:
        return False
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass
    return True


def force_release_lock() -> bool:
    """Admin override: forcibly remove the lock file."""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        return True
    except OSError:
        return False


def get_lock_info() -> dict | None:
    """Read current lock info, or None if unlocked."""
    if not os.path.exists(LOCK_FILE):
        return None
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return None


def is_lock_stale() -> bool:
    """Check if the lock is older than the threshold."""
    info = get_lock_info()
    if info is None:
        return False
    try:
        lock_time = datetime.fromisoformat(info["timestamp"])
        age = datetime.now(timezone.utc) - lock_time
        return age > timedelta(minutes=STALE_LOCK_THRESHOLD_MINUTES)
    except (KeyError, ValueError):
        return True


def _write_lock(username: str):
    """Write the lock file."""
    data = {
        "username": username,
        "computer": socket.gethostname(),
        "os_user": getpass.getuser(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    tmp = LOCK_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, LOCK_FILE)
