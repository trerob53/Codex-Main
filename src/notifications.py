"""
Cerasus Hub -- Notification Center
Aggregates alerts from all modules: approaching OT, expiring certs, pending reviews, low stock, etc.
"""

from datetime import datetime, timezone, timedelta, date
from src.database import get_conn


def get_all_alerts() -> list:
    """Gather alerts from all modules. Returns list of dicts sorted by severity."""
    alerts = []
    alerts.extend(_attendance_alerts())
    alerts.extend(_uniforms_alerts())
    alerts.extend(_operations_alerts())
    alerts.extend(_training_alerts())
    return sorted(
        alerts,
        key=lambda a: {"critical": 0, "warning": 1, "info": 2}.get(
            a.get("severity", "info"), 3
        ),
    )


def get_all_notifications() -> list[dict]:
    """Aggregate notification dicts across all modules.

    Each dict has keys: module, type, message, severity, timestamp, count, action_data.
    Uses try/except per module so one failure doesn't break others.
    """
    notifications: list[dict] = []

    # ── Attendance notifications ──────────────────────────────────────
    try:
        notifications.extend(_attendance_notifications())
    except Exception:
        pass

    # ── DA Generator notifications ────────────────────────────────────
    try:
        notifications.extend(_da_generator_notifications())
    except Exception:
        pass

    # ── Uniforms notifications (reuse existing alerts) ────────────────
    try:
        for a in _uniforms_alerts():
            notifications.append({
                "module": "uniforms",
                "type": "uniforms_alert",
                "message": a["title"],
                "severity": a["severity"],
                "timestamp": a["timestamp"],
                "count": 1,
                "action_data": {"detail": a.get("detail", "")},
            })
    except Exception:
        pass

    # ── Operations notifications (reuse existing alerts) ──────────────
    try:
        for a in _operations_alerts():
            notifications.append({
                "module": "operations",
                "type": "operations_alert",
                "message": a["title"],
                "severity": a["severity"],
                "timestamp": a["timestamp"],
                "count": 1,
                "action_data": {"detail": a.get("detail", "")},
            })
    except Exception:
        pass

    # ── Training notifications (reuse existing alerts) ────────────────
    try:
        for a in _training_alerts():
            notifications.append({
                "module": "training",
                "type": "training_alert",
                "message": a["title"],
                "severity": a["severity"],
                "timestamp": a["timestamp"],
                "count": 1,
                "action_data": {"detail": a.get("detail", "")},
            })
    except Exception:
        pass

    return sorted(
        notifications,
        key=lambda n: {"critical": 0, "warning": 1, "info": 2}.get(
            n.get("severity", "info"), 3
        ),
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str() -> str:
    return date.today().isoformat()


# ── Attendance Alerts ─────────────────────────────────────────────────

def _attendance_alerts() -> list:
    alerts = []
    try:
        conn = get_conn()

        # Officers with 8+ active points
        try:
            rows = conn.execute(
                "SELECT name, active_points FROM officers "
                "WHERE status = 'Active' AND active_points >= 8"
            ).fetchall()
            for r in rows:
                pts = r["active_points"]
                name = r["name"]
                if pts >= 10:
                    alerts.append({
                        "severity": "critical",
                        "module": "ATTENDANCE",
                        "title": f"Officer {name} has {pts} active points",
                        "detail": "Termination eligible per attendance policy",
                        "timestamp": _now_iso(),
                    })
                else:
                    alerts.append({
                        "severity": "critical",
                        "module": "ATTENDANCE",
                        "title": f"Officer {name} has {pts} active points",
                        "detail": "Employment review triggered",
                        "timestamp": _now_iso(),
                    })
        except Exception:
            pass

        # Pending employment reviews
        try:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM ats_employment_reviews "
                "WHERE review_status = 'Pending'"
            ).fetchone()
            count = row["c"] if row else 0
            if count > 0:
                alerts.append({
                    "severity": "warning",
                    "module": "ATTENDANCE",
                    "title": f"{count} pending employment review{'s' if count != 1 else ''}",
                    "detail": "Reviews awaiting supervisor action",
                    "timestamp": _now_iso(),
                })
        except Exception:
            pass

        # Officers approaching clean slate (within 7 days of 90-day no-infraction mark)
        try:
            cutoff = (date.today() - timedelta(days=83)).isoformat()  # 90 - 7 = 83
            threshold = (date.today() - timedelta(days=90)).isoformat()
            rows = conn.execute(
                "SELECT o.name, o.last_infraction_date FROM officers o "
                "WHERE o.status = 'Active' AND o.active_points > 0 "
                "AND o.last_infraction_date != '' AND o.last_infraction_date <= ? "
                "AND o.last_infraction_date > ?",
                (cutoff, threshold),
            ).fetchall()
            for r in rows:
                alerts.append({
                    "severity": "info",
                    "module": "ATTENDANCE",
                    "title": f"{r['name']} approaching clean slate",
                    "detail": f"Last infraction: {r['last_infraction_date']} -- within 7 days of 90-day mark",
                    "timestamp": _now_iso(),
                })
        except Exception:
            pass

        conn.close()
    except Exception:
        pass
    return alerts


