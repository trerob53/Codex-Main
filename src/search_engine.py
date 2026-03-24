"""
Cerasus Hub -- Cross-Module Search Engine
Searches across all modules (officers, infractions, DA records, audit log)
and returns unified results for the hub-level search bar.
"""

from src.database import get_conn


# Module color mapping for search result display
MODULE_COLORS = {
    "hub":          "#374151",
    "operations":   "#2563EB",
    "uniforms":     "#7C3AED",
    "attendance":   "#059669",
    "training":     "#D97706",
    "da_generator": "#DC2626",
    "audit":        "#374151",
}


def search_all(query: str, limit: int = 50) -> list[dict]:
    """Search across all modules for a query string.

    Returns list of results with keys:
        module, type, title, subtitle, record_id, officer_id, color
    """
    if not query or len(query.strip()) < 2:
        return []

    query = query.strip()
    like = f"%{query}%"
    results: list[dict] = []

    conn = get_conn()

    # 1. Officers table
    try:
        rows = conn.execute(
            """SELECT officer_id, name, employee_id, email, site, job_title, status
               FROM officers
               WHERE name LIKE ? OR employee_id LIKE ? OR email LIKE ?
               LIMIT ?""",
            (like, like, like, limit),
        ).fetchall()
        for r in rows:
            r = dict(r)
            name = r.get("name", "")
            emp_id = r.get("employee_id", "")
            title = f"{name} ({emp_id})" if emp_id else name
            site = r.get("site", "")
            job = r.get("job_title", "")
            parts = [p for p in [job, f"at {site}" if site else ""] if p]
            subtitle = " ".join(parts) if parts else r.get("status", "")
            results.append({
                "module": "hub",
                "type": "officer",
                "title": title,
                "subtitle": subtitle,
                "record_id": r["officer_id"],
                "officer_id": r["officer_id"],
                "color": MODULE_COLORS["hub"],
            })
    except Exception:
        pass

    # 2. Infractions table (ats_infractions)
    try:
        rows = conn.execute(
            """SELECT i.id, i.infraction_type, i.description, i.site,
                      i.infraction_date, i.employee_id,
                      o.name AS officer_name
               FROM ats_infractions i
               LEFT JOIN officers o ON o.officer_id = i.employee_id
               WHERE i.description LIKE ? OR i.site LIKE ?
                     OR i.infraction_type LIKE ? OR o.name LIKE ?
               LIMIT ?""",
            (like, like, like, like, limit),
        ).fetchall()
        for r in rows:
            r = dict(r)
            inf_type = (r.get("infraction_type") or "Infraction").replace("_", " ").title()
            officer_name = r.get("officer_name") or ""
            title = f"{inf_type} - {officer_name}" if officer_name else inf_type
            date = (r.get("infraction_date") or "")[:10]
            site = r.get("site") or ""
            subtitle_parts = [p for p in [date, f"at {site}" if site else ""] if p]
            subtitle = " ".join(subtitle_parts)
            results.append({
                "module": "attendance",
                "type": "infraction",
                "title": title,
                "subtitle": subtitle,
                "record_id": r.get("id"),
                "officer_id": r.get("employee_id"),
                "color": MODULE_COLORS["attendance"],
            })
    except Exception:
        pass

    # 3. DA records (da_records)
    try:
        rows = conn.execute(
            """SELECT id, employee_name, employee_officer_id, incident_narrative,
                      violation_type, discipline_level, status, created_at
               FROM da_records
               WHERE employee_name LIKE ? OR incident_narrative LIKE ?
                     OR violation_type LIKE ?
               LIMIT ?""",
            (like, like, like, limit),
        ).fetchall()
        for r in rows:
            r = dict(r)
            level = r.get("discipline_level") or "DA"
            # Abbreviate discipline level
            abbrev = {
                "Verbal Warning": "VW",
                "Written Warning": "WW",
                "Final Written Warning": "FWW",
                "Suspension": "SUSP",
                "Termination": "TERM",
            }
            short = abbrev.get(level, level)
            name = r.get("employee_name") or ""
            title = f"{short} - {name}" if name else short
            date = (r.get("created_at") or "")[:10]
            status = r.get("status") or ""
            subtitle = f"{level} - {date}" if date else level
            if status:
                subtitle += f" ({status})"
            results.append({
                "module": "da_generator",
                "type": "da",
                "title": title,
                "subtitle": subtitle,
                "record_id": r.get("id"),
                "officer_id": r.get("employee_officer_id"),
                "color": MODULE_COLORS["da_generator"],
            })
    except Exception:
        pass

    # 4. Audit log (last 200 entries only)
    try:
        rows = conn.execute(
            """SELECT id, event_type, username, details, module_name, timestamp
               FROM audit_log
               WHERE details LIKE ? OR username LIKE ?
               ORDER BY id DESC
               LIMIT ?""",
            (like, like, min(limit, 200)),
        ).fetchall()
        for r in rows:
            r = dict(r)
            event = r.get("event_type") or ""
            user = r.get("username") or ""
            title = f"{event} by {user}" if user else event
            details = r.get("details") or ""
            subtitle = details[:80]
            results.append({
                "module": "audit",
                "type": "event",
                "title": title,
                "subtitle": subtitle,
                "record_id": r.get("id"),
                "officer_id": None,
                "color": MODULE_COLORS["audit"],
            })
    except Exception:
        pass

    conn.close()

    # Trim to overall limit
    return results[:limit]
