"""
Cerasus Hub — Automated Report Generator
Generates weekly PDF reports per site and a hub-wide executive summary.
"""

from datetime import datetime, timedelta
from src.database import get_conn
from src.pdf_export import PDFDocument


def _week_bounds(week_start=None, week_end=None):
    """Return (start, end) as YYYY-MM-DD strings. Defaults to current Mon-Sun."""
    if week_start and week_end:
        return week_start, week_end
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def generate_site_report(site_name: str, week_start: str, week_end: str) -> str:
    """
    Generate a PDF report for one site for one week.

    Includes coverage summary, officer roster, attendance infractions,
    uniform compliance, and training completion for the site.

    Returns the filepath of the generated PDF.
    """
    conn = get_conn()
    safe_name = site_name.replace(" ", "_").replace("/", "-")
    filename = f"site_{safe_name}_{week_start}_to_{week_end}.pdf"
    doc = PDFDocument(filename=filename, title=f"Site Report — {site_name}")
    doc.begin()

    # ── Site header ───────────────────────────────────────────────────
    doc.add_text(f"Site: {site_name}", bold=True, size=14)
    try:
        site_row = conn.execute(
            "SELECT address, city, state FROM sites WHERE name = ?", (site_name,)
        ).fetchone()
        if site_row:
            addr_parts = [site_row["address"], site_row["city"], site_row["state"]]
            doc.add_text(", ".join(p for p in addr_parts if p), size=10, color="#6B7280")
    except Exception:
        pass
    doc.add_text(f"Period: {week_start}  to  {week_end}", size=10, color="#6B7280")
    doc.add_spacing(10)

    # ── Coverage summary ──────────────────────────────────────────────
    doc.add_section_title("Coverage Summary")
    total_hours = 0.0
    officers_set = set()
    shifts_covered = 0
    try:
        rows = conn.execute(
            "SELECT officer_name, hours FROM ops_assignments "
            "WHERE site_name = ? AND date BETWEEN ? AND ?",
            (site_name, week_start, week_end),
        ).fetchall()
        for r in rows:
            try:
                total_hours += float(r["hours"])
            except (ValueError, TypeError):
                pass
            if r["officer_name"]:
                officers_set.add(r["officer_name"])
            shifts_covered += 1
    except Exception:
        pass

    doc.add_kpi_row([
        ("Total Hours", f"{total_hours:.1f}", "#374151"),
        ("Officers Assigned", str(len(officers_set)), "#2563EB"),
        ("Shifts Covered", str(shifts_covered), "#059669"),
    ])
    doc.add_spacing(6)

    # ── Officer roster with hours ─────────────────────────────────────
    doc.add_section_title("Officer Roster")
    officer_hours = {}
    try:
        rows = conn.execute(
            "SELECT officer_name, SUM(CAST(hours AS REAL)) as h "
            "FROM ops_assignments WHERE site_name = ? AND date BETWEEN ? AND ? "
            "GROUP BY officer_name ORDER BY h DESC",
            (site_name, week_start, week_end),
        ).fetchall()
        for r in rows:
            officer_hours[r["officer_name"]] = r["h"] or 0
    except Exception:
        pass

    if officer_hours:
        roster_rows = [[name, f"{hrs:.1f}"] for name, hrs in officer_hours.items()]
        doc.add_table(["Officer", "Hours Worked"], roster_rows)
    else:
        doc.add_text("No assignments found for this period.", color="#6B7280")
    doc.add_spacing(6)

    # ── Attendance infractions ────────────────────────────────────────
    doc.add_section_title("Attendance Infractions")
    infraction_rows = []
    try:
        rows = conn.execute(
            "SELECT i.employee_id, o.name, i.infraction_type, i.infraction_date, "
            "i.points_assigned FROM ats_infractions i "
            "LEFT JOIN officers o ON i.employee_id = o.officer_id "
            "WHERE i.site = ? AND i.infraction_date BETWEEN ? AND ? "
            "ORDER BY i.infraction_date",
            (site_name, week_start, week_end),
        ).fetchall()
        for r in rows:
            infraction_rows.append([
                r["name"] or r["employee_id"],
                r["infraction_type"],
                r["infraction_date"],
                str(r["points_assigned"]),
            ])
    except Exception:
        pass

    if infraction_rows:
        doc.add_table(
            ["Officer", "Type", "Date", "Points"], infraction_rows,
        )
    else:
        doc.add_text("No infractions logged this period.", color="#059669")
    doc.add_spacing(6)

    # ── Uniform compliance ────────────────────────────────────────────
    doc.add_section_title("Uniform Compliance")
    try:
        site_officers = list(officers_set)
        if site_officers:
            placeholders = ",".join("?" * len(site_officers))
            total_issued = conn.execute(
                f"SELECT COUNT(*) as c FROM uni_issuances "
                f"WHERE officer_name IN ({placeholders}) AND status = 'Outstanding'",
                site_officers,
            ).fetchone()["c"]
            total_req = conn.execute(
                "SELECT COUNT(*) as c FROM uni_requirements"
            ).fetchone()["c"]
            officer_count = len(site_officers)
            expected = total_req * officer_count if total_req else 0
            compliance = (total_issued / expected * 100) if expected > 0 else 100.0
            doc.add_kpi_row([
                ("Compliance %", f"{compliance:.0f}%", "#059669" if compliance >= 80 else "#C8102E"),
                ("Items Outstanding", str(total_issued), "#374151"),
            ])
        else:
            doc.add_text("No officers assigned — compliance N/A.", color="#6B7280")
    except Exception:
        doc.add_text("Uniform data unavailable.", color="#6B7280")
    doc.add_spacing(6)

    # ── Training completion ───────────────────────────────────────────
    doc.add_section_title("Training Completion")
    try:
        site_officers = list(officers_set)
        if site_officers:
            # Get officer IDs for names
            placeholders = ",".join("?" * len(site_officers))
            oid_rows = conn.execute(
                f"SELECT officer_id, name FROM officers WHERE name IN ({placeholders})",
                site_officers,
            ).fetchall()
            oid_map = {r["officer_id"]: r["name"] for r in oid_rows}
            officer_ids = list(oid_map.keys())

            total_courses = conn.execute(
                "SELECT COUNT(*) as c FROM trn_courses WHERE status = 'Published'"
            ).fetchone()["c"]

            if officer_ids and total_courses > 0:
                id_ph = ",".join("?" * len(officer_ids))
                certs = conn.execute(
                    f"SELECT officer_id, COUNT(DISTINCT course_id) as cnt "
                    f"FROM trn_certificates WHERE officer_id IN ({id_ph}) "
                    f"AND status = 'Active' GROUP BY officer_id",
                    officer_ids,
                ).fetchall()
                cert_map = {r["officer_id"]: r["cnt"] for r in certs}
                training_rows = []
                for oid, name in oid_map.items():
                    completed = cert_map.get(oid, 0)
                    pct = completed / total_courses * 100 if total_courses > 0 else 0
                    training_rows.append([name, str(completed), str(total_courses), f"{pct:.0f}%"])
                doc.add_table(
                    ["Officer", "Completed", "Total Courses", "Completion %"],
                    training_rows,
                )
            else:
                doc.add_text("No courses or officers to report.", color="#6B7280")
        else:
            doc.add_text("No officers assigned — training N/A.", color="#6B7280")
    except Exception:
        doc.add_text("Training data unavailable.", color="#6B7280")

    conn.close()
    return doc.finish()


