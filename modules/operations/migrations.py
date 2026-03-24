"""
Cerasus Hub -- Operations Module: SQLite Schema Migrations
"""


def _migration_001(conn):
    """Create operations module tables: ops_records, ops_assignments, ops_pto_entries."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ops_records (
            record_id TEXT PRIMARY KEY,
            employee_name TEXT DEFAULT '',
            site_name TEXT DEFAULT '',
            date TEXT DEFAULT '',
            status TEXT DEFAULT 'Open',
            priority TEXT DEFAULT 'Normal',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ops_assignments (
            assignment_id TEXT PRIMARY KEY,
            officer_name TEXT DEFAULT '',
            site_name TEXT DEFAULT '',
            date TEXT DEFAULT '',
            start_time TEXT DEFAULT '',
            end_time TEXT DEFAULT '',
            hours TEXT DEFAULT '0',
            assignment_type TEXT DEFAULT 'Billable',
            status TEXT DEFAULT 'Scheduled',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ops_pto_entries (
            pto_id TEXT PRIMARY KEY,
            officer_name TEXT DEFAULT '',
            start_date TEXT DEFAULT '',
            end_date TEXT DEFAULT '',
            pto_type TEXT DEFAULT 'Unavailable',
            status TEXT DEFAULT 'Approved',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
    """)


def _migration_002(conn):
    """Create ops_incidents table for Incident Report system."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ops_incidents (
            incident_id TEXT PRIMARY KEY,
            site TEXT NOT NULL,
            incident_date TEXT NOT NULL,
            incident_time TEXT DEFAULT '',
            incident_type TEXT NOT NULL,
            severity TEXT DEFAULT 'low',
            reporting_officer TEXT DEFAULT '',
            reporting_officer_id TEXT DEFAULT '',
            description TEXT NOT NULL,
            persons_involved TEXT DEFAULT '',
            actions_taken TEXT DEFAULT '',
            police_called INTEGER DEFAULT 0,
            police_report_number TEXT DEFAULT '',
            medical_required INTEGER DEFAULT 0,
            property_damage INTEGER DEFAULT 0,
            witness_names TEXT DEFAULT '',
            supervisor_notified INTEGER DEFAULT 0,
            supervisor_name TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            resolution TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)


def _migration_003(conn):
    """Create ops_handoff_notes table for shift handoff notes."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ops_handoff_notes (
            note_id TEXT PRIMARY KEY,
            site TEXT NOT NULL,
            shift_date TEXT NOT NULL,
            shift_type TEXT DEFAULT '',
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            priority TEXT DEFAULT 'normal',
            acknowledged_by TEXT DEFAULT '',
            acknowledged_at TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)


def _migration_004(conn):
    """Create ops_flex_team table — Operations-only officer roster, separate from shared officers."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ops_flex_team (
            member_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            employee_id TEXT DEFAULT '',
            email TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            job_title TEXT DEFAULT 'Flex Officer',
            role TEXT DEFAULT 'Flex Officer',
            site TEXT DEFAULT '',
            weekly_hours TEXT DEFAULT '40',
            trained_sites TEXT DEFAULT '[]',
            approved_sites TEXT DEFAULT '[]',
            anchor_sites TEXT DEFAULT '[]',
            hire_date TEXT DEFAULT '',
            status TEXT DEFAULT 'Active',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
    """)


def _migration_005(conn):
    """Create ops_open_requests table for coverage requests dispatch system."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ops_open_requests (
            request_id TEXT PRIMARY KEY,
            site_name TEXT NOT NULL DEFAULT '',
            date TEXT NOT NULL DEFAULT '',
            start_time TEXT DEFAULT '',
            end_time TEXT DEFAULT '',
            hours TEXT DEFAULT '0',
            reason TEXT DEFAULT 'Coverage',
            priority TEXT DEFAULT 'Normal',
            status TEXT DEFAULT 'Open',
            requested_by TEXT DEFAULT '',
            assigned_officer TEXT DEFAULT '',
            linked_assignment_id TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_ops_req_status ON ops_open_requests(status);
        CREATE INDEX IF NOT EXISTS idx_ops_req_date ON ops_open_requests(date);
        CREATE INDEX IF NOT EXISTS idx_ops_req_site ON ops_open_requests(site_name);
    """)


