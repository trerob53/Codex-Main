"""
Deep Runtime Validation — CerasusHub
Exercises code paths headlessly: imports, sidebar/page consistency,
CEIS engine, data_managers, source checks, and widget dimensions.
"""

import sys
import os
import traceback

# ── Setup paths ────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Must have a QApplication for any QWidget import to work
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

# ── Counters ───────────────────────────────────────────────────────────
PASS = 0
FAIL = 0
FAILURES = []

def ok(tag, msg=""):
    global PASS
    PASS += 1
    print(f"  [PASS] {tag} {msg}")

def fail(tag, msg):
    global FAIL
    FAIL += 1
    FAILURES.append(f"{tag}: {msg}")
    print(f"  [FAIL] {tag} — {msg}")


# ======================================================================
#  1. Import every module and page class
# ======================================================================
print("\n" + "=" * 72)
print("1. IMPORT EVERY MODULE AND PAGE CLASS")
print("=" * 72)

MODULE_PACKAGES = [
    "attendance", "da_generator", "incidents",
    "operations", "overtime", "training", "uniforms",
]

modules_loaded = {}

for pkg in MODULE_PACKAGES:
    mod_path = f"src.modules.{pkg}"
    try:
        mod = __import__(mod_path, fromlist=["get_module"])
        module_obj = mod.get_module()
        modules_loaded[pkg] = module_obj
        ok(f"import:{pkg}", f"loaded {module_obj.name}")
    except Exception as e:
        fail(f"import:{pkg}", f"{type(e).__name__}: {e}")
        continue

    # Try page_classes property
    try:
        pages = module_obj.page_classes
        if not pages:
            fail(f"pages:{pkg}", "page_classes returned empty list")
        else:
            for cls, _admin in pages:
                ok(f"page:{pkg}/{cls.__name__}")
    except Exception as e:
        fail(f"pages:{pkg}", f"{type(e).__name__}: {e}")

# Also import key shared modules
SHARED_IMPORTS = [
    "src.config", "src.database", "src.auth", "src.audit",
    "src.hub_gui", "src.hub_people", "src.hub_analytics",
    "src.hub_audit_viewer", "src.hub_backups", "src.shared_widgets",
    "src.search_engine", "src.permissions", "src.shared_data",
    "src.officer_360", "src.officer_profile", "src.form_validation",
    "src.report_builder", "src.report_generator", "src.notifications",
    "src.notification_ui", "src.loading_overlay", "src.pdf_export",
    "src.print_helper", "src.backup_manager", "src.lock_manager",
    "src.session_manager", "src.announcements", "src.web_companion",
    "src.pages_activity_feed", "src.pages_site_comparison",
    "src.pages_site_dashboard", "src.pages_task_queue",
    "src.analytics_engine", "src.scheduled_reports",
    "src.change_password_dialog", "src.custom_fields",
    "src.user_management", "src.document_vault", "src.executive_report",
    "src.db_tools",
]
for mod_name in SHARED_IMPORTS:
    try:
        __import__(mod_name)
        ok(f"import:{mod_name}")
    except Exception as e:
        fail(f"import:{mod_name}", f"{type(e).__name__}: {e}")


# ======================================================================
#  2. Verify sidebar_sections page count matches page_classes count
# ======================================================================
print("\n" + "=" * 72)
print("2. SIDEBAR-SECTIONS vs PAGE-CLASSES COUNT")
print("=" * 72)

for pkg, module_obj in modules_loaded.items():
    sidebar_page_count = sum(
        len(pages) for _section_name, pages in module_obj.sidebar_sections
    )
    try:
        pc = module_obj.page_classes
        page_count = len(pc)
    except Exception as e:
        fail(f"sidebar:{pkg}", f"page_classes error: {e}")
        continue

    if sidebar_page_count == page_count:
        ok(f"sidebar:{pkg}", f"sidebar={sidebar_page_count}  pages={page_count}")
    else:
        fail(f"sidebar:{pkg}",
             f"MISMATCH sidebar={sidebar_page_count} vs pages={page_count}")


# ======================================================================
#  3. Instantiate local CEIS engine with sample data — 3 violation types
# ======================================================================
print("\n" + "=" * 72)
print("3. CEIS ENGINE — 3 violation types, 6 sections each")
print("=" * 72)

