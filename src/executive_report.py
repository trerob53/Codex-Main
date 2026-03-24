"""
Cerasus Hub -- Monthly Operations Report
Generates a comprehensive monthly operations report as print-ready HTML,
rendered via QPrintPreviewDialog.
"""

from datetime import datetime, date, timedelta
from src.database import get_conn


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _safe_query(conn, sql, params=()):
    """Execute a query, returning [] on error (table may not exist)."""
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []


def _safe_scalar(conn, sql, params=(), default=0):
    """Execute a scalar query, returning default on error."""
    try:
        row = conn.execute(sql, params).fetchone()
        if row:
            val = row[0]
            return val if val is not None else default
        return default
    except Exception:
        return default


def _month_range(offset=0):
    """Return (first_day, last_day) as ISO strings for the month offset months ago."""
    today = date.today()
    month = today.month - offset
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()


def _trend_arrow(current, previous):
    if current > previous:
        return '<span style="color:#C8102E;">&#9650;</span>'  # up red
    elif current < previous:
        return '<span style="color:#059669;">&#9660;</span>'  # down green
    return '<span style="color:#6B7280;">&#9654;</span>'  # flat gray


# ---------------------------------------------------------------------------
# Wins / Improvement auto-generation
# ---------------------------------------------------------------------------

def _generate_wins(conn, inf_this, inf_last, da_this, avg_turnaround,
                   active_officers, total_sites, this_start, this_end):
    """Auto-generate operational wins from the data."""
    wins = []

    # W1: Zero termination-eligible officers
    at_ten = _safe_scalar(
        conn,
        "SELECT COUNT(*) FROM officers WHERE status='Active' AND active_points >= 10",
    )
    if at_ten == 0:
        wins.append(("Retention", "Zero termination-eligible officers this month"))

    # W2: Infraction reduction vs. last month
    if inf_last > 0 and inf_this < inf_last:
        pct = round((1 - inf_this / inf_last) * 100)
        wins.append(("Infractions", f"{pct}% reduction in infractions vs. last month"))

    # W3: DA turnaround
    if avg_turnaround is not None and avg_turnaround < 3:
        wins.append(("Disciplinary Actions",
                      f"All DAs delivered within {avg_turnaround:.1f} days average turnaround"))

    # W4: Clean-record officers
    clean = _safe_scalar(
        conn,
        "SELECT COUNT(*) FROM officers WHERE status='Active' AND (active_points = 0 OR active_points IS NULL)",
    )
    if clean > 0:
        wins.append(("Officer Performance",
                      f"{clean} officer{'s' if clean != 1 else ''} maintained clean record"))

    # W5: Full site coverage
    uncovered = _safe_scalar(
        conn,
        """SELECT COUNT(*) FROM sites s WHERE s.status='Active'
           AND (SELECT COUNT(*) FROM officers o WHERE o.site = s.name AND o.status='Active') = 0""",
    )
    if uncovered == 0 and total_sites > 0:
        wins.append(("Coverage", "Full site coverage maintained"))

    # W6: Zero infractions month
    if inf_this == 0:
        wins.append(("Infractions", "Zero infractions recorded this month"))

    return wins


