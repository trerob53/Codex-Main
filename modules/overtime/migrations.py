"""
Cerasus Hub -- DLS & Overtime Module: SQLite Schema Migrations
"""


def _migration_001(conn):
    """Create DLS/Overtime module tables: dls_labor_entries, dls_site_budgets."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS dls_labor_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            officer_id TEXT DEFAULT '',
            officer_name TEXT DEFAULT '',
            site TEXT DEFAULT '',
            week_ending TEXT DEFAULT '',
            regular_hours REAL DEFAULT 0,
            overtime_hours REAL DEFAULT 0,
            double_time_hours REAL DEFAULT 0,
            total_hours REAL DEFAULT 0,
            regular_rate REAL DEFAULT 0,
            overtime_rate REAL DEFAULT 0,
            regular_pay REAL DEFAULT 0,
            overtime_pay REAL DEFAULT 0,
            total_pay REAL DEFAULT 0,
            billable_hours REAL DEFAULT 0,
            non_billable_hours REAL DEFAULT 0,
            dls_percentage REAL DEFAULT 0,
            source TEXT DEFAULT 'manual',
            imported_at TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_dls_officer ON dls_labor_entries(officer_id);
        CREATE INDEX IF NOT EXISTS idx_dls_site ON dls_labor_entries(site);
        CREATE INDEX IF NOT EXISTS idx_dls_week ON dls_labor_entries(week_ending);

        CREATE TABLE IF NOT EXISTS dls_site_budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT DEFAULT '',
            weekly_budget_hours REAL DEFAULT 0,
            weekly_budget_dollars REAL DEFAULT 0,
            ot_threshold_hours REAL DEFAULT 40,
            ot_alert_percentage REAL DEFAULT 80,
            effective_date TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        );
    """)


MIGRATIONS = {1: _migration_001}