# ── Attendance Notifications (granular format) ───────────────────────

def _attendance_notifications() -> list[dict]:
    """Attendance-specific notifications: expiring points, near-termination, today's infractions."""
    notifications: list[dict] = []
    try:
        conn = get_conn()

        # Officers at/near termination threshold (8+ points)
        try:
            rows = conn.execute(
                "SELECT name, officer_id, active_points FROM officers "
                "WHERE status = 'Active' AND active_points >= 8"
            ).fetchall()
            for r in rows:
                pts = r["active_points"]
                name = r["name"]
                sev = "critical" if pts >= 10 else "warning"
                detail = "Termination eligible" if pts >= 10 else "Employment review triggered"
                notifications.append({
                    "module": "attendance",
                    "type": "near_termination",
                    "message": f"{name} has {pts} active points -- {detail}",
                    "severity": sev,
                    "timestamp": _now_iso(),
                    "count": int(pts),
                    "action_data": {"officer_id": r["officer_id"]},
                })
        except Exception:
            pass

        # Points expiring within 30 days
        try:
            cutoff = (date.today() + timedelta(days=30)).isoformat()
            today = _today_str()
            rows = conn.execute(
                "SELECT i.employee_id, i.points_assigned, i.point_expiry_date, o.name "
                "FROM ats_infractions i "
                "LEFT JOIN officers o ON i.employee_id = o.officer_id "
                "WHERE i.points_active = 1 AND i.point_expiry_date != '' "
                "AND i.point_expiry_date >= ? AND i.point_expiry_date <= ?",
                (today, cutoff),
            ).fetchall()
            if rows:
                # Group by officer
                by_officer: dict[str, list] = {}
                for r in rows:
                    name = r["name"] or r["employee_id"]
                    by_officer.setdefault(name, []).append(r)
                for name, infrs in by_officer.items():
                    total_pts = sum(r["points_assigned"] for r in infrs)
                    earliest = min(r["point_expiry_date"] for r in infrs)
                    notifications.append({
                        "module": "attendance",
                        "type": "expiring_points",
                        "message": f"{name} has {total_pts:.0f} pts expiring on {earliest}",
                        "severity": "warning",
                        "timestamp": _now_iso(),
                        "count": len(infrs),
                        "action_data": {"officer_name": name, "expiry_date": earliest},
                    })
        except Exception:
            pass

        # Infractions logged today (informational)
        try:
            today = _today_str()
            row = conn.execute(
                "SELECT COUNT(*) as c FROM ats_infractions WHERE infraction_date = ?",
                (today,),
            ).fetchone()
            count = row["c"] if row else 0
            if count > 0:
                notifications.append({
                    "module": "attendance",
                    "type": "today_infractions",
                    "message": f"{count} infraction{'s' if count != 1 else ''} logged today",
                    "severity": "info",
                    "timestamp": _now_iso(),
                    "count": count,
                    "action_data": {},
                })
        except Exception:
            pass

        conn.close()
    except Exception:
        pass
    return notifications


