"""
Cerasus Hub -- Incidents Module: SQLite Schema Migrations
"""


def _migration_001(conn):
    """Create incidents module table: inc_incidents."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS inc_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT UNIQUE,
            officer_id TEXT DEFAULT '',
            officer_name TEXT DEFAULT '',
            site TEXT DEFAULT '',
            incident_date TEXT DEFAULT '',
            incident_time TEXT DEFAULT '',
            incident_type TEXT DEFAULT '',
            severity TEXT DEFAULT 'Low',
            status TEXT DEFAULT 'Open',
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            location_detail TEXT DEFAULT '',
            persons_involved TEXT DEFAULT '[]',
            witnesses TEXT DEFAULT '',
            police_called INTEGER DEFAULT 0,
            police_report_number TEXT DEFAULT '',
            injuries_reported INTEGER DEFAULT 0,
            injury_details TEXT DEFAULT '',
            property_damage INTEGER DEFAULT 0,
            damage_description TEXT DEFAULT '',
            immediate_action TEXT DEFAULT '',
            resolution TEXT DEFAULT '',
            resolved_by TEXT DEFAULT '',
            resolved_date TEXT DEFAULT '',
            assigned_to TEXT DEFAULT '',
            follow_up_required INTEGER DEFAULT 0,
            follow_up_notes TEXT DEFAULT '',
            attachments TEXT DEFAULT '[]',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_inc_site ON inc_incidents(site);
        CREATE INDEX IF NOT EXISTS idx_inc_date ON inc_incidents(incident_date);
        CREATE INDEX IF NOT EXISTS idx_inc_status ON inc_incidents(status);
        CREATE INDEX IF NOT EXISTS idx_inc_severity ON inc_incidents(severity);
        CREATE INDEX IF NOT EXISTS idx_inc_officer ON inc_incidents(officer_id);
    """)


MIGRATIONS = {1: _migration_001}
