"""
Cerasus Hub — Legacy Data Migration Script
Imports data from the two standalone apps into the CerasusHub unified database:
  1. CerasusOperationsManager (JSON) -> officers, sites, assignments, records, PTO
  2. cerasus-uniform (SQLite)        -> officers, sites, catalog, issuances,
                                        requirements, kits, site_requirements,
                                        pending_orders, catalog_sizes

De-duplicates officers and sites by name, logs everything, and prints a summary.

Usage:
    cd CerasusHub
    python migrate_legacy.py
"""

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Ensure CerasusHub's own modules are importable
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from src.config import ensure_directories, DB_FILE
from src.database import get_conn, initialize_database, run_migrations

# We need the migration dicts to ensure all tables exist before inserting.
from src.modules.operations.migrations import MIGRATIONS as OPS_MIGRATIONS
from src.modules.uniforms.migrations import MIGRATIONS as UNI_MIGRATIONS

# ---------------------------------------------------------------------------
# Paths to legacy data
# ---------------------------------------------------------------------------
COWORK = os.path.dirname(SCRIPT_DIR)  # "Claude Cowork" folder

OPS_JSON = os.path.join(COWORK, "CerasusOperationsManager", "data", "app_data.json")
UNI_DB = os.path.join(COWORK, "cerasus-uniform", "data", "uniform_data.db")
UNI_JSON = os.path.join(COWORK, "cerasus-uniform", "data", "uniform_data.json")

LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
def setup_logging():
    logger = logging.getLogger("migration")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                            datefmt="%H:%M:%S")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


log = setup_logging()


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
class Stats:
    def __init__(self):
        self.officers_imported = 0
        self.officers_skipped = 0
        self.sites_imported = 0
        self.sites_skipped = 0
        self.records_imported = 0
        self.records_skipped = 0
        self.assignments_imported = 0
        self.assignments_skipped = 0
        self.pto_imported = 0
        self.pto_skipped = 0
        self.catalog_imported = 0
        self.catalog_skipped = 0
        self.catalog_sizes_imported = 0
        self.catalog_sizes_skipped = 0
        self.issuances_imported = 0
        self.issuances_skipped = 0
        self.requirements_imported = 0
        self.requirements_skipped = 0
        self.kits_imported = 0
        self.kits_skipped = 0
        self.site_requirements_imported = 0
        self.site_requirements_skipped = 0
        self.pending_orders_imported = 0
        self.pending_orders_skipped = 0
        self.errors = 0


stats = Stats()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    """Normalize a name for dedup comparison."""
    return " ".join(name.strip().lower().split())


def _list_to_json(val) -> str:
    """Ensure list-type fields are stored as JSON strings."""
    if isinstance(val, list):
        return json.dumps(val)
    if isinstance(val, str):
        return val
    return "[]"


def _dict_to_json(val) -> str:
    """Ensure dict-type fields are stored as JSON strings."""
    if isinstance(val, dict):
        return json.dumps(val)
    if isinstance(val, str):
        return val
    return "{}"


# ---------------------------------------------------------------------------
# Name -> ID maps (built during migration for dedup)
# ---------------------------------------------------------------------------
officer_name_map: dict[str, str] = {}   # normalized name -> officer_id
site_name_map: dict[str, str] = {}      # normalized name -> site_id


def _load_existing_hub_data(conn):
    """Pre-populate dedup maps from any data already in the Hub DB."""
    rows = conn.execute("SELECT officer_id, name FROM officers").fetchall()
    for r in rows:
        key = _normalize_name(r["name"])
        if key:
            officer_name_map[key] = r["officer_id"]

    rows = conn.execute("SELECT site_id, name FROM sites").fetchall()
    for r in rows:
        key = _normalize_name(r["name"])
        if key:
            site_name_map[key] = r["site_id"]


