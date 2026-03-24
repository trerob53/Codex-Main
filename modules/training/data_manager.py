"""
Cerasus Hub -- Training Module: Data Manager
SQLite-backed CRUD for all trn_* tables.
Officers and sites are delegated to the shared data layer.
"""

import json
import secrets
from datetime import datetime, timezone, timedelta

from src.database import get_conn
from src.shared_data import (
    get_all_officers,
    get_officer,
    get_active_officers,
    get_officer_names,
    get_all_sites,
    get_site_names,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _gen_id() -> str:
    return secrets.token_hex(8)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════
# Courses
# ══════════════════════════════════════════════════════════════════════

def get_all_courses() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trn_courses ORDER BY title").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_courses_for_user(role: str = "", user_sites: list = None) -> list:
    """Get published courses visible to a user based on their role and site.

    A course is visible if:
    - No assigned_roles AND no assigned_sites (available to everyone), OR
    - User's role is in assigned_roles, OR
    - User's site(s) overlap with assigned_sites
    """
    import json
    all_courses = get_all_courses()
    visible = []
    for c in all_courses:
        if c.get("status") != "Published":
            continue
        # Parse stored JSON arrays
        try:
            c_roles = json.loads(c.get("assigned_roles", "") or "[]")
        except (json.JSONDecodeError, TypeError):
            c_roles = []
        try:
            c_sites = json.loads(c.get("assigned_sites", "") or "[]")
        except (json.JSONDecodeError, TypeError):
            c_sites = []
        # If no restrictions, everyone can see it
        if not c_roles and not c_sites:
            visible.append(c)
            continue
        # Check role match
        if c_roles and role in c_roles:
            visible.append(c)
            continue
        # Check site match
        if c_sites and user_sites:
            if any(s in c_sites for s in user_sites):
                visible.append(c)
                continue
    return visible


def get_course(course_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM trn_courses WHERE course_id = ?", (course_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_course(fields: dict) -> str:
    cid = fields.get("course_id") or _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO trn_courses
           (course_id, title, description, category, image_path, status, created_by,
            assigned_roles, assigned_sites, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (cid, fields.get("title", ""), fields.get("description", ""),
         fields.get("category", "General Training"), fields.get("image_path", ""),
         fields.get("status", "Published"), fields.get("created_by", ""),
         fields.get("assigned_roles", ""), fields.get("assigned_sites", ""),
         now, now),
    )
    conn.commit()
    conn.close()
    return cid


def update_course(course_id: str, fields: dict) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM trn_courses WHERE course_id = ?", (course_id,)).fetchone()
    if not row:
        conn.close()
        return False
    allowed = ["title", "description", "category", "image_path", "status", "created_by",
                "assigned_roles", "assigned_sites"]
    updates, params = [], []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])
    if updates:
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(course_id)
        conn.execute(f"UPDATE trn_courses SET {', '.join(updates)} WHERE course_id = ?", params)
        conn.commit()
    conn.close()
    return True


