"""
Cerasus Hub -- DA Generator Module: Data Manager
SQLite-backed CRUD for da_records and module settings.
"""

import json
import secrets
from datetime import datetime, timezone, timedelta

from src.database import get_conn


# ── Table Safety ──────────────────────────────────────────────────────

def _ensure_da_tables():
    """Ensure da_records table exists (safety net if migration was skipped)."""
    conn = get_conn()
    try:
        conn.execute("SELECT 1 FROM da_records LIMIT 1")
    except Exception:
        # Table doesn't exist — run migration 001 directly
        from src.modules.da_generator.migrations import MIGRATIONS
        try:
            MIGRATIONS[1](conn)
            conn.execute(
                "INSERT OR IGNORE INTO schema_versions (module_name, version, description) VALUES (?, ?, ?)",
                ("da_generator", 1, "Create DA Generator tables."),
            )
            # Also run migration 002 and 003 if available
            for ver in [2, 3]:
                if ver in MIGRATIONS:
                    try:
                        MIGRATIONS[ver](conn)
                        conn.execute(
                            "INSERT OR IGNORE INTO schema_versions (module_name, version, description) VALUES (?, ?, ?)",
                            ("da_generator", ver, MIGRATIONS[ver].__doc__ or ""),
                        )
                    except Exception:
                        pass
            conn.commit()
        except Exception:
            pass
    conn.close()


# Run on import to guarantee table exists
_ensure_da_tables()


# ── Helpers ───────────────────────────────────────────────────────────

def _gen_da_id() -> str:
    """Generate a DA ID like DA-20260319-XXXXXXXX."""
    date_part = datetime.now().strftime("%Y%m%d")
    rand_part = secrets.token_hex(4).upper()
    return f"DA-{date_part}-{rand_part}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# All columns that may be updated (everything except da_id, created_by, created_at)
ALLOWED_FIELDS = [
    "employee_name", "employee_position", "employee_officer_id",
    "site", "security_director",
    "incident_dates", "incident_narrative", "violation_type",
    "prior_verbal_same", "prior_written_same", "prior_final_same",
    "prior_verbal_other", "prior_written_other", "prior_final_other",
    "coaching_occurred", "coaching_date", "coaching_content", "coaching_outcome",
    "has_victim_statement", "has_subject_statement", "has_witness_statements",
    "clarifying_qa",
    "ceis_narrative", "ceis_citations", "ceis_violation_analysis",
    "ceis_discipline_determination", "ceis_risk_assessment", "ceis_recommendation",
    "use_of_force_applies", "post_orders_apply", "post_order_details",
    "additional_violations", "discipline_level",
    "final_narrative", "final_citations", "final_prior_discipline",
    "final_coaching", "required_improvements", "additional_comments",
    "da_payload", "status", "current_step",
    "attendance_points_at_da", "attendance_record_json",
    "pdf_filename", "updated_by", "updated_at",
    "delivered_at", "signed_at",
    "acknowledged", "acknowledged_by", "acknowledged_at",
    "employee_response", "witness_name", "witness_signed", "witness_signed_at",
]


# ── Status workflow ──────────────────────────────────────────────────

STATUS_WORKFLOW = ["draft", "pending_review", "delivered", "signed", "completed"]


