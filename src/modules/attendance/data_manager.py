"""
Cerasus Hub -- Attendance Module: Data Manager
SQLite-backed CRUD for ats_infractions and ats_employment_reviews.
Officers and sites are delegated to the shared data layer.
"""

import csv
import io
import secrets
from datetime import datetime, timezone

from src.database import get_conn

# ── Shared Data Delegates (Officers & Sites) ─────────────────────────
from src.shared_data import (
    get_all_officers,
    get_officer,
    search_officers,
    create_officer,
    update_officer,
    delete_officer,
    get_active_officers,
    get_officer_names,
    get_all_sites,
    get_site,
    create_site,
    update_site,
    delete_site,
    get_site_names,
)

from src.modules.attendance.policy_engine import (
    calculate_active_points,
    determine_discipline_level,
    should_trigger_review,
    get_point_expiry_date,
    count_emergency_exemptions,
    INFRACTION_TYPES,
    DISCIPLINE_LABELS,
)


# ── Helpers ───────────────────────────────────────────────────────────

def _gen_id() -> str:
    return secrets.token_hex(4)


# ── Settings Helpers ─────────────────────────────────────────────────

def get_setting(key: str) -> str | None:
    """Read a value from the shared settings table."""
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def save_setting(key: str, value: str) -> None:
    """Write a value to the shared settings table."""
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, _now()),
    )
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Infractions CRUD ──────────────────────────────────────────────────

