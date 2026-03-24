"""
Cerasus Hub -- DA Generator Module: Template Customization Page
Editable narrative templates, citations, required improvements, and escalation language
organized by review category (Attendance, Performance/Conduct, Employment Review)
and discipline level.
"""

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QFrame, QTabWidget, QScrollArea, QMessageBox, QGroupBox, QFormLayout,
    QComboBox, QSplitter, QDialog, QDialogButtonBox, QTextBrowser,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.config import COLORS, tc, btn_style, _is_dark
from src.modules.da_generator import data_manager
from src import audit


# ═══════════════════════════════════════════════════════════════════════
#  Default Templates — these ship with the app and are the fallback
# ═══════════════════════════════════════════════════════════════════════

REVIEW_CATEGORIES = {
    "attendance": "Attendance Review (Type A)",
    "performance": "Performance / Conduct Review (Type B)",
    "employment": "Employment Review (Type C)",
}

DISCIPLINE_LEVELS = [
    "Verbal Warning",
    "Written Warning",
    "Final Warning",
    "Termination",
]

# Placeholder reference: {employee}, {position}, {site}, {dates}, {narrative},
# {supervisor}, {points}, {prior_summary}, {coaching_summary}

DEFAULT_TEMPLATES = {
    # ── ATTENDANCE ──────────────────────────────────────────────────
    "attendance": {
        "narrative": {
            "Verbal Warning": (
                "On {dates}, {employee}, employed as a {position} at {site}, "
                "failed to meet attendance expectations as outlined in the Cerasus Security "
                "Employee Handbook.\n\n{narrative}\n\n"
                "This is the employee's first attendance threshold under the progressive "
                "point system. {employee} currently carries {points} active attendance points.\n\n"
                "(Violation Section 3.5 -- Attendance and Punctuality)"
            ),
            "Written Warning": (
                "On {dates}, {employee}, employed as a {position} at {site}, "
                "committed an additional attendance infraction.\n\n{narrative}\n\n"
                "Despite a prior Verbal Warning, {employee} has continued to accumulate "
                "attendance infractions. The employee currently carries {points} active points, "
                "which exceeds the Written Warning threshold under the progressive attendance "
                "point system.\n\n{prior_summary}\n\n"
                "(Violation Section 3.5 -- Attendance and Punctuality)"
            ),
            "Final Warning": (
                "On {dates}, {employee}, employed as a {position} at {site}, "
                "committed a further attendance infraction.\n\n{narrative}\n\n"
                "{employee} has continued to demonstrate a pattern of unreliable attendance "
                "despite prior corrective actions. The employee currently carries {points} active "
                "points, triggering a Final Written Warning under the progressive discipline framework.\n\n"
                "{prior_summary}\n\n"
                "This is the final step before potential termination of employment. "
                "Any further attendance violations may result in immediate separation.\n\n"
                "(Violation Section 3.5 -- Attendance and Punctuality)"
            ),
            "Termination": (
                "On {dates}, {employee}, employed as a {position} at {site}, "
                "committed an attendance infraction that has caused the employee to reach "
                "or exceed the termination threshold.\n\n{narrative}\n\n"
                "{employee} currently carries {points} active attendance points, meeting or exceeding "
                "the 10-point termination threshold. Progressive discipline has been exhausted.\n\n"
                "{prior_summary}\n\n"
                "Despite multiple prior disciplinary actions, the employee has failed to demonstrate "
                "sustained improvement in attendance.\n\n"
                "(Violation Section 3.5 -- Attendance and Punctuality)"
            ),
        },
        "citations": (
            'Section 3.5 -- Attendance and Punctuality\n'
            '"Regular and reliable attendance is an essential function of every position. '
            'Employees are expected to report to their assigned post on time and remain '
            'on duty for the duration of their scheduled shift. Excessive absenteeism, '
            'tardiness, or failure to report without proper notice will result in '
            'progressive disciplinary action."\n\n'
            'Section 3.5.1 -- Attendance Point System\n'
            '"Attendance infractions are tracked using a progressive point system. '
            'Points accumulate over a rolling 365-day window. Discipline thresholds: '
            '2 points -- Verbal Warning; 4 points -- Written Warning; '
            '6 points -- Final Written Warning; 8 points -- Employment Review; '
            '10 points -- Termination Eligible."\n\n'
            'Section 3.6 -- Call-Off Procedures\n'
            '"Employees must notify their supervisor or the operations center at least '
            'four (4) hours prior to the start of their scheduled shift. Failure to '
            'provide adequate notice may result in additional disciplinary points."\n\n'
            'Section 3.7 -- No Call / No Show\n'
            '"Failure to report for a scheduled shift without notification constitutes '
            'a No Call / No Show (NCNS). A first NCNS offense carries 6 points and an '
            'automatic Written Warning. A second NCNS offense is grounds for immediate '
            'termination."'
        ),
        "improvements": {
            "Verbal Warning": (
                "- Report to all scheduled shifts on time as assigned.\n"
                "- Provide proper advance notice (minimum 4 hours) for any absences.\n"
                "- Maintain regular and reliable attendance going forward.\n"
                "- Review and acknowledge the company attendance policy."
            ),
            "Written Warning": (
                "- Report to all scheduled shifts on time as assigned.\n"
                "- Provide proper advance notice (minimum 4 hours) for any absences.\n"
                "- Maintain regular and reliable attendance for the next 90 days.\n"
                "- Any further attendance infractions will result in escalated discipline.\n"
                "- Review the attendance point system and understand your current standing."
            ),
            "Final Warning": (
                "- Report to all scheduled shifts on time with zero exceptions.\n"
                "- Provide proper advance notice (minimum 4 hours) for any absences.\n"
                "- Maintain perfect attendance for the next 90 days.\n"
                "- Understand that ANY further attendance violation may result in immediate termination.\n"
                "- Acknowledge receipt of this Final Warning in writing."
            ),
            "Termination": "N/A -- Employment terminated.",
        },
        "escalation": {
            "Verbal Warning": (
                "This constitutes a Verbal Warning under the progressive attendance discipline policy. "
                "Further attendance infractions will result in escalation to a Written Warning."
            ),
            "Written Warning": (
                "This constitutes a Written Warning under the progressive attendance discipline policy. "
                "Continued attendance issues will result in a Final Written Warning."
            ),
            "Final Warning": (
                "This constitutes a Final Written Warning. This is the last step before termination. "
                "Any further attendance violations, regardless of point value, may result in "
                "immediate termination of employment."
            ),
            "Termination": (
                "Based on the exhaustion of progressive discipline and the employee's cumulative "
                "attendance record, termination of employment is recommended effective immediately."
            ),
        },
    },

    # ── PERFORMANCE / CONDUCT ──────────────────────────────────────
    "performance": {
        "narrative": {
            "Verbal Warning": (
                "On {dates}, {employee}, employed as a {position} at {site}, "
                "was involved in the following incident:\n\n{narrative}\n\n"
                "This behavior constitutes a violation of Cerasus Security's Standards of Conduct "
                "and professional expectations.\n\n"
                "(Violation Section 4.1 -- Standards of Conduct)"
            ),
            "Written Warning": (
                "On {dates}, {employee}, employed as a {position} at {site}, "
                "was involved in the following incident:\n\n{narrative}\n\n"
                "{prior_summary}\n\n"
                "Despite prior counseling, {employee} has repeated or continued behavior "
                "that falls below the professional standards required of all Cerasus Security personnel.\n\n"
                "{coaching_summary}\n\n"
                "(Violation Section 4.1 -- Standards of Conduct)"
            ),
            "Final Warning": (
                "On {dates}, {employee}, employed as a {position} at {site}, "
                "was involved in the following incident:\n\n{narrative}\n\n"
                "{prior_summary}\n\n"
                "This incident represents a continued failure to comply with company policy "
                "despite multiple prior corrective actions. {employee} has been given "
                "reasonable opportunities to correct the behavior and has failed to do so.\n\n"
                "{coaching_summary}\n\n"
                "This Final Written Warning is the last step before potential termination.\n\n"
                "(Violation Section 4.1 -- Standards of Conduct)"
            ),
            "Termination": (
                "On {dates}, {employee}, employed as a {position} at {site}, "
                "was involved in the following incident:\n\n{narrative}\n\n"
                "{prior_summary}\n\n"
                "Progressive discipline has been exhausted. Despite Verbal Warning, Written Warning, "
                "and Final Written Warning, {employee} has failed to demonstrate sustained "
                "improvement in professional conduct.\n\n"
                "{coaching_summary}\n\n"
                "(Violation Section 4.1 -- Standards of Conduct)"
            ),
        },
        "citations": (
            'Section 4.1 -- Standards of Conduct\n'
            '"All employees are expected to conduct themselves in a professional manner '
            'at all times while on duty. Failure to meet these standards may result in '
            'disciplinary action up to and including termination of employment."\n\n'
            'Section 4.2 -- Workplace Conduct\n'
            '"Employees shall maintain a professional demeanor and treat all persons '
            'with courtesy and respect. Disruptive, insubordinate, threatening, or '
            'otherwise unprofessional behavior will not be tolerated."\n\n'
            'Section 4.3 -- Insubordination\n'
            '"Refusal to follow a lawful and reasonable directive from a supervisor '
            'or management representative constitutes insubordination and may result '
            'in disciplinary action up to and including termination."'
        ),
        "improvements": {
            "Verbal Warning": (
                "- Conduct yourself professionally at all times while on duty.\n"
                "- Follow all directives from supervisors and management.\n"
                "- Comply with all company policies and post orders.\n"
                "- Maintain appropriate workplace behavior and communication."
            ),
            "Written Warning": (
                "- Immediately cease the identified behavior.\n"
                "- Conduct yourself professionally at all times while on duty.\n"
                "- Follow all directives from supervisors and management without exception.\n"
                "- Attend any required retraining or coaching session as directed.\n"
                "- Maintain appropriate workplace behavior for the next 90 days."
            ),
            "Final Warning": (
                "- Immediately and permanently cease the identified behavior.\n"
                "- Demonstrate consistent professional conduct on every shift.\n"
                "- Follow all directives from supervisors without exception.\n"
                "- Complete any assigned retraining within 14 days.\n"
                "- Understand that ANY further conduct violation will result in termination.\n"
                "- Acknowledge receipt of this Final Warning in writing."
            ),
            "Termination": "N/A -- Employment terminated.",
        },
        "escalation": {
            "Verbal Warning": (
                "This constitutes a Verbal Warning in the progressive discipline process. "
                "The employee is expected to immediately correct the behavior. "
                "Further violations will result in a Written Warning."
            ),
            "Written Warning": (
                "This constitutes a Written Warning in the progressive discipline process. "
                "The employee has previously received verbal counseling for similar or related behavior. "
                "Continued violations will result in a Final Written Warning."
            ),
            "Final Warning": (
                "This constitutes a Final Written Warning. Any further violations of company policy "
                "may result in immediate termination of employment. The employee has exhausted "
                "all intermediate steps of progressive discipline."
            ),
            "Termination": (
                "Based on the severity and/or cumulative history of policy violations, "
                "and the exhaustion of progressive discipline, termination of employment is recommended."
            ),
        },
    },

    # ── EMPLOYMENT REVIEW ──────────────────────────────────────────
    "employment": {
        "narrative": {
            "Verbal Warning": (
                "An Employment Review has been initiated for {employee}, employed as a "
                "{position} at {site}, based on cumulative performance concerns.\n\n"
                "{narrative}\n\n"
                "This review considers the employee's overall record, including attendance, "
                "conduct, and job performance.\n\n"
                "(Violation Section 4.1 -- Standards of Conduct)"
            ),
            "Written Warning": (
                "A continued Employment Review is being conducted for {employee}, employed as a "
                "{position} at {site}.\n\n{narrative}\n\n"
                "{prior_summary}\n\n"
                "Despite prior corrective action, {employee} has not demonstrated the sustained "
                "improvement necessary to meet the expectations of the position.\n\n"
                "(Violation Section 4.1 -- Standards of Conduct)"
            ),
            "Final Warning": (
                "This Employment Review for {employee}, employed as a {position} at {site}, "
                "has reached the Final Warning stage.\n\n{narrative}\n\n"
                "{prior_summary}\n\n"
                "The employee has been given multiple opportunities and reasonable time to "
                "demonstrate improvement. This is the final step before potential separation.\n\n"
                "(Violation Section 4.1 -- Standards of Conduct)"
            ),
            "Termination": (
                "Following a comprehensive Employment Review, it is recommended that "
                "{employee}'s employment as a {position} at {site} be terminated.\n\n"
                "{narrative}\n\n"
                "{prior_summary}\n\n"
                "The employee has failed to meet the minimum standards of employment "
                "despite extended progressive discipline and multiple opportunities for improvement.\n\n"
                "(Violation Section 4.1 -- Standards of Conduct)"
            ),
        },
        "citations": (
            'Section 4.1 -- Standards of Conduct\n'
            '"All employees are expected to conduct themselves in a professional manner '
            'at all times while on duty. Failure to meet these standards may result in '
            'disciplinary action up to and including termination of employment."\n\n'
            'Section 3.5 -- Attendance and Punctuality (if applicable)\n'
            '"Regular and reliable attendance is an essential function of every position."\n\n'
            'Section 4.2 -- Workplace Conduct (if applicable)\n'
            '"Employees shall maintain a professional demeanor and treat all persons '
            'with courtesy and respect."'
        ),
        "improvements": {
            "Verbal Warning": (
                "- Demonstrate sustained improvement in overall job performance.\n"
                "- Comply with all company policies and procedures.\n"
                "- Participate in any required retraining or coaching sessions.\n"
                "- Maintain open communication with your supervisor.\n"
                "- Meet all attendance and punctuality requirements."
            ),
            "Written Warning": (
                "- Show measurable improvement within 30 days across all deficient areas.\n"
                "- Comply with all company policies without exception.\n"
                "- Complete any assigned retraining or development activities.\n"
                "- Meet with supervisor bi-weekly for progress check-ins.\n"
                "- Maintain satisfactory attendance and conduct."
            ),
            "Final Warning": (
                "- Achieve and maintain satisfactory performance in all areas.\n"
                "- Complete all assigned corrective action items within 14 days.\n"
                "- Maintain zero additional infractions for the next 90 days.\n"
                "- Attend all scheduled supervisor check-ins.\n"
                "- Understand that failure to improve will result in termination."
            ),
            "Termination": "N/A -- Employment terminated.",
        },
        "escalation": {
            "Verbal Warning": (
                "This Employment Review serves as formal notice that the employee's overall "
                "performance is under evaluation. Failure to demonstrate improvement may result "
                "in escalated discipline."
            ),
            "Written Warning": (
                "This Employment Review has escalated to a Written Warning. The employee must "
                "demonstrate measurable improvement within 30 days or face further escalation."
            ),
            "Final Warning": (
                "This Employment Review has reached the Final Warning stage. This is the last "
                "opportunity for the employee to demonstrate sustained improvement. Failure to "
                "improve will result in termination of employment."
            ),
            "Termination": (
                "The Employment Review process has concluded. Based on the employee's failure "
                "to meet the minimum standards of employment despite progressive discipline, "
                "termination is recommended."
            ),
        },
    },
}

