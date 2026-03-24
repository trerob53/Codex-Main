"""
CerasusHub — Pre-Build Test Suite
Run this before every build to catch crashes, missing tables, broken imports,
and data integrity issues. If this passes, the EXE works.

Usage:  python test_suite.py
"""

import sys
import os
import traceback
import sqlite3
import json
import csv
import io
from datetime import datetime, timezone

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0
WARN = 0
RESULTS = []


def ok(test_name, detail=""):
    global PASS
    PASS += 1
    RESULTS.append(("PASS", test_name, detail))
    print(f"  PASS  {test_name}")


def fail(test_name, detail=""):
    global FAIL
    FAIL += 1
    RESULTS.append(("FAIL", test_name, detail))
    print(f"  FAIL  {test_name}  --  {detail}")


def warn(test_name, detail=""):
    global WARN
    WARN += 1
    RESULTS.append(("WARN", test_name, detail))
    print(f"  WARN  {test_name}  --  {detail}")


def section(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


# ======================================================================
#  1. CORE IMPORTS
# ======================================================================
def test_core_imports():
    section("1. Core Imports")
    modules = [
        "src.config",
        "src.database",
        "src.auth",
        "src.audit",
        "src.shared_data",
        "src.shared_widgets",
        "src.session_manager",
        "src.lock_manager",
        "src.hub_people",
        "src.hub_gui",
        "src.permissions",
        "src.form_validation",
        "src.custom_fields",
    ]
    for mod in modules:
        try:
            __import__(mod)
            ok(f"import {mod}")
        except Exception as e:
            fail(f"import {mod}", str(e))


# ======================================================================
#  2. DATABASE & MIGRATIONS
# ======================================================================
def test_database():
    section("2. Database & Migrations")

    # Test connection
    try:
        from src.database import get_conn, initialize_database
        initialize_database()
        ok("initialize_database()")
    except Exception as e:
        fail("initialize_database()", str(e))
        return

    conn = get_conn()

    # Check all expected tables exist
    expected_tables = [
        # Core
        "schema_versions", "users", "officers", "sites", "audit_log",
        "sessions", "settings",
        # Operations
        "ops_records", "ops_assignments", "ops_pto_entries",
        "ops_incidents", "ops_handoff_notes", "ops_flex_team",
        "ops_open_requests", "ops_anchor_schedules",
        # Uniforms
        "uni_catalog", "uni_catalog_sizes", "uni_issuances",
        "uni_requirements", "uni_kits", "uni_site_requirements",
        "uni_pending_orders",
        # Attendance
        "ats_infractions", "ats_employment_reviews",
        # Training
        "trn_courses", "trn_modules", "trn_chapters", "trn_tests",
        "trn_progress", "trn_test_attempts", "trn_certificates",
        # DA Generator
        "da_records",
    ]

    actual_tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    for table in expected_tables:
        if table in actual_tables:
            ok(f"table exists: {table}")
        else:
            fail(f"table exists: {table}", "MISSING")

    # Check migration versions
    try:
        rows = conn.execute(
            "SELECT module_name, MAX(version) as v FROM schema_versions GROUP BY module_name"
        ).fetchall()
        versions = {r[0]: r[1] for r in rows}

        expected_versions = {
            "core": 1,
            "operations": 6,
            "uniforms": 1,
            "attendance": 1,
            "training": 1,
            "da_generator": 3,
        }
        for mod, expected_v in expected_versions.items():
            actual_v = versions.get(mod, 0)
            if actual_v >= expected_v:
                ok(f"migration {mod} v{actual_v} >= v{expected_v}")
            else:
                fail(f"migration {mod}", f"at v{actual_v}, expected >= v{expected_v}")
    except Exception as e:
        fail("migration versions", str(e))

    conn.close()


# ======================================================================
#  3. FRESH DB MIGRATION TEST
# ======================================================================
def test_fresh_db_migrations():
    section("3. Fresh DB Migration (clean slate)")
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "cerasus_test_fresh.db")
    if os.path.exists(tmp):
        os.remove(tmp)

    try:
        from src.database import get_conn, run_migrations, CORE_MIGRATIONS

        conn = sqlite3.connect(tmp)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Bootstrap schema_versions
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

        # Run core
        run_migrations(conn, "core", CORE_MIGRATIONS)
        ok("core migrations on fresh DB")

        # Run each module
        module_names = ["operations", "uniforms", "attendance", "training", "da_generator"]
        for mod_name in module_names:
            try:
                m = __import__(f"src.modules.{mod_name}", fromlist=["get_module"])
                mod = m.get_module()
                migs = mod.get_migrations()
                if migs:
                    run_migrations(conn, mod.module_id, migs)
                ok(f"fresh migration: {mod_name}")
            except Exception as e:
                fail(f"fresh migration: {mod_name}", str(e))

        conn.close()
    except Exception as e:
        fail("fresh DB migration", str(e))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
        for ext in ["-wal", "-shm"]:
            p = tmp + ext
            if os.path.exists(p):
                os.remove(p)


