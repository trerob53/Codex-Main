"""
Cerasus Hub -- Attendance Module: Duplicate Scanner
Detect duplicate infractions and rapid-fire audit entries.
"""

from datetime import datetime, timedelta


def scan_infraction_duplicates(infractions: list) -> list:
    """Find same-day or near-day (within 1 day) duplicates for same employee+type.

    Returns list of dicts: {infraction_a, infraction_b, reason}
    """
    duplicates = []
    seen = []

    for inf in infractions:
        emp = inf.get("employee_id", "")
        itype = inf.get("infraction_type", "")
        idate = inf.get("infraction_date", "")

        if not emp or not itype or not idate:
            continue

        try:
            d = datetime.fromisoformat(idate).date() if "T" in idate else datetime.strptime(idate, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        for prev_inf, prev_date in seen:
            if prev_inf.get("employee_id") == emp and prev_inf.get("infraction_type") == itype:
                delta = abs((d - prev_date).days)
                if delta == 0:
                    duplicates.append({
                        "infraction_a": prev_inf,
                        "infraction_b": inf,
                        "reason": f"Same-day duplicate: {itype} for employee {emp} on {idate}",
                    })
                elif delta <= 1:
                    duplicates.append({
                        "infraction_a": prev_inf,
                        "infraction_b": inf,
                        "reason": f"Near-day duplicate: {itype} for employee {emp} ({delta} day apart)",
                    })

        seen.append((inf, d))

    return duplicates


def scan_rapid_fire_audit(audit_entries: list) -> list:
    """Find same-user same-action entries within 5 seconds.

    Returns list of dicts: {entry_a, entry_b, reason}
    """
    rapid = []

    for i, entry in enumerate(audit_entries):
        user = entry.get("username", "")
        action = entry.get("event_type", "") or entry.get("action", "")
        ts_str = entry.get("timestamp", "")

        if not user or not action or not ts_str:
            continue

        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            continue

        for j in range(i + 1, len(audit_entries)):
            other = audit_entries[j]
            other_user = other.get("username", "")
            other_action = other.get("event_type", "") or other.get("action", "")
            other_ts_str = other.get("timestamp", "")

            if other_user != user or other_action != action:
                continue
            if not other_ts_str:
                continue

            try:
                other_ts = datetime.fromisoformat(other_ts_str)
            except (ValueError, TypeError):
                continue

            delta = abs((ts - other_ts).total_seconds())
            if delta <= 5:
                rapid.append({
                    "entry_a": entry,
                    "entry_b": other,
                    "reason": f"Rapid-fire: {user} performed '{action}' twice within {delta:.1f}s",
                })

    return rapid