# ---------------------------------------------------------------------------
# Officer merge/insert
# ---------------------------------------------------------------------------
def _upsert_officer(conn, fields: dict, source: str) -> str:
    """Insert an officer or return existing ID if name matches."""
    name = fields.get("name", "").strip()
    if not name:
        return ""

    key = _normalize_name(name)
    if key in officer_name_map:
        oid = officer_name_map[key]
        log.debug("Officer '%s' already exists (id=%s), skipping (%s)", name, oid, source)
        stats.officers_skipped += 1
        return oid

    now = _now()
    import secrets
    oid = secrets.token_hex(12)

    trained = _list_to_json(fields.get("trained_sites", []))
    approved = _list_to_json(fields.get("approved_sites", []))
    anchor = _list_to_json(fields.get("anchor_sites", []))
    sizes = _dict_to_json(fields.get("uniform_sizes", {}))

    conn.execute(
        """INSERT INTO officers
           (officer_id, name, employee_id, first_name, last_name,
            email, phone, job_title, role, site, supervisor_id, hire_date,
            status, weekly_hours, trained_sites, approved_sites, anchor_sites,
            uniform_sizes, role_title, active_points, discipline_level,
            last_infraction_date, emergency_exemptions_used,
            notes, created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (oid, name,
         fields.get("employee_id", ""),
         fields.get("first_name", ""), fields.get("last_name", ""),
         fields.get("email", ""), fields.get("phone", ""),
         fields.get("job_title", "Security Officer"),
         fields.get("role", "Flex Officer"),
         fields.get("site", ""),
         fields.get("supervisor_id", ""),
         fields.get("hire_date", ""),
         fields.get("status", "Active"),
         str(fields.get("weekly_hours", "40")),
         trained, approved, anchor, sizes,
         fields.get("role_title", ""),
         fields.get("active_points", 0),
         fields.get("discipline_level", "None"),
         fields.get("last_infraction_date", ""),
         fields.get("emergency_exemptions_used", 0),
         fields.get("notes", ""),
         f"migration:{source}", f"migration:{source}", now, now)
    )
    officer_name_map[key] = oid
    stats.officers_imported += 1
    log.info("Imported officer '%s' from %s (id=%s)", name, source, oid)
    return oid


# ---------------------------------------------------------------------------
# Site merge/insert
# ---------------------------------------------------------------------------
def _upsert_site(conn, fields: dict, source: str) -> str:
    """Insert a site or return existing ID if name matches."""
    name = fields.get("name", "").strip()
    if not name:
        return ""

    key = _normalize_name(name)
    if key in site_name_map:
        sid = site_name_map[key]
        log.debug("Site '%s' already exists (id=%s), skipping (%s)", name, sid, source)
        stats.sites_skipped += 1
        return sid

    now = _now()
    import secrets
    sid = secrets.token_hex(12)

    conn.execute(
        """INSERT INTO sites
           (site_id, name, address, city, state, style,
            billing_code, market, overtime_sensitivity, status,
            notes, created_by, updated_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, name,
         fields.get("address", ""),
         fields.get("city", ""),
         fields.get("state", ""),
         fields.get("style", "Soft Look"),
         fields.get("billing_code", ""),
         fields.get("market", ""),
         fields.get("overtime_sensitivity", "Normal"),
         fields.get("status", "Active"),
         fields.get("notes", ""),
         f"migration:{source}", f"migration:{source}", now, now)
    )
    site_name_map[key] = sid
    stats.sites_imported += 1
    log.info("Imported site '%s' from %s (id=%s)", name, source, sid)
    return sid


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: Operations Manager (JSON)
# ═══════════════════════════════════════════════════════════════════════════

