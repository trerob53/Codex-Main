"""
Cerasus Hub — Unified Authentication
PBKDF2-HMAC-SHA256 auth against the SQLite users table.
"""

import hashlib
import json
import secrets
from datetime import datetime, timezone

from src.config import ROLE_ADMIN, ROLE_STANDARD
from src.database import get_conn


def _hash_password(password: str, salt: str = "") -> tuple:
    """Hash a password with PBKDF2. Returns (hash_hex, salt_hex)."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return hashed.hex(), salt


def _gen_id() -> str:
    return secrets.token_hex(12)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_users():
    """Ensure default admin account exists on first run."""
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
    if row["c"] == 0:
        pw_hash, salt = _hash_password("admin")
        conn.execute(
            """INSERT INTO users (user_id, username, password_hash, salt, role,
               display_name, email, active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (_gen_id(), "admin", pw_hash, salt, ROLE_ADMIN,
             "Administrator", "admin@cerasus.us", _now(), _now())
        )
        conn.commit()
    conn.close()


def authenticate(username: str, password: str):
    """Authenticate with username and password. Returns user dict or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND active = 1",
        (username.strip().lower(),)
    ).fetchone()
    conn.close()

    if not row:
        return None

    pw_hash, _ = _hash_password(password, row["salt"])
    if pw_hash != row["password_hash"]:
        return None

    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "role": row["role"],
        "display_name": row["display_name"],
        "email": row["email"],
    }


def verify_password(username: str, password: str) -> bool:
    """Check if the given password matches the stored hash for a user."""
    username = username.strip().lower()
    conn = get_conn()
    row = conn.execute(
        "SELECT password_hash, salt FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    if not row:
        return False
    pw_hash, _ = _hash_password(password, row["salt"])
    return pw_hash == row["password_hash"]


def get_all_users() -> list:
    """Get all user accounts (without password hashes)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, username, role, display_name, email, active, created_at FROM users"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str, display_name: str, email: str = "") -> bool:
    """Create a new user. Returns False if username already exists."""
    conn = get_conn()
    existing = conn.execute(
        "SELECT 1 FROM users WHERE username = ?", (username.strip().lower(),)
    ).fetchone()
    if existing:
        conn.close()
        return False

    pw_hash, salt = _hash_password(password)
    conn.execute(
        """INSERT INTO users (user_id, username, password_hash, salt, role,
           display_name, email, active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (_gen_id(), username.strip().lower(), pw_hash, salt, role,
         display_name.strip() or username, email.strip(), _now(), _now())
    )
    conn.commit()
    conn.close()
    return True


def update_user(username: str, new_password: str = "", new_role: str = "",
                new_display_name: str = "", new_active: int = -1) -> bool:
    """Update user fields. Only updates non-empty/non-default values."""
    username = username.strip().lower()
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        conn.close()
        return False

    updates = []
    params = []
    if new_password:
        pw_hash, salt = _hash_password(new_password)
        updates.extend(["password_hash = ?", "salt = ?"])
        params.extend([pw_hash, salt])
    if new_role:
        updates.append("role = ?")
        params.append(new_role)
    if new_display_name:
        updates.append("display_name = ?")
        params.append(new_display_name.strip())
    if new_active >= 0:
        updates.append("active = ?")
        params.append(new_active)

    if updates:
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(username)
        conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE username = ?", params)
        conn.commit()

    conn.close()
    return True


PASSWORD_EXPIRY_DAYS = 90


def must_change_password(username: str) -> bool:
    """Check if user needs to change password (default or expired)."""
    username = username.strip().lower()
    conn = get_conn()
    row = conn.execute("SELECT password_hash, salt, updated_at FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if not row:
        return False
    # Check if password is still the default "admin"
    test_hash, _ = _hash_password("admin", row["salt"])
    if test_hash == row["password_hash"] and username == "admin":
        return True
    # Check password expiry (90 days)
    if row["updated_at"]:
        try:
            updated = datetime.fromisoformat(str(row["updated_at"])[:19])
            if (datetime.now(timezone.utc).replace(tzinfo=None) - updated).days >= PASSWORD_EXPIRY_DAYS:
                return True
        except (ValueError, TypeError):
            pass
    return False


def password_expires_soon(username: str, days_warning: int = 14) -> int:
    """Return days until password expires, or -1 if not expiring soon."""
    username = username.strip().lower()
    conn = get_conn()
    row = conn.execute("SELECT updated_at FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if not row or not row["updated_at"]:
        return -1
    try:
        updated = datetime.fromisoformat(str(row["updated_at"])[:19])
        age_days = (datetime.now(timezone.utc).replace(tzinfo=None) - updated).days
        remaining = PASSWORD_EXPIRY_DAYS - age_days
        if 0 < remaining <= days_warning:
            return remaining
    except (ValueError, TypeError):
        pass
    return -1


def delete_user(username: str) -> bool:
    """Delete a user. Prevents deleting the last admin."""
    username = username.strip().lower()
    conn = get_conn()
    row = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        conn.close()
        return False

    if row["role"] == ROLE_ADMIN:
        admin_count = conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE role = ? AND active = 1",
            (ROLE_ADMIN,)
        ).fetchone()["c"]
        if admin_count <= 1:
            conn.close()
            return False

    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return True


def get_user_modules(username: str) -> list[str]:
    """Get list of allowed module IDs for a user.

    Returns an empty list if the user has no restrictions (all modules allowed).
    A non-empty list means only those module_ids are accessible.
    """
    username = username.strip().lower()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT module_permissions FROM users WHERE username = ?", (username,)
        ).fetchone()
    except Exception:
        conn.close()
        return []
    conn.close()

    if not row:
        return []

    raw = row["module_permissions"] or ""
    if not raw or raw.strip() in ("", "[]"):
        return []

    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def set_user_modules(username: str, module_ids: list[str]):
    """Set the allowed modules for a user. Empty list means all modules."""
    username = username.strip().lower()
    value = json.dumps(module_ids) if module_ids else ""
    conn = get_conn()
    conn.execute(
        "UPDATE users SET module_permissions = ?, updated_at = ? WHERE username = ?",
        (value, _now(), username),
    )
    conn.commit()
    conn.close()


# ── Site-Based Access Control ────────────────────────────────────────

def get_user_sites(username: str) -> list[str]:
    """Get assigned sites for a user. Empty list = all sites (no restriction)."""
    username = username.strip().lower()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT assigned_sites FROM users WHERE username = ?", (username,)
        ).fetchone()
    except Exception:
        conn.close()
        return []
    conn.close()

    if not row:
        return []

    raw = row["assigned_sites"] or ""
    if not raw or raw.strip() in ("", "[]"):
        return []

    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def set_user_sites(username: str, site_names: list[str]):
    """Set the assigned sites for a user. Empty list means all sites (unrestricted)."""
    username = username.strip().lower()
    value = json.dumps(site_names) if site_names else ""
    conn = get_conn()
    conn.execute(
        "UPDATE users SET assigned_sites = ?, updated_at = ? WHERE username = ?",
        (value, _now(), username),
    )
    conn.commit()
    conn.close()


def get_accessible_sites(username: str, role: str) -> list[str]:
    """Get list of site names this user can access. Admin role = all sites (empty list)."""
    if role == ROLE_ADMIN:
        return []  # No restriction
    return get_user_sites(username)
