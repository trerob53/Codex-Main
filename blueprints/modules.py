"""
Cerasus Hub — Modules Blueprint
Module shell and placeholder pages for unconverted module pages.
"""

from flask import Blueprint, render_template, session, abort

from src.web_middleware import login_required, module_access_required
from src.modules import discover_modules
from src.config import COLORS

modules_bp = Blueprint("modules", __name__, url_prefix="/module")

MODULE_COLORS = {
    "operations": "#374151",
    "uniforms": "#7C3AED",
    "attendance": "#C8102E",
    "training": "#059669",
    "da_generator": "#B91C1C",
    "incidents": "#D97706",
    "overtime": "#2563EB",
}

MODULE_BGS = {
    "operations": "#F3F4F6",
    "uniforms": "#F3E8FF",
    "attendance": "#FDE8EB",
    "training": "#D1FAE5",
    "da_generator": "#FDE8EB",
    "incidents": "#FEF3C7",
    "overtime": "#DBEAFE",
}

MODULE_ICONS = {
    "operations": "&#9881;",
    "uniforms": "&#128084;",
    "attendance": "&#128197;",
    "training": "&#127891;",
    "da_generator": "&#128196;",
    "incidents": "&#9888;",
    "overtime": "&#9201;",
}


def _find_module(module_id):
    """Find a module by ID."""
    for mod in discover_modules():
        if mod.module_id == module_id:
            return mod
    return None


def _get_page_list(module):
    """Extract flat list of page names from module sidebar_sections.

    sidebar_sections format: [("SECTION_TITLE", [("PageName", "icon"), ...]), ...]
    """
    sections = []
    page_index = 0
    for section in module.sidebar_sections:
        if isinstance(section, (list, tuple)) and len(section) == 2:
            title, items = section
            section_pages = []
            for item in items:
                if isinstance(item, (list, tuple)):
                    page_name = item[0]
                else:
                    page_name = str(item)
                section_pages.append({"name": page_name, "index": page_index})
                page_index += 1
            sections.append({
                "title": title,
                "pages": section_pages,
                "offset": 0,
            })

    return sections


@modules_bp.route("/<module_id>")
@login_required
def module_index(module_id):
    module = _find_module(module_id)
    if not module:
        abort(404)

    # Check module access
    from src import auth as auth_module
    username = session.get("username", "")
    role = session.get("role", "viewer")
    allowed = auth_module.get_user_modules(username)
    if role != "admin" and allowed and module_id not in allowed:
        abort(403)

    # Update session tracking
    from src import session_manager
    sid = session.get("session_id")
    if sid:
        try:
            session_manager.heartbeat_session(sid, module_id)
        except Exception:
            pass

    sections = _get_page_list(module)
    color = MODULE_COLORS.get(module_id, COLORS["accent"])

    return render_template(
        "module/shell.html",
        module=module,
        module_color=color,
        module_bg=MODULE_BGS.get(module_id, "#F3F4F6"),
        module_icon=MODULE_ICONS.get(module_id, "&#9881;"),
        active_module=module_id,
        active_page=None,
    )


@modules_bp.route("/<module_id>/page/<int:page_index>")
@login_required
def module_page(module_id, page_index):
    module = _find_module(module_id)
    if not module:
        abort(404)

    # Get page name from sidebar_sections
    all_pages = []
    for section in module.sidebar_sections:
        if isinstance(section, (list, tuple)) and len(section) == 2:
            _, items = section
            for item in items:
                page_name = item[0] if isinstance(item, (list, tuple)) else str(item)
                all_pages.append(page_name)

    if page_index < 0 or page_index >= len(all_pages):
        abort(404)

    page_name = all_pages[page_index]
    color = MODULE_COLORS.get(module_id, COLORS["accent"])

    return render_template(
        "module/placeholder.html",
        module=module,
        page_name=page_name,
        module_color=color,
        module_bg=MODULE_BGS.get(module_id, "#F3F4F6"),
        active_module=module_id,
        active_page=f"page_{page_index}",
    )