def migrate_ops_manager(conn):
    """Import data from CerasusOperationsManager's app_data.json."""
    log.info("=" * 60)
    log.info("PHASE 1: CerasusOperationsManager (JSON)")
    log.info("=" * 60)

    if not os.path.exists(OPS_JSON):
        log.warning("Operations Manager data file not found: %s — skipping", OPS_JSON)
        return

    try:
        with open(OPS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log.error("Failed to read Operations Manager JSON: %s", e)
        stats.errors += 1
        return

    log.info("Loaded JSON with keys: %s", list(data.keys()))

    # -- Officers --
    for o in data.get("officers", []):
        try:
            _upsert_officer(conn, o, "ops-manager")
        except Exception as e:
            log.error("Error importing officer '%s': %s", o.get("name", "?"), e)
            stats.errors += 1

    # -- Sites --
    for s in data.get("sites", []):
        try:
            _upsert_site(conn, s, "ops-manager")
        except Exception as e:
            log.error("Error importing site '%s': %s", s.get("name", "?"), e)
            stats.errors += 1

    # -- Records --
    now = _now()
    for r in data.get("records", []):
        try:
            rid = r.get("record_id", "")
            if rid:
                existing = conn.execute(
                    "SELECT 1 FROM ops_records WHERE record_id = ?", (rid,)
                ).fetchone()
                if existing:
                    stats.records_skipped += 1
                    continue

            import secrets
            rid = rid or secrets.token_hex(4)
            conn.execute(
                """INSERT OR IGNORE INTO ops_records
                   (record_id, employee_name, site_name, date, status, priority,
                    notes, created_by, updated_by, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (rid,
                 r.get("employee_name", ""), r.get("site_name", ""),
                 r.get("date", ""), r.get("status", "Open"),
                 r.get("priority", "Normal"), r.get("notes", ""),
                 r.get("created_by", "migration:ops-manager"),
                 r.get("updated_by", "migration:ops-manager"),
                 r.get("created_at", now), r.get("updated_at", now))
            )
            stats.records_imported += 1
            log.info("Imported record %s", rid)
        except Exception as e:
            log.error("Error importing record: %s", e)
            stats.errors += 1

    # -- Assignments --
    for a in data.get("assignments", []):
        try:
            aid = a.get("assignment_id", "")
            if aid:
                existing = conn.execute(
                    "SELECT 1 FROM ops_assignments WHERE assignment_id = ?", (aid,)
                ).fetchone()
                if existing:
                    stats.assignments_skipped += 1
                    continue

            import secrets
            aid = aid or secrets.token_hex(4)
            conn.execute(
                """INSERT OR IGNORE INTO ops_assignments
                   (assignment_id, officer_name, site_name, date,
                    start_time, end_time, hours, assignment_type, status,
                    notes, created_by, updated_by, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (aid,
                 a.get("officer_name", ""), a.get("site_name", ""),
                 a.get("date", ""), a.get("start_time", ""),
                 a.get("end_time", ""), str(a.get("hours", "0")),
                 a.get("assignment_type", "Billable"),
                 a.get("status", "Scheduled"),
                 a.get("notes", ""),
                 a.get("created_by", "migration:ops-manager"),
                 a.get("updated_by", "migration:ops-manager"),
                 a.get("created_at", now), a.get("updated_at", now))
            )
            stats.assignments_imported += 1
            log.info("Imported assignment %s (%s @ %s on %s)",
                     aid, a.get("officer_name", ""), a.get("site_name", ""), a.get("date", ""))
        except Exception as e:
            log.error("Error importing assignment: %s", e)
            stats.errors += 1

    # -- PTO --
    for p in data.get("pto_entries", []):
        try:
            pid = p.get("pto_id", "")
            if pid:
                existing = conn.execute(
                    "SELECT 1 FROM ops_pto_entries WHERE pto_id = ?", (pid,)
                ).fetchone()
                if existing:
                    stats.pto_skipped += 1
                    continue

            import secrets
            pid = pid or secrets.token_hex(4)
            conn.execute(
                """INSERT OR IGNORE INTO ops_pto_entries
                   (pto_id, officer_name, start_date, end_date, pto_type,
                    status, notes, created_by, updated_by, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (pid,
                 p.get("officer_name", ""),
                 p.get("start_date", ""), p.get("end_date", ""),
                 p.get("pto_type", "Unavailable"),
                 p.get("status", "Approved"),
                 p.get("notes", ""),
                 p.get("created_by", "migration:ops-manager"),
                 p.get("updated_by", "migration:ops-manager"),
                 p.get("created_at", now), p.get("updated_at", now))
            )
            stats.pto_imported += 1
            log.info("Imported PTO %s for %s", pid, p.get("officer_name", ""))
        except Exception as e:
            log.error("Error importing PTO: %s", e)
            stats.errors += 1

    conn.commit()
    log.info("Phase 1 complete.")


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: Uniform Module (SQLite)
# ═══════════════════════════════════════════════════════════════════════════

def _open_legacy_uniform_db() -> sqlite3.Connection | None:
    """Open the legacy uniform SQLite database, if it exists."""
    if os.path.exists(UNI_DB):
        conn = sqlite3.connect(UNI_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    return None


def _read_legacy_uniform_json() -> dict | None:
    """Read the legacy uniform JSON file as a fallback."""
    # Check the .migrated backup too
    for path in [UNI_JSON, UNI_JSON + ".migrated"]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                continue
    return None


def migrate_uniform_module(hub_conn):
    """Import data from cerasus-uniform into the Hub's uni_* tables."""
    log.info("=" * 60)
    log.info("PHASE 2: cerasus-uniform (SQLite / JSON)")
    log.info("=" * 60)

    legacy_conn = _open_legacy_uniform_db()
    legacy_json = None

    if legacy_conn is None:
        log.warning("Uniform SQLite DB not found: %s", UNI_DB)
        legacy_json = _read_legacy_uniform_json()
        if legacy_json is None:
            log.warning("No uniform data files found at all — skipping Phase 2.")
            return
        log.info("Using legacy JSON fallback.")
    else:
        log.info("Opened legacy uniform SQLite DB: %s", UNI_DB)

    now = _now()

    # ------------------------------------------------------------------
    # Officers from uniform module
    # ------------------------------------------------------------------
    if legacy_conn:
        try:
            rows = legacy_conn.execute("SELECT * FROM officers").fetchall()
            for r in rows:
                o = dict(r)
                # Parse uniform_sizes if JSON string
                sizes = o.get("uniform_sizes", "{}")
                if isinstance(sizes, str):
                    try:
                        sizes = json.loads(sizes)
                    except json.JSONDecodeError:
                        sizes = {}

                fields = {
                    "name": o.get("name", ""),
                    "employee_id": o.get("employee_id", ""),
                    "email": o.get("email", ""),
                    "phone": o.get("phone", ""),
                    "job_title": o.get("job_title", "Security Officer"),
                    "site": o.get("site", ""),
                    "hire_date": o.get("hire_date", ""),
                    "uniform_sizes": sizes,
                    "status": o.get("status", "Active"),
                    "notes": o.get("notes", ""),
                }
                _upsert_officer(hub_conn, fields, "uniform-db")
        except sqlite3.OperationalError as e:
            log.warning("Could not read officers from uniform DB: %s", e)
    elif legacy_json:
        for o in legacy_json.get("officers", []):
            fields = {
                "name": o.get("name", ""),
                "employee_id": o.get("employee_id", ""),
                "email": o.get("email", ""),
                "phone": o.get("phone", ""),
                "job_title": o.get("job_title", "Security Officer"),
                "site": o.get("site", ""),
                "hire_date": o.get("hire_date", ""),
                "uniform_sizes": o.get("uniform_sizes", {}),
                "status": o.get("status", "Active"),
                "notes": o.get("notes", ""),
            }
            _upsert_officer(hub_conn, fields, "uniform-json")

    # ------------------------------------------------------------------
    # Sites from uniform module
    # ------------------------------------------------------------------
    if legacy_conn:
        try:
            rows = legacy_conn.execute("SELECT * FROM sites").fetchall()
            for r in rows:
                s = dict(r)
                _upsert_site(hub_conn, {
                    "name": s.get("name", ""),
                    "address": s.get("address", ""),
                    "city": s.get("city", ""),
                    "state": s.get("state", ""),
                    "style": s.get("style", "Soft Look"),
                    "notes": s.get("notes", ""),
                }, "uniform-db")
        except sqlite3.OperationalError as e:
            log.warning("Could not read sites from uniform DB: %s", e)

    hub_conn.commit()

    # ------------------------------------------------------------------
    # Catalog items
    # ------------------------------------------------------------------
    def _import_catalog(items, source_label):
        for c in items:
            try:
                item_id = c.get("item_id", "")
                name = c.get("name", "").strip()
                if not name:
                    continue

                # Check if already exists by name (dedup)
                existing = hub_conn.execute(
                    "SELECT item_id FROM uni_catalog WHERE LOWER(name) = LOWER(?)", (name,)
                ).fetchone()
                if existing:
                    stats.catalog_skipped += 1
                    log.debug("Catalog item '%s' already exists, skipping", name)
                    continue

                import secrets
                new_id = item_id or secrets.token_hex(4)

                # Also check by original ID to avoid PK collision
                if item_id:
                    pk_exists = hub_conn.execute(
                        "SELECT 1 FROM uni_catalog WHERE item_id = ?", (item_id,)
                    ).fetchone()
                    if pk_exists:
                        new_id = secrets.token_hex(4)

                hub_conn.execute(
                    """INSERT INTO uni_catalog
                       (item_id, name, category, style, gender, description,
                        stock_qty, reorder_point, unit_cost, lifecycle_days,
                        created_by, updated_by, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (new_id, name,
                     c.get("category", "Other"),
                     c.get("style", ""), c.get("gender", ""),
                     c.get("description", ""),
                     int(c.get("stock_qty", 0)),
                     int(c.get("reorder_point", 5)),
                     float(c.get("unit_cost", 0)),
                     int(c.get("lifecycle_days", 365)),
                     f"migration:{source_label}", f"migration:{source_label}",
                     c.get("created_at", now), c.get("updated_at", now))
                )
                stats.catalog_imported += 1
                log.info("Imported catalog item '%s' from %s", name, source_label)
            except Exception as e:
                log.error("Error importing catalog item '%s': %s", c.get("name", "?"), e)
                stats.errors += 1

    if legacy_conn:
        try:
            rows = legacy_conn.execute("SELECT * FROM catalog").fetchall()
            _import_catalog([dict(r) for r in rows], "uniform-db")
        except sqlite3.OperationalError as e:
            log.warning("Could not read catalog from uniform DB: %s", e)
    elif legacy_json:
        _import_catalog(legacy_json.get("catalog", []), "uniform-json")

    hub_conn.commit()

    # ------------------------------------------------------------------
    # Catalog sizes
    # ------------------------------------------------------------------
    if legacy_conn:
        try:
            rows = legacy_conn.execute("SELECT * FROM catalog_sizes").fetchall()
            for r in rows:
                cs = dict(r)
                try:
                    hub_conn.execute(
                        """INSERT OR IGNORE INTO uni_catalog_sizes
                           (item_id, size, location, stock_qty)
                           VALUES (?,?,?,?)""",
                        (cs.get("item_id", ""),
                         cs.get("size", ""),
                         cs.get("location", "Cerasus HQ"),
                         int(cs.get("stock_qty", 0)))
                    )
                    stats.catalog_sizes_imported += 1
                except Exception as e:
                    log.error("Error importing catalog size: %s", e)
                    stats.errors += 1
            hub_conn.commit()
        except sqlite3.OperationalError as e:
            log.warning("Could not read catalog_sizes from uniform DB: %s", e)

    # ------------------------------------------------------------------
    # Issuances
    # ------------------------------------------------------------------
    def _import_issuances(items, source_label):
        for i in items:
            try:
                iid = i.get("issuance_id", "")
                if iid:
                    existing = hub_conn.execute(
                        "SELECT 1 FROM uni_issuances WHERE issuance_id = ?", (iid,)
                    ).fetchone()
                    if existing:
                        stats.issuances_skipped += 1
                        continue

                import secrets
                iid = iid or secrets.token_hex(4)

                hub_conn.execute(
                    """INSERT OR IGNORE INTO uni_issuances
                       (issuance_id, officer_id, officer_name, item_id, item_name,
                        size, quantity, condition_issued, date_issued, issued_by,
                        notes, status, date_returned, return_condition, return_notes,
                        location, created_by, updated_by, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (iid,
                     i.get("officer_id", ""), i.get("officer_name", ""),
                     i.get("item_id", ""), i.get("item_name", ""),
                     i.get("size", ""), int(i.get("quantity", 1)),
                     i.get("condition_issued", "New"),
                     i.get("date_issued", ""), i.get("issued_by", ""),
                     i.get("notes", ""),
                     i.get("status", "Outstanding"),
                     i.get("date_returned"), i.get("return_condition"),
                     i.get("return_notes", ""),
                     i.get("location", ""),
                     f"migration:{source_label}", f"migration:{source_label}",
                     i.get("created_at", now), i.get("updated_at", now))
                )
                stats.issuances_imported += 1
                log.info("Imported issuance %s (%s -> %s)",
                         iid, i.get("officer_name", "?"), i.get("item_name", "?"))
            except Exception as e:
                log.error("Error importing issuance: %s", e)
                stats.errors += 1

    if legacy_conn:
        try:
            rows = legacy_conn.execute("SELECT * FROM issuances").fetchall()
            _import_issuances([dict(r) for r in rows], "uniform-db")
        except sqlite3.OperationalError as e:
            log.warning("Could not read issuances from uniform DB: %s", e)
    elif legacy_json:
        _import_issuances(legacy_json.get("issuances", []), "uniform-json")

    hub_conn.commit()

    # ------------------------------------------------------------------
    # Requirements (job-title-based)
    # ------------------------------------------------------------------
    def _import_requirements(items, source_label):
        for r in items:
            try:
                hub_conn.execute(
                    """INSERT INTO uni_requirements
                       (job_title, item_id, item_name, qty_required)
                       VALUES (?,?,?,?)""",
                    (r.get("job_title", ""), r.get("item_id", ""),
                     r.get("item_name", ""), int(r.get("qty_required", 1)))
                )
                stats.requirements_imported += 1
            except Exception as e:
                log.error("Error importing requirement: %s", e)
                stats.errors += 1

    if legacy_conn:
        try:
            # Check if there are already requirements in the hub
            hub_count = hub_conn.execute("SELECT COUNT(*) FROM uni_requirements").fetchone()[0]
            if hub_count == 0:
                rows = legacy_conn.execute("SELECT * FROM requirements").fetchall()
                _import_requirements([dict(r) for r in rows], "uniform-db")
            else:
                log.info("Hub already has %d requirements — skipping import", hub_count)
                stats.requirements_skipped += hub_count
        except sqlite3.OperationalError as e:
            log.warning("Could not read requirements from uniform DB: %s", e)
    elif legacy_json:
        hub_count = hub_conn.execute("SELECT COUNT(*) FROM uni_requirements").fetchone()[0]
        if hub_count == 0:
            _import_requirements(legacy_json.get("requirements", []), "uniform-json")

    hub_conn.commit()

    # ------------------------------------------------------------------
    # Kits
    # ------------------------------------------------------------------
    if legacy_conn:
        try:
            rows = legacy_conn.execute("SELECT * FROM kits").fetchall()
            for r in rows:
                k = dict(r)
                try:
                    kit_id = k.get("kit_id", "")
                    if kit_id:
                        existing = hub_conn.execute(
                            "SELECT 1 FROM uni_kits WHERE kit_id = ?", (kit_id,)
                        ).fetchone()
                        if existing:
                            stats.kits_skipped += 1
                            continue

                    import secrets
                    kit_id = kit_id or secrets.token_hex(4)
                    items_json = k.get("items", "[]")
                    if isinstance(items_json, list):
                        items_json = json.dumps(items_json)

                    hub_conn.execute(
                        """INSERT OR IGNORE INTO uni_kits
                           (kit_id, name, description, items, created_by, created_at)
                           VALUES (?,?,?,?,?,?)""",
                        (kit_id, k.get("name", "Standard Kit"),
                         k.get("description", ""), items_json,
                         f"migration:uniform-db",
                         k.get("created_at", now))
                    )
                    stats.kits_imported += 1
                    log.info("Imported kit '%s'", k.get("name", "?"))
                except Exception as e:
                    log.error("Error importing kit: %s", e)
                    stats.errors += 1
        except sqlite3.OperationalError as e:
            log.warning("Could not read kits from uniform DB: %s", e)

    hub_conn.commit()

    # ------------------------------------------------------------------
    # Site requirements
    # ------------------------------------------------------------------
    if legacy_conn:
        try:
            hub_count = hub_conn.execute("SELECT COUNT(*) FROM uni_site_requirements").fetchone()[0]
            if hub_count == 0:
                rows = legacy_conn.execute("SELECT * FROM site_requirements").fetchall()
                for r in rows:
                    sr = dict(r)
                    try:
                        hub_conn.execute(
                            """INSERT INTO uni_site_requirements
                               (site_id, item_id, item_name, qty_required)
                               VALUES (?,?,?,?)""",
                            (sr.get("site_id", ""), sr.get("item_id", ""),
                             sr.get("item_name", ""), int(sr.get("qty_required", 1)))
                        )
                        stats.site_requirements_imported += 1
                    except Exception as e:
                        log.error("Error importing site requirement: %s", e)
                        stats.errors += 1
            else:
                log.info("Hub already has %d site requirements — skipping", hub_count)
        except sqlite3.OperationalError as e:
            log.warning("Could not read site_requirements from uniform DB: %s", e)

    hub_conn.commit()

    # ------------------------------------------------------------------
    # Pending orders
    # ------------------------------------------------------------------
    if legacy_conn:
        try:
            rows = legacy_conn.execute("SELECT * FROM pending_orders").fetchall()
            for r in rows:
                po = dict(r)
                try:
                    oid = po.get("order_id", "")
                    if oid:
                        existing = hub_conn.execute(
                            "SELECT 1 FROM uni_pending_orders WHERE order_id = ?", (oid,)
                        ).fetchone()
                        if existing:
                            stats.pending_orders_skipped += 1
                            continue

                    import secrets
                    oid = oid or secrets.token_hex(4)

                    hub_conn.execute(
                        """INSERT OR IGNORE INTO uni_pending_orders
                           (order_id, officer_id, officer_name, item_id, item_name,
                            size, quantity, order_type, date_ordered, date_expected,
                            ordered_by, notes, status, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (oid,
                         po.get("officer_id", ""), po.get("officer_name", ""),
                         po.get("item_id", ""), po.get("item_name", ""),
                         po.get("size", ""), int(po.get("quantity", 1)),
                         po.get("order_type", "New Hire"),
                         po.get("date_ordered", ""), po.get("date_expected", ""),
                         po.get("ordered_by", ""), po.get("notes", ""),
                         po.get("status", "Pending"),
                         po.get("created_at", now), po.get("updated_at", now))
                    )
                    stats.pending_orders_imported += 1
                    log.info("Imported pending order %s", oid)
                except Exception as e:
                    log.error("Error importing pending order: %s", e)
                    stats.errors += 1
        except sqlite3.OperationalError as e:
            log.warning("Could not read pending_orders from uniform DB: %s", e)

    hub_conn.commit()

    if legacy_conn:
        legacy_conn.close()

    log.info("Phase 2 complete.")


# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════

def print_summary():
    """Print a formatted migration summary."""
    lines = [
        "",
        "=" * 60,
        "  MIGRATION SUMMARY",
        "=" * 60,
        "",
        f"  Officers ....... {stats.officers_imported:4d} imported, {stats.officers_skipped:4d} skipped (dedup)",
        f"  Sites .......... {stats.sites_imported:4d} imported, {stats.sites_skipped:4d} skipped (dedup)",
        f"  Records ........ {stats.records_imported:4d} imported, {stats.records_skipped:4d} skipped",
        f"  Assignments .... {stats.assignments_imported:4d} imported, {stats.assignments_skipped:4d} skipped",
        f"  PTO entries .... {stats.pto_imported:4d} imported, {stats.pto_skipped:4d} skipped",
        f"  Catalog items .. {stats.catalog_imported:4d} imported, {stats.catalog_skipped:4d} skipped",
        f"  Catalog sizes .. {stats.catalog_sizes_imported:4d} imported, {stats.catalog_sizes_skipped:4d} skipped",
        f"  Issuances ...... {stats.issuances_imported:4d} imported, {stats.issuances_skipped:4d} skipped",
        f"  Requirements ... {stats.requirements_imported:4d} imported, {stats.requirements_skipped:4d} skipped",
        f"  Kits ........... {stats.kits_imported:4d} imported, {stats.kits_skipped:4d} skipped",
        f"  Site reqs ...... {stats.site_requirements_imported:4d} imported, {stats.site_requirements_skipped:4d} skipped",
        f"  Pending orders . {stats.pending_orders_imported:4d} imported, {stats.pending_orders_skipped:4d} skipped",
        "",
        f"  Errors: {stats.errors}",
        "",
        f"  Hub database: {DB_FILE}",
        f"  Migration log: {LOG_FILE}",
        "=" * 60,
    ]
    text = "\n".join(lines)
    print(text)
    log.info(text)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    log.info("Cerasus Hub — Legacy Data Migration")
    log.info("Started at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Hub DB: %s", DB_FILE)
    log.info("Ops JSON: %s (exists=%s)", OPS_JSON, os.path.exists(OPS_JSON))
    log.info("Uniform DB: %s (exists=%s)", UNI_DB, os.path.exists(UNI_DB))

    # Ensure CerasusHub directories and database schema are ready
    ensure_directories()
    initialize_database()

    # Run module migrations to create ops and uniform tables
    conn = get_conn()
    run_migrations(conn, "operations", OPS_MIGRATIONS)
    run_migrations(conn, "uniforms", UNI_MIGRATIONS)
    conn.commit()

    # Load existing data for dedup
    _load_existing_hub_data(conn)
    log.info("Pre-existing officers in Hub: %d", len(officer_name_map))
    log.info("Pre-existing sites in Hub: %d", len(site_name_map))

    # Run both migration phases
    try:
        migrate_ops_manager(conn)
        migrate_uniform_module(conn)
        conn.commit()
    except Exception as e:
        log.error("Migration failed with unexpected error: %s", e, exc_info=True)
        stats.errors += 1
        conn.rollback()
    finally:
        conn.close()

    print_summary()

    if stats.errors > 0:
        log.warning("Migration completed WITH ERRORS. Check the log for details.")
        sys.exit(1)
    else:
        log.info("Migration completed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