from src.modules.da_generator.local_engine import generate_ceis_output

CEIS_REQUIRED_KEYS = [
    "narrative", "citations", "violation_analysis",
    "discipline_determination", "risk_assessment", "recommendation",
]

test_cases = {
    "Type A (attendance, 6 pts)": {
        "employee_name": "John Smith",
        "employee_position": "Security Officer",
        "site": "Acme Tower",
        "security_director": "Jane Doe",
        "incident_dates": "2026-03-15",
        "incident_narrative": (
            "On March 15, 2026, at approximately 0630 hours, Officer Smith failed to report "
            "for his scheduled shift at Acme Tower. No call was made to the operations center. "
            "This constitutes a no call/no show. Officer Smith has accumulated 6 attendance points."
        ),
        "violation_type": "Type A — Attendance/Punctuality",
        "attendance_points_at_da": 6,
        "prior_verbal_same": 1,
        "prior_written_same": 1,
        "prior_final_same": 0,
        "coaching_occurred": 0,
    },
    "Type B (conduct, prior verbal)": {
        "employee_name": "Maria Garcia",
        "employee_position": "Security Officer",
        "site": "Downtown Plaza",
        "security_director": "Robert Jones",
        "incident_dates": "2026-03-10",
        "incident_narrative": (
            "On March 10, 2026, Officer Garcia was observed using profane language toward "
            "a visitor in the lobby at approximately 1430 hours. The visitor filed a complaint. "
            "The supervisor on duty witnessed the exchange."
        ),
        "violation_type": "Type B — Performance/Conduct",
        "prior_verbal_same": 1,
        "prior_written_same": 0,
        "prior_final_same": 0,
        "coaching_occurred": 1,
        "coaching_date": "2026-02-20",
        "coaching_content": "Discussed professional communication standards",
        "coaching_outcome": "Employee acknowledged expectations",
    },
    "Type C (employment review, prior final)": {
        "employee_name": "David Lee",
        "employee_position": "Site Supervisor",
        "site": "Industrial Park",
        "security_director": "Sarah Williams",
        "incident_dates": "2026-03-18",
        "incident_narrative": (
            "On March 18, 2026, Site Supervisor Lee abandoned his post during a scheduled shift "
            "without authorization. This is part of an ongoing pattern of performance issues."
        ),
        "violation_type": "Type C — Employment Review",
        "prior_verbal_same": 1,
        "prior_written_same": 1,
        "prior_final_same": 1,
        "coaching_occurred": 1,
        "coaching_date": "2026-01-15",
        "coaching_content": "Formal coaching on job responsibilities and attendance",
        "coaching_outcome": "Employee signed acknowledgment",
    },
}

for label, intake in test_cases.items():
    try:
        result = generate_ceis_output(intake)
        for key in CEIS_REQUIRED_KEYS:
            val = result.get(key, "")
            if val and len(str(val).strip()) > 0:
                ok(f"ceis:{label}/{key}", f"({len(str(val))} chars)")
            else:
                fail(f"ceis:{label}/{key}", "Section is EMPTY")
    except Exception as e:
        fail(f"ceis:{label}", f"EXCEPTION: {type(e).__name__}: {e}\n{traceback.format_exc()}")


# ======================================================================
#  4. Verify every data_manager function can be called without crashing
# ======================================================================
print("\n" + "=" * 72)
print("4. DATA-MANAGER FUNCTION SMOKE TESTS")
print("=" * 72)

# First ensure the database is initialized
from src.database import initialize_database, run_module_migrations
initialize_database()
run_module_migrations(list(modules_loaded.values()))

# -- da_generator data_manager --
print("\n  --- da_generator ---")
from src.modules.da_generator import data_manager as da_dm

