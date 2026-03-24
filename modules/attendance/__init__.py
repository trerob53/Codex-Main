"""Cerasus Hub — Attendance Tracking Module (ATS) stub."""
from src.modules.base import BaseModule


class AttendanceModule(BaseModule):
    name = "Attendance"
    module_id = "attendance"
    version = "1.0"
    icon = "A"
    description = "Attendance tracking, discipline management, and infraction monitoring"
    schema_version = 1

    sidebar_sections = [
        ("OVERVIEW", [("Dashboard", ""), ("Officer Roster", ""), ("Site Dashboard", ""), ("Site Comparison", "")]),
        ("DISCIPLINE", [
            ("Log Infraction", ""),
            ("Discipline Tracker", ""),
            ("Employment Reviews", ""),
        ]),
        ("IMPORT", [("Import CSV", ""), ("Bulk Import", "")]),
        ("ADMIN", [
            ("Reports & Export", ""),
            ("Audit Trail", ""),
            ("User Management", ""),
            ("Site Management", ""),
            ("Policy Settings", ""),
        ]),
    ]

    @property
    def page_classes(self):
        try:
            from src.modules.attendance.pages_dashboard import DashboardPage
            from src.modules.attendance.pages_roster import RosterPage
            from src.pages_site_dashboard import SiteDashboardPage
            from src.pages_site_comparison import SiteComparisonPage
            from src.modules.attendance.pages_infractions import InfractionsPage
            from src.modules.attendance.pages_discipline import DisciplinePage
            from src.modules.attendance.pages_reviews import ReviewsPage
            from src.modules.attendance.pages_reports import ReportsPage
            from src.modules.attendance.pages_import import ImportInfractionsPage
            from src.modules.attendance.pages_bulk_import import BulkImportPage
            from src.modules.attendance.pages_admin import (
                AuditTrailPage, UserManagementPage, SiteManagementPage,
                PolicySettingsPage,
            )
            return [
                (DashboardPage, False), (RosterPage, False),
                (SiteDashboardPage, False),
                (SiteComparisonPage, False),
                (InfractionsPage, False), (DisciplinePage, False),
                (ReviewsPage, False),
                (ImportInfractionsPage, True),
                (BulkImportPage, False),
                (ReportsPage, False),
                (AuditTrailPage, False), (UserManagementPage, True),
                (SiteManagementPage, False),
                (PolicySettingsPage, True),
            ]
        except ImportError:
            return []

    def get_migrations(self):
        try:
            from src.modules.attendance.migrations import MIGRATIONS
            return MIGRATIONS
        except ImportError:
            return {}


def get_module():
    # Apply any saved policy threshold overrides on module load
    try:
        from src.modules.attendance.pages_admin import load_policy_overrides_on_startup
        load_policy_overrides_on_startup()
    except Exception:
        pass
    return AttendanceModule()
