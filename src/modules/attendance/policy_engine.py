"""
Cerasus Hub -- Attendance Module: Policy Engine
Core discipline logic, point calculations, thresholds, and clean-slate checks.
"""

from datetime import datetime, date, timedelta

from src.database import get_conn
from src.shared_data import get_all_officers, update_officer


# ── Infraction Type Definitions ───────────────────────────────────────

INFRACTION_TYPES = {
    "tardiness_1st": {
        "label": "Tardiness (1st Offense)",
        "points": 0,
        "auto_discipline": "verbal_warning",
        "category": "Tardiness",
    },
    "tardiness_additional": {
        "label": "Tardiness (Additional)",
        "points": 1.5,
        "auto_discipline": "",
        "category": "Tardiness",
    },
    "extreme_tardiness_1st": {
        "label": "Extreme Tardiness (1st Offense)",
        "points": 6,
        "auto_discipline": "written_warning",
        "category": "Tardiness",
    },
    "extreme_tardiness_2nd": {
        "label": "Extreme Tardiness (2nd Offense)",
        "points": 0,
        "auto_discipline": "termination_flag",
        "category": "Tardiness",
    },
    "calloff_proper_notice_1st": {
        "label": "Call-Off w/ Proper Notice (1st)",
        "points": 0,
        "auto_discipline": "verbal_warning",
        "category": "Call-Off",
    },
    "calloff_proper_notice_additional": {
        "label": "Call-Off w/ Proper Notice (Additional)",
        "points": 2,
        "auto_discipline": "",
        "category": "Call-Off",
    },
    "calloff_under4h": {
        "label": "Call-Off Under 4hr Notice",
        "points": 3,
        "auto_discipline": "",
        "category": "Call-Off",
    },
    "calloff_under2h": {
        "label": "Call-Off Under 2hr Notice",
        "points": 4,
        "auto_discipline": "",
        "category": "Call-Off",
    },
    "ncns_1st": {
        "label": "No Call / No Show (1st)",
        "points": 6,
        "auto_discipline": "written_warning",
        "category": "NCNS",
    },
    "ncns_2nd": {
        "label": "No Call / No Show (2nd)",
        "points": 0,
        "auto_discipline": "termination_flag",
        "category": "NCNS",
    },
    "post_abandonment": {
        "label": "Post Abandonment",
        "points": 6,
        "auto_discipline": "written_warning",
        "category": "NCNS",
    },
    "emergency_exemption_denied": {
        "label": "Emergency Exemption (Denied)",
        "points": 3,
        "auto_discipline": "",
        "category": "Emergency",
    },
    "emergency_exemption_approved": {
        "label": "Emergency Exemption (Approved)",
        "points": 0,
        "auto_discipline": "",
        "category": "Emergency",
    },
}


# ── Discipline Thresholds ─────────────────────────────────────────────

THRESHOLDS = [
    (1.5, "verbal_warning"),
    (6, "written_warning"),
    (8, "employment_review"),
    (10, "termination_eligible"),
]

POINT_WINDOW_DAYS = 365
CLEAN_SLATE_DAYS = 90
EMERGENCY_MAX = 2
REVIEW_TRIGGER_POINTS = 8
TERMINATION_POINTS = 10

DISCIPLINE_LABELS = {
    "": "None",
    "none": "None",
    "verbal_warning": "Verbal Warning",
    "written_warning": "Written Warning",
    "employment_review": "Employment Review",
    "termination_eligible": "Termination Eligible",
    "termination_flag": "Termination Flag",
}


# ── Point Calculation ─────────────────────────────────────────────────

def calculate_active_points(infractions: list) -> float:
    """Sum points where infraction_date is within 365 days and points_active=1."""
    cutoff = (date.today() - timedelta(days=POINT_WINDOW_DAYS)).isoformat()
    total = 0.0
    for inf in infractions:
        if not inf.get("points_active", 1):
            continue
        inf_date = inf.get("infraction_date", "")
        if inf_date and inf_date >= cutoff:
            total += float(inf.get("points_assigned", 0))
    return round(total, 2)


def determine_discipline_level(active_points: float) -> str:
    """Return discipline level string based on point thresholds."""
    level = "none"
    for threshold, discipline in THRESHOLDS:
        if active_points >= threshold:
            level = discipline
    return level


def check_point_expiry(infraction: dict) -> bool:
    """Return True if the infraction is expired (older than 365 days)."""
    inf_date = infraction.get("infraction_date", "")
    if not inf_date:
        return False
    try:
        d = datetime.fromisoformat(inf_date).date() if "T" in inf_date else date.fromisoformat(inf_date)
        return (date.today() - d).days > POINT_WINDOW_DAYS
    except (ValueError, TypeError):
        return False


def count_emergency_exemptions(infractions: list, days: int = 90) -> int:
    """Count approved emergency exemptions in the last N days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    count = 0
    for inf in infractions:
        if inf.get("infraction_type") in ("emergency_exemption_approved", "emergency_exemption_denied"):
            if inf.get("exemption_approved") and inf.get("infraction_date", "") >= cutoff:
                count += 1
    return count


def should_trigger_review(active_points: float) -> bool:
    """True if active points >= REVIEW_TRIGGER_POINTS."""
    return active_points >= REVIEW_TRIGGER_POINTS


def is_clean_slate(infractions: list, days: int = 90) -> bool:
    """True if no infractions in the last N days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    for inf in infractions:
        if inf.get("infraction_date", "") >= cutoff:
            return False
    return True


def get_point_expiry_date(infraction_date: str) -> str:
    """Calculate the expiry date (infraction_date + 365 days)."""
    if not infraction_date:
        return ""
    try:
        d = datetime.fromisoformat(infraction_date).date() if "T" in infraction_date else date.fromisoformat(infraction_date)
        return (d + timedelta(days=POINT_WINDOW_DAYS)).isoformat()
    except (ValueError, TypeError):
        return ""


# ── Recalculation ─────────────────────────────────────────────────────

def recalc_all_discipline_levels():
    """Recalculate all officers' active_points and discipline_level from infractions."""
    conn = get_conn()

    # Expire old infractions
    cutoff = (date.today() - timedelta(days=POINT_WINDOW_DAYS)).isoformat()
    conn.execute(
        "UPDATE ats_infractions SET points_active = 0 WHERE infraction_date < ? AND points_active = 1",
        (cutoff,),
    )
    conn.commit()

    # Get all officers
    officers = get_all_officers()

    for off in officers:
        oid = off.get("officer_id", "") or off.get("employee_id", "")
        if not oid:
            continue

        # Get active infractions for this officer
        rows = conn.execute(
            "SELECT * FROM ats_infractions WHERE employee_id = ? AND points_active = 1",
            (oid,),
        ).fetchall()
        infractions = [dict(r) for r in rows]

        active_pts = calculate_active_points(infractions)
        level = determine_discipline_level(active_pts)

        # Get last infraction date
        last_inf = conn.execute(
            "SELECT MAX(infraction_date) as d FROM ats_infractions WHERE employee_id = ?",
            (oid,),
        ).fetchone()
        last_date = last_inf["d"] if last_inf and last_inf["d"] else ""

        # Count emergency exemptions
        exemptions = count_emergency_exemptions(infractions)

        update_officer(oid, {
            "active_points": active_pts,
            "discipline_level": DISCIPLINE_LABELS.get(level, level),
            "last_infraction_date": last_date,
            "emergency_exemptions_used": exemptions,
        })

    conn.close()