def update_da_status(da_id: str, new_status: str, updated_by: str = "") -> bool:
    """Update the status of a DA and set the appropriate timestamp.

    If *new_status* is ``delivered``, ``delivered_at`` is set to the current
    UTC timestamp.  If *new_status* is ``signed``, ``signed_at`` is set.
    Returns ``True`` on success.
    """
    if new_status not in STATUS_WORKFLOW:
        return False

    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM da_records WHERE da_id = ?", (da_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    now = _now()
    fields_to_set = {
        "status": new_status,
        "updated_by": updated_by,
        "updated_at": now,
    }
    if new_status == "delivered":
        fields_to_set["delivered_at"] = now
    elif new_status == "signed":
        fields_to_set["signed_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in fields_to_set)
    params = list(fields_to_set.values()) + [da_id]
    conn.execute(
        f"UPDATE da_records SET {set_clause} WHERE da_id = ?",
        params,
    )
    conn.commit()
    conn.close()
    return True


# ── DA Records CRUD ──────────────────────────────────────────────────

def create_da(fields: dict, created_by: str = "") -> str:
    """Create a new DA record. Returns da_id."""
    da_id = _gen_da_id()
    now = _now()

    # Serialize clarifying_qa if provided as a list
    if "clarifying_qa" in fields and isinstance(fields["clarifying_qa"], list):
        fields = dict(fields)
        fields["clarifying_qa"] = json.dumps(fields["clarifying_qa"])

    conn = get_conn()
    conn.execute(
        """INSERT INTO da_records
           (da_id, employee_name, employee_position, employee_officer_id,
            site, security_director,
            incident_dates, incident_narrative, violation_type,
            prior_verbal_same, prior_written_same, prior_final_same,
            prior_verbal_other, prior_written_other, prior_final_other,
            coaching_occurred, coaching_date, coaching_content, coaching_outcome,
            has_victim_statement, has_subject_statement, has_witness_statements,
            clarifying_qa,
            ceis_narrative, ceis_citations, ceis_violation_analysis,
            ceis_discipline_determination, ceis_risk_assessment, ceis_recommendation,
            use_of_force_applies, post_orders_apply, post_order_details,
            additional_violations, discipline_level,
            final_narrative, final_citations, final_prior_discipline,
            final_coaching, required_improvements, additional_comments,
            da_payload, status, current_step,
            attendance_points_at_da, attendance_record_json,
            pdf_filename,
            created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            da_id,
            fields.get("employee_name", ""),
            fields.get("employee_position", ""),
            fields.get("employee_officer_id", ""),
            fields.get("site", ""),
            fields.get("security_director", ""),
            fields.get("incident_dates", ""),
            fields.get("incident_narrative", ""),
            fields.get("violation_type", ""),
            int(fields.get("prior_verbal_same", 0)),
            int(fields.get("prior_written_same", 0)),
            int(fields.get("prior_final_same", 0)),
            int(fields.get("prior_verbal_other", 0)),
            int(fields.get("prior_written_other", 0)),
            int(fields.get("prior_final_other", 0)),
            int(fields.get("coaching_occurred", 0)),
            fields.get("coaching_date", ""),
            fields.get("coaching_content", ""),
            fields.get("coaching_outcome", ""),
            int(fields.get("has_victim_statement", 0)),
            int(fields.get("has_subject_statement", 0)),
            int(fields.get("has_witness_statements", 0)),
            fields.get("clarifying_qa", "[]"),
            fields.get("ceis_narrative", ""),
            fields.get("ceis_citations", ""),
            fields.get("ceis_violation_analysis", ""),
            fields.get("ceis_discipline_determination", ""),
            fields.get("ceis_risk_assessment", ""),
            fields.get("ceis_recommendation", ""),
            int(fields.get("use_of_force_applies", 0)),
            int(fields.get("post_orders_apply", 0)),
            fields.get("post_order_details", ""),
            fields.get("additional_violations", ""),
            fields.get("discipline_level", ""),
            fields.get("final_narrative", ""),
            fields.get("final_citations", ""),
            fields.get("final_prior_discipline", ""),
            fields.get("final_coaching", ""),
            fields.get("required_improvements", ""),
            fields.get("additional_comments", ""),
            fields.get("da_payload", ""),
            fields.get("status", "draft"),
            int(fields.get("current_step", 1)),
            float(fields.get("attendance_points_at_da", 0)),
            fields.get("attendance_record_json", ""),
            fields.get("pdf_filename", ""),
            created_by,
            created_by,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return da_id


def get_da(da_id: str) -> dict | None:
    """Fetch a single DA record by ID."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM da_records WHERE da_id = ?", (da_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    record = dict(row)
    # Deserialize clarifying_qa from JSON
    try:
        record["clarifying_qa"] = json.loads(record.get("clarifying_qa", "[]"))
    except (json.JSONDecodeError, TypeError):
        record["clarifying_qa"] = []
    return record


def update_da(da_id: str, fields: dict, updated_by: str = "") -> bool:
    """Update an existing DA record. Only allowed fields are written."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM da_records WHERE da_id = ?", (da_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    # Serialize clarifying_qa if provided as a list
    if "clarifying_qa" in fields and isinstance(fields["clarifying_qa"], list):
        fields = dict(fields)
        fields["clarifying_qa"] = json.dumps(fields["clarifying_qa"])

    updates = []
    params = []
    for key in ALLOWED_FIELDS:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])

    if updates:
        updates.append("updated_by = ?")
        params.append(updated_by)
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(da_id)
        conn.execute(
            f"UPDATE da_records SET {', '.join(updates)} WHERE da_id = ?",
            params,
        )
        conn.commit()

    conn.close()
    return True


def get_all_das(status_filter: str = "") -> list:
    """Get all DA records, optionally filtered by status."""
    conn = get_conn()
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM da_records WHERE status = ? ORDER BY created_at DESC",
            (status_filter,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM da_records ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_da(da_id: str) -> bool:
    """Delete a DA record by ID."""
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM da_records WHERE da_id = ?", (da_id,)
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def check_duplicate_da(employee_name: str, incident_dates: str, violation_type: str) -> dict | None:
    """Check if a DA already exists for the same employee, same dates, same type.

    Returns the existing DA record dict if found, or None.
    """
    if not employee_name or not incident_dates:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM da_records "
        "WHERE LOWER(employee_name) = LOWER(?) "
        "  AND incident_dates = ? "
        "  AND violation_type = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (employee_name.strip(), incident_dates.strip(), violation_type.strip()),
    ).fetchone()
    conn.close()
    if row:
        record = dict(row)
        try:
            record["clarifying_qa"] = json.loads(record.get("clarifying_qa", "[]"))
        except (json.JSONDecodeError, TypeError):
            record["clarifying_qa"] = []
        return record
    return None


def get_das_for_employee(employee_name: str) -> list:
    """Get all DA records for a given employee (partial match)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM da_records WHERE employee_name LIKE ? ORDER BY created_at DESC",
        (f"%{employee_name}%",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_das_for_officer_id(officer_id: str) -> list:
    """Get all DA records for a given officer_id, most recent first."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM da_records WHERE employee_officer_id = ? ORDER BY created_at DESC",
        (officer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Acknowledgment Tracking ───────────────────────────────────────────

def acknowledge_da(da_id: str, acknowledged_by: str, employee_response: str = "") -> bool:
    """Mark a DA as acknowledged.

    Sets acknowledged=1, records who acknowledged, the timestamp, and the
    employee's response (e.g. "Acknowledged", "Acknowledged Under Protest",
    "Refused to Sign").  Returns ``True`` on success.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM da_records WHERE da_id = ?", (da_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    now = _now()
    conn.execute(
        """UPDATE da_records
           SET acknowledged = 1,
               acknowledged_by = ?,
               acknowledged_at = ?,
               employee_response = ?,
               updated_at = ?
           WHERE da_id = ?""",
        (acknowledged_by, now, employee_response, now, da_id),
    )
    conn.commit()
    conn.close()
    return True


def witness_sign_da(da_id: str, witness_name: str) -> bool:
    """Record a witness signature on a DA.

    Sets witness_name, witness_signed=1, and the timestamp.
    Returns ``True`` on success.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM da_records WHERE da_id = ?", (da_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    now = _now()
    conn.execute(
        """UPDATE da_records
           SET witness_name = ?,
               witness_signed = 1,
               witness_signed_at = ?,
               updated_at = ?
           WHERE da_id = ?""",
        (witness_name, now, now, da_id),
    )
    conn.commit()
    conn.close()
    return True


def get_pending_acknowledgments() -> list:
    """Return DAs that have been delivered but not yet acknowledged."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM da_records "
        "WHERE status = 'delivered' AND acknowledged = 0 "
        "ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Turnaround Statistics ─────────────────────────────────────────────

def get_da_turnaround_stats() -> dict:
    """Return turnaround statistics for completed DAs.

    Returns dict with keys:
        avg_hours, min_hours, max_hours  -- floats (0.0 if no data)
        open_count                       -- int
        completed_this_month             -- int
    """
    conn = get_conn()

    # All records
    rows = conn.execute(
        "SELECT status, created_at, updated_at, delivered_at, signed_at "
        "FROM da_records"
    ).fetchall()

    now = datetime.now(timezone.utc)
    current_month = now.month
    current_year = now.year

    completed_statuses = {"signed", "completed", "delivered"}
    open_count = 0
    completed_this_month = 0
    turnaround_hours: list[float] = []

    for r in rows:
        status = r["status"] or ""
        created_str = r["created_at"] or ""
        if not created_str:
            continue

        try:
            created_dt = datetime.fromisoformat(created_str)
        except (ValueError, TypeError):
            continue

        if status in completed_statuses:
            # Determine end timestamp
            end_str = ""
            signed_str = r["signed_at"] or ""
            delivered_str = r["delivered_at"] or ""
            updated_str = r["updated_at"] or ""

            if signed_str:
                end_str = signed_str
            elif delivered_str:
                end_str = delivered_str
            elif updated_str:
                end_str = updated_str

            if end_str:
                try:
                    end_dt = datetime.fromisoformat(end_str)
                    hours = (end_dt - created_dt).total_seconds() / 3600.0
                    if hours >= 0:
                        turnaround_hours.append(hours)

                    # Check if completed this month
                    if end_dt.month == current_month and end_dt.year == current_year:
                        completed_this_month += 1
                except (ValueError, TypeError):
                    pass
        else:
            open_count += 1

    conn.close()

    avg_hours = sum(turnaround_hours) / len(turnaround_hours) if turnaround_hours else 0.0
    min_hours = min(turnaround_hours) if turnaround_hours else 0.0
    max_hours = max(turnaround_hours) if turnaround_hours else 0.0

    return {
        "avg_hours": avg_hours,
        "min_hours": min_hours,
        "max_hours": max_hours,
        "open_count": open_count,
        "completed_this_month": completed_this_month,
    }


def get_da_extended_stats() -> dict:
    """Return extended statistics: avg draft-to-delivery hours, most common
    violation type, and DA counts per month for the last 6 months.

    Returns dict with keys:
        avg_draft_to_delivery_hours  -- float (0.0 if no data)
        most_common_violation        -- str (empty if no data)
        das_by_month                 -- list of (month_label, count) tuples, last 6 months
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT created_at, delivered_at, violation_type FROM da_records"
    ).fetchall()
    conn.close()

    now = datetime.now(timezone.utc)

    # Avg draft-to-delivery
    delivery_hours: list[float] = []
    violation_counts: dict[str, int] = {}

    # Monthly buckets for last 6 months
    from collections import OrderedDict
    month_buckets: dict[str, int] = OrderedDict()
    for i in range(5, -1, -1):
        d = now.replace(day=1) - timedelta(days=i * 30)
        key = d.strftime("%Y-%m")
        month_buckets[key] = 0

    for r in rows:
        created_str = r["created_at"] or ""
        delivered_str = r["delivered_at"] or ""
        vtype = r["violation_type"] or ""

        if vtype:
            violation_counts[vtype] = violation_counts.get(vtype, 0) + 1

        if created_str and delivered_str:
            try:
                c_dt = datetime.fromisoformat(created_str)
                d_dt = datetime.fromisoformat(delivered_str)
                hours = (d_dt - c_dt).total_seconds() / 3600.0
                if hours >= 0:
                    delivery_hours.append(hours)
            except (ValueError, TypeError):
                pass

        if created_str:
            month_key = created_str[:7]  # "YYYY-MM"
            if month_key in month_buckets:
                month_buckets[month_key] += 1

    avg_dtd = sum(delivery_hours) / len(delivery_hours) if delivery_hours else 0.0
    most_common = max(violation_counts, key=violation_counts.get) if violation_counts else ""

    das_by_month = [(k, v) for k, v in month_buckets.items()]

    return {
        "avg_draft_to_delivery_hours": avg_dtd,
        "most_common_violation": most_common,
        "das_by_month": das_by_month,
    }


# ── Settings ─────────────────────────────────────────────────────────

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


# ── Summary / Dashboard ──────────────────────────────────────────────

def get_da_summary() -> dict:
    """Return aggregate counts by status and discipline_level."""
    conn = get_conn()

    status_rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM da_records GROUP BY status"
    ).fetchall()
    status_counts = {r["status"]: r["cnt"] for r in status_rows}

    level_rows = conn.execute(
        "SELECT discipline_level, COUNT(*) as cnt FROM da_records "
        "WHERE discipline_level != '' GROUP BY discipline_level"
    ).fetchall()
    level_counts = {r["discipline_level"]: r["cnt"] for r in level_rows}

    total = sum(status_counts.values())

    conn.close()

    return {
        "total": total,
        "status_counts": status_counts,
        "level_counts": level_counts,
    }
