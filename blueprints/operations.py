"""
Cerasus Hub -- Operations Module Blueprint
Full web pages for the Operations module: dashboard, dispatch, scheduling, management, admin.
"""

from datetime import date, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, jsonify,
)

from src.web_middleware import login_required, module_access_required, apply_site_restriction
from src.modules.operations import data_manager as dm
from src import audit

ops_bp = Blueprint("operations", __name__, url_prefix="/module/operations")

# ── Sidebar definition (shared with templates) ───────────────────────
SIDEBAR_SECTIONS = [
    ("OVERVIEW", [
        ("Dashboard", "dashboard", "&#9670;"),
    ]),
    ("DISPATCH", [
        ("Flex Board", "flex_board", "&#128101;"),
        ("Open Requests", "open_requests", "&#128203;"),
        ("Coverage Map", "coverage_map", "&#127758;"),
        ("Open Positions", "open_positions", "&#128188;"),
        ("PTO & Coverage", "pto", "&#128197;"),
    ]),
    ("SCHEDULING", [
        ("Anchor Schedules", "anchor_schedules", "&#9875;"),
        ("Weekly View", "weekly_view", "&#128467;"),
    ]),
    ("MANAGEMENT", [
        ("Officers", "officers", "&#128100;"),
        ("Sites", "sites", "&#127970;"),
        ("Handoff Notes", "handoff_notes", "&#128221;"),
    ]),
    ("ADMIN", [
        ("Reports", "reports", "&#128202;"),
        ("Audit Log", "audit_log", "&#128270;"),
        ("Settings", "settings", "&#9881;"),
    ]),
]

MODULE_COLOR = "#374151"
MODULE_BG = "#F3F4F6"


def _ctx(active_page=""):
    """Build common template context."""
    return {
        "sidebar_sections": SIDEBAR_SECTIONS,
        "active_page": active_page,
        "active_module": "operations",
        "module_color": MODULE_COLOR,
        "module_bg": MODULE_BG,
    }


def _user():
    return session.get("username", "system")


def _sites_and_filter(site_param=""):
    """Get site list and effective filter, respecting user's assigned sites."""
    all_sites = dm.get_site_names()
    site_filter = site_param or request.args.get("site", "")
    return apply_site_restriction(site_filter, all_sites)


def _filter_records_by_site(records, site_field="site_name"):
    """Filter a list of record dicts to only the user's assigned sites."""
    user_sites = session.get("assigned_sites", [])
    if not user_sites:
        return records
    return [r for r in records
            if (r.get(site_field, "") or r.get("site", "") or r.get("anchor_site", "")) in user_sites]


# ═════════════════════════════════════════════════════════════════════
#  OVERVIEW
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/")
@ops_bp.route("/dashboard")
@login_required
@module_access_required("operations")
def dashboard():
    summary = dm.get_dashboard_summary()
    req_summary = dm.get_request_summary()
    pos_kpis = dm.get_position_kpis()
    return render_template(
        "operations/dashboard.html",
        summary=summary,
        req_summary=req_summary,
        pos_kpis=pos_kpis,
        **_ctx("dashboard"),
    )


# ═════════════════════════════════════════════════════════════════════
#  DISPATCH — Flex Board
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/flex-board")
@login_required
@module_access_required("operations")
def flex_board():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    if q:
        officers = dm.search_ops_officers(q)
    else:
        officers = dm.get_ops_officers(active_only=(status != "all"))
    if status and status != "all":
        officers = [o for o in officers if o.get("status") == status]
    officers = _filter_records_by_site(officers)
    _, sites = _sites_and_filter()
    return render_template(
        "operations/flex_board.html",
        officers=officers,
        sites=sites,
        q=q,
        status_filter=status,
        **_ctx("flex_board"),
    )


# ═════════════════════════════════════════════════════════════════════
#  DISPATCH — Open Requests
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/open-requests")
@login_required
@module_access_required("operations")
def open_requests():
    site = request.args.get("site", "")
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    site, sites = _sites_and_filter(site)
    requests_list = dm.get_all_requests(
        site_filter=site, status_filter=status, priority_filter=priority,
    )
    req_summary = dm.get_request_summary()
    officer_names = dm.get_ops_officer_names()
    return render_template(
        "operations/open_requests.html",
        requests=requests_list,
        req_summary=req_summary,
        sites=sites,
        officer_names=officer_names,
        site_filter=site,
        status_filter=status,
        priority_filter=priority,
        **_ctx("open_requests"),
    )


