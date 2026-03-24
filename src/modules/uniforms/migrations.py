"""
Cerasus Hub -- Uniforms Module: SQLite Schema Migrations
"""


def _migration_001(conn):
    """Create uniforms module tables: catalog, item_sizes, issuances, pending_orders, kits, requirements."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS uni_catalog (
            item_id TEXT PRIMARY KEY,
            item_name TEXT NOT NULL DEFAULT '',
            category TEXT DEFAULT '',
            description TEXT DEFAULT '',
            unit_cost TEXT DEFAULT '0',
            reorder_point TEXT DEFAULT '5',
            status TEXT DEFAULT 'Active',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS uni_item_sizes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            size TEXT DEFAULT '',
            stock_qty INTEGER DEFAULT 0,
            location TEXT DEFAULT 'Main Office',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_uni_sizes_item ON uni_item_sizes(item_id);
        CREATE INDEX IF NOT EXISTS idx_uni_sizes_loc ON uni_item_sizes(location);

        CREATE TABLE IF NOT EXISTS uni_issuances (
            issuance_id TEXT PRIMARY KEY,
            officer_id TEXT DEFAULT '',
            officer_name TEXT DEFAULT '',
            item_id TEXT DEFAULT '',
            item_name TEXT DEFAULT '',
            size TEXT DEFAULT '',
            quantity TEXT DEFAULT '1',
            condition_issued TEXT DEFAULT 'New',
            date_issued TEXT DEFAULT '',
            issued_by TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            location TEXT DEFAULT '',
            status TEXT DEFAULT 'Issued',
            return_condition TEXT DEFAULT '',
            return_notes TEXT DEFAULT '',
            return_date TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_uni_iss_officer ON uni_issuances(officer_id);
        CREATE INDEX IF NOT EXISTS idx_uni_iss_item ON uni_issuances(item_id);
        CREATE INDEX IF NOT EXISTS idx_uni_iss_status ON uni_issuances(status);

        CREATE TABLE IF NOT EXISTS uni_pending_orders (
            order_id TEXT PRIMARY KEY,
            officer_id TEXT DEFAULT '',
            officer_name TEXT DEFAULT '',
            item_id TEXT DEFAULT '',
            item_name TEXT DEFAULT '',
            size TEXT DEFAULT '',
            quantity TEXT DEFAULT '1',
            reason TEXT DEFAULT '',
            status TEXT DEFAULT 'Pending',
            fulfilled_by TEXT DEFAULT '',
            fulfilled_at TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS uni_kits (
            kit_id TEXT PRIMARY KEY,
            kit_name TEXT NOT NULL DEFAULT '',
            job_title TEXT DEFAULT '',
            items TEXT DEFAULT '[]',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS uni_requirements (
            req_id TEXT PRIMARY KEY,
            job_title TEXT DEFAULT '',
            item_id TEXT DEFAULT '',
            item_name TEXT DEFAULT '',
            qty_required TEXT DEFAULT '1',
            created_at TEXT DEFAULT ''
        );
    """)


MIGRATIONS = {1: _migration_001}
