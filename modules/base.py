"""
Cerasus Hub — Base Module ABC
Every hub module subclasses BaseModule and implements its manifest.
"""


class BaseModule:
    """Abstract base for all Cerasus Hub modules."""

    # Module identity
    name: str = ""
    module_id: str = ""
    version: str = "1.0"
    icon: str = ""
    description: str = ""

    # Sidebar sections: [("SECTION_LABEL", [("Page Name", "icon_char")])]
    sidebar_sections: list = []

    # Page classes: [(PageClass, requires_admin: bool)]
    page_classes: list = []

    # Schema migration version (integer, starts at 1)
    schema_version: int = 0

    def get_migrations(self) -> dict:
        """Return {version_int: migration_function} dict.
        Each function receives a sqlite3.Connection."""
        return {}

    def on_activate(self, app_state: dict):
        """Called when user switches to this module."""
        pass

    def on_deactivate(self):
        """Called when user leaves this module."""
        pass