# ======================================================================
#  4. MODULE IMPORTS & PAGE CLASSES
# ======================================================================
def test_module_imports():
    section("4. Module Imports & Page Classes")

    module_pages = {
        "operations": [
            "src.modules.operations.pages_dashboard",
            "src.modules.operations.pages_flex_board",
            "src.modules.operations.pages_open_requests",
            "src.modules.operations.pages_coverage_map",
            "src.modules.operations.pages_anchor_schedules",
            "src.modules.operations.pages_ops",
            "src.modules.operations.pages_pto",
            "src.modules.operations.pages_admin",
            "src.modules.operations.pages_handoff",
            "src.modules.operations.data_manager",
        ],
        "uniforms": [
            "src.modules.uniforms.pages_dashboard",
            "src.modules.uniforms.pages_personnel",
            "src.modules.uniforms.pages_uniform",
            "src.modules.uniforms.pages_inventory",
            "src.modules.uniforms.pages_compliance",
            "src.modules.uniforms.pages_sites",
            "src.modules.uniforms.pages_admin",
            "src.modules.uniforms.data_manager",
            "src.modules.uniforms.email_service",
            "src.modules.uniforms.notification_log",
            "src.modules.uniforms.qr_labels",
        ],
        "attendance": [
            "src.modules.attendance.pages_dashboard",
            "src.modules.attendance.pages_roster",
            "src.modules.attendance.pages_infractions",
            "src.modules.attendance.pages_discipline",
            "src.modules.attendance.pages_reviews",
            "src.modules.attendance.pages_reports",
            "src.modules.attendance.pages_admin",
            "src.modules.attendance.pages_import",
            "src.modules.attendance.pages_bulk_import",
            "src.modules.attendance.data_manager",
            "src.modules.attendance.policy_engine",
            "src.modules.attendance.duplicate_scanner",
        ],
        "training": [
            "src.modules.training.pages_dashboard",
            "src.modules.training.pages_courses",
            "src.modules.training.pages_leaderboard",
            "src.modules.training.pages_certificates",
            "src.modules.training.pages_admin",
            "src.modules.training.data_manager",
        ],
        "da_generator": [
            "src.modules.da_generator.pages_wizard",
            "src.modules.da_generator.pages_history",
            "src.modules.da_generator.pages_templates",
            "src.modules.da_generator.pages_settings",
            "src.modules.da_generator.data_manager",
            "src.modules.da_generator.local_engine",
            "src.modules.da_generator.ceis_prompts",
            "src.modules.da_generator.pdf_filler",
        ],
    }

    for mod_name, page_modules in module_pages.items():
        for pm in page_modules:
            try:
                __import__(pm)
                ok(f"import {pm}")
            except Exception as e:
                fail(f"import {pm}", str(e)[:120])


# ======================================================================
#  5. SHARED DATA CRUD
# ======================================================================
def test_shared_data_crud():
    section("5. Shared Data CRUD (Officers & Sites)")

    from src.shared_data import (
        get_all_officers, get_all_sites, get_officer, get_site,
        create_officer, create_site, update_officer, update_site,
        delete_officer, delete_site, search_officers, get_officer_names,
        get_site_names, get_active_officers,
    )

    # Officers
    try:
        officers = get_all_officers()
        ok(f"get_all_officers() -> {len(officers)} records")
    except Exception as e:
        fail("get_all_officers()", str(e))

    try:
        active = get_active_officers()
        ok(f"get_active_officers() -> {len(active)} records")
    except Exception as e:
        fail("get_active_officers()", str(e))

    try:
        names = get_officer_names()
        ok(f"get_officer_names() -> {len(names)} records")
    except Exception as e:
        fail("get_officer_names()", str(e))

    try:
        results = search_officers("test")
        ok(f"search_officers('test') -> {len(results)} results")
    except Exception as e:
        fail("search_officers()", str(e))

    # Create / update / delete cycle
    try:
        oid = create_officer({
            "first_name": "Test", "last_name": "Officer",
            "name": "Test Officer", "status": "Active",
            "employee_id": "TEST-999",
        }, created_by="test_suite")
        officer = get_officer(oid)
        assert officer is not None, "Created officer not found"
        assert officer["name"] == "Test Officer", f"Name mismatch: {officer['name']}"
        ok("create_officer() + get_officer()")

        update_officer(oid, {"notes": "test note"}, updated_by="test_suite")
        updated = get_officer(oid)
        assert updated["notes"] == "test note", "Update didn't stick"
        ok("update_officer()")

        delete_officer(oid)
        gone = get_officer(oid)
        assert gone is None, "Delete didn't work"
        ok("delete_officer()")
    except Exception as e:
        fail("officer CRUD cycle", str(e))

    # Sites
    try:
        sites = get_all_sites()
        ok(f"get_all_sites() -> {len(sites)} records")
    except Exception as e:
        fail("get_all_sites()", str(e))

    try:
        site_names = get_site_names()
        ok(f"get_site_names() -> {len(site_names)} records")
    except Exception as e:
        fail("get_site_names()", str(e))

    # Create / update / delete cycle
    try:
        sid = create_site({
            "name": "Test Site", "city": "TestCity",
            "state": "TS", "status": "Active",
        }, created_by="test_suite")
        site = get_site(sid)
        assert site is not None, "Created site not found"
        assert site["name"] == "Test Site"
        ok("create_site() + get_site()")

        update_site(sid, {"notes": "test"}, updated_by="test_suite")
        ok("update_site()")

        delete_site(sid)
        ok("delete_site()")
    except Exception as e:
        fail("site CRUD cycle", str(e))