# ── DA Generator Notifications ───────────────────────────────────────

def _da_generator_notifications() -> list[dict]:
    """DA Generator notifications: stale drafts and pending reviews."""
    notifications: list[dict] = []
    try:
        conn = get_conn()

        # DAs in draft or pending_review status for more than 3 days
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            rows = conn.execute(
                "SELECT da_id, employee_name, status, created_at, updated_at "
                "FROM da_records "
                "WHERE status IN ('draft', 'pending_review') "
                "AND created_at != '' AND created_at <= ?",
                (cutoff,),
            ).fetchall()
            for r in rows:
                name = r["employee_name"] or "Unknown"
                status = r["status"]
                notifications.append({
                    "module": "da_generator",
                    "type": "stale_da",
                    "message": f"DA for {name} in '{status}' for 3+ days",
                    "severity": "warning",
                    "timestamp": _now_iso(),
                    "count": 1,
                    "action_data": {"da_id": r["da_id"], "status": status},
                })
        except Exception:
            pass

        conn.close()
    except Exception:
        pass
    return notifications


# ── Uniforms Alerts ───────────────────────────────────────────────────

def _uniforms_alerts() -> list:
    alerts = []
    try:
        conn = get_conn()

        # Items at zero stock (critical)
        try:
            rows = conn.execute(
                "SELECT name FROM uni_catalog WHERE stock_qty <= 0"
            ).fetchall()
            for r in rows:
                alerts.append({
                    "severity": "critical",
                    "module": "UNIFORMS",
                    "title": f"{r['name']} is out of stock",
                    "detail": "Catalog item has zero inventory",
                    "timestamp": _now_iso(),
                })
        except Exception:
            pass

        # Items at or below reorder point (warning) -- exclude already-zero items
        try:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM uni_catalog "
                "WHERE stock_qty <= reorder_point AND stock_qty > 0"
            ).fetchone()
            count = row["c"] if row else 0
            if count > 0:
                alerts.append({
                    "severity": "warning",
                    "module": "UNIFORMS",
                    "title": f"{count} catalog item{'s' if count != 1 else ''} at or below reorder point",
                    "detail": "Stock levels need attention",
                    "timestamp": _now_iso(),
                })
        except Exception:
            pass

        # Pending orders overdue
        try:
            today = _today_str()
            row = conn.execute(
                "SELECT COUNT(*) as c FROM uni_pending_orders "
                "WHERE status = 'Pending' AND date_expected != '' AND date_expected < ?",
                (today,),
            ).fetchone()
            count = row["c"] if row else 0
            if count > 0:
                alerts.append({
                    "severity": "warning",
                    "module": "UNIFORMS",
                    "title": f"{count} pending order{'s' if count != 1 else ''} overdue",
                    "detail": "Expected delivery date has passed",
                    "timestamp": _now_iso(),
                })
        except Exception:
            pass

        # Replacement items due within 30 days (based on lifecycle)
        try:
            cutoff = (date.today() + timedelta(days=30)).isoformat()
            rows = conn.execute(
                "SELECT COUNT(*) as c FROM uni_issuances i "
                "JOIN uni_catalog c ON i.item_id = c.item_id "
                "WHERE i.status = 'Outstanding' AND c.lifecycle_days > 0 "
                "AND date(i.date_issued, '+' || c.lifecycle_days || ' days') <= ? "
                "AND date(i.date_issued, '+' || c.lifecycle_days || ' days') >= date('now')",
                (cutoff,),
            ).fetchone()
            count = rows["c"] if rows else 0
            if count > 0:
                alerts.append({
                    "severity": "info",
                    "module": "UNIFORMS",
                    "title": f"{count} replacement item{'s' if count != 1 else ''} due within 30 days",
                    "detail": "Issued items approaching lifecycle end",
                    "timestamp": _now_iso(),
                })
        except Exception:
            pass

        conn.close()
    except Exception:
        pass
    return alerts