def _generate_improvements(conn, inf_this, inf_last, near_term, stale_das,
                           inf_by_type, expiring_points, this_start, this_end):
    """Auto-generate areas for improvement from the data."""
    items = []

    # L1: Infraction increase
    if inf_last > 0 and inf_this > inf_last:
        pct = round((inf_this / inf_last - 1) * 100)
        items.append(("Infractions", f"Infraction increase of {pct}% vs. last month"))
    elif inf_last == 0 and inf_this > 0:
        items.append(("Infractions", f"{inf_this} infraction{'s' if inf_this != 1 else ''} recorded (none last month)"))

    # L2: Officers at 8+ points
    at_eight = _safe_scalar(
        conn,
        "SELECT COUNT(*) FROM officers WHERE status='Active' AND active_points >= 8",
    )
    if at_eight > 0:
        items.append(("Employment Review",
                       f"{at_eight} officer{'s' if at_eight != 1 else ''} at 8+ points requiring employment review"))

    # L3: Stale DAs
    if stale_das:
        n = len(stale_das)
        items.append(("Pending DAs",
                       f"{n} DA{'s' if n != 1 else ''} pending review for 3+ days"))

    # L4: Top infraction type
    if inf_by_type:
        top = inf_by_type[0]
        itype = (top.get("infraction_type") or "Unknown").replace("_", " ").title()
        items.append(("Top Infraction Type",
                       f"Top infraction type: {itype} ({top['cnt']} occurrence{'s' if top['cnt'] != 1 else ''})"))

    # L5: Expiring points
    if expiring_points:
        total_pts = sum(p.get("points_assigned", 0) for p in expiring_points)
        items.append(("Point Expirations",
                       f"{total_pts} point{'s' if total_pts != 1 else ''} expiring in next 30 days"))

    return items


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def generate_executive_summary(username: str = "") -> str:
    """Generate HTML for the monthly operations report."""
    conn = get_conn()
    now = datetime.now()
    report_date = now.strftime("%B %d, %Y at %I:%M %p")
    this_start, this_end = _month_range(0)
    last_start, last_end = _month_range(1)

    today = date.today()
    first_of_month = today.replace(day=1)
    last_of_month_date = (date(today.year, today.month + 1, 1) if today.month < 12
                          else date(today.year + 1, 1, 1)) - timedelta(days=1)
    month_label = today.strftime("%B %Y")
    period_start = first_of_month.strftime("%B %#d, %Y")
    period_end = last_of_month_date.strftime("%B %#d, %Y")
    prev_month_date = first_of_month - timedelta(days=1)
    prev_month_label = prev_month_date.strftime("%B %Y")
    next_month_date = last_of_month_date + timedelta(days=1)
    next_month_label = next_month_date.strftime("%B %Y")

    # ── 1. Company Overview ───────────────────────────────────────────
    active_officers = _safe_scalar(conn, "SELECT COUNT(*) FROM officers WHERE status='Active'")
    total_sites = _safe_scalar(conn, "SELECT COUNT(*) FROM sites WHERE status='Active'")

    # ── 2. Attendance Summary ─────────────────────────────────────────
    inf_this = _safe_scalar(
        conn,
        "SELECT COUNT(*) FROM ats_infractions WHERE infraction_date BETWEEN ? AND ?",
        (this_start, this_end),
    )
    inf_last = _safe_scalar(
        conn,
        "SELECT COUNT(*) FROM ats_infractions WHERE infraction_date BETWEEN ? AND ?",
        (last_start, last_end),
    )

    # Infraction breakdown by type
    inf_by_type = _safe_query(
        conn,
        """SELECT infraction_type, COUNT(*) as cnt FROM ats_infractions
           WHERE infraction_date BETWEEN ? AND ?
           GROUP BY infraction_type ORDER BY cnt DESC""",
        (this_start, this_end),
    )

    # ── 3. Disciplinary Actions ───────────────────────────────────────
    da_this = _safe_scalar(
        conn,
        "SELECT COUNT(*) FROM da_records WHERE created_at BETWEEN ? AND ?",
        (this_start, this_end + "T23:59:59"),
    )
    da_last = _safe_scalar(
        conn,
        "SELECT COUNT(*) FROM da_records WHERE created_at BETWEEN ? AND ?",
        (last_start, last_end + "T23:59:59"),
    )

    # Average turnaround (created_at -> delivered_at) for delivered DAs
    avg_turnaround = _safe_scalar(
        conn,
        """SELECT AVG(julianday(delivered_at) - julianday(created_at))
           FROM da_records WHERE delivered_at != '' AND delivered_at IS NOT NULL
           AND created_at != '' AND created_at IS NOT NULL""",
        default=None,
    )

    # ── 4. Site Performance ───────────────────────────────────────────
    site_perf = _safe_query(
        conn,
        """SELECT
              s.name as site_name,
              (SELECT COUNT(*) FROM officers o WHERE o.site = s.name AND o.status='Active') as headcount,
              (SELECT COUNT(*) FROM ats_infractions i
               JOIN officers o2 ON o2.officer_id = i.employee_id
               WHERE o2.site = s.name
               AND i.infraction_date BETWEEN ? AND ?) as inf_count,
              (SELECT ROUND(AVG(o3.active_points), 1) FROM officers o3 WHERE o3.site = s.name AND o3.status='Active') as avg_pts,
              (SELECT COUNT(*) FROM da_records d WHERE d.site = s.name AND d.status NOT IN ('completed','signed')) as open_das
           FROM sites s WHERE s.status='Active'
           ORDER BY inf_count DESC""",
        (this_start, this_end),
    )

    # ── 5. Alerts & Action Items ──────────────────────────────────────
    near_term = _safe_query(
        conn,
        """SELECT name, employee_id, active_points, discipline_level, site
           FROM officers WHERE status='Active' AND active_points >= 8
           ORDER BY active_points DESC""",
    )

    three_days_ago = (date.today() - timedelta(days=3)).isoformat()
    stale_das = _safe_query(
        conn,
        """SELECT da_id, employee_name, discipline_level, status, created_at, site
           FROM da_records WHERE status IN ('draft','pending')
           AND created_at != '' AND created_at <= ?
           ORDER BY created_at""",
        (three_days_ago + "T23:59:59",),
    )

    expiring_docs = []
    try:
        from src.document_vault import get_expiring_documents
        expiring_docs = get_expiring_documents(days=30)
    except Exception:
        pass

    cutoff_start = date.today().isoformat()
    cutoff_end = (date.today() + timedelta(days=30)).isoformat()
    expiring_points = _safe_query(
        conn,
        """SELECT i.employee_id, o.name, o.employee_id as emp_id, i.points_assigned,
                  i.point_expiry_date, i.infraction_type
           FROM ats_infractions i
           JOIN officers o ON o.officer_id = i.employee_id
           WHERE i.points_active = 1 AND i.point_expiry_date != ''
           AND i.point_expiry_date BETWEEN ? AND ?
           ORDER BY i.point_expiry_date""",
        (cutoff_start, cutoff_end),
    )

    # Top 5 by active points
    top_officers = _safe_query(
        conn,
        """SELECT name, employee_id, active_points, discipline_level, site
           FROM officers WHERE status='Active' AND active_points > 0
           ORDER BY active_points DESC LIMIT 5""",
    )

    # ── 6. Training Data ─────────────────────────────────────────────
    training_completed = _safe_query(
        conn,
        """SELECT course_name, delivery_method FROM trn_progress
           WHERE completed_at BETWEEN ? AND ?
           GROUP BY course_name, delivery_method
           ORDER BY course_name""",
        (last_start, last_end),
    )

    training_planned = _safe_query(
        conn,
        """SELECT course_name, delivery_method FROM trn_progress
           WHERE status IN ('in_progress', 'not_started', 'enrolled')
           GROUP BY course_name, delivery_method
           ORDER BY course_name""",
    )

    # ── Generate Wins & Improvements ─────────────────────────────────
    wins = _generate_wins(conn, inf_this, inf_last, da_this, avg_turnaround,
                          active_officers, total_sites, this_start, this_end)
    improvements = _generate_improvements(conn, inf_this, inf_last, near_term,
                                          stale_das, inf_by_type, expiring_points,
                                          this_start, this_end)

    conn.close()

    # ── Build HTML ────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html>
