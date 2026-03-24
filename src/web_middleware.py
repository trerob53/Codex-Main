"""
Cerasus Hub — Web Middleware
Authentication and authorization decorators for Flask routes.
"""

from functools import wraps
from flask import session, redirect, url_for, flash, abort

from src import session_manager


def login_required(f):
    """Require a logged-in user. Redirects to /login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        # Heartbeat the session to keep it alive
        sid = session.get("session_id")
        if sid:
            try:
                session_manager.heartbeat_session(sid)
            except Exception:
                pass
        return f(*args, **kwargs)
    return decorated


def role_required(min_role):
    """Require a minimum role level. admin > standard > viewer."""
    ROLE_RANK = {"admin": 3, "director": 2, "standard": 2, "viewer": 1}

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("auth.login"))
            user_role = session.get("role", "viewer")
            if ROLE_RANK.get(user_role, 0) < ROLE_RANK.get(min_role, 0):
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("hub.picker"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_site_filter(all_sites):
    """Apply site restriction for users with assigned_sites.

    Returns (filtered_sites, forced_site_filter):
    - filtered_sites: list of sites the user can see
    - forced_site_filter: the site to force-filter by (first assigned site), or '' if unrestricted
    """
    user_sites = session.get("assigned_sites", [])
    if not user_sites:
        return all_sites, ""
    filtered = [s for s in all_sites if (s if isinstance(s, str) else s.get("name", "")) in user_sites]
    return filtered, user_sites[0] if len(user_sites) == 1 else ""


def apply_site_restriction(site_filter, all_sites):
    """Return (effective_site_filter, visible_sites) respecting assigned_sites.

    If user has assigned sites, restricts the site dropdown and forces filter.
    """
    user_sites = session.get("assigned_sites", [])
    if not user_sites:
        return site_filter, all_sites
    visible = [s for s in all_sites if s in user_sites]
    # If user picked a site outside their scope, override
    if site_filter and site_filter not in user_sites:
        site_filter = user_sites[0] if len(user_sites) == 1 else ""
    # If no filter set and only one site, auto-select it
    if not site_filter and len(user_sites) == 1:
        site_filter = user_sites[0]
    return site_filter, visible


def module_access_required(module_id):
    """Check that the user has access to a specific module."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("auth.login"))
            from src import auth
            username = session.get("username", "")
            allowed = auth.get_user_modules(username)
            # Empty list = all modules allowed
            if allowed and module_id not in allowed:
                flash(f"You do not have access to this module.", "danger")
                return redirect(url_for("hub.picker"))
            return f(*args, **kwargs)
        return decorated
    return decorator
