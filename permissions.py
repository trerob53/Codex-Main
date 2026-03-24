"""Granular role-based permission system for CerasusHub.

Permissions are stored in the database settings table as JSON.
Default permissions are assigned based on role (admin/standard/viewer).
Admins can customize permissions per user.
"""

import json
from src.database import get_conn

# Default permission sets by role
DEFAULT_PERMISSIONS = {
    "admin": {
        "operations.view": True, "operations.edit": True, "operations.admin": True,
        "uniforms.view": True, "uniforms.edit": True, "uniforms.admin": True,
        "attendance.view": True, "attendance.edit": True, "attendance.admin": True,
        "training.view": True, "training.edit": True, "training.admin": True,
        "hub.analytics": True, "hub.settings": True,
    },
    "standard": {
        "operations.view": True, "operations.edit": True, "operations.admin": False,
        "uniforms.view": True, "uniforms.edit": True, "uniforms.admin": False,
        "attendance.view": True, "attendance.edit": True, "attendance.admin": False,
        "training.view": True, "training.edit": False, "training.admin": False,
        "hub.analytics": True, "hub.settings": False,
    },
    "director": {
        "operations.view": True, "operations.edit": False, "operations.admin": False,
        "uniforms.view": True, "uniforms.edit": False, "uniforms.admin": False,
        "attendance.view": True, "attendance.edit": False, "attendance.admin": False,
        "training.view": True, "training.edit": False, "training.admin": False,
        "hub.analytics": True, "hub.settings": False,
    },
    "viewer": {
        "operations.view": True, "operations.edit": False, "operations.admin": False,
        "uniforms.view": True, "uniforms.edit": False, "uniforms.admin": False,
        "attendance.view": True, "attendance.edit": False, "attendance.admin": False,
        "training.view": True, "training.edit": False, "training.admin": False,
        "hub.analytics": False, "hub.settings": False,
    },
}


def get_user_permissions(username: str, role: str = "") -> dict:
    """Get permissions for a user. Checks for custom overrides first, then falls back to role defaults."""
    # Check for custom user-level permissions
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (f"permissions_{username}",)
        ).fetchone()
        conn.close()
        if row:
            return json.loads(row["value"])
    except Exception:
        pass

    # Fall back to role defaults
    return DEFAULT_PERMISSIONS.get(role, DEFAULT_PERMISSIONS["viewer"]).copy()


def set_user_permissions(username: str, permissions: dict):
    """Save custom permissions for a specific user."""
    try:
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (f"permissions_{username}", json.dumps(permissions))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def has_permission(app_state: dict, permission: str) -> bool:
    """Check if the current user has a specific permission.
    Usage: has_permission(app_state, 'attendance.edit')
    """
    user = app_state.get("user", {})
    username = user.get("username", "")
    role = user.get("role", "viewer")

    perms = get_user_permissions(username, role)
    return perms.get(permission, False)


def get_all_permission_keys() -> list:
    """Return list of all permission keys for UI display."""
    return sorted(DEFAULT_PERMISSIONS["admin"].keys())