def _migration_006(conn):
    """Create ops_anchor_schedules table for officer baseline weekly patterns."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ops_anchor_schedules (
            schedule_id TEXT PRIMARY KEY,
            officer_name TEXT NOT NULL DEFAULT '',
            position_title TEXT DEFAULT '',
            anchor_site TEXT DEFAULT '',
            pay_rate TEXT DEFAULT '0.00',
            sunday TEXT DEFAULT 'OFF',
            monday TEXT DEFAULT 'OFF',
            tuesday TEXT DEFAULT 'OFF',
            wednesday TEXT DEFAULT 'OFF',
            thursday TEXT DEFAULT 'OFF',
            friday TEXT DEFAULT 'OFF',
            saturday TEXT DEFAULT 'OFF',
            total_hours TEXT DEFAULT '0',
            active INTEGER DEFAULT 1,
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_ops_anchor_officer ON ops_anchor_schedules(officer_name);
    """)


def _migration_007(conn):
    """Create ops_certifications table for officer skills/certifications tracking."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ops_certifications (
            cert_id TEXT PRIMARY KEY,
            officer_name TEXT NOT NULL DEFAULT '',
            cert_name TEXT NOT NULL DEFAULT '',
            issued_date TEXT DEFAULT '',
            expiry_date TEXT DEFAULT '',
            status TEXT DEFAULT 'Active',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_ops_cert_officer ON ops_certifications(officer_name);
        CREATE INDEX IF NOT EXISTS idx_ops_cert_expiry ON ops_certifications(expiry_date);
    """)


def _migration_008(conn):
    """Create ops_positions and ops_candidates tables for Open Positions Tracker."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ops_positions (
            position_id TEXT PRIMARY KEY,
            site_name TEXT NOT NULL DEFAULT '',
            position_title TEXT NOT NULL DEFAULT '',
            shift TEXT DEFAULT '',
            pay_rate TEXT DEFAULT '0.00',
            sunday TEXT DEFAULT 'OFF',
            monday TEXT DEFAULT 'OFF',
            tuesday TEXT DEFAULT 'OFF',
            wednesday TEXT DEFAULT 'OFF',
            thursday TEXT DEFAULT 'OFF',
            friday TEXT DEFAULT 'OFF',
            saturday TEXT DEFAULT 'OFF',
            total_hours TEXT DEFAULT '0',
            status TEXT DEFAULT 'Open',
            pipeline_stage TEXT DEFAULT 'Open',
            notes TEXT DEFAULT '',
            date_opened TEXT DEFAULT '',
            date_filled TEXT DEFAULT '',
            date_job_offer TEXT DEFAULT '',
            date_background_check TEXT DEFAULT '',
            date_orientation TEXT DEFAULT '',
            date_training_ojt TEXT DEFAULT '',
            expected_orientation_end TEXT DEFAULT '',
            expected_training_end TEXT DEFAULT '',
            filled_by TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_ops_pos_site ON ops_positions(site_name);
        CREATE INDEX IF NOT EXISTS idx_ops_pos_status ON ops_positions(status);

        CREATE TABLE IF NOT EXISTS ops_candidates (
            candidate_id TEXT PRIMARY KEY,
            position_id TEXT NOT NULL DEFAULT '',
            candidate_name TEXT NOT NULL DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            source TEXT DEFAULT '',
            stage TEXT DEFAULT 'Applied',
            interview_date TEXT DEFAULT '',
            offer_date TEXT DEFAULT '',
            start_date TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_ops_cand_pos ON ops_candidates(position_id);
    """)


def _migration_009(conn):
    """Add date tracking columns to ops_positions for pipeline stage dates."""
    new_cols = [
        ("date_job_offer", "TEXT DEFAULT ''"),
        ("date_background_check", "TEXT DEFAULT ''"),
        ("date_orientation", "TEXT DEFAULT ''"),
        ("date_training_ojt", "TEXT DEFAULT ''"),
        ("expected_orientation_end", "TEXT DEFAULT ''"),
        ("expected_training_end", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE ops_positions ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass  # Column already exists
    conn.commit()


MIGRATIONS = {
    1: _migration_001, 2: _migration_002, 3: _migration_003,
    4: _migration_004, 5: _migration_005, 6: _migration_006,
    7: _migration_007, 8: _migration_008, 9: _migration_009,
}