@ops_bp.route("/open-requests/create", methods=["POST"])
@login_required
@module_access_required("operations")
def open_requests_create():
    fields = {
        "site_name": request.form.get("site_name", ""),
        "date": request.form.get("date", ""),
        "start_time": request.form.get("start_time", ""),
        "end_time": request.form.get("end_time", ""),
        "reason": request.form.get("reason", "Coverage"),
        "priority": request.form.get("priority", "Normal"),
        "requested_by": request.form.get("requested_by", ""),
        "notes": request.form.get("notes", ""),
    }
    rid = dm.create_request(fields, created_by=_user())
    audit.log_event("operations", "create", _user(), f"Created coverage request {rid}",
                     table_name="ops_open_requests", record_id=rid, action="create")
    flash("Coverage request created.", "success")
    return redirect(url_for("operations.open_requests"))


@ops_bp.route("/open-requests/<request_id>/fill", methods=["POST"])
@login_required
@module_access_required("operations")
def open_requests_fill(request_id):
    officer_name = request.form.get("officer_name", "")
    if not officer_name:
        flash("Select an officer to fill the request.", "danger")
        return redirect(url_for("operations.open_requests"))
    aid = dm.fill_request(request_id, officer_name, updated_by=_user())
    if aid:
        audit.log_event("operations", "update", _user(),
                         f"Filled request {request_id} with {officer_name}, assignment {aid}",
                         table_name="ops_open_requests", record_id=request_id, action="fill")
        flash(f"Request filled — assignment {aid} created for {officer_name}.", "success")
    else:
        flash("Failed to fill request.", "danger")
    return redirect(url_for("operations.open_requests"))


@ops_bp.route("/open-requests/<request_id>/delete", methods=["POST"])
@login_required
@module_access_required("operations")
def open_requests_delete(request_id):
    dm.delete_request(request_id)
    audit.log_event("operations", "delete", _user(), f"Deleted request {request_id}",
                     table_name="ops_open_requests", record_id=request_id, action="delete")
    flash("Request deleted.", "success")
    return redirect(url_for("operations.open_requests"))


# ═════════════════════════════════════════════════════════════════════
#  DISPATCH — Coverage Map
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/coverage-map")
@login_required
@module_access_required("operations")
def coverage_map():
    week_start_str = request.args.get("week_start", "")
    if week_start_str:
        try:
            week_start = date.fromisoformat(week_start_str)
        except ValueError:
            week_start = date.today() - timedelta(days=date.today().weekday() + 1)  # Sunday
    else:
        today = date.today()
        week_start = today - timedelta(days=(today.weekday() + 1) % 7)  # Sunday

    week_end = week_start + timedelta(days=6)
    days = [(week_start + timedelta(days=i)) for i in range(7)]
    assignments = dm.get_assignments_for_week(
        week_start.isoformat(), week_end.isoformat()
    )
    sites = dm.get_active_sites()
    # Build grid: site -> day -> list of assignments
    grid = {}
    for site in sites:
        sn = site.get("name", "")
        grid[sn] = {}
        for d in days:
            ds = d.isoformat()
            grid[sn][ds] = [a for a in assignments if a.get("site_name") == sn and a.get("date") == ds]

    return render_template(
        "operations/coverage_map.html",
        grid=grid,
        sites=sites,
        days=days,
        week_start=week_start,
        week_end=week_end,
        prev_week=(week_start - timedelta(days=7)).isoformat(),
        next_week=(week_start + timedelta(days=7)).isoformat(),
        **_ctx("coverage_map"),
    )


# ═════════════════════════════════════════════════════════════════════
#  DISPATCH — Open Positions
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/open-positions")
@login_required
@module_access_required("operations")
def open_positions():
    site = request.args.get("site", "")
    stage = request.args.get("stage", "")
    include_filled = request.args.get("include_filled", "") == "1"
    site, sites = _sites_and_filter(site)
    positions = dm.get_all_positions(site_filter=site, status_filter=stage,
                                     include_filled=include_filled)
    kpis = dm.get_position_kpis()
    pipeline = dm.POSITION_PIPELINE
    return render_template(
        "operations/open_positions.html",
        positions=positions,
        kpis=kpis,
        sites=sites,
        pipeline=pipeline,
        site_filter=site,
        stage_filter=stage,
        include_filled=include_filled,
        **_ctx("open_positions"),
    )


