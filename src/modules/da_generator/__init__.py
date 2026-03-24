"""
Cerasus Hub -- DA Generator Module
Disciplinary Action document generator with CEIS engine.
"""

from src.modules.base import BaseModule


class DAGeneratorModule(BaseModule):
    name = "DA Generator"
    module_id = "da_generator"
    version = "1.0"
    icon = "DA"
    description = "Disciplinary Action document generator with CEIS engine"
    schema_version = 3

    sidebar_sections = [
        ("GENERATOR", [("New DA", ""), ("DA History", "")]),
        ("SETTINGS", [("Templates", ""), ("Configuration", "")]),
    ]

    @property
    def page_classes(self):
        from src.modules.da_generator.pages_wizard import DAWizardPage
        from src.modules.da_generator.pages_history import DAHistoryPage
        from src.modules.da_generator.pages_templates import DATemplatesPage
        from src.modules.da_generator.pages_settings import DASettingsPage
        return [
            (DAWizardPage, False),
            (DAHistoryPage, False),
            (DATemplatesPage, True),
            (DASettingsPage, True),
        ]

    def get_migrations(self):
        from src.modules.da_generator.migrations import MIGRATIONS
        return MIGRATIONS


def get_module():
    return DAGeneratorModule()