# Settings key prefix for storing custom templates
TEMPLATE_SETTINGS_KEY = "da_templates_v1"

# Sample data used for template preview
SAMPLE_DATA = {
    "employee": "John A. Smith",
    "position": "Security Officer",
    "site": "Downtown Campus",
    "dates": "2026-03-15",
    "narrative": "Employee failed to report for scheduled shift without prior notification to supervisor or operations center.",
    "supervisor": "Jane Doe, Security Director",
    "points": "6.0",
    "prior_summary": "Prior Discipline: Verbal Warning issued 2026-01-10; Written Warning issued 2026-02-20.",
    "coaching_summary": "Management coaching was conducted on 2026-02-25. Employee acknowledged expectations but has not demonstrated sustained improvement.",
}


def get_templates(category: str) -> dict:
    """
    Load templates for a category, falling back to defaults.
    Returns the full template dict for the category.
    """
    try:
        saved = data_manager.get_setting(f"{TEMPLATE_SETTINGS_KEY}_{category}")
        if saved:
            custom = json.loads(saved)
            # Merge with defaults — custom overrides default
            defaults = DEFAULT_TEMPLATES.get(category, {})
            merged = {}
            for key in ("narrative", "citations", "improvements", "escalation"):
                if key in ("citations",):
                    # citations is a flat string
                    merged[key] = custom.get(key, defaults.get(key, ""))
                else:
                    # narrative, improvements, escalation are dicts keyed by discipline level
                    merged[key] = {}
                    default_dict = defaults.get(key, {})
                    custom_dict = custom.get(key, {})
                    if isinstance(default_dict, dict):
                        for level in DISCIPLINE_LEVELS:
                            merged[key][level] = custom_dict.get(level, default_dict.get(level, ""))
                    else:
                        merged[key] = custom_dict if custom_dict else default_dict
            return merged
    except Exception:
        pass
    return DEFAULT_TEMPLATES.get(category, {})


