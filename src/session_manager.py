"""
Cerasus Hub — Session Manager
Tracks active user sessions with heartbeat for multi-user awareness.
"""

import secrets
import socket
from datetime import datetime, timezone, timedelta

from src.database import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_session(username: str, role: str) -> str:
    """Register a new session. Returns session_id."""
    session_id = secrets.token_hex(12)
    conn = get_conn()
    conn.execute(
        """INSERT INTO sessions (session_id, username, role, machine_name,
           active_module, started_at, last_heartbeat)
           VALUES (?, ?, ?, ?, '', ?, ?)""",
        (session_id, username, role, socket.gethostname(), _now(), _now())
    )
    conn.commit()
    conn.close()
    return session_id


def heartbeat_session(session_id: str, active_module: str = ""):
    """Update the heartbeat timestamp for a session."""
    conn = get_conn()
    conn.execute(
        "UPDATE sessions SET last_heartbeat = ?, active_module = ? WHERE session_id = ?",
        (_now(), active_module, session_id)
    )
    conn.commit()
    conn.close()


def remove_session(session_id: str):
    """Remove a session on logout/close."""
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def get_active_sessions(max_age_minutes: int = 5) -> list:
    """Get sessions with a heartbeat within the last N minutes."""
    conn = get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat()
    rows = conn.execute(
        "SELECT * FROM sessions WHERE last_heartbeat > ?", (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_online_users(max_age_minutes: int = 3) -> list:
    """Get currently online users with their active module and machine."""
    conn = get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat()
    rows = conn.execute(
        """SELECT username, role, machine_name, active_module, started_at, last_heartbeat
           FROM sessions WHERE last_heartbeat > ?
           ORDER BY username""",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_history(hours: int = 24) -> list:
    """Get recent session activity for the last N hours."""
    conn = get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """SELECT username, role, machine_name, active_module, started_at, last_heartbeat
           FROM sessions WHERE started_at > ?
           ORDER BY last_heartbeat DESC""",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cleanup_stale_sessions(max_age_minutes: int = 10):
    """Remove sessions that haven't sent a heartbeat recently."""
    conn = get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat()
    conn.execute("DELETE FROM sessions WHERE last_heartbeat < ?", (cutoff,))
    conn.commit()
    conn.close()