# ======================================================================
#  6. OPERATIONS MODULE DATA
# ======================================================================
def test_operations_data():
    section("6. Operations Module Data (Siloed)")

    try:
        from src.modules.operations.data_manager import (
            get_ops_officers, get_ops_officer, create_ops_officer,
            update_ops_officer, delete_ops_officer, search_ops_officers,
            get_all_records, create_record, get_record, delete_record,
            get_all_assignments, create_assignment, delete_assignment,
            get_all_pto, create_pto, delete_pto,
            get_dashboard_summary,
        )
        ok("import operations.data_manager")
    except Exception as e:
        fail("import operations.data_manager", str(e))
        return

    # Flex team is SILOED
    try:
        flex = get_ops_officers()
        ok(f"get_ops_officers() -> {len(flex)} flex officers")
        if len(flex) < 3:
            warn("flex team count", f"Expected 3, got {len(flex)}")
    except Exception as e:
        fail("get_ops_officers()", str(e))

    # Verify silo: flex officers with role "Flex Officer" should NOT be in shared table
    # (Some flex officers may exist in shared table as regular Guards — that's OK)
    try:
        from src.database import get_conn
        conn = get_conn()
        leaked = conn.execute("""
            SELECT name FROM officers
            WHERE LOWER(name) IN ('luis gonzalez', 'jeremiah gonzalez', 'jarrod allen')
            AND (role = 'Flex Officer' OR job_title LIKE '%Flex%')
        """).fetchall()
        conn.close()
        if leaked:
            warn("flex silo leak", f"Flex-tagged officers in shared table: {[r[0] for r in leaked]}")
        else:
            ok("flex team silo verified (no Flex-tagged officers in shared table)")
    except Exception as e:
        fail("flex silo check", str(e))

    # CRUD cycle for ops record
    try:
        rid = create_record({
            "employee_name": "Test", "site_name": "Test Site",
            "date": "2026-01-01", "status": "Open",
        }, created_by="test_suite")
        r = get_record(rid)
        assert r is not None
        delete_record(rid)
        ok("ops_records CRUD cycle")
    except Exception as e:
        fail("ops_records CRUD", str(e))

    # CRUD cycle for assignment
    try:
        aid = create_assignment({
            "officer_name": "Test", "site_name": "Test Site",
            "date": "2026-01-01", "start_time": "08:00", "end_time": "16:00",
            "assignment_type": "Billable", "status": "Scheduled",
        }, created_by="test_suite")
        delete_assignment(aid)
        ok("ops_assignments CRUD cycle")
    except Exception as e:
        fail("ops_assignments CRUD", str(e))

    # CRUD cycle for PTO
    try:
        pid = create_pto({
            "officer_name": "Test", "start_date": "2026-01-01",
            "end_date": "2026-01-02", "pto_type": "PTO", "status": "Approved",
        }, created_by="test_suite")
        delete_pto(pid)
        ok("ops_pto CRUD cycle")
    except Exception as e:
        fail("ops_pto CRUD", str(e))

    # Dashboard summary
    try:
        summary = get_dashboard_summary()
        assert isinstance(summary, dict)
        ok(f"ops dashboard_summary keys: {list(summary.keys())[:5]}...")
    except Exception as e:
        fail("ops dashboard_summary", str(e))

    # Open Requests CRUD
    try:
        from src.modules.operations.data_manager import (
            get_all_requests, create_request, get_request,
            update_request, delete_request, get_request_summary,
        )
        req_id = create_request({
            "site_name": "Test Site", "date": "2026-01-01",
            "start_time": "08:00", "end_time": "16:00",
            "reason": "Coverage", "priority": "Normal", "status": "Open",
        }, created_by="test_suite")
        req = get_request(req_id)
        assert req is not None, "Created request not found"
        update_request(req_id, {"priority": "Urgent"}, updated_by="test_suite")
        delete_request(req_id)
        ok("ops_open_requests CRUD cycle")
    except Exception as e:
        fail("ops_open_requests CRUD", str(e))

    try:
        summary = get_request_summary()
        assert isinstance(summary, dict)
        ok("get_request_summary()")
    except Exception as e:
        fail("get_request_summary()", str(e))

    # Anchor Schedules CRUD
    try:
        from src.modules.operations.data_manager import (
            get_all_anchor_schedules, create_anchor_schedule,
            get_anchor_schedule, update_anchor_schedule,
            delete_anchor_schedule, DAYS_OF_WEEK,
        )
        assert len(DAYS_OF_WEEK) == 7
        sid = create_anchor_schedule({
            "officer_name": "Test Officer",
            "position_title": "Flex Officer",
            "anchor_site": "Test Site",
            "monday": "0800-1600",
            "tuesday": "0800-1600",
            "wednesday": "0800-1600",
            "thursday": "0800-1600",
            "friday": "0800-1600",
        }, created_by="test_suite")
        sched = get_anchor_schedule(sid)
        assert sched is not None, "Created schedule not found"
        assert float(sched["total_hours"]) == 40.0, f"Hours: {sched['total_hours']}"
        delete_anchor_schedule(sid)
        ok("ops_anchor_schedules CRUD cycle (40hr week verified)")
    except Exception as e:
        fail("ops_anchor_schedules CRUD", str(e))