da_smoke_calls = {
    "get_all_das": lambda: da_dm.get_all_das(),
    "get_all_das(filtered)": lambda: da_dm.get_all_das("draft"),
    "get_da_summary": lambda: da_dm.get_da_summary(),
    "get_da_turnaround_stats": lambda: da_dm.get_da_turnaround_stats(),
    "get_pending_acknowledgments": lambda: da_dm.get_pending_acknowledgments(),
    "get_das_for_employee": lambda: da_dm.get_das_for_employee("test_nonexist"),
    "get_das_for_officer_id": lambda: da_dm.get_das_for_officer_id("OFF-000"),
    "get_setting": lambda: da_dm.get_setting("test_nonexist_key"),
    "create+get+update+delete DA": lambda: _da_crud_smoke(),
}

def _da_crud_smoke():
    da_id = da_dm.create_da({
        "employee_name": "Test Employee",
        "violation_type": "Type B — Performance/Conduct",
    }, created_by="validation_script")
    assert da_id, "create_da returned falsy"
    rec = da_dm.get_da(da_id)
    assert rec, "get_da returned None"
    assert rec["employee_name"] == "Test Employee"
    ok_upd = da_dm.update_da(da_id, {"site": "Test Site"}, updated_by="validation_script")
    assert ok_upd, "update_da returned False"
    ok_status = da_dm.update_da_status(da_id, "delivered", updated_by="validation_script")
    assert ok_status, "update_da_status returned False"
    ok_ack = da_dm.acknowledge_da(da_id, "validator", "Acknowledged")
    assert ok_ack, "acknowledge_da returned False"
    ok_wit = da_dm.witness_sign_da(da_id, "Witness Person")
    assert ok_wit, "witness_sign_da returned False"
    ok_del = da_dm.delete_da(da_id)
    assert ok_del, "delete_da returned False"
    return "CRUD cycle OK"

for name, fn in da_smoke_calls.items():
    try:
        result = fn()
        ok(f"da_dm:{name}")
    except Exception as e:
        fail(f"da_dm:{name}", f"{type(e).__name__}: {e}")

# -- attendance data_manager --
print("\n  --- attendance ---")
from src.modules.attendance import data_manager as att_dm

att_smoke_calls = {
    "get_all_infractions": lambda: att_dm.get_all_infractions(),
    "get_dashboard_summary": lambda: att_dm.get_dashboard_summary(),
    "get_infractions_this_month": lambda: att_dm.get_infractions_this_month(),
    "get_monthly_infraction_counts": lambda: att_dm.get_monthly_infraction_counts(),
    "get_current_month_by_type": lambda: att_dm.get_current_month_by_type(),
    "get_site_attendance_summary": lambda: att_dm.get_site_attendance_summary(),
    "get_all_reviews": lambda: att_dm.get_all_reviews(),
    "export_discipline_csv": lambda: att_dm.export_discipline_csv(),
    "export_infractions_csv": lambda: att_dm.export_infractions_csv(),
    "export_reviews_csv": lambda: att_dm.export_reviews_csv(),
}
for name, fn in att_smoke_calls.items():
    try:
        fn()
        ok(f"att_dm:{name}")
    except Exception as e:
        fail(f"att_dm:{name}", f"{type(e).__name__}: {e}")

# -- incidents data_manager --
print("\n  --- incidents ---")
from src.modules.incidents import data_manager as inc_dm

inc_smoke_calls = {
    "get_all_incidents": lambda: inc_dm.get_all_incidents(),
    "search_incidents": lambda: inc_dm.search_incidents("test"),
    "get_dashboard_summary": lambda: inc_dm.get_dashboard_summary(),
    "get_investigation_queue": lambda: inc_dm.get_investigation_queue(),
    "get_incidents_by_status": lambda: inc_dm.get_incidents_by_status("Open"),
    "get_incidents_by_site": lambda: inc_dm.get_incidents_by_site("Acme"),
    "export_incidents_csv": lambda: inc_dm.export_incidents_csv(),
}
for name, fn in inc_smoke_calls.items():
    try:
        fn()
        ok(f"inc_dm:{name}")
    except Exception as e:
        fail(f"inc_dm:{name}", f"{type(e).__name__}: {e}")

# -- operations data_manager --
print("\n  --- operations ---")
from src.modules.operations import data_manager as ops_dm