<head>
<style>
@page {{ margin: 0.5in 0.6in; size: letter portrait; }}
body {{
    font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
    font-size: 10px;
    color: #1F2937;
    margin: 0;
    padding: 0;
    line-height: 1.45;
}}
h1 {{
    font-size: 15px;
    font-weight: 700;
    color: #1A1A2E;
    margin: 0 0 2px 0;
    letter-spacing: 2.5px;
    text-transform: uppercase;
}}
h2 {{
    font-size: 11px;
    font-weight: 700;
    color: #1A1A2E;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    border-bottom: 2px solid #1A1A2E;
    padding-bottom: 3px;
    margin: 16px 0 8px 0;
}}
.header {{
    text-align: center;
    border-bottom: 3px solid #1A1A2E;
    padding-bottom: 10px;
    margin-bottom: 12px;
}}
.header .subtitle {{
    font-size: 9px;
    color: #6B7280;
    margin-top: 4px;
    letter-spacing: 0.5px;
}}

/* KPI Cards */
.kpi-row {{
    display: flex;
    gap: 10px;
    margin-bottom: 12px;
}}
.kpi-box {{
    border: 1px solid #D1D5DB;
    border-top: 3px solid #1A1A2E;
    border-radius: 3px;
    padding: 10px 14px;
    text-align: center;
    flex: 1;
    background: #FAFBFC;
}}
.kpi-box .value {{
    font-size: 24px;
    font-weight: 700;
    color: #1A1A2E;
    line-height: 1.2;
}}
.kpi-box .label {{
    font-size: 8px;
    color: #6B7280;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 2px;
}}

