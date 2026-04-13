"""
Cerasus Hub -- Operations Module: Data Manager
SQLite-backed CRUD for ops_records, ops_assignments, ops_pto_entries,
and the siloed ops_flex_team table (separate from the hub-wide officers).
"""

import csv
import io
import secrets
from datetime import datetime, timezone

from src.database import get_conn

# ── Shared site helpers (sites are still hub-wide) ────────────────────
from src.shared_data import (
    get_all_sites,
    get_site,
    create_site,
    update_site,
    delete_site,
    get_site_names,
)


# Re-export for callers that do `from data_manager import get_active_sites`
def get_active_sites() -> list:
    """Return sites with status = Active."""
    return get_all_sites(status_filter="Active")


def search_sites(query: str) -> list:
    """Search sites by name, city, or address."""
    conn = get_conn()
    q = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM sites WHERE name LIKE ? OR city LIKE ? OR address LIKE ?
           ORDER BY name""",
        (q, q, q),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════
#  Siloed Flex Team — ops_flex_team table (NOT shared officers)
# ═══════════════════════════════════════════════════════════════════════

def _ensure_flex_table():
    """Safety net: create ops_flex_team if migration hasn't run yet."""
    conn = get_conn()
    try:
        conn.execute("SELECT 1 FROM ops_flex_team LIMIT 1")
    except Exception:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ops_flex_team (
                member_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                first_name TEXT DEFAULT '',
                last_name TEXT DEFAULT '',
                employee_id TEXT DEFAULT '',
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                job_title TEXT DEFAULT 'Flex Officer',
                role TEXT DEFAULT 'Flex Officer',
                site TEXT DEFAULT '',
                weekly_hours TEXT DEFAULT '40',
                trained_sites TEXT DEFAULT '[]',
                approved_sites TEXT DEFAULT '[]',
                anchor_sites TEXT DEFAULT '[]',
                hire_date TEXT DEFAULT '',
                status TEXT DEFAULT 'Active',
                notes TEXT DEFAULT '',
                created_by TEXT DEFAULT '',
                updated_by TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            );
        """)
        conn.commit()
    conn.close()


_ensure_flex_table()


def _add_officer_id_alias(d: dict) -> dict:
    """Add officer_id alias and parse JSON list fields for existing pages."""
    import json
    d["officer_id"] = d.get("member_id", "")
    for key in ("trained_sites", "approved_sites", "anchor_sites"):
        val = d.get(key, "[]")
        if isinstance(val, str):
            try:
                d[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                d[key] = []
    return d


def get_ops_officers(active_only: bool = True) -> list:
    """Return officers for Operations pages.

    Queries ops_flex_team first; if empty, falls back to the shared
    officers table so dropdowns are never unpopulated.
    """
    conn = get_conn()
    if active_only:
        rows = conn.execute(
            "SELECT * FROM ops_flex_team WHERE status = 'Active' ORDER BY name"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM ops_flex_team ORDER BY name").fetchall()
    if rows:
        conn.close()
        return [_add_officer_id_alias(dict(r)) for r in rows]
    # Fallback to shared officers table
    if active_only:
        rows = conn.execute(
            "SELECT * FROM officers WHERE status = 'Active' ORDER BY name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM officers WHERE status != 'Deleted' ORDER BY name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ops_officer_names() -> list:
    """Return name list for Operations officers."""
    return [o.get("name", "") for o in get_ops_officers() if o.get("name")]


def get_ops_officer(member_id: str) -> dict | None:
    """Fetch a single flex team member by ID."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM ops_flex_team WHERE member_id = ?", (member_id,)
    ).fetchone()
    conn.close()
    return _add_officer_id_alias(dict(row)) if row else None


def get_officer(member_id: str) -> dict | None:
    """Alias for get_ops_officer (compatibility)."""
    return get_ops_officer(member_id)


def _json_list(val) -> str:
    """Ensure a value is stored as a JSON list string."""
    import json
    if isinstance(val, list):
        return json.dumps(val)
    if isinstance(val, str) and val:
        return val
    return "[]"