def get_all_infractions() -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT i.*,
                  COALESCE(o.name, m.officer_name, i.employee_id) as officer_name
           FROM ats_infractions i
           LEFT JOIN officers o ON i.employee_id = o.officer_id OR i.employee_id = o.employee_id
           LEFT JOIN ats_id_mapping m ON i.employee_id = m.ats_id
           ORDER BY i.infraction_date DESC, i.id DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_infractions_for_employee(employee_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ats_infractions WHERE employee_id = ? ORDER BY infraction_date DESC, id DESC",
        (employee_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_infraction(fields: dict, entered_by: str = "") -> int:
    """Create an infraction. Returns the new infraction id."""
    now = _now()

    # Determine points from type if not explicitly set
    inf_type = fields.get("infraction_type", "")
    type_info = INFRACTION_TYPES.get(inf_type, {})
    points = fields.get("points_assigned")
    if points is None:
        points = type_info.get("points", 0)

    infraction_date = fields.get("infraction_date", "")
    expiry_date = fields.get("point_expiry_date") or get_point_expiry_date(infraction_date)

    # Determine if emergency exemption
    is_emergency = 1 if inf_type in ("emergency_exemption_approved", "emergency_exemption_denied") else 0

    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO ats_infractions
           (employee_id, infraction_type, infraction_date, points_assigned,
            description, site, entered_by, discipline_triggered,
            is_emergency_exemption, exemption_approved, documentation_provided,
            point_expiry_date, points_active, edited, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)""",
        (
            fields.get("employee_id", ""),
            inf_type,
            infraction_date,
            float(points),
            fields.get("description", ""),
            fields.get("site", ""),
            entered_by,
            fields.get("discipline_triggered", type_info.get("auto_discipline", "")),
            is_emergency,
            1 if fields.get("exemption_approved") else 0,
            1 if fields.get("documentation_provided") else 0,
            expiry_date,
            1,
            now,
            now,
        ),
    )
    infraction_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Update officer's points and discipline level
    _refresh_officer_discipline(fields.get("employee_id", ""))

    return infraction_id


def update_infraction(infraction_id: int, fields: dict) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT * FROM ats_infractions WHERE id = ?", (infraction_id,)).fetchone()
    if not row:
        conn.close()
        return False

    allowed = [
        "employee_id", "infraction_type", "infraction_date", "points_assigned",
        "description", "site", "discipline_triggered",
        "is_emergency_exemption", "exemption_approved", "documentation_provided",
        "point_expiry_date", "points_active",
    ]
    updates = []
    params = []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])

    if updates:
        updates.append("edited = 1")
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(infraction_id)
        conn.execute(
            f"UPDATE ats_infractions SET {', '.join(updates)} WHERE id = ?", params
        )
        conn.commit()

    emp_id = fields.get("employee_id") or dict(row).get("employee_id", "")
    conn.close()

    # Refresh officer discipline
    if emp_id:
        _refresh_officer_discipline(emp_id)

    return True


def delete_infraction(infraction_id: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT employee_id FROM ats_infractions WHERE id = ?", (infraction_id,)).fetchone()
    emp_id = row["employee_id"] if row else ""

    cur = conn.execute("DELETE FROM ats_infractions WHERE id = ?", (infraction_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()

    if emp_id:
        _refresh_officer_discipline(emp_id)

    return affected > 0


# ── Employment Reviews CRUD ───────────────────────────────────────────

def get_all_reviews() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ats_employment_reviews ORDER BY triggered_date DESC, id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_reviews_for_employee(employee_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ats_employment_reviews WHERE employee_id = ? ORDER BY triggered_date DESC",
        (employee_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_review(fields: dict) -> int:
    """Create an employment review. Returns review id."""
    now = _now()
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO ats_employment_reviews
           (employee_id, triggered_date, points_at_trigger, review_status,
            reviewed_by, review_date, outcome, reviewer_notes,
            supervisor_comments, points_after_outcome, locked,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)""",
        (
            fields.get("employee_id", ""),
            fields.get("triggered_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            float(fields.get("points_at_trigger", 0)),
            fields.get("review_status", "Pending"),
            fields.get("reviewed_by", ""),
            fields.get("review_date", ""),
            fields.get("outcome", ""),
            fields.get("reviewer_notes", ""),
            fields.get("supervisor_comments", ""),
            float(fields.get("points_after_outcome", 0)),
            now,
            now,
        ),
    )
    review_id = cur.lastrowid
    conn.commit()
    conn.close()
    return review_id


def update_review(review_id: int, fields: dict) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT * FROM ats_employment_reviews WHERE id = ?", (review_id,)).fetchone()
    if not row:
        conn.close()
        return False

    existing = dict(row)
    if existing.get("locked"):
        conn.close()
        return False

    # Default points_after_outcome to 6.0 for retain outcomes if caller didn't set it.
    # This matches the DA threshold logic (retain = Final Warning, reset to 6).
    retained_outcomes = {
        "retain", "retain_reduce", "Retained", "retained",
        "probation", "Probation", "Final Warning", "final_warning",
    }
    if fields.get("outcome") in retained_outcomes and "points_after_outcome" not in fields:
        fields["points_after_outcome"] = 6.0

    allowed = [
        "review_status", "reviewed_by", "review_date", "outcome",
        "reviewer_notes", "supervisor_comments", "points_after_outcome",
    ]
    updates = []
    params = []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])

    if updates:
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(review_id)
        conn.execute(
            f"UPDATE ats_employment_reviews SET {', '.join(updates)} WHERE id = ?", params
        )
        conn.commit()

    emp_id = existing.get("employee_id", "")
    conn.close()

    # Refresh officer discipline so retain/reset logic takes effect immediately
    if emp_id:
        _refresh_officer_discipline(emp_id)

    return True


def lock_review(review_id: int) -> bool:
    conn = get_conn()
    conn.execute(
        "UPDATE ats_employment_reviews SET locked = 1, updated_at = ? WHERE id = ?",
        (_now(), review_id),
    )
    conn.commit()
    conn.close()
    return True


# ── Dashboard Summary ─────────────────────────────────────────────────