/* Tables */
table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 8px;
    font-size: 9.5px;
}}
th {{
    background: #1A1A2E;
    color: #FFFFFF;
    padding: 5px 8px;
    text-align: left;
    font-weight: 600;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
td {{
    padding: 4px 8px;
    border-bottom: 1px solid #E5E7EB;
}}
tr:nth-child(even) {{
    background: #F9FAFB;
}}

/* Win / Loss Badges */
.badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 9px;
    font-weight: 700;
    color: #FFFFFF;
    text-align: center;
    min-width: 24px;
}}
.badge-win {{
    background: #1A1A2E;
}}
.badge-loss {{
    background: #991B1B;
}}

/* Alert Boxes */
.alert-box {{
    border-left: 4px solid #FCA5A5;
    background: #FEF2F2;
    border-radius: 3px;
    padding: 6px 10px;
    margin-bottom: 6px;
    font-size: 9.5px;
}}
.alert-box.warning {{
    border-left-color: #F59E0B;
    background: #FFFBEB;
}}
.alert-box.info {{
    border-left-color: #3B82F6;
    background: #EFF6FF;
}}
.alert-box .alert-title {{
    font-weight: 700;
    font-size: 9.5px;
    margin-bottom: 2px;
}}

/* Footer */
.footer {{
    text-align: center;
    font-size: 8.5px;
    color: #9CA3AF;
    border-top: 1px solid #D1D5DB;
    padding-top: 8px;
    margin-top: 18px;
    line-height: 1.6;
}}
.footer .name-line {{
    font-size: 9px;
    color: #4B5563;
    font-weight: 600;
}}

.none-msg {{
    color: #9CA3AF;
    font-style: italic;
    font-size: 9.5px;
    margin: 4px 0;
}}
</style>
</head>
<body>

<!-- ================================================================ -->
<!--  HEADER                                                          -->
<!-- ================================================================ -->
<div class="header">
    <h1>CERASUS SECURITY &mdash; MONTHLY OPERATIONS REPORT</h1>
    <div class="subtitle">REPORTING PERIOD: {period_start} &ndash; {period_end} &nbsp;&nbsp;|&nbsp;&nbsp; PREPARED BY: Cerasus LLC</div>
</div>

<!-- ================================================================ -->
<!--  SECTION 1: EXECUTIVE OVERVIEW                                   -->
<!-- ================================================================ -->
<h2>EXECUTIVE OVERVIEW</h2>
<div class="kpi-row">
    <div class="kpi-box">
        <div class="value">{active_officers}</div>
        <div class="label">Active Officers</div>
    </div>
    <div class="kpi-box">
        <div class="value">{total_sites}</div>
        <div class="label">Active Sites</div>
    </div>
    <div class="kpi-box">
        <div class="value">{inf_this}</div>
        <div class="label">Total Infractions This Month</div>
    </div>
    <div class="kpi-box">
        <div class="value">{da_this}</div>
        <div class="label">DAs This Month</div>
    </div>
</div>

<!-- ================================================================ -->
<!--  SECTION 2: OPERATIONAL WINS                                     -->
<!-- ================================================================ -->
<h2>OPERATIONAL WINS</h2>
"""

    # Build wins table
    if wins:
        html += """<table>
<tr><th style="width:50px; text-align:center;">#</th><th style="width:160px;">Win Category</th><th>Details</th></tr>
"""
        for i, (category, detail) in enumerate(wins, 1):
            html += f'<tr><td style="text-align:center;"><span class="badge badge-win">W{i}</span></td>'
            html += f'<td style="font-weight:600;">{category}</td><td>{detail}</td></tr>\n'
        html += '</table>\n'
    else:
        html += '<p class="none-msg">No operational wins auto-detected for this period.</p>\n'

    # ── Section 3: Areas for Improvement ─────────────────────────────
    html += '<h2>AREAS FOR IMPROVEMENT</h2>\n'

    if improvements:
        html += """<table>