def save_templates(category: str, templates: dict):
    """Save custom templates for a category."""
    data_manager.save_setting(
        f"{TEMPLATE_SETTINGS_KEY}_{category}",
        json.dumps(templates, ensure_ascii=False),
    )


def reset_templates(category: str):
    """Reset templates for a category back to defaults."""
    data_manager.save_setting(f"{TEMPLATE_SETTINGS_KEY}_{category}", "")


# ═══════════════════════════════════════════════════════════════════════
#  Template Editor Page
# ═══════════════════════════════════════════════════════════════════════

class DATemplatesPage(QWidget):
    """Admin page for customizing DA narrative templates per review category."""

    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._editors = {}  # (category, section, level) -> QTextEdit
        self._dirty = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("DA Template Editor")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        header_row.addWidget(title)
        header_row.addStretch()

        # Placeholder guide label
        preview_btn = QPushButton("Preview Template")
        preview_btn.setCursor(Qt.PointingHandCursor)
        preview_btn.setStyleSheet(btn_style(COLORS["accent"]))
        preview_btn.clicked.connect(self._preview_template)
        header_row.addWidget(preview_btn)

        guide_btn = QPushButton("Placeholder Guide")
        guide_btn.setCursor(Qt.PointingHandCursor)
        guide_btn.setStyleSheet(btn_style(COLORS["info"]))
        guide_btn.clicked.connect(self._show_placeholder_guide)
        header_row.addWidget(guide_btn)

        root.addLayout(header_row)

        # Description
        desc = QLabel(
            "Customize the narrative language, policy citations, required improvements, "
            "and escalation language for each review type and discipline level. "
            "Use placeholders like {employee}, {site}, {dates} in your templates."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        root.addWidget(desc)

        # ── Tab widget for review categories ──
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 8px; border-top-left-radius: 0;
            }}
            QTabBar::tab {{
                background: {tc('bg')}; color: {tc('text_light')};
                padding: 10px 20px; border: 1px solid {tc('border')};
                border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;
                min-width: 180px; font-size: 13px; font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background: {tc('card')}; color: {tc('text')};
                border-bottom: 2px solid {COLORS['accent']};
            }}
            QTabBar::tab:hover {{
                background: {tc('card')};
            }}
        """)

        for cat_key, cat_label in REVIEW_CATEGORIES.items():
            tab = self._build_category_tab(cat_key)
            self.tabs.addTab(tab, cat_label)

        root.addWidget(self.tabs, 1)

        # ── Bottom buttons ──
        btn_row = QHBoxLayout()

        self.btn_save = QPushButton("Save All Templates")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet(btn_style(COLORS["success"]))
        self.btn_save.setFixedHeight(40)
        self.btn_save.setFixedWidth(200)
        self.btn_save.clicked.connect(self._save_all)
        btn_row.addWidget(self.btn_save)

        self.btn_reset = QPushButton("Reset Current Tab to Defaults")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setStyleSheet(btn_style(COLORS["warning"]))
        self.btn_reset.setFixedHeight(40)
        self.btn_reset.clicked.connect(self._reset_current)
        btn_row.addWidget(self.btn_reset)

        self.btn_reset_all = QPushButton("Reset All to Defaults")
        self.btn_reset_all.setCursor(Qt.PointingHandCursor)
        self.btn_reset_all.setStyleSheet(btn_style(COLORS["danger"]))
        self.btn_reset_all.setFixedHeight(40)
        self.btn_reset_all.clicked.connect(self._reset_all_defaults)
        btn_row.addWidget(self.btn_reset_all)

        btn_row.addStretch()

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        btn_row.addWidget(self.lbl_status)

        root.addLayout(btn_row)

    def _build_category_tab(self, category: str) -> QWidget:
        """Build the editor tab for one review category."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(20)

        templates = get_templates(category)

        # ── Section: Policy Citations (shared across all levels) ──
        citations_group = QGroupBox("Policy Citations (all levels)")
        citations_group.setStyleSheet(self._group_style())
        cit_lay = QVBoxLayout(citations_group)

        cit_desc = QLabel("These handbook citations are included in every DA for this review type.")
        cit_desc.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
        cit_desc.setWordWrap(True)
        cit_lay.addWidget(cit_desc)

        cit_edit = QTextEdit()
        cit_edit.setPlainText(templates.get("citations", ""))
        cit_edit.setMinimumHeight(120)
        cit_edit.setMaximumHeight(180)
        cit_edit.setStyleSheet(self._editor_style())
        cit_lay.addWidget(cit_edit)
        self._editors[(category, "citations", "_all")] = cit_edit

        layout.addWidget(citations_group)

        # ── Per-level sections ──
        for level in DISCIPLINE_LEVELS:
            level_group = QGroupBox(level)
            level_group.setStyleSheet(self._group_style_level(level))
            level_lay = QVBoxLayout(level_group)
            level_lay.setSpacing(12)

            # Narrative template
            narr_label = QLabel("Narrative Template:")
            narr_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
            narr_label.setStyleSheet(f"color: {tc('text')};")
            level_lay.addWidget(narr_label)

            narr_edit = QTextEdit()
            narr_text = templates.get("narrative", {})
            narr_edit.setPlainText(narr_text.get(level, "") if isinstance(narr_text, dict) else "")
            narr_edit.setMinimumHeight(100)
            narr_edit.setMaximumHeight(160)
            narr_edit.setStyleSheet(self._editor_style())
            level_lay.addWidget(narr_edit)
            self._editors[(category, "narrative", level)] = narr_edit

            # Required Improvements
            imp_label = QLabel("Required Improvements:")
            imp_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
            imp_label.setStyleSheet(f"color: {tc('text')};")
            level_lay.addWidget(imp_label)

            imp_edit = QTextEdit()
            imp_text = templates.get("improvements", {})
            imp_edit.setPlainText(imp_text.get(level, "") if isinstance(imp_text, dict) else "")
            imp_edit.setMinimumHeight(80)
            imp_edit.setMaximumHeight(120)
            imp_edit.setStyleSheet(self._editor_style())
            level_lay.addWidget(imp_edit)
            self._editors[(category, "improvements", level)] = imp_edit

            # Escalation Language
            esc_label = QLabel("Escalation / Progression Language:")
            esc_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
            esc_label.setStyleSheet(f"color: {tc('text')};")
            level_lay.addWidget(esc_label)

            esc_edit = QTextEdit()
            esc_text = templates.get("escalation", {})
            esc_edit.setPlainText(esc_text.get(level, "") if isinstance(esc_text, dict) else "")
            esc_edit.setMinimumHeight(60)
            esc_edit.setMaximumHeight(100)
            esc_edit.setStyleSheet(self._editor_style())
            level_lay.addWidget(esc_edit)
            self._editors[(category, "escalation", level)] = esc_edit

            layout.addWidget(level_group)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Styles ─────────────────────────────────────────────────────
    def _group_style(self):
        return f"""
            QGroupBox {{
                font-weight: 700; font-size: 14px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 10px; padding-top: 24px; background: {tc('bg')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 8px;
            }}
        """

    def _group_style_level(self, level: str):
        level_colors = {
            "Verbal Warning": "#3B82F6",
            "Written Warning": "#F59E0B",
            "Final Warning": "#EF4444",
            "Termination": "#DC2626",
        }
        color = level_colors.get(level, tc('text'))
        return f"""
            QGroupBox {{
                font-weight: 700; font-size: 14px; color: {color};
                border: 1px solid {tc('border')}; border-left: 4px solid {color};
                border-radius: 6px;
                margin-top: 10px; padding-top: 24px; background: {tc('bg')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 8px;
            }}
        """

    def _editor_style(self):
        return f"""
            QTextEdit {{
                background: {tc('card')}; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 4px;
                padding: 8px; font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }}
            QTextEdit:focus {{
                border: 1px solid {COLORS['accent']};
            }}
        """

    # ── Actions ────────────────────────────────────────────────────
    def _save_all(self):
        """Save all templates for all categories."""
        for cat_key in REVIEW_CATEGORIES:
            templates = self._collect_templates(cat_key)
            save_templates(cat_key, templates)

        username = self.app_state.get("username", "system")
        audit.log_event(
            module_name="da_generator",
            event_type="config_change",
            username=username,
            details="Updated DA narrative templates",
            table_name="settings",
            record_id="da_templates",
            action="update",
        )

        self.lbl_status.setText("All templates saved successfully.")
        self.lbl_status.setStyleSheet(f"color: {COLORS['success']}; font-size: 13px;")

    def _reset_current(self):
        """Reset the current tab's templates to defaults."""
        idx = self.tabs.currentIndex()
        cat_key = list(REVIEW_CATEGORIES.keys())[idx]
        cat_label = REVIEW_CATEGORIES[cat_key]

        reply = QMessageBox.question(
            self, "Reset Templates",
            f"Reset all {cat_label} templates to factory defaults?\n\n"
            f"This will overwrite your custom templates for this category.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        reset_templates(cat_key)

        # Reload editors with defaults
        defaults = DEFAULT_TEMPLATES.get(cat_key, {})
        self._load_into_editors(cat_key, defaults)

        self.lbl_status.setText(f"{cat_label} templates reset to defaults.")
        self.lbl_status.setStyleSheet(f"color: {COLORS['warning']}; font-size: 13px;")

    def _reset_all_defaults(self):
        """Reset ALL categories back to factory defaults."""
        reply = QMessageBox.question(
            self, "Reset All Templates",
            "Reset ALL template categories to factory defaults?\n\n"
            "This will overwrite custom templates for Attendance, Performance, and Employment.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for cat_key in REVIEW_CATEGORIES:
            reset_templates(cat_key)
            defaults = DEFAULT_TEMPLATES.get(cat_key, {})
            self._load_into_editors(cat_key, defaults)

        username = self.app_state.get("username", "system")
        audit.log_event(
            module_name="da_generator",
            event_type="config_change",
            username=username,
            details="Reset ALL DA narrative templates to defaults",
            table_name="settings",
            record_id="da_templates",
            action="reset",
        )

        self.lbl_status.setText("All templates reset to factory defaults.")
        self.lbl_status.setStyleSheet(f"color: {COLORS['warning']}; font-size: 13px;")

    def _preview_template(self):
        """Show a preview dialog with the current tab's narrative template filled with sample data."""
        idx = self.tabs.currentIndex()
        cat_key = list(REVIEW_CATEGORIES.keys())[idx]
        cat_label = REVIEW_CATEGORIES[cat_key]

        # Collect current editor content (not necessarily saved yet)
        templates = self._collect_templates(cat_key)

        # Build preview content
        accent_color = COLORS["accent"]
        primary_color = COLORS["primary"]
        text_light_color = tc("text_light")
        preview_parts = []
        preview_parts.append(f"<h2 style='color:{accent_color};'>Preview: {cat_label}</h2>")
        preview_parts.append(f"<p style='color:{text_light_color};font-size:12px;'>"
                             "Placeholders filled with sample data. "
                             "This shows how the template will appear in the final DA document.</p><hr>")

        for level in DISCIPLINE_LEVELS:
            narr_template = templates.get("narrative", {}).get(level, "")
            imp_template = templates.get("improvements", {}).get(level, "")
            esc_template = templates.get("escalation", {}).get(level, "")
            citations = templates.get("citations", "")

            # Fill placeholders with sample data
            filled_narr = self._fill_sample(narr_template)
            filled_imp = self._fill_sample(imp_template)
            filled_esc = self._fill_sample(esc_template)
            filled_cit = self._fill_sample(citations)

            preview_parts.append(
                f"<h3 style='color:{primary_color};'>{level}</h3>"
            )
            if filled_narr:
                preview_parts.append(f"<b>Narrative:</b><br><pre style='white-space:pre-wrap;font-family:Consolas;font-size:12px;'>{filled_narr}</pre>")
            if filled_cit:
                preview_parts.append(f"<b>Citations:</b><br><pre style='white-space:pre-wrap;font-family:Consolas;font-size:11px;'>{filled_cit}</pre>")
            if filled_imp:
                preview_parts.append(f"<b>Required Improvements:</b><br><pre style='white-space:pre-wrap;font-family:Consolas;font-size:12px;'>{filled_imp}</pre>")
            if filled_esc:
                preview_parts.append(f"<b>Escalation Language:</b><br><pre style='white-space:pre-wrap;font-family:Consolas;font-size:12px;'>{filled_esc}</pre>")
            preview_parts.append("<hr>")

        # Show in dialog
        from src.config import build_dialog_stylesheet, _is_dark
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Template Preview -- {cat_label}")
        dlg.setMinimumSize(720, 600)
        dlg.setStyleSheet(build_dialog_stylesheet(_is_dark()))

        layout = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setHtml("".join(preview_parts))
        browser.setStyleSheet(f"background: {tc('card')}; color: {tc('text')}; border: none; padding: 12px;")
        layout.addWidget(browser, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        dlg.exec()

    @staticmethod
    def _fill_sample(template_text: str) -> str:
        """Replace placeholders with sample data values."""
        if not template_text:
            return ""
        result = template_text
        for key, value in SAMPLE_DATA.items():
            result = result.replace("{" + key + "}", value)
        return result

    def _collect_templates(self, category: str) -> dict:
        """Collect all editor values for a category into a template dict."""
        templates = {}

        # Citations
        cit_editor = self._editors.get((category, "citations", "_all"))
        templates["citations"] = cit_editor.toPlainText() if cit_editor else ""

        # Per-level sections
        for section in ("narrative", "improvements", "escalation"):
            templates[section] = {}
            for level in DISCIPLINE_LEVELS:
                editor = self._editors.get((category, section, level))
                templates[section][level] = editor.toPlainText() if editor else ""

        return templates

    def _load_into_editors(self, category: str, templates: dict):
        """Load template values into the editors for a category."""
        cit_editor = self._editors.get((category, "citations", "_all"))
        if cit_editor:
            cit_editor.setPlainText(templates.get("citations", ""))

        for section in ("narrative", "improvements", "escalation"):
            section_data = templates.get(section, {})
            for level in DISCIPLINE_LEVELS:
                editor = self._editors.get((category, section, level))
                if editor and isinstance(section_data, dict):
                    editor.setPlainText(section_data.get(level, ""))

    def _show_placeholder_guide(self):
        QMessageBox.information(
            self, "Template Placeholders",
            "Use these placeholders in your narrative templates:\n\n"
            "{employee} — Employee's full name\n"
            "{position} — Job title (e.g., Security Officer)\n"
            "{site} — Job site / location name\n"
            "{dates} — Incident date(s)\n"
            "{narrative} — The incident description from the intake form\n"
            "{supervisor} — Supervisor / Security Director name\n"
            "{points} — Active attendance points (Type A only)\n"
            "{prior_summary} — Auto-generated prior discipline summary\n"
            "{coaching_summary} — Coaching session details (if any)\n\n"
            "Placeholders are replaced with actual values when the\n"
            "DA document is generated.",
        )

    def refresh(self):
        """Reload all editors from saved settings."""
        for cat_key in REVIEW_CATEGORIES:
            templates = get_templates(cat_key)
            self._load_into_editors(cat_key, templates)
        self.lbl_status.setText("")