def get_dashboard_summary() -> dict:
    """Aggregate counts for the attendance dashboard."""
    conn = get_conn()

    # Active officers
    officer_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM officers WHERE status = 'Active'"
    ).fetchone()["cnt"]

    # At-risk officers (5+ points)
    at_risk = conn.execute(
        "SELECT COUNT(*) as cnt FROM officers WHERE status = 'Active' AND active_points >= 5"
    ).fetchone()["cnt"]

    # Pending reviews
    pending_reviews = conn.execute(
        "SELECT COUNT(*) as cnt FROM ats_employment_reviews WHERE review_status = 'Pending'"
    ).fetchone()["cnt"]

    # Termination eligible
    termination = conn.execute(
        "SELECT COUNT(*) as cnt FROM officers WHERE status = 'Active' AND active_points >= 10"
    ).fetchone()["cnt"]

    # Active infractions count
    active_infractions = conn.execute(
        "SELECT COUNT(*) as cnt FROM ats_infractions WHERE points_active = 1"
    ).fetchone()["cnt"]

    # Recent infractions (last 10) — join with officers + ATS mapping for name
    recent_rows = conn.execute(
        """SELECT i.*,
                  COALESCE(o.name, m.officer_name, i.employee_id) as officer_name,
                  COALESCE(o.site, i.site) as resolved_site
           FROM ats_infractions i
           LEFT JOIN officers o ON i.employee_id = o.officer_id OR i.employee_id = o.employee_id
           LEFT JOIN ats_id_mapping m ON i.employee_id = m.ats_id
           ORDER BY i.infraction_date DESC, i.id DESC LIMIT 10"""
    ).fetchall()
    recent_infractions = [dict(r) for r in recent_rows]

    # Top at-risk officers
    top_risk_rows = conn.execute(
        """SELECT officer_id, name, employee_id, active_points, discipline_level, site
           FROM officers WHERE status = 'Active' AND active_points > 0
           ORDER BY active_points DESC LIMIT 5"""
    ).fetchall()
    top_at_risk = [dict(r) for r in top_risk_rows]

    # Infraction breakdown by category
    cat_rows = conn.execute(
        """SELECT infraction_type, COUNT(*) as cnt
           FROM ats_infractions WHERE points_active = 1
           GROUP BY infraction_type ORDER BY cnt DESC"""
    ).fetchall()
    infraction_breakdown = {r["infraction_type"]: r["cnt"] for r in cat_rows}

    # Infractions this month
    now = datetime.now(timezone.utc)
    month_start = now.strftime("%Y-%m-01")
    infractions_this_month = conn.execute(
        "SELECT COUNT(*) as cnt FROM ats_infractions WHERE infraction_date >= ?",
        (month_start,)
    ).fetchone()["cnt"]

    conn.close()

    return {
        "active_officers": officer_count,
        "at_risk": at_risk,
        "pending_reviews": pending_reviews,
        "termination_eligible": termination,
        "active_infractions": active_infractions,
        "infractions_this_month": infractions_this_month,
        "recent_infractions": recent_infractions,
        "top_at_risk": top_at_risk,
        "infraction_breakdown": infraction_breakdown,
    }


def get_infractions_this_month() -> int:
    """Count infractions logged in the current calendar month."""
    conn = get_conn()
    now = datetime.now(timezone.utc)
    month_start = now.strftime("%Y-%m-01")
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM ats_infractions WHERE infraction_date >= ?",
        (month_start,)
    ).fetchone()["cnt"]
    conn.close()
    return count


def get_monthly_infraction_counts(months: int = 6) -> list:
    """Return infraction counts grouped by month for the last N months.
    Returns [(label, count), ...] sorted chronologically.
    """
    conn = get_conn()
    rows = conn.execute(
        """SELECT strftime('%Y-%m', infraction_date) AS month, COUNT(*) AS cnt
           FROM ats_infractions
           WHERE infraction_date >= date('now', ?)
           GROUP BY month ORDER BY month ASC""",
        (f'-{months} months',),
    ).fetchall()
    conn.close()

    import calendar
    result = []
    for r in rows:
        ym = r["month"]  # e.g. "2026-01"
        try:
            year, mon = ym.split("-")
            label = f"{calendar.month_abbr[int(mon)]} {year[-2:]}"
        except (ValueError, IndexError):
            label = ym
        result.append((label, r["cnt"]))
    return result