# ======================================================================
#  7. UNIFORMS MODULE DATA
# ======================================================================
def test_uniforms_data():
    section("7. Uniforms Module Data")

    try:
        from src.modules.uniforms.data_manager import (
            get_all_catalog, get_catalog_item,
            create_catalog_item, delete_catalog_item,
            get_all_issuances,
            get_all_kits, get_all_pending_orders,
        )
        ok("import uniforms.data_manager")
    except Exception as e:
        fail("import uniforms.data_manager", str(e))
        return

    # Catalog
    try:
        items = get_all_catalog()
        ok(f"uni_catalog -> {len(items)} items")
        if len(items) == 0:
            warn("uni_catalog empty", "No catalog items -- source data not ported?")
    except Exception as e:
        fail("get_all_catalog()", str(e))

    # Issuances
    try:
        iss = get_all_issuances()
        ok(f"uni_issuances -> {len(iss)} records")
    except Exception as e:
        fail("get_all_issuances()", str(e))

    # Kits
    try:
        kits = get_all_kits()
        ok(f"uni_kits -> {len(kits)} kits")
    except Exception as e:
        fail("get_all_kits()", str(e))

    # Pending orders
    try:
        orders = get_all_pending_orders()
        ok(f"uni_pending_orders -> {len(orders)} orders")
    except Exception as e:
        fail("get_all_pending_orders()", str(e))


# ======================================================================
#  8. ATTENDANCE MODULE DATA
# ======================================================================
def test_attendance_data():
    section("8. Attendance Module Data")

    try:
        from src.modules.attendance.data_manager import (
            get_all_infractions, get_infractions_for_employee,
            create_infraction,
            get_all_reviews, create_review,
            get_dashboard_summary,
        )
        ok("import attendance.data_manager")
    except Exception as e:
        fail("import attendance.data_manager", str(e))
        return

    try:
        infractions = get_all_infractions()
        ok(f"ats_infractions -> {len(infractions)} records")
    except Exception as e:
        fail("get_all_infractions()", str(e))

    try:
        reviews = get_all_reviews()
        ok(f"ats_employment_reviews -> {len(reviews)} records")
    except Exception as e:
        fail("get_all_reviews()", str(e))

    try:
        summary = get_dashboard_summary()
        assert isinstance(summary, dict)
        ok(f"ats dashboard_summary keys: {list(summary.keys())[:5]}...")
    except Exception as e:
        fail("ats dashboard_summary", str(e))

    # Policy engine
    try:
        from src.modules.attendance.policy_engine import (
            INFRACTION_TYPES, calculate_active_points,
            determine_discipline_level,
        )
        assert len(INFRACTION_TYPES) >= 10, f"Only {len(INFRACTION_TYPES)} types"
        ok(f"policy_engine: {len(INFRACTION_TYPES)} infraction types loaded")
    except Exception as e:
        fail("policy_engine import", str(e))


