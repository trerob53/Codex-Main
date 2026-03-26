"""
Cerasus Hub — Uniforms Module Blueprint
Web routes for the uniforms management module.
"""

from flask import (
    Blueprint, render_template, request, session, redirect, url_for, flash, Response,
)

from src.web_middleware import login_required, role_required, apply_site_restriction
from src.modules.uniforms import data_manager as dm
from src.modules.uniforms import notification_log

uni_bp = Blueprint("uniforms", __name__, url_prefix="/module/uniforms")

MODULE_ID = "uniforms"
MODULE_COLOR = "#7C3AED"
MODULE_BG = "#F3E8FF"

SIDEBAR = [
    ("OVERVIEW", [("Dashboard", "uniforms.dashboard"), ("Cost Analytics", "uniforms.cost_analytics")]),
    ("PERSONNEL", [("Officers", "uniforms.officers"), ("Sites", "uniforms.sites")]),
    ("UNIFORMS", [
        ("Issue Items", "uniforms.issue_items"),
        ("Process Return", "uniforms.process_return"),
        ("All Issuances", "uniforms.all_issuances"),
        ("Pending Orders", "uniforms.pending_orders"),
    ]),
    ("INVENTORY", [
        ("Stock", "uniforms.stock"),
        ("Compliance", "uniforms.compliance"),
        ("Replacements", "uniforms.replacements"),
    ]),
    ("ADMIN", [
        ("Reports", "uniforms.reports"),
        ("Audit Log", "uniforms.audit_log"),
        ("Notifications", "uniforms.notifications"),
        ("Settings", "uniforms.settings"),
    ]),
]


def _ctx(active_tab, **extra):
    """Common template context for all uniforms pages."""
    ctx = dict(
        active_module=MODULE_ID,
        module_color=MODULE_COLOR,
        module_bg=MODULE_BG,
        sidebar_sections=SIDEBAR,
        active_tab=active_tab,
    )
    ctx.update(extra)
    return ctx


# ── OVERVIEW ─────────────────────────────────────────────────────────

@uni_bp.route("/")
@uni_bp.route("/dashboard")
@login_required
def dashboard():
    site_filter = request.args.get("site", "All Sites")
    site_filter, sites = apply_site_restriction(
        site_filter if site_filter != "All Sites" else "", dm.get_all_site_names())
    if not site_filter:
        site_filter = "All Sites"
    summary = dm.get_dashboard_summary_filtered(site_filter)
    return render_template(
        "uniforms/dashboard.html",
        **_ctx("Dashboard", summary=summary, sites=sites, site_filter=site_filter),
    )


@uni_bp.route("/cost-analytics")
@login_required
def cost_analytics():
    site_filter = request.args.get("site", "All Sites")
    site_filter, sites = apply_site_restriction(
        site_filter if site_filter != "All Sites" else "", dm.get_all_site_names())
    if not site_filter:
        site_filter = "All Sites"
    cost_data = dm.get_cost_analytics(site_filter)
    return render_template(
        "uniforms/cost_analytics.html",
        **_ctx("Cost Analytics", cost_data=cost_data, sites=sites, site_filter=site_filter),
    )


# ── PERSONNEL ────────────────────────────────────────────────────────

@uni_bp.route("/officers")
@login_required
def officers():
    officers_list = dm.get_all_officers_parsed()
    return render_template(
        "uniforms/officers.html",
        **_ctx("Officers", officers=officers_list),
    )


@uni_bp.route("/sites")
@login_required
def sites():
    sites_list = dm.get_all_managed_sites()
    return render_template(
        "uniforms/sites.html",
        **_ctx("Sites", sites=sites_list),
    )


# ── UNIFORMS ─────────────────────────────────────────────────────────