@ops_bp.route("/open-positions/create", methods=["POST"])
@login_required
@module_access_required("operations")
def open_positions_create():
    data = {
        "site_name": request.form.get("site_name", ""),
        "position_title": request.form.get("position_title", ""),
        "shift": request.form.get("shift", ""),
        "pay_rate": request.form.get("pay_rate", "0.00"),
        "sunday": request.form.get("sunday", "OFF"),
        "monday": request.form.get("monday", "OFF"),
        "tuesday": request.form.get("tuesday", "OFF"),
        "wednesday": request.form.get("wednesday", "OFF"),
        "thursday": request.form.get("thursday", "OFF"),
        "friday": request.form.get("friday", "OFF"),
        "saturday": request.form.get("saturday", "OFF"),
        "total_hours": request.form.get("total_hours", "0"),
        "notes": request.form.get("notes", ""),
        "created_by": _user(),
    }
    pid = dm.create_position(data)
    audit.log_event("operations", "create", _user(), f"Created position {pid}",
                     table_name="ops_positions", record_id=pid, action="create")
    flash("Position created.", "success")
    return redirect(url_for("operations.open_positions"))


@ops_bp.route("/open-positions/<position_id>/advance", methods=["POST"])
@login_required
@module_access_required("operations")
def open_positions_advance(position_id):
    new_stage = request.form.get("new_stage", "")
    if new_stage:
        dm.advance_position_pipeline(position_id, new_stage)
        audit.log_event("operations", "update", _user(),
                         f"Advanced position {position_id} to {new_stage}",
                         table_name="ops_positions", record_id=position_id, action="advance")
        flash(f"Position advanced to {new_stage}.", "success")
    return redirect(url_for("operations.open_positions"))


@ops_bp.route("/open-positions/<position_id>/edit", methods=["POST"])
@login_required
@module_access_required("operations")
def open_positions_edit(position_id):
    data = {
        "site_name": request.form.get("site_name", ""),
        "position_title": request.form.get("position_title", ""),
        "shift": request.form.get("shift", ""),
        "pay_rate": request.form.get("pay_rate", "0.00"),
        "sunday": request.form.get("sunday", "OFF"),
        "monday": request.form.get("monday", "OFF"),
        "tuesday": request.form.get("tuesday", "OFF"),
        "wednesday": request.form.get("wednesday", "OFF"),
        "thursday": request.form.get("thursday", "OFF"),
        "friday": request.form.get("friday", "OFF"),
        "saturday": request.form.get("saturday", "OFF"),
        "total_hours": request.form.get("total_hours", "0"),
        "notes": request.form.get("notes", ""),
        "updated_by": _user(),
    }
    dm.update_position(position_id, data)
    audit.log_event("operations", "update", _user(), f"Edited position {position_id}",
                     table_name="ops_positions", record_id=position_id, action="edit")
    flash("Position updated.", "success")
    return redirect(url_for("operations.open_positions"))


@ops_bp.route("/open-positions/<position_id>/delete", methods=["POST"])
@login_required
@module_access_required("operations")
def open_positions_delete(position_id):
    dm.delete_position(position_id)
    audit.log_event("operations", "delete", _user(), f"Deleted position {position_id}",
                     table_name="ops_positions", record_id=position_id, action="delete")
    flash("Position deleted.", "success")
    return redirect(url_for("operations.open_positions"))


# ═════════════════════════════════════════════════════════════════════
#  DISPATCH — PTO & Coverage
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/pto")
@login_required
@module_access_required("operations")
def pto():
    entries = dm.get_all_pto()
    officer_names = dm.get_ops_officer_names()
    return render_template(
        "operations/pto.html",
        entries=entries,
        officer_names=officer_names,
        **_ctx("pto"),
    )


