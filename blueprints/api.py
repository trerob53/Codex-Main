"""
Cerasus Hub — API Blueprint
REST API endpoints (replaces web_companion.py).
"""

from flask import Blueprint, jsonify, session

from src.web_middleware import login_required
from src import session_manager
from src.config import COLORS, save_setting

api_bp = Blueprint("api", __name__, url_prefix="/api")


# dev_login endpoint REMOVED — was a critical security vulnerability (BUG-001)
# Any user could access /api/dev-login to bypass authentication entirely.


@api_bp.route("/dashboard")
@login_required
def dashboard():
    """Hub-level KPI snapshot."""
    data = {"officers": 0, "pending_reviews": 0, "low_stock": 0, "open_requests": 0}
    try:
        from src.database import get_conn
        conn = get_conn()
        data["officers"] = conn.execute(
            "SELECT COUNT(*) FROM officers WHERE status='Active' OR status IS NULL"
        ).fetchone()[0]
        try:
            data["pending_reviews"] = conn.execute(
                "SELECT COUNT(*) FROM ats_employment_reviews WHERE status='Pending'"
            ).fetchone()[0]
        except Exception:
            pass
        try:
            data["low_stock"] = conn.execute(
                "SELECT COUNT(*) FROM uni_catalog WHERE quantity <= reorder_point"
            ).fetchone()[0]
        except Exception:
            pass
        conn.close()
    except Exception:
        pass
    return jsonify(data)


@api_bp.route("/officers")
@login_required
def officers():
    """Active officers list."""
    try:
        from src.shared_data import get_all_officers
        officers = get_all_officers()
        return jsonify([{
            "officer_id": o.get("officer_id"),
            "name": o.get("name"),
            "employee_id": o.get("employee_id"),
            "site": o.get("site"),
            "status": o.get("status", "Active"),
        } for o in officers])
    except Exception:
        return jsonify([])


@api_bp.route("/sessions")
@login_required
def sessions():
    """Online users."""
    try:
        users = session_manager.get_online_users()
        return jsonify(users)
    except Exception:
        return jsonify([])


@api_bp.route("/online-users")
@login_required
def online_users():
    """HTMX partial — online user count for topbar (clickable for details)."""
    try:
        users = session_manager.get_online_users()
        current = session.get("username", "")
        others = [u for u in users if u.get("username") != current]
        count = len(others) + 1
        if others:
            names = ", ".join(u["username"] for u in others[:3])
            label = f'{count} online'
        else:
            label = 'You are the only one online'
        # Wrap in a clickable span that shows detail dropdown
        return (f'<span class="online-dot"></span>'
                f'<span style="cursor:pointer;" onclick="toggleOnlineDetail()">{label}</span>'
                f'<div id="online-detail" style="display:none;position:absolute;top:48px;right:0;background:var(--card);'
                f'border:1px solid var(--border);border-radius:8px;padding:12px 16px;min-width:240px;'
                f'box-shadow:0 8px 24px rgba(0,0,0,0.15);z-index:200;font-size:13px;">'
                f'<div style="font-weight:600;margin-bottom:8px;">{count} user{"s" if count != 1 else ""} online</div>'
                + ''.join(
                    f'<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border);">'
                    f'<span>{u["username"]}</span>'
                    f'<span style="color:var(--text-light);font-size:12px;">{u.get("active_module") or "hub"}</span></div>'
                    for u in users
                )
                + '</div>')
    except Exception:
        return '<span class="online-dot"></span><span>1 online</span>'


@api_bp.route("/online-users-bar")
@login_required
def online_users_bar():
    """HTMX partial — online user detail for hub picker."""
    try:
        users = session_manager.get_online_users()
        current = session.get("username", "")
        others = [u for u in users if u.get("username") != current]
        if not others:
            return '<span class="online-dot"></span><span style="font-weight:600;">You\'re the only one online</span>'
        count = len(others) + 1
        names = ", ".join(u["username"] for u in others[:5])
        details = []
        for u in others[:5]:
            mod = u.get("active_module", "")
            if mod:
                details.append(f'{u["username"]} in {mod}')
            else:
                details.append(f'{u["username"]} (hub)')
        detail_str = "  |  ".join(details)
        return (f'<span class="online-dot"></span>'
                f'<span style="font-weight:600;">{count} online</span>'
                f'<span class="text-light" style="font-size:12px;">{detail_str}</span>')
    except Exception:
        return '<span class="online-dot"></span><span>Checking...</span>'


@api_bp.route("/toggle-dark", methods=["POST"])
@login_required
def toggle_dark():
    """Toggle dark mode preference."""
    current = session.get("dark_mode", False)
    session["dark_mode"] = not current
    save_setting("dark_mode", not current)
    return jsonify({"dark_mode": not current})


@api_bp.route("/set-last-module", methods=["POST"])
@login_required
def set_last_module():
    """Track which module the user last visited."""
    from flask import request
    data = request.get_json(silent=True) or {}
    module = data.get("module", "")
    if module:
        session["last_module"] = module
    return jsonify({"ok": True})
