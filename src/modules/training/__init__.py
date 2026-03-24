"""Cerasus Hub — Training / E-Learning Module."""
from src.modules.base import BaseModule


class TrainingModule(BaseModule):
    name = "Training"
    module_id = "training"
    version = "1.0"
    icon = "\U0001F393"
    description = "Employee training, e-learning courses, quizzes, and certification tracking"
    schema_version = 1

    sidebar_sections = [
        ("LEARNING", [
            ("Dashboard", ""),
            ("My Courses", ""),
            ("Leaderboard", ""),
            ("Certificates", ""),
            ("My Profile", ""),
        ]),
        ("ADMIN", [
            ("Manage Courses", ""),
            ("Manage Simulations", ""),
            ("Reports", ""),
        ]),
    ]

    @property
    def page_classes(self):
        return []

    def get_migrations(self):
        try:
            from src.modules.training.migrations import MIGRATIONS
            return MIGRATIONS
        except ImportError:
            return {}


def get_module():
    return TrainingModule()