ops_smoke_calls = {
    "get_active_sites": lambda: ops_dm.get_active_sites(),
    "get_ops_officers": lambda: ops_dm.get_ops_officers(),
    "get_ops_officer_names": lambda: ops_dm.get_ops_officer_names(),
    "get_all_records": lambda: ops_dm.get_all_records(),
    "get_summary": lambda: ops_dm.get_summary(),
    "get_all_assignments": lambda: ops_dm.get_all_assignments(),
    "get_all_pto": lambda: ops_dm.get_all_pto(),
    "get_dashboard_summary": lambda: ops_dm.get_dashboard_summary(),
    "get_all_anchor_schedules": lambda: ops_dm.get_all_anchor_schedules(),
}
for name, fn in ops_smoke_calls.items():
    try:
        fn()
        ok(f"ops_dm:{name}")
    except Exception as e:
        fail(f"ops_dm:{name}", f"{type(e).__name__}: {e}")

# -- overtime data_manager --
print("\n  --- overtime ---")
from src.modules.overtime import data_manager as ot_dm

ot_smoke_calls = {
    "get_all_entries": lambda: ot_dm.get_all_entries(),
    "get_current_week_ending": lambda: ot_dm.get_current_week_ending(),
    "get_dashboard_summary": lambda: ot_dm.get_dashboard_summary(),
    "get_overtime_alerts": lambda: ot_dm.get_overtime_alerts(),
    "get_site_budgets": lambda: ot_dm.get_site_budgets(),
    "export_labor_csv": lambda: ot_dm.export_labor_csv(),
}
for name, fn in ot_smoke_calls.items():
    try:
        fn()
        ok(f"ot_dm:{name}")
    except Exception as e:
        fail(f"ot_dm:{name}", f"{type(e).__name__}: {e}")

# -- training data_manager --
print("\n  --- training ---")
from src.modules.training import data_manager as trn_dm

trn_smoke_calls = {
    "get_all_courses": lambda: trn_dm.get_all_courses(),
    "get_all_certificates": lambda: trn_dm.get_all_certificates(),
    "get_leaderboard": lambda: trn_dm.get_leaderboard(),
    "get_completion_by_site": lambda: trn_dm.get_completion_by_site(),
    "get_officer_progress_report": lambda: trn_dm.get_officer_progress_report(),
}
for name, fn in trn_smoke_calls.items():
    try:
        fn()
        ok(f"trn_dm:{name}")
    except Exception as e:
        fail(f"trn_dm:{name}", f"{type(e).__name__}: {e}")

# -- uniforms data_manager --
print("\n  --- uniforms ---")
from src.modules.uniforms import data_manager as uni_dm

uni_smoke_calls = {
    "get_all_officers_parsed": lambda: uni_dm.get_all_officers_parsed(),
    "get_active_officers_parsed": lambda: uni_dm.get_active_officers_parsed(),
    "get_all_site_names": lambda: uni_dm.get_all_site_names(),
    "get_all_managed_sites": lambda: uni_dm.get_all_managed_sites(),
    "get_all_catalog": lambda: uni_dm.get_all_catalog(),
    "get_all_issuances": lambda: uni_dm.get_all_issuances(),
    "get_dashboard_summary": lambda: uni_dm.get_dashboard_summary(),
    "get_low_stock_items": lambda: uni_dm.get_low_stock_items(),
    "get_requirements": lambda: uni_dm.get_requirements(),
    "get_all_kits": lambda: uni_dm.get_all_kits(),
    "get_all_pending_orders": lambda: uni_dm.get_all_pending_orders(),
    "get_pending_order_count": lambda: uni_dm.get_pending_order_count(),
    "get_compliance_report": lambda: uni_dm.get_compliance_report(),
    "get_cost_analytics": lambda: uni_dm.get_cost_analytics(),
    "get_replacement_schedule": lambda: uni_dm.get_replacement_schedule(),
    "get_location_inventory_summary": lambda: uni_dm.get_location_inventory_summary(),
    "get_monthly_issuance_trends": lambda: uni_dm.get_monthly_issuance_trends(),
    "get_cost_breakdown_by_category": lambda: uni_dm.get_cost_breakdown_by_category(),
    "get_cost_breakdown_by_officer": lambda: uni_dm.get_cost_breakdown_by_officer(),
    "get_cost_breakdown_by_site": lambda: uni_dm.get_cost_breakdown_by_site(),
    "get_location_comparison": lambda: uni_dm.get_location_comparison(),
    "get_all_requirements": lambda: uni_dm.get_all_requirements(),
    "get_compliance_summary": lambda: uni_dm.get_compliance_summary(),
    "export_collection_csv(catalog)": lambda: uni_dm.export_collection_csv("catalog"),
    "export_collection_csv(issuances)": lambda: uni_dm.export_collection_csv("issuances"),
    "export_compliance_csv": lambda: uni_dm.export_compliance_csv(),
    "export_outstanding_csv": lambda: uni_dm.export_outstanding_csv(),
}
for name, fn in uni_smoke_calls.items():
    try:
        fn()
        ok(f"uni_dm:{name}")
    except Exception as e:
        fail(f"uni_dm:{name}", f"{type(e).__name__}: {e}")