def get_current_month_by_type() -> list:
    """Return infraction counts by type for the current month.
    Returns [(label, count), ...] sorted by count descending.
    """
    conn = get_conn()
    now = datetime.now(timezone.utc)
    month_start = now.strftime("%Y-%m-01")
    rows = conn.execute(
        """SELECT infraction_type, COUNT(*) AS cnt
           FROM ats_infractions
           WHERE infraction_date >= ?
           GROUP BY infraction_type ORDER BY cnt DESC""",
        (month_start,),
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        itype = r["infraction_type"]
        label = INFRACTION_TYPES.get(itype, {}).get("label", itype)
        result.append((label, r["cnt"]))
    return result


def get_site_attendance_summary() -> list:
    """Get attendance summary by site."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT site, COUNT(*) as officer_count,
           SUM(active_points) as total_points,
           AVG(active_points) as avg_points
           FROM officers WHERE status = 'Active' AND site != ''
           GROUP BY site ORDER BY total_points DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Report Queries ───────────────────────────────────────────────

def get_officer_points_summary(limit: int = 10) -> list:
    """Top officers by active points. Returns list of dicts."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT officer_id, name, employee_id, site, active_points, discipline_level
           FROM officers WHERE status = 'Active' AND active_points > 0
           ORDER BY active_points DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_discipline_level_distribution() -> list:
    """Count of active officers per discipline level. Returns [(level, count), ...]."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT discipline_level, COUNT(*) as cnt
           FROM officers WHERE status = 'Active'
           GROUP BY discipline_level ORDER BY cnt DESC"""
    ).fetchall()
    conn.close()
    return [(r["discipline_level"] or "None", r["cnt"]) for r in rows]


