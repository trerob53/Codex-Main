"""
Cerasus Hub — Unified Audit Logger
All modules log to the shared audit_log SQLite table.
"""

import getpass
import socket
from datetime import datetime, timezone

from src.database import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(module_name: str, event_type: str, username: str, details: str = "",
              table_name: str = "", record_id: str = "", action: str = "",
              before_value: str = "", after_value: str = "",
              justification: str = "", employee_id: str = ""):
    """Log an audit event to the unified audit_log table."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO audit_log (module_name, event_type, username, computer, os_user,
           table_name, record_id, action, before_value, after_value,
           justification, details, employee_id, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (module_name, event_type, username, socket.gethostname(), getpass.getuser(),
         table_name, record_id, action, before_value, after_value,
         justification, details, employee_id, _now())
    )
    conn.commit()
    conn.close()


def get_log(module_name: str = "", limit: int = 500) -> list:
    """Get recent audit entries, optionally filtered by module."""
    conn = get_conn()
    if module_name:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE module_name = ? ORDER BY id DESC LIMIT ?",
            (module_name, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
