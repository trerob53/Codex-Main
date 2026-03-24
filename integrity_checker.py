"""
Cerasus Hub -- Data Integrity Checker

Diagnostic tool that scans the database for orphaned records,
duplicate entries, invalid foreign keys, and suspicious dates.

Usage:
    from src.integrity_checker import run_integrity_checks
    issues = run_integrity_checks(conn)
"""

from datetime import datetime


def _table_exists(conn, table_name: str) -> bool:
    """Return True if the table exists in the database."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def run_integrity_checks(conn) -> list[dict]:
    """
    Run all integrity checks against the database and return a list of issues.

    Each issue is a dict with keys:
        severity  - "warning" or "error"
        table     - the table name involved
        description - human-readable explanation
        count     - number of affected rows
    """
    issues: list[dict] = []

    # ------------------------------------------------------------------
    # 1. Orphaned infractions — employee_id not in officers table
    # ------------------------------------------------------------------
    if _table_exists(conn, "ats_infractions") and _table_exists(conn, "officers"):
        row = conn.execute("""
            SELECT COUNT(*) FROM ats_infractions
            WHERE employee_id != ''
              AND employee_id NOT IN (SELECT officer_id FROM officers)
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "error",
                "table": "ats_infractions",
                "description": "Infractions referencing non-existent officer (employee_id not in officers)",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 2. Orphaned employment reviews — employee_id not in officers
    # ------------------------------------------------------------------
    if _table_exists(conn, "ats_employment_reviews") and _table_exists(conn, "officers"):
        row = conn.execute("""
            SELECT COUNT(*) FROM ats_employment_reviews
            WHERE employee_id != ''
              AND employee_id NOT IN (SELECT officer_id FROM officers)
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "error",
                "table": "ats_employment_reviews",
                "description": "Employment reviews referencing non-existent officer",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 3. Orphaned incident reports — officer_id not in officers
    # ------------------------------------------------------------------
    if _table_exists(conn, "inc_incidents") and _table_exists(conn, "officers"):
        row = conn.execute("""
            SELECT COUNT(*) FROM inc_incidents
            WHERE officer_id != ''
              AND officer_id NOT IN (SELECT officer_id FROM officers)
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "error",
                "table": "inc_incidents",
                "description": "Incidents referencing non-existent officer_id",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 4. Orphaned DA records — employee_officer_id not in officers
    # ------------------------------------------------------------------
    if _table_exists(conn, "da_records") and _table_exists(conn, "officers"):
        row = conn.execute("""
            SELECT COUNT(*) FROM da_records
            WHERE employee_officer_id != ''
              AND employee_officer_id NOT IN (SELECT officer_id FROM officers)
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "error",
                "table": "da_records",
                "description": "DA records referencing non-existent officer",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 5. Orphaned labor entries — officer_id not in officers
    # ------------------------------------------------------------------
    if _table_exists(conn, "dls_labor_entries") and _table_exists(conn, "officers"):
        row = conn.execute("""
            SELECT COUNT(*) FROM dls_labor_entries
            WHERE officer_id != ''
              AND officer_id NOT IN (SELECT officer_id FROM officers)
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "error",
                "table": "dls_labor_entries",
                "description": "Labor entries referencing non-existent officer_id",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 6. Officers with no site assigned
    # ------------------------------------------------------------------
    if _table_exists(conn, "officers"):
        row = conn.execute("""
            SELECT COUNT(*) FROM officers
            WHERE status = 'Active'
              AND (site IS NULL OR site = '')
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "warning",
                "table": "officers",
                "description": "Active officers with no site assigned",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 7. Duplicate officer names
    # ------------------------------------------------------------------
    if _table_exists(conn, "officers"):
        row = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT name FROM officers
                WHERE name != '' AND status = 'Active'
                GROUP BY LOWER(TRIM(name))
                HAVING COUNT(*) > 1
            )
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "warning",
                "table": "officers",
                "description": "Duplicate officer names found (case-insensitive)",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 8. Future dates in infraction records
    # ------------------------------------------------------------------
    if _table_exists(conn, "ats_infractions"):
        today = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute("""
            SELECT COUNT(*) FROM ats_infractions
            WHERE infraction_date > ? AND infraction_date != ''
        """, (today,)).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "warning",
                "table": "ats_infractions",
                "description": "Infractions with future dates",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 9. Future dates in incident records
    # ------------------------------------------------------------------
    if _table_exists(conn, "inc_incidents"):
        today = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute("""
            SELECT COUNT(*) FROM inc_incidents
            WHERE incident_date > ? AND incident_date != ''
        """, (today,)).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "warning",
                "table": "inc_incidents",
                "description": "Incidents with future dates",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 10. Officers referencing non-existent sites
    # ------------------------------------------------------------------
    if _table_exists(conn, "officers") and _table_exists(conn, "sites"):
        row = conn.execute("""
            SELECT COUNT(*) FROM officers
            WHERE site != ''
              AND site NOT IN (SELECT name FROM sites)
              AND site NOT IN (SELECT site_id FROM sites)
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "error",
                "table": "officers",
                "description": "Officers assigned to non-existent sites",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 11. Assignments referencing unknown site names
    # ------------------------------------------------------------------
    if _table_exists(conn, "ops_assignments") and _table_exists(conn, "sites"):
        row = conn.execute("""
            SELECT COUNT(*) FROM ops_assignments
            WHERE site_name != ''
              AND site_name NOT IN (SELECT name FROM sites)
              AND site_name NOT IN (SELECT site_id FROM sites)
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "warning",
                "table": "ops_assignments",
                "description": "Assignments referencing unknown site names",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 12. Assignments referencing unknown officer names
    # ------------------------------------------------------------------
    if _table_exists(conn, "ops_assignments") and _table_exists(conn, "officers"):
        row = conn.execute("""
            SELECT COUNT(*) FROM ops_assignments
            WHERE officer_name != ''
              AND officer_name NOT IN (SELECT name FROM officers)
        """).fetchone()
        if row and row[0] > 0:
            issues.append({
                "severity": "warning",
                "table": "ops_assignments",
                "description": "Assignments referencing unknown officer names",
                "count": row[0],
            })

    # ------------------------------------------------------------------
    # 13. Uniform issuances referencing non-existent officers
    # ------------------------------------------------------------------
    if _table_exists(conn, "uni_issuances") and _table_exists(conn, "officers"):
        # Check if officer_id column exists in uni_issuances
        cols = [r[1] for r in conn.execute("PRAGMA table_info(uni_issuances)").fetchall()]
        if "officer_id" in cols:
            row = conn.execute("""
                SELECT COUNT(*) FROM uni_issuances
                WHERE officer_id != ''
                  AND officer_id NOT IN (SELECT officer_id FROM officers)
            """).fetchone()
            if row and row[0] > 0:
                issues.append({
                    "severity": "error",
                    "table": "uni_issuances",
                    "description": "Uniform issuances referencing non-existent officer",
                    "count": row[0],
                })

    return issues
