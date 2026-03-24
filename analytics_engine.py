"""
Cerasus Hub — Analytics Engine
Cross-module data aggregation for trends, KPIs, and insights.
"""

from datetime import datetime, timedelta
from src.database import get_conn


def _date_range(days: int = 30):
    """Return (start_date, end_date) as YYYY-MM-DD strings for the given lookback."""
    end = datetime.now().date()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _safe_query(conn, sql, params=(), default=None):
    """Execute a query returning a single row, or default on any error."""
    try:
        row = conn.execute(sql, params).fetchone()
        return row
    except Exception:
        return default


def _safe_query_all(conn, sql, params=()):
    """Execute a query returning all rows, or [] on any error."""
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []


def get_hub_analytics(days: int = 30) -> dict:
    """
    Return a comprehensive analytics dictionary spanning all modules.

    Covers workforce, attendance, operations, uniforms, and training
    for the specified number of lookback days.
    """
    start_date, end_date = _date_range(days)
    conn = get_conn()

    # ── Workforce ─────────────────────────────────────────────────────
    total_officers = 0
    active = 0
    inactive = 0
    terminated = 0
    new_hires = 0
    turnover_rate = 0.0

    try:
        total_officers = (_safe_query(conn, "SELECT COUNT(*) as c FROM officers") or {"c": 0})["c"]
        active = (_safe_query(conn, "SELECT COUNT(*) as c FROM officers WHERE status = 'Active'") or {"c": 0})["c"]
        inactive = (_safe_query(conn, "SELECT COUNT(*) as c FROM officers WHERE status = 'Inactive'") or {"c": 0})["c"]
        terminated = (_safe_query(conn, "SELECT COUNT(*) as c FROM officers WHERE status = 'Terminated'") or {"c": 0})["c"]
        new_hires = (_safe_query(
            conn,
            "SELECT COUNT(*) as c FROM officers WHERE hire_date BETWEEN ? AND ?",
            (start_date, end_date),
        ) or {"c": 0})["c"]
        if total_officers > 0:
            term_period = (_safe_query(
                conn,
                "SELECT COUNT(*) as c FROM officers WHERE status = 'Terminated' AND updated_at >= ?",
                (start_date,),
            ) or {"c": 0})["c"]
            turnover_rate = term_period / total_officers
    except Exception:
        pass

    workforce = {
        "total_officers": total_officers,
        "active": active,
        "inactive": inactive,
        "terminated": terminated,
        "new_hires_period": new_hires,
        "turnover_rate": round(turnover_rate, 4),
    }

    # ── Attendance ────────────────────────────────────────────────────
    total_infractions = 0
    infractions_by_type = {}
    infractions_by_site = {}
    avg_points = 0.0
    at_risk_count = 0
    clean_slate_count = 0
    trend = []

    try:
        total_infractions = (_safe_query(
            conn,
            "SELECT COUNT(*) as c FROM ats_infractions WHERE infraction_date BETWEEN ? AND ?",
            (start_date, end_date),
        ) or {"c": 0})["c"]

        # By type
        rows = _safe_query_all(
            conn,
            "SELECT infraction_type, COUNT(*) as c FROM ats_infractions "
            "WHERE infraction_date BETWEEN ? AND ? GROUP BY infraction_type ORDER BY c DESC",
            (start_date, end_date),
        )
        infractions_by_type = {r["infraction_type"]: r["c"] for r in rows}

        # By site
        rows = _safe_query_all(
            conn,
            "SELECT site, COUNT(*) as c FROM ats_infractions "
            "WHERE infraction_date BETWEEN ? AND ? AND site != '' "
            "GROUP BY site ORDER BY c DESC",
            (start_date, end_date),
        )
        infractions_by_site = {r["site"]: r["c"] for r in rows}

        # Average points
        row = _safe_query(conn, "SELECT AVG(active_points) as a FROM officers WHERE status = 'Active'")
        avg_points = round(row["a"], 2) if row and row["a"] else 0.0

        at_risk_count = (_safe_query(
            conn, "SELECT COUNT(*) as c FROM officers WHERE active_points >= 5"
        ) or {"c": 0})["c"]

        clean_slate_count = (_safe_query(
            conn, "SELECT COUNT(*) as c FROM officers WHERE active_points = 0 AND status = 'Active'"
        ) or {"c": 0})["c"]

        # Weekly trend
        trend = _build_weekly_trend(
            conn,
            "SELECT COUNT(*) as c FROM ats_infractions "
            "WHERE infraction_date BETWEEN ? AND ?",
            weeks=min(days // 7, 12) or 4,
        )
    except Exception:
        pass

    attendance = {
        "total_infractions_period": total_infractions,
        "infractions_by_type": infractions_by_type,
        "infractions_by_site": infractions_by_site,
        "avg_points_per_officer": avg_points,
        "at_risk_count": at_risk_count,
        "clean_slate_count": clean_slate_count,
        "trend": trend,
    }

    # ── Operations ────────────────────────────────────────────────────
    total_assignments = 0
    total_hours_scheduled = 0.0
    coverage_rate = 0.0
    hours_by_site = {}
    assignments_by_type = {}

    try:
        total_assignments = (_safe_query(
            conn,
            "SELECT COUNT(*) as c FROM ops_assignments WHERE date BETWEEN ? AND ?",
            (start_date, end_date),
        ) or {"c": 0})["c"]

        row = _safe_query(
            conn,
            "SELECT SUM(CAST(hours AS REAL)) as h FROM ops_assignments WHERE date BETWEEN ? AND ?",
            (start_date, end_date),
        )
        total_hours_scheduled = round(row["h"], 1) if row and row["h"] else 0.0

        # Hours by site
        rows = _safe_query_all(
            conn,
            "SELECT site_name, SUM(CAST(hours AS REAL)) as h FROM ops_assignments "
            "WHERE date BETWEEN ? AND ? GROUP BY site_name ORDER BY h DESC",
            (start_date, end_date),
        )
        hours_by_site = {r["site_name"]: round(r["h"] or 0, 1) for r in rows}

        # Assignments by type
        rows = _safe_query_all(
            conn,
            "SELECT assignment_type, COUNT(*) as c FROM ops_assignments "
            "WHERE date BETWEEN ? AND ? GROUP BY assignment_type",
            (start_date, end_date),
        )
        assignments_by_type = {r["assignment_type"]: r["c"] for r in rows}

        # Coverage rate: assigned / total sites with requirements
        active_sites = (_safe_query(
            conn, "SELECT COUNT(*) as c FROM sites WHERE status = 'Active'"
        ) or {"c": 0})["c"]
        sites_with_coverage = len(hours_by_site)
        coverage_rate = round(sites_with_coverage / active_sites, 2) if active_sites > 0 else 0.0
    except Exception:
        pass

    operations = {
        "total_assignments_period": total_assignments,
        "total_hours_scheduled": total_hours_scheduled,
        "coverage_rate": coverage_rate,
        "hours_by_site": hours_by_site,
        "assignments_by_type": assignments_by_type,
    }

    # ── Uniforms ──────────────────────────────────────────────────────
    total_outstanding = 0
    issuances_period = 0
    returns_period = 0
    compliance_rate = 0.0
    total_inventory_value = 0.0
    low_stock_count = 0

    try:
        total_outstanding = (_safe_query(
            conn, "SELECT COUNT(*) as c FROM uni_issuances WHERE status = 'Outstanding'"
        ) or {"c": 0})["c"]

        issuances_period = (_safe_query(
            conn,
            "SELECT COUNT(*) as c FROM uni_issuances WHERE date_issued BETWEEN ? AND ?",
            (start_date, end_date),
        ) or {"c": 0})["c"]

        returns_period = (_safe_query(
            conn,
            "SELECT COUNT(*) as c FROM uni_issuances "
            "WHERE status = 'Returned' AND date_returned BETWEEN ? AND ?",
            (start_date, end_date),
        ) or {"c": 0})["c"]

        # Compliance rate
        active_count = (_safe_query(
            conn, "SELECT COUNT(*) as c FROM officers WHERE status = 'Active'"
        ) or {"c": 0})["c"]
        total_req = (_safe_query(
            conn, "SELECT COUNT(*) as c FROM uni_requirements"
        ) or {"c": 0})["c"]
        expected = active_count * total_req
        if expected > 0:
            compliance_rate = round(total_outstanding / expected * 100, 1)

        # Inventory value
        row = _safe_query(conn, "SELECT SUM(stock_qty * unit_cost) as v FROM uni_catalog")
        total_inventory_value = round(row["v"], 2) if row and row["v"] else 0.0

        low_stock_count = (_safe_query(
            conn, "SELECT COUNT(*) as c FROM uni_catalog WHERE stock_qty <= reorder_point"
        ) or {"c": 0})["c"]
    except Exception:
        pass

    uniforms = {
        "total_outstanding": total_outstanding,
        "issuances_period": issuances_period,
        "returns_period": returns_period,
        "compliance_rate": compliance_rate,
        "total_inventory_value": total_inventory_value,
        "low_stock_count": low_stock_count,
    }

    # ── Training ──────────────────────────────────────────────────────
    avg_completion_pct = 0.0
    certs_issued_period = 0
    courses_available = 0
    top_completers = []

    try:
        courses_available = (_safe_query(
            conn, "SELECT COUNT(*) as c FROM trn_courses WHERE status = 'Published'"
        ) or {"c": 0})["c"]

        certs_issued_period = (_safe_query(
            conn,
            "SELECT COUNT(*) as c FROM trn_certificates WHERE issued_date BETWEEN ? AND ?",
            (start_date, end_date),
        ) or {"c": 0})["c"]

        # Average completion %
        if courses_available > 0 and active > 0:
            total_active_certs = (_safe_query(
                conn, "SELECT COUNT(*) as c FROM trn_certificates WHERE status = 'Active'"
            ) or {"c": 0})["c"]
            avg_completion_pct = round(total_active_certs / (courses_available * active) * 100, 1)

        # Top completers
        rows = _safe_query_all(
            conn,
            "SELECT c.officer_id, o.name, COUNT(DISTINCT c.course_id) as cnt "
            "FROM trn_certificates c "
            "LEFT JOIN officers o ON c.officer_id = o.officer_id "
            "WHERE c.status = 'Active' "
            "GROUP BY c.officer_id ORDER BY cnt DESC LIMIT 5",
        )
        top_completers = [
            {"name": r["name"] or r["officer_id"], "courses": r["cnt"]}
            for r in rows
        ]
    except Exception:
        pass

    training = {
        "avg_completion_pct": avg_completion_pct,
        "certificates_issued_period": certs_issued_period,
        "courses_available": courses_available,
        "top_completers": top_completers,
    }

    conn.close()

    return {
        "period": {"start": start_date, "end": end_date, "days": days},
        "workforce": workforce,
        "attendance": attendance,
        "operations": operations,
        "uniforms": uniforms,
        "training": training,
    }


def _build_weekly_trend(conn, base_sql, weeks=12):
    """Build a list of weekly counts by running base_sql with date range params."""
    trend = []
    today = datetime.now().date()
    for i in range(weeks - 1, -1, -1):
        week_end = today - timedelta(days=i * 7)
        week_start = week_end - timedelta(days=6)
        row = _safe_query(conn, base_sql, (week_start.isoformat(), week_end.isoformat()))
        count = row["c"] if row and row["c"] else 0
        trend.append({"week": week_start.isoformat(), "count": count})
    return trend


def get_trend_data(metric: str, weeks: int = 12) -> list:
    """
    Return weekly trend data for charting.

    Supported metrics: "infractions", "assignments", "issuances", "hours"
    Returns: [{"week_start": "YYYY-MM-DD", "value": float}, ...]
    """
    conn = get_conn()
    results = []
    today = datetime.now().date()

    sql_map = {
        "infractions": "SELECT COUNT(*) as v FROM ats_infractions WHERE infraction_date BETWEEN ? AND ?",
        "assignments": "SELECT COUNT(*) as v FROM ops_assignments WHERE date BETWEEN ? AND ?",
        "issuances": "SELECT COUNT(*) as v FROM uni_issuances WHERE date_issued BETWEEN ? AND ?",
        "hours": "SELECT SUM(CAST(hours AS REAL)) as v FROM ops_assignments WHERE date BETWEEN ? AND ?",
    }

    sql = sql_map.get(metric)
    if not sql:
        conn.close()
        return []

    for i in range(weeks - 1, -1, -1):
        week_end = today - timedelta(days=i * 7)
        week_start = week_end - timedelta(days=6)
        row = _safe_query(conn, sql, (week_start.isoformat(), week_end.isoformat()))
        value = 0
        if row and row["v"] is not None:
            value = row["v"]
        results.append({
            "week_start": week_start.isoformat(),
            "value": round(float(value), 1) if value else 0,
        })

    conn.close()
    return results
