"""
Cerasus Hub -- Attendance Module Blueprint
Full web routes for dashboard, roster, discipline, reviews, import/export, admin.
"""

from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, flash, Response,
)

import json

from src.web_middleware import login_required, module_access_required, apply_site_restriction
from src.modules.attendance import data_manager as dm
from src.modules.attendance.policy_engine import (
    INFRACTION_TYPES, DISCIPLINE_LABELS, THRESHOLDS,
    POINT_WINDOW_DAYS, calculate_active_points,
)
from src import audit

att_bp = Blueprint("attendance", __name__, url_prefix="/module/attendance")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE_ID = "attendance"
BREADCRUMB_ROOT = {"label": "Attendance", "url": "/module/attendance"}


def _ctx(active_tab, **extra):
    """Common template context for every attendance page."""
    ctx = {
        "active_module": MODULE_ID,
        "active_tab": active_tab,
        "breadcrumb_items": [BREADCRUMB_ROOT],
    }
    ctx.update(extra)
    return ctx


def _username():
    return session.get("username", "system")


# ===========================================================================
# OVERVIEW
# ===========================================================================

@att_bp.route("/")
@att_bp.route("/dashboard")
@login_required
@module_access_required(MODULE_ID)
def dashboard():
    summary = dm.get_dashboard_summary()
    return render_template("attendance/dashboard.html", **_ctx("dashboard"), summary=summary)


@att_bp.route("/roster")
@login_required
@module_access_required(MODULE_ID)
def roster():
    q = request.args.get("q", "").strip()
    site_filter = request.args.get("site", "")
    status_filter = request.args.get("status", "")
    site_filter, att_sites = apply_site_restriction(site_filter, dm.get_site_names())

    if q:
        officers = dm.search_officers(q)
    else:
        officers = dm.get_all_officers()

    # Apply site restriction for scoped users
    user_sites = session.get("assigned_sites", [])
    if user_sites:
        officers = [o for o in officers if o.get("site") in user_sites]
    if site_filter:
        officers = [o for o in officers if o.get("site") == site_filter]
    if status_filter:
        officers = [o for o in officers if o.get("status") == status_filter]

    sites = att_sites
    return render_template(
        "attendance/roster.html",
        **_ctx("roster"),
        officers=officers,
        sites=sites,
        q=q,
        site_filter=site_filter,
        status_filter=status_filter,
    )


@att_bp.route("/sites")
@login_required
@module_access_required(MODULE_ID)
def sites():
    site_summary = dm.get_site_attendance_summary()
    return render_template("attendance/sites.html", **_ctx("sites"), site_summary=site_summary)


@att_bp.route("/compare")
@login_required
@module_access_required(MODULE_ID)
def compare():
    site_summary = dm.get_site_attendance_summary()
    infraction_summary = dm.get_site_infraction_summary()
    return render_template(
        "attendance/compare.html",
        **_ctx("compare"),
        site_summary=site_summary,
        infraction_summary=infraction_summary,
    )


# ===========================================================================
# DISCIPLINE
# ===========================================================================

@att_bp.route("/log", methods=["GET", "POST"])
@login_required
@module_access_required(MODULE_ID)
def log_infraction():
    if request.method == "POST":
        fields = {
            "employee_id": request.form.get("employee_id", ""),
            "infraction_type": request.form.get("infraction_type", ""),
            "infraction_date": request.form.get("infraction_date", ""),
            "points_assigned": request.form.get("points_assigned") or None,
            "site": request.form.get("site", ""),
            "description": request.form.get("description", ""),
        }
        if not fields["employee_id"] or not fields["infraction_type"]:
            flash("Officer and infraction type are required.", "danger")
        else:
            inf_id = dm.create_infraction(fields, entered_by=_username())
            audit.log_event(
                MODULE_ID, "create_infraction", _username(),
                details=f"Infraction #{inf_id} for {fields['employee_id']}",
                table_name="ats_infractions", record_id=str(inf_id), action="create",
            )
            flash("Infraction logged successfully.", "success")
            return redirect(url_for("attendance.discipline"))

    officers = dm.get_all_officers()
    sites = dm.get_site_names()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return render_template(
        "attendance/log.html",
        **_ctx("log"),
        officers=officers,
        sites=sites,
        infraction_types=INFRACTION_TYPES,
        today=today,
    )


