"""
Cerasus Hub — Admin Blueprint
User management, audit trail, backups, settings (SMTP).
"""

import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from src.config import save_setting, load_setting
from src.web_middleware import login_required, role_required
from src import auth, audit

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/users")
@login_required
@role_required("admin")
def users():
    user_list = _get_all_users()
    sites_list = _get_all_site_names()
    return render_template("admin/users.html", users=user_list, sites_list=sites_list, active_page="admin_users")


@admin_bp.route("/users/create", methods=["POST"])
@login_required
@role_required("admin")
def create_user():
    username = request.form.get("username", "").strip()
    display_name = request.form.get("display_name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "standard")

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for("admin.users"))

    result = auth.create_user(username, password, role, display_name, email)
    if result:
        # Assign site for director role
        assigned_site = request.form.get("assigned_site", "").strip()
        if role == "director" and assigned_site:
            auth.set_user_sites(username, [assigned_site])
        audit.log_event("hub", "user_created", session.get("username", ""),
                        f"Created user: {username} ({role})" + (f" @ {assigned_site}" if assigned_site else ""))
        flash(f"User '{username}' created.", "success")
    else:
        flash(f"Could not create user '{username}' — may already exist.", "danger")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<username>/toggle", methods=["POST"])
@login_required
@role_required("admin")
def toggle_user(username):
    user_list = _get_all_users()
    target = next((u for u in user_list if u["username"] == username), None)
    if target:
        new_active = 0 if target.get("active", 1) else 1
        auth.update_user(username, new_active=new_active)
        state = "enabled" if new_active else "disabled"
        audit.log_event("hub", f"user_{state}", session.get("username", ""),
                        f"User {username} {state}")
        flash(f"User '{username}' {state}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<username>/reset-password", methods=["POST"])
@login_required
@role_required("admin")
def reset_password(username):
    auth.update_user(username, new_password="password123")
    audit.log_event("hub", "password_reset", session.get("username", ""),
                    f"Reset password for {username}")
    flash(f"Password for '{username}' reset to default.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<username>/role", methods=["POST"])
@login_required
@role_required("admin")
def update_role(username):
    new_role = request.form.get("role", "").strip()
    assigned_site = request.form.get("assigned_site", "").strip()

    if new_role not in ("admin", "director", "standard", "viewer"):
        flash("Invalid role.", "danger")
        return redirect(url_for("admin.users"))

    if username == session.get("username") and new_role != "admin":
        flash("You cannot change your own role.", "danger")
        return redirect(url_for("admin.users"))

    auth.update_user(username, new_role=new_role)

    # Update site assignment
    if new_role == "director" and assigned_site:
        auth.set_user_sites(username, [assigned_site])
    elif new_role != "director":
        auth.set_user_sites(username, [])  # Clear site restriction for non-directors

    audit.log_event("hub", "role_changed", session.get("username", ""),
                    f"Changed {username} to {new_role}" + (f" @ {assigned_site}" if assigned_site else ""))
    flash(f"Role for '{username}' updated to {new_role}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<username>/sites", methods=["POST"])
