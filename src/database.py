"""
Cerasus Hub — Database Layer
SQLite connection manager (WAL mode) and schema migration runner.
"""

import sqlite3
import os
import shutil
import glob
from datetime import datetime, timezone

from src.config import DB_FILE, ensure_directories


def get_conn() -> sqlite3.Connection:
    """Get a connection to the hub database with standard settings."""
    ensure_directories()
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        # WAL may fail on some network drives; fall back to DELETE mode
        conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def backup_database():
    """Create a timestamped backup of the database on launch. Keep last 5 backups."""
    if not os.path.exists(DB_FILE):
        return
    backup_dir = os.path.join(os.path.dirname(DB_FILE), "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"cerasus_hub_{timestamp}.db")

    try:
        shutil.copy2(DB_FILE, backup_path)
    except Exception:
        pass  # Don't block startup on backup failure

    # Keep only last 5 backups
    backups = sorted(glob.glob(os.path.join(backup_dir, "cerasus_hub_*.db")))
    while len(backups) > 5:
        try:
            os.remove(backups.pop(0))
        except Exception:
            pass


# ── Core Schema Migrations ─────────────────────────────────────────────

def _core_migration_001(conn):
    """Create all shared core tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now')),
            description TEXT DEFAULT ''
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_schema_mod_ver
            ON schema_versions(module_name, version);

        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'standard',
            display_name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS officers (
            officer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            employee_id TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            job_title TEXT DEFAULT 'Security Officer',
            role TEXT DEFAULT '',
            site TEXT DEFAULT '',
            supervisor_id TEXT DEFAULT '',
            hire_date TEXT DEFAULT '',
            status TEXT DEFAULT 'Active',
            weekly_hours TEXT DEFAULT '40',
            trained_sites TEXT DEFAULT '[]',
            approved_sites TEXT DEFAULT '[]',
            anchor_sites TEXT DEFAULT '[]',
            uniform_sizes TEXT DEFAULT '{}',
            role_title TEXT DEFAULT '',
            active_points REAL DEFAULT 0,
            discipline_level TEXT DEFAULT 'None',
            last_infraction_date TEXT DEFAULT '',
            emergency_exemptions_used INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sites (
            site_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            address TEXT DEFAULT '',
            city TEXT DEFAULT '',
            state TEXT DEFAULT '',
            style TEXT DEFAULT 'Soft Look',
            billing_code TEXT DEFAULT '',
            market TEXT DEFAULT '',
            overtime_sensitivity TEXT DEFAULT 'Normal',
            status TEXT DEFAULT 'Active',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_name TEXT DEFAULT '',
            event_type TEXT NOT NULL,
            username TEXT DEFAULT '',
            computer TEXT DEFAULT '',
            os_user TEXT DEFAULT '',
            table_name TEXT DEFAULT '',
            record_id TEXT DEFAULT '',
            action TEXT DEFAULT '',
            before_value TEXT DEFAULT '',
            after_value TEXT DEFAULT '',
            justification TEXT DEFAULT '',
            details TEXT DEFAULT '',
            employee_id TEXT DEFAULT '',
            timestamp TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_audit_module ON audit_log(module_name);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            username TEXT DEFAULT '',
            role TEXT DEFAULT '',
            machine_name TEXT DEFAULT '',
            active_module TEXT DEFAULT '',
            started_at TEXT DEFAULT '',
            last_heartbeat TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
    """)


CORE_MIGRATIONS = {1: _core_migration_001}


# ── Migration Runner ───────────────────────────────────────────────────

def _get_current_version(conn, module_name: str) -> int:
    """Get the current schema version for a module (0 if no migrations run)."""
    try:
        row = conn.execute(
            "SELECT MAX(version) as v FROM schema_versions WHERE module_name = ?",
            (module_name,)
        ).fetchone()
        return row["v"] if row and row["v"] is not None else 0
    except sqlite3.OperationalError:
        return 0