# ======================================================================
#  5. Check QDateEdit fields have setCalendarPopup(True)
# ======================================================================
print("\n" + "=" * 72)
print("5. QDateEdit calendarPopup SOURCE CHECK")
print("=" * 72)

wizard_path = os.path.join(
    PROJECT_ROOT, "src", "modules", "da_generator", "pages_wizard.py"
)
with open(wizard_path, "r", encoding="utf-8") as f:
    wizard_lines = f.readlines()

# Find all QDateEdit() constructions and verify next non-blank line has setCalendarPopup(True)
import re

date_edit_vars = []
for i, line in enumerate(wizard_lines):
    m = re.search(r'(self\.\w+)\s*=\s*QDateEdit\(\)', line)
    if m:
        var_name = m.group(1)
        date_edit_vars.append(var_name)
        # Search the next 3 lines for setCalendarPopup(True)
        found_popup = False
        for j in range(i + 1, min(i + 4, len(wizard_lines))):
            if f"{var_name}.setCalendarPopup(True)" in wizard_lines[j]:
                found_popup = True
                break
        if found_popup:
            ok(f"calendarPopup:{var_name}", f"line {i+1}")
        else:
            fail(f"calendarPopup:{var_name}",
                 f"line {i+1}: QDateEdit created WITHOUT setCalendarPopup(True)")


# ======================================================================
#  6. Step indicator widget dimensions
# ======================================================================
print("\n" + "=" * 72)
print("6. STEP INDICATOR WIDGET DIMENSIONS")
print("=" * 72)

from src.modules.da_generator.pages_wizard import StepIndicator, STEP_LABELS

si = StepIndicator()

# Check height
fixed_h = si.height()
if fixed_h >= 90:
    ok(f"step_indicator:height", f"{fixed_h}px >= 90")
else:
    fail(f"step_indicator:height", f"{fixed_h}px < 90 (minimum required)")

# Check label width from source — we know lbl_w = 120 from reading the paintEvent
# Parse it from source to verify
found_lbl_w = None
for line in wizard_lines:
    m = re.search(r'lbl_w\s*=\s*(\d+)', line)
    if m:
        found_lbl_w = int(m.group(1))
        break

if found_lbl_w is not None:
    if found_lbl_w >= 110:
        ok(f"step_indicator:label_width", f"lbl_w={found_lbl_w}px >= 110")
    else:
        fail(f"step_indicator:label_width",
             f"lbl_w={found_lbl_w}px < 110 (minimum required)")
else:
    fail("step_indicator:label_width", "Could not find lbl_w in paintEvent source")

# Check step count matches STEP_LABELS
if len(STEP_LABELS) == 5:
    ok("step_indicator:step_count", f"{len(STEP_LABELS)} steps")
else:
    fail("step_indicator:step_count", f"Expected 5, got {len(STEP_LABELS)}")

# Exercise set_step for each valid step
for i in range(len(STEP_LABELS)):
    try:
        si.set_step(i)
        ok(f"step_indicator:set_step({i})")
    except Exception as e:
        fail(f"step_indicator:set_step({i})", str(e))


# ======================================================================
#  7. _professionalize_narrative() and _detect_additional_citations()
# ======================================================================
print("\n" + "=" * 72)
print("7. LOCAL ENGINE HELPER FUNCTION TESTS")
print("=" * 72)