# ── Operations Alerts ─────────────────────────────────────────────────

def _operations_alerts() -> list:
    alerts = []
    try:
        conn = get_conn()

        # Open/unassigned requests
        try:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM ops_records WHERE status = 'Open'"
            ).fetchone()
            count = row["c"] if row else 0
            if count > 0:
                alerts.append({
                    "severity": "warning",
                    "module": "OPERATIONS",
                    "title": f"{count} open request{'s' if count != 1 else ''} need attention",
                    "detail": "Unresolved operations records",
                    "timestamp": _now_iso(),
                })
        except Exception:
            pass

        # Sites with no coverage today or next 7 days
        try:
            today = _today_str()
            end_window = (date.today() + timedelta(days=7)).isoformat()

            # Get active sites
            sites = conn.execute(
                "SELECT site_id, name FROM sites WHERE status = 'Active'"
            ).fetchall()

            # Get sites that have assignments in the window
            covered = conn.execute(
                "SELECT DISTINCT site_name FROM ops_assignments "
                "WHERE date >= ? AND date <= ? AND status != 'Cancelled'",
                (today, end_window),
            ).fetchall()
            covered_names = {r["site_name"] for r in covered}

            uncovered = [s for s in sites if s["name"] not in covered_names]
            if uncovered:
                names = ", ".join(s["name"] for s in uncovered[:3])
                more = f" +{len(uncovered) - 3} more" if len(uncovered) > 3 else ""
                alerts.append({
                    "severity": "critical",
                    "module": "OPERATIONS",
                    "title": f"{len(uncovered)} site{'s' if len(uncovered) != 1 else ''} with no coverage",
                    "detail": f"No assignments next 7 days: {names}{more}",
                    "timestamp": _now_iso(),
                })
        except Exception:
            pass

        conn.close()
    except Exception:
        pass
    return alerts


# ── Training Alerts ───────────────────────────────────────────────────

def _training_alerts() -> list:
    alerts = []
    try:
        conn = get_conn()

        # Certificates expiring within 30 days
        try:
            cutoff = (date.today() + timedelta(days=30)).isoformat()
            today = _today_str()
            rows = conn.execute(
                "SELECT c.cert_id, c.officer_id, c.expiry_date, o.name as officer_name, "
                "cr.title as course_title "
                "FROM trn_certificates c "
                "LEFT JOIN officers o ON c.officer_id = o.officer_id "
                "LEFT JOIN trn_courses cr ON c.course_id = cr.course_id "
                "WHERE c.status = 'Active' AND c.expiry_date != '' "
                "AND c.expiry_date <= ? AND c.expiry_date >= ?",
                (cutoff, today),
            ).fetchall()
            if rows:
                for r in rows:
                    name = r["officer_name"] or r["officer_id"]
                    course = r["course_title"] or "Unknown course"
                    alerts.append({
                        "severity": "warning",
                        "module": "TRAINING",
                        "title": f"Certificate expiring: {name}",
                        "detail": f"{course} -- expires {r['expiry_date']}",
                        "timestamp": _now_iso(),
                    })
        except Exception:
            pass

        # Officers with 0% training completion
        try:
            # Active officers who have no progress records at all
            row = conn.execute(
                "SELECT COUNT(*) as c FROM officers o "
                "WHERE o.status = 'Active' "
                "AND NOT EXISTS (SELECT 1 FROM trn_progress p WHERE p.officer_id = o.officer_id AND p.completed = 1)"
            ).fetchone()
            count = row["c"] if row else 0
            if count > 0:
                alerts.append({
                    "severity": "info",
                    "module": "TRAINING",
                    "title": f"{count} officer{'s' if count != 1 else ''} with no training progress",
                    "detail": "No completed training modules on record",
                    "timestamp": _now_iso(),
                })
        except Exception:
            pass

        conn.close()
    except Exception:
        pass
    return alerts
