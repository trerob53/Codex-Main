"""Cerasus Hub — DLS & Overtime Analysis Module."""
from src.modules.base import BaseModule


class OvertimeModule(BaseModule):
    name = "DLS & Overtime"
    module_id = "overtime"
    version = "1.0"
    icon = "\u23F1"
    description = "Direct labor spend analysis, overtime tracking, and staffing coverage"
    schema_version = 1

    sidebar_sections = [
        ("OVERVIEW", [
            ("Dashboard", "\u25A3"),
            ("Weekly Summary", "\U0001F4C5"),
        ]),
        ("ANALYSIS", [
            ("By Site", "\U0001F3E2"),
            ("By Officer", "\U0001F464"),
            ("Overtime Alerts", "\u26A0"),
        ]),
        ("ADMIN", [
            ("Import Data", "\U0001F4E5"),
            ("Reports & Export", "\u2637"),
        ]),
    ]

    @property
    def page_classes(self):
        try:
            from src.modules.overtime.pages_dashboard import DashboardPage
            from src.modules.overtime.pages_analysis import (
                WeeklySummaryPage, BySitePage, ByOfficerPage, OvertimeAlertsPage,
            )
            from src.modules.overtime.pages_admin import ImportDataPage, ReportsPage
            return [
                (DashboardPage, False),
                (WeeklySummaryPage, False),
                (BySitePage, False),
                (ByOfficerPage, False),
                (OvertimeAlertsPage, False),
                (ImportDataPage, True),
                (ReportsPage, True),
            ]
        except ImportError:
            return []

    def get_migrations(self):
        try:
            from src.modules.overtime.migrations import MIGRATIONS
            return MIGRATIONS
        except ImportError:
            return {}


def get_module():
    return OvertimeModule()