# ======================================================================
#  9. TRAINING MODULE DATA
# ======================================================================
def test_training_data():
    section("9. Training Module Data")

    try:
        from src.modules.training.data_manager import (
            get_all_courses, get_course,
            get_modules_for_course, get_chapters_for_course,
            get_test_for_chapter,
        )
        ok("import training.data_manager")
    except Exception as e:
        fail("import training.data_manager", str(e))
        return

    try:
        courses = get_all_courses()
        ok(f"trn_courses -> {len(courses)} courses")
        if len(courses) == 0:
            warn("trn_courses empty", "No training courses found")
    except Exception as e:
        fail("get_all_courses()", str(e))

    # If courses exist, verify module/chapter/test chain
    if courses:
        try:
            cid = courses[0]["course_id"]
            modules = get_modules_for_course(cid)
            ok(f"trn_modules for course -> {len(modules)}")

            chapters = get_chapters_for_course(cid)
            ok(f"trn_chapters for course -> {len(chapters)}")

            if chapters:
                ch_id = chapters[0]["chapter_id"]
                test = get_test_for_chapter(ch_id)
                if test:
                    ok(f"trn_test for chapter -> found (passing_score={test.get('passing_score', '?')})")
                else:
                    warn("trn_test for chapter", "No test found for first chapter")
        except Exception as e:
            fail("training chain (modules->chapters->tests)", str(e))


# ======================================================================
#  10. DA GENERATOR MODULE
# ======================================================================
def test_da_generator():
    section("10. DA Generator Module")

    try:
        from src.modules.da_generator.data_manager import (
            create_da, get_da, get_all_das, update_da, delete_da,
        )
        ok("import da_generator.data_manager")
    except Exception as e:
        fail("import da_generator.data_manager", str(e))
        return

    try:
        das = get_all_das()
        ok(f"da_records -> {len(das)} records")
    except Exception as e:
        fail("get_all_das()", str(e))

    # CRUD cycle
    try:
        da_id = create_da({
            "employee_name": "Test Employee",
            "site": "Test Site",
            "violation_type": "Test",
            "status": "draft",
            "current_step": 1,
        }, created_by="test_suite")
        assert da_id, "No da_id returned"

        da = get_da(da_id)
        assert da is not None, "Created DA not found"
        assert da["employee_name"] == "Test Employee"
        ok("create_da() + get_da()")

        update_da(da_id, {"notes": "test"}, updated_by="test_suite")
        ok("update_da()")

        delete_da(da_id)
        ok("delete_da()")
    except Exception as e:
        fail("DA CRUD cycle", str(e))

    # Supporting modules
    for mod in [
        "src.modules.da_generator.local_engine",
        "src.modules.da_generator.ceis_prompts",
        "src.modules.da_generator.pdf_filler",
    ]:
        try:
            __import__(mod)
            ok(f"import {mod}")
        except Exception as e:
            fail(f"import {mod}", str(e)[:100])


# ======================================================================
#  11. AUTH SYSTEM
# ======================================================================
def test_auth():
    section("11. Auth System")

    try:
        from src.auth import verify_password, create_user
        ok("import auth")
    except Exception as e:
        fail("import auth", str(e))
        return

    # Verify admin user exists in DB
    try:
        from src.database import get_conn
        conn = get_conn()
        admin = conn.execute(
            "SELECT username, role FROM users WHERE username = 'admin'"
        ).fetchone()
        conn.close()
        assert admin is not None, "No admin user found"
        ok(f"admin user exists (role={admin['role']})")
    except Exception as e:
        fail("admin user check", str(e))

    # Test password verification works (don't test wrong password — just that function runs)
    try:
        result = verify_password("admin", "wrong_password_test")
        assert result is False, "Wrong password should return False"
        ok("verify_password() works")
    except Exception as e:
        fail("verify_password()", str(e))


# ======================================================================
#  12. CSV IMPORT COMPATIBILITY (TrackTik format)
# ======================================================================
def test_csv_import():
    section("12. CSV Import Compatibility")

    # Test officer TrackTik CSV parsing
    try:
        from src.hub_people import HubPeoplePage

        # Simulate a TrackTik employee row
        row = {
            "Staffr Id": "9999",
            "Name": "Test",
            "Middle Name": "",
            "Last Name": "Employee",
            "Title": "Security Officer",
            "Hiredate": "2026-01-01",
            "Termination Date": "",
            "Phone": "317-555-0100",
            "Address": "201 N. Illinois St.",
            "Email": "test@cerasus.us",
            "Role": "Guard",
            "Gender": "",
        }
        fields = HubPeoplePage._normalize_tracktik_row(row)
        assert fields["name"] == "Test Employee", f"Name: {fields['name']}"
        assert fields["employee_id"] == "9999"
        assert fields["job_title"] == "Security Officer"
        assert fields["status"] == "Active"
        ok("TrackTik officer CSV parsing")
    except Exception as e:
        fail("TrackTik officer CSV parsing", str(e))

    # Test site TrackTik CSV parsing
    try:
        row = {
            "Company": "Test Building",
            "Address": "123 Main St",
            "Address Suite": "Suite 200",
            "City": "Indianapolis",
            "State": "IN",
            "Zip": "46204",
            "First Name": "John",
            "Last Name": "Doe",
            "Title": "Property Manager",
            "Phone Main": "317-555-0200",
            "Email": "john@test.com",
            "Status": "Active",
            "Closed Date": "",
            "Remarks": "",
        }
        fields = HubPeoplePage._normalize_tracktik_site_row(row)
        assert fields["name"] == "Test Building"
        assert fields["city"] == "Indianapolis"
        assert fields["state"] == "IN"
        assert fields["market"] == "Indianapolis"
        assert "John Doe" in fields["notes"]
        ok("TrackTik site CSV parsing")
    except Exception as e:
        fail("TrackTik site CSV parsing", str(e))