@ops_bp.route("/pto/create", methods=["POST"])
@login_required
@module_access_required("operations")
def pto_create():
    fields = {
        "officer_name": request.form.get("officer_name", ""),
        "start_date": request.form.get("start_date", ""),
        "end_date": request.form.get("end_date", ""),
        "pto_type": request.form.get("pto_type", "Unavailable"),
        "status": request.form.get("status", "Approved"),
        "notes": request.form.get("notes", ""),
    }
    pid = dm.create_pto(fields, created_by=_user())
    audit.log_event("operations", "create", _user(), f"Created PTO {pid}",
                     table_name="ops_pto_entries", record_id=pid, action="create")
    flash("PTO entry created.", "success")
    return redirect(url_for("operations.pto"))


@ops_bp.route("/pto/<pto_id>/edit", methods=["POST"])
@login_required
@module_access_required("operations")
def pto_edit(pto_id):
    fields = {
        "officer_name": request.form.get("officer_name", ""),
        "start_date": request.form.get("start_date", ""),
        "end_date": request.form.get("end_date", ""),
        "pto_type": request.form.get("pto_type", ""),
        "status": request.form.get("status", ""),
        "notes": request.form.get("notes", ""),
    }
    dm.update_pto(pto_id, fields, updated_by=_user())
    audit.log_event("operations", "update", _user(), f"Updated PTO {pto_id}",
                     table_name="ops_pto_entries", record_id=pto_id, action="update")
    flash("PTO entry updated.", "success")
    return redirect(url_for("operations.pto"))


@ops_bp.route("/pto/<pto_id>/delete", methods=["POST"])
@login_required
@module_access_required("operations")
def pto_delete(pto_id):
    dm.delete_pto(pto_id)
    audit.log_event("operations", "delete", _user(), f"Deleted PTO {pto_id}",
                     table_name="ops_pto_entries", record_id=pto_id, action="delete")
    flash("PTO entry deleted.", "success")
    return redirect(url_for("operations.pto"))


# ═════════════════════════════════════════════════════════════════════
#  SCHEDULING — Anchor Schedules
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/anchor-schedules")
@login_required
@module_access_required("operations")
def anchor_schedules():
    show_all = request.args.get("show_all", "") == "1"
    schedules = dm.get_all_anchor_schedules(active_only=not show_all)
    schedules = _filter_records_by_site(schedules)
    officer_names = dm.get_ops_officer_names()
    _, sites = _sites_and_filter()
    return render_template(
        "operations/anchor_schedules.html",
        schedules=schedules,
        officer_names=officer_names,
        sites=sites,
        show_all=show_all,
        **_ctx("anchor_schedules"),
    )


@ops_bp.route("/anchor-schedules/create", methods=["POST"])
@login_required
@module_access_required("operations")
def anchor_schedules_create():
    fields = {
        "officer_name": request.form.get("officer_name", ""),
        "position_title": request.form.get("position_title", ""),
        "anchor_site": request.form.get("anchor_site", ""),
        "pay_rate": request.form.get("pay_rate", "0.00"),
        "sunday": request.form.get("sunday", "OFF"),
        "monday": request.form.get("monday", "OFF"),
        "tuesday": request.form.get("tuesday", "OFF"),
        "wednesday": request.form.get("wednesday", "OFF"),
        "thursday": request.form.get("thursday", "OFF"),
        "friday": request.form.get("friday", "OFF"),
        "saturday": request.form.get("saturday", "OFF"),
        "notes": request.form.get("notes", ""),
    }
    sid = dm.create_anchor_schedule(fields, created_by=_user())
    audit.log_event("operations", "create", _user(), f"Created anchor schedule {sid}",
                     table_name="ops_anchor_schedules", record_id=sid, action="create")
    flash("Anchor schedule created.", "success")
    return redirect(url_for("operations.anchor_schedules"))


