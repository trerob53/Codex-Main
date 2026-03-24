"""
Cerasus Hub -- Attendance Module: Discipline Tracker Page
Officers grouped by discipline level with expandable sections.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, tc, _is_dark, btn_style
from src.modules.attendance import data_manager


# ════════════════════════════════════════════════════════════════════════
# Collapsible Section
# ════════════════════════════════════════════════════════════════════════

class CollapsibleSection(QWidget):
    """Expandable section with header button and content area."""

    def __init__(self, title, color, count=0, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._color = color

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header button
        self.header_btn = QPushButton(f"  {title}  ({count})")
        self.header_btn.setFixedHeight(44)
        self.header_btn.setCursor(Qt.PointingHandCursor)
        self.header_btn.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self._update_header_style()
        self.header_btn.clicked.connect(self.toggle)
        layout.addWidget(self.header_btn)

        # Content area
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(6)
        layout.addWidget(self.content)

    def update_count(self, title, count):
        self.header_btn.setText(f"  {title}  ({count})")

    def toggle(self):
        self._expanded = not self._expanded
        self.content.setVisible(self._expanded)
        self._update_header_style()

    def _update_header_style(self):
        arrow = "v" if self._expanded else ">"
        self.header_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._color}; color: white;
                text-align: left; padding-left: 12px;
                border: none; border-radius: 6px;
                font-size: 14px; font-weight: 700;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)

    def clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()


# ════════════════════════════════════════════════════════════════════════
# Officer Card (inside a section)
# ════════════════════════════════════════════════════════════════════════

def _make_officer_card(off):
    """Create a small card widget for an officer in the discipline section."""
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background: {tc('card')}; border: 1px solid {tc('border')};
            border-radius: 6px; padding: 8px;
        }}
    """)
    row = QHBoxLayout(card)
    row.setContentsMargins(12, 8, 12, 8)
    row.setSpacing(12)

    # Name
    name_lbl = QLabel(off.get("name", "Unknown"))
    name_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
    name_lbl.setStyleSheet(f"color: {tc('text')}; border: none;")
    row.addWidget(name_lbl)

    # Employee ID
    eid_lbl = QLabel(off.get("employee_id", ""))
    eid_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; border: none;")
    row.addWidget(eid_lbl)

    # Site
    site_lbl = QLabel(off.get("site", ""))
    site_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; border: none;")
    row.addWidget(site_lbl)

    row.addStretch()

    # Points badge
    pts = float(off.get("active_points", 0))
    pts_lbl = QLabel(f"{pts:.1f} pts")
    pts_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
    pts_lbl.setAlignment(Qt.AlignCenter)
    pts_lbl.setFixedWidth(70)
    if pts >= 10:
        pts_lbl.setStyleSheet(f"background: {COLORS['danger']}; color: white; border-radius: 4px; padding: 4px; border: none;")
    elif pts >= 8:
        pts_lbl.setStyleSheet("background: #9333EA; color: white; border-radius: 4px; padding: 4px; border: none;")
    elif pts >= 6:
        pts_lbl.setStyleSheet(f"background: {COLORS['warning']}; color: white; border-radius: 4px; padding: 4px; border: none;")
    elif pts >= 1.5:
        pts_lbl.setStyleSheet(f"background: #FEF3C7; color: {COLORS['warning']}; border-radius: 4px; padding: 4px; border: none;")
    else:
        pts_lbl.setStyleSheet(f"background: {COLORS['success_light']}; color: {COLORS['success']}; border-radius: 4px; padding: 4px; border: none;")
    row.addWidget(pts_lbl)

    # Last infraction date
    last = off.get("last_infraction_date", "")
    if last:
        date_lbl = QLabel(f"Last: {last}")
        date_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px; border: none;")
        row.addWidget(date_lbl)

    return card


# ════════════════════════════════════════════════════════════════════════
# Discipline Tracker Page
# ════════════════════════════════════════════════════════════════════════

class DisciplinePage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._sections = {}
        self._build()

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(30, 24, 30, 24)
        self._layout.setSpacing(12)

        # Header
        title = QLabel("Discipline Tracker")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        self._layout.addWidget(title)

        subtitle = QLabel("Officers grouped by current discipline level")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        self._layout.addWidget(subtitle)

        # Create sections for each level
        levels = [
            ("None", COLORS["success"], "none"),
            ("Verbal Warning", COLORS["info"], "verbal_warning"),
            ("Written Warning", COLORS["warning"], "written_warning"),
            ("Employment Review", "#9333EA", "employment_review"),
            ("Termination Eligible", COLORS["danger"], "termination_eligible"),
        ]

        for display_name, color, key in levels:
            section = CollapsibleSection(display_name, color)
            self._sections[key] = (section, display_name)
            self._layout.addWidget(section)

        self._layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self):
        from src.shared_data import filter_by_user_sites
        officers = data_manager.get_all_officers()
        officers = filter_by_user_sites(self.app_state, officers)
        active = [o for o in officers if o.get("status") == "Active"]

        # Group officers by discipline level
        groups = {
            "none": [],
            "verbal_warning": [],
            "written_warning": [],
            "employment_review": [],
            "termination_eligible": [],
        }

        level_map = {
            "None": "none",
            "none": "none",
            "Verbal Warning": "verbal_warning",
            "verbal_warning": "verbal_warning",
            "Written Warning": "written_warning",
            "written_warning": "written_warning",
            "Employment Review": "employment_review",
            "employment_review": "employment_review",
            "Termination Eligible": "termination_eligible",
            "termination_eligible": "termination_eligible",
            "Termination Flag": "termination_eligible",
            "termination_flag": "termination_eligible",
        }

        for off in active:
            level = off.get("discipline_level", "None")
            key = level_map.get(level, "none")
            groups[key].append(off)

        # Sort each group by points descending
        for key in groups:
            groups[key].sort(key=lambda o: float(o.get("active_points", 0)), reverse=True)

        # Update sections
        for key, (section, display_name) in self._sections.items():
            officers_in_group = groups.get(key, [])
            section.update_count(display_name, len(officers_in_group))
            section.clear_content()

            if not officers_in_group:
                empty_lbl = QLabel("No officers in this category")
                empty_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; padding: 8px;")
                section.content_layout.addWidget(empty_lbl)
            else:
                for off in officers_in_group:
                    card = _make_officer_card(off)
                    section.content_layout.addWidget(card)