# ======================================================================
#  13. CROSS-MODULE DATA INTEGRITY
# ======================================================================
def test_cross_module_integrity():
    section("13. Cross-Module Data Integrity")

    from src.database import get_conn
    conn = get_conn()

    # Officers referenced in infractions should exist in officers table
    try:
        orphaned = conn.execute("""
            SELECT DISTINCT i.employee_id
            FROM ats_infractions i
            LEFT JOIN officers o ON o.officer_id = i.employee_id
            WHERE o.officer_id IS NULL
        """).fetchall()
        if orphaned:
            warn("infraction orphans", f"{len(orphaned)} infractions reference non-existent officers")
        else:
            ok("all infraction employee_ids exist in officers table")
    except Exception as e:
        fail("infraction FK check", str(e))

    # Officers referenced in employment reviews should exist
    try:
        orphaned = conn.execute("""
            SELECT DISTINCT r.employee_id
            FROM ats_employment_reviews r
            LEFT JOIN officers o ON o.officer_id = r.employee_id
            WHERE o.officer_id IS NULL
        """).fetchall()
        if orphaned:
            warn("review orphans", f"{len(orphaned)} reviews reference non-existent officers")
        else:
            ok("all review employee_ids exist in officers table")
    except Exception as e:
        fail("review FK check", str(e))

    # Site styles should be populated for TrackTik sites
    try:
        sites = conn.execute(
            "SELECT name, style FROM sites WHERE status = 'Active'"
        ).fetchall()
        no_style = [s[0] for s in sites if not s[1] or s[1].strip() == ""]
        if no_style:
            warn("sites missing style", f"{len(no_style)} active sites have no style: {no_style[:5]}")
        else:
            ok(f"all {len(sites)} active sites have a style set")
    except Exception as e:
        fail("site style check", str(e))

    # Uniform catalog should have items
    try:
        cnt = conn.execute("SELECT COUNT(*) FROM uni_catalog").fetchone()[0]
        if cnt >= 17:
            ok(f"uni_catalog has {cnt} items (source had 17)")
        elif cnt > 0:
            warn("uni_catalog", f"Only {cnt} items (source had 17)")
        else:
            fail("uni_catalog", "EMPTY - source data not ported")
    except Exception as e:
        fail("uni_catalog check", str(e))

    # Training course should exist
    try:
        cnt = conn.execute("SELECT COUNT(*) FROM trn_courses").fetchone()[0]
        if cnt >= 1:
            ok(f"trn_courses has {cnt} course(s)")
        else:
            warn("trn_courses", "No courses found")
    except Exception as e:
        fail("trn_courses check", str(e))

    conn.close()


# ======================================================================
#  14. DATA COUNTS (sanity check)
# ======================================================================
def test_data_counts():
    section("14. Data Counts (Sanity Check)")

    from src.database import get_conn
    conn = get_conn()

    checks = {
        "officers": (">=", 100, "Should have 100+ from TrackTik import"),
        "sites": (">=", 10, "Should have 10+ sites"),
        "ops_flex_team": (">=", 3, "Should have 3 default flex officers"),
        "ats_infractions": (">=", 1, "Should have attendance data"),
        "uni_catalog": (">=", 17, "Should have 17 uniform items from source"),
        "trn_courses": (">=", 1, "Should have at least 1 training course"),
        "trn_chapters": (">=", 1, "Should have training chapters"),
        "users": (">=", 1, "Should have at least admin user"),
    }

    for table, (op, expected, desc) in checks.items():
        try:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if op == ">=" and cnt >= expected:
                ok(f"{table}: {cnt} rows (expected {op}{expected})")
            else:
                warn(f"{table}: {cnt} rows", f"Expected {op}{expected} -- {desc}")
        except Exception as e:
            fail(f"count {table}", str(e))

    conn.close()