@ops_bp.route("/anchor-schedules/<schedule_id>/edit", methods=["POST"])
@login_required
@module_access_required("operations")
def anchor_schedules_edit(schedule_id):
    fields = {
        "officer_name": request.form.get("officer_name", ""),
        "position_title": request.form.get("position_title", ""),
        "anchor_site": request.form.get("anchor_site", ""),
        "pay_rate": request.form.get("pay_rate", "0.00"),
        "sunday": request.form.get("sunday", "OFF"),
        "monday": request.form.get("monday", "OFF"),
        "tuesday": request.form.get("tuesday", "OFF"),
        "wednesday": request.form.get("wednesday", "OFF"),
        "thursday": request.form.get("thursday", "OFF"),
        "friday": request.form.get("friday", "OFF"),
        "saturday": request.form.get("saturday", "OFF"),
        "active": 1 if request.form.get("active") else 0,
        "notes": request.form.get("notes", ""),
    }
    dm.update_anchor_schedule(schedule_id, fields, updated_by=_user())
    audit.log_event("operations", "update", _user(), f"Updated anchor schedule {schedule_id}",
                     table_name="ops_anchor_schedules", record_id=schedule_id, action="update")
    flash("Anchor schedule updated.", "success")
    return redirect(url_for("operations.anchor_schedules"))


@ops_bp.route("/anchor-schedules/<schedule_id>/delete", methods=["POST"])
@login_required
@module_access_required("operations")
def anchor_schedules_delete(schedule_id):
    dm.delete_anchor_schedule(schedule_id)
    audit.log_event("operations", "delete", _user(), f"Deleted anchor schedule {schedule_id}",
                     table_name="ops_anchor_schedules", record_id=schedule_id, action="delete")
    flash("Anchor schedule deleted.", "success")
    return redirect(url_for("operations.anchor_schedules"))


@ops_bp.route("/anchor-schedules/generate-week", methods=["POST"])
@login_required
@module_access_required("operations")
def anchor_schedules_generate():
    start_date = request.form.get("start_date", "")
    if not start_date:
        today = date.today()
        start_date = (today - timedelta(days=(today.weekday() + 1) % 7)).isoformat()
    ids = dm.generate_week_from_anchors(start_date)
    audit.log_event("operations", "generate", _user(),
                     f"Generated {len(ids)} assignments from anchors for week of {start_date}",
                     table_name="ops_assignments", action="generate")
    flash(f"Generated {len(ids)} assignments for week of {start_date}.", "success")
    return redirect(url_for("operations.anchor_schedules"))


# ═════════════════════════════════════════════════════════════════════
#  SCHEDULING — Weekly View
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/weekly-view")
@login_required
@module_access_required("operations")
def weekly_view():
    week_start_str = request.args.get("week_start", "")
    if week_start_str:
        try:
            week_start = date.fromisoformat(week_start_str)
        except ValueError:
            week_start = date.today() - timedelta(days=(date.today().weekday() + 1) % 7)
    else:
        today = date.today()
        week_start = today - timedelta(days=(today.weekday() + 1) % 7)

    week_end = week_start + timedelta(days=6)
    days = [(week_start + timedelta(days=i)) for i in range(7)]
    assignments = dm.get_assignments_for_week(
        week_start.isoformat(), week_end.isoformat()
    )
    officers = dm.get_ops_officers()
    officers = _filter_records_by_site(officers)
    _, sites = _sites_and_filter()

    # Build grid: officer -> day -> list of assignments
    officer_grid = {}
    for off in officers:
        name = off.get("name", "")
        officer_grid[name] = {}
        for d in days:
            ds = d.isoformat()
            officer_grid[name][ds] = [
                a for a in assignments
                if a.get("officer_name") == name and a.get("date") == ds
            ]

    return render_template(
        "operations/weekly_view.html",
        officer_grid=officer_grid,
        officers=officers,
        sites=sites,
        days=days,
        week_start=week_start,
        week_end=week_end,
        prev_week=(week_start - timedelta(days=7)).isoformat(),
        next_week=(week_start + timedelta(days=7)).isoformat(),
        **_ctx("weekly_view"),
    )


@ops_bp.route("/assignments/create", methods=["POST"])
@login_required
@module_access_required("operations")
def assignment_create():
    fields = {
        "officer_name": request.form.get("officer_name", ""),
        "site_name": request.form.get("site_name", ""),
        "date": request.form.get("date", ""),
        "start_time": request.form.get("start_time", ""),
        "end_time": request.form.get("end_time", ""),
        "assignment_type": request.form.get("assignment_type", "Billable"),
        "status": request.form.get("status", "Scheduled"),
        "notes": request.form.get("notes", ""),
    }
    aid = dm.create_assignment(fields, created_by=_user())
    audit.log_event("operations", "create", _user(), f"Created assignment {aid}",
                     table_name="ops_assignments", record_id=aid, action="create")
    flash("Assignment created.", "success")
    redirect_to = request.form.get("redirect_to", "")
    if redirect_to:
        return redirect(redirect_to)
    return redirect(url_for("operations.weekly_view"))