def create_ops_officer(fields: dict, created_by: str = "") -> str:
    """Add a member to the flex team. Returns member_id."""
    mid = fields.get("member_id") or secrets.token_hex(12)
    now = datetime.now(timezone.utc).isoformat()
    name = fields.get("name", "")
    if not name and (fields.get("first_name") or fields.get("last_name")):
        name = f"{fields.get('first_name', '')} {fields.get('last_name', '')}".strip()
    conn = get_conn()
    conn.execute(
        """INSERT INTO ops_flex_team
           (member_id, name, first_name, last_name, employee_id,
            email, phone, job_title, role, site,
            weekly_hours, trained_sites, approved_sites, anchor_sites,
            hire_date, status, notes,
            created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (mid, name,
         fields.get("first_name", ""), fields.get("last_name", ""),
         fields.get("employee_id", ""),
         fields.get("email", ""), fields.get("phone", ""),
         fields.get("job_title", "Flex Officer"),
         fields.get("role", "Flex Officer"),
         fields.get("site", ""),
         fields.get("weekly_hours", "40"),
         _json_list(fields.get("trained_sites", "[]")),
         _json_list(fields.get("approved_sites", "[]")),
         _json_list(fields.get("anchor_sites", "[]")),
         fields.get("hire_date", ""),
         fields.get("status", "Active"),
         fields.get("notes", ""),
         created_by, created_by, now, now),
    )
    conn.commit()
    conn.close()
    return mid


def update_ops_officer(member_id: str, fields: dict, updated_by: str = "") -> bool:
    """Update a flex team member."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM ops_flex_team WHERE member_id = ?", (member_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    json_fields = {"trained_sites", "approved_sites", "anchor_sites"}
    allowed = [
        "name", "first_name", "last_name", "employee_id",
        "email", "phone", "job_title", "role", "site",
        "weekly_hours", "trained_sites", "approved_sites", "anchor_sites",
        "hire_date", "status", "notes",
    ]
    updates, params = [], []
    for key in allowed:
        if key in fields:
            val = fields[key]
            if key in json_fields:
                val = _json_list(val)
            updates.append(f"{key} = ?")
            params.append(val)
    if updates:
        updates.append("updated_by = ?")
        params.append(updated_by)
        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(member_id)
        conn.execute(
            f"UPDATE ops_flex_team SET {', '.join(updates)} WHERE member_id = ?", params
        )
        conn.commit()
    conn.close()
    return True


def delete_ops_officer(member_id: str) -> bool:
    """Remove a flex team member."""
    conn = get_conn()
    cur = conn.execute("DELETE FROM ops_flex_team WHERE member_id = ?", (member_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def search_ops_officers(query: str) -> list:
    """Search the flex team by name or employee_id."""
    conn = get_conn()
    q = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM ops_flex_team
           WHERE name LIKE ? OR employee_id LIKE ? OR first_name LIKE ? OR last_name LIKE ?
           ORDER BY name""",
        (q, q, q, q),
    ).fetchall()
    conn.close()
    return [_add_officer_id_alias(dict(r)) for r in rows]


# ── Compatibility aliases (pages_ops.py calls these names) ────────────
create_officer = create_ops_officer
update_officer = update_ops_officer
delete_officer = delete_ops_officer
search_officers = search_ops_officers


def _is_ops_officer(officer: dict) -> bool:
    """Compatibility stub — all ops_flex_team members are ops officers by definition."""
    return True


# ── Helpers ───────────────────────────────────────────────────────────

def _gen_id() -> str:
    return secrets.token_hex(4)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Records CRUD ──────────────────────────────────────────────────────

def get_all_records() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM ops_records ORDER BY date DESC, created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_record(record_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM ops_records WHERE record_id = ?", (record_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def search_records(query: str) -> list:
    conn = get_conn()
    q = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM ops_records
           WHERE employee_name LIKE ? OR site_name LIKE ? OR status LIKE ?
                 OR priority LIKE ? OR notes LIKE ?
           ORDER BY date DESC""",
        (q, q, q, q, q),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_record(fields: dict, created_by: str = "") -> str:
    """Create an ops record. Returns record_id."""
    rid = fields.get("record_id") or _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO ops_records
           (record_id, employee_name, site_name, date, status, priority,
            notes, created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            rid,
            fields.get("employee_name", ""),
            fields.get("site_name", ""),
            fields.get("date", ""),
            fields.get("status", "Open"),
            fields.get("priority", "Normal"),
            fields.get("notes", ""),
            created_by,
            created_by,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return rid


def update_record(record_id: str, fields: dict, updated_by: str = "") -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM ops_records WHERE record_id = ?", (record_id,)).fetchone()
    if not row:
        conn.close()
        return False

    allowed = ["employee_name", "site_name", "date", "status", "priority", "notes"]
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
        params.append(record_id)
        conn.execute(
            f"UPDATE ops_records SET {', '.join(updates)} WHERE record_id = ?", params
        )
        conn.commit()

    conn.close()
    return True


def delete_record(record_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM ops_records WHERE record_id = ?", (record_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def get_summary() -> dict:
    """Return counts of records grouped by status."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM ops_records GROUP BY status"
    ).fetchall()
    conn.close()
    return {r["status"]: r["cnt"] for r in rows}


# ── Assignments CRUD ──────────────────────────────────────────────────

def get_all_assignments() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ops_assignments ORDER BY date, start_time"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_assignment(assignment_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM ops_assignments WHERE assignment_id = ?", (assignment_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def search_assignments(query: str) -> list:
    conn = get_conn()
    q = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM ops_assignments
           WHERE officer_name LIKE ? OR site_name LIKE ? OR status LIKE ?
                 OR assignment_type LIKE ? OR notes LIKE ?
           ORDER BY date, start_time""",
        (q, q, q, q, q),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_assignment(fields: dict, created_by: str = "") -> str:
    """Create an assignment. Returns assignment_id."""
    aid = fields.get("assignment_id") or _gen_id()
    now = _now()

    start = fields.get("start_time", "")
    end = fields.get("end_time", "")
    hours = fields.get("hours") or str(calculate_shift_hours(start, end))

    conn = get_conn()
    conn.execute(
        """INSERT INTO ops_assignments
           (assignment_id, officer_name, site_name, date, start_time, end_time,
            hours, assignment_type, status, notes,
            created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            aid,
            fields.get("officer_name", ""),
            fields.get("site_name", ""),
            fields.get("date", ""),
            start,
            end,
            hours,
            fields.get("assignment_type", "Billable"),
            fields.get("status", "Scheduled"),
            fields.get("notes", ""),
            created_by,
            created_by,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return aid


def update_assignment(assignment_id: str, fields: dict, updated_by: str = "") -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM ops_assignments WHERE assignment_id = ?", (assignment_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    allowed = [
        "officer_name", "site_name", "date", "start_time", "end_time",
        "hours", "assignment_type", "status", "notes",
    ]
    updates = []
    params = []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])

    # Recalculate hours if times changed
    if "start_time" in fields or "end_time" in fields:
        current = get_assignment(assignment_id) or {}
        st = fields.get("start_time", current.get("start_time", ""))
        et = fields.get("end_time", current.get("end_time", ""))
        if "hours" not in fields:
            updates.append("hours = ?")
            params.append(str(calculate_shift_hours(st, et)))

    if updates:
        updates.append("updated_by = ?")
        params.append(updated_by)
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(assignment_id)
        conn.execute(
            f"UPDATE ops_assignments SET {', '.join(updates)} WHERE assignment_id = ?",
            params,
        )
        conn.commit()

    conn.close()
    return True


def delete_assignment(assignment_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM ops_assignments WHERE assignment_id = ?", (assignment_id,)
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def get_assignments_for_week(start_date: str, end_date: str) -> list:
    """Return assignments whose date falls within [start_date, end_date]."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM ops_assignments
           WHERE date >= ? AND date <= ?
           ORDER BY date, start_time""",
        (start_date, end_date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_assignments_for_officer(officer_name: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ops_assignments WHERE officer_name = ? ORDER BY date, start_time",
        (officer_name,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_assignments_for_site(site_name: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ops_assignments WHERE site_name = ? ORDER BY date, start_time",
        (site_name,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def calculate_shift_hours(start_time: str, end_time: str) -> float:
    """Calculate hours between two time strings (handles HH:MM and HHMM). Returns 0 on bad input."""
    if not start_time or not end_time:
        return 0.0
    try:
        s_str = _normalize_time(str(start_time))
        e_str = _normalize_time(str(end_time))
        fmt = "%H:%M"
        s = datetime.strptime(s_str, fmt)
        e = datetime.strptime(e_str, fmt)
        delta = (e - s).total_seconds()
        if delta < 0:
            delta += 86400  # overnight shift
        return round(delta / 3600, 2)
    except (ValueError, AttributeError):
        return 0.0


def detect_conflicts(
    officer_name: str,
    date: str,
    start_time: str,
    end_time: str,
    exclude_id: str = "",
) -> list:
    """Return assignments that overlap with the proposed shift for the same officer/date."""
    conn = get_conn()
    if exclude_id:
        rows = conn.execute(
            """SELECT * FROM ops_assignments
               WHERE officer_name = ? AND date = ? AND assignment_id != ?
               ORDER BY start_time""",
            (officer_name, date, exclude_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM ops_assignments
               WHERE officer_name = ? AND date = ?
               ORDER BY start_time""",
            (officer_name, date),
        ).fetchall()
    conn.close()

    def _time_to_minutes(t: str) -> int:
        """Convert HH:MM or H:MM time string to minutes since midnight."""
        try:
            parts = t.strip().split(":")
            return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            return -1

    conflicts = []
    new_start = _time_to_minutes(start_time)
    new_end = _time_to_minutes(end_time)
    if new_start < 0 or new_end < 0:
        return conflicts

    for r in rows:
        existing = dict(r)
        ex_start = _time_to_minutes(existing.get("start_time", ""))
        ex_end = _time_to_minutes(existing.get("end_time", ""))
        if ex_start < 0 or ex_end < 0:
            continue
        # Overlap check: new start < existing end AND new end > existing start
        if new_start < ex_end and new_end > ex_start:
            conflicts.append(existing)
    return conflicts


# ── PTO CRUD ──────────────────────────────────────────────────────────

def create_pto(fields: dict, created_by: str = "") -> str:
    """Create a PTO entry. Returns pto_id."""
    pid = fields.get("pto_id") or _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO ops_pto_entries
           (pto_id, officer_name, start_date, end_date, pto_type, status,
            notes, created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pid,
            fields.get("officer_name", ""),
            fields.get("start_date", ""),
            fields.get("end_date", ""),
            fields.get("pto_type", "Unavailable"),
            fields.get("status", "Approved"),
            fields.get("notes", ""),
            created_by,
            created_by,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return pid


def get_all_pto() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ops_pto_entries ORDER BY start_date DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pto(pto_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM ops_pto_entries WHERE pto_id = ?", (pto_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_pto(pto_id: str, fields: dict, updated_by: str = "") -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM ops_pto_entries WHERE pto_id = ?", (pto_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    allowed = ["officer_name", "start_date", "end_date", "pto_type", "status", "notes"]
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
        params.append(pto_id)
        conn.execute(
            f"UPDATE ops_pto_entries SET {', '.join(updates)} WHERE pto_id = ?", params
        )
        conn.commit()

    conn.close()
    return True


def delete_pto(pto_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM ops_pto_entries WHERE pto_id = ?", (pto_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def get_officer_pto_for_date(officer_name: str, date: str) -> list:
    """Return PTO entries that cover the given date for an officer."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM ops_pto_entries
           WHERE officer_name = ? AND start_date <= ? AND end_date >= ?
           ORDER BY start_date""",
        (officer_name, date, date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_officer_availability(officer_name: str, date: str) -> dict:
    """Check an officer's availability for a given date.

    Returns a dict with:
        has_pto (bool): whether the officer has PTO covering that date
        pto_entries (list): PTO entries for that date
        assignments (list): existing assignments for that date
        total_hours (float): total hours already scheduled that day
        available (bool): True if no PTO and no assignments
    """
    pto_entries = get_officer_pto_for_date(officer_name, date)
    has_pto = len(pto_entries) > 0

    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM ops_assignments
           WHERE officer_name = ? AND date = ?
           ORDER BY start_time""",
        (officer_name, date),
    ).fetchall()
    conn.close()
    assignments = [dict(r) for r in rows]

    total_hours = 0.0
    for a in assignments:
        start = a.get("start_time", "")
        end = a.get("end_time", "")
        if start and end:
            total_hours += calculate_shift_hours(start, end)
        else:
            try:
                total_hours += float(a.get("hours", 0))
            except (ValueError, TypeError):
                pass

    return {
        "has_pto": has_pto,
        "pto_entries": pto_entries,
        "assignments": assignments,
        "total_hours": round(total_hours, 2),
        "available": not has_pto and len(assignments) == 0,
    }


# ── Dashboard ─────────────────────────────────────────────────────────

# ── Incidents CRUD ────────────────────────────────────────────────────

def create_incident(fields: dict, created_by: str = "") -> str:
    """Create an incident report. Returns incident_id."""
    iid = fields.get("incident_id") or _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO ops_incidents
           (incident_id, site, incident_date, incident_time, incident_type,
            severity, reporting_officer, reporting_officer_id, description,
            persons_involved, actions_taken, police_called, police_report_number,
            medical_required, property_damage, witness_names, supervisor_notified,
            supervisor_name, status, resolution, created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            iid,
            fields.get("site", ""),
            fields.get("incident_date", ""),
            fields.get("incident_time", ""),
            fields.get("incident_type", ""),
            fields.get("severity", "low"),
            fields.get("reporting_officer", ""),
            fields.get("reporting_officer_id", ""),
            fields.get("description", ""),
            fields.get("persons_involved", ""),
            fields.get("actions_taken", ""),
            1 if fields.get("police_called") else 0,
            fields.get("police_report_number", ""),
            1 if fields.get("medical_required") else 0,
            1 if fields.get("property_damage") else 0,
            fields.get("witness_names", ""),
            1 if fields.get("supervisor_notified") else 0,
            fields.get("supervisor_name", ""),
            fields.get("status", "Open"),
            fields.get("resolution", ""),
            created_by,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return iid


def get_all_incidents(status_filter: str = "", site_filter: str = "",
                      date_from: str = "", date_to: str = "") -> list:
    """Return incidents, optionally filtered by status, site, and/or date range."""
    conn = get_conn()
    query = "SELECT * FROM ops_incidents WHERE 1=1"
    params = []
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if site_filter:
        query += " AND site = ?"
        params.append(site_filter)
    if date_from:
        query += " AND incident_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND incident_date <= ?"
        params.append(date_to)
    query += " ORDER BY incident_date DESC, created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_incident(incident_id: str) -> dict | None:
    """Return a single incident by ID."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM ops_incidents WHERE incident_id = ?", (incident_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_incident(incident_id: str, fields: dict, updated_by: str = "") -> bool:
    """Update an incident report. Returns True on success."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM ops_incidents WHERE incident_id = ?", (incident_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    allowed = [
        "site", "incident_date", "incident_time", "incident_type", "severity",
        "reporting_officer", "reporting_officer_id", "description",
        "persons_involved", "actions_taken", "police_called", "police_report_number",
        "medical_required", "property_damage", "witness_names", "supervisor_notified",
        "supervisor_name", "status", "resolution",
    ]
    bool_fields = {"police_called", "medical_required", "property_damage", "supervisor_notified"}
    updates = []
    params = []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            if key in bool_fields:
                params.append(1 if fields[key] else 0)
            else:
                params.append(fields[key])

    if updates:
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(incident_id)
        conn.execute(
            f"UPDATE ops_incidents SET {', '.join(updates)} WHERE incident_id = ?",
            params,
        )
        conn.commit()

    conn.close()
    return True


def get_dashboard_summary() -> dict:
    """Aggregate counts for the operations dashboard."""
    conn = get_conn()

    # Record stats
    rec_rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM ops_records GROUP BY status"
    ).fetchall()
    record_counts = {r["status"]: r["cnt"] for r in rec_rows}
    total_records = sum(record_counts.values())

    # Assignment stats
    asn_total = conn.execute("SELECT COUNT(*) as cnt FROM ops_assignments").fetchone()["cnt"]
    asn_scheduled = conn.execute(
        "SELECT COUNT(*) as cnt FROM ops_assignments WHERE status = 'Scheduled'"
    ).fetchone()["cnt"]

    # Officer count (from ops_flex_team, siloed)
    try:
        officer_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM ops_flex_team WHERE status = 'Active'"
        ).fetchone()["cnt"]
    except Exception:
        officer_count = 0
    site_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM sites WHERE status = 'Active'"
    ).fetchone()["cnt"]

    # PTO stats
    pto_total = conn.execute("SELECT COUNT(*) as cnt FROM ops_pto_entries").fetchone()["cnt"]
    pto_approved = conn.execute(
        "SELECT COUNT(*) as cnt FROM ops_pto_entries WHERE status = 'Approved'"
    ).fetchone()["cnt"]

    conn.close()

    return {
        "total_records": total_records,
        "record_counts": record_counts,
        "total_assignments": asn_total,
        "scheduled_assignments": asn_scheduled,
        "active_officers": officer_count,
        "active_sites": site_count,
        "total_pto": pto_total,
        "approved_pto": pto_approved,
    }


# ── CSV Import / Export ───────────────────────────────────────────────

def import_officers_csv(csv_text: str, created_by: str = "") -> dict:
    """Import flex team members from CSV text into ops_flex_team. Returns {imported, skipped, errors}."""
    reader = csv.DictReader(io.StringIO(csv_text))
    imported, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):
        try:
            name = row.get("name", "").strip()
            if not name:
                skipped += 1
                continue
            create_ops_officer(dict(row), created_by=created_by)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")
    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_sites_csv(csv_text: str, created_by: str = "") -> dict:
    """Import sites from CSV text. Returns {imported, skipped, errors}."""
    reader = csv.DictReader(io.StringIO(csv_text))
    imported, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):
        try:
            name = row.get("name", "").strip()
            if not name:
                skipped += 1
                continue
            create_site(dict(row), created_by=created_by)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")
    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_records_csv(csv_text: str, created_by: str = "") -> dict:
    """Import ops records from CSV text. Returns {imported, skipped, errors}."""
    reader = csv.DictReader(io.StringIO(csv_text))
    imported, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):
        try:
            if not row.get("employee_name", "").strip() and not row.get("site_name", "").strip():
                skipped += 1
                continue
            create_record(dict(row), created_by=created_by)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")
    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_assignments_csv(csv_text: str, created_by: str = "") -> dict:
    """Import assignments from CSV text.

    Expected columns: officer_name, site_name, date, start_time, end_time, assignment_type
    Returns {imported, skipped, errors}.
    """
    import re
    reader = csv.DictReader(io.StringIO(csv_text))
    imported, skipped, errors = 0, 0, []
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    time_re = re.compile(r"^\d{2}:\d{2}$")

    for i, row in enumerate(reader, start=2):
        try:
            officer = row.get("officer_name", "").strip()
            site = row.get("site_name", "").strip()
            dt = row.get("date", "").strip()
            st = row.get("start_time", "").strip()
            et = row.get("end_time", "").strip()
            atype = row.get("assignment_type", "Billable").strip()

            if not officer or not site:
                errors.append(f"Row {i}: officer_name and site_name are required")
                skipped += 1
                continue
            if not date_re.match(dt):
                errors.append(f"Row {i}: invalid date format '{dt}' (expected YYYY-MM-DD)")
                skipped += 1
                continue
            if st and not time_re.match(st):
                errors.append(f"Row {i}: invalid start_time format '{st}' (expected HH:MM)")
                skipped += 1
                continue
            if et and not time_re.match(et):
                errors.append(f"Row {i}: invalid end_time format '{et}' (expected HH:MM)")
                skipped += 1
                continue

            create_assignment({
                "officer_name": officer,
                "site_name": site,
                "date": dt,
                "start_time": st,
                "end_time": et,
                "assignment_type": atype or "Billable",
                "status": "Scheduled",
                "notes": "",
            }, created_by=created_by)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")
    return {"imported": imported, "skipped": skipped, "errors": errors}


# ── Handoff Notes CRUD ────────────────────────────────────────────────

def create_handoff_note(fields: dict, author: str = "") -> str:
    """Create a shift handoff note. Returns note_id."""
    nid = fields.get("note_id") or _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO ops_handoff_notes
           (note_id, site, shift_date, shift_type, author, content,
            priority, acknowledged_by, acknowledged_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            nid,
            fields.get("site", ""),
            fields.get("shift_date", ""),
            fields.get("shift_type", ""),
            author,
            fields.get("content", ""),
            fields.get("priority", "normal"),
            "",
            "",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return nid


def get_notes_for_site_date(site: str, date: str) -> list:
    """Return handoff notes for a given site and date, newest first."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM ops_handoff_notes
           WHERE site = ? AND shift_date = ?
           ORDER BY created_at DESC""",
        (site, date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def acknowledge_note(note_id: str, username: str) -> bool:
    """Mark a handoff note as acknowledged by the given user."""
    now = _now()
    conn = get_conn()
    cur = conn.execute(
        """UPDATE ops_handoff_notes
           SET acknowledged_by = ?, acknowledged_at = ?, updated_at = ?
           WHERE note_id = ?""",
        (username, now, now, note_id),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def get_recent_notes(site: str, days: int = 7) -> list:
    """Return handoff notes for a site from the last N days, newest first."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM ops_handoff_notes
           WHERE site = ? AND shift_date >= ?
           ORDER BY shift_date DESC, created_at DESC""",
        (site, cutoff),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Open Requests CRUD ────────────────────────────────────────────────

def get_all_requests(site_filter: str = "", status_filter: str = "",
                     priority_filter: str = "") -> list:
    """Return coverage requests, optionally filtered."""
    conn = get_conn()
    query = "SELECT * FROM ops_open_requests WHERE 1=1"
    params = []
    if site_filter:
        query += " AND site_name = ?"
        params.append(site_filter)
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if priority_filter:
        query += " AND priority = ?"
        params.append(priority_filter)
    query += " ORDER BY date DESC, created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_request(fields: dict, created_by: str = "") -> str:
    """Create a coverage request. Returns request_id."""
    rid = fields.get("request_id") or _gen_id()
    now = _now()
    start = fields.get("start_time", "")
    end = fields.get("end_time", "")
    hours = fields.get("hours") or str(calculate_shift_hours(start, end))
    conn = get_conn()
    conn.execute(
        """INSERT INTO ops_open_requests
           (request_id, site_name, date, start_time, end_time, hours,
            reason, priority, status, requested_by, assigned_officer,
            linked_assignment_id, notes,
            created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rid, fields.get("site_name", ""), fields.get("date", ""),
         start, end, hours,
         fields.get("reason", "Coverage"),
         fields.get("priority", "Normal"),
         fields.get("status", "Open"),
         fields.get("requested_by", ""),
         fields.get("assigned_officer", ""),
         fields.get("linked_assignment_id", ""),
         fields.get("notes", ""),
         created_by, created_by, now, now),
    )
    conn.commit()
    conn.close()
    return rid


def update_request(request_id: str, fields: dict, updated_by: str = "") -> bool:
    """Update a coverage request."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM ops_open_requests WHERE request_id = ?", (request_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    allowed = [
        "site_name", "date", "start_time", "end_time", "hours",
        "reason", "priority", "status", "requested_by",
        "assigned_officer", "linked_assignment_id", "notes",
    ]
    updates, params = [], []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])
    # Recalculate hours if times changed
    if "start_time" in fields or "end_time" in fields:
        current = get_request(request_id) or {}
        st = fields.get("start_time", current.get("start_time", ""))
        et = fields.get("end_time", current.get("end_time", ""))
        if "hours" not in fields:
            updates.append("hours = ?")
            params.append(str(calculate_shift_hours(st, et)))
    if updates:
        updates.append("updated_by = ?")
        params.append(updated_by)
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(request_id)
        conn.execute(
            f"UPDATE ops_open_requests SET {', '.join(updates)} WHERE request_id = ?",
            params,
        )
        conn.commit()
    conn.close()
    return True


def get_request(request_id: str) -> dict | None:
    """Fetch a single coverage request."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM ops_open_requests WHERE request_id = ?", (request_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_request(request_id: str) -> bool:
    """Delete a coverage request."""
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM ops_open_requests WHERE request_id = ?", (request_id,)
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def fill_request(request_id: str, officer_name: str, updated_by: str = "") -> str:
    """Assign an officer to a request, mark it Filled, and create a matching assignment.
    Returns the new assignment_id."""
    req = get_request(request_id)
    if not req:
        return ""
    # Create an assignment for the officer
    aid = create_assignment({
        "officer_name": officer_name,
        "site_name": req.get("site_name", ""),
        "date": req.get("date", ""),
        "start_time": req.get("start_time", ""),
        "end_time": req.get("end_time", ""),
        "assignment_type": "Coverage",
        "status": "Scheduled",
        "notes": f"Filled from request {request_id}",
    }, created_by=updated_by)
    # Update the request
    update_request(request_id, {
        "status": "Filled",
        "assigned_officer": officer_name,
        "linked_assignment_id": aid,
    }, updated_by=updated_by)
    return aid


def get_request_summary() -> dict:
    """Return counts for open-request stats cards."""
    from datetime import date as _date
    conn = get_conn()
    total_open = conn.execute(
        "SELECT COUNT(*) as cnt FROM ops_open_requests WHERE status = 'Open'"
    ).fetchone()["cnt"]
    urgent = conn.execute(
        "SELECT COUNT(*) as cnt FROM ops_open_requests WHERE status = 'Open' AND priority IN ('Urgent', 'Emergency')"
    ).fetchone()["cnt"]
    today = _date.today().isoformat()
    filled_today = conn.execute(
        "SELECT COUNT(*) as cnt FROM ops_open_requests WHERE status = 'Filled' AND date = ?",
        (today,),
    ).fetchone()["cnt"]
    total_all = conn.execute(
        "SELECT COUNT(*) as cnt FROM ops_open_requests"
    ).fetchone()["cnt"]
    total_filled = conn.execute(
        "SELECT COUNT(*) as cnt FROM ops_open_requests WHERE status = 'Filled'"
    ).fetchone()["cnt"]
    conn.close()
    fill_rate = round((total_filled / total_all * 100) if total_all else 0, 1)
    return {
        "open": total_open,
        "urgent": urgent,
        "filled_today": filled_today,
        "fill_rate": fill_rate,
    }


def export_collection_csv(collection: str) -> str:
    """Export a collection to CSV text. collection: 'officers', 'sites', 'records', 'assignments', 'pto'."""
    loaders = {
        "officers": lambda: get_ops_officers(active_only=False),
        "sites": get_all_sites,
        "records": get_all_records,
        "assignments": get_all_assignments,
        "pto": get_all_pto,
    }
    loader = loaders.get(collection)
    if not loader:
        return ""

    rows = loader()
    if not rows:
        return ""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ── Anchor Schedules ──────────────────────────────────────────────────

DAYS_OF_WEEK = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


def get_all_anchor_schedules(active_only=True):
    conn = get_conn()
    if active_only:
        rows = conn.execute(
            "SELECT * FROM ops_anchor_schedules WHERE active = 1 ORDER BY officer_name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ops_anchor_schedules ORDER BY officer_name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_anchor_schedule(schedule_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM ops_anchor_schedules WHERE schedule_id = ?", (schedule_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_anchor_for_officer(officer_name):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM ops_anchor_schedules WHERE officer_name = ? AND active = 1",
        (officer_name,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _normalize_time(t):
    """Ensure time is in HH:MM format (handles both 0800 and 08:00)."""
    t = t.strip()
    if ":" not in t and len(t) == 4 and t.isdigit():
        return f"{t[:2]}:{t[2:]}"
    return t


def create_anchor_schedule(fields, created_by=""):
    sid = secrets.token_hex(12)
    now = _now()
    # Calculate total hours from day shifts
    total = 0.0
    for day in DAYS_OF_WEEK:
        shift = fields.get(day, "OFF").strip().upper()
        if shift != "OFF" and "-" in shift:
            parts = shift.split("-")
            total += calculate_shift_hours(_normalize_time(parts[0]), _normalize_time(parts[1]))
    conn = get_conn()
    conn.execute(
        """INSERT INTO ops_anchor_schedules
           (schedule_id, officer_name, position_title, anchor_site, pay_rate,
            sunday, monday, tuesday, wednesday, thursday, friday, saturday,
            total_hours, active, notes, created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, fields.get("officer_name", ""), fields.get("position_title", ""),
         fields.get("anchor_site", ""), fields.get("pay_rate", "0.00"),
         fields.get("sunday", "OFF"), fields.get("monday", "OFF"),
         fields.get("tuesday", "OFF"), fields.get("wednesday", "OFF"),
         fields.get("thursday", "OFF"), fields.get("friday", "OFF"),
         fields.get("saturday", "OFF"), str(total),
         1 if fields.get("active", True) else 0,
         fields.get("notes", ""), created_by, created_by, now, now)
    )
    conn.commit()
    conn.close()
    return sid


def update_anchor_schedule(schedule_id, fields, updated_by=""):
    conn = get_conn()
    allowed = ["officer_name", "position_title", "anchor_site", "pay_rate",
               "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
               "total_hours", "active", "notes"]
    updates = []
    params = []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])
    # Recalculate total hours if any day changed
    if any(d in fields for d in DAYS_OF_WEEK):
        existing = get_anchor_schedule(schedule_id) or {}
        total = 0.0
        for day in DAYS_OF_WEEK:
            shift = fields.get(day, existing.get(day, "OFF")).strip().upper()
            if shift != "OFF" and "-" in shift:
                parts = shift.split("-")
                total += calculate_shift_hours(_normalize_time(parts[0]), _normalize_time(parts[1]))
        updates.append("total_hours = ?")
        params.append(str(total))
    if updates:
        updates.append("updated_by = ?")
        params.append(updated_by)
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(schedule_id)
        conn.execute(f"UPDATE ops_anchor_schedules SET {', '.join(updates)} WHERE schedule_id = ?", params)
        conn.commit()
    conn.close()
    return True


def delete_anchor_schedule(schedule_id):
    conn = get_conn()
    conn.execute("DELETE FROM ops_anchor_schedules WHERE schedule_id = ?", (schedule_id,))
    conn.commit()
    conn.close()
    return True


def generate_week_from_anchors(start_date: str) -> list:
    """Read all active anchor schedules and create draft assignments for the week.

    Args:
        start_date: ISO date string (YYYY-MM-DD) for the Sunday of the target week.

    Returns:
        List of created assignment IDs.
    """
    from datetime import date as dt_date, timedelta

    try:
        week_start = dt_date.fromisoformat(start_date)
    except (ValueError, TypeError):
        return []

    anchors = get_all_anchor_schedules(active_only=True)
    if not anchors:
        return []

    created_ids = []
    # Map day index (0=Sun) to column name in anchor schedule
    day_columns = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]

    for anchor in anchors:
        officer_name = anchor.get("officer_name", "")
        site_name = anchor.get("anchor_site", "")
        if not officer_name or not site_name:
            continue

        for day_idx, day_col in enumerate(day_columns):
            shift = (anchor.get(day_col, "") or "OFF").strip().upper()
            if shift == "OFF" or "-" not in shift:
                continue

            parts = shift.split("-")
            if len(parts) != 2:
                continue

            start_time = _normalize_time(parts[0])
            end_time = _normalize_time(parts[1])
            target_date = (week_start + timedelta(days=day_idx)).strftime("%Y-%m-%d")

            # Skip if an assignment already exists for this officer/site/date
            existing = get_assignments_for_week(target_date, target_date)
            already_exists = any(
                a.get("officer_name") == officer_name
                and a.get("site_name") == site_name
                and a.get("date") == target_date
                for a in existing
            )
            if already_exists:
                continue

            asn_id = create_assignment({
                "officer_name": officer_name,
                "site_name": site_name,
                "date": target_date,
                "start_time": start_time,
                "end_time": end_time,
                "assignment_type": "Anchor",
                "status": "Draft",
                "notes": f"Auto-generated from anchor schedule",
            }, created_by="system")
            created_ids.append(asn_id)

    return created_ids


# ═══════════════════════════════════════════════════════════════════════
#  Open Positions Tracker
# ═══════════════════════════════════════════════════════════════════════

POSITION_PIPELINE = [
    "Open", "Job Offer", "Background Check",
    "Company Orientation", "Training (OJT)", "Filled",
]

def _ensure_positions_tables():
    conn = get_conn()
    try:
        conn.execute("SELECT 1 FROM ops_positions LIMIT 1")
    except Exception:
        from src.modules.operations.migrations import _migration_008
        _migration_008(conn)
        conn.commit()
    finally:
        conn.close()

def get_all_positions(site_filter="", status_filter="", include_filled=False):
    _ensure_positions_tables()
    conn = get_conn()
    sql = "SELECT * FROM ops_positions WHERE 1=1"
    params = []
    if site_filter:
        sql += " AND site_name = ?"
        params.append(site_filter)
    if status_filter:
        sql += " AND pipeline_stage = ?"
        params.append(status_filter)
    if not include_filled:
        sql += " AND pipeline_stage != 'Filled'"
    sql += " ORDER BY date_opened DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_position(position_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM ops_positions WHERE position_id = ?", (position_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_position(data: dict) -> str:
    _ensure_positions_tables()
    conn = get_conn()
    pid = f"pos-{secrets.token_hex(6)}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO ops_positions (
            position_id, site_name, position_title, shift, pay_rate,
            sunday, monday, tuesday, wednesday, thursday, friday, saturday,
            total_hours, status, pipeline_stage, notes, date_opened,
            date_job_offer, date_background_check, date_orientation,
            date_training_ojt, expected_orientation_end, expected_training_end,
            created_by, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        pid,
        data.get("site_name", ""),
        data.get("position_title", ""),
        data.get("shift", ""),
        data.get("pay_rate", "0.00"),
        data.get("sunday", "OFF"),
        data.get("monday", "OFF"),
        data.get("tuesday", "OFF"),
        data.get("wednesday", "OFF"),
        data.get("thursday", "OFF"),
        data.get("friday", "OFF"),
        data.get("saturday", "OFF"),
        data.get("total_hours", "0"),
        "Open",
        data.get("pipeline_stage", "Open"),
        data.get("notes", ""),
        data.get("date_opened", now[:10]),
        data.get("date_job_offer", ""),
        data.get("date_background_check", ""),
        data.get("date_orientation", ""),
        data.get("date_training_ojt", ""),
        data.get("expected_orientation_end", ""),
        data.get("expected_training_end", ""),
        data.get("created_by", ""),
        now, now,
    ))
    conn.commit()
    conn.close()
    return pid

def update_position(position_id: str, data: dict):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    fields = []
    vals = []
    for k, v in data.items():
        if k not in ("position_id", "created_at"):
            fields.append(f"{k} = ?")
            vals.append(v)
    fields.append("updated_at = ?")
    vals.append(now)
    # Keep status in sync with pipeline_stage
    new_stage = data.get("pipeline_stage", "")
    if new_stage and "status" not in data:
        fields.append("status = ?")
        vals.append("Filled" if new_stage == "Filled" else "Open")
    if new_stage == "Filled":
        if "date_filled" not in data:
            fields.append("date_filled = ?")
            vals.append(now[:10])
    # Auto-set stage date when pipeline_stage changes (if not already provided)
    _stage_date_map = {
        "Job Offer": "date_job_offer",
        "Background Check": "date_background_check",
        "Company Orientation": "date_orientation",
        "Training (OJT)": "date_training_ojt",
    }
    new_stage = data.get("pipeline_stage", "")
    if new_stage in _stage_date_map:
        date_col = _stage_date_map[new_stage]
        if date_col not in data:
            # Only set if currently empty in the DB
            cur = conn.execute(
                f"SELECT {date_col} FROM ops_positions WHERE position_id = ?",
                (position_id,)
            ).fetchone()
            if cur and not cur[0]:
                fields.append(f"{date_col} = ?")
                vals.append(now[:10])
    vals.append(position_id)
    conn.execute(f"UPDATE ops_positions SET {', '.join(fields)} WHERE position_id = ?", vals)
    conn.commit()
    conn.close()

def delete_position(position_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM ops_positions WHERE position_id = ?", (position_id,))
    conn.execute("DELETE FROM ops_candidates WHERE position_id = ?", (position_id,))
    conn.commit()
    conn.close()

def advance_position_pipeline(position_id: str, new_stage: str):
    update_position(position_id, {"pipeline_stage": new_stage})

# ── Candidates ────────────────────────────────────────────────────────

def get_candidates(position_id: str) -> list:
    _ensure_positions_tables()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ops_candidates WHERE position_id = ? ORDER BY created_at DESC",
        (position_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_candidates() -> list:
    _ensure_positions_tables()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM ops_candidates ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_candidate(data: dict) -> str:
    _ensure_positions_tables()
    conn = get_conn()
    cid = f"cand-{secrets.token_hex(6)}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO ops_candidates (
            candidate_id, position_id, candidate_name, phone, email,
            source, stage, interview_date, offer_date, start_date,
            notes, created_by, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        cid,
        data.get("position_id", ""),
        data.get("candidate_name", ""),
        data.get("phone", ""),
        data.get("email", ""),
        data.get("source", ""),
        data.get("stage", "Applied"),
        data.get("interview_date", ""),
        data.get("offer_date", ""),
        data.get("start_date", ""),
        data.get("notes", ""),
        data.get("created_by", ""),
        now, now,
    ))
    conn.commit()
    conn.close()
    return cid

def update_candidate(candidate_id: str, data: dict):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    fields = []
    vals = []
    for k, v in data.items():
        if k not in ("candidate_id", "created_at"):
            fields.append(f"{k} = ?")
            vals.append(v)
    fields.append("updated_at = ?")
    vals.append(now)
    vals.append(candidate_id)
    conn.execute(f"UPDATE ops_candidates SET {', '.join(fields)} WHERE candidate_id = ?", vals)
    conn.commit()
    conn.close()

def delete_candidate(candidate_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM ops_candidates WHERE candidate_id = ?", (candidate_id,))
    conn.commit()
    conn.close()

# ── Position KPIs ─────────────────────────────────────────────────────

def get_position_kpis() -> dict:
    """Return summary KPIs for open positions tracker."""
    _ensure_positions_tables()
    conn = get_conn()
    # Total open (not Filled)
    total_open = conn.execute(
        "SELECT COUNT(*) FROM ops_positions WHERE pipeline_stage != 'Filled'"
    ).fetchone()[0]
    # Total open hours
    rows = conn.execute(
        "SELECT total_hours FROM ops_positions WHERE pipeline_stage != 'Filled'"
    ).fetchall()
    total_hours = sum(float(r["total_hours"] or 0) for r in rows)
    # Weekly OT cost exposure (open hours × avg pay rate × 1.5 OT multiplier)
    rate_rows = conn.execute(
        "SELECT pay_rate, total_hours FROM ops_positions WHERE pipeline_stage != 'Filled'"
    ).fetchall()
    ot_cost = sum(
        float(r["pay_rate"] or 0) * float(r["total_hours"] or 0) * 1.5
        for r in rate_rows
    )
    # Avg days to fill (for filled positions that have both dates)
    filled = conn.execute(
        "SELECT date_opened, date_filled FROM ops_positions WHERE pipeline_stage = 'Filled' AND date_opened != '' AND date_filled != ''"
    ).fetchall()
    if filled:
        from datetime import date as dt_date
        total_days = 0
        count = 0
        for r in filled:
            try:
                d1 = dt_date.fromisoformat(r["date_opened"])
                d2 = dt_date.fromisoformat(r["date_filled"])
                total_days += (d2 - d1).days
                count += 1
            except Exception:
                pass
        avg_days = round(total_days / count, 1) if count else 0
    else:
        avg_days = 0
    # Positions by site
    site_rows = conn.execute(
        "SELECT site_name, COUNT(*) as cnt FROM ops_positions WHERE pipeline_stage != 'Filled' GROUP BY site_name ORDER BY cnt DESC"
    ).fetchall()
    by_site = {r["site_name"]: r["cnt"] for r in site_rows}
    # Pipeline distribution
    pipe_rows = conn.execute(
        "SELECT pipeline_stage, COUNT(*) as cnt FROM ops_positions WHERE pipeline_stage != 'Filled' GROUP BY pipeline_stage"
    ).fetchall()
    pipeline_dist = {r["pipeline_stage"]: r["cnt"] for r in pipe_rows}
    conn.close()
    return {
        "total_open": total_open,
        "total_hours": total_hours,
        "ot_cost_exposure": round(ot_cost, 2),
        "avg_days_to_fill": avg_days,
        "by_site": by_site,
        "pipeline_distribution": pipeline_dist,
    }

def calculate_position_ot_cost(pay_rate, total_hours):
    """Calculate weekly OT cost exposure for a single position."""
    try:
        return round(float(pay_rate or 0) * float(total_hours or 0) * 1.5, 2)
    except (ValueError, TypeError):
        return 0.0


# ── Officer Certifications (#26) ─────────────────────────────────────

def _ensure_certifications_table():
    """Safety net: create ops_certifications if migration hasn't run yet."""
    conn = get_conn()
    try:
        conn.execute("SELECT 1 FROM ops_certifications LIMIT 1")
    except Exception:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ops_certifications (
                cert_id TEXT PRIMARY KEY,
                officer_name TEXT NOT NULL DEFAULT '',
                cert_name TEXT NOT NULL DEFAULT '',
                issued_date TEXT DEFAULT '',
                expiry_date TEXT DEFAULT '',
                status TEXT DEFAULT 'Active',
                notes TEXT DEFAULT '',
                created_by TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_ops_cert_officer ON ops_certifications(officer_name);
            CREATE INDEX IF NOT EXISTS idx_ops_cert_expiry ON ops_certifications(expiry_date);
        """)
        conn.commit()
    conn.close()


_ensure_certifications_table()


def get_officer_certifications(officer_name: str) -> list:
    """Return all certifications for a given officer."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM ops_certifications
           WHERE officer_name = ?
           ORDER BY expiry_date""",
        (officer_name,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_officer_certification(officer_name: str, cert_name: str, expiry_date: str,
                              issued_date: str = "", notes: str = "",
                              created_by: str = "") -> str:
    """Add a certification for an officer. Returns cert_id."""
    cid = secrets.token_hex(8)
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO ops_certifications
           (cert_id, officer_name, cert_name, issued_date, expiry_date,
            status, notes, created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (cid, officer_name, cert_name, issued_date, expiry_date,
         "Active", notes, created_by, now, now),
    )
    conn.commit()
    conn.close()
    return cid


def get_expiring_certifications(days: int = 30) -> list:
    """Return certifications expiring within the next N days."""
    from datetime import timedelta
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM ops_certifications
           WHERE status = 'Active'
             AND expiry_date >= ? AND expiry_date <= ?
           ORDER BY expiry_date""",
        (today, cutoff),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
