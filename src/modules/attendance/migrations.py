"""
Cerasus Hub -- Attendance Module: SQLite Schema Migrations
"""


def _migration_001(conn):
    """Create attendance module tables: ats_infractions, ats_employment_reviews."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ats_infractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            infraction_type TEXT NOT NULL,
            infraction_date TEXT DEFAULT '',
            points_assigned REAL DEFAULT 0,
            description TEXT DEFAULT '',
            site TEXT DEFAULT '',
            entered_by TEXT DEFAULT '',
            discipline_triggered TEXT DEFAULT '',
            is_emergency_exemption INTEGER DEFAULT 0,
            exemption_approved INTEGER DEFAULT 0,
            documentation_provided INTEGER DEFAULT 0,
            point_expiry_date TEXT DEFAULT '',
            points_active INTEGER DEFAULT 1,
            edited INTEGER DEFAULT 0,
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_ats_inf_emp ON ats_infractions(employee_id);
        CREATE INDEX IF NOT EXISTS idx_ats_inf_date ON ats_infractions(infraction_date);

        CREATE TABLE IF NOT EXISTS ats_employment_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            triggered_date TEXT DEFAULT '',
            points_at_trigger REAL DEFAULT 0,
            review_status TEXT DEFAULT 'Pending',
            reviewed_by TEXT DEFAULT '',
            review_date TEXT DEFAULT '',
            outcome TEXT DEFAULT '',
            reviewer_notes TEXT DEFAULT '',
            supervisor_comments TEXT DEFAULT '',
            points_after_outcome REAL DEFAULT 0,
            locked INTEGER DEFAULT 0,
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_ats_rev_emp ON ats_employment_reviews(employee_id);
    """)


def _migration_002(conn):
    """Create ATS ID mapping table for resolving Genspark-imported officer IDs to names."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ats_id_mapping (
            ats_id TEXT PRIMARY KEY,
            officer_id TEXT DEFAULT '',
            officer_name TEXT DEFAULT '',
            employee_number TEXT DEFAULT ''
        );
    """)


MIGRATIONS = {1: _migration_001, 2: _migration_002}