@ops_bp.route("/assignments/<assignment_id>/edit", methods=["POST"])
@login_required
@module_access_required("operations")
def assignment_edit(assignment_id):
    fields = {
        "officer_name": request.form.get("officer_name", ""),
        "site_name": request.form.get("site_name", ""),
        "date": request.form.get("date", ""),
        "start_time": request.form.get("start_time", ""),
        "end_time": request.form.get("end_time", ""),
        "assignment_type": request.form.get("assignment_type", ""),
        "status": request.form.get("status", ""),
        "notes": request.form.get("notes", ""),
    }
    dm.update_assignment(assignment_id, fields, updated_by=_user())
    audit.log_event("operations", "update", _user(), f"Updated assignment {assignment_id}",
                     table_name="ops_assignments", record_id=assignment_id, action="update")
    flash("Assignment updated.", "success")
    redirect_to = request.form.get("redirect_to", "")
    if redirect_to:
        return redirect(redirect_to)
    return redirect(url_for("operations.weekly_view"))


@ops_bp.route("/assignments/<assignment_id>/delete", methods=["POST"])
@login_required
@module_access_required("operations")
def assignment_delete(assignment_id):
    dm.delete_assignment(assignment_id)
    audit.log_event("operations", "delete", _user(), f"Deleted assignment {assignment_id}",
                     table_name="ops_assignments", record_id=assignment_id, action="delete")
    flash("Assignment deleted.", "success")
    redirect_to = request.form.get("redirect_to", "")
    if redirect_to:
        return redirect(redirect_to)
    return redirect(url_for("operations.weekly_view"))


# ═════════════════════════════════════════════════════════════════════
#  MANAGEMENT — Officers CRUD
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/officers")
@login_required
@module_access_required("operations")
def officers():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "Active")
    if q:
        officers_list = dm.search_ops_officers(q)
    else:
        officers_list = dm.get_ops_officers(active_only=(status == "Active"))
    if status and status != "all":
        officers_list = [o for o in officers_list if o.get("status") == status]
    officers_list = _filter_records_by_site(officers_list)
    _, sites = _sites_and_filter()
    return render_template(
        "operations/officers.html",
        officers=officers_list,
        sites=sites,
        q=q,
        status_filter=status,
        **_ctx("officers"),
    )


@ops_bp.route("/officers/create", methods=["POST"])
@login_required
@module_access_required("operations")
def officers_create():
    fields = {
        "first_name": request.form.get("first_name", ""),
        "last_name": request.form.get("last_name", ""),
        "name": request.form.get("name", ""),
        "employee_id": request.form.get("employee_id", ""),
        "email": request.form.get("email", ""),
        "phone": request.form.get("phone", ""),
        "job_title": request.form.get("job_title", "Flex Officer"),
        "role": request.form.get("role", "Flex Officer"),
        "site": request.form.get("site", ""),
        "weekly_hours": request.form.get("weekly_hours", "40"),
        "hire_date": request.form.get("hire_date", ""),
        "status": request.form.get("status", "Active"),
        "notes": request.form.get("notes", ""),
    }
    if not fields["name"]:
        fields["name"] = f"{fields['first_name']} {fields['last_name']}".strip()
    mid = dm.create_ops_officer(fields, created_by=_user())
    audit.log_event("operations", "create", _user(), f"Created officer {mid} ({fields['name']})",
                     table_name="ops_flex_team", record_id=mid, action="create")
    flash(f"Officer {fields['name']} created.", "success")
    return redirect(url_for("operations.officers"))


