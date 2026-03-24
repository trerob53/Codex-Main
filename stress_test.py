"""
Cerasus Hub — Stress Test Suite
Tests database performance, concurrent access, large data loads, and page instantiation.
"""

import sys
import os
import time
import random
import string
import threading
import traceback
from datetime import datetime, timezone, timedelta

# Setup path
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

os.environ['QT_QPA_PLATFORM'] = 'offscreen'


def _random_name():
    first = random.choice(["James", "Maria", "Robert", "Patricia", "John", "Jennifer",
                           "Michael", "Linda", "David", "Elizabeth", "William", "Barbara",
                           "Carlos", "Susan", "Thomas", "Jessica", "Charles", "Sarah"])
    last = random.choice(["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
                          "Miller", "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor",
                          "Thomas", "Hernandez", "Moore", "Martin", "Jackson", "Lee"])
    return f"{first} {last}"


def _random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase, k=length))


def _random_date(days_back=365):
    d = datetime.now() - timedelta(days=random.randint(0, days_back))
    return d.strftime("%Y-%m-%d")


class StressTest:
    def __init__(self):
        self.results = {}
        self.errors = []

    def run_all(self):
        print("=" * 60)
        print("  CERASUS HUB — STRESS TEST SUITE")
        print("=" * 60)
        print()

        # Initialize
        from src.config import ensure_directories
        from src.database import initialize_database, run_module_migrations
        from src.auth import initialize_users
        from src.modules import discover_modules

        ensure_directories()
        initialize_database()
        modules = discover_modules()
        run_module_migrations(modules)
        initialize_users()

        print(f"[OK] Database initialized, {len(modules)} modules discovered")
        print()

        # Run tests
        self._test_bulk_officer_insert()
        self._test_bulk_site_insert()
        self._test_bulk_infraction_insert()
        self._test_bulk_issuance_insert()
        self._test_bulk_incident_insert()
        self._test_bulk_labor_insert()
        self._test_concurrent_writes()
        self._test_query_performance()
        self._test_page_instantiation(modules)
        self._test_csv_export_performance()
        self._test_dashboard_performance()
        self._test_memory_usage()

        # Summary
        print()
        print("=" * 60)
        print("  RESULTS SUMMARY")
        print("=" * 60)
        for name, result in self.results.items():
            status = "PASS" if result["pass"] else "FAIL"
            print(f"  [{status}] {name}: {result['detail']}")

        if self.errors:
            print()
            print(f"  {len(self.errors)} ERROR(S):")
            for err in self.errors:
                print(f"    - {err}")

        total = len(self.results)
        passed = sum(1 for r in self.results.values() if r["pass"])
        failed = total - passed
        print()
        print(f"  Total: {total} | Passed: {passed} | Failed: {failed}")
        print("=" * 60)

        return failed == 0

    def _record(self, name, passed, detail):
        self.results[name] = {"pass": passed, "detail": detail}
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {detail}")

    def _test_bulk_officer_insert(self):
        """Insert 500 officers and measure throughput."""
        print("[TEST] Bulk Officer Insert (500 records)...")
        try:
            from src.shared_data import create_officer, get_all_officers

            start = time.time()
            for i in range(500):
                create_officer({
                    "name": _random_name(),
                    "employee_id": f"EMP-{10000 + i}",
                    "job_title": random.choice(["Security Officer", "Lead Officer", "Field Supervisor"]),
                    "site": random.choice(["Site Alpha", "Site Beta", "Site Gamma", "Site Delta", "Site Echo"]),
                    "status": "Active",
                    "hire_date": _random_date(730),
                    "email": f"officer{i}@cerasus.us",
                    "role": "Flex Officer",
                }, created_by="stress_test")
            elapsed = time.time() - start

            count = len(get_all_officers())
            rate = 500 / elapsed
            self._record("Bulk Officer Insert (500)", elapsed < 30, f"{elapsed:.2f}s ({rate:.0f} ops/sec), {count} total")
        except Exception as e:
            self._record("Bulk Officer Insert", False, str(e))
            self.errors.append(f"Officer insert: {e}")

    def _test_bulk_site_insert(self):
        """Insert 50 sites."""
        print("[TEST] Bulk Site Insert (50 records)...")
        try:
            from src.shared_data import create_site

            start = time.time()
            for i in range(50):
                create_site({
                    "name": f"Test Site {i:03d}",
                    "address": f"{random.randint(100, 9999)} Main St",
                    "city": random.choice(["Indianapolis", "Carmel", "Fishers", "Noblesville"]),
                    "state": "IN",
                    "style": random.choice(["Soft Look", "Hard Look"]),
                    "status": "Active",
                }, created_by="stress_test")
            elapsed = time.time() - start
            self._record("Bulk Site Insert (50)", elapsed < 10, f"{elapsed:.2f}s")
        except Exception as e:
            self._record("Bulk Site Insert", False, str(e))
            self.errors.append(f"Site insert: {e}")

    def _test_bulk_infraction_insert(self):
        """Insert 2000 infractions."""
        print("[TEST] Bulk Infraction Insert (2000 records)...")
        try:
            from src.modules.attendance.data_manager import create_infraction
            from src.modules.attendance.policy_engine import INFRACTION_TYPES
            from src.shared_data import get_all_officers

            officers = get_all_officers()
            if not officers:
                self._record("Bulk Infraction Insert", False, "No officers to assign")
                return

            types = list(INFRACTION_TYPES.keys())
            start = time.time()
            for i in range(2000):
                off = random.choice(officers)
                create_infraction({
                    "employee_id": off["officer_id"],
                    "infraction_type": random.choice(types),
                    "infraction_date": _random_date(365),
                    "site": off.get("site", ""),
                    "description": f"Stress test infraction {i}",
                }, entered_by="stress_test")
            elapsed = time.time() - start
            rate = 2000 / elapsed
            self._record("Bulk Infraction Insert (2000)", elapsed < 120, f"{elapsed:.2f}s ({rate:.0f} ops/sec)")
        except Exception as e:
            self._record("Bulk Infraction Insert", False, str(e))
            self.errors.append(f"Infraction insert: {e}")

    def _test_bulk_issuance_insert(self):
        """Insert 1000 uniform issuances."""
        print("[TEST] Bulk Issuance Insert (1000 records)...")
        try:
            from src.modules.uniforms.data_manager import create_issuance, seed_default_catalog, get_all_catalog
            from src.shared_data import get_all_officers

            # Seed catalog if empty
            catalog = get_all_catalog()
            if not catalog:
                seed_default_catalog()
                catalog = get_all_catalog()

            officers = get_all_officers()
            if not officers or not catalog:
                self._record("Bulk Issuance Insert", False, "No officers or catalog items")
                return

            start = time.time()
            for i in range(1000):
                off = random.choice(officers)
                item = random.choice(catalog)
                create_issuance({
                    "officer_id": off["officer_id"],
                    "officer_name": off.get("name", ""),
                    "item_id": item["item_id"],
                    "item_name": item.get("name", ""),
                    "size": random.choice(["S", "M", "L", "XL", "2XL"]),
                    "quantity": 1,
                    "condition_issued": "New",
                    "date_issued": _random_date(180),
                    "issued_by": "stress_test",
                    "location": "Cerasus HQ",
                }, "stress_test")
            elapsed = time.time() - start
            rate = 1000 / elapsed
            self._record("Bulk Issuance Insert (1000)", elapsed < 60, f"{elapsed:.2f}s ({rate:.0f} ops/sec)")
        except Exception as e:
            self._record("Bulk Issuance Insert", False, str(e))
            self.errors.append(f"Issuance insert: {e}")

    def _test_bulk_incident_insert(self):
        """Insert 500 incidents."""
        print("[TEST] Bulk Incident Insert (500 records)...")
        try:
            from src.modules.incidents.data_manager import create_incident
            from src.shared_data import get_all_officers

            officers = get_all_officers()
            types = ["Trespass", "Theft", "Vandalism", "Assault", "Medical",
                     "Fire/Alarm", "Suspicious Activity", "Policy Violation", "Other"]
            severities = ["Low", "Medium", "High", "Critical"]

            start = time.time()
            for i in range(500):
                off = random.choice(officers) if officers else {"officer_id": "", "name": "Unknown"}
                create_incident({
                    "officer_id": off["officer_id"],
                    "officer_name": off.get("name", ""),
                    "site": off.get("site", "Test Site"),
                    "incident_date": _random_date(180),
                    "incident_time": f"{random.randint(0,23):02d}:{random.randint(0,59):02d}",
                    "incident_type": random.choice(types),
                    "severity": random.choice(severities),
                    "status": random.choice(["Open", "Under Investigation", "Resolved", "Closed"]),
                    "title": f"Stress test incident {i}",
                    "description": f"Test incident description for stress testing #{i}",
                    "location_detail": random.choice(["Lobby", "Parking Lot", "Stairwell", "Perimeter"]),
                    "immediate_action": "Documented and reported",
                }, "stress_test")
            elapsed = time.time() - start
            rate = 500 / elapsed
            self._record("Bulk Incident Insert (500)", elapsed < 60, f"{elapsed:.2f}s ({rate:.0f} ops/sec)")
        except ImportError:
            self._record("Bulk Incident Insert", False, "Incidents module not found — skipped")
        except Exception as e:
            self._record("Bulk Incident Insert", False, str(e))
            self.errors.append(f"Incident insert: {e}")

    def _test_bulk_labor_insert(self):
        """Insert 1000 labor entries."""
        print("[TEST] Bulk Labor Entry Insert (1000 records)...")
        try:
            from src.modules.overtime.data_manager import create_labor_entry
            from src.shared_data import get_all_officers

            officers = get_all_officers()
            sites = ["Site Alpha", "Site Beta", "Site Gamma", "Site Delta"]

            start = time.time()
            for i in range(1000):
                off = random.choice(officers) if officers else {"officer_id": "", "name": "Unknown"}
                reg = round(random.uniform(20, 40), 1)
                ot = round(random.uniform(0, 15), 1) if random.random() > 0.5 else 0
                rate = round(random.uniform(15, 35), 2)
                create_labor_entry({
                    "officer_id": off["officer_id"],
                    "officer_name": off.get("name", ""),
                    "site": random.choice(sites),
                    "week_ending": _random_date(180),
                    "regular_hours": reg,
                    "overtime_hours": ot,
                    "total_hours": reg + ot,
                    "regular_rate": rate,
                    "overtime_rate": rate * 1.5,
                    "regular_pay": reg * rate,
                    "overtime_pay": ot * rate * 1.5,
                    "total_pay": reg * rate + ot * rate * 1.5,
                    "billable_hours": reg + ot,
                    "source": "stress_test",
                }, "stress_test")
            elapsed = time.time() - start
            rate_val = 1000 / elapsed
            self._record("Bulk Labor Entry Insert (1000)", elapsed < 60, f"{elapsed:.2f}s ({rate_val:.0f} ops/sec)")
        except ImportError:
            self._record("Bulk Labor Entry Insert", False, "Overtime module not found — skipped")
        except Exception as e:
            self._record("Bulk Labor Entry Insert", False, str(e))
            self.errors.append(f"Labor insert: {e}")

    def _test_concurrent_writes(self):
        """Test 10 concurrent write threads."""
        print("[TEST] Concurrent Writes (10 threads x 50 writes)...")
        try:
            from src.shared_data import create_officer
            errors_found = []

            def _writer(thread_id):
                try:
                    for i in range(50):
                        create_officer({
                            "name": f"Thread{thread_id}-Officer{i}",
                            "employee_id": f"T{thread_id}-{i}",
                            "status": "Active",
                        }, created_by=f"thread_{thread_id}")
                except Exception as e:
                    errors_found.append(f"Thread {thread_id}: {e}")

            start = time.time()
            threads = []
            for t in range(10):
                th = threading.Thread(target=_writer, args=(t,))
                threads.append(th)
                th.start()
            for th in threads:
                th.join(timeout=60)
            elapsed = time.time() - start

            if errors_found:
                self._record("Concurrent Writes", False, f"{len(errors_found)} errors in {elapsed:.2f}s")
                self.errors.extend(errors_found[:3])
            else:
                self._record("Concurrent Writes (10x50)", True, f"{elapsed:.2f}s, 500 writes, no conflicts")
        except Exception as e:
            self._record("Concurrent Writes", False, str(e))
            self.errors.append(f"Concurrent: {e}")

    def _test_query_performance(self):
        """Test query speed on large dataset."""
        print("[TEST] Query Performance (search, aggregation, joins)...")
        try:
            from src.shared_data import search_officers, get_all_officers
            from src.database import get_conn

            # Search test
            start = time.time()
            for _ in range(100):
                search_officers("Smith")
            search_time = time.time() - start

            # Full table scan
            start = time.time()
            for _ in range(50):
                get_all_officers()
            scan_time = time.time() - start

            # Aggregation
            start = time.time()
            conn = get_conn()
            for _ in range(100):
                conn.execute("SELECT site, COUNT(*) as c, AVG(active_points) as avg_pts FROM officers GROUP BY site").fetchall()
            conn.close()
            agg_time = time.time() - start

            detail = f"Search: {search_time:.2f}s/100, Scan: {scan_time:.2f}s/50, Agg: {agg_time:.2f}s/100"
            self._record("Query Performance", search_time < 10 and scan_time < 10, detail)
        except Exception as e:
            self._record("Query Performance", False, str(e))
            self.errors.append(f"Query perf: {e}")

    def _test_page_instantiation(self, modules):
        """Instantiate all pages and measure time."""
        print("[TEST] Page Instantiation (all modules)...")
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication(sys.argv)

            app_state = {
                "user": {"user_id": "test", "username": "admin", "role": "admin",
                         "display_name": "Admin", "email": ""},
                "dark_mode": False,
            }

            start = time.time()
            total = 0
            page_errors = []
            for mod in modules:
                for page_cls, req_admin in mod.page_classes:
                    try:
                        p = page_cls(app_state)
                        total += 1
                    except Exception as e:
                        page_errors.append(f"{mod.name}/{page_cls.__name__}: {e}")

            elapsed = time.time() - start

            if page_errors:
                self._record("Page Instantiation", False, f"{total} OK, {len(page_errors)} failed in {elapsed:.2f}s")
                self.errors.extend(page_errors[:5])
            else:
                self._record(f"Page Instantiation ({total} pages)", True, f"{elapsed:.2f}s")
        except Exception as e:
            self._record("Page Instantiation", False, str(e))
            self.errors.append(f"Page inst: {e}")

    def _test_csv_export_performance(self):
        """Test CSV export with large dataset."""
        print("[TEST] CSV Export Performance...")
        try:
            from src.modules.attendance.data_manager import export_discipline_csv, export_infractions_csv

            start = time.time()
            disc_csv = export_discipline_csv()
            inf_csv = export_infractions_csv()
            elapsed = time.time() - start

            disc_lines = disc_csv.count('\n') if disc_csv else 0
            inf_lines = inf_csv.count('\n') if inf_csv else 0
            self._record("CSV Export", elapsed < 10, f"{elapsed:.2f}s — discipline: {disc_lines} rows, infractions: {inf_lines} rows")
        except Exception as e:
            self._record("CSV Export", False, str(e))
            self.errors.append(f"CSV export: {e}")

    def _test_dashboard_performance(self):
        """Test dashboard summary generation speed."""
        print("[TEST] Dashboard Summary Performance...")
        try:
            from src.modules.attendance.data_manager import get_dashboard_summary

            start = time.time()
            for _ in range(20):
                summary = get_dashboard_summary()
            elapsed = time.time() - start

            keys = list(summary.keys())
            self._record("Dashboard Summary (20x)", elapsed < 15, f"{elapsed:.2f}s — keys: {', '.join(keys[:5])}...")
        except Exception as e:
            self._record("Dashboard Summary", False, str(e))
            self.errors.append(f"Dashboard: {e}")

    def _test_memory_usage(self):
        """Check database file size after stress test."""
        print("[TEST] Database Size Check...")
        try:
            from src.config import DB_FILE
            size_bytes = os.path.getsize(DB_FILE)
            size_mb = size_bytes / (1024 * 1024)
            self._record("Database Size", size_mb < 500, f"{size_mb:.1f} MB")
        except Exception as e:
            self._record("Database Size", False, str(e))


if __name__ == "__main__":
    test = StressTest()
    success = test.run_all()
    sys.exit(0 if success else 1)
