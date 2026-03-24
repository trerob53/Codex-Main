"""
Cerasus Hub -- Attendance Module: Predictive Attrition Risk Engine
Scores officers 0-100 on likelihood of leaving or being terminated.
"""

from datetime import date, timedelta

from src.database import get_conn
from src.modules.attendance.policy_engine import (
    calculate_active_points,
    POINT_WINDOW_DAYS,
)


def calculate_attrition_risk(officer_id: str) -> dict:
    """Score 0-100 risk of attrition/termination for a single officer.

    Factors:
        1. Active attendance points          (max 40 pts)
        2. Disciplinary Action (DA) count    (max 25 pts)
        3. Recent infraction frequency       (max 20 pts)
        4. Discipline escalation speed       (max 15 pts)

    Returns dict with score, level, factors list, and officer metadata.
    """
    conn = get_conn()

    # Fetch officer info
    off_row = conn.execute(
        "SELECT officer_id, name, site, hire_date, status FROM officers WHERE officer_id = ?",
        (officer_id,),
    ).fetchone()
    if not off_row:
        conn.close()
        return {"score": 0, "level": "low", "factors": [], "name": "", "site": ""}

    off = dict(off_row)

    # Fetch active infractions within the point window
    cutoff_date = (date.today() - timedelta(days=POINT_WINDOW_DAYS)).isoformat()
    inf_rows = conn.execute(
        """SELECT * FROM ats_infractions
           WHERE employee_id = ? AND points_active = 1
           ORDER BY infraction_date ASC""",
        (officer_id,),
    ).fetchall()
    infractions = [dict(r) for r in inf_rows]

    # Fetch DA records for this officer
    da_rows = conn.execute(
        "SELECT da_id, discipline_level, created_at FROM da_records WHERE employee_officer_id = ?",
        (officer_id,),
    ).fetchall()
    da_count = len(da_rows)

    conn.close()

    score = 0
    factors = []

    # ── Factor 1: Active points (max 40 pts) ────────────────────────
    active_pts = calculate_active_points(infractions)
    if active_pts >= 10:
        f1 = 40
    elif active_pts >= 8:
        f1 = 35
    elif active_pts >= 6:
        f1 = 30
    elif active_pts >= 4:
        f1 = 18
    elif active_pts >= 2:
        f1 = 8
    else:
        f1 = 0
    score += f1
    if f1 > 0:
        factors.append(f"{active_pts:.1f} active points (+{f1})")

    # ── Factor 2: DA count (max 25 pts) ─────────────────────────────
    if da_count >= 3:
        f2 = 25
    elif da_count == 2:
        f2 = 18
    elif da_count == 1:
        f2 = 10
    else:
        f2 = 0
    score += f2
    if f2 > 0:
        factors.append(f"{da_count} DA(s) on file (+{f2})")

    # ── Factor 3: Recent infraction frequency — last 90 days (max 20)
    recent_cutoff = (date.today() - timedelta(days=90)).isoformat()
    recent_count = sum(
        1 for inf in infractions
        if inf.get("infraction_date", "") >= recent_cutoff
    )
    if recent_count >= 3:
        f3 = 20
    elif recent_count == 2:
        f3 = 12
    elif recent_count == 1:
        f3 = 5
    else:
        f3 = 0
    score += f3
    if f3 > 0:
        factors.append(f"{recent_count} infraction(s) in last 90 days (+{f3})")

    # ── Factor 4: Discipline escalation speed (max 15 pts) ──────────
    # How quickly did the officer reach a Written Warning level?
    f4 = 0
    if infractions:
        first_date_str = infractions[0].get("infraction_date", "")
        # Find earliest infraction that triggered written_warning or higher
        ww_date_str = None
        for inf in infractions:
            disc = inf.get("discipline_triggered", "")
            if disc in ("written_warning", "employment_review", "termination_eligible", "termination_flag"):
                ww_date_str = inf.get("infraction_date", "")
                break

        if first_date_str and ww_date_str:
            try:
                first_d = date.fromisoformat(first_date_str[:10])
                ww_d = date.fromisoformat(ww_date_str[:10])
                gap_days = (ww_d - first_d).days
                if gap_days <= 90:
                    f4 = 15
                elif gap_days <= 180:
                    f4 = 10
            except (ValueError, TypeError):
                pass

    score += f4
    if f4 > 0:
        factors.append(f"Fast escalation to Written Warning (+{f4})")

    # Clamp
    score = min(score, 100)

    if score < 30:
        level = "low"
    elif score < 60:
        level = "moderate"
    elif score < 80:
        level = "high"
    else:
        level = "critical"

    return {
        "officer_id": officer_id,
        "name": off.get("name", ""),
        "site": off.get("site", ""),
        "score": score,
        "level": level,
        "factors": factors,
        "top_factor": factors[0] if factors else "",
    }


def get_at_risk_officers(min_level: str = "moderate", limit: int = 10) -> list[dict]:
    """Return officers at or above *min_level*, sorted by score descending.

    Levels (ascending severity): low, moderate, high, critical.
    Only 'Active' officers are evaluated.
    """
    level_order = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
    min_rank = level_order.get(min_level, 1)

    conn = get_conn()
    rows = conn.execute(
        "SELECT officer_id FROM officers WHERE status = 'Active'"
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        oid = row["officer_id"]
        risk = calculate_attrition_risk(oid)
        if level_order.get(risk["level"], 0) >= min_rank:
            results.append(risk)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]