@ops_bp.route("/officers/<member_id>/edit", methods=["POST"])
@login_required
@module_access_required("operations")
def officers_edit(member_id):
    fields = {
        "first_name": request.form.get("first_name", ""),
        "last_name": request.form.get("last_name", ""),
        "name": request.form.get("name", ""),
        "employee_id": request.form.get("employee_id", ""),
        "email": request.form.get("email", ""),
        "phone": request.form.get("phone", ""),
        "job_title": request.form.get("job_title", ""),
        "role": request.form.get("role", ""),
        "site": request.form.get("site", ""),
        "weekly_hours": request.form.get("weekly_hours", ""),
        "hire_date": request.form.get("hire_date", ""),
        "status": request.form.get("status", ""),
        "notes": request.form.get("notes", ""),
    }
    if not fields["name"]:
        fields["name"] = f"{fields['first_name']} {fields['last_name']}".strip()
    dm.update_ops_officer(member_id, fields, updated_by=_user())
    audit.log_event("operations", "update", _user(), f"Updated officer {member_id}",
                     table_name="ops_flex_team", record_id=member_id, action="update")
    flash("Officer updated.", "success")
    return redirect(url_for("operations.officers"))


@ops_bp.route("/officers/<member_id>/delete", methods=["POST"])
@login_required
@module_access_required("operations")
def officers_delete(member_id):
    dm.delete_ops_officer(member_id)
    audit.log_event("operations", "delete", _user(), f"Deleted officer {member_id}",
                     table_name="ops_flex_team", record_id=member_id, action="delete")
    flash("Officer deleted.", "success")
    return redirect(url_for("operations.officers"))


# ═════════════════════════════════════════════════════════════════════
#  MANAGEMENT — Sites CRUD
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/sites")
@login_required
@module_access_required("operations")
def sites():
    q = request.args.get("q", "").strip()
    if q:
        sites_list = dm.search_sites(q)
    else:
        sites_list = dm.get_active_sites()
    return render_template(
        "operations/sites.html",
        sites=sites_list,
        q=q,
        **_ctx("sites"),
    )


@ops_bp.route("/sites/create", methods=["POST"])
@login_required
@module_access_required("operations")
def sites_create():
    fields = {
        "name": request.form.get("name", ""),
        "address": request.form.get("address", ""),
        "city": request.form.get("city", ""),
        "state": request.form.get("state", ""),
        "zip": request.form.get("zip", ""),
        "contact_name": request.form.get("contact_name", ""),
        "contact_phone": request.form.get("contact_phone", ""),
        "contact_email": request.form.get("contact_email", ""),
        "status": request.form.get("status", "Active"),
        "notes": request.form.get("notes", ""),
    }
    sid = dm.create_site(fields, created_by=_user())
    audit.log_event("operations", "create", _user(), f"Created site {sid} ({fields['name']})",
                     table_name="sites", record_id=sid, action="create")
    flash(f"Site {fields['name']} created.", "success")
    return redirect(url_for("operations.sites"))


@ops_bp.route("/sites/<site_id>/edit", methods=["POST"])
@login_required
@module_access_required("operations")
def sites_edit(site_id):
    fields = {
        "name": request.form.get("name", ""),
        "address": request.form.get("address", ""),
        "city": request.form.get("city", ""),
        "state": request.form.get("state", ""),
        "zip": request.form.get("zip", ""),
        "contact_name": request.form.get("contact_name", ""),
        "contact_phone": request.form.get("contact_phone", ""),
        "contact_email": request.form.get("contact_email", ""),
        "status": request.form.get("status", ""),
        "notes": request.form.get("notes", ""),
    }
    dm.update_site(site_id, fields, updated_by=_user())
    audit.log_event("operations", "update", _user(), f"Updated site {site_id}",
                     table_name="sites", record_id=site_id, action="update")
    flash("Site updated.", "success")
    return redirect(url_for("operations.sites"))


# ═════════════════════════════════════════════════════════════════════
#  MANAGEMENT — Handoff Notes
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/handoff-notes")
@login_required
@module_access_required("operations")
def handoff_notes():
    site = request.args.get("site", "")
    site, sites = _sites_and_filter(site)
    notes = []
    if site:
        notes = dm.get_recent_notes(site, days=14)
    return render_template(
        "operations/handoff_notes.html",
        notes=notes,
        sites=sites,
        site_filter=site,
        **_ctx("handoff_notes"),
    )


