"""
Cerasus Hub — DA Generator Module Blueprint
Web routes for the Disciplinary Action generator module.
"""

import os
import tempfile

from flask import (
    Blueprint, render_template, request, session, redirect, url_for, flash,
    send_file,
)

from src.web_middleware import login_required, role_required
from src.modules.da_generator import data_manager as dm
from src.shared_data import get_all_officers, get_site_names

da_bp = Blueprint("da_generator", __name__, url_prefix="/module/da_generator")

MODULE_ID = "da_generator"
MODULE_COLOR = "#B91C1C"
MODULE_BG = "#FDE8EB"

SIDEBAR = [
    ("GENERATOR", [
        ("New DA", "da_generator.new_da"),
        ("DA History", "da_generator.da_history"),
    ]),
    ("SETTINGS", [
        ("Templates", "da_generator.templates"),
        ("Configuration", "da_generator.configuration"),
    ]),
]

VIOLATION_TYPES = [
    "Attendance",
    "Tardiness",
    "No Call / No Show",
    "Policy Violation",
    "Conduct / Behavior",
    "Job Performance",
    "Insubordination",
    "Safety Violation",
    "Uniform / Appearance",
    "Other",
]

DISCIPLINE_LEVELS = [
    "Verbal Warning",
    "Written Warning",
    "Final Warning",
    "Termination",
]


def _ctx(active_tab, **extra):
    """Common template context for all DA generator pages."""
    ctx = dict(
        active_module=MODULE_ID,
        module_color=MODULE_COLOR,
        module_bg=MODULE_BG,
        sidebar_sections=SIDEBAR,
        active_tab=active_tab,
    )
    ctx.update(extra)
    return ctx


# ── GENERATOR ────────────────────────────────────────────────────────

@da_bp.route("/")
@da_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_da():
    if request.method == "POST":
        fields = {
            "employee_name": request.form.get("employee_name", ""),
            "employee_position": request.form.get("employee_position", ""),
            "employee_officer_id": request.form.get("employee_officer_id", ""),
            "site": request.form.get("site", ""),
            "security_director": request.form.get("security_director", ""),
            "incident_dates": request.form.get("incident_dates", ""),
            "incident_narrative": request.form.get("incident_narrative", ""),
            "violation_type": request.form.get("violation_type", ""),
            "discipline_level": request.form.get("discipline_level", ""),
            "coaching_occurred": 1 if request.form.get("coaching_occurred") else 0,
            "coaching_date": request.form.get("coaching_date", ""),
            "coaching_content": request.form.get("coaching_content", ""),
            "prior_verbal_same": int(request.form.get("prior_verbal_same", 0)),
            "prior_written_same": int(request.form.get("prior_written_same", 0)),
            "prior_final_same": int(request.form.get("prior_final_same", 0)),
            "additional_comments": request.form.get("additional_comments", ""),
            "status": "draft",
        }
        username = session.get("username", "system")
        da_id = dm.create_da(fields, created_by=username)
        flash(f"DA created successfully: {da_id}", "success")
        return redirect(url_for("da_generator.da_history"))

    officers = get_all_officers()
    sites = get_site_names()

    # Support pre-filling from an existing DA (e.g., created by attendance integration)
    da = None
    da_id = request.args.get("da_id", "")
    if da_id:
        da = dm.get_da(da_id)

    return render_template(
        "da_generator/new_da.html",
        **_ctx("New DA", officers=officers, sites=sites,
               violation_types=VIOLATION_TYPES, discipline_levels=DISCIPLINE_LEVELS,
               da=da),
    )


@da_bp.route("/history")
@login_required
def da_history():
    status_filter = request.args.get("status", "")
    das = dm.get_all_das(status_filter)
    summary = dm.get_da_summary()
    turnaround = dm.get_da_turnaround_stats()
    return render_template(
        "da_generator/da_history.html",
        **_ctx("DA History", das=das, summary=summary, turnaround=turnaround,
               status_filter=status_filter),
    )


@da_bp.route("/history/<da_id>/status", methods=["POST"])
@login_required
def update_status(da_id):
    new_status = request.form.get("status", "")
    username = session.get("username", "system")
    ok = dm.update_da_status(da_id, new_status, updated_by=username)
    if ok:
        flash(f"DA {da_id} status updated to {new_status}.", "success")
    else:
        flash("Status update failed. Invalid status or DA not found.", "danger")
    return redirect(url_for("da_generator.da_history"))


