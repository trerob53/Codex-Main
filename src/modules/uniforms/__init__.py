"""Cerasus Hub — Uniforms Management Module."""
from src.modules.base import BaseModule


class UniformsModule(BaseModule):
    name = "Uniforms"
    module_id = "uniforms"
    version = "1.0"
    icon = "\U0001F455"
    description = "Uniform issuance, inventory tracking, compliance, and cost analytics"
    schema_version = 1

    sidebar_sections = [
        ("OVERVIEW", [("Dashboard", ""), ("Cost Analytics", "")]),
        ("PERSONNEL", [("Officers", ""), ("Sites", "")]),
        ("UNIFORMS", [
            ("Issue Items", ""),
            ("Process Return", ""),
            ("All Issuances", ""),
            ("Pending Orders", ""),
        ]),
        ("INVENTORY", [
            ("Stock", ""),
            ("Compliance", ""),
            ("Replacements", ""),
        ]),
        ("ADMIN", [
            ("Reports", ""),
            ("Audit Log", ""),
            ("Notifications", ""),
            ("Settings", ""),
        ]),
    ]

    @property
    def page_classes(self):
        return []

    def get_migrations(self):
        try:
            from src.modules.uniforms.migrations import MIGRATIONS
            return MIGRATIONS
        except ImportError:
            return {}


def get_module():
    return UniformsModule()
