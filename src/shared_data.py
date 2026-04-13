"""
Cerasus Hub — Shared Data Layer
CRUD operations for the shared officers and sites tables.
All modules use these instead of maintaining their own officer/site stores.
"""

import secrets
from datetime import datetime, timezone

from src.database import get_conn


def _gen_id() -> str:
    return secrets.token_hex(12)


def _gen_employee_id() -> str:
    """Generate a sequential human-readable employee ID like EMP-001."""
    conn = get_conn()
    row = conn.execute(
        "SELECT employee_id FROM officers WHERE employee_id LIKE 'EMP-%' ORDER BY employee_id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row and row["employee_id"]:
        try:
            num = int(row["employee_id"].split("-")[1]) + 1
        except (IndexError, ValueError):
            num = 1
    else:
        num = 1
    return f"EMP-{num:03d}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Officers ───────────────────────────────────────────────────────────

def get_all_officers(status_filter: str = "", include_deleted: bool = False) -> list:
    conn = get_conn()
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM officers WHERE status = ? ORDER BY name", (status_filter,)
        ).fetchall()
    elif include_deleted:
        rows = conn.execute("SELECT * FROM officers ORDER BY name").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM officers WHERE status != 'Deleted' ORDER BY name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_officer(officer_id: str, include_deleted: bool = False) -> dict | None:
    conn = get_conn()
    if include_deleted:
        row = conn.execute("SELECT * FROM officers WHERE officer_id = ?", (officer_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM officers WHERE officer_id = ? AND status != 'Deleted'",
            (officer_id,),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def search_officers(query: str) -> list:
    conn = get_conn()
    q = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM officers WHERE name LIKE ? OR employee_id LIKE ?
           OR first_name LIKE ? OR last_name LIKE ? OR email LIKE ?
           ORDER BY name""",
        (q, q, q, q, q)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_officers(include_deleted: bool = False) -> list:
    if include_deleted:
        return get_all_officers(include_deleted=True)
    return get_all_officers(status_filter="Active")


# ── Site-Based Access Filtering ──────────────────────────────────────

def filter_by_user_sites(app_state: dict, records: list, site_field: str = "site") -> list:
    """Filter a list of record dicts to only include records matching the user's assigned sites.
    Admin users and users with no site restrictions see everything."""
    role = app_state.get("role", "")
    sites = app_state.get("assigned_sites", [])
    if role == "admin" or not sites:
        return records  # No restriction
    return [r for r in records if r.get(site_field, "") in sites]


def get_filtered_officers(app_state: dict, status_filter: str = "") -> list:
    """Get officers filtered by the current user's assigned sites."""
    officers = get_all_officers(status_filter=status_filter)
    return filter_by_user_sites(app_state, officers)


def get_officers_for_user(app_state: dict) -> list:
    """Get active officers filtered by the current user's assigned sites."""
    officers = get_active_officers()
    return filter_by_user_sites(app_state, officers)


def get_sites_for_user(app_state: dict) -> list:
    """Get site names filtered by the current user's assigned sites."""
    sites = get_site_names()
    role = app_state.get("role", "")
    assigned = app_state.get("assigned_sites", [])
    if role == "admin" or not assigned:
        return sites
    return [s for s in sites if s.get("name", "") in assigned]


def get_officer_names() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT officer_id, name, first_name, last_name FROM officers WHERE status = 'Active' ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_officer(fields: dict, created_by: str = "") -> str:
    """Create an officer. Returns officer_id.

    If ``employee_id`` is supplied in *fields* it is preserved as-is (e.g.
    TrackTik Staffr Id).  Only when the field is blank do we auto-generate a
    sequential ``EMP-###`` value.
    """
    oid = fields.get("officer_id") or _gen_id()
    now = _now()
    name = fields.get("name", "")
    if not name and (fields.get("first_name") or fields.get("last_name")):
        name = f"{fields.get('first_name', '')} {fields.get('last_name', '')}".strip()

    # Preserve imported employee_id; only auto-generate when missing
    emp_id = fields.get("employee_id", "").strip()
    if not emp_id:
        emp_id = _gen_employee_id()

    conn = get_conn()
    conn.execute(
        """INSERT INTO officers (officer_id, name, employee_id, first_name, last_name,
           email, phone, job_title, role, site, supervisor_id, hire_date, status,
           weekly_hours, trained_sites, approved_sites, anchor_sites,
           uniform_sizes, role_title, active_points, discipline_level,
           last_infraction_date, emergency_exemptions_used,
           notes, created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (oid, name, emp_id,
         fields.get("first_name", ""), fields.get("last_name", ""),
         fields.get("email", ""), fields.get("phone", ""),
         fields.get("job_title", "Security Officer"), fields.get("role", ""),
         fields.get("site", ""), fields.get("supervisor_id", ""),
         fields.get("hire_date", ""), fields.get("status", "Active"),
         fields.get("weekly_hours", "40"),
         fields.get("trained_sites", "[]"), fields.get("approved_sites", "[]"),
         fields.get("anchor_sites", "[]"), fields.get("uniform_sizes", "{}"),
         fields.get("role_title", ""), fields.get("active_points", 0),
         fields.get("discipline_level", "None"),
         fields.get("last_infraction_date", ""),
         fields.get("emergency_exemptions_used", 0),
         fields.get("notes", ""), created_by, created_by, now, now)
    )
    conn.commit()
    conn.close()
    return oid


def update_officer(officer_id: str, fields: dict, updated_by: str = "") -> bool:
    """Update officer fields. Only updates keys present in fields dict."""
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM officers WHERE officer_id = ?", (officer_id,)).fetchone()
    if not row:
        conn.close()
        return False

    # Build dynamic update
    allowed = [
        "name", "employee_id", "first_name", "last_name", "email", "phone",
        "job_title", "role", "site", "supervisor_id", "hire_date", "status",
        "weekly_hours", "trained_sites", "approved_sites", "anchor_sites",
        "uniform_sizes", "role_title", "active_points", "discipline_level",
        "last_infraction_date", "emergency_exemptions_used", "notes",
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
        params.append(officer_id)
        conn.execute(f"UPDATE officers SET {', '.join(updates)} WHERE officer_id = ?", params)
        conn.commit()

    conn.close()
    return True


def delete_officer(officer_id: str, updated_by: str = "") -> bool:
    """Soft-delete an officer by setting status to 'Deleted'."""
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM officers WHERE officer_id = ?", (officer_id,)).fetchone()
    if not row:
        conn.close()
        return False
    now = _now()
    conn.execute(
        "UPDATE officers SET status = 'Deleted', updated_by = ?, updated_at = ? WHERE officer_id = ?",
        (updated_by, now, officer_id),
    )
    conn.commit()
    conn.close()
    return True


def terminate_officer(officer_id: str, updated_by: str = "") -> bool:
    """Terminate an officer (soft-delete with status 'Terminated').

    The officer record is preserved so foreign-key references (discipline
    records, reviews, audit trail) remain valid.
    """
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM officers WHERE officer_id = ?", (officer_id,)).fetchone()
    if not row:
        conn.close()
        return False
    now = _now()
    conn.execute(
        "UPDATE officers SET status = 'Terminated', updated_by = ?, updated_at = ? WHERE officer_id = ?",
        (updated_by, now, officer_id),
    )
    conn.commit()
    conn.close()
    return True


def purge_officer(officer_id: str) -> bool:
    """Hard-delete an officer record permanently (admin cleanup).

    WARNING: This removes the row entirely. Any discipline records, reviews,
    or audit entries referencing this officer_id will have broken JOINs.
    Prefer delete_officer() or terminate_officer() instead.
    """
    conn = get_conn()
    conn.execute("DELETE FROM officers WHERE officer_id = ?", (officer_id,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def get_deleted_officers() -> list:
    """Return all soft-deleted officer records."""
    return get_all_officers(status_filter="Deleted")


def restore_officer(officer_id: str, updated_by: str = "") -> bool:
    """Restore a soft-deleted officer back to 'Active' status."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM officers WHERE officer_id = ? AND status = 'Deleted'", (officer_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    now = _now()
    conn.execute(
        "UPDATE officers SET status = 'Active', updated_by = ?, updated_at = ? WHERE officer_id = ?",
        (updated_by, now, officer_id),
    )
    conn.commit()
    conn.close()
    return True


# ── Officer Merge ─────────────────────────────────────────────────────

def merge_officers(keep_id: str, remove_id: str, conn=None, merged_by: str = "") -> bool:
    """Merge *remove* officer into *keep* officer.

    1. Reassign ops_assignments by officer name
    2. Reassign ats_infractions by employee_id
    3. Reassign uni_issuances by officer_id
    4. Reassign da_records by employee_officer_id
    5. Fill empty fields on *keep* from *remove*
    6. Soft-delete *remove* officer
    7. Log to audit
    """
    from src.audit import log_event

    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    keep = conn.execute("SELECT * FROM officers WHERE officer_id = ?", (keep_id,)).fetchone()
    remove = conn.execute("SELECT * FROM officers WHERE officer_id = ?", (remove_id,)).fetchone()
    if not keep or not remove:
        if own_conn:
            conn.close()
        return False

    keep = dict(keep)
    remove = dict(remove)
    now = _now()

    # 1. ops_assignments — match by officer name
    remove_name = remove.get("name", "")
    keep_name = keep.get("name", "")
    if remove_name:
        conn.execute(
            "UPDATE ops_assignments SET officer_name = ?, updated_at = ? WHERE officer_name = ?",
            (keep_name, now, remove_name),
        )

    # 2. ats_infractions — match by employee_id
    conn.execute(
        "UPDATE ats_infractions SET employee_id = ? WHERE employee_id = ?",
        (keep_id, remove_id),
    )

    # 3. uni_issuances — match by officer_id
    conn.execute(
        "UPDATE uni_issuances SET officer_id = ?, officer_name = ? WHERE officer_id = ?",
        (keep_id, keep_name, remove_id),
    )

    # 4. da_records — match by employee_officer_id
    conn.execute(
        "UPDATE da_records SET employee_officer_id = ?, employee_name = ? WHERE employee_officer_id = ?",
        (keep_id, keep_name, remove_id),
    )

    # 5. Merge empty fields from remove into keep
    mergeable_fields = [
        "email", "phone", "job_title", "role", "site", "supervisor_id",
        "hire_date", "weekly_hours", "trained_sites", "approved_sites",
        "anchor_sites", "uniform_sizes", "role_title", "notes",
    ]
    fill_updates = []
    fill_params = []
    for field in mergeable_fields:
        keep_val = keep.get(field, "") or ""
        remove_val = remove.get(field, "") or ""
        # Treat empty-ish JSON as blank
        if (not keep_val or keep_val in ("[]", "{}", "0")) and remove_val and remove_val not in ("[]", "{}", "0"):
            fill_updates.append(f"{field} = ?")
            fill_params.append(remove_val)

    if fill_updates:
        fill_updates.append("updated_by = ?")
        fill_params.append(merged_by)
        fill_updates.append("updated_at = ?")
        fill_params.append(now)
        fill_params.append(keep_id)
        conn.execute(
            f"UPDATE officers SET {', '.join(fill_updates)} WHERE officer_id = ?",
            fill_params,
        )

    # 6. Soft-delete the remove officer
    conn.execute(
        "UPDATE officers SET status = 'Deleted', updated_by = ?, updated_at = ? WHERE officer_id = ?",
        (merged_by, now, remove_id),
    )

    conn.commit()
    if own_conn:
        conn.close()

    # 7. Audit log
    log_event(
        module_name="hub",
        event_type="officer_merge",
        username=merged_by,
        details=f"Merged officer '{remove_name}' ({remove_id}) into '{keep_name}' ({keep_id})",
        table_name="officers",
        record_id=keep_id,
        action="merge",
        before_value=remove_id,
        after_value=keep_id,
        employee_id=keep_id,
    )

    return True


# ── Sites ──────────────────────────────────────────────────────────────

def get_all_sites(status_filter: str = "") -> list:
    conn = get_conn()
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM sites WHERE status = ? ORDER BY name", (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM sites ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_site(site_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM sites WHERE site_id = ?", (site_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_site_names() -> list:
    """Return list of active site name strings (not dicts)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT name FROM sites WHERE status = 'Active' ORDER BY name"
    ).fetchall()
    conn.close()
    return [r["name"] for r in rows]


def get_site_names_with_ids() -> list:
    """Return list of dicts with site_id and name."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT site_id, name FROM sites WHERE status = 'Active' ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_site(fields: dict, created_by: str = "") -> str:
    """Create a site. Returns site_id."""
    sid = fields.get("site_id") or _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO sites (site_id, name, address, city, state, style,
           billing_code, market, overtime_sensitivity, status,
           notes, created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, fields.get("name", ""), fields.get("address", ""),
         fields.get("city", ""), fields.get("state", ""),
         fields.get("style", "Soft Look"), fields.get("billing_code", ""),
         fields.get("market", ""), fields.get("overtime_sensitivity", "Normal"),
         fields.get("status", "Active"), fields.get("notes", ""),
         created_by, created_by, now, now)
    )
    conn.commit()
    conn.close()
    return sid


def update_site(site_id: str, fields: dict, updated_by: str = "") -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM sites WHERE site_id = ?", (site_id,)).fetchone()
    if not row:
        conn.close()
        return False

    allowed = [
        "name", "address", "city", "state", "style", "billing_code",
        "market", "overtime_sensitivity", "status", "notes",
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
        params.append(site_id)
        conn.execute(f"UPDATE sites SET {', '.join(updates)} WHERE site_id = ?", params)
        conn.commit()

    conn.close()
    return True


def delete_site(site_id: str) -> bool:
    conn = get_conn()
    conn.execute("DELETE FROM sites WHERE site_id = ?", (site_id,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


# ── Officer Timeline ──────────────────────────────────────────────────

def get_officer_timeline(officer_id: str) -> list:
    """Query all modules for events related to an officer and return a merged,
    date-descending list of normalised event dicts.

    Each dict: {"date": "YYYY-MM-DD", "module": str, "type": str,
                "summary": str, "severity": str}

    Severity values: "info", "warning", "danger", "success", "neutral"
    """
    events: list[dict] = []
    conn = get_conn()

    # ── Attendance infractions (ats_infractions) ──
    try:
        rows = conn.execute(
            "SELECT * FROM ats_infractions WHERE employee_id = ?", (officer_id,)
        ).fetchall()
        for r in rows:
            r = dict(r)
            inf_type = r.get("infraction_type", "")
            desc = r.get("description", "") or ""
            pts = ""
            # Try to get point info from policy engine at render time; keep it simple here
            summary = inf_type.replace("_", " ").title()
            if desc:
                summary += f" - {desc[:60]}"
            events.append({
                "date": (r.get("infraction_date") or r.get("created_at", ""))[:10],
                "module": "attendance",
                "type": "infraction",
                "summary": summary,
                "severity": "warning",
            })
    except Exception:
        pass

    # ── Disciplinary actions (da_records) ──
    try:
        rows = conn.execute(
            "SELECT * FROM da_records WHERE employee_officer_id = ?", (officer_id,)
        ).fetchall()
        for r in rows:
            r = dict(r)
            level = r.get("discipline_level", "Unknown")
            status = r.get("status", "draft")
            violation = r.get("violation_type", "")
            summary = level or "DA Record"
            if violation:
                summary += f" - {violation}"
            summary += f" ({status})"
            sev = "danger"
            if level in ("Verbal Warning",):
                sev = "warning"
            elif level in ("Suspension", "Termination"):
                sev = "danger"
            events.append({
                "date": (r.get("created_at") or "")[:10],
                "module": "da_generator",
                "type": "disciplinary_action",
                "summary": summary,
                "severity": sev,
            })
    except Exception:
        pass

    # ── Uniform issuances (uni_issuances) ──
    try:
        rows = conn.execute(
            "SELECT * FROM uni_issuances WHERE officer_id = ?", (officer_id,)
        ).fetchall()
        for r in rows:
            r = dict(r)
            item = r.get("item_name", "") or r.get("item_id", "")
            size = r.get("size", "")
            qty = r.get("quantity", 1)
            status = r.get("status", "")
            summary = f"{item}"
            if size:
                summary += f" ({size})"
            if qty and qty > 1:
                summary += f" x{qty}"
            summary += f" - {status}"
            events.append({
                "date": (r.get("date_issued") or r.get("created_at", ""))[:10],
                "module": "uniforms",
                "type": "issuance",
                "summary": summary,
                "severity": "info",
            })
    except Exception:
        pass

    # ── Training completions (trn_progress) ──
    try:
        rows = conn.execute(
            """SELECT p.*, c.title as course_title
               FROM trn_progress p
               LEFT JOIN trn_courses c ON c.course_id = p.course_id
               WHERE p.officer_id = ? AND p.completed = 1""",
            (officer_id,)
        ).fetchall()
        for r in rows:
            r = dict(r)
            course = r.get("course_title") or r.get("course_id", "")
            chapter = r.get("chapter_id", "")
            summary = f"Completed: {course}"
            if chapter:
                summary += f" (Ch: {chapter})"
            events.append({
                "date": (r.get("completed_at") or "")[:10],
                "module": "training",
                "type": "completion",
                "summary": summary,
                "severity": "success",
            })
    except Exception:
        pass

    # ── Audit log events ──
    try:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE employee_id = ? ORDER BY timestamp DESC LIMIT 50",
            (officer_id,)
        ).fetchall()
        for r in rows:
            r = dict(r)
            module = r.get("module_name", "system")
            event = r.get("event_type", "")
            details = r.get("details", "") or ""
            summary = event.replace("_", " ").title()
            if details:
                summary += f" - {details[:60]}"
            events.append({
                "date": (r.get("timestamp") or "")[:10],
                "module": module,
                "type": "audit",
                "summary": summary,
                "severity": "neutral",
            })
    except Exception:
        pass

    conn.close()

    # Sort descending by date
    events.sort(key=lambda e: e.get("date", ""), reverse=True)
    return events


# ── Backfill ──────────────────────────────────────────────────────────

def backfill_employee_ids():
    """Assign sequential EMP-### IDs to officers that have blank employee_id."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT officer_id FROM officers WHERE employee_id IS NULL OR employee_id = '' ORDER BY created_at"
    ).fetchall()
    if not rows:
        conn.close()
        return 0

    # Find current max EMP-### number
    max_row = conn.execute(
        "SELECT employee_id FROM officers WHERE employee_id LIKE 'EMP-%' ORDER BY employee_id DESC LIMIT 1"
    ).fetchone()
    start = 1
    if max_row and max_row["employee_id"]:
        try:
            start = int(max_row["employee_id"].split("-")[1]) + 1
        except (IndexError, ValueError):
            pass

    count = 0
    for i, row in enumerate(rows):
        emp_id = f"EMP-{start + i:03d}"
        conn.execute(
            "UPDATE officers SET employee_id = ? WHERE officer_id = ?",
            (emp_id, row["officer_id"])
        )
        count += 1
    conn.commit()
    conn.close()
    return count