@ops_bp.route("/handoff-notes/create", methods=["POST"])
@login_required
@module_access_required("operations")
def handoff_notes_create():
    fields = {
        "site": request.form.get("site", ""),
        "shift_date": request.form.get("shift_date", ""),
        "shift_type": request.form.get("shift_type", ""),
        "content": request.form.get("content", ""),
        "priority": request.form.get("priority", "normal"),
    }
    nid = dm.create_handoff_note(fields, author=_user())
    audit.log_event("operations", "create", _user(), f"Created handoff note {nid}",
                     table_name="ops_handoff_notes", record_id=nid, action="create")
    flash("Handoff note created.", "success")
    return redirect(url_for("operations.handoff_notes", site=fields["site"]))


@ops_bp.route("/handoff-notes/<note_id>/acknowledge", methods=["POST"])
@login_required
@module_access_required("operations")
def handoff_notes_ack(note_id):
    dm.acknowledge_note(note_id, _user())
    flash("Note acknowledged.", "success")
    site = request.form.get("site", "")
    return redirect(url_for("operations.handoff_notes", site=site))


# ═════════════════════════════════════════════════════════════════════
#  ADMIN — Reports
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/reports")
@login_required
@module_access_required("operations")
def reports():
    summary = dm.get_dashboard_summary()
    record_summary = dm.get_summary()
    req_summary = dm.get_request_summary()
    pos_kpis = dm.get_position_kpis()
    return render_template(
        "operations/reports.html",
        summary=summary,
        record_summary=record_summary,
        req_summary=req_summary,
        pos_kpis=pos_kpis,
        **_ctx("reports"),
    )


@ops_bp.route("/reports/export/<collection>")
@login_required
@module_access_required("operations")
def reports_export(collection):
    csv_text = dm.export_collection_csv(collection)
    if not csv_text:
        flash("No data to export.", "warning")
        return redirect(url_for("operations.reports"))
    from flask import Response
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ops_{collection}.csv"},
    )


# ═════════════════════════════════════════════════════════════════════
#  ADMIN — Audit Log
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/audit-log")
@login_required
@module_access_required("operations")
def audit_log():
    entries = audit.get_log(module_name="operations", limit=500)
    return render_template(
        "operations/audit_log.html",
        entries=entries,
        **_ctx("audit_log"),
    )


# ═════════════════════════════════════════════════════════════════════
#  ADMIN — Settings
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/settings")
@login_required
@module_access_required("operations")
def settings():
    from src.config import load_setting
    return render_template(
        "operations/settings.html",
        **_ctx("settings"),
    )


# ═════════════════════════════════════════════════════════════════════
#  ADMIN — Incidents (linked from dashboard)
# ═════════════════════════════════════════════════════════════════════

@ops_bp.route("/incidents")
@login_required
@module_access_required("operations")
def incidents():
    site = request.args.get("site", "")
    status = request.args.get("status", "")
    site, sites = _sites_and_filter(site)
    incidents_list = dm.get_all_incidents(site_filter=site, status_filter=status)
    return render_template(
        "operations/incidents.html",
        incidents=incidents_list,
        sites=sites,
        site_filter=site,
        status_filter=status,
        **_ctx("dashboard"),
    )


@ops_bp.route("/incidents/create", methods=["POST"])
@login_required
@module_access_required("operations")
def incidents_create():
    fields = {
        "site": request.form.get("site", ""),
        "incident_date": request.form.get("incident_date", ""),
        "incident_time": request.form.get("incident_time", ""),
        "incident_type": request.form.get("incident_type", ""),
        "severity": request.form.get("severity", "low"),
        "reporting_officer": request.form.get("reporting_officer", ""),
        "description": request.form.get("description", ""),
        "persons_involved": request.form.get("persons_involved", ""),
        "actions_taken": request.form.get("actions_taken", ""),
        "police_called": request.form.get("police_called", "") == "1",
        "police_report_number": request.form.get("police_report_number", ""),
        "medical_required": request.form.get("medical_required", "") == "1",
        "property_damage": request.form.get("property_damage", "") == "1",
        "witness_names": request.form.get("witness_names", ""),
        "supervisor_notified": request.form.get("supervisor_notified", "") == "1",
        "supervisor_name": request.form.get("supervisor_name", ""),
        "status": "Open",
    }
    iid = dm.create_incident(fields, created_by=_user())
    audit.log_event("operations", "create", _user(), f"Created incident {iid}",
                     table_name="ops_incidents", record_id=iid, action="create")
    flash("Incident report created.", "success")
    return redirect(url_for("operations.incidents"))