<tr><th style="width:50px; text-align:center;">#</th><th style="width:160px;">Area</th><th>Details</th></tr>
"""
        for i, (category, detail) in enumerate(improvements, 1):
            html += f'<tr><td style="text-align:center;"><span class="badge badge-loss">L{i}</span></td>'
            html += f'<td style="font-weight:600;">{category}</td><td>{detail}</td></tr>\n'
        html += '</table>\n'
    else:
        html += '<p class="none-msg">No areas for improvement auto-detected for this period.</p>\n'

    # ── Section 4: Site Performance ──────────────────────────────────
    html += '<h2>SITE PERFORMANCE</h2>\n'

    if site_perf:
        html += """<table>
<tr><th>Site</th><th style="text-align:right;">Headcount</th>
<th style="text-align:right;">Infractions</th><th style="text-align:right;">Avg Points</th>
<th style="text-align:right;">Open DAs</th></tr>
"""
        for s in site_perf:
            html += (f'<tr><td>{s["site_name"]}</td>'
                     f'<td style="text-align:right;">{s.get("headcount", 0)}</td>'
                     f'<td style="text-align:right;">{s.get("inf_count", 0)}</td>'
                     f'<td style="text-align:right;">{s.get("avg_pts", 0) or 0}</td>'
                     f'<td style="text-align:right;">{s.get("open_das", 0)}</td></tr>\n')
        html += '</table>\n'
    else:
        html += '<p class="none-msg">No site performance data available.</p>\n'

    # ── Section 5: Training Completed ────────────────────────────────
    html += f'<h2>TRAINING COMPLETED &mdash; {prev_month_label.upper()}</h2>\n'

    if training_completed:
        html += """<table>
<tr><th>Topic / Module</th><th>Delivery Method</th></tr>
"""
        for t in training_completed:
            course = t.get("course_name", "Unknown")
            method = (t.get("delivery_method") or "N/A").replace("_", " ").title()
            html += f'<tr><td>{course}</td><td>{method}</td></tr>\n'
        html += '</table>\n'
    else:
        html += """<table>
<tr><th>Topic / Module</th><th>Delivery Method</th></tr>
<tr><td colspan="2" class="none-msg" style="text-align:center; padding:10px;">[No training data recorded for this period]</td></tr>
</table>
"""

    # ── Section 6: Training Planned ──────────────────────────────────
    html += f'<h2>TRAINING PLANNED &mdash; {next_month_label.upper()}</h2>\n'

    if training_planned:
        html += """<table>
<tr><th>Topic / Module</th><th>Delivery Method</th></tr>
"""
        for t in training_planned:
            course = t.get("course_name", "Unknown")
            method = (t.get("delivery_method") or "N/A").replace("_", " ").title()
            html += f'<tr><td>{course}</td><td>{method}</td></tr>\n'
        html += '</table>\n'
    else:
        html += """<table>
