"""
Cerasus Hub -- DLS & Overtime Module: Data Manager
SQLite-backed CRUD for dls_labor_entries and dls_site_budgets.
Officers and sites are delegated to the shared data layer.
"""

import csv
import io
from datetime import datetime, timezone, date, timedelta

from src.database import get_conn

# ── Shared Data Delegates (Officers & Sites) ─────────────────────────
from src.shared_data import (
    get_all_officers,
    get_officer,
    get_active_officers,
    get_officer_names,
    get_all_sites,
    get_site,
    get_site_names,
)


# ── Helpers ───────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_current_week_ending() -> str:
    """Return this week's Saturday date as YYYY-MM-DD."""
    today = date.today()
    days_until_sat = (5 - today.weekday()) % 7
    saturday = today + timedelta(days=days_until_sat)
    return saturday.isoformat()


# ── Labor Entry CRUD ──────────────────────────────────────────────────

def create_labor_entry(fields: dict, created_by: str = "") -> int:
    """Create a labor entry. Returns the new row id."""
    now = _now()

    # Auto-calculate totals if not provided
    regular = float(fields.get("regular_hours", 0))
    overtime = float(fields.get("overtime_hours", 0))
    double_time = float(fields.get("double_time_hours", 0))
    total_hours = fields.get("total_hours") or (regular + overtime + double_time)

    regular_rate = float(fields.get("regular_rate", 0))
    overtime_rate = float(fields.get("overtime_rate", 0))
    regular_pay = fields.get("regular_pay") or (regular * regular_rate)
    overtime_pay = fields.get("overtime_pay") or (overtime * overtime_rate * 1.5 + double_time * regular_rate * 2)
    total_pay = fields.get("total_pay") or (float(regular_pay) + float(overtime_pay))

    billable = float(fields.get("billable_hours", total_hours))
    non_billable = float(fields.get("non_billable_hours", 0))

    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO dls_labor_entries
           (officer_id, officer_name, site, week_ending,
            regular_hours, overtime_hours, double_time_hours, total_hours,
            regular_rate, overtime_rate,
            regular_pay, overtime_pay, total_pay,
            billable_hours, non_billable_hours, dls_percentage,
            source, imported_at, created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            fields.get("officer_id", ""),
            fields.get("officer_name", ""),
            fields.get("site", ""),
            fields.get("week_ending", get_current_week_ending()),
            regular,
            overtime,
            double_time,
            float(total_hours),
            regular_rate,
            overtime_rate,
            float(regular_pay),
            float(overtime_pay),
            float(total_pay),
            billable,
            non_billable,
            float(fields.get("dls_percentage", 0)),
            fields.get("source", "manual"),
            fields.get("imported_at", ""),
            created_by,
            now,
            now,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_all_entries() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM dls_labor_entries ORDER BY week_ending DESC, site, officer_name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_entries_for_week(week_ending: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM dls_labor_entries WHERE week_ending = ? ORDER BY site, officer_name",
        (week_ending,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_entries_for_officer(officer_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM dls_labor_entries WHERE officer_id = ? ORDER BY week_ending DESC",
        (officer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_entries_for_site(site: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM dls_labor_entries WHERE site = ? ORDER BY week_ending DESC, officer_name",
        (site,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Dashboard & Analysis ──────────────────────────────────────────────

def get_dashboard_summary(week_ending: str = None) -> dict:
    """Get dashboard KPI data for a given week (defaults to current week)."""
    if not week_ending:
        week_ending = get_current_week_ending()

    entries = get_entries_for_week(week_ending)

    total_hours = sum(e.get("total_hours", 0) for e in entries)
    ot_hours = sum(e.get("overtime_hours", 0) + e.get("double_time_hours", 0) for e in entries)
    total_pay = sum(e.get("total_pay", 0) for e in entries)
    ot_pay = sum(e.get("overtime_pay", 0) for e in entries)
    reg_hours = sum(e.get("regular_hours", 0) for e in entries)

    ot_pct = (ot_hours / total_hours * 100) if total_hours > 0 else 0
    dls_pct = sum(e.get("dls_percentage", 0) for e in entries) / len(entries) if entries else 0

    # Officers over 40 hours
    officer_totals = {}
    for e in entries:
        key = e.get("officer_id") or e.get("officer_name", "")
        if key not in officer_totals:
            officer_totals[key] = {
                "officer_id": e.get("officer_id", ""),
                "officer_name": e.get("officer_name", ""),
                "site": e.get("site", ""),
                "regular_hours": 0,
                "overtime_hours": 0,
                "double_time_hours": 0,
                "total_hours": 0,
                "total_pay": 0,
            }
        officer_totals[key]["regular_hours"] += e.get("regular_hours", 0)
        officer_totals[key]["overtime_hours"] += e.get("overtime_hours", 0)
        officer_totals[key]["double_time_hours"] += e.get("double_time_hours", 0)
        officer_totals[key]["total_hours"] += e.get("total_hours", 0)
        officer_totals[key]["total_pay"] += e.get("total_pay", 0)

    officers_over_40 = [o for o in officer_totals.values() if o["total_hours"] > 40]
    top_ot_officers = sorted(officer_totals.values(), key=lambda x: -x["overtime_hours"])[:10]

    # Site breakdown
    site_totals = {}
    for e in entries:
        s = e.get("site", "Unknown")
        if s not in site_totals:
            site_totals[s] = {"regular_hours": 0, "overtime_hours": 0, "total_hours": 0, "total_pay": 0}
        site_totals[s]["regular_hours"] += e.get("regular_hours", 0)
        site_totals[s]["overtime_hours"] += e.get("overtime_hours", 0) + e.get("double_time_hours", 0)
        site_totals[s]["total_hours"] += e.get("total_hours", 0)
        site_totals[s]["total_pay"] += e.get("total_pay", 0)

    return {
        "week_ending": week_ending,
        "total_hours": total_hours,
        "regular_hours": reg_hours,
        "overtime_hours": ot_hours,
        "ot_percentage": ot_pct,
        "total_pay": total_pay,
        "overtime_pay": ot_pay,
        "dls_percentage": dls_pct,
        "officers_over_40": len(officers_over_40),
        "top_ot_officers": top_ot_officers,
        "site_breakdown": site_totals,
        "officer_totals": officer_totals,
        "entry_count": len(entries),
    }


def get_weekly_summary(week_ending: str) -> list:
    """Per-site weekly totals for the summary table."""
    entries = get_entries_for_week(week_ending)
    budgets = {b["site"]: b for b in get_site_budgets()}

    site_data = {}
    for e in entries:
        s = e.get("site", "Unknown")
        if s not in site_data:
            site_data[s] = {
                "site": s,
                "actual_hours": 0,
                "ot_hours": 0,
                "ot_cost": 0,
                "total_pay": 0,
                "dls_total": 0,
                "entry_count": 0,
            }
        site_data[s]["actual_hours"] += e.get("total_hours", 0)
        site_data[s]["ot_hours"] += e.get("overtime_hours", 0) + e.get("double_time_hours", 0)
        site_data[s]["ot_cost"] += e.get("overtime_pay", 0)
        site_data[s]["total_pay"] += e.get("total_pay", 0)
        site_data[s]["dls_total"] += e.get("dls_percentage", 0)
        site_data[s]["entry_count"] += 1

    result = []
    for s, d in sorted(site_data.items()):
        budget = budgets.get(s, {})
        budget_hrs = budget.get("weekly_budget_hours", 0)
        variance = d["actual_hours"] - budget_hrs if budget_hrs > 0 else 0
        dls_pct = d["dls_total"] / d["entry_count"] if d["entry_count"] > 0 else 0
        result.append({
            "site": s,
            "budget_hours": budget_hrs,
            "actual_hours": round(d["actual_hours"], 2),
            "variance": round(variance, 2),
            "ot_hours": round(d["ot_hours"], 2),
            "ot_cost": round(d["ot_cost"], 2),
            "dls_percentage": round(dls_pct, 1),
        })
    return result


def get_overtime_alerts(week_ending: str = None) -> list:
    """Officers approaching or exceeding 40 hours."""
    if not week_ending:
        week_ending = get_current_week_ending()

    entries = get_entries_for_week(week_ending)

    officer_totals = {}
    for e in entries:
        key = e.get("officer_id") or e.get("officer_name", "")
        if key not in officer_totals:
            officer_totals[key] = {
                "officer_id": e.get("officer_id", ""),
                "officer_name": e.get("officer_name", ""),
                "site": e.get("site", ""),
                "total_hours": 0,
                "regular_hours": 0,
                "overtime_hours": 0,
            }
        officer_totals[key]["total_hours"] += e.get("total_hours", 0)
        officer_totals[key]["regular_hours"] += e.get("regular_hours", 0)
        officer_totals[key]["overtime_hours"] += e.get("overtime_hours", 0)
        # Keep most recent site
        if e.get("site"):
            officer_totals[key]["site"] = e["site"]

    alerts = []
    for o in officer_totals.values():
        total = o["total_hours"]
        if total >= 32:
            if total >= 48:
                level = "Critical"
            elif total >= 40:
                level = "Over"
            else:
                level = "Warning"
            alerts.append({
                "officer_id": o["officer_id"],
                "officer_name": o["officer_name"],
                "site": o["site"],
                "total_hours": round(total, 2),
                "regular_hours": round(o["regular_hours"], 2),
                "overtime_hours": round(o["overtime_hours"], 2),
                "level": level,
            })

    return sorted(alerts, key=lambda x: -x["total_hours"])


def get_site_analysis(site: str, date_from: str, date_to: str) -> list:
    """Detailed site breakdown for a date range."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM dls_labor_entries
           WHERE site = ? AND week_ending >= ? AND week_ending <= ?
           ORDER BY week_ending DESC, officer_name""",
        (site, date_from, date_to),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_officer_analysis(officer_id: str, date_from: str, date_to: str) -> list:
    """Officer labor history for a date range."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM dls_labor_entries
           WHERE officer_id = ? AND week_ending >= ? AND week_ending <= ?
           ORDER BY week_ending DESC""",
        (officer_id, date_from, date_to),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── CSV Import Functions ──────────────────────────────────────────────

def import_tractic_csv(csv_text: str, created_by: str = "") -> dict:
    """Parse Tractic export CSV format.
    Expected columns: Employee ID, Employee Name, Site, Week Ending,
    Regular Hours, OT Hours, DT Hours, Regular Rate, OT Rate.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    imported, skipped, errors = 0, 0, []
    now = _now()

    for i, row in enumerate(reader, start=2):
        try:
            name = row.get("Employee Name", "").strip()
            if not name:
                skipped += 1
                continue

            reg = float(row.get("Regular Hours", 0) or 0)
            ot = float(row.get("OT Hours", 0) or 0)
            dt = float(row.get("DT Hours", 0) or 0)
            reg_rate = float(row.get("Regular Rate", 0) or 0)
            ot_rate = float(row.get("OT Rate", 0) or 0)

            fields = {
                "officer_id": row.get("Employee ID", "").strip(),
                "officer_name": name,
                "site": row.get("Site", "").strip(),
                "week_ending": row.get("Week Ending", "").strip(),
                "regular_hours": reg,
                "overtime_hours": ot,
                "double_time_hours": dt,
                "regular_rate": reg_rate,
                "overtime_rate": ot_rate,
                "source": "tractic_import",
                "imported_at": now,
            }
            create_labor_entry(fields, created_by=created_by)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")

    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_winteam_csv(csv_text: str, created_by: str = "") -> dict:
    """Parse WinTeam export CSV format.
    Expected columns: EmpID, Name, Location, WeekEnd, RegHrs, OTHrs,
    DTHrs, PayRate.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    imported, skipped, errors = 0, 0, []
    now = _now()

    for i, row in enumerate(reader, start=2):
        try:
            name = row.get("Name", "").strip()
            if not name:
                skipped += 1
                continue

            reg = float(row.get("RegHrs", 0) or 0)
            ot = float(row.get("OTHrs", 0) or 0)
            dt = float(row.get("DTHrs", 0) or 0)
            rate = float(row.get("PayRate", 0) or 0)

            fields = {
                "officer_id": row.get("EmpID", "").strip(),
                "officer_name": name,
                "site": row.get("Location", "").strip(),
                "week_ending": row.get("WeekEnd", "").strip(),
                "regular_hours": reg,
                "overtime_hours": ot,
                "double_time_hours": dt,
                "regular_rate": rate,
                "overtime_rate": rate,
                "source": "winteam_import",
                "imported_at": now,
            }
            create_labor_entry(fields, created_by=created_by)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")

    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_generic_csv(csv_text: str, created_by: str = "") -> dict:
    """Parse a generic hours CSV.
    Expected columns: officer_id, officer_name, site, week_ending,
    regular_hours, overtime_hours, double_time_hours, regular_rate, overtime_rate.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    imported, skipped, errors = 0, 0, []
    now = _now()

    for i, row in enumerate(reader, start=2):
        try:
            name = row.get("officer_name", "").strip()
            if not name:
                skipped += 1
                continue

            fields = {
                "officer_id": row.get("officer_id", "").strip(),
                "officer_name": name,
                "site": row.get("site", "").strip(),
                "week_ending": row.get("week_ending", "").strip(),
                "regular_hours": float(row.get("regular_hours", 0) or 0),
                "overtime_hours": float(row.get("overtime_hours", 0) or 0),
                "double_time_hours": float(row.get("double_time_hours", 0) or 0),
                "regular_rate": float(row.get("regular_rate", 0) or 0),
                "overtime_rate": float(row.get("overtime_rate", 0) or 0),
                "source": "generic_import",
                "imported_at": now,
            }
            create_labor_entry(fields, created_by=created_by)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")

    return {"imported": imported, "skipped": skipped, "errors": errors}


# ── CSV Export ────────────────────────────────────────────────────────

def export_labor_csv(week_ending: str = None) -> str:
    """Export labor entries to CSV text. If week_ending is None, export all."""
    if week_ending:
        rows = get_entries_for_week(week_ending)
    else:
        rows = get_all_entries()

    if not rows:
        return ""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ── DLS Calculation ───────────────────────────────────────────────────

def calculate_dls(total_pay: float, revenue: float) -> float:
    """Calculate DLS percentage: total_pay / revenue * 100."""
    if revenue <= 0:
        return 0.0
    return round((total_pay / revenue) * 100, 2)


# ── Site Budget CRUD ──────────────────────────────────────────────────

def get_site_budgets() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM dls_site_budgets ORDER BY site"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_site_budget(site: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM dls_site_budgets WHERE site = ? ORDER BY effective_date DESC LIMIT 1",
        (site,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_site_budget(fields: dict, created_by: str = "") -> int:
    """Create or update a site budget. Returns row id."""
    now = _now()
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO dls_site_budgets
           (site, weekly_budget_hours, weekly_budget_dollars,
            ot_threshold_hours, ot_alert_percentage,
            effective_date, created_by, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            fields.get("site", ""),
            float(fields.get("weekly_budget_hours", 0)),
            float(fields.get("weekly_budget_dollars", 0)),
            float(fields.get("ot_threshold_hours", 40)),
            float(fields.get("ot_alert_percentage", 80)),
            fields.get("effective_date", _now()[:10]),
            created_by,
            now,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def delete_labor_entry(entry_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM dls_labor_entries WHERE id = ?", (entry_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0