def generate_executive_summary(week_start: str, week_end: str) -> str:
    """
    Generate a hub-wide executive summary PDF for the given week.

    Includes KPIs across all modules: workforce, attendance, operations,
    uniforms, and training. Also includes a site-by-site breakdown table.

    Returns the filepath of the generated PDF.
    """
    conn = get_conn()
    filename = f"executive_summary_{week_start}_to_{week_end}.pdf"
    doc = PDFDocument(filename=filename, title="Executive Summary", orientation="landscape")
    doc.begin()

    doc.add_text(f"Period: {week_start}  to  {week_end}", size=10, color="#6B7280")
    doc.add_spacing(8)

    # ── Workforce KPIs ────────────────────────────────────────────────
    doc.add_section_title("Workforce")
    total_officers = 0
    total_sites = 0
    try:
        total_officers = conn.execute("SELECT COUNT(*) as c FROM officers").fetchone()["c"]
        total_sites = conn.execute("SELECT COUNT(*) as c FROM sites WHERE status = 'Active'").fetchone()["c"]
    except Exception:
        pass

    total_hours = 0.0
    ot_hours = 0.0
    try:
        rows = conn.execute(
            "SELECT officer_name, SUM(CAST(hours AS REAL)) as h "
            "FROM ops_assignments WHERE date BETWEEN ? AND ? "
            "GROUP BY officer_name",
            (week_start, week_end),
        ).fetchall()
        for r in rows:
            h = r["h"] or 0
            total_hours += h
            if h > 40:
                ot_hours += h - 40
    except Exception:
        pass

    doc.add_kpi_row([
        ("Total Officers", str(total_officers), "#374151"),
        ("Active Sites", str(total_sites), "#2563EB"),
        ("Hours Scheduled", f"{total_hours:.0f}", "#059669"),
        ("OT Hours", f"{ot_hours:.0f}", "#D97706"),
    ])
    doc.add_spacing(8)

    # ── Attendance ────────────────────────────────────────────────────
    doc.add_section_title("Attendance")
    infractions_week = 0
    at_risk = 0
    pending_reviews = 0
    try:
        infractions_week = conn.execute(
            "SELECT COUNT(*) as c FROM ats_infractions WHERE infraction_date BETWEEN ? AND ?",
            (week_start, week_end),
        ).fetchone()["c"]
        at_risk = conn.execute(
            "SELECT COUNT(*) as c FROM officers WHERE active_points >= 5"
        ).fetchone()["c"]
        pending_reviews = conn.execute(
            "SELECT COUNT(*) as c FROM ats_employment_reviews WHERE review_status = 'Pending'"
        ).fetchone()["c"]
    except Exception:
        pass

    doc.add_kpi_row([
        ("Infractions This Week", str(infractions_week), "#C8102E"),
        ("At-Risk Officers (5+ pts)", str(at_risk), "#D97706"),
        ("Pending Reviews", str(pending_reviews), "#374151"),
    ])
    doc.add_spacing(8)

    # ── Uniforms ──────────────────────────────────────────────────────
    doc.add_section_title("Uniforms")
    outstanding = 0
    low_stock = 0
    try:
        outstanding = conn.execute(
            "SELECT COUNT(*) as c FROM uni_issuances WHERE status = 'Outstanding'"
        ).fetchone()["c"]
        low_stock = conn.execute(
            "SELECT COUNT(*) as c FROM uni_catalog WHERE stock_qty <= reorder_point"
        ).fetchone()["c"]
    except Exception:
        pass

    compliance_rate = 0.0
    try:
        active_officers = conn.execute(
            "SELECT COUNT(*) as c FROM officers WHERE status = 'Active'"
        ).fetchone()["c"]
        total_req = conn.execute("SELECT COUNT(*) as c FROM uni_requirements").fetchone()["c"]
        expected = active_officers * total_req if total_req else 0
        if expected > 0:
            compliance_rate = outstanding / expected * 100
    except Exception:
        pass

    doc.add_kpi_row([
        ("Outstanding Items", str(outstanding), "#374151"),
        ("Low Stock Items", str(low_stock), "#C8102E"),
        ("Compliance Rate", f"{compliance_rate:.0f}%", "#059669" if compliance_rate >= 80 else "#D97706"),
    ])
    doc.add_spacing(8)

    # ── Training ──────────────────────────────────────────────────────
    doc.add_section_title("Training")
    avg_completion = 0.0
    certs_this_week = 0
    try:
        certs_this_week = conn.execute(
            "SELECT COUNT(*) as c FROM trn_certificates WHERE issued_date BETWEEN ? AND ?",
            (week_start, week_end),
        ).fetchone()["c"]

        total_courses = conn.execute(
            "SELECT COUNT(*) as c FROM trn_courses WHERE status = 'Published'"
        ).fetchone()["c"]
        active_officers = conn.execute(
            "SELECT COUNT(*) as c FROM officers WHERE status = 'Active'"
        ).fetchone()["c"]

        if total_courses > 0 and active_officers > 0:
            total_certs = conn.execute(
                "SELECT COUNT(*) as c FROM trn_certificates WHERE status = 'Active'"
            ).fetchone()["c"]
            avg_completion = total_certs / (total_courses * active_officers) * 100
    except Exception:
        pass

    doc.add_kpi_row([
        ("Avg Completion %", f"{avg_completion:.0f}%", "#059669" if avg_completion >= 70 else "#D97706"),
        ("Certificates This Week", str(certs_this_week), "#2563EB"),
    ])
    doc.add_spacing(10)

    # ── Site-by-site breakdown ────────────────────────────────────────
    doc.add_section_title("Site-by-Site Breakdown")
    site_rows = []
    try:
        sites = conn.execute(
            "SELECT name FROM sites WHERE status = 'Active' ORDER BY name"
        ).fetchall()
        for s in sites:
            sn = s["name"]
            # Hours
            hr = conn.execute(
                "SELECT SUM(CAST(hours AS REAL)) as h FROM ops_assignments "
                "WHERE site_name = ? AND date BETWEEN ? AND ?",
                (sn, week_start, week_end),
            ).fetchone()
            hours = hr["h"] or 0 if hr else 0

            # Officers
            ofc = conn.execute(
                "SELECT COUNT(DISTINCT officer_name) as c FROM ops_assignments "
                "WHERE site_name = ? AND date BETWEEN ? AND ?",
                (sn, week_start, week_end),
            ).fetchone()
            officers = ofc["c"] if ofc else 0

            # Infractions
            inf = conn.execute(
                "SELECT COUNT(*) as c FROM ats_infractions "
                "WHERE site = ? AND infraction_date BETWEEN ? AND ?",
                (sn, week_start, week_end),
            ).fetchone()
            infractions = inf["c"] if inf else 0

            site_rows.append([sn, str(officers), f"{hours:.0f}", str(infractions)])
    except Exception:
        pass

    if site_rows:
        doc.add_table(
            ["Site", "Officers", "Hours", "Infractions"], site_rows,
        )
    else:
        doc.add_text("No active sites found.", color="#6B7280")

    conn.close()
    return doc.finish()


def generate_all_site_reports(week_start: str = None, week_end: str = None) -> list:
    """
    Generate one PDF per active site plus an executive summary.

    If dates not provided, uses current week (Monday - Sunday).
    Returns a list of generated PDF filepaths.
    """
    ws, we = _week_bounds(week_start, week_end)
    filepaths = []

    conn = get_conn()
    try:
        sites = conn.execute(
            "SELECT name FROM sites WHERE status = 'Active' ORDER BY name"
        ).fetchall()
    except Exception:
        sites = []
    conn.close()

    for site in sites:
        try:
            fp = generate_site_report(site["name"], ws, we)
            filepaths.append(fp)
        except Exception:
            pass

    # Executive summary
    try:
        fp = generate_executive_summary(ws, we)
        filepaths.append(fp)
    except Exception:
        pass

    return filepaths
