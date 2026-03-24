"""Cerasus Hub — Operations Module (Flex Control Tower)."""
from src.modules.base import BaseModule


class OperationsModule(BaseModule):
    name = "Operations"
    module_id = "operations"
    version = "4.0"
    icon = "O"
    description = "Flex Control Tower — dispatch, scheduling, PTO coverage, and flex officer management"
    schema_version = 8

    sidebar_sections = [
        ("OVERVIEW", [("Dashboard", "")]),
        ("DISPATCH", [
            ("Flex Board", ""),
            ("Open Requests", ""),
            ("Coverage Map", ""),
            ("Open Positions", ""),
            ("PTO & Coverage", ""),
        ]),
        ("SCHEDULING", [
            ("Anchor Schedules", ""),
            ("Weekly View", ""),
        ]),
        ("MANAGEMENT", [
            ("Officers", ""),
            ("Sites", ""),
            ("Handoff Notes", ""),
        ]),
        ("ADMIN", [
            ("Reports", ""),
            ("Audit Log", ""),
            ("Settings", ""),
        ]),
    ]

    @property
    def page_classes(self):
        try:
            from src.modules.operations.pages_dashboard import DashboardPage
            from src.modules.operations.pages_flex_board import FlexBoardPage
            from src.modules.operations.pages_open_requests import OpenRequestsPage
            from src.modules.operations.pages_coverage_map import CoverageMapPage
            from src.modules.operations.pages_positions import OpenPositionsPage
            from src.modules.operations.pages_ops import (
                OfficersPage, SitesPage, WeeklyScheduleGrid,
            )
            from src.modules.operations.pages_pto import PTOCoveragePage
            from src.modules.operations.pages_anchor_schedules import AnchorSchedulesPage
            from src.modules.operations.pages_admin import (
                ReportsPage, AuditLogPage, SettingsPage,
            )
            from src.modules.operations.pages_handoff import HandoffNotesPage
            return [
                (DashboardPage, False),       # Dashboard
                (FlexBoardPage, False),        # Flex Board
                (OpenRequestsPage, False),     # Open Requests
                (CoverageMapPage, False),      # Coverage Map
                (OpenPositionsPage, False),    # Open Positions
                (PTOCoveragePage, False),      # PTO & Coverage
                (AnchorSchedulesPage, False),  # Anchor Schedules
                (WeeklyScheduleGrid, False),   # Weekly View
                (OfficersPage, False),         # Officers
                (SitesPage, False),            # Sites
                (HandoffNotesPage, False),     # Handoff Notes
                (ReportsPage, False),          # Reports
                (AuditLogPage, False),         # Audit Log
                (SettingsPage, False),         # Settings
            ]
        except ImportError as e:
            print(f"[Operations] Page import error: {e}")
            return []

    def get_migrations(self):
        try:
            from src.modules.operations.migrations import MIGRATIONS
            return MIGRATIONS
        except ImportError:
            return {}


def get_module():
    return OperationsModule()
