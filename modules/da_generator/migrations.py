"""
Cerasus Hub -- DA Generator Module: Schema Migrations
"""


def _migration_001(conn):
    """Create DA Generator tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS da_records (
            da_id TEXT PRIMARY KEY,
            employee_name TEXT NOT NULL DEFAULT '',
            employee_position TEXT DEFAULT '',
            employee_officer_id TEXT DEFAULT '',
            site TEXT DEFAULT '',
            security_director TEXT DEFAULT '',
            incident_dates TEXT DEFAULT '',
            incident_narrative TEXT DEFAULT '',
            violation_type TEXT DEFAULT '',
            prior_verbal_same INTEGER DEFAULT 0,
            prior_written_same INTEGER DEFAULT 0,
            prior_final_same INTEGER DEFAULT 0,
            prior_verbal_other INTEGER DEFAULT 0,
            prior_written_other INTEGER DEFAULT 0,
            prior_final_other INTEGER DEFAULT 0,
            coaching_occurred INTEGER DEFAULT 0,
            coaching_date TEXT DEFAULT '',
            coaching_content TEXT DEFAULT '',
            coaching_outcome TEXT DEFAULT '',
            has_victim_statement INTEGER DEFAULT 0,
            has_subject_statement INTEGER DEFAULT 0,
            has_witness_statements INTEGER DEFAULT 0,
            clarifying_qa TEXT DEFAULT '[]',
            ceis_narrative TEXT DEFAULT '',
            ceis_citations TEXT DEFAULT '',
            ceis_violation_analysis TEXT DEFAULT '',
            ceis_discipline_determination TEXT DEFAULT '',
            ceis_risk_assessment TEXT DEFAULT '',
            ceis_recommendation TEXT DEFAULT '',
            use_of_force_applies INTEGER DEFAULT 0,
            post_orders_apply INTEGER DEFAULT 0,
            post_order_details TEXT DEFAULT '',
            additional_violations TEXT DEFAULT '',
            discipline_level TEXT DEFAULT '',
            final_narrative TEXT DEFAULT '',
            final_citations TEXT DEFAULT '',
            final_prior_discipline TEXT DEFAULT '',
            final_coaching TEXT DEFAULT '',
            required_improvements TEXT DEFAULT '',
            additional_comments TEXT DEFAULT '',
            da_payload TEXT DEFAULT '',
            status TEXT DEFAULT 'draft',
            current_step INTEGER DEFAULT 1,
            attendance_points_at_da REAL DEFAULT 0,
            attendance_record_json TEXT DEFAULT '',
            pdf_filename TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
    """)


def _migration_002(conn):
    """Add delivered_at and signed_at columns to da_records."""
    conn.executescript("""
        ALTER TABLE da_records ADD COLUMN delivered_at TEXT DEFAULT '';
        ALTER TABLE da_records ADD COLUMN signed_at TEXT DEFAULT '';
    """)


def _migration_003(conn):
    """Add acknowledgment tracking columns to da_records."""
    conn.executescript("""
        ALTER TABLE da_records ADD COLUMN acknowledged INTEGER DEFAULT 0;
        ALTER TABLE da_records ADD COLUMN acknowledged_by TEXT DEFAULT '';
        ALTER TABLE da_records ADD COLUMN acknowledged_at TEXT DEFAULT '';
        ALTER TABLE da_records ADD COLUMN employee_response TEXT DEFAULT '';
        ALTER TABLE da_records ADD COLUMN witness_name TEXT DEFAULT '';
        ALTER TABLE da_records ADD COLUMN witness_signed INTEGER DEFAULT 0;
        ALTER TABLE da_records ADD COLUMN witness_signed_at TEXT DEFAULT '';
    """)


MIGRATIONS = {1: _migration_001, 2: _migration_002, 3: _migration_003}
