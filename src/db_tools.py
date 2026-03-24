"""Database backup, export, and import tools."""

import json
import os
import shutil
from datetime import datetime
from src.config import DATA_DIR, REPORTS_DIR, DB_FILE, ensure_directories
from src.database import get_conn


def export_full_database(output_path: str = "") -> str:
    """Export the entire database to a JSON file."""
    ensure_directories()
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(REPORTS_DIR, f"cerasus_hub_export_{timestamp}.json")

    conn = get_conn()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]

    data = {"exported_at": datetime.now().isoformat(), "tables": {}}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM [{table}]").fetchall()
        data["tables"][table] = [dict(r) for r in rows]

    conn.close()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    return output_path


def import_full_database(input_path: str) -> dict:
    """Import a previously exported JSON database. Merges data (INSERT OR IGNORE)."""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = get_conn()
    counts = {}

    for table, rows in data.get("tables", {}).items():
        if not rows:
            counts[table] = 0
            continue

        # Check if table exists
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            counts[table] = -1  # table doesn't exist
            continue

        cols = list(rows[0].keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(f"[{c}]" for c in cols)

        imported = 0
        for row in rows:
            try:
                vals = [row.get(c) for c in cols]
                conn.execute(f"INSERT OR IGNORE INTO [{table}] ({col_names}) VALUES ({placeholders})", vals)
                imported += 1
            except Exception:
                pass
        counts[table] = imported

    conn.commit()
    conn.close()
    return counts


def create_backup() -> str:
    """Create a timestamped backup of the database file."""
    ensure_directories()
    backup_dir = os.path.join(DATA_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"cerasus_hub_{timestamp}.db")
    shutil.copy2(DB_FILE, backup_path)

    # Keep only last 10 backups
    backups = sorted([f for f in os.listdir(backup_dir) if f.endswith(".db")])
    while len(backups) > 10:
        os.remove(os.path.join(backup_dir, backups.pop(0)))

    return backup_path


def get_database_stats() -> dict:
    """Get table row counts and database file size."""
    conn = get_conn()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]

    stats = {"file_size_mb": round(os.path.getsize(DB_FILE) / (1024*1024), 2), "tables": {}}
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) as c FROM [{table}]").fetchone()["c"]
        stats["tables"][table] = count

    conn.close()
    return stats