# ======================================================================
#  15. UI LAYOUT AUDIT (static code analysis)
# ======================================================================
def test_ui_layout_audit():
    """
    Static analysis of PySide6 source to catch visual/layout bugs
    that only show up at runtime: truncated labels, clipped badges,
    missing calendar popups, step indicator sizing, etc.
    """
    section("15. UI Layout Audit (Static)")
    import re

    SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")

    # Collect all .py files under src/
    py_files = []
    for root, dirs, files in os.walk(SRC):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    # ── Check 1: QDateEdit must have setCalendarPopup(True) ──
    date_edit_files = {}
    for fp in py_files:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        creates = len(re.findall(r"QDateEdit\s*\(", src))
        popups = len(re.findall(r"setCalendarPopup\s*\(\s*True\s*\)", src))
        if creates > 0:
            date_edit_files[fp] = (creates, popups)

    all_good = True
    for fp, (creates, popups) in date_edit_files.items():
        if creates > popups:
            fail(f"QDateEdit missing calendar popup",
                 f"{os.path.basename(fp)}: {creates} QDateEdit but only {popups} setCalendarPopup(True)")
            all_good = False
    if all_good:
        ok(f"all QDateEdit fields have setCalendarPopup(True) ({sum(v[0] for v in date_edit_files.values())} total)")

    # ── Check 2: Badge/label heights not too small ──
    tiny_height_issues = []
    for fp in py_files:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        for i, line in enumerate(lines, 1):
            m = re.search(r"setFixedHeight\((\d+)\)", line)
            if m:
                h = int(m.group(1))
                # Labels/badges under 24px with text are risky at 10-11px font
                if h < 22:
                    # Check if it's a QLabel or badge-like widget
                    context = "".join(lines[max(0, i-3):i+1])
                    if "QLabel" in context or "badge" in context.lower():
                        tiny_height_issues.append(
                            f"{os.path.basename(fp)}:{i} setFixedHeight({h}) on label/badge"
                        )
    if tiny_height_issues:
        for issue in tiny_height_issues:
            warn("tiny label height", issue)
    else:
        ok("no dangerously small label/badge heights (<22px)")

    # ── Check 3: Fixed widths under 80 on labels with multi-word text ──
    narrow_label_issues = []
    for fp in py_files:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        for i, line in enumerate(lines, 1):
            m = re.search(r"setFixedWidth\((\d+)\)", line)
            if m:
                w = int(m.group(1))
                if w < 80:
                    # Check surrounding context for QLabel with multi-word text
                    context = "".join(lines[max(0, i-5):i+1])
                    if "QLabel" in context:
                        # Look for text with spaces (multi-word)
                        text_match = re.search(r'QLabel\(["\'](.+?)["\']\)', context)
                        if text_match and " " in text_match.group(1):
                            narrow_label_issues.append(
                                f"{os.path.basename(fp)}:{i} setFixedWidth({w}) "
                                f"on label \"{text_match.group(1)}\""
                            )
    if narrow_label_issues:
        for issue in narrow_label_issues:
            warn("narrow label width", issue)
    else:
        ok("no multi-word labels with dangerously narrow fixed widths (<80px)")

    # ── Check 4: StepIndicator sizing ──
    try:
        wizard_path = os.path.join(SRC, "modules", "da_generator", "pages_wizard.py")
        with open(wizard_path, "r", encoding="utf-8") as fh:
            src = fh.read()

        # Height check
        m = re.search(r"self\.setFixedHeight\((\d+)\)", src)
        if m:
            h = int(m.group(1))
            if h >= 108:
                ok(f"StepIndicator height {h}px (sufficient for 2-line labels)")
            else:
                warn("StepIndicator height", f"{h}px — may clip bottom of 2-line step labels (need ~108+)")

        # Label width check
        m = re.search(r"lbl_w\s*=\s*(\d+)", src)
        if m:
            lbl_w = int(m.group(1))
            if lbl_w >= 110:
                ok(f"StepIndicator label width {lbl_w}px (sufficient)")
            else:
                fail("StepIndicator label width", f"{lbl_w}px — too narrow for step labels")

        # Minimum width check
        if "setMinimumWidth" in src:
            m = re.search(r"setMinimumWidth\((\d+)\)", src)
            if m:
                min_w = int(m.group(1))
                ok(f"StepIndicator has minimum width {min_w}px (prevents label overlap)")
        else:
            warn("StepIndicator min width", "No setMinimumWidth — labels may overlap on narrow windows")

    except Exception as e:
        fail("StepIndicator audit", str(e))

    # ── Check 5: CEIS local engine produces non-empty sections ──
    try:
        from src.modules.da_generator.local_engine import generate_ceis_output
        test_intake = {
            "employee_name": "Test Employee",
            "employee_position": "Security Officer",
            "site": "Test Site",
            "incident_dates": "2026-03-15",
            "incident_narrative": "Employee failed to report for scheduled shift without providing any notification.",
            "violation_type": "Type A — Attendance",
            "attendance_points_at_da": 6,
        }
        result = generate_ceis_output(test_intake)
        empty_sections = [k for k, v in result.items() if not v or len(v.strip()) < 50]
        if empty_sections:
            fail("CEIS engine output", f"Sections too short or empty: {empty_sections}")
        else:
            ok(f"CEIS engine produces 6 non-empty sections (shortest: {min(len(v) for v in result.values())} chars)")
    except Exception as e:
        fail("CEIS engine smoke test", str(e))

    # ── Check 6: tc() key validation (catches "Coming soon" page crashes) ──
    try:
        import re as _re
        from src.config import COLORS as _C, DARK_COLORS as _DC
        valid_tc_keys = set(_C.keys()) | set(_DC.keys())
        tc_issues = []
        for fp in py_files:
            with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    for m in _re.finditer(r"tc\(['\"]([^'\"]+)['\"]\)", line):
                        key = m.group(1)
                        if key not in valid_tc_keys:
                            tc_issues.append(f"{os.path.basename(fp)}:{i} tc('{key}')")
        if tc_issues:
            for issue in tc_issues:
                fail("invalid tc() key", issue)
        else:
            ok("all tc() color keys are valid")
    except Exception as e:
        fail("tc() key audit", str(e))

    # ── Check 7: Page instantiation (catches silent "Coming soon" fallbacks) ──
    try:
        from src.modules import REGISTERED_MODULES
        app_state_test = {'username': 'test', 'role': 'admin', 'assigned_sites': [], 'display_name': 'Test'}
        page_crashes = []
        for mod_id in REGISTERED_MODULES:
            mod = __import__(f"src.modules.{mod_id}", fromlist=["get_module"])
            module = mod.get_module()
            for page_cls, requires_admin in module.page_classes:
                try:
                    page = page_cls(app_state_test)
                except Exception as e:
                    page_crashes.append(f"{mod_id}.{page_cls.__name__}: {e}")
        if page_crashes:
            for crash in page_crashes:
                fail("page instantiation crash", crash)
        else:
            total_pages = sum(
                len(__import__(f"src.modules.{m}", fromlist=["get_module"]).get_module().page_classes)
                for m in REGISTERED_MODULES
            )
            ok(f"all {total_pages} pages instantiate without errors")
    except Exception as e:
        fail("page instantiation audit", str(e))

    # ── Check 8: Module sidebar count matches page_classes count ──
    try:
        from src.modules import REGISTERED_MODULES
        mismatches = []
        for mod_id in REGISTERED_MODULES:
            try:
                mod = __import__(f"src.modules.{mod_id}", fromlist=["get_module"])
                module = mod.get_module()
                sidebar_count = sum(len(items) for _, items in module.sidebar_sections)
                page_count = len(module.page_classes)
                if sidebar_count != page_count:
                    mismatches.append(
                        f"{mod_id}: sidebar={sidebar_count} vs pages={page_count}"
                    )
            except Exception:
                pass  # Import failures caught by other tests
        if mismatches:
            for mm in mismatches:
                fail("sidebar/page mismatch", mm)
        else:
            ok(f"all {len(REGISTERED_MODULES)} modules have matching sidebar/page counts")
    except Exception as e:
        fail("module sidebar/page audit", str(e))