def get_site_infraction_summary() -> list:
    """Infractions per site with total points. Returns list of dicts."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT site, COUNT(*) as infraction_count,
           SUM(CASE WHEN points_active = 1 THEN points_assigned ELSE 0 END) as total_active_points
           FROM ats_infractions WHERE site != ''
           GROUP BY site ORDER BY infraction_count DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Analytics Queries ─────────────────────────────────────────────────

def get_analytics_data() -> dict:
    """Comprehensive analytics data for the attendance analytics page."""
    conn = get_conn()

    # Overall totals
    total_infractions = conn.execute("SELECT COUNT(*) as c FROM ats_infractions").fetchone()["c"]
    active_infractions = conn.execute(
        "SELECT COUNT(*) as c FROM ats_infractions WHERE points_active = 1"
    ).fetchone()["c"]
    total_points = conn.execute(
        "SELECT COALESCE(SUM(points_assigned), 0) as s FROM ats_infractions WHERE points_active = 1"
    ).fetchone()["s"]
    unique_offenders = conn.execute(
        "SELECT COUNT(DISTINCT employee_id) as c FROM ats_infractions"
    ).fetchone()["c"]
    active_officers = conn.execute(
        "SELECT COUNT(*) as c FROM officers WHERE status = 'Active'"
    ).fetchone()["c"]

    # Avg points per offender
    avg_points_per_offender = round(total_points / unique_offenders, 1) if unique_offenders else 0

    # Infraction rate (% of active officers with any infraction)
    offenders_active = conn.execute(
        """SELECT COUNT(DISTINCT i.employee_id) as c
           FROM ats_infractions i
           LEFT JOIN ats_id_mapping m ON i.employee_id = m.ats_id
           LEFT JOIN officers o ON COALESCE(m.officer_id, i.employee_id) = o.officer_id
           WHERE o.status = 'Active' OR o.officer_id IS NULL"""
    ).fetchone()["c"]
    infraction_rate = round(offenders_active / active_officers * 100, 1) if active_officers else 0

    # Monthly trend (last 12 months)
    monthly_trend = conn.execute(
        """SELECT strftime('%Y-%m', infraction_date) AS month,
                  COUNT(*) AS cnt,
                  SUM(points_assigned) AS pts
           FROM ats_infractions
           WHERE infraction_date >= date('now', '-12 months')
           GROUP BY month ORDER BY month ASC"""
    ).fetchall()
    monthly_labels = []
    monthly_counts = []
    monthly_points = []
    import calendar
    for r in monthly_trend:
        ym = r["month"] or ""
        try:
            year, mon = ym.split("-")
            monthly_labels.append(f"{calendar.month_abbr[int(mon)]} '{year[-2:]}")
        except (ValueError, IndexError):
            monthly_labels.append(ym)
        monthly_counts.append(r["cnt"])
        monthly_points.append(round(r["pts"] or 0, 1))

    # By type (all time)
    by_type = conn.execute(
        """SELECT infraction_type, COUNT(*) as cnt,
                  SUM(points_assigned) as pts
           FROM ats_infractions
           GROUP BY infraction_type ORDER BY cnt DESC"""
    ).fetchall()
    type_data = []
    for r in by_type:
        itype = r["infraction_type"]
        label = INFRACTION_TYPES.get(itype, {}).get("label", itype.replace("_", " ").title())
        type_data.append({"label": label, "count": r["cnt"], "points": round(r["pts"] or 0, 1)})

    # By site (with officer names resolved)
    by_site = conn.execute(
        """SELECT COALESCE(NULLIF(site, ''), 'Unassigned') as site_name,
                  COUNT(*) as cnt,
                  SUM(points_assigned) as pts,
                  COUNT(DISTINCT employee_id) as unique_officers
           FROM ats_infractions
           GROUP BY site_name ORDER BY cnt DESC"""
    ).fetchall()
    site_data = [dict(r) for r in by_site]

    # Day of week distribution
    day_of_week = conn.execute(
        """SELECT CASE CAST(strftime('%w', infraction_date) AS INTEGER)
                  WHEN 0 THEN 'Sun' WHEN 1 THEN 'Mon' WHEN 2 THEN 'Tue'
                  WHEN 3 THEN 'Wed' WHEN 4 THEN 'Thu' WHEN 5 THEN 'Fri'
                  WHEN 6 THEN 'Sat' END as dow,
                  CAST(strftime('%w', infraction_date) AS INTEGER) as dow_num,
                  COUNT(*) as cnt
           FROM ats_infractions
           WHERE infraction_date != ''
           GROUP BY dow_num ORDER BY dow_num"""
    ).fetchall()
    dow_labels = [r["dow"] for r in day_of_week]
    dow_counts = [r["cnt"] for r in day_of_week]

    # Top repeat offenders (with names)
    top_offenders = conn.execute(
        """SELECT i.employee_id,
                  COALESCE(o.name, m.officer_name, i.employee_id) as officer_name,
                  COUNT(*) as infraction_count,
                  SUM(i.points_assigned) as total_points,
                  MAX(i.infraction_date) as last_infraction
           FROM ats_infractions i
           LEFT JOIN officers o ON i.employee_id = o.officer_id OR i.employee_id = o.employee_id
           LEFT JOIN ats_id_mapping m ON i.employee_id = m.ats_id
           GROUP BY i.employee_id
           ORDER BY infraction_count DESC LIMIT 15"""
    ).fetchall()
    top_offenders_data = [dict(r) for r in top_offenders]

    # Discipline level distribution
    discipline_dist = conn.execute(
        """SELECT COALESCE(NULLIF(discipline_level, ''), 'None') as level,
                  COUNT(*) as cnt
           FROM officers WHERE status = 'Active'
           GROUP BY level ORDER BY cnt DESC"""
    ).fetchall()
    disc_labels = [r["level"] for r in discipline_dist]
    disc_counts = [r["cnt"] for r in discipline_dist]

    # Points expiring soon (next 30 days)
    expiring_soon = conn.execute(
        """SELECT COUNT(*) as c FROM ats_infractions
           WHERE points_active = 1
           AND point_expiry_date != ''
           AND point_expiry_date BETWEEN date('now') AND date('now', '+30 days')"""
    ).fetchone()["c"]

    # Emergency exemptions stats
    emergency = conn.execute(
        """SELECT
           COUNT(CASE WHEN is_emergency_exemption = 1 THEN 1 END) as total_emergency,
           COUNT(CASE WHEN is_emergency_exemption = 1 AND exemption_approved = 1 THEN 1 END) as approved,
           COUNT(CASE WHEN is_emergency_exemption = 1 AND exemption_approved = 0 THEN 1 END) as denied
           FROM ats_infractions"""
    ).fetchone()

    conn.close()

    return {
        "total_infractions": total_infractions,
        "active_infractions": active_infractions,
        "total_points": round(total_points, 1),
        "unique_offenders": unique_offenders,
        "active_officers": active_officers,
        "avg_points_per_offender": avg_points_per_offender,
        "infraction_rate": infraction_rate,
        "monthly_labels": monthly_labels,
        "monthly_counts": monthly_counts,
        "monthly_points": monthly_points,
        "type_data": type_data,
        "site_data": site_data,
        "dow_labels": dow_labels,
        "dow_counts": dow_counts,
        "top_offenders": top_offenders_data,
        "disc_labels": disc_labels,
        "disc_counts": disc_counts,
        "expiring_soon": expiring_soon,
        "emergency_total": emergency["total_emergency"],
        "emergency_approved": emergency["approved"],
        "emergency_denied": emergency["denied"],
    }


# ── CSV Import / Export ───────────────────────────────────────────────

def import_employees_csv(csv_text: str, created_by: str = "") -> dict:
    """Import officers from CSV text. Returns {imported, skipped, errors}."""
    reader = csv.DictReader(io.StringIO(csv_text))
    imported, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):
        try:
            name = row.get("name", "").strip()
            if not name:
                skipped += 1
                continue
            create_officer(dict(row), created_by=created_by)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")
    return {"imported": imported, "skipped": skipped, "errors": errors}


def _resolve_employee_by_name(name: str) -> str | None:
    """Look up an officer_id by name. Returns officer_id or None."""
    if not name:
        return None
    conn = get_conn()
    # Try exact match on name or first_name + last_name
    row = conn.execute(
        "SELECT officer_id FROM officers WHERE name = ? OR (first_name || ' ' || last_name) = ?",
        (name.strip(), name.strip()),
    ).fetchone()
    conn.close()
    return row["officer_id"] if row else None


def _map_tracktik_infraction_type(raw_type: str) -> str:
    """Map a TrackTik CSV infraction type string to our internal type key."""
    rt = raw_type.strip().lower()
    if "no call" in rt or "no show" in rt or "ncns" in rt:
        return "ncns"
    if "less than two" in rt or "under 2" in rt or "less than 2" in rt:
        return "calloff_under2h"
    if "less than four" in rt or "under 4" in rt or "less than 4" in rt:
        return "calloff_under4h"
    if "proper notice" in rt or "call-off with proper" in rt or "call off with proper" in rt:
        return "calloff_proper_notice"
    if "tardy" in rt or "tardiness" in rt or "late" in rt:
        return "tardiness"
    if "post abandon" in rt:
        return "post_abandonment"
    if "emergency exemption" in rt or "emergency" in rt:
        # Treat missing documentation or denied as denied, otherwise approved
        if "denied" in rt or "missing" in rt:
            return "emergency_exemption_denied"
        return "emergency_exemption_approved"
    return ""


def import_infractions_csv(csv_text: str, entered_by: str = "") -> dict:
    """Import infractions from CSV text. Supports both simple format and TrackTik format.

    Simple format columns: employee_id, infraction_type, infraction_date, points_assigned, site, description
    TrackTik format columns: Attendance Issue:Employee, Attendance Issue:Infraction Type, etc.

    For TrackTik format, applies 1st-offense logic:
    - Tardiness: 1st chronological per person = 0 pts, subsequent = 1.5 pts
    - Call-off with proper notice: 1st chronological per person = 0 pts, subsequent = 2 pts
    - Short-notice call-offs (< 4hr, < 2hr): Always get points
    - NCNS: 1st = 6 pts, 2nd = termination flag
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    headers = reader.fieldnames or []

    # Detect format: TrackTik if "Attendance Issue:Employee" column exists
    is_tracktik = any("Attendance Issue:Employee" in h for h in headers)

    if not is_tracktik:
        # Simple format — original logic
        imported, skipped, errors = 0, 0, []
        for i, row in enumerate(reader, start=2):
            try:
                emp = row.get("employee_id", "").strip()
                itype = row.get("infraction_type", "").strip()
                if not emp or not itype:
                    skipped += 1
                    continue
                create_infraction(dict(row), entered_by=entered_by)
                imported += 1
            except Exception as exc:
                errors.append(f"Row {i}: {exc}")
        return {"imported": imported, "skipped": skipped, "errors": errors}

    # ── TrackTik format import with smart 1st/additional logic ──
    imported, skipped = 0, 0
    errors: list[str] = []
    not_found: set[str] = set()

    # First pass: collect all rows and sort by date per employee
    rows_parsed = []
    for i, row in enumerate(reader, start=2):
        emp_name = row.get("Attendance Issue:Employee", "").strip()
        raw_type = row.get("Attendance Issue:Infraction Type", "").strip()
        inf_date = row.get("Attendance Issue:Scheduled Shift Date", "").strip()
        site = row.get("Attendance Issue:Site", "").strip()
        shift = row.get("Attendance Issue:Scheduled Shift Time", "").strip()
        reason = row.get("Attendance Issue:Reason Provided", "").strip()
        time_notified = row.get("Attendance Issue:Time notified", "").strip()
        documentation = row.get("Attendance Issue:Documentation:", "").strip()
        coverage = row.get("Attendance Issue:Coverage Actions Taken", "").strip()
        reporter = row.get("Reporter Employee Name", "").strip()

        if not emp_name or not raw_type:
            skipped += 1
            continue

        base_type = _map_tracktik_infraction_type(raw_type)
        if not base_type:
            errors.append(f"Row {i}: Unknown infraction type '{raw_type}'")
            continue

        # Resolve employee
        officer_id = _resolve_employee_by_name(emp_name)
        if not officer_id:
            not_found.add(emp_name)
            skipped += 1
            continue

        # Build description from available fields
        desc_parts = []
        if reason:
            desc_parts.append(f"Reason: {reason}")
        if shift:
            desc_parts.append(f"Shift: {shift}")
        if time_notified:
            desc_parts.append(f"Notified at: {time_notified}")
        if documentation:
            desc_parts.append(f"Documentation: {documentation}")
        if coverage:
            desc_parts.append(f"Coverage: {coverage}")
        if reporter:
            desc_parts.append(f"Reported by: {reporter}")
        description = " | ".join(desc_parts)

        rows_parsed.append({
            "row_num": i,
            "employee_id": officer_id,
            "employee_name": emp_name,
            "base_type": base_type,
            "infraction_date": inf_date,
            "site": site,
            "description": description,
        })

    # Sort all rows by date so 1st/additional logic works chronologically
    rows_parsed.sort(key=lambda r: r.get("infraction_date", ""))

    # Track counts per employee per category for 1st/additional logic
    emp_counts: dict[str, dict[str, int]] = {}

    for r in rows_parsed:
        eid = r["employee_id"]
        base = r["base_type"]

        if eid not in emp_counts:
            emp_counts[eid] = {}
        count = emp_counts[eid].get(base, 0)

        # Determine specific infraction type with 1st/additional logic
        if base == "tardiness":
            itype = "tardiness_1st" if count == 0 else "tardiness_additional"
        elif base == "calloff_proper_notice":
            itype = "calloff_proper_notice_1st" if count == 0 else "calloff_proper_notice_additional"
        elif base == "ncns":
            itype = "ncns_1st" if count == 0 else "ncns_2nd"
        else:
            # calloff_under4h, calloff_under2h, post_abandonment — always points
            itype = base

        emp_counts[eid][base] = count + 1

        try:
            create_infraction({
                "employee_id": eid,
                "infraction_type": itype,
                "infraction_date": r["infraction_date"],
                "site": r["site"],
                "description": r["description"],
            }, entered_by=entered_by)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {r['row_num']} ({r['employee_name']}): {exc}")

    # Add not-found employees as informational errors
    if not_found:
        for name in sorted(not_found):
            errors.append(f"Employee not found in system: {name}")

    return {"imported": imported, "skipped": skipped, "errors": errors, "not_found": sorted(not_found)}