def delete_course(course_id: str) -> bool:
    conn = get_conn()
    # Cascade: delete modules, chapters, tests, progress, attempts, certs
    conn.execute("DELETE FROM trn_chapters WHERE course_id = ?", (course_id,))
    conn.execute("DELETE FROM trn_modules WHERE course_id = ?", (course_id,))
    conn.execute("DELETE FROM trn_tests WHERE course_id = ?", (course_id,))
    conn.execute("DELETE FROM trn_progress WHERE course_id = ?", (course_id,))
    conn.execute("DELETE FROM trn_test_attempts WHERE course_id = ?", (course_id,))
    conn.execute("DELETE FROM trn_certificates WHERE course_id = ?", (course_id,))
    cur = conn.execute("DELETE FROM trn_courses WHERE course_id = ?", (course_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


# ══════════════════════════════════════════════════════════════════════
# Modules
# ══════════════════════════════════════════════════════════════════════

def get_modules_for_course(course_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trn_modules WHERE course_id = ? ORDER BY sort_order", (course_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_module(fields: dict) -> str:
    mid = fields.get("module_id") or _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO trn_modules (module_id, course_id, title, sort_order, created_at)
           VALUES (?,?,?,?,?)""",
        (mid, fields.get("course_id", ""), fields.get("title", ""),
         fields.get("sort_order", 0), now),
    )
    conn.commit()
    conn.close()
    return mid


def update_module(module_id: str, fields: dict) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM trn_modules WHERE module_id = ?", (module_id,)).fetchone()
    if not row:
        conn.close()
        return False
    allowed = ["title", "sort_order", "course_id"]
    updates, params = [], []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])
    if updates:
        params.append(module_id)
        conn.execute(f"UPDATE trn_modules SET {', '.join(updates)} WHERE module_id = ?", params)
        conn.commit()
    conn.close()
    return True


def delete_module(module_id: str) -> bool:
    conn = get_conn()
    # Cascade: delete chapters belonging to this module
    conn.execute("DELETE FROM trn_chapters WHERE module_id = ?", (module_id,))
    cur = conn.execute("DELETE FROM trn_modules WHERE module_id = ?", (module_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


# ══════════════════════════════════════════════════════════════════════
# Chapters
# ══════════════════════════════════════════════════════════════════════

def get_chapters_for_module(module_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trn_chapters WHERE module_id = ? ORDER BY sort_order", (module_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_chapters_for_course(course_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trn_chapters WHERE course_id = ? ORDER BY sort_order", (course_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_chapter(fields: dict) -> str:
    chid = fields.get("chapter_id") or _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO trn_chapters
           (chapter_id, module_id, course_id, title, content, sort_order, has_test, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (chid, fields.get("module_id", ""), fields.get("course_id", ""),
         fields.get("title", ""), fields.get("content", ""),
         fields.get("sort_order", 0), fields.get("has_test", 0), now),
    )
    conn.commit()
    conn.close()
    return chid


def update_chapter(chapter_id: str, fields: dict) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM trn_chapters WHERE chapter_id = ?", (chapter_id,)).fetchone()
    if not row:
        conn.close()
        return False
    allowed = ["title", "content", "sort_order", "has_test", "module_id", "course_id"]
    updates, params = [], []
    for key in allowed:
        if key in fields:
            updates.append(f"{key} = ?")
            params.append(fields[key])
    if updates:
        params.append(chapter_id)
        conn.execute(f"UPDATE trn_chapters SET {', '.join(updates)} WHERE chapter_id = ?", params)
        conn.commit()
    conn.close()
    return True


def delete_chapter(chapter_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM trn_chapters WHERE chapter_id = ?", (chapter_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

def get_test_for_chapter(chapter_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM trn_tests WHERE chapter_id = ?", (chapter_id,)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        try:
            d["questions"] = json.loads(d.get("questions", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["questions"] = []
        return d
    return None


def get_tests_for_course(course_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trn_tests WHERE course_id = ?", (course_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["questions"] = json.loads(d.get("questions", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["questions"] = []
        result.append(d)
    return result


def create_test(fields: dict) -> str:
    tid = fields.get("test_id") or _gen_id()
    now = _now()
    questions = fields.get("questions", [])
    if isinstance(questions, list):
        questions = json.dumps(questions)
    conn = get_conn()
    conn.execute(
        """INSERT INTO trn_tests (test_id, chapter_id, course_id, title, passing_score, questions, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (tid, fields.get("chapter_id", ""), fields.get("course_id", ""),
         fields.get("title", ""), fields.get("passing_score", 70.0), questions, now),
    )
    conn.commit()
    conn.close()
    return tid


def update_test(test_id: str, fields: dict) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM trn_tests WHERE test_id = ?", (test_id,)).fetchone()
    if not row:
        conn.close()
        return False
    allowed = ["chapter_id", "course_id", "title", "passing_score", "questions"]
    updates, params = [], []
    for key in allowed:
        if key in fields:
            val = fields[key]
            if key == "questions" and isinstance(val, list):
                val = json.dumps(val)
            updates.append(f"{key} = ?")
            params.append(val)
    if updates:
        params.append(test_id)
        conn.execute(f"UPDATE trn_tests SET {', '.join(updates)} WHERE test_id = ?", params)
        conn.commit()
    conn.close()
    return True


# ══════════════════════════════════════════════════════════════════════
# Progress
# ══════════════════════════════════════════════════════════════════════

def get_progress(officer_id: str, course_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trn_progress WHERE officer_id = ? AND course_id = ?",
        (officer_id, course_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_chapter_complete(officer_id: str, course_id: str, chapter_id: str) -> bool:
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO trn_progress (officer_id, course_id, chapter_id, completed, completed_at)
           VALUES (?, ?, ?, 1, ?)
           ON CONFLICT(officer_id, course_id, chapter_id) DO UPDATE SET completed = 1, completed_at = ?""",
        (officer_id, course_id, chapter_id, now, now),
    )
    conn.commit()
    conn.close()
    return True


def get_course_progress(officer_id: str, course_id: str) -> dict:
    """Return detailed progress: total chapters, completed count, and percent."""
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM trn_chapters WHERE course_id = ?", (course_id,)
    ).fetchone()["cnt"]
    if total == 0:
        conn.close()
        return {"total_chapters": 0, "completed": 0, "percent": 0.0}
    done = conn.execute(
        """SELECT COUNT(*) as cnt FROM trn_progress
           WHERE officer_id = ? AND course_id = ? AND chapter_id != '' AND completed = 1""",
        (officer_id, course_id),
    ).fetchone()["cnt"]
    conn.close()
    pct = round((done / total) * 100, 1)
    return {"total_chapters": total, "completed": done, "percent": pct}


def all_course_tests_passed(officer_id: str, course_id: str) -> bool:
    """Check if the officer has passed all tests in the course (at least once)."""
    conn = get_conn()
    tests = conn.execute(
        "SELECT test_id FROM trn_tests WHERE course_id = ?", (course_id,)
    ).fetchall()
    if not tests:
        conn.close()
        return True  # No tests means nothing to fail
    for t in tests:
        best = conn.execute(
            """SELECT MAX(passed) as best FROM trn_test_attempts
               WHERE officer_id = ? AND test_id = ?""",
            (officer_id, t["test_id"]),
        ).fetchone()
        if not best or not best["best"]:
            conn.close()
            return False
    conn.close()
    return True


def get_course_completion_pct(officer_id: str, course_id: str) -> float:
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM trn_chapters WHERE course_id = ?", (course_id,)
    ).fetchone()["cnt"]
    if total == 0:
        conn.close()
        return 0.0
    done = conn.execute(
        """SELECT COUNT(*) as cnt FROM trn_progress
           WHERE officer_id = ? AND course_id = ? AND chapter_id != '' AND completed = 1""",
        (officer_id, course_id),
    ).fetchone()["cnt"]
    conn.close()
    return round((done / total) * 100, 1)


# ══════════════════════════════════════════════════════════════════════
# Test Attempts
# ══════════════════════════════════════════════════════════════════════

def get_attempts_for_officer(officer_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT a.*, t.title as test_title, c.title as course_title
           FROM trn_test_attempts a
           LEFT JOIN trn_tests t ON a.test_id = t.test_id
           LEFT JOIN trn_courses c ON a.course_id = c.course_id
           WHERE a.officer_id = ?
           ORDER BY a.completed_at DESC""",
        (officer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_attempt(fields: dict) -> str:
    aid = fields.get("attempt_id") or _gen_id()
    now = _now()
    answers = fields.get("answers", [])
    if isinstance(answers, list):
        answers = json.dumps(answers)
    conn = get_conn()
    conn.execute(
        """INSERT INTO trn_test_attempts
           (attempt_id, officer_id, test_id, course_id, score, passed, answers, started_at, completed_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (aid, fields.get("officer_id", ""), fields.get("test_id", ""),
         fields.get("course_id", ""), fields.get("score", 0),
         fields.get("passed", 0), answers,
         fields.get("started_at", now), fields.get("completed_at", now)),
    )
    conn.commit()
    conn.close()
    return aid


def get_best_attempt(officer_id: str, test_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM trn_test_attempts
           WHERE officer_id = ? AND test_id = ?
           ORDER BY score DESC LIMIT 1""",
        (officer_id, test_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════════════
# Certificates
# ══════════════════════════════════════════════════════════════════════

def get_certificates_for_officer(officer_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT cert.*, c.title as course_title
           FROM trn_certificates cert
           LEFT JOIN trn_courses c ON cert.course_id = c.course_id
           WHERE cert.officer_id = ?
           ORDER BY cert.issued_date DESC""",
        (officer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_certificates() -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT cert.*, c.title as course_title, o.name as officer_name, o.site as officer_site
           FROM trn_certificates cert
           LEFT JOIN trn_courses c ON cert.course_id = c.course_id
           LEFT JOIN officers o ON cert.officer_id = o.officer_id
           ORDER BY cert.issued_date DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def issue_certificate(officer_id: str, course_id: str, points: int = 100,
                      completion_date: str = "") -> str:
    cid = _gen_id()
    now = _now()
    # Use completion_date if provided; otherwise fall back to today
    if completion_date:
        try:
            base_dt = datetime.strptime(completion_date[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            base_dt = datetime.now(timezone.utc)
    else:
        base_dt = datetime.now(timezone.utc)
    today = base_dt.strftime("%Y-%m-%d")
    expiry = (base_dt + timedelta(days=365)).strftime("%Y-%m-%d")
    conn = get_conn()
    conn.execute(
        """INSERT INTO trn_certificates
           (cert_id, officer_id, course_id, issued_date, expiry_date, status, points_earned, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (cid, officer_id, course_id, today, expiry, "Active", points, now),
    )
    conn.commit()
    conn.close()
    return cid


def enroll_officer(officer_id: str, course_id: str) -> bool:
    """Create a progress stub to enroll an officer in a course. Returns False if already enrolled."""
    conn = get_conn()
    existing = conn.execute(
        "SELECT 1 FROM trn_progress WHERE officer_id = ? AND course_id = ? LIMIT 1",
        (officer_id, course_id),
    ).fetchone()
    if existing:
        conn.close()
        return False
    # Find first chapter to create a real progress record (not completed)
    first_ch = conn.execute(
        "SELECT chapter_id FROM trn_chapters WHERE course_id = ? ORDER BY sort_order LIMIT 1",
        (course_id,),
    ).fetchone()
    chapter_id = first_ch["chapter_id"] if first_ch else ""
    conn.execute(
        """INSERT OR IGNORE INTO trn_progress
           (officer_id, course_id, chapter_id, completed, completed_at)
           VALUES (?, ?, ?, 0, '')""",
        (officer_id, course_id, chapter_id),
    )
    conn.commit()
    conn.close()
    return True


# ══════════════════════════════════════════════════════════════════════
# Leaderboard
# ══════════════════════════════════════════════════════════════════════

def get_leaderboard(site_filter: str = "") -> list:
    """Return sorted list of officers with training points, courses completed, avg score."""
    conn = get_conn()

    query = """
        SELECT o.officer_id, o.name, o.site,
            COALESCE(SUM(c.points_earned), 0) as points,
            COUNT(DISTINCT c.course_id) as courses_completed,
            (SELECT COUNT(*) FROM trn_test_attempts ta
             WHERE ta.officer_id = o.officer_id AND ta.passed = 1) as tests_passed,
            (SELECT AVG(ta2.score) FROM trn_test_attempts ta2
             WHERE ta2.officer_id = o.officer_id) as avg_score
        FROM officers o
        LEFT JOIN trn_certificates c ON o.officer_id = c.officer_id
        WHERE o.status = 'Active'
    """
    params = []
    if site_filter == "__unassigned__":
        query += " AND (o.site IS NULL OR o.site = '')"
    elif site_filter:
        query += " AND o.site LIKE ?"
        params.append(f"%{site_filter}%")

    query += " GROUP BY o.officer_id, o.name, o.site ORDER BY points DESC, courses_completed DESC, tests_passed DESC, o.name ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        r = dict(r)
        r["site"] = r.get("site") or ""
        r["avg_score"] = round(r["avg_score"], 1) if r["avg_score"] is not None else 0.0
        result.append(r)

    return result


# ══════════════════════════════════════════════════════════════════════
# Dashboard Summary
# ══════════════════════════════════════════════════════════════════════

def get_dashboard_summary(officer_id: str) -> dict:
    """Return dashboard stats for a specific officer."""
    conn = get_conn()

    courses_available = conn.execute(
        "SELECT COUNT(*) as cnt FROM trn_courses WHERE status = 'Published'"
    ).fetchone()["cnt"]

    courses_completed = conn.execute(
        "SELECT COUNT(DISTINCT course_id) as cnt FROM trn_certificates WHERE officer_id = ?",
        (officer_id,),
    ).fetchone()["cnt"]

    certificates = conn.execute(
        "SELECT COUNT(*) as cnt FROM trn_certificates WHERE officer_id = ?",
        (officer_id,),
    ).fetchone()["cnt"]

    test_attempts = conn.execute(
        "SELECT COUNT(*) as cnt FROM trn_test_attempts WHERE officer_id = ?",
        (officer_id,),
    ).fetchone()["cnt"]

    conn.close()

    return {
        "courses_available": courses_available,
        "courses_completed": courses_completed,
        "certificates": certificates,
        "test_attempts": test_attempts,
    }


# ══════════════════════════════════════════════════════════════════════
# Reports helpers
# ══════════════════════════════════════════════════════════════════════

def get_completion_by_site() -> list:
    """Return training completion summary grouped by site."""
    conn = get_conn()

    total_courses = conn.execute(
        "SELECT COUNT(*) as cnt FROM trn_courses WHERE status = 'Published'"
    ).fetchone()["cnt"]

    if total_courses == 0:
        # No published courses -- return sites with 0% completion
        rows = conn.execute(
            """SELECT site, COUNT(DISTINCT officer_id) as officers
               FROM officers WHERE status = 'Active' AND site != ''
               GROUP BY site ORDER BY site"""
        ).fetchall()
        conn.close()
        return [{"site": r["site"], "officers": r["officers"], "avg_completion": 0.0} for r in rows]

    rows = conn.execute(
        """SELECT o.site,
                  COUNT(DISTINCT o.officer_id) as officers,
                  AVG(COALESCE(cert_counts.completed, 0) * 100.0 / ?) as avg_completion
           FROM officers o
           LEFT JOIN (
               SELECT officer_id, COUNT(DISTINCT course_id) as completed
               FROM trn_certificates GROUP BY officer_id
           ) cert_counts ON o.officer_id = cert_counts.officer_id
           WHERE o.status = 'Active' AND o.site != ''
           GROUP BY o.site
           ORDER BY avg_completion DESC""",
        (total_courses,),
    ).fetchall()
    conn.close()

    return [
        {
            "site": r["site"],
            "officers": r["officers"],
            "avg_completion": round(r["avg_completion"], 1) if r["avg_completion"] is not None else 0.0,
        }
        for r in rows
    ]


def get_completion_by_course() -> list:
    """Return completion rate for each published course: enrolled, completed, pct."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.course_id, c.title, c.category,
                  (SELECT COUNT(DISTINCT p.officer_id) FROM trn_progress p
                   WHERE p.course_id = c.course_id) as enrolled,
                  (SELECT COUNT(DISTINCT cert.officer_id) FROM trn_certificates cert
                   WHERE cert.course_id = c.course_id) as completed
           FROM trn_courses c
           WHERE c.status = 'Published'
           ORDER BY c.title"""
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        r = dict(r)
        enrolled = r["enrolled"]
        completed = r["completed"]
        pct = round((completed / enrolled) * 100, 1) if enrolled > 0 else 0.0
        result.append({
            "course_id": r["course_id"],
            "title": r["title"],
            "category": r.get("category", "General Training"),
            "enrolled": enrolled,
            "completed": completed,
            "completion_pct": pct,
            "avg_completion": pct,
        })
    return result


def get_top_performers(limit: int = 10) -> list:
    """Return officers with the most completed courses (certificates)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT o.officer_id, o.name,
                  COUNT(DISTINCT cert.course_id) as courses_completed,
                  COALESCE(SUM(cert.points_earned), 0) as total_points,
                  (SELECT AVG(ta.score) FROM trn_test_attempts ta
                   WHERE ta.officer_id = o.officer_id) as avg_score
           FROM officers o
           INNER JOIN trn_certificates cert ON o.officer_id = cert.officer_id
           WHERE o.status = 'Active'
           GROUP BY o.officer_id, o.name
           ORDER BY courses_completed DESC, total_points DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "officer_id": r["officer_id"],
            "name": r["name"],
            "courses_completed": r["courses_completed"],
            "total_points": r["total_points"],
            "avg_score": round(r["avg_score"], 1) if r["avg_score"] is not None else 0.0,
        }
        for r in rows
    ]


def get_expiring_certificates(days: int = 30) -> list:
    """Return certificates expiring within the given number of days."""
    conn = get_conn()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    future = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT cert.*, c.title as course_title, o.name as officer_name
           FROM trn_certificates cert
           LEFT JOIN trn_courses c ON cert.course_id = c.course_id
           LEFT JOIN officers o ON cert.officer_id = o.officer_id
           WHERE cert.expiry_date >= ? AND cert.expiry_date <= ?
           ORDER BY cert.expiry_date ASC""",
        (today, future),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════
# Settings (shared settings table)
# ══════════════════════════════════════════════════════════════════════

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
    now = _now()
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, now),
    )
    conn.commit()
    conn.close()


def get_course_categories() -> list:
    """Return list of course categories from settings, with defaults."""
    raw = get_setting("trn_course_categories")
    defaults = ["General Training", "Safety", "Compliance", "Leadership",
                "Technical", "Onboarding", "Site-Specific", "Professional Development"]
    if not raw:
        return defaults
    try:
        cats = json.loads(raw)
        return cats if isinstance(cats, list) and cats else defaults
    except (json.JSONDecodeError, TypeError):
        return defaults


def save_course_categories(categories: list) -> None:
    """Save course categories list to settings as JSON."""
    save_setting("trn_course_categories", json.dumps(categories))


def get_officer_progress_report() -> list:
    """Return per-officer progress for export."""
    conn = get_conn()

    rows = conn.execute(
        """SELECT o.officer_id, o.name, o.site,
                  c.course_id, c.title as course_title,
                  (SELECT COUNT(*) FROM trn_chapters ch
                   WHERE ch.course_id = c.course_id) as total_chapters,
                  (SELECT COUNT(*) FROM trn_progress p
                   WHERE p.officer_id = o.officer_id AND p.course_id = c.course_id
                         AND p.chapter_id != '' AND p.completed = 1) as completed_chapters,
                  CASE WHEN cert.cert_id IS NOT NULL THEN 1 ELSE 0 END as certified
           FROM officers o
           CROSS JOIN trn_courses c
           LEFT JOIN trn_certificates cert
               ON cert.officer_id = o.officer_id AND cert.course_id = c.course_id
           WHERE o.status = 'Active' AND c.status = 'Published'
           ORDER BY o.name, c.title"""
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        r = dict(r)
        total_ch = r["total_chapters"]
        done_ch = r["completed_chapters"]
        pct = round((done_ch / total_ch) * 100, 1) if total_ch > 0 else 0.0
        result.append({
            "officer_name": r["name"],
            "site": r.get("site") or "",
            "course": r["course_title"],
            "chapters_total": total_ch,
            "chapters_done": done_ch,
            "completion_pct": pct,
            "certified": "Yes" if r["certified"] else "No",
        })

    return result


# ═══════════════════════════════════════════════════════════════════════
#  SIMULATIONS
# ═══════════════════════════════════════════════════════════════════════

def _ensure_simulation_tables():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trn_simulations (
            sim_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'General',
            duration TEXT DEFAULT '',
            status TEXT DEFAULT 'Draft',
            scenarios TEXT DEFAULT '[]',
            created_by TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trn_sim_attempts (
            attempt_id TEXT PRIMARY KEY,
            officer_id TEXT,
            sim_id TEXT,
            score REAL DEFAULT 0,
            passed INTEGER DEFAULT 0,
            responses TEXT DEFAULT '[]',
            completed_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_all_simulations() -> list:
    _ensure_simulation_tables()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trn_simulations ORDER BY created_at DESC").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["scenarios"] = json.loads(d.get("scenarios", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["scenarios"] = []
        result.append(d)
    return result


def get_simulation(sim_id: str):
    _ensure_simulation_tables()
    conn = get_conn()
    row = conn.execute("SELECT * FROM trn_simulations WHERE sim_id = ?", (sim_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["scenarios"] = json.loads(d.get("scenarios", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["scenarios"] = []
    return d


def get_published_simulations() -> list:
    _ensure_simulation_tables()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trn_simulations WHERE status = 'Published' ORDER BY title"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["scenarios"] = json.loads(d.get("scenarios", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["scenarios"] = []
        result.append(d)
    return result


def create_simulation(fields: dict) -> str:
    _ensure_simulation_tables()
    sid = f"sim-{_gen_id()}"
    now = _now()
    scenarios = fields.get("scenarios", [])
    if isinstance(scenarios, list):
        scenarios = json.dumps(scenarios)
    conn = get_conn()
    conn.execute("""
        INSERT INTO trn_simulations (sim_id, title, description, category, duration,
            status, scenarios, created_by, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (sid, fields.get("title", ""), fields.get("description", ""),
          fields.get("category", "General"), fields.get("duration", ""),
          fields.get("status", "Draft"), scenarios,
          fields.get("created_by", ""), now, now))
    conn.commit()
    conn.close()
    return sid


def update_simulation(sim_id: str, fields: dict):
    _ensure_simulation_tables()
    conn = get_conn()
    updates, vals = [], []
    for k, v in fields.items():
        if k == "sim_id":
            continue
        if k == "scenarios" and isinstance(v, list):
            v = json.dumps(v)
        updates.append(f"{k} = ?")
        vals.append(v)
    updates.append("updated_at = ?")
    vals.append(_now())
    vals.append(sim_id)
    conn.execute(f"UPDATE trn_simulations SET {', '.join(updates)} WHERE sim_id = ?", vals)
    conn.commit()
    conn.close()


def delete_simulation(sim_id: str):
    _ensure_simulation_tables()
    conn = get_conn()
    conn.execute("DELETE FROM trn_simulations WHERE sim_id = ?", (sim_id,))
    conn.execute("DELETE FROM trn_sim_attempts WHERE sim_id = ?", (sim_id,))
    conn.commit()
    conn.close()


def create_sim_attempt(fields: dict) -> str:
    _ensure_simulation_tables()
    aid = f"sa-{_gen_id()}"
    responses = fields.get("responses", [])
    if isinstance(responses, list):
        responses = json.dumps(responses)
    conn = get_conn()
    conn.execute("""
        INSERT INTO trn_sim_attempts (attempt_id, officer_id, sim_id, score, passed, responses, completed_at)
        VALUES (?,?,?,?,?,?,?)
    """, (aid, fields.get("officer_id", ""), fields.get("sim_id", ""),
          fields.get("score", 0), fields.get("passed", 0), responses, _now()))
    conn.commit()
    conn.close()
    return aid


def get_sim_attempts(officer_id: str, sim_id: str) -> list:
    _ensure_simulation_tables()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trn_sim_attempts WHERE officer_id = ? AND sim_id = ? ORDER BY completed_at DESC",
        (officer_id, sim_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