# ======================================================================
#  MAIN
# ======================================================================
def main():
    print("\n" + "=" * 60)
    print("  CERASUS HUB -- PRE-BUILD TEST SUITE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Need QApplication for PySide6 imports to not crash
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
    except Exception:
        pass

    test_core_imports()
    test_database()
    test_fresh_db_migrations()
    test_module_imports()
    test_shared_data_crud()
    test_operations_data()
    test_uniforms_data()
    test_attendance_data()
    test_training_data()
    test_da_generator()
    test_auth()
    test_csv_import()
    test_cross_module_integrity()
    test_data_counts()
    test_ui_layout_audit()

    # Summary
    print("\n" + "=" * 60)
    print(f"  RESULTS:  {PASS} passed  |  {FAIL} failed  |  {WARN} warnings")
    print("=" * 60)

    if FAIL > 0:
        print("\n  FAILURES:")
        for status, name, detail in RESULTS:
            if status == "FAIL":
                print(f"    X  {name}  --  {detail}")
        print(f"\n  BUILD BLOCKED -- fix {FAIL} failure(s) before building.\n")
        return 1
    elif WARN > 0:
        print(f"\n  BUILD OK with {WARN} warning(s). Review above.\n")
        return 0
    else:
        print("\n  ALL CLEAR -- safe to build.\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