@att_bp.route("/discipline")
@login_required
@module_access_required(MODULE_ID)
def discipline():
    infractions = dm.get_all_infractions()

    # Filters
    q = request.args.get("q", "").strip().lower()
    site_filter = request.args.get("site", "")
    type_filter = request.args.get("type", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    site_filter, sites = apply_site_restriction(site_filter, dm.get_site_names())

    # Apply site restriction for scoped users
    user_sites = session.get("assigned_sites", [])
    if user_sites:
        infractions = [i for i in infractions if i.get("site") in user_sites]

    if q:
        infractions = [
            i for i in infractions
            if q in i.get("officer_name", i.get("employee_id", "")).lower()
            or q in i.get("description", "").lower()
            or q in i.get("site", "").lower()
        ]
    if site_filter:
        infractions = [i for i in infractions if i.get("site") == site_filter]
    if type_filter:
        infractions = [i for i in infractions if i.get("infraction_type") == type_filter]
    if date_from:
        infractions = [i for i in infractions if i.get("infraction_date", "") >= date_from]
    if date_to:
        infractions = [i for i in infractions if i.get("infraction_date", "") <= date_to]
    return render_template(
        "attendance/discipline.html",
        **_ctx("discipline"),
        infractions=infractions,
        sites=sites,
        infraction_types=INFRACTION_TYPES,
        q=q,
        site_filter=site_filter,
        type_filter=type_filter,
        date_from=date_from,
        date_to=date_to,
    )


@att_bp.route("/discipline/edit/<int:infraction_id>", methods=["POST"])
@login_required
@module_access_required(MODULE_ID)
def edit_infraction(infraction_id):
    raw_points = request.form.get("points_assigned", "")
    try:
        points = float(raw_points) if raw_points != "" else 0.0
    except (ValueError, TypeError):
        points = 0.0
    fields = {
        "infraction_type": request.form.get("infraction_type", ""),
        "infraction_date": request.form.get("infraction_date", ""),
        "points_assigned": points,
        "site": request.form.get("site", ""),
        "description": request.form.get("description", ""),
    }
    ok = dm.update_infraction(infraction_id, fields)
    if ok:
        audit.log_event(
            MODULE_ID, "update_infraction", _username(),
            details=f"Updated infraction #{infraction_id}",
            table_name="ats_infractions", record_id=str(infraction_id), action="update",
        )
        flash("Infraction updated.", "success")
    else:
        flash("Infraction not found.", "danger")
    return redirect(url_for("attendance.discipline"))


@att_bp.route("/discipline/delete/<int:infraction_id>", methods=["POST"])
@login_required
@module_access_required(MODULE_ID)
def delete_infraction(infraction_id):
    ok = dm.delete_infraction(infraction_id)
    if ok:
        audit.log_event(
            MODULE_ID, "delete_infraction", _username(),
            details=f"Deleted infraction #{infraction_id}",
            table_name="ats_infractions", record_id=str(infraction_id), action="delete",
        )
        flash("Infraction deleted.", "success")
    else:
        flash("Infraction not found.", "danger")
    return redirect(url_for("attendance.discipline"))


@att_bp.route("/reviews", methods=["GET", "POST"])
@login_required
@module_access_required(MODULE_ID)
def reviews():
    if request.method == "POST":
        action = request.form.get("_action", "")
        review_id = request.form.get("review_id")

        if action == "create":
            fields = {
                "employee_id": request.form.get("employee_id", ""),
                "triggered_date": request.form.get("triggered_date", ""),
                "points_at_trigger": float(request.form.get("points_at_trigger") or 0),
                "review_status": "Pending",
            }
            rid = dm.create_review(fields)
            audit.log_event(
                MODULE_ID, "create_review", _username(),
                details=f"Created review #{rid}",
                table_name="ats_employment_reviews", record_id=str(rid), action="create",
            )
            flash("Employment review created.", "success")

        elif action == "update" and review_id:
            fields = {
                "review_status": request.form.get("review_status", ""),
                "reviewed_by": request.form.get("reviewed_by", ""),
                "review_date": request.form.get("review_date", ""),
                "outcome": request.form.get("outcome", ""),
                "reviewer_notes": request.form.get("reviewer_notes", ""),
            }
            dm.update_review(int(review_id), fields)
            audit.log_event(
                MODULE_ID, "update_review", _username(),
                details=f"Updated review #{review_id}",
                table_name="ats_employment_reviews", record_id=str(review_id), action="update",
            )
            flash("Review updated.", "success")

        return redirect(url_for("attendance.reviews"))

    all_reviews = dm.get_all_reviews()
    officers = dm.get_all_officers()
    # Build lookup: employee_id -> name (include ATS ID mapping)
    officer_map = {o.get("employee_id", o.get("officer_id", "")): o.get("name", "") for o in officers}
    officer_map.update({o.get("officer_id", ""): o.get("name", "") for o in officers})
    # Add ATS id mappings
    try:
        from src.database import get_conn
        conn = get_conn()
        ats_rows = conn.execute("SELECT ats_id, officer_name FROM ats_id_mapping").fetchall()
        conn.close()
        for r in ats_rows:
            if r["ats_id"] not in officer_map or not officer_map.get(r["ats_id"]):
                officer_map[r["ats_id"]] = r["officer_name"]
    except Exception:
        pass
    return render_template(
        "attendance/reviews.html",
        **_ctx("reviews"),
        reviews=all_reviews,
        officers=officers,
        officer_map=officer_map,
    )


# ===========================================================================
# IMPORT
# ===========================================================================

@att_bp.route("/import", methods=["GET", "POST"])
@login_required
@module_access_required(MODULE_ID)
def import_csv():
    result = None
    if request.method == "POST":
        f = request.files.get("csv_file")
        if not f or not f.filename:
            flash("Please select a CSV file.", "danger")
        else:
            csv_text = f.read().decode("utf-8-sig")
            result = dm.import_employees_csv(csv_text, created_by=_username())
            audit.log_event(
                MODULE_ID, "import_employees", _username(),
                details=f"Imported {result['imported']} officers, {result['skipped']} skipped",
            )
            flash(f"Import complete: {result['imported']} imported, {result['skipped']} skipped.", "success")

    return render_template("attendance/import.html", **_ctx("import"), result=result)


@att_bp.route("/bulk-import", methods=["GET", "POST"])
@login_required
@module_access_required(MODULE_ID)
def bulk_import():
    result = None
    if request.method == "POST":
        f = request.files.get("csv_file")
        if not f or not f.filename:
            flash("Please select a CSV file.", "danger")
        else:
            csv_text = f.read().decode("utf-8-sig")
            result = dm.import_infractions_csv(csv_text, entered_by=_username())
            audit.log_event(
                MODULE_ID, "import_infractions", _username(),
                details=f"Imported {result['imported']} infractions, {result['skipped']} skipped",
            )
            flash(f"Import complete: {result['imported']} imported, {result['skipped']} skipped.", "success")

    return render_template("attendance/bulk_import.html", **_ctx("bulk_import"), result=result)


# ===========================================================================
# ADMIN
# ===========================================================================

@att_bp.route("/reports")
@login_required
@module_access_required(MODULE_ID)
def reports():
    summary = dm.get_dashboard_summary()
    dist = dm.get_discipline_level_distribution()
    site_inf = dm.get_site_infraction_summary()
    top_points = dm.get_officer_points_summary(limit=10)
    return render_template(
        "attendance/reports.html",
        **_ctx("reports"),
        summary=summary,
        distribution=dist,
        site_infractions=site_inf,
        top_points=top_points,
    )


@att_bp.route("/reports/export/<export_type>")
@login_required
@module_access_required(MODULE_ID)
def export_csv(export_type):
    if export_type == "discipline":
        csv_str = dm.export_discipline_csv()
        filename = "discipline_export.csv"
    elif export_type == "infractions":
        csv_str = dm.export_infractions_csv()
        filename = "infractions_export.csv"
    elif export_type == "reviews":
        csv_str = dm.export_reviews_csv()
        filename = "reviews_export.csv"
    else:
        flash("Unknown export type.", "danger")
        return redirect(url_for("attendance.reports"))

    if not csv_str:
        flash("No data to export.", "warning")
        return redirect(url_for("attendance.reports"))

    audit.log_event(
        MODULE_ID, "export_csv", _username(),
        details=f"Exported {export_type} CSV",
    )
    return Response(
        csv_str,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@att_bp.route("/analytics")
@login_required
@module_access_required(MODULE_ID)
def analytics():
    data = dm.get_analytics_data()
    return render_template("attendance/analytics.html", **_ctx("analytics"), data=data)


@att_bp.route("/audit")
@login_required
@module_access_required(MODULE_ID)
def audit_trail():
    entries = audit.get_log(module_name=MODULE_ID, limit=200)
    return render_template("attendance/audit.html", **_ctx("audit"), entries=entries)


@att_bp.route("/users")
@login_required
@module_access_required(MODULE_ID)
def user_management():
    return redirect(url_for("admin.users"))


@att_bp.route("/site-management", methods=["GET", "POST"])
@login_required
@module_access_required(MODULE_ID)
def site_management():
    if request.method == "POST":
        action = request.form.get("_action", "")
        if action == "create":
            name = request.form.get("name", "").strip()
            address = request.form.get("address", "").strip()
            if name:
                dm.create_site({"name": name, "address": address})
                audit.log_event(MODULE_ID, "create_site", _username(), details=f"Created site: {name}")
                flash(f"Site '{name}' created.", "success")
            else:
                flash("Site name is required.", "danger")
        elif action == "update":
            site_id = request.form.get("site_id", "")
            name = request.form.get("name", "").strip()
            address = request.form.get("address", "").strip()
            if site_id and name:
                dm.update_site(site_id, {"name": name, "address": address})
                audit.log_event(MODULE_ID, "update_site", _username(), details=f"Updated site: {name}")
                flash(f"Site '{name}' updated.", "success")
        elif action == "delete":
            site_id = request.form.get("site_id", "")
            if site_id:
                dm.delete_site(site_id)
                audit.log_event(MODULE_ID, "delete_site", _username(), details=f"Deleted site {site_id}")
                flash("Site deleted.", "success")
        return redirect(url_for("attendance.site_management"))

    all_sites = dm.get_all_sites()
    return render_template("attendance/site_mgmt.html", **_ctx("site_mgmt"), sites_list=all_sites)


@att_bp.route("/policy", methods=["GET", "POST"])
@login_required
@module_access_required(MODULE_ID)
def policy_settings():
    if request.method == "POST":
        # Save threshold overrides
        from src.modules.attendance.policy_engine import (
            THRESHOLDS, POINT_WINDOW_DAYS, CLEAN_SLATE_DAYS, EMERGENCY_MAX,
        )
        # We store overrides in the settings table
        for key in ("point_window_days", "clean_slate_days", "emergency_max",
                     "verbal_warning_pts", "written_warning_pts",
                     "employment_review_pts", "termination_pts"):
            val = request.form.get(key, "").strip()
            if val:
                dm.save_setting(f"ats_{key}", val)

        audit.log_event(MODULE_ID, "update_policy", _username(), details="Updated policy settings")
        flash("Policy settings saved.", "success")
        return redirect(url_for("attendance.policy_settings"))

    from src.modules.attendance.policy_engine import (
        THRESHOLDS, POINT_WINDOW_DAYS, CLEAN_SLATE_DAYS, EMERGENCY_MAX,
    )
    settings = {
        "point_window_days": dm.get_setting("ats_point_window_days") or str(POINT_WINDOW_DAYS),
        "clean_slate_days": dm.get_setting("ats_clean_slate_days") or str(CLEAN_SLATE_DAYS),
        "emergency_max": dm.get_setting("ats_emergency_max") or str(EMERGENCY_MAX),
        "verbal_warning_pts": dm.get_setting("ats_verbal_warning_pts") or "1.5",
        "written_warning_pts": dm.get_setting("ats_written_warning_pts") or "6",
        "employment_review_pts": dm.get_setting("ats_employment_review_pts") or "8",
        "termination_pts": dm.get_setting("ats_termination_pts") or "10",
    }
    return render_template(
        "attendance/policy.html",
        **_ctx("policy"),
        settings=settings,
        infraction_types=INFRACTION_TYPES,
        discipline_labels=DISCIPLINE_LABELS,
    )


# ===========================================================================
# DA INTEGRATION — Attendance → DA Generator
# ===========================================================================

DA_THRESHOLDS = [
    (1.5, "verbal_warning", "Verbal Warning"),
    (6.0, "written_warning", "Written Warning"),
    (8.0, "employment_review", "Final Warning"),  # Employment Review = Final Warning if retained
    (10.0, "termination_eligible", "Termination"),
]


def _resolve_officer(employee_id):
    """Resolve an employee_id to an officer dict. Tries officers table then ats_id_mapping."""
    from src.shared_data import get_officer
    from src.database import get_conn

    # Try direct lookup by officer_id
    off = get_officer(employee_id)
    if off:
        return off

    # Try lookup by employee_id field in officers table
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM officers WHERE employee_id = ? AND status != 'Deleted'",
        (employee_id,),
    ).fetchone()
    if row:
        conn.close()
        return dict(row)

    # Try ats_id_mapping
    row = conn.execute(
        "SELECT officer_id, officer_name FROM ats_id_mapping WHERE ats_id = ?",
        (employee_id,),
    ).fetchone()
    if row and row["officer_id"]:
        off = get_officer(row["officer_id"])
        if off:
            conn.close()
            return off
    # Build minimal dict from mapping
    if row:
        conn.close()
        return {"name": row["officer_name"], "officer_id": row.get("officer_id", employee_id),
                "employee_id": employee_id, "job_title": "Security Officer", "site": ""}
    conn.close()
    return {"name": employee_id, "officer_id": employee_id, "employee_id": employee_id,
            "job_title": "", "site": ""}


def compute_threshold_crossings(employee_id, infractions, reviews):
    """Walk infractions chronologically and detect discipline threshold crossings.

    Returns a list of crossing dicts, each with:
      - level, label, crossing_date, cumulative_points, included_infractions
    Accounts for Employment Review retain/reset dynamics.
    """
    from datetime import date, timedelta

    cutoff = (date.today() - timedelta(days=POINT_WINDOW_DAYS)).isoformat()

    # Filter to active infractions within the point window, sort chronologically
    active = [
        inf for inf in infractions
        if inf.get("points_active", 1)
        and inf.get("infraction_date", "") >= cutoff
    ]
    active.sort(key=lambda x: (x.get("infraction_date", ""), x.get("id", 0)))

    crossings = []
    crossed = set()
    running = 0.0
    seen = []

    # Find the most recent completed review for retain/reset logic
    completed_review = None
    for rev in (reviews or []):
        if rev.get("review_status") == "Completed":
            completed_review = rev
            break  # reviews are ordered by date desc

    review_date = (completed_review or {}).get("review_date", "")
    review_outcome = (completed_review or {}).get("outcome", "")
    was_retained = review_outcome in ("retain_reduce", "retain", "probation", "Retained",
                                       "Probation", "Final Warning")
    was_terminated_in_review = review_outcome in ("terminated", "Terminated")

    for inf in active:
        running += float(inf.get("points_assigned", 0))
        seen.append(inf)

        for pts, level, label in DA_THRESHOLDS:
            if level in crossed:
                continue
            if running < pts:
                continue

            # Employment Review crossing (8 pts)
            if level == "employment_review":
                crossed.add(level)
                if was_terminated_in_review:
                    # If terminated at review, this is a Termination DA
                    crossings.append({
                        "level": "termination",
                        "label": "Termination",
                        "crossing_date": inf.get("infraction_date", ""),
                        "cumulative_points": round(running, 2),
                        "included_infractions": list(seen),
                        "review_outcome": "terminated",
                    })
                    crossed.add("termination_eligible")
                elif was_retained:
                    # Retained = Final Warning DA, then reset to 6
                    crossings.append({
                        "level": "final_warning",
                        "label": "Final Warning (Employment Review — Retained)",
                        "crossing_date": inf.get("infraction_date", ""),
                        "cumulative_points": round(running, 2),
                        "included_infractions": list(seen),
                        "review_outcome": "retained",
                    })
                    running = 6.0  # Reset to 6 after retain
                elif completed_review:
                    # Review exists with another outcome
                    crossings.append({
                        "level": "employment_review",
                        "label": "Employment Review",
                        "crossing_date": inf.get("infraction_date", ""),
                        "cumulative_points": round(running, 2),
                        "included_infractions": list(seen),
                        "review_outcome": review_outcome or "pending",
                    })
                else:
                    # No review yet — still show the crossing
                    crossings.append({
                        "level": "employment_review",
                        "label": "Employment Review (Pending)",
                        "crossing_date": inf.get("infraction_date", ""),
                        "cumulative_points": round(running, 2),
                        "included_infractions": list(seen),
                        "review_outcome": "pending",
                    })
                continue

            # Termination crossing (10 pts — only after retain/reset)
            if level == "termination_eligible":
                crossings.append({
                    "level": "termination",
                    "label": "Termination",
                    "crossing_date": inf.get("infraction_date", ""),
                    "cumulative_points": round(running, 2),
                    "included_infractions": list(seen),  # Full history
                    "review_outcome": "post_retain",
                })
                crossed.add(level)
                continue

            # Normal threshold (Verbal / Written)
            crossings.append({
                "level": level,
                "label": label,
                "crossing_date": inf.get("infraction_date", ""),
                "cumulative_points": round(running, 2),
                "included_infractions": list(seen),
            })
            crossed.add(level)

    return crossings


def build_attendance_da_narrative(officer_name, threshold_label, infractions, cumulative_points):
    """Build a professional DA narrative from attendance infraction data."""
    lines = []
    lines.append(
        f"{officer_name} has accumulated {cumulative_points} attendance infraction points "
        f"under the Company's progressive discipline policy, crossing the "
        f"{threshold_label} threshold."
    )
    lines.append("")
    lines.append("The following attendance infractions have been recorded:")
    lines.append("")

    for inf in infractions:
        inf_date = inf.get("infraction_date", "Unknown date")
        inf_type = INFRACTION_TYPES.get(inf.get("infraction_type", ""), {})
        type_label = inf_type.get("label", inf.get("infraction_type", "Unknown").replace("_", " ").title())
        points = inf.get("points_assigned", 0)
        desc = (inf.get("description") or "").strip()

        detail_line = f"• {inf_date}: {type_label} ({points} pts)"
        if desc:
            # Truncate long descriptions for the narrative
            short_desc = desc[:200] + "..." if len(desc) > 200 else desc
            detail_line += f" — {short_desc}"
        else:
            detail_line += " [⚠ Add shift/timing details before finalizing]"
        lines.append(detail_line)

    lines.append("")
    lines.append(
        "Per Company Handbook Section 3.5 (Attendance and Punctuality), "
        "employees who accumulate attendance points are subject to "
        "progressive discipline."
    )
    lines.append("")
    lines.append(f"Total active points at time of this action: {cumulative_points}")

    return "\n".join(lines)


@att_bp.route("/officer/<employee_id>/da-options")
@login_required
@module_access_required(MODULE_ID)
def officer_da_options(employee_id):
    """Show available DA drafts for an officer based on threshold crossings."""
    officer = _resolve_officer(employee_id)
    infractions = dm.get_infractions_for_employee(employee_id)
    reviews = dm.get_reviews_for_employee(employee_id)

    crossings = compute_threshold_crossings(employee_id, infractions, reviews)

    # Generate narrative previews for each crossing
    for c in crossings:
        c["narrative"] = build_attendance_da_narrative(
            officer.get("name", employee_id),
            c["label"],
            c["included_infractions"],
            c["cumulative_points"],
        )

    active_points = calculate_active_points(infractions)

    return render_template(
        "attendance/da_options.html",
        **_ctx("discipline"),
        officer=officer,
        employee_id=employee_id,
        crossings=crossings,
        active_points=active_points,
        infraction_types=INFRACTION_TYPES,
    )


@att_bp.route("/officer/<employee_id>/create-da", methods=["POST"])
@login_required
@module_access_required(MODULE_ID)
def create_attendance_da(employee_id):
    """Create a DA record from attendance infraction data and redirect to DA Generator."""
    from src.modules.da_generator import data_manager as da_dm

    officer = _resolve_officer(employee_id)
    threshold_level = request.form.get("threshold_level", "")
    threshold_label = request.form.get("threshold_label", "")
    infraction_ids = request.form.get("infraction_ids", "").split(",")
    cumulative_points = float(request.form.get("cumulative_points") or 0)
    narrative = request.form.get("narrative", "")

    # Fetch the actual infraction records
    all_inf = dm.get_infractions_for_employee(employee_id)
    included = [inf for inf in all_inf if str(inf.get("id")) in infraction_ids]
    if not included:
        included = all_inf  # Fallback

    incident_dates = ", ".join(sorted(set(
        inf.get("infraction_date", "") for inf in included if inf.get("infraction_date")
    )))

    # Map discipline level to DA form values
    level_map = {
        "verbal_warning": "Verbal Warning",
        "written_warning": "Written Warning",
        "final_warning": "Final Warning",
        "employment_review": "Final Warning",
        "termination": "Termination",
        "termination_eligible": "Termination",
    }
    discipline_level = level_map.get(threshold_level, threshold_label)

    # Build prior discipline flags
    prior_verbal = 1 if threshold_level in ("written_warning", "final_warning",
                                              "employment_review", "termination") else 0
    prior_written = 1 if threshold_level in ("final_warning", "employment_review",
                                              "termination") else 0
    prior_final = 1 if threshold_level in ("termination",) else 0

    fields = {
        "employee_name": officer.get("name", ""),
        "employee_position": officer.get("job_title", "Security Officer"),
        "employee_officer_id": officer.get("officer_id", employee_id),
        "site": officer.get("site", ""),
        "violation_type": "Attendance",
        "incident_dates": incident_dates,
        "incident_narrative": narrative,
        "discipline_level": discipline_level,
        "attendance_points_at_da": cumulative_points,
        "attendance_record_json": json.dumps([{
            "id": inf.get("id"),
            "date": inf.get("infraction_date"),
            "type": inf.get("infraction_type"),
            "points": inf.get("points_assigned"),
            "description": inf.get("description", ""),
        } for inf in included]),
        "prior_verbal_same": prior_verbal,
        "prior_written_same": prior_written,
        "prior_final_same": prior_final,
        "status": "draft",
    }

    username = _username()
    da_id = da_dm.create_da(fields, created_by=username)
    audit.log_event(MODULE_ID, "create_attendance_da", username,
                    f"Created {discipline_level} DA for {officer.get('name', employee_id)}: {da_id}",
                    table_name="da_records", record_id=da_id, action="create")

    flash(f"Attendance DA created: {da_id} ({discipline_level})", "success")
    return redirect(url_for("da_generator.new_da", da_id=da_id))
