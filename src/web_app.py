"""
Cerasus Hub — Flask Application Factory
Creates and configures the Flask app with all blueprints.
"""

import os
import sys
import time
import secrets

from flask import Flask, session, redirect, url_for, request, render_template, flash

from src.config import (
    APP_NAME, APP_VERSION, COLORS, DARK_COLORS,
    load_setting, save_setting, load_all_settings,
)


def create_app():
    """Create and configure the Flask application."""

    # Resolve paths for templates and static files
    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS
        template_dir = os.path.join(base_dir, "src", "templates")
        static_dir = os.path.join(base_dir, "src", "static")
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(base_dir, "templates")
        static_dir = os.path.join(base_dir, "static")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir,
    )

    # Secret key: load from DB or generate
    load_all_settings()
    secret = load_setting("flask_secret_key", "")
    if not secret:
        secret = secrets.token_hex(32)
        save_setting("flask_secret_key", secret)
    app.secret_key = secret

    # Session config
    app.config["SESSION_COOKIE_NAME"] = "cerasus_session"
    app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 24 hours
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # Register blueprints
    from src.web_auth import auth_bp
    from src.blueprints.hub import hub_bp
    from src.blueprints.admin import admin_bp
    from src.blueprints.api import api_bp
    from src.blueprints.modules import modules_bp
    from src.blueprints.attendance import att_bp
    from src.blueprints.operations import ops_bp
    from src.blueprints.uniforms import uni_bp
    from src.blueprints.training import trn_bp
    from src.blueprints.da_generator import da_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(hub_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(modules_bp)
    app.register_blueprint(att_bp)
    app.register_blueprint(ops_bp)
    app.register_blueprint(uni_bp)
    app.register_blueprint(trn_bp)
    app.register_blueprint(da_bp)

    # After-request: prevent browser caching of authenticated pages (BUG-003/004)
    @app.after_request
    def add_no_cache_headers(response):
        try:
            if session.get("user_id") and not request.path.startswith("/static/"):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
        except Exception:
            pass
        return response

    # Before-request: redirect unauthenticated users to login + idle timeout
    IDLE_TIMEOUT = 1800  # 30 minutes

    @app.before_request
    def require_login():
        # Skip for static files and auth pages only
        allowed_endpoints = {"auth.login", "auth.forgot_password", "auth.logout", "static"}
        if request.endpoint in allowed_endpoints:
            return
        if request.path.startswith("/static/"):
            return
        if not session.get("user_id"):
            if request.endpoint and request.endpoint != "auth.login":
                return redirect(url_for("auth.login"))
            return

        # Idle session timeout
        last_active = session.get("last_active", 0)
        now = time.time()
        if last_active and (now - last_active) > IDLE_TIMEOUT:
            session.clear()
            flash("Session expired due to inactivity. Please sign in again.", "warning")
            return redirect(url_for("auth.login"))
        session["last_active"] = now

    # Error handlers for graceful failure (#31)
    @app.errorhandler(404)
    def not_found(e):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return {"error": "Not found"}, 404
        return render_template("error.html", code=404, message="Page not found",
                               description="The page you're looking for doesn't exist or has been moved."), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500, message="Server Error",
                               description="Something went wrong. Please try again or restart the application."), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        app.logger.error(f"Unhandled exception: {e}")
        return render_template("error.html", code=500, message="Unexpected Error",
                               description="An unexpected error occurred. Please try again."), 500

    # Custom Jinja filters
    @app.template_filter("format_chapter")
    def format_chapter_filter(text):
        """Convert plain-text chapter content into styled HTML.

        Recognises:
        - ALL-CAPS lines → <h2>
        - Numbered sub-headers like '1.2 — TITLE' → <h3> with callout style
        - Blank-line separated paragraphs → <p>
        - Lines matching 'Label: description' within a run → <ul><li>
        """
        import re
        from markupsafe import Markup

        if not text:
            return Markup("")

        lines = text.split("\n")
        html_parts: list[str] = []
        i = 0
        total = len(lines)

        # Skip the first line if it duplicates the chapter title (already in <h1>)
        if total and re.match(r"^Chapter\s+\d+", lines[0], re.IGNORECASE):
            i = 1

        def _is_section_header(ln: str) -> bool:
            """ALL-CAPS line with 3+ alpha chars, no lowercase."""
            stripped = ln.strip()
            alpha = re.sub(r"[^A-Za-z]", "", stripped)
            return (len(alpha) >= 3
                    and alpha == alpha.upper()
                    and stripped == stripped.upper())

        def _is_numbered_header(ln: str) -> bool:
            """Lines like '1.2 — OUR MISSION' or '1.4 — CULTURE'."""
            return bool(re.match(r"^\d+\.\d+\s*[—–-]\s+", ln.strip()))

        def _is_bullet_line(ln: str) -> bool:
            """Lines like 'Label: description text' (bold label pattern)."""
            return bool(re.match(r"^[A-Z][A-Za-z ,&/()]+(\([^)]*\))?:\s", ln.strip()))

        def _escape(s: str) -> str:
            return (s.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;"))

        def _format_inline(s: str) -> str:
            """Bold text before a colon in bullet-style lines, preserve nbsp."""
            s = _escape(s)
            s = s.replace("\xa0", "&nbsp;")
            # Bold 'Label:' at start of line
            s = re.sub(r"^([A-Z][A-Za-z ,&amp;/()]+(?:\([^)]*\))?:)",
                        r"<strong>\1</strong>", s)
            return s

        while i < total:
            line = lines[i].strip()

            # Skip empty lines
            if not line:
                i += 1
                continue

            # Skip nav leftovers at end (Previous/Next/Completed)
            if line in ("Previous", "Next", "Completed", "Next →", "← Previous"):
                i += 1
                continue

            # Numbered sub-header → <h3> styled as callout
            if _is_numbered_header(line):
                html_parts.append(
                    f'<h3>{_escape(line)}</h3>')
                i += 1
                continue

            # ALL-CAPS section header → <h2>
            if _is_section_header(line):
                html_parts.append(f'<h2>{_escape(line)}</h2>')
                i += 1
                continue

            # Check if this starts a run of bullet-style lines
            if _is_bullet_line(line):
                html_parts.append("<ul>")
                while i < total and lines[i].strip() and _is_bullet_line(lines[i].strip()):
                    html_parts.append(
                        f"<li>{_format_inline(lines[i].strip())}</li>")
                    i += 1
                html_parts.append("</ul>")
                continue

            # Regular paragraph — collect consecutive non-empty lines
            para_lines: list[str] = []
            while i < total and lines[i].strip():
                ln = lines[i].strip()
                if (_is_section_header(ln) or _is_numbered_header(ln)
                        or _is_bullet_line(ln)
                        or ln in ("Previous", "Next", "Completed",
                                  "Next →", "← Previous")):
                    break
                para_lines.append(_format_inline(ln))
                i += 1
            if para_lines:
                html_parts.append(f'<p>{" ".join(para_lines)}</p>')

        return Markup("\n".join(html_parts))

    @app.template_filter("from_json")
    def from_json_filter(value):
        """Parse a JSON string into a Python object."""
        import json as _json
        if not value:
            return []
        try:
            return _json.loads(value)
        except (ValueError, TypeError):
            return []

    @app.template_filter("officer_link")
    def officer_link_filter(name, officer_id=""):
        """Wrap an officer name in a clickable link to their 360 page."""
        from markupsafe import Markup
        if not name or name == "—":
            return name or "—"
        if officer_id:
            url = f"/people/{officer_id}"
        else:
            url = f"/people/by-name/{name}"
        return Markup(
            f'<a href="{url}" style="color:var(--blue);text-decoration:none;font-weight:600;" '
            f'title="View Officer 360">{name}</a>'
        )

    @app.template_filter("site_name")
    def site_name_filter(value):
        """Extract site name from either a dict or string."""
        if isinstance(value, dict):
            return value.get("name", str(value))
        return str(value) if value else "—"

    @app.template_filter("friendly_time")
    def friendly_time_filter(value):
        """Convert ISO timestamp to human-readable format."""
        if not value:
            return "—"
        try:
            from datetime import datetime
            ts = str(value)[:19]  # Strip microseconds and timezone
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%b %d, %Y %I:%M %p")
        except Exception:
            return str(value)[:19] if value else "—"

    # Context processor: inject common template variables
    @app.context_processor
    def inject_globals():
        from src.modules import discover_modules

        user = None
        if session.get("user_id"):
            user = {
                "user_id": session.get("user_id"),
                "username": session.get("username"),
                "role": session.get("role"),
                "display_name": session.get("display_name"),
            }

        dark_mode = session.get("dark_mode", False)
        user_sites = session.get("assigned_sites", [])

        return {
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "current_user": user,
            "dark_mode": dark_mode,
            "modules_list": discover_modules() if user else [],
            "colors": COLORS,
            "active_page": None,
            "active_module": None,
            "user_sites": user_sites,
        }

    return app