def export_discipline_csv() -> str:
    """Export discipline summary as CSV text."""
    officers = get_all_officers()
    if not officers:
        return ""

    output = io.StringIO()
    fieldnames = [
        "name", "employee_id", "site", "active_points",
        "discipline_level", "last_infraction_date", "status",
        "emergency_exemptions_used",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for off in officers:
        writer.writerow({k: off.get(k, "") for k in fieldnames})
    return output.getvalue()


def export_infractions_csv() -> str:
    """Export all infractions as CSV text."""
    infractions = get_all_infractions()
    if not infractions:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=infractions[0].keys())
    writer.writeheader()
    writer.writerows(infractions)
    return output.getvalue()


def export_reviews_csv() -> str:
    """Export all employment reviews as CSV text."""
    reviews = get_all_reviews()
    if not reviews:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=reviews[0].keys())
    writer.writeheader()
    writer.writerows(reviews)
    return output.getvalue()


# ── Internal Helpers ──────────────────────────────────────────────────

def _latest_retain_review(reviews: list) -> dict | None:
    """Return the most recent completed review with a retain/probation outcome."""
    retained_outcomes = {
        "retain", "retain_reduce", "Retained", "retained",
        "probation", "Probation", "Final Warning", "final_warning",
    }
    latest = None
    for rev in (reviews or []):
        if rev.get("review_status") != "Completed":
            continue
        if rev.get("outcome", "") not in retained_outcomes:
            continue
        rd = rev.get("review_date", "") or ""
        if not rd:
            continue
        if latest is None or rd > (latest.get("review_date", "") or ""):
            latest = rev
    return latest


