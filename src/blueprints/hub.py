"""
Cerasus Hub — Hub Blueprint
Module picker, people, analytics, activity, announcements.
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, session, request, redirect, url_for, flash

from src.config import COLORS
from src.web_middleware import login_required
from src.modules import discover_modules
from src import auth

hub_bp = Blueprint("hub", __name__)

MODULE_COLORS = {
    "operations": "#374151",
    "uniforms": "#7C3AED",
    "attendance": "#C8102E",
    "training": "#059669",
    "da_generator": "#B91C1C",
    "incidents": "#D97706",
    "overtime": "#2563EB",
}

MODULE_ICONS = {
    "operations": "&#128202;",
    "uniforms": "&#128085;",
    "attendance": "&#128197;",
    "training": "&#127891;",
    "da_generator": "&#128221;",
    "incidents": "&#9888;",
    "overtime": "&#9201;",
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


@hub_bp.route("/")
@login_required
def picker():
    username = session.get("username", "")
    role = session.get("role", "viewer")
    modules = discover_modules()

    # Filter by user's allowed modules
    allowed = auth.get_user_modules(username)
    if role != "admin" and allowed:
        modules = [m for m in modules if m.module_id in allowed]

    # Build module data for template with icons and colors
    visible_modules = []
    for mod in modules:
        mid = mod.module_id
        visible_modules.append({
            "module_id": mid,
            "name": mod.name,
            "version": mod.version,
            "description": mod.description,
            "color": MODULE_COLORS.get(mid, COLORS["accent"]),
            "bg": MODULE_BGS.get(mid, "#F3F4F6"),
            "icon": MODULE_ICONS.get(mid, "&#9881;"),
            "badge_count": 0,
        })

    # KPIs with icons
    kpis = _get_kpis()

    # Recent activity for the dashboard table
    recent_events = _get_recent_activity(limit=5)

    # Current date
    current_date = datetime.now().strftime("%A, %B %d, %Y")

    return render_template(
        "hub/picker.html",
        visible_modules=visible_modules,
        kpis=kpis,
        recent_events=recent_events,
        current_date=current_date,
        active_page="picker",
    )


@hub_bp.route("/people")
@login_required
def people():
    from src.shared_data import get_all_officers, get_all_sites
    officers = get_all_officers()
    sites = get_all_sites()
    return render_template("hub/people.html", officers=officers, sites=sites, active_page="people")


@hub_bp.route("/people/by-name/<path:name>")
@login_required
def officer_360_by_name(name):
    """Redirect to Officer 360 by name lookup."""
    from src.database import get_conn
    conn = get_conn()
    row = conn.execute(
        "SELECT officer_id FROM officers WHERE name = ? LIMIT 1", (name,)
    ).fetchone()
    conn.close()
    if row:
        return redirect(url_for("hub.officer_360", officer_id=row["officer_id"]))
    flash(f"Officer '{name}' not found.", "warning")
    return redirect(url_for("hub.people"))


@hub_bp.route("/people/<officer_id>")
@login_required
def officer_360(officer_id):
    """Officer 360 — comprehensive officer profile page."""
    from src.shared_data import get_officer, get_officer_timeline
    from src.database import get_conn

    officer = get_officer(officer_id, include_deleted=True)
    if not officer:
        flash("Officer not found.", "danger")
        return redirect(url_for("hub.people"))

    conn = get_conn()

    # ── Timeline ──
    try:
        timeline = get_officer_timeline(officer_id)
    except Exception:
        timeline = []

    # ── Attendance: infractions via ats_id_mapping ──
    infractions = []
    try:
        infractions = [dict(r) for r in conn.execute(
            """SELECT i.infraction_date, i.infraction_type, i.points_assigned, i.site, i.description
               FROM ats_infractions i
               JOIN ats_id_mapping m ON i.employee_id = m.ats_id
               WHERE m.officer_id = ?
               ORDER BY i.infraction_date DESC LIMIT 20""",
            (officer_id,),
        ).fetchall()]
    except Exception:
        # Fallback: try direct employee_id match
        try:
            infractions = [dict(r) for r in conn.execute(
                """SELECT infraction_date, infraction_type, points_assigned, site, description
                   FROM ats_infractions WHERE employee_id = ?
                   ORDER BY infraction_date DESC LIMIT 20""",
                (officer_id,),
            ).fetchall()]
        except Exception:
            pass

    # ── Days since last infraction ──
    days_since = None
    if infractions:
        try:
            last_date = datetime.strptime(infractions[0]["infraction_date"], "%Y-%m-%d").date()
            days_since = (date.today() - last_date).days
        except Exception:
            pass

    # ── Schedule: assignments (next 14 days) ──
    assignments = []
    try:
        today_str = date.today().isoformat()
        end_str = (date.today() + timedelta(days=14)).isoformat()
        assignments = [dict(r) for r in conn.execute(
            """SELECT date, site_name, start_time, end_time, hours, assignment_type, status
               FROM ops_assignments WHERE officer_name = ? AND date >= ? AND date <= ?
               ORDER BY date ASC""",
            (officer.get("name", ""), today_str, end_str),
        ).fetchall()]
    except Exception:
        pass

    # ── PTO (next 30 days) ──
    pto_entries = []
    try:
        today_str = date.today().isoformat()
        end_str = (date.today() + timedelta(days=30)).isoformat()
        pto_entries = [dict(r) for r in conn.execute(
            """SELECT start_date, end_date, pto_type, status, notes
               FROM ops_pto_entries WHERE officer_name = ? AND end_date >= ? AND start_date <= ?
               ORDER BY start_date ASC""",
            (officer.get("name", ""), today_str, end_str),
        ).fetchall()]
    except Exception:
        pass

    # ── Uniforms: outstanding items ──
    uniform_items = []
    try:
        uniform_items = [dict(r) for r in conn.execute(
            """SELECT item_name, size, quantity, date_issued, condition_issued
               FROM uni_issuances WHERE officer_id = ? AND status = 'Outstanding'
               ORDER BY date_issued DESC""",
            (officer_id,),
        ).fetchall()]
    except Exception:
        pass

    # ── Uniform compliance checklist ──
    uniform_compliance = []
    uniform_pct = 100
    try:
        job_title = officer.get("job_title", "")
        reqs = conn.execute(
            "SELECT item_id, item_name, qty_required FROM uni_requirements WHERE job_title = ?",
            (job_title,),
        ).fetchall()
        if reqs:
            met = 0
            for req in reqs:
                issued = conn.execute(
                    "SELECT COALESCE(SUM(quantity), 0) AS qty FROM uni_issuances WHERE officer_id = ? AND item_id = ? AND status = 'Outstanding'",
                    (officer_id, req["item_id"]),
                ).fetchone()
                qty = issued["qty"] if issued else 0
                uniform_compliance.append({
                    "item_name": req["item_name"],
                    "required": req["qty_required"],
                    "issued": qty,
                })
                if qty >= req["qty_required"]:
                    met += 1
            uniform_pct = int((met / len(reqs)) * 100)
    except Exception:
        pass

    # ── Training: course progress ──
    courses = []
    training_pct = 0
    try:
        published = conn.execute("SELECT course_id, title FROM trn_courses WHERE status='Published'").fetchall()
        total_certs = 0
        active_certs = 0
        for course in published:
            total_chapters = conn.execute(
                "SELECT COUNT(*) AS cnt FROM trn_chapters WHERE course_id = ?", (course["course_id"],)
            ).fetchone()["cnt"]
            completed = conn.execute(
                "SELECT COUNT(*) AS cnt FROM trn_progress WHERE officer_id = ? AND course_id = ? AND completed = 1 AND chapter_id != ''",
                (officer_id, course["course_id"]),
            ).fetchone()["cnt"]
            pct = int((completed / total_chapters) * 100) if total_chapters > 0 else 0
            courses.append({"title": course["title"], "completed": completed, "total": total_chapters, "pct": pct})

        # Training pct based on certificates
        total_certs = len(published)
        if total_certs > 0:
            active_certs = conn.execute(
                "SELECT COUNT(DISTINCT course_id) AS cnt FROM trn_certificates WHERE officer_id = ? AND status = 'Active'",
                (officer_id,),
            ).fetchone()["cnt"]
            training_pct = int((active_certs / total_certs) * 100)
    except Exception:
        pass

    # ── Certificates ──
    certificates = []
    try:
        certificates = [dict(r) for r in conn.execute(
            """SELECT cr.issued_date, cr.expiry_date, cr.status, c.title AS course_title
               FROM trn_certificates cr LEFT JOIN trn_courses c ON cr.course_id = c.course_id
               WHERE cr.officer_id = ? ORDER BY cr.issued_date DESC""",
            (officer_id,),
        ).fetchall()]
    except Exception:
        pass

    # ── Test attempts ──
    test_attempts = []
    try:
        test_attempts = [dict(r) for r in conn.execute(
            """SELECT ta.score, ta.passed, ta.completed_at, t.title AS test_title, c.title AS course_title
               FROM trn_test_attempts ta
               LEFT JOIN trn_tests t ON ta.test_id = t.test_id
               LEFT JOIN trn_courses c ON ta.course_id = c.course_id
               WHERE ta.officer_id = ? ORDER BY ta.completed_at DESC""",
            (officer_id,),
        ).fetchall()]
    except Exception:
        pass

    # ── DA records ──
    da_records = []
    try:
        da_records = [dict(r) for r in conn.execute(
            """SELECT da_id, violation_type, discipline_level, status, created_at
               FROM da_records WHERE employee_officer_id = ? OR employee_name = ?
               ORDER BY created_at DESC""",
            (officer_id, officer.get("name", "")),
        ).fetchall()]
    except Exception:
        pass

    conn.close()

    # ── Risk Score ──
    pts = float(officer.get("active_points") or 0)
    active_das = len([d for d in da_records if d.get("status") in ("draft", "pending_review")])
    risk_score = int(min(100,
        min(40, pts * 4) +
        (100 - training_pct) * 0.2 +
        (100 - uniform_pct) * 0.2 +
        min(20, active_das * 10)
    ))

    return render_template(
        "hub/officer_360.html",
        officer=officer,
        timeline=timeline,
        infractions=infractions,
        days_since=days_since,
        assignments=assignments,
        pto_entries=pto_entries,
        uniform_items=uniform_items,
        uniform_compliance=uniform_compliance,
        uniform_pct=uniform_pct,
        courses=courses,
        training_pct=training_pct,
        certificates=certificates,
        test_attempts=test_attempts,
        da_records=da_records,
        risk_score=risk_score,
        active_page="people",
    )


@hub_bp.route("/people/add-officer", methods=["POST"])
@login_required
def add_officer():
    """Create a new officer."""
    from src.shared_data import create_officer
    from src import audit

    fields = {
        "name": request.form.get("name", "").strip(),
        "first_name": request.form.get("first_name", "").strip(),
        "last_name": request.form.get("last_name", "").strip(),
        "employee_id": request.form.get("employee_id", "").strip(),
        "email": request.form.get("email", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "site": request.form.get("site", "").strip(),
        "job_title": request.form.get("job_title", "Security Officer").strip(),
        "hire_date": request.form.get("hire_date", ""),
        "status": "Active",
    }
    if not fields["name"]:
        # Build name from first/last if not provided
        fields["name"] = f"{fields['first_name']} {fields['last_name']}".strip()
    if not fields["name"]:
        flash("Officer name is required.", "danger")
        return redirect(url_for("hub.people"))

    username = session.get("username", "system")
    oid = create_officer(fields, created_by=username)
    audit.log_event("hub", "create_officer", username, f"Created officer: {fields['name']} ({oid})")
    flash(f"Officer '{fields['name']}' created.", "success")
    return redirect(url_for("hub.people"))


@hub_bp.route("/people/delete-officer", methods=["POST"])
@login_required
def delete_officer_route():
    """Soft-delete an officer (set status to Deleted)."""
    from src.shared_data import delete_officer, get_officer
    from src import audit

    officer_id = request.form.get("officer_id", "")
    if not officer_id:
        flash("No officer selected.", "danger")
        return redirect(url_for("hub.people"))

    off = get_officer(officer_id, include_deleted=True)
    name = off.get("name", officer_id) if off else officer_id

    username = session.get("username", "system")
    ok = delete_officer(officer_id, updated_by=username)
    if ok:
        audit.log_event("hub", "delete_officer", username, f"Deleted officer: {name} ({officer_id})")
        flash(f"Officer '{name}' deleted.", "success")
    else:
        flash("Could not delete officer.", "danger")
    return redirect(url_for("hub.people"))


@hub_bp.route("/people/add-site", methods=["POST"])
@login_required
def add_site():
    """Create a new site."""
    from src.shared_data import create_site
    from src import audit

    fields = {
        "name": request.form.get("name", "").strip(),
        "city": request.form.get("city", "").strip(),
        "state": request.form.get("state", "").strip(),
        "market": request.form.get("market", "").strip(),
        "address": request.form.get("address", "").strip(),
        "status": "Active",
    }
    if not fields["name"]:
        flash("Site name is required.", "danger")
        return redirect(url_for("hub.people"))

    username = session.get("username", "system")
    sid = create_site(fields, created_by=username)
    audit.log_event("hub", "create_site", username, f"Created site: {fields['name']} ({sid})")
    flash(f"Site '{fields['name']}' created.", "success")
    return redirect(url_for("hub.people"))


@hub_bp.route("/people/mass-reassign", methods=["POST"])
@login_required
def mass_reassign():
    """Mass reassign selected officers to a new site."""
    from src.shared_data import update_officer
    from src import audit

    new_site = request.form.get("new_site", "").strip()
    officer_ids = request.form.getlist("officer_ids")

    if not officer_ids:
        flash("No officers selected.", "danger")
        return redirect(url_for("hub.people"))

    count = 0
    username = session.get("username", "system")
    for oid in officer_ids:
        update_officer(oid, {"site": new_site}, updated_by=username)
        count += 1

    site_label = new_site if new_site else "Unassigned"
    audit.log_event("hub", "mass_reassign", username,
                    f"Reassigned {count} officer(s) to {site_label}")
    flash(f"Reassigned {count} officer(s) to {site_label}.", "success")
    return redirect(url_for("hub.people"))


@hub_bp.route("/people/delete-site", methods=["POST"])
@login_required
def delete_site():
    """Delete a site. Optionally reassign its officers first."""
    from src.shared_data import delete_site as sd_delete_site, get_all_officers
    from src import audit

    site_id = request.form.get("site_id", "")
    reassign_to = request.form.get("reassign_to", "").strip()

    if not site_id:
        flash("No site selected.", "danger")
        return redirect(url_for("hub.people"))

    # Reassign officers from deleted site if requested
    if reassign_to != "__skip__":
        from src.shared_data import update_officer
        from src.database import get_conn
        conn = get_conn()
        site_row = conn.execute("SELECT name FROM sites WHERE site_id = ?", (site_id,)).fetchone()
        site_name = site_row["name"] if site_row else ""
        officers = conn.execute(
            "SELECT officer_id FROM officers WHERE site = ? AND status != 'Deleted'",
            (site_name,),
        ).fetchall()
        conn.close()

        username = session.get("username", "system")
        for off in officers:
            update_officer(off["officer_id"], {"site": reassign_to}, updated_by=username)

        if officers:
            target_label = reassign_to if reassign_to else "Unassigned"
            flash(f"Reassigned {len(officers)} officer(s) from {site_name} to {target_label}.", "info")

    sd_delete_site(site_id)
    audit.log_event("hub", "delete_site", session.get("username", "system"),
                    f"Deleted site {site_id}")
    flash("Site deleted.", "success")
    return redirect(url_for("hub.people"))


@hub_bp.route("/analytics")
@login_required
def analytics():
    return render_template("hub/analytics.html", active_page="analytics")


@hub_bp.route("/activity")
@login_required
def activity():
    events = _get_recent_activity()
    return render_template("hub/activity.html", events=events, active_page="activity")


@hub_bp.route("/announcements")
@login_required
def announcements():
    return render_template("hub/announcements.html", active_page="announcements")


@hub_bp.route("/search")
@login_required
def search():
    from flask import request
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return ""
    try:
        from src.search_engine import search_all
        results = search_all(q, limit=15)
    except Exception:
        results = []

    if not results:
        return '<div style="padding:12px; color:var(--text-light); font-size:13px;">No results found</div>'

    html_parts = []
    for item in results:
        title = item.get("title", "")
        subtitle = item.get("subtitle", "")
        color = item.get("color", "#374151")
        display = title
        if subtitle:
            display += f" &mdash; {subtitle}"
        html_parts.append(
            f'<div style="padding:8px 12px; border-radius:6px; cursor:pointer; font-size:13px; '
            f'transition:background 0.1s;" '
            f'onmouseover="this.style.background=\'var(--hover)\'" '
            f'onmouseout="this.style.background=\'transparent\'">'
            f'<span style="display:inline-block; width:8px; height:8px; border-radius:50%; '
            f'background:{color}; margin-right:8px;"></span>{display}</div>'
        )
    return "\n".join(html_parts)


def _get_kpis():
    """Load KPI data with icons for the hub picker."""
    kpis = [
        {"label": "Active Officers", "value": "0", "color": "#059669", "bg": "#D1FAE5",
         "icon": "&#128101;"},
        {"label": "Pending Reviews", "value": "0", "color": "#D97706", "bg": "#FEF3C7",
         "icon": "&#128203;"},
        {"label": "Low Stock", "value": "0", "color": "#C8102E", "bg": "#FDE8EB",
         "icon": "&#9888;"},
        {"label": "Open Requests", "value": "0", "color": "#3B82F6", "bg": "#DBEAFE",
         "icon": "&#128230;"},
    ]
    try:
        from src.database import get_conn
        conn = get_conn()
        count = conn.execute("SELECT COUNT(*) FROM officers WHERE status='Active' OR status IS NULL").fetchone()[0]
        kpis[0]["value"] = str(count)

        try:
            count = conn.execute("SELECT COUNT(*) FROM ats_employment_reviews WHERE status='Pending'").fetchone()[0]
            kpis[1]["value"] = str(count)
        except Exception:
            pass

        try:
            count = conn.execute("SELECT COUNT(*) FROM uni_catalog WHERE quantity <= reorder_point").fetchone()[0]
            kpis[2]["value"] = str(count)
        except Exception:
            pass

        conn.close()
    except Exception:
        pass
    return kpis


def _get_recent_activity(limit=50):
    """Load recent audit events."""
    try:
        from src.database import get_conn
        conn = get_conn()
        rows = conn.execute(
            "SELECT timestamp, username, module_name, "
            "COALESCE(NULLIF(action, ''), event_type, '') as action, details "
            "FROM audit_log ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) if hasattr(r, "keys") else {
            "timestamp": r[0], "username": r[1], "module_name": r[2],
            "action": r[3], "details": r[4]
        } for r in rows]
    except Exception:
        return []