@uni_bp.route("/issue", methods=["GET", "POST"])
@login_required
def issue_items():
    if request.method == "POST":
        fields = {
            "officer_id": request.form.get("officer_id", ""),
            "officer_name": request.form.get("officer_name", ""),
            "item_id": request.form.get("item_id", ""),
            "item_name": request.form.get("item_name", ""),
            "size": request.form.get("size", ""),
            "quantity": request.form.get("quantity", "1"),
            "condition_issued": request.form.get("condition_issued", "New"),
            "date_issued": request.form.get("date_issued", ""),
            "issued_by": request.form.get("issued_by", ""),
            "notes": request.form.get("notes", ""),
            "location": request.form.get("location", ""),
        }
        username = session.get("username", "system")
        dm.create_issuance(fields, created_by=username)
        flash("Item issued successfully.", "success")
        return redirect(url_for("uniforms.issue_items"))

    officers_list = dm.get_active_officers_parsed()
    catalog = dm.get_all_catalog()
    return render_template(
        "uniforms/issue_items.html",
        **_ctx("Issue Items", officers=officers_list, catalog=catalog,
               categories=dm.ITEM_CATEGORIES, locations=dm.STORAGE_LOCATIONS),
    )


@uni_bp.route("/return", methods=["GET", "POST"])
@login_required
def process_return():
    if request.method == "POST":
        issuance_id = request.form.get("issuance_id", "")
        condition = request.form.get("return_condition", "Good")
        notes = request.form.get("return_notes", "")
        username = session.get("username", "system")
        ok = dm.process_return(issuance_id, condition, notes, updated_by=username)
        if ok:
            flash("Return processed successfully.", "success")
        else:
            flash("Return failed. Issuance not found or already returned.", "danger")
        return redirect(url_for("uniforms.process_return"))

    outstanding = dm.get_outstanding_issuances()
    return render_template(
        "uniforms/process_return.html",
        **_ctx("Process Return", outstanding=outstanding),
    )


@uni_bp.route("/issuances")
@login_required
def all_issuances():
    issuances = dm.get_all_issuances()
    return render_template(
        "uniforms/all_issuances.html",
        **_ctx("All Issuances", issuances=issuances),
    )


@uni_bp.route("/pending-orders", methods=["GET", "POST"])
@login_required
def pending_orders():
    if request.method == "POST":
        action = request.form.get("action", "")
        order_id = request.form.get("order_id", "")
        username = session.get("username", "system")
        if action == "fulfill" and order_id:
            dm.fulfill_pending_order(order_id, fulfilled_by=username)
            flash("Order fulfilled and issuance created.", "success")
        elif action == "cancel" and order_id:
            dm.cancel_pending_order(order_id)
            flash("Order cancelled.", "warning")
        return redirect(url_for("uniforms.pending_orders"))

    orders = dm.get_all_pending_orders()
    return render_template(
        "uniforms/pending_orders.html",
        **_ctx("Pending Orders", orders=orders),
    )


# ── INVENTORY ────────────────────────────────────────────────────────

@uni_bp.route("/stock", methods=["GET", "POST"])
@login_required
def stock():
    if request.method == "POST" and request.form.get("action") == "update_stock":
        item_id = request.form.get("item_id", "")
        for loc in dm.STORAGE_LOCATIONS:
            for size in dm.UNIFORM_SIZES:
                key = f"qty_{loc}_{size}"
                val = request.form.get(key, "")
                if val != "":
                    dm.set_item_size_stock(item_id, size, int(val), loc)
        flash("Stock updated.", "success")
        return redirect(url_for("uniforms.stock"))

    catalog = dm.get_all_catalog()
    low_stock = dm.get_low_stock_items()
    # Attach size/location breakdown for each item
    for item in catalog:
        item["size_grid"] = {}
        for loc in dm.STORAGE_LOCATIONS:
            sizes = dm.get_item_sizes(item["item_id"], loc)
            item["size_grid"][loc] = {s["size"]: s["stock_qty"] for s in sizes}
    return render_template(
        "uniforms/stock.html",
        **_ctx("Stock", catalog=catalog, low_stock=low_stock,
               sizes=dm.UNIFORM_SIZES, locations=dm.STORAGE_LOCATIONS),
    )