def run_migrations(conn, module_name: str, migrations: dict):
    """Run pending migrations for a module."""
    if not migrations:
        return

    current = _get_current_version(conn, module_name)
    latest = max(migrations.keys())

    for ver in range(current + 1, latest + 1):
        if ver not in migrations:
            continue
        fn = migrations[ver]
        fn(conn)
        conn.execute(
            "INSERT INTO schema_versions (module_name, version, description) VALUES (?, ?, ?)",
            (module_name, ver, fn.__doc__ or "")
        )
    conn.commit()


def initialize_database():
    """Create/open the database and run all core migrations."""
    conn = get_conn()
    # Ensure schema_versions exists first (bootstrap)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now')),
            description TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_schema_mod_ver
            ON schema_versions(module_name, version)
    """)
    conn.commit()
    # Run core migrations
    run_migrations(conn, "core", CORE_MIGRATIONS)
    conn.close()

    # Ensure custom fields tables exist
    try:
        from src.custom_fields import ensure_custom_fields_tables
        ensure_custom_fields_tables()
    except Exception:
        pass  # Custom fields module may not be loaded yet


def ensure_module_permissions_column():
    """Add module_permissions column to users table if it doesn't exist."""
    conn = get_conn()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN module_permissions TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass  # Column already exists
    conn.close()


def ensure_assigned_sites_column():
    """Add assigned_sites column to users table if it doesn't exist."""
    conn = get_conn()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN assigned_sites TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass  # Column already exists
    conn.close()


def ensure_default_flex_officers():
    """Seed the default flex officers into ops_flex_team (NOT the shared officers table)."""
    conn = get_conn()
    # Ensure ops_flex_team table exists
    try:
        conn.execute("SELECT 1 FROM ops_flex_team LIMIT 1")
    except Exception:
        return  # Table not yet created by migration; will seed next launch

    existing = conn.execute("SELECT name FROM ops_flex_team").fetchall()
    existing_names = {r["name"].lower() for r in existing}

    default_flex = [
        {"name": "Luis Gonzalez", "first_name": "Luis", "last_name": "Gonzalez",
         "job_title": "Flex Security Officer", "role": "Flex Officer", "status": "Active"},
        {"name": "Jeremiah Gonzalez", "first_name": "Jeremiah", "last_name": "Gonzalez",
         "job_title": "Field Service Supervisor", "role": "Flex Officer", "status": "Active"},
        {"name": "Jarrod Allen", "first_name": "Jarrod", "last_name": "Allen",
         "job_title": "Flex Security Officer", "role": "Flex Officer", "status": "Active"},
    ]

    import secrets
    now = datetime.now(timezone.utc).isoformat()
    for officer in default_flex:
        if officer["name"].lower() not in existing_names:
            mid = secrets.token_hex(12)
            conn.execute(
                """INSERT INTO ops_flex_team
                   (member_id, name, first_name, last_name, employee_id,
                    email, phone, job_title, role, site,
                    weekly_hours, trained_sites, approved_sites, anchor_sites,
                    hire_date, status, notes,
                    created_by, updated_by, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (mid, officer["name"], officer.get("first_name", ""),
                 officer.get("last_name", ""), "",
                 "", "", officer.get("job_title", "Flex Officer"),
                 officer.get("role", "Flex Officer"), "",
                 "40", "[]", "[]", "[]",
                 "", officer.get("status", "Active"), "",
                 "system", "system", now, now),
            )
    conn.commit()
    conn.close()
    # Clean up any flex officers that were previously seeded into the shared officers table
    conn2 = get_conn()
    try:
        flex_names = ["luis gonzalez", "jeremiah gonzalez", "jarrod allen"]
        for fn in flex_names:
            conn2.execute(
                "DELETE FROM officers WHERE LOWER(name) = ? AND (role = 'Flex Officer' OR job_title LIKE '%Flex%')",
                (fn,),
            )
        conn2.commit()
    except Exception:
        pass
    conn2.close()


def run_module_migrations(modules: list):
    """Run migrations for all registered modules."""
    conn = get_conn()
    for mod in modules:
        migrations = mod.get_migrations()
        if migrations:
            run_migrations(conn, mod.module_id, migrations)
    conn.close()