def _refresh_officer_discipline(employee_id: str):
    """Recalculate an officer's active points and discipline level.

    Honors retain/reset logic: if the officer has a completed review with a
    retain-type outcome, only infractions after that review count toward
    active points, plus the review's points_after_outcome (default 6.0).
    """
    if not employee_id:
        return

    infractions = get_infractions_for_employee(employee_id)
    reviews = get_reviews_for_employee(employee_id)

    # Apply retain/reset logic if a retain review exists
    latest_retain = _latest_retain_review(reviews)
    if latest_retain and latest_retain.get("review_date"):
        review_date = latest_retain["review_date"]
        post_retain = [i for i in infractions
                       if (i.get("infraction_date") or "") > review_date]
        active_pts = calculate_active_points(post_retain)
        baseline = float(latest_retain.get("points_after_outcome") or 6.0)
        active_pts = round(active_pts + baseline, 2)
    else:
        active_pts = calculate_active_points(infractions)

    level = determine_discipline_level(active_pts)
    exemptions = count_emergency_exemptions(infractions)

    # Last infraction date
    last_date = ""
    if infractions:
        last_date = infractions[0].get("infraction_date", "")

    update_officer(employee_id, {
        "active_points": active_pts,
        "discipline_level": DISCIPLINE_LABELS.get(level, level),
        "last_infraction_date": last_date,
        "emergency_exemptions_used": exemptions,
    })

    # Auto-create employment review if threshold met (only if no recent retain)
    if not latest_retain and should_trigger_review(active_pts):
        _auto_create_review_if_needed(employee_id, active_pts)


def _auto_create_review_if_needed(employee_id: str, active_points: float):
    """Create a pending employment review if none already exists for this point level."""
    conn = get_conn()
    existing = conn.execute(
        """SELECT id FROM ats_employment_reviews
           WHERE employee_id = ? AND review_status = 'Pending'""",
        (employee_id,),
    ).fetchone()
    conn.close()

    if existing:
        return

    create_review({
        "employee_id": employee_id,
        "points_at_trigger": active_points,
    })