@uni_bp.route("/compliance")
@login_required
def compliance():
    site_filter = request.args.get("site", "")
    sites = dm.get_all_site_names()
    report = dm.get_compliance_report(site_filter)
    summary = dm.get_compliance_summary(site_filter)
    return render_template(
        "uniforms/compliance.html",
        **_ctx("Compliance", report=report, summary=summary,
               sites=sites, site_filter=site_filter),
    )


@uni_bp.route("/replacements")
@login_required
def replacements():
    site_filter = request.args.get("site", "All Sites")
    days = int(request.args.get("days", 90))
    sites = dm.get_all_site_names()
    schedule = dm.get_replacement_schedule(days, site_filter)
    return render_template(
        "uniforms/replacements.html",
        **_ctx("Replacements", schedule=schedule, sites=sites,
               site_filter=site_filter, days=days),
    )


# ── ADMIN ────────────────────────────────────────────────────────────

@uni_bp.route("/reports")
@login_required
def reports():
    return render_template("uniforms/reports.html", **_ctx("Reports"))


@uni_bp.route("/reports/export/<collection>")
@login_required
def export_csv(collection):
    csv_data = dm.export_collection_csv(collection)
    if not csv_data:
        flash("No data to export.", "warning")
        return redirect(url_for("uniforms.reports"))
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=uniforms_{collection}.csv"},
    )


@uni_bp.route("/audit-log")
@login_required
def audit_log():
    entries = dm.get_audit_log_entries(limit=200)
    return render_template(
        "uniforms/audit_log.html",
        **_ctx("Audit Log", entries=entries),
    )


@uni_bp.route("/notifications")
@login_required
def notifications():
    notifs = notification_log.get_notifications(limit=100)
    stats = notification_log.get_notification_stats()
    return render_template(
        "uniforms/notifications.html",
        **_ctx("Notifications", notifications=notifs, stats=stats),
    )


@uni_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "save_setting":
            key = request.form.get("key", "")
            value = request.form.get("value", "")
            if key:
                dm.save_setting(key, value)
                flash("Setting saved.", "success")
        elif action == "add_requirement":
            data = {
                "job_title": request.form.get("job_title", ""),
                "item_id": request.form.get("item_id", ""),
                "item_name": request.form.get("item_name", ""),
                "qty_required": request.form.get("qty_required", "1"),
            }
            dm.create_requirement(data)
            flash("Requirement added.", "success")
        elif action == "delete_requirement":
            req_id = request.form.get("req_id", "")
            dm.delete_requirement(req_id)
            flash("Requirement deleted.", "warning")
        elif action == "add_catalog_item":
            data = {
                "item_name": request.form.get("item_name", ""),
                "category": request.form.get("category", ""),
                "description": request.form.get("description", ""),
                "unit_cost": request.form.get("unit_cost", "0"),
                "reorder_point": request.form.get("reorder_point", "5"),
                "status": request.form.get("status", "Active"),
            }
            username = session.get("username", "system")
            dm.create_catalog_item(data, created_by=username)
            flash("Catalog item added.", "success")
        elif action == "edit_catalog_item":
            item_id = request.form.get("item_id", "")
            data = {
                "item_name": request.form.get("item_name", ""),
                "category": request.form.get("category", ""),
                "description": request.form.get("description", ""),
                "unit_cost": request.form.get("unit_cost", "0"),
                "reorder_point": request.form.get("reorder_point", "5"),
                "status": request.form.get("status", "Active"),
            }
            if dm.update_catalog_item(item_id, data):
                flash("Catalog item updated.", "success")
            else:
                flash("Catalog item not found.", "danger")
        elif action == "delete_catalog_item":
            item_id = request.form.get("item_id", "")
            dm.delete_catalog_item(item_id)
            flash("Catalog item deleted.", "warning")
        return redirect(url_for("uniforms.settings"))

    catalog = dm.get_all_catalog()
    requirements = dm.get_all_requirements()
    return render_template(
        "uniforms/settings.html",
        **_ctx("Settings", catalog=catalog, requirements=requirements,
               job_titles=dm.JOB_TITLES, categories=dm.ITEM_CATEGORIES),
    )
