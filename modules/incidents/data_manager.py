"""
Cerasus Hub -- Incidents Module: Data Manager
SQLite-backed CRUD for inc_incidents.
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
    get_officer_names,
    get_all_sites,
    get_site_names,
)

# ── Constants ─────────────────────────────────────────────────────────

INCIDENT_TYPES = [
    "Trespass", "Theft", "Vandalism", "Assault", "Medical",
    "Fire/Alarm", "Suspicious Activity", "Policy Violation",
    "Vehicle Incident", "Other",
]

SEVERITY_LEVELS = ["Low", "Medium", "High", "Critical"]

STATUS_OPTIONS = ["Open", "Under Investigation", "Resolved", "Closed"]


# ── Helpers ───────────────────────────────────────────────────────────

def _gen_incident_id() -> str:
    """Generate an incident ID like INC-20260318-XXXXXXXX."""
    date_part = datetime.now().strftime("%Y%m%d")
    rand_part = secrets.token_hex(4).upper()
    return f"INC-{date_part}-{rand_part}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Incidents CRUD ────────────────────────────────────────────────────

def get_all_incidents() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM inc_incidents ORDER BY incident_date DESC, incident_time DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_incident(incident_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM inc_incidents WHERE incident_id = ?", (incident_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def search_incidents(query: str) -> list:
    conn = get_conn()
    q = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM inc_incidents
           WHERE title LIKE ? OR description LIKE ? OR incident_type LIKE ?
                 OR site LIKE ? OR officer_name LIKE ? OR incident_id LIKE ?
                 OR severity LIKE ? OR status LIKE ?
           ORDER BY incident_date DESC""",
        (q, q, q, q, q, q, q, q),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_incident(fields: dict, created_by: str = "") -> str:
    """Create an incident. Returns incident_id."""
    iid = fields.get("incident_id") or _gen_incident_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO inc_incidents
           (incident_id, officer_id, officer_name, site, incident_date, incident_time,
            incident_type, severity, status, title, description, location_detail,
            persons_involved, witnesses, police_called, police_report_number,
            injuries_reported, injury_details, property_damage, damage_description,
            immediate_action, resolution, resolved_by, resolved_date,
            assigned_to, follow_up_required, follow_up_notes, attachments,
            created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            iid,
            fields.get("officer_id", ""),
            fields.get("officer_name", ""),
            fields.get("site", ""),
            fields.get("incident_date", ""),
            fields.get("incident_time", ""),
            fields.get("incident_type", ""),
            fields.get("severity", "Low"),
            fields.get("status", "Open"),
            fields.get("title", ""),
            fields.get("description", ""),
            fields.get("location_detail", ""),
            fields.get("persons_involved", "[]"),
            fields.get("witnesses", ""),
            int(fields.get("police_called", 0)),
            fields.get("police_report_number", ""),
            int(fields.get("injuries_reported", 0)),
            fields.get("injury_details", ""),
            int(fields.get("property_damage", 0)),
            fields.get("damage_description", ""),
            fields.get("immediate_action", ""),
            fields.get("resolution", ""),
            fields.get("resolved_by", ""),
            fields.get("resolved_date", ""),
            fields.get("assigned_to", ""),
            int(fields.get("follow_up_required", 0)),
            fields.get("follow_up_notes", ""),
            fields.get("attachments", "[]"),
            created_by,
            created_by,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return iid


def update_incident(incident_id: str, fields: dict, updated_by: str = "") -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM inc_incidents WHERE incident_id = ?", (incident_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    allowed = [
        "officer_id", "officer_name", "site", "incident_date", "incident_time",
        "incident_type", "severity", "status", "title", "description",
        "location_detail", "persons_involved", "witnesses",
        "police_called", "police_report_number",
        "injuries_reported", "injury_details",
        "property_damage", "damage_description",
        "immediate_action", "resolution", "resolved_by", "resolved_date",
        "assigned_to", "follow_up_required", "follow_up_notes", "attachments",
    ]
    updates = []
    params = []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])

    if updates:
        updates.append("updated_by = ?")
        params.append(updated_by)
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(incident_id)
        conn.execute(
            f"UPDATE inc_incidents SET {', '.join(updates)} WHERE incident_id = ?",
            params,
        )
        conn.commit()

    conn.close()
    return True


def delete_incident(incident_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM inc_incidents WHERE incident_id = ?", (incident_id,)
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


# ── Filtered Queries ──────────────────────────────────────────────────

def get_incidents_by_status(status: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM inc_incidents WHERE status = ? ORDER BY incident_date DESC",
        (status,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_incidents_by_site(site: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM inc_incidents WHERE site = ? ORDER BY incident_date DESC",
        (site,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_incidents_by_officer(officer_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM inc_incidents WHERE officer_id = ? ORDER BY incident_date DESC",
        (officer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Dashboard / Summaries ────────────────────────────────────────────

def get_dashboard_summary() -> dict:
    """Aggregate counts for the incidents dashboard."""
    conn = get_conn()

    # Count by status
    status_rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM inc_incidents GROUP BY status"
    ).fetchall()
    status_counts = {r["status"]: r["cnt"] for r in status_rows}

    total = sum(status_counts.values())

    # Count by severity
    sev_rows = conn.execute(
        "SELECT severity, COUNT(*) as cnt FROM inc_incidents GROUP BY severity"
    ).fetchall()
    severity_counts = {r["severity"]: r["cnt"] for r in sev_rows}

    # Count by type
    type_rows = conn.execute(
        "SELECT incident_type, COUNT(*) as cnt FROM inc_incidents GROUP BY incident_type ORDER BY cnt DESC"
    ).fetchall()
    type_counts = {r["incident_type"]: r["cnt"] for r in type_rows}

    # Count by site
    site_rows = conn.execute(
        "SELECT site, COUNT(*) as cnt FROM inc_incidents WHERE site != '' GROUP BY site ORDER BY cnt DESC"
    ).fetchall()
    site_counts = {r["site"]: r["cnt"] for r in site_rows}

    # Recent incidents (last 20)
    recent = conn.execute(
        "SELECT * FROM inc_incidents ORDER BY incident_date DESC, incident_time DESC LIMIT 20"
    ).fetchall()

    conn.close()

    return {
        "total": total,
        "status_counts": status_counts,
        "severity_counts": severity_counts,
        "type_counts": type_counts,
        "site_counts": site_counts,
        "recent": [dict(r) for r in recent],
    }


def get_investigation_queue() -> list:
    """Return incidents that are Open or Under Investigation, sorted by severity (Critical first)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM inc_incidents
           WHERE status IN ('Open', 'Under Investigation')
           ORDER BY
               CASE severity
                   WHEN 'Critical' THEN 1
                   WHEN 'High' THEN 2
                   WHEN 'Medium' THEN 3
                   WHEN 'Low' THEN 4
                   ELSE 5
               END,
               incident_date DESC, incident_time DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── CSV Export ────────────────────────────────────────────────────────

def export_incidents_csv() -> str:
    """Export all incidents to CSV text."""
    rows = get_all_incidents()
    if not rows:
        return ""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