@login_required
@role_required("admin")
def update_sites(username):
    sites = request.form.getlist("sites")
    auth.set_user_sites(username, sites)
    audit.log_event("hub", "sites_changed", session.get("username", ""),
                    f"Updated sites for {username}: {', '.join(sites) if sites else 'All'}")
    flash(f"Site assignment for '{username}' updated.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<username>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_user(username):
    if username == session.get("username"):
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin.users"))

    result = auth.delete_user(username)
    if result:
        audit.log_event("hub", "user_deleted", session.get("username", ""),
                        f"Deleted user: {username}")
        flash(f"User '{username}' deleted.", "success")
    else:
        flash(f"Could not delete '{username}'.", "danger")
    return redirect(url_for("admin.users"))


@admin_bp.route("/audit")
@login_required
@role_required("admin")
def audit_page():
    try:
        from src.database import get_conn
        conn = get_conn()
        rows = conn.execute(
            "SELECT timestamp, username, module_name, event_type, action, details "
            "FROM audit_log ORDER BY timestamp DESC LIMIT 500"
        ).fetchall()
        conn.close()
        events = []
        for r in rows:
            d = dict(r) if hasattr(r, "keys") else {
                "timestamp": r[0], "username": r[1], "module_name": r[2],
                "event_type": r[3], "action": r[4], "details": r[5]
            }
            # Use event_type as display action (it holds login, logout, etc.)
            d["action"] = d.get("event_type") or d.get("action") or ""
            events.append(d)
    except Exception:
        events = []
    return render_template("admin/audit.html", events=events, active_page="admin_audit")


@admin_bp.route("/backups")
@login_required
@role_required("admin")
def backups():
    try:
        from src.backup_manager import get_backup_list
        backup_list = get_backup_list()
    except Exception:
        backup_list = []
    return render_template("admin/backups.html", backups=backup_list, active_page="admin_backups")


@admin_bp.route("/backups/create", methods=["POST"])
@login_required
@role_required("admin")
def create_backup():
    try:
        from src.backup_manager import create_backup as do_backup
        path = do_backup("manual_web")
        if path:
            flash("Backup created successfully.", "success")
        else:
            flash("Backup failed.", "danger")
    except Exception as e:
        flash(f"Backup failed: {e}", "danger")
    return redirect(url_for("admin.backups"))


@admin_bp.route("/settings")
@login_required
@role_required("admin")
def settings():
    smtp = _load_smtp_settings()
    return render_template("admin/settings.html", smtp=smtp, active_page="admin_settings")


@admin_bp.route("/settings/smtp", methods=["POST"])
@login_required
@role_required("admin")
def save_smtp():
    settings_dict = {
        "enabled": "enabled" in request.form,
        "server": request.form.get("server", "").strip(),
        "port": int(request.form.get("port", 587)),
        "use_tls": "use_tls" in request.form,
        "username": request.form.get("username", "").strip(),
        "password": request.form.get("password", "").strip(),
        "from_email": request.form.get("from_email", "").strip(),
        "from_name": request.form.get("from_name", "Cerasus Hub").strip(),
        "admin_email": request.form.get("admin_email", "").strip(),
    }
    save_setting("hub_smtp", json.dumps(settings_dict))
    audit.log_event("hub", "smtp_configured", session.get("username", ""), "SMTP settings updated")
    flash("SMTP settings saved.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/test-smtp", methods=["POST"])
@login_required
@role_required("admin")
def test_smtp():
    try:
        from src.email_service import test_smtp_connection
        ok, msg = test_smtp_connection()
        if ok:
            return f'<div class="flash flash-success">Connection successful: {msg}</div>'
        else:
            return f'<div class="flash flash-danger">Connection failed: {msg}</div>'
    except Exception as e:
        return f'<div class="flash flash-danger">Error: {e}</div>'


@admin_bp.route("/settings/send-test-email", methods=["POST"])
@login_required
@role_required("admin")
def send_test_email():
    try:
        from src.email_service import send_email, is_email_configured
        if not is_email_configured():
            return '<div class="flash flash-warning">SMTP is not configured. Save settings first.</div>'
        smtp = _load_smtp_settings()
        to = smtp.get("admin_email", "")
        if not to:
            return '<div class="flash flash-warning">No admin email configured.</div>'
        ok = send_email(to, "Cerasus Hub — Test Email",
                        "<h2>Test Email</h2><p>This confirms that email sending is working correctly.</p>")
        if ok:
            return f'<div class="flash flash-success">Test email sent to {to}</div>'
        else:
            return '<div class="flash flash-danger">Failed to send test email. Check SMTP settings.</div>'
    except Exception as e:
        return f'<div class="flash flash-danger">Error: {e}</div>'


def _get_all_users():
    """Get all users from database."""
    try:
        from src.database import get_conn
        conn = get_conn()
        rows = conn.execute(
            "SELECT user_id, username, role, display_name, email, active, assigned_sites FROM users ORDER BY username"
        ).fetchall()
        conn.close()
        users = []
        for r in rows:
            d = dict(r) if hasattr(r, "keys") else {
                "user_id": r[0], "username": r[1], "role": r[2],
                "display_name": r[3], "email": r[4], "active": r[5],
                "assigned_sites": r[6],
            }
            # Parse JSON assigned_sites into display string
            raw = d.get("assigned_sites", "")
            if raw:
                try:
                    sites = json.loads(raw)
                    d["assigned_sites"] = ", ".join(sites) if isinstance(sites, list) else ""
                except (json.JSONDecodeError, TypeError):
                    d["assigned_sites"] = ""
            else:
                d["assigned_sites"] = ""
            users.append(d)
        return users
    except Exception:
        return []


def _get_all_site_names():
    """Get all site names for dropdowns."""
    try:
        from src.database import get_conn
        conn = get_conn()
        rows = conn.execute("SELECT DISTINCT name FROM sites ORDER BY name").fetchall()
        conn.close()
        return [r["name"] if hasattr(r, "keys") else r[0] for r in rows]
    except Exception:
        return []


def _load_smtp_settings():
    """Load SMTP settings from the settings table."""
    try:
        raw = load_setting("hub_smtp", "{}")
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {}