<tr><th>Topic / Module</th><th>Delivery Method</th></tr>
<tr><td colspan="2" class="none-msg" style="text-align:center; padding:10px;">[No upcoming training scheduled]</td></tr>
</table>
"""

    # ── Section 7: Alerts & Action Items ─────────────────────────────
    html += '<h2>ALERTS &amp; ACTION ITEMS</h2>\n'

    if near_term:
        html += '<div class="alert-box">\n'
        html += f'<div class="alert-title">Officers at 8+ Active Points ({len(near_term)})</div>\n'
        html += '<table style="margin:4px 0 0 0;"><tr><th>Officer</th><th>ID</th><th>Site</th><th style="text-align:right;">Points</th><th>Level</th></tr>\n'
        for o in near_term:
            html += (f'<tr><td>{o["name"]}</td><td>{o.get("employee_id", "")}</td>'
                     f'<td>{o.get("site", "")}</td>'
                     f'<td style="text-align:right;">{o["active_points"]}</td>'
                     f'<td>{o.get("discipline_level", "")}</td></tr>\n')
        html += '</table></div>\n'
    else:
        html += '<div class="alert-box info">No officers at or above the 8-point threshold.</div>\n'

    if stale_das:
        html += '<div class="alert-box warning">\n'
        html += f'<div class="alert-title">DAs Pending Review for 3+ Days ({len(stale_das)})</div>\n'
        html += '<table style="margin:4px 0 0 0;"><tr><th>DA ID</th><th>Employee</th><th>Site</th><th>Level</th><th>Status</th><th>Created</th></tr>\n'
        for d in stale_das:
            created = (d.get("created_at") or "")[:10]
            html += (f'<tr><td>{d.get("da_id", "")[:12]}</td><td>{d.get("employee_name", "")}</td>'
                     f'<td>{d.get("site", "")}</td>'
                     f'<td>{d.get("discipline_level", "")}</td><td>{(d.get("status", "")).title()}</td>'
                     f'<td>{created}</td></tr>\n')
        html += '</table></div>\n'
    else:
        html += '<div class="alert-box info">No stale DAs pending review.</div>\n'

    if expiring_docs:
        html += '<div class="alert-box warning">\n'
        html += f'<div class="alert-title">Documents Expiring Within 30 Days ({len(expiring_docs)})</div>\n'
        html += '<table style="margin:4px 0 0 0;"><tr><th>Officer</th><th>Document</th><th>Type</th><th>Expires</th><th style="text-align:right;">Days Left</th></tr>\n'
        for d in expiring_docs:
            html += (f'<tr><td>{d.get("officer_name", "")}</td><td>{d.get("original_filename", "")}</td>'
                     f'<td>{d.get("doc_type", "")}</td><td>{d.get("expiry_date", "")}</td>'
                     f'<td style="text-align:right;">{d.get("_days_remaining", "")}</td></tr>\n')
        html += '</table></div>\n'

    if expiring_points:
        html += '<div class="alert-box warning">\n'
        html += f'<div class="alert-title">Points Expiring in Next 30 Days ({len(expiring_points)})</div>\n'
        html += '<table style="margin:4px 0 0 0;"><tr><th>Officer</th><th>ID</th><th>Type</th><th style="text-align:right;">Points</th><th>Expires</th></tr>\n'
        for p in expiring_points:
            itype = (p.get("infraction_type") or "").replace("_", " ").title()
            html += (f'<tr><td>{p.get("name", "")}</td><td>{p.get("emp_id", "")}</td>'
                     f'<td>{itype}</td>'
                     f'<td style="text-align:right;">{p.get("points_assigned", 0)}</td>'
                     f'<td>{p.get("point_expiry_date", "")}</td></tr>\n')
        html += '</table></div>\n'
    elif not near_term and not stale_das and not expiring_docs:
        html += '<div class="alert-box info">No active alerts or action items at this time.</div>\n'

    # ── Footer ────────────────────────────────────────────────────────
    html += f"""
<!-- ================================================================ -->
<!--  FOOTER                                                          -->
<!-- ================================================================ -->
<div class="footer">
    <div class="name-line">Submitted by: Tremaine Robinson, AVP of Operations &mdash; Cerasus LLC</div>
    Contact: tremaine@cerasusllc.com &nbsp;|&nbsp; (555) 000-0000<br/>
    Generated by CerasusHub on {now.strftime("%B %d, %Y at %I:%M %p")} &mdash; CONFIDENTIAL
</div>

</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Print preview dialog
# ---------------------------------------------------------------------------

def show_executive_report(parent_widget, username: str = ""):
    """Open the executive summary in a print preview dialog."""
    from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
    from PySide6.QtGui import QTextDocument, QPageLayout
    from PySide6.QtCore import QMarginsF

    html = generate_executive_summary(username)

    doc = QTextDocument()
    doc.setHtml(html)

    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageOrientation(QPageLayout.Orientation.Portrait)
    printer.setPageMargins(QMarginsF(12, 12, 12, 12))

    preview = QPrintPreviewDialog(printer, parent_widget)
    preview.setWindowTitle("Monthly Operations Report \u2014 Cerasus Hub")
    preview.resize(900, 700)
    preview.paintRequested.connect(lambda p: doc.print_(p))
    preview.exec()
