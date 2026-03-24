"""
Cerasus Hub — Web Authentication Blueprint
Login, logout, and password change routes using existing auth.py.
"""

import time
from collections import defaultdict

from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from src import auth, audit, session_manager
from src.web_middleware import login_required

auth_bp = Blueprint("auth", __name__)

# ── Rate limiting ────────────────────────────────────────────────────
# Track failed login attempts per IP: {ip: [timestamp, ...]}
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_LOCKOUT_THRESHOLD = 5       # failures before lockout
_LOCKOUT_WINDOW = 300        # 5-minute window
_LOCKOUT_DURATION = 300      # 5-minute lockout


def _is_locked_out(ip: str) -> tuple[bool, int]:
    """Check if an IP is locked out. Returns (locked, seconds_remaining)."""
    now = time.time()
    # Prune old attempts
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if now - t < _LOCKOUT_WINDOW]
    if len(_failed_attempts[ip]) >= _LOCKOUT_THRESHOLD:
        oldest = _failed_attempts[ip][0]
        remaining = int(_LOCKOUT_DURATION - (now - oldest))
        if remaining > 0:
            return True, remaining
        # Lockout expired, clear
        _failed_attempts[ip].clear()
    return False, 0


def _record_failure(ip: str):
    _failed_attempts[ip].append(time.time())


def _clear_failures(ip: str):
    _failed_attempts.pop(ip, None)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("hub.picker"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        ip = request.remote_addr or "unknown"

        # Check rate limiting
        locked, remaining = _is_locked_out(ip)
        if locked:
            minutes = remaining // 60 + 1
            error = f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            from src.config import APP_VERSION
            return render_template("login.html", error=error, app_version=APP_VERSION)

        user = auth.authenticate(username, password)
        if user:
            _clear_failures(ip)

            # Store user info in session
            session["user_id"] = user.get("user_id") or user.get("username")
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["display_name"] = user.get("display_name", username)
            session["last_active"] = time.time()

            # Store assigned sites for site-scoped roles (director)
            session["assigned_sites"] = auth.get_user_sites(user["username"])

            # Register a session for online tracking
            try:
                sid = session_manager.register_session(user["username"], user["role"])
                session["session_id"] = sid
            except Exception:
                pass

            # Audit log
            audit.log_event("hub", "login", username, "Web login")

            # Check if must change password
            if auth.must_change_password(username):
                session["must_change_password"] = True
                return redirect(url_for("auth.change_password"))

            # Warn if password expires soon
            days_left = auth.password_expires_soon(username)
            if days_left > 0:
                flash(f"Your password expires in {days_left} day{'s' if days_left != 1 else ''}. Please change it soon.", "warning")

            # Redirect to last module if available
            last_module = session.get("last_module")
            if last_module:
                return redirect(f"/module/{last_module}/")

            return redirect(url_for("hub.picker"))
        else:
            _record_failure(ip)
            attempts_left = _LOCKOUT_THRESHOLD - len(_failed_attempts.get(ip, []))
            if attempts_left <= 2 and attempts_left > 0:
                error = f"Invalid username or password. {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining."
            else:
                error = "Invalid username or password."

    from src.config import APP_VERSION
    return render_template("login.html", error=error, app_version=APP_VERSION)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    username = session.get("username", "")
    sid = session.get("session_id")

    if sid:
        try:
            session_manager.remove_session(sid)
        except Exception:
            pass

    if username:
        audit.log_event("hub", "logout", username, "Web logout")

    session.clear()
    resp = redirect(url_for("auth.login"))
    resp.set_cookie("cerasus_session", "", expires=0, max_age=0, path="/")
    return resp


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    must_change = session.get("must_change_password", False)
    error = None

    if request.method == "POST":
        username = session["username"]
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not must_change:
            current_pw = request.form.get("current_password", "")
            if not auth.verify_password(username, current_pw):
                error = "Current password is incorrect."
                return render_template("change_password.html", error=error, must_change=must_change)

        if len(new_pw) < 6:
            error = "Password must be at least 6 characters."
        elif new_pw != confirm_pw:
            error = "Passwords do not match."
        else:
            auth.update_user(username, new_password=new_pw)
            session.pop("must_change_password", None)
            audit.log_event("hub", "password_change", username, "Password changed via web")
            flash("Password updated successfully.", "success")
            return redirect(url_for("hub.picker"))

    return render_template("change_password.html", error=error, must_change=must_change)


@auth_bp.route("/forgot-password")
def forgot_password():
    """Forgot password — redirect to login with info message."""
    flash("Please contact your administrator to reset your password.", "info")
    return redirect(url_for("auth.login"))
