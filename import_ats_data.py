"""
Cerasus Hub — Import ATS Website Data
Imports officers, sites, infractions, employment reviews, and audit log
from the cerasus_ats_export.json file exported from the live ATS website.

Usage:
    python import_ats_data.py [path_to_json]

If no path is given, looks in common locations for cerasus_ats_export.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import ensure_directories
from src.database import initialize_database, get_conn


def _ts_to_iso(ts):
    """Convert millisecond timestamp or ISO string to ISO format."""
    if not ts:
        return ""
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        except Exception:
            return ""
    return str(ts)


def _status_map(status):
    """Map ATS status values to hub format."""
    if not status:
        return "Active"
    s = str(status).lower().strip()
    if s in ("active", "true"):
        return "Active"
    if s in ("inactive", "false"):
        return "Inactive"
    if s in ("terminated",):
        return "Terminated"
    return status.title()


def import_data(json_path):
    """Import all ATS data into the hub database."""
    print(f"[Import] Loading data from: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ensure_directories()
    initialize_database()
    conn = get_conn()

    counts = {
        "officers_imported": 0,
        "officers_skipped": 0,
        "sites_imported": 0,
        "sites_skipped": 0,
        "infractions_imported": 0,
        "infractions_skipped": 0,
        "reviews_imported": 0,
        "reviews_skipped": 0,
        "errors": 0,
    }

    # ── Sites ──────────────────────────────────────────────────────────
    print(f"\n[Sites] Importing {len(data.get('sites', []))} sites...")
    for site in data.get("sites", []):
        try:
            name = (site.get("name") or "").strip()
            if not name:
                continue

            # Check if site already exists by name
            existing = conn.execute(
                "SELECT site_id FROM sites WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()

            if existing:
                counts["sites_skipped"] += 1
                continue

            site_id = site.get("id", f"ats_{name[:8]}")
            conn.execute(
                """INSERT INTO sites (site_id, name, address, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'Active', ?, ?)""",
                (
                    site_id,
                    name,
                    site.get("address", ""),
                    _ts_to_iso(site.get("created_at")),
                    _ts_to_iso(site.get("updated_at", site.get("created_at"))),
                ),
            )
            counts["sites_imported"] += 1
        except Exception as e:
            counts["errors"] += 1
            print(f"  [ERROR] Site '{site.get('name')}': {e}")

    conn.commit()
    print(f"  Imported: {counts['sites_imported']}, Skipped: {counts['sites_skipped']}")

    # ── Build employee ID mapping (ATS id -> hub officer_id) ──────────
    # We need this to link infractions/reviews to officers
    emp_id_map = {}  # ATS employee id -> hub officer_id

    # ── Officers (Employees) ──────────────────────────────────────────
    print(f"\n[Officers] Importing {len(data.get('employees', []))} employees...")
    for emp in data.get("employees", []):
        try:
            first = (emp.get("first_name") or "").strip()
            last = (emp.get("last_name") or "").strip()
            name = f"{first} {last}".strip()
            if not name:
                continue

            ats_id = emp.get("id", "")
            employee_id = emp.get("employee_id", "")

            # Check if officer already exists by employee_id or name
            existing = None
            if employee_id:
                existing = conn.execute(
                    "SELECT officer_id FROM officers WHERE employee_id = ?",
                    (employee_id,),
                ).fetchone()
            if not existing:
                existing = conn.execute(
                    "SELECT officer_id FROM officers WHERE LOWER(name) = LOWER(?)",
                    (name,),
                ).fetchone()

            if existing:
                emp_id_map[ats_id] = existing["officer_id"]
                counts["officers_skipped"] += 1
                continue

            # Use ATS id as officer_id for consistent linking
            officer_id = ats_id or f"ats_{employee_id}"
            emp_id_map[ats_id] = officer_id

            conn.execute(
                """INSERT INTO officers
                   (officer_id, name, employee_id, first_name, last_name,
                    email, phone, site, role_title, job_title,
                    supervisor_id, hire_date, status,
                    active_points, discipline_level,
                    last_infraction_date, emergency_exemptions_used,
                    notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    officer_id,
                    name,
                    employee_id,
                    first,
                    last,
                    emp.get("email", ""),
                    emp.get("phone", ""),
                    emp.get("site", ""),
                    emp.get("role_title", ""),
                    emp.get("role_title", "Security Officer"),
                    emp.get("supervisor_id", ""),
                    emp.get("hire_date", ""),
                    _status_map(emp.get("status")),
                    emp.get("active_points", 0) or 0,
                    emp.get("discipline_level", "none") or "none",
                    emp.get("last_infraction_date", "") or "",
                    emp.get("emergency_exemptions_used", 0) or 0,
                    emp.get("notes", ""),
                    _ts_to_iso(emp.get("created_at")),
                    _ts_to_iso(emp.get("updated_at")),
                ),
            )
            counts["officers_imported"] += 1
        except Exception as e:
            counts["errors"] += 1
            print(f"  [ERROR] Employee '{emp.get('first_name')} {emp.get('last_name')}': {e}")

    conn.commit()
    print(f"  Imported: {counts['officers_imported']}, Skipped: {counts['officers_skipped']}")

    # ── Infractions ───────────────────────────────────────────────────
    print(f"\n[Infractions] Importing {len(data.get('infractions', []))} infractions...")
    for inf in data.get("infractions", []):
        try:
            ats_emp_id = inf.get("employee_id", "")
            hub_officer_id = emp_id_map.get(ats_emp_id, ats_emp_id)

            # Check for duplicate by employee + date + type
            existing = conn.execute(
                """SELECT id FROM ats_infractions
                   WHERE employee_id = ? AND infraction_date = ? AND infraction_type = ?""",
                (
                    hub_officer_id,
                    inf.get("infraction_date", ""),
                    inf.get("infraction_type", ""),
                ),
            ).fetchone()

            if existing:
                counts["infractions_skipped"] += 1
                continue

            conn.execute(
                """INSERT INTO ats_infractions
                   (employee_id, infraction_type, infraction_date, points_assigned,
                    description, site, entered_by, discipline_triggered,
                    is_emergency_exemption, exemption_approved,
                    documentation_provided, point_expiry_date,
                    points_active, edited, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    hub_officer_id,
                    inf.get("infraction_type", ""),
                    inf.get("infraction_date", ""),
                    inf.get("points_assigned", 0) or 0,
                    inf.get("description", ""),
                    inf.get("site", ""),
                    inf.get("entered_by", ""),
                    inf.get("discipline_triggered", ""),
                    1 if inf.get("is_emergency_exemption") else 0,
                    1 if inf.get("exemption_approved") else 0,
                    1 if inf.get("documentation_provided") else 0,
                    inf.get("point_expiry_date", ""),
                    1 if inf.get("points_active", True) else 0,
                    1 if inf.get("edited") else 0,
                    _ts_to_iso(inf.get("created_at")),
                    _ts_to_iso(inf.get("updated_at")),
                ),
            )
            counts["infractions_imported"] += 1
        except Exception as e:
            counts["errors"] += 1
            print(f"  [ERROR] Infraction: {e}")

    conn.commit()
    print(f"  Imported: {counts['infractions_imported']}, Skipped: {counts['infractions_skipped']}")

    # ── Employment Reviews ────────────────────────────────────────────
    print(f"\n[Reviews] Importing {len(data.get('employment_reviews', []))} reviews...")
    for rev in data.get("employment_reviews", []):
        try:
            ats_emp_id = rev.get("employee_id", "")
            hub_officer_id = emp_id_map.get(ats_emp_id, ats_emp_id)

            # Check duplicate by employee + triggered date
            existing = conn.execute(
                """SELECT id FROM ats_employment_reviews
                   WHERE employee_id = ? AND triggered_date = ?""",
                (hub_officer_id, rev.get("triggered_date", "")),
            ).fetchone()

            if existing:
                counts["reviews_skipped"] += 1
                continue

            # Map status values
            status = rev.get("review_status", "Pending") or "Pending"
            status = status.title() if status.lower() in ("pending", "completed") else status

            conn.execute(
                """INSERT INTO ats_employment_reviews
                   (employee_id, triggered_date, points_at_trigger,
                    review_status, reviewed_by, review_date, outcome,
                    reviewer_notes, supervisor_comments,
                    points_after_outcome, locked, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    hub_officer_id,
                    rev.get("triggered_date", ""),
                    rev.get("points_at_trigger", 0) or 0,
                    status,
                    rev.get("reviewed_by", "") or "",
                    rev.get("review_date", "") or "",
                    rev.get("outcome", "") or "",
                    rev.get("reviewer_notes", ""),
                    rev.get("supervisor_comments", ""),
                    rev.get("points_after_outcome", 0) or 0,
                    1 if rev.get("locked") else 0,
                    _ts_to_iso(rev.get("created_at")),
                    _ts_to_iso(rev.get("updated_at")),
                ),
            )
            counts["reviews_imported"] += 1
        except Exception as e:
            counts["errors"] += 1
            print(f"  [ERROR] Review: {e}")

    conn.commit()
    print(f"  Imported: {counts['reviews_imported']}, Skipped: {counts['reviews_skipped']}")

    conn.close()

    # ── Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  IMPORT COMPLETE")
    print("=" * 60)
    print(f"  Officers:     {counts['officers_imported']} imported, {counts['officers_skipped']} skipped")
    print(f"  Sites:        {counts['sites_imported']} imported, {counts['sites_skipped']} skipped")
    print(f"  Infractions:  {counts['infractions_imported']} imported, {counts['infractions_skipped']} skipped")
    print(f"  Reviews:      {counts['reviews_imported']} imported, {counts['reviews_skipped']} skipped")
    print(f"  Errors:       {counts['errors']}")
    print("=" * 60)

    return counts


if __name__ == "__main__":
    # Find JSON file
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        # Look in common locations
        candidates = [
            os.path.join(os.path.dirname(__file__), "cerasus_ats_export.json"),
            os.path.expanduser("~/Downloads/cerasus_ats_export.json"),
            os.path.expanduser("~/Desktop/cerasus_ats_export.json"),
        ]
        path = None
        for c in candidates:
            if os.path.isfile(c):
                path = c
                break

    if not path or not os.path.isfile(path):
        print("ERROR: Could not find cerasus_ats_export.json")
        print("Usage: python import_ats_data.py <path_to_json>")
        sys.exit(1)

    import_data(path)
