"""
Cerasus Hub -- Uniforms Module: Notification Log
Tracks uniform-related notifications (low stock alerts, compliance warnings, etc.).
"""

from datetime import datetime, timezone

from src.database import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_notification(category: str, message: str, officer_id: str = "", severity: str = "info"):
    """Log a uniform-related notification."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uni_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT DEFAULT '',
            message TEXT DEFAULT '',
            officer_id TEXT DEFAULT '',
            severity TEXT DEFAULT 'info',
            read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ''
        )
    """)
    conn.execute(
        """INSERT INTO uni_notifications (category, message, officer_id, severity, created_at)
           VALUES (?,?,?,?,?)""",
        (category, message, officer_id, severity, _now()),
    )
    conn.commit()
    conn.close()


def get_notifications(limit: int = 100) -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM uni_notifications ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []


def get_notification_stats() -> dict:
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM uni_notifications").fetchone()["cnt"]
        unread = conn.execute("SELECT COUNT(*) as cnt FROM uni_notifications WHERE read = 0").fetchone()["cnt"]
        conn.close()
        return {"total": total, "unread": unread}
    except Exception:
        conn.close()
        return {"total": 0, "unread": 0}


def mark_read(notification_id: int):
    conn = get_conn()
    conn.execute("UPDATE uni_notifications SET read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()
