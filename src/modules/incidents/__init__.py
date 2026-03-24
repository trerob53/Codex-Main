"""Cerasus Hub — Incidents Module: Security incident reporting, tracking, and resolution."""
from src.modules.base import BaseModule


class IncidentsModule(BaseModule):
    name = "Incidents"
    module_id = "incidents"
    version = "1.0"
    icon = "\u26A0"
    description = "Security incident reporting, tracking, and resolution"
    schema_version = 1

    sidebar_sections = [
        ("OVERVIEW", [
            ("Dashboard", "\u25A3"),
            ("Incident Log", "\U0001F4CB"),
        ]),
        ("MANAGEMENT", [
            ("New Report", "\u270E"),
            ("Investigation Queue", "\U0001F50D"),
        ]),
        ("ADMIN", [
            ("Reports & Export", "\u2637"),
            ("Settings", "\u2699"),
        ]),
    ]

    @property
    def page_classes(self):
        try:
            from src.modules.incidents.pages_dashboard import DashboardPage
            from src.modules.incidents.pages_incidents import (
                IncidentLogPage, NewReportPage, InvestigationPage,
            )
            from src.modules.incidents.pages_admin import ReportsPage, SettingsPage
            return [
                (DashboardPage, False),
                (IncidentLogPage, False),
                (NewReportPage, False),
                (InvestigationPage, False),
                (ReportsPage, False),
                (SettingsPage, True),
            ]
        except ImportError:
            return []

    def get_migrations(self):
        try:
            from src.modules.incidents.migrations import MIGRATIONS
            return MIGRATIONS
        except ImportError:
            return {}


def get_module():
    return IncidentsModule()