@da_bp.route("/history/<da_id>/delete", methods=["POST"])
@login_required
def delete_da(da_id):
    ok = dm.delete_da(da_id)
    if ok:
        flash(f"DA {da_id} deleted.", "warning")
    else:
        flash("Delete failed. DA not found.", "danger")
    return redirect(url_for("da_generator.da_history"))


@da_bp.route("/history/<da_id>/download-pdf")
@login_required
def download_pdf(da_id):
    """Generate and download a filled DA PDF for the given record."""
    from src.modules.da_generator.pdf_filler import fill_da_pdf, generate_da_filename
    from datetime import date

    da = dm.get_da(da_id)
    if not da:
        flash("DA not found.", "danger")
        return redirect(url_for("da_generator.da_history"))

    # Build the data dict expected by pdf_filler
    # Prefer final (wizard-refined) fields, fall back to raw input fields
    pdf_data = {
        "employee_name": da.get("employee_name", ""),
        "position": da.get("employee_position", ""),
        "site": da.get("site", ""),
        "supervisor": da.get("security_director", ""),
        "date_occurred": da.get("incident_dates", ""),
        "date_written": date.today().isoformat(),
        "discipline_level": da.get("discipline_level", ""),
        "narrative": da.get("final_narrative") or da.get("ceis_narrative") or da.get("incident_narrative", ""),
        "citations": da.get("final_citations") or da.get("ceis_citations", ""),
        "prior_same": da.get("final_prior_discipline") or _build_prior_text(da, "same"),
        "prior_other": _build_prior_text(da, "other"),
        "improvements": da.get("required_improvements", ""),
        "additional_comments": da.get("additional_comments", ""),
    }

    filename = generate_da_filename(
        da.get("employee_name", "Unknown"),
        da.get("discipline_level", "DA"),
        da.get("violation_type", ""),
    )

    tmp_dir = tempfile.mkdtemp()
    output_path = os.path.join(tmp_dir, filename)

    try:
        fill_da_pdf(output_path, pdf_data)
        return send_file(output_path, as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f"PDF generation failed: {e}", "danger")
        return redirect(url_for("da_generator.da_history"))


def _build_prior_text(da, category):
    """Build prior discipline summary text for PDF field."""
    parts = []
    if category == "same":
        if da.get("prior_verbal_same"):
            parts.append(f"Verbal Warning(s): {da['prior_verbal_same']}")
        if da.get("prior_written_same"):
            parts.append(f"Written Warning(s): {da['prior_written_same']}")
        if da.get("prior_final_same"):
            parts.append(f"Final Warning(s): {da['prior_final_same']}")
    else:
        if da.get("prior_verbal_other"):
            parts.append(f"Verbal Warning(s): {da['prior_verbal_other']}")
        if da.get("prior_written_other"):
            parts.append(f"Written Warning(s): {da['prior_written_other']}")
        if da.get("prior_final_other"):
            parts.append(f"Final Warning(s): {da['prior_final_other']}")
    return "; ".join(parts) if parts else "None"


# ── SETTINGS ─────────────────────────────────────────────────────────

@da_bp.route("/templates")
@login_required
def templates():
    # Load saved template overrides from settings
    saved_templates = {}
    for key in ["narrative_template", "citations_template", "improvements_template"]:
        val = dm.get_setting(key)
        if val:
            saved_templates[key] = val
    return render_template(
        "da_generator/templates.html",
        **_ctx("Templates", saved_templates=saved_templates, discipline_levels=DISCIPLINE_LEVELS),
    )


@da_bp.route("/configuration", methods=["GET", "POST"])
@login_required
def configuration():
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "save_setting":
            key = request.form.get("key", "")
            value = request.form.get("value", "")
            if key:
                dm.save_setting(key, value)
                flash("Setting saved.", "success")
        return redirect(url_for("da_generator.configuration"))

    settings = {}
    for key in ["company_name", "security_director_default", "default_violation_type",
                 "auto_save_drafts", "require_witness"]:
        settings[key] = dm.get_setting(key) or ""
    summary = dm.get_da_summary()
    extended = dm.get_da_extended_stats()
    return render_template(
        "da_generator/configuration.html",
        **_ctx("Configuration", settings=settings, summary=summary, extended=extended),
    )