from src.modules.da_generator.local_engine import (
    _professionalize_narrative, _detect_additional_citations,
)

# --- _professionalize_narrative tests ---
prof_tests = {
    "empty string": {
        "input": ("", "John"),
        "check": lambda r: r == "",
    },
    "lowercase first char": {
        "input": ("the officer was late.", "John Smith"),
        "check": lambda r: r[0].isupper(),
    },
    "first-person replacement": {
        "input": ("I observed the employee arriving late at 0700", "Jane Doe"),
        "check": lambda r: "It was observed that" in r and "I observed" not in r,
    },
    "employee name substitution": {
        "input": ("The officer was sleeping on duty", "Mike Brown"),
        "check": lambda r: "Mike Brown" in r and "The officer" not in r,
    },
    "adds period at end": {
        "input": ("Officer was tardy", "Employee X"),
        "check": lambda r: r.endswith("."),
    },
    "keeps existing punctuation": {
        "input": ("Officer was tardy!", "Employee X"),
        "check": lambda r: r.endswith("!"),
    },
    "he/she replacement": {
        "input": ("He was found sleeping on post at 0300 hours", "James Wilson"),
        "check": lambda r: "the employee was" in r.lower(),
    },
}

for label, test in prof_tests.items():
    try:
        result = _professionalize_narrative(*test["input"])
        if test["check"](result):
            ok(f"professionalize:{label}")
        else:
            fail(f"professionalize:{label}", f"Check failed. Got: '{result}'")
    except Exception as e:
        fail(f"professionalize:{label}", f"{type(e).__name__}: {e}")

# --- _detect_additional_citations tests ---
citation_tests = {
    "Type A - no call/no show": {
        "input": ("Employee was a no call no show on March 15", "Type A — Attendance"),
        "expect_contains": "3.7",
    },
    "Type A - call off": {
        "input": ("Employee called off with insufficient notice", "Type A — Attendance"),
        "expect_contains": "3.6",
    },
    "Type B - insubordination": {
        "input": ("The officer refused a direct order from the supervisor", "Type B — Conduct"),
        "expect_contains": "4.3",
    },
    "Type B - post abandonment": {
        "input": ("The officer abandoned his post without relief", "Type B — Conduct"),
        "expect_contains": "4.5",
    },
    "Type B - uniform": {
        "input": ("The officer was out of uniform during inspection", "Type B — Conduct"),
        "expect_contains": "6.1",
    },
    "Type B - use of force": {
        "input": ("The officer grabbed a trespasser by the arm", "Type B — Conduct"),
        "expect_contains": "5.1",
    },
    "Type B - workplace conduct (profanity)": {
        "input": ("Officer used profane language toward a client", "Type B — Conduct"),
        "expect_contains": "4.2",
    },
    "Type A - no false positive on conduct": {
        "input": ("Employee was tardy by 15 minutes", "Type A — Attendance"),
        "expect_empty": True,
    },
    "Type B - no false positive on clean narrative": {
        "input": ("Employee completed the shift without incident", "Type B — Conduct"),
        "expect_empty": True,
    },
}

for label, test in citation_tests.items():
    try:
        result = _detect_additional_citations(*test["input"])
        if test.get("expect_empty"):
            if len(result) == 0:
                ok(f"citations:{label}")
            else:
                fail(f"citations:{label}", f"Expected empty, got: {result}")
        else:
            section = test["expect_contains"]
            if any(section in c for c in result):
                ok(f"citations:{label}", f"found {section}")
            else:
                fail(f"citations:{label}",
                     f"Expected section {section} in citations. Got: {result}")
    except Exception as e:
        fail(f"citations:{label}", f"{type(e).__name__}: {e}")


# ======================================================================
#  FINAL REPORT
# ======================================================================
print("\n" + "=" * 72)
print(f"FINAL RESULTS:  {PASS} passed,  {FAIL} failed")
print("=" * 72)

if FAILURES:
    print("\nFAILURES:")
    for i, f_msg in enumerate(FAILURES, 1):
        print(f"  {i}. {f_msg}")
else:
    print("\nAll tests passed!")

sys.exit(1 if FAIL else 0)
