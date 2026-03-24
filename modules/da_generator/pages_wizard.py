"""
Cerasus Hub -- DA Generator Module: Wizard Page
5-step wizard for creating Disciplinary Action documents.
Step 1: Incident Intake  |  Step 2: Clarifying Questions  |  Step 3: CEIS Engine Output
Step 4: Additional Policy  |  Step 5: DA Draft Editor & Final Generation
"""

import json
import os
from datetime import datetime, date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QTextBrowser, QComboBox, QCheckBox, QRadioButton, QButtonGroup,
    QGroupBox, QFormLayout, QFrame, QScrollArea, QStackedWidget,
    QDateEdit, QMessageBox, QSizePolicy, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog,
)
from PySide6.QtCore import Qt, QDate, QTimer, QUrl
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QDesktopServices

from src.config import COLORS, tc, _is_dark, btn_style, build_dialog_stylesheet, REPORTS_DIR
from src.shared_data import get_active_officers, get_all_sites, search_officers, get_officer, update_officer
from src.modules.da_generator.local_engine import (
    generate_clarifying_questions, generate_ceis_output,
    generate_additional_policy_output, generate_required_improvements,
)
from src.modules.da_generator import data_manager
from src import audit


# ── Step Labels ──────────────────────────────────────────────────────

STEP_LABELS = [
    "Incident\nIntake",
    "Clarifying\nQuestions",
    "CEIS\nEngine",
    "Additional\nPolicy",
    "DA Draft\nEditor",
]

# Map display-format discipline levels to snake_case DB values
_LEVEL_DISPLAY_TO_DB = {
    "Verbal Warning": "verbal_warning",
    "Written Warning": "written_warning",
    "Final Warning": "final_warning",
    "Termination": "termination",
}


# ═════════════════════════════════════════════════════════════════════
#  StepIndicator — painted step circles connected by lines
# ═════════════════════════════════════════════════════════════════════

class StepIndicator(QWidget):
    """Custom painted widget showing 5 steps as circles connected by lines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_step = 0  # 0-indexed
        self.setFixedHeight(110)
        self.setMinimumWidth(600)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_step(self, step: int):
        self.current_step = step
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        n = len(STEP_LABELS)
        circle_r = 16
        top_y = 22
        label_y = top_y + circle_r + 16

        # Calculate even spacing — use wider margins so edge labels don't clip
        lbl_w = 120
        margin = max(70, lbl_w // 2 + 10)
        usable = w - 2 * margin
        spacing = usable / (n - 1) if n > 1 else 0

        positions = []
        for i in range(n):
            x = margin + int(i * spacing)
            positions.append(x)

        # Draw connecting lines
        for i in range(n - 1):
            if i < self.current_step:
                painter.setPen(QPen(QColor(COLORS["success"]), 3))
            else:
                border_col = tc("border")
                painter.setPen(QPen(QColor(border_col), 2))
            painter.drawLine(positions[i] + circle_r, top_y,
                             positions[i + 1] - circle_r, top_y)

        # Draw circles and labels
        for i in range(n):
            cx = positions[i]
            cy = top_y

            if i < self.current_step:
                # Completed — green filled
                painter.setPen(QPen(QColor(COLORS["success"]), 2))
                painter.setBrush(QBrush(QColor(COLORS["success"])))
            elif i == self.current_step:
                # Current — Cerasus red filled
                painter.setPen(QPen(QColor(COLORS["accent"]), 2))
                painter.setBrush(QBrush(QColor(COLORS["accent"])))
            else:
                # Future — gray outline
                border_col = tc("border")
                painter.setPen(QPen(QColor(border_col), 2))
                painter.setBrush(QBrush(QColor(tc("card"))))

            painter.drawEllipse(cx - circle_r, cy - circle_r,
                                circle_r * 2, circle_r * 2)

            # Step number inside circle
            if i <= self.current_step:
                painter.setPen(QPen(QColor("white")))
            else:
                painter.setPen(QPen(QColor(tc("text_light"))))
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.drawText(cx - circle_r, cy - circle_r,
                             circle_r * 2, circle_r * 2,
                             Qt.AlignCenter, str(i + 1))

            # Label below
            painter.setPen(QPen(QColor(tc("text") if i == self.current_step else tc("text_light"))))
            painter.setFont(QFont("Segoe UI", 9,
                                  QFont.Bold if i == self.current_step else QFont.Normal))
            lbl_w = 120
            painter.drawText(cx - lbl_w // 2, label_y, lbl_w, 50,
                             Qt.AlignHCenter | Qt.AlignTop, STEP_LABELS[i])

        painter.end()


# ═════════════════════════════════════════════════════════════════════
#  LoadingOverlay — semi-transparent overlay during API calls
# ═════════════════════════════════════════════════════════════════════

class LoadingOverlay(QWidget):
    """Semi-transparent overlay with processing message and spinning dots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._dots = 0
        self._message = "Processing"
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)

    def show_with_message(self, msg: str = "Processing"):
        self._message = msg
        self._dots = 0
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.setVisible(True)
        self.raise_()
        self._timer.start(400)

    def hide_overlay(self):
        self._timer.stop()
        self.setVisible(False)

    def _animate(self):
        self._dots = (self._dots + 1) % 4
        self.update()

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Semi-transparent background
        if _is_dark():
            painter.fillRect(self.rect(), QColor(0, 0, 0, 180))
        else:
            painter.fillRect(self.rect(), QColor(255, 255, 255, 200))

        # Center message
        text = self._message + "." * self._dots
        painter.setPen(QPen(QColor(COLORS["accent"])))
        painter.setFont(QFont("Segoe UI", 18, QFont.Bold))
        painter.drawText(self.rect(), Qt.AlignCenter, text)

        # Sub-message
        painter.setPen(QPen(QColor(tc("text_light"))))
        painter.setFont(QFont("Segoe UI", 11))
        sub_rect = self.rect().adjusted(0, 40, 0, 40)
        painter.drawText(sub_rect, Qt.AlignCenter,
                         "CEIS Engine is analyzing your intake data...")

        painter.end()


# ═════════════════════════════════════════════════════════════════════
#  Helper: styled card frame
# ═════════════════════════════════════════════════════════════════════

def _card_frame(parent=None) -> QFrame:
    """Return a QFrame styled as a card."""
    frame = QFrame(parent)
    frame.setFrameShape(QFrame.StyledPanel)
    frame.setStyleSheet(f"""
        QFrame {{
            background: {tc('card')};
            border: 1px solid {tc('border')};
            border-radius: 8px;
            padding: 16px;
        }}
        QLineEdit, QComboBox, QDateEdit {{
            min-height: 36px;
            padding: 6px 10px;
            font-size: 14px;
        }}
        QTextEdit {{
            font-size: 14px;
            padding: 6px;
        }}
        QLabel {{
            font-size: 14px;
        }}
    """)
    return frame


def _section_header(text: str, parent=None) -> QLabel:
    """Return a styled section header label."""
    lbl = QLabel(text, parent)
    lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
    lbl.setStyleSheet(f"color: {tc('text')}; padding: 4px 0; border: none; background: transparent;")
    return lbl


# ═════════════════════════════════════════════════════════════════════
#  DAWizardPage — Main wizard page
# ═════════════════════════════════════════════════════════════════════

class DAWizardPage(QWidget):
    """5-step wizard for creating Disciplinary Action documents."""

    def __init__(self, app_state=None):
        super().__init__()
        self.app_state = app_state or {}
        self.da_data = {}
        self.da_id = None
        self._matched_officer = None
        self._attendance_infractions = []
        self._clarifying_questions = []
        self._clarifying_answers = []
        self._ceis_sections = {}
        self._current_step = 0

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Step indicator
        self.step_indicator = StepIndicator()
        root.addWidget(self.step_indicator)

        # Stacked widget for step content
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # Build each step
        self._build_step1()
        self._build_step2()
        self._build_step3()
        self._build_step4()
        self._build_step5()

        # Navigation bar
        nav_bar = QHBoxLayout()
        nav_bar.setContentsMargins(16, 8, 16, 12)

        self.btn_back = QPushButton("Back")
        self.btn_back.setFixedWidth(120)
        self.btn_back.setStyleSheet(btn_style(tc("info"), "white", tc("text_light")))
        self.btn_back.clicked.connect(self._go_back)

        self.btn_next = QPushButton("Submit Intake")
        self.btn_next.setFixedWidth(180)
        self.btn_next.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        self.btn_next.clicked.connect(self._go_next)

        nav_bar.addWidget(self.btn_back)
        nav_bar.addStretch()
        nav_bar.addWidget(self.btn_next)

        root.addLayout(nav_bar)

        # Loading overlay (on top of everything)
        self.loading = LoadingOverlay(self)

        # Initialize state
        self._update_nav()

    # ── Step 1: Incident Intake ──────────────────────────────────────

    def _build_step1(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("Step 1 — Incident Intake")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['accent']};")
        layout.addWidget(title)

        subtitle = QLabel("Provide all known facts about the incident. The CEIS Engine will handle policy language.")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── Main Intake Card ──
        card = _card_frame()
        form = QFormLayout(card)
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # Employee Name
        self.s1_employee = QComboBox()
        self.s1_employee.setEditable(True)
        self.s1_employee.setMinimumWidth(400)
        self.s1_employee.setMinimumHeight(38)
        self.s1_employee.setPlaceholderText("Start typing to search...")
        self.s1_employee.currentTextChanged.connect(self._on_employee_changed)
        form.addRow("Employee Name:", self.s1_employee)

        # Employee Position
        self.s1_position = QComboBox()
        self.s1_position.addItems([
            "Security Officer", "Field Supervisor", "Team Lead",
            "Site Supervisor", "Operations Manager",
        ])
        form.addRow("Employee Position:", self.s1_position)

        # Job Site
        self.s1_site = QComboBox()
        self.s1_site.setEditable(True)
        self.s1_site.setPlaceholderText("Select or type a site...")
        form.addRow("Job Site:", self.s1_site)

        # Security Director
        self.s1_director = QLineEdit()
        self.s1_director.setPlaceholderText("Name of security director")
        form.addRow("Security Director:", self.s1_director)

        # Incident Dates — calendar picker with optional range
        dates_widget = QWidget()
        dates_lay = QHBoxLayout(dates_widget)
        dates_lay.setContentsMargins(0, 0, 0, 0)
        dates_lay.setSpacing(8)

        self.s1_date_start = QDateEdit()
        self.s1_date_start.setCalendarPopup(True)
        self.s1_date_start.setDate(QDate.currentDate())
        self.s1_date_start.setDisplayFormat("yyyy-MM-dd")
        self.s1_date_start.setMinimumWidth(160)
        dates_lay.addWidget(self.s1_date_start)

        self.s1_date_range_cb = QCheckBox("Date Range")
        self.s1_date_range_cb.toggled.connect(self._toggle_date_range)
        dates_lay.addWidget(self.s1_date_range_cb)

        self.s1_date_end_label = QLabel("through")
        self.s1_date_end_label.setVisible(False)
        dates_lay.addWidget(self.s1_date_end_label)

        self.s1_date_end = QDateEdit()
        self.s1_date_end.setCalendarPopup(True)
        self.s1_date_end.setDate(QDate.currentDate())
        self.s1_date_end.setDisplayFormat("yyyy-MM-dd")
        self.s1_date_end.setMinimumWidth(160)
        self.s1_date_end.setVisible(False)
        dates_lay.addWidget(self.s1_date_end)

        dates_lay.addStretch()
        form.addRow("Date(s) of Incident:", dates_widget)

        # Incident Type
        self.s1_type = QComboBox()
        self.s1_type.addItems([
            "Type A \u2014 Attendance",
            "Type B \u2014 Performance/Conduct",
            "Type C \u2014 Employment Review",
        ])
        self.s1_type.currentIndexChanged.connect(self._on_incident_type_changed)
        form.addRow("Incident Type:", self.s1_type)

        # Incident Narrative
        self.s1_narrative = QTextEdit()
        self.s1_narrative.setMinimumHeight(180)
        self.s1_narrative.setPlaceholderText("Facts only \u2014 no policy language. Describe what happened, when, and who was involved.")
        form.addRow("Incident Narrative:", self.s1_narrative)

        layout.addWidget(card)

        # ── Attendance Record Card (initially hidden) ──
        self.s1_attendance_card = _card_frame()
        self.s1_attendance_card.setVisible(False)
        att_layout = QVBoxLayout(self.s1_attendance_card)
        att_layout.setSpacing(8)

        att_header = QHBoxLayout()
        att_title = QLabel("Attendance Record")
        att_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        att_title.setStyleSheet(f"color: {tc('text')}; border: none; background: transparent;")
        att_header.addWidget(att_title)
        att_header.addStretch()

        self.s1_att_badge = QLabel()
        self.s1_att_badge.setFixedHeight(26)
        self.s1_att_badge.setStyleSheet(f"""
            background: {COLORS['success']}; color: white;
            border-radius: 13px; padding: 2px 14px; font-weight: bold; font-size: 12px;
        """)
        att_header.addWidget(self.s1_att_badge)
        att_layout.addLayout(att_header)

        # Summary labels
        self.s1_att_summary = QLabel()
        self.s1_att_summary.setWordWrap(True)
        self.s1_att_summary.setStyleSheet(f"color: {tc('text')}; font-size: 13px; border: none; background: transparent;")
        att_layout.addWidget(self.s1_att_summary)

        # Infraction table (collapsible)
        self.s1_att_table_toggle = QPushButton("Show Infraction History")
        self.s1_att_table_toggle.setStyleSheet(btn_style(tc("info"), "white"))
        self.s1_att_table_toggle.setFixedWidth(230)
        self.s1_att_table_toggle.clicked.connect(self._toggle_att_table)
        att_layout.addWidget(self.s1_att_table_toggle)

        self.s1_att_table = QTableWidget()
        self.s1_att_table.setColumnCount(5)
        self.s1_att_table.setHorizontalHeaderLabels(["Date", "Type", "Points", "Active", "Notes"])
        self.s1_att_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.s1_att_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.s1_att_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.s1_att_table.setAlternatingRowColors(True)
        self.s1_att_table.setMaximumHeight(250)
        self.s1_att_table.setVisible(False)
        att_layout.addWidget(self.s1_att_table)

        # Manual override
        self.s1_att_override = QCheckBox("Manual Override \u2014 edit pulled attendance data manually")
        self.s1_att_override.setStyleSheet(f"color: {tc('text')}; font-size: 13px; border: none; background: transparent;")
        att_layout.addWidget(self.s1_att_override)

        layout.addWidget(self.s1_attendance_card)

        # ── Prior Discipline Record ──
        prior_group = QGroupBox("Prior Discipline Record")
        prior_layout = QVBoxLayout(prior_group)

        same_label = QLabel("Same Issue:")
        same_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        same_label.setStyleSheet(f"color: {tc('text')}; border: none;")
        prior_layout.addWidget(same_label)

        same_row = QHBoxLayout()
        self.s1_prior_verbal_same = QCheckBox("Verbal Warning")
        self.s1_prior_written_same = QCheckBox("Written Warning")
        self.s1_prior_final_same = QCheckBox("Final Warning")
        for cb in [self.s1_prior_verbal_same, self.s1_prior_written_same, self.s1_prior_final_same]:
            cb.setStyleSheet(f"color: {tc('text')}; border: none;")
        same_row.addWidget(self.s1_prior_verbal_same)
        same_row.addWidget(self.s1_prior_written_same)
        same_row.addWidget(self.s1_prior_final_same)
        same_row.addStretch()
        prior_layout.addLayout(same_row)

        other_label = QLabel("Other Issue:")
        other_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        other_label.setStyleSheet(f"color: {tc('text')}; border: none;")
        prior_layout.addWidget(other_label)

        other_row = QHBoxLayout()
        self.s1_prior_verbal_other = QCheckBox("Verbal Warning")
        self.s1_prior_written_other = QCheckBox("Written Warning")
        self.s1_prior_final_other = QCheckBox("Final Warning")
        for cb in [self.s1_prior_verbal_other, self.s1_prior_written_other, self.s1_prior_final_other]:
            cb.setStyleSheet(f"color: {tc('text')}; border: none;")
        other_row.addWidget(self.s1_prior_verbal_other)
        other_row.addWidget(self.s1_prior_written_other)
        other_row.addWidget(self.s1_prior_final_other)
        other_row.addStretch()
        prior_layout.addLayout(other_row)

        layout.addWidget(prior_group)

        # ── Management Coaching ──
        coaching_group = QGroupBox("Management Coaching")
        coaching_layout = QFormLayout(coaching_group)
        coaching_layout.setSpacing(8)

        self.s1_coaching = QComboBox()
        self.s1_coaching.addItems(["No", "Yes"])
        self.s1_coaching.currentIndexChanged.connect(self._on_coaching_changed)
        coaching_layout.addRow("Coaching Occurred:", self.s1_coaching)

        # Conditional coaching fields
        self.s1_coaching_frame = QFrame()
        self.s1_coaching_frame.setVisible(False)
        cf_layout = QFormLayout(self.s1_coaching_frame)
        cf_layout.setSpacing(8)

        self.s1_coaching_date = QDateEdit()
        self.s1_coaching_date.setCalendarPopup(True)
        self.s1_coaching_date.setDate(QDate.currentDate())
        cf_layout.addRow("Coaching Date:", self.s1_coaching_date)

        self.s1_coaching_content = QTextEdit()
        self.s1_coaching_content.setMinimumHeight(90)
        self.s1_coaching_content.setMaximumHeight(140)
        self.s1_coaching_content.setPlaceholderText("What coaching was provided?")
        cf_layout.addRow("Content:", self.s1_coaching_content)

        self.s1_coaching_outcome = QTextEdit()
        self.s1_coaching_outcome.setMinimumHeight(90)
        self.s1_coaching_outcome.setMaximumHeight(140)
        self.s1_coaching_outcome.setPlaceholderText("What was the result/outcome of coaching?")
        cf_layout.addRow("Outcome:", self.s1_coaching_outcome)

        coaching_layout.addRow(self.s1_coaching_frame)
        layout.addWidget(coaching_group)

        # ── Written Statements ──
        statements_group = QGroupBox("Written Statements Collected")
        stmt_layout = QHBoxLayout(statements_group)
        self.s1_victim_stmt = QCheckBox("Victim Statement")
        self.s1_subject_stmt = QCheckBox("Subject Statement")
        self.s1_witness_stmt = QCheckBox("Witness Statements")
        for cb in [self.s1_victim_stmt, self.s1_subject_stmt, self.s1_witness_stmt]:
            cb.setStyleSheet(f"color: {tc('text')}; border: none;")
        stmt_layout.addWidget(self.s1_victim_stmt)
        stmt_layout.addWidget(self.s1_subject_stmt)
        stmt_layout.addWidget(self.s1_witness_stmt)
        stmt_layout.addStretch()
        layout.addWidget(statements_group)

        layout.addStretch()
        scroll.setWidget(container)
        self.stack.addWidget(scroll)

    # ── Step 2: Clarifying Questions ─────────────────────────────────

    def _build_step2(self):
        self.s2_widget = QWidget()
        s2_layout = QVBoxLayout(self.s2_widget)
        s2_layout.setContentsMargins(20, 12, 20, 20)
        s2_layout.setSpacing(12)

        title = QLabel("Step 2 \u2014 Clarifying Questions")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['accent']};")
        s2_layout.addWidget(title)

        subtitle = QLabel("The CEIS Engine may need additional information to produce accurate output.")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        subtitle.setWordWrap(True)
        s2_layout.addWidget(subtitle)

        # Success message (initially hidden)
        self.s2_success_frame = _card_frame()
        self.s2_success_frame.setVisible(False)
        sf_layout = QVBoxLayout(self.s2_success_frame)
        self.s2_success_label = QLabel()
        self.s2_success_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.s2_success_label.setStyleSheet(f"color: {COLORS['success']}; border: none; background: transparent;")
        self.s2_success_label.setAlignment(Qt.AlignCenter)
        sf_layout.addWidget(self.s2_success_label)
        s2_layout.addWidget(self.s2_success_frame)

        # Scroll area for questions
        self.s2_scroll = QScrollArea()
        self.s2_scroll.setWidgetResizable(True)
        self.s2_scroll.setFrameShape(QFrame.NoFrame)

        self.s2_questions_container = QWidget()
        self.s2_questions_layout = QVBoxLayout(self.s2_questions_container)
        self.s2_questions_layout.setContentsMargins(0, 0, 0, 0)
        self.s2_questions_layout.setSpacing(12)
        self.s2_questions_layout.addStretch()
        self.s2_scroll.setWidget(self.s2_questions_container)
        s2_layout.addWidget(self.s2_scroll, 1)

        # Error label (hidden until needed)
        self.s2_error_label = QLabel()
        self.s2_error_label.setStyleSheet(f"color: {COLORS['danger']}; font-size: 13px; font-weight: bold;")
        self.s2_error_label.setWordWrap(True)
        self.s2_error_label.setVisible(False)
        s2_layout.addWidget(self.s2_error_label)

        self.stack.addWidget(self.s2_widget)

    # ── Step 3: CEIS Engine Output ───────────────────────────────────

    def _build_step3(self):
        self.s3_widget = QWidget()
        s3_layout = QVBoxLayout(self.s3_widget)
        s3_layout.setContentsMargins(20, 12, 20, 20)
        s3_layout.setSpacing(12)

        title = QLabel("Step 3 \u2014 CEIS Engine Output")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['accent']};")
        s3_layout.addWidget(title)

        subtitle = QLabel("Review the CEIS analysis below. Each section can be edited in Step 5.")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        subtitle.setWordWrap(True)
        s3_layout.addWidget(subtitle)

        # Error label
        self.s3_error_label = QLabel()
        self.s3_error_label.setStyleSheet(f"color: {COLORS['danger']}; font-size: 13px; font-weight: bold;")
        self.s3_error_label.setWordWrap(True)
        self.s3_error_label.setVisible(False)
        s3_layout.addWidget(self.s3_error_label)

        # Scroll area for sections
        self.s3_scroll = QScrollArea()
        self.s3_scroll.setWidgetResizable(True)
        self.s3_scroll.setFrameShape(QFrame.NoFrame)

        self.s3_sections_container = QWidget()
        self.s3_sections_layout = QVBoxLayout(self.s3_sections_container)
        self.s3_sections_layout.setContentsMargins(0, 0, 0, 0)
        self.s3_sections_layout.setSpacing(12)
        self.s3_sections_layout.addStretch()
        self.s3_scroll.setWidget(self.s3_sections_container)
        s3_layout.addWidget(self.s3_scroll, 1)

        self.stack.addWidget(self.s3_widget)

    # ── Step 4: Additional Policy Application ────────────────────────

    def _build_step4(self):
        self.s4_widget = QWidget()
        s4_layout = QVBoxLayout(self.s4_widget)
        s4_layout.setContentsMargins(20, 12, 20, 20)
        s4_layout.setSpacing(12)

        title = QLabel("Step 4 \u2014 Additional Policy Application")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['accent']};")
        s4_layout.addWidget(title)

        subtitle = QLabel("Indicate whether additional policies apply to this incident.")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        subtitle.setWordWrap(True)
        s4_layout.addWidget(subtitle)

        card = _card_frame()
        form = QFormLayout(card)
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # Use of Force
        self.s4_uof = QComboBox()
        self.s4_uof.setMinimumHeight(38)
        self.s4_uof.addItems(["No", "Yes"])
        form.addRow("Does Use of Force policy apply?", self.s4_uof)

        # Post Orders
        self.s4_post_orders = QComboBox()
        self.s4_post_orders.setMinimumHeight(38)
        self.s4_post_orders.addItems(["No", "Yes"])
        self.s4_post_orders.currentIndexChanged.connect(self._on_post_orders_changed)
        form.addRow("Do any post orders apply?", self.s4_post_orders)

        self.s4_post_order_details = QTextEdit()
        self.s4_post_order_details.setMinimumHeight(120)
        self.s4_post_order_details.setMaximumHeight(180)
        self.s4_post_order_details.setPlaceholderText("Describe which post orders and how they apply...")
        self.s4_post_order_details.setVisible(False)
        form.addRow("Post Order Details:", self.s4_post_order_details)

        # Additional Violations
        self.s4_additional = QTextEdit()
        self.s4_additional.setMinimumHeight(120)
        self.s4_additional.setMaximumHeight(180)
        self.s4_additional.setPlaceholderText("Optional: describe any additional violations to layer in...")
        form.addRow("Additional violations to layer in?", self.s4_additional)

        s4_layout.addWidget(card)

        # Error label
        self.s4_error_label = QLabel()
        self.s4_error_label.setStyleSheet(f"color: {COLORS['danger']}; font-size: 13px; font-weight: bold;")
        self.s4_error_label.setWordWrap(True)
        self.s4_error_label.setVisible(False)
        s4_layout.addWidget(self.s4_error_label)

        s4_layout.addStretch()
        self.stack.addWidget(self.s4_widget)

    # ── Step 5: DA Draft Editor ──────────────────────────────────────

    def _build_step5(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Step 5 \u2014 DA Draft Editor")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['accent']};")
        layout.addWidget(title)

        subtitle = QLabel("Review and edit every field. All data is pre-populated from previous steps.")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── Employee Info Card ──
        info_card = _card_frame()
        info_form = QFormLayout(info_card)
        info_form.setSpacing(12)
        info_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        hdr = _section_header("Employee Information")
        info_form.addRow(hdr)

        self.s5_employee = QLineEdit()
        info_form.addRow("Employee Name:", self.s5_employee)

        self.s5_position = QLineEdit()
        info_form.addRow("Position:", self.s5_position)

        self.s5_site = QLineEdit()
        info_form.addRow("Site / Location:", self.s5_site)

        self.s5_director = QLineEdit()
        info_form.addRow("Security Director:", self.s5_director)

        # Date picker with optional range (mirrors Step 1)
        s5_dates_widget = QWidget()
        s5_dates_lay = QHBoxLayout(s5_dates_widget)
        s5_dates_lay.setContentsMargins(0, 0, 0, 0)
        s5_dates_lay.setSpacing(8)

        self.s5_date_start = QDateEdit()
        self.s5_date_start.setCalendarPopup(True)
        self.s5_date_start.setDate(QDate.currentDate())
        self.s5_date_start.setDisplayFormat("yyyy-MM-dd")
        self.s5_date_start.setMinimumWidth(160)
        s5_dates_lay.addWidget(self.s5_date_start)

        self.s5_date_range_cb = QCheckBox("Date Range")
        self.s5_date_range_cb.toggled.connect(self._toggle_s5_date_range)
        s5_dates_lay.addWidget(self.s5_date_range_cb)

        self.s5_date_end_label = QLabel("through")
        self.s5_date_end_label.setVisible(False)
        s5_dates_lay.addWidget(self.s5_date_end_label)

        self.s5_date_end = QDateEdit()
        self.s5_date_end.setCalendarPopup(True)
        self.s5_date_end.setDate(QDate.currentDate())
        self.s5_date_end.setDisplayFormat("yyyy-MM-dd")
        self.s5_date_end.setMinimumWidth(160)
        self.s5_date_end.setVisible(False)
        s5_dates_lay.addWidget(self.s5_date_end)

        s5_dates_lay.addStretch()
        info_form.addRow("Date of Incident(s):", s5_dates_widget)

        layout.addWidget(info_card)

        # ── Discipline Level Card ──
        level_card = _card_frame()
        level_layout = QVBoxLayout(level_card)

        level_hdr = _section_header("Discipline Level")
        level_layout.addWidget(level_hdr)

        self.s5_level_group = QButtonGroup(self)
        level_row = QHBoxLayout()
        self._level_radios = {}
        for i, label in enumerate(["Verbal Warning", "Written Warning", "Final Warning", "Termination"]):
            rb = QRadioButton(label)
            rb.setStyleSheet(f"color: {tc('text')}; font-size: 13px; border: none; background: transparent;")
            self.s5_level_group.addButton(rb, i)
            level_row.addWidget(rb)
            self._level_radios[label] = rb
        level_row.addStretch()
        level_layout.addLayout(level_row)

        layout.addWidget(level_card)

        # ── Narrative Card ──
        narr_card = _card_frame()
        narr_layout = QVBoxLayout(narr_card)
        narr_layout.addWidget(_section_header("Incident Narrative"))

        self.s5_narrative = QTextEdit()
        self.s5_narrative.setMinimumHeight(220)
        self.s5_narrative.setPlaceholderText("CEIS-generated narrative will appear here...")
        narr_layout.addWidget(self.s5_narrative)

        layout.addWidget(narr_card)

        # ── Policy Violations Card ──
        policy_card = _card_frame()
        policy_layout = QVBoxLayout(policy_card)
        policy_layout.addWidget(_section_header("Handbook Policy Violations"))

        self.s5_citations = QTextEdit()
        self.s5_citations.setMinimumHeight(180)
        self.s5_citations.setPlaceholderText("Policy citations will be populated from CEIS analysis...")
        policy_layout.addWidget(self.s5_citations)

        layout.addWidget(policy_card)

        # ── Prior Discipline Card ──
        prior_card = _card_frame()
        prior_layout = QVBoxLayout(prior_card)
        prior_layout.addWidget(_section_header("Prior Discipline"))

        self.s5_prior = QTextEdit()
        self.s5_prior.setMinimumHeight(110)
        self.s5_prior.setPlaceholderText("Prior discipline summary...")
        prior_layout.addWidget(self.s5_prior)

        layout.addWidget(prior_card)

        # ── Coaching Card ──
        coaching_card = _card_frame()
        coaching_layout = QVBoxLayout(coaching_card)
        coaching_layout.addWidget(_section_header("Management Coaching"))

        self.s5_coaching = QTextEdit()
        self.s5_coaching.setMinimumHeight(110)
        self.s5_coaching.setPlaceholderText("Coaching details from intake...")
        coaching_layout.addWidget(self.s5_coaching)

        layout.addWidget(coaching_card)

        # ── Required Improvements Card ──
        improve_card = _card_frame()
        improve_layout = QVBoxLayout(improve_card)
        improve_layout.addWidget(_section_header("Required Improvements"))

        self.s5_improvements = QTextEdit()
        self.s5_improvements.setMinimumHeight(130)
        self.s5_improvements.setPlaceholderText("Required improvements for the employee...")
        improve_layout.addWidget(self.s5_improvements)

        layout.addWidget(improve_card)

        # ── Additional Comments Card ──
        comments_card = _card_frame()
        comments_layout = QVBoxLayout(comments_card)
        comments_layout.addWidget(_section_header("Additional Comments"))

        self.s5_comments = QTextEdit()
        self.s5_comments.setMinimumHeight(110)
        self.s5_comments.setPlaceholderText("Any additional notes or comments...")
        comments_layout.addWidget(self.s5_comments)

        layout.addWidget(comments_card)

        # ── PREVIEW + GENERATE Buttons ──
        generate_btn_layout = QHBoxLayout()
        generate_btn_layout.addStretch()

        self.btn_preview = QPushButton("  PREVIEW PDF  ")
        self.btn_preview.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.btn_preview.setFixedHeight(56)
        self.btn_preview.setMinimumWidth(220)
        self.btn_preview.setStyleSheet(f"""
            QPushButton {{
                background: {tc('card')}; color: {COLORS['accent']};
                border: 2px solid {COLORS['accent']};
                border-radius: 8px; padding: 12px 28px;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: {COLORS['accent']}; color: white;
            }}
            QPushButton:disabled {{
                background: {tc('border')}; color: {tc('text_light')};
                border-color: {tc('border')};
            }}
        """)
        self.btn_preview.clicked.connect(self._show_preview_dialog)
        generate_btn_layout.addWidget(self.btn_preview)

        generate_btn_layout.addSpacing(16)

        self.btn_generate = QPushButton("  GENERATE FINAL DA  ")
        self.btn_generate.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.btn_generate.setFixedHeight(56)
        self.btn_generate.setMinimumWidth(320)
        self.btn_generate.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                border-radius: 8px; padding: 12px 40px;
                font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: {COLORS['accent_hover']};
            }}
            QPushButton:disabled {{
                background: {tc('border')}; color: {tc('text_light')};
            }}
        """)
        self.btn_generate.clicked.connect(self._generate_final_da)
        generate_btn_layout.addWidget(self.btn_generate)

        generate_btn_layout.addStretch()
        layout.addLayout(generate_btn_layout)

        layout.addStretch()
        scroll.setWidget(container)
        self.stack.addWidget(scroll)

    # ═════════════════════════════════════════════════════════════════
    #  Data population
    # ═════════════════════════════════════════════════════════════════

    def _populate_step1_combos(self):
        """Load officers and sites into Step 1 combo boxes."""
        # Officers
        self.s1_employee.blockSignals(True)
        self.s1_employee.clear()
        try:
            officers = get_active_officers()
            for off in officers:
                name = off.get("name", "")
                if name:
                    self.s1_employee.addItem(name)
        except Exception:
            pass
        self.s1_employee.setCurrentText("")
        self.s1_employee.blockSignals(False)

        # Sites
        self.s1_site.blockSignals(True)
        self.s1_site.clear()
        try:
            sites = get_all_sites()
            for s in sites:
                name = s.get("name", "")
                if name:
                    self.s1_site.addItem(name)
        except Exception:
            pass
        self.s1_site.setCurrentText("")
        self.s1_site.blockSignals(False)

    # ═════════════════════════════════════════════════════════════════
    #  Step 1 handlers
    # ═════════════════════════════════════════════════════════════════

    def _on_employee_changed(self, text: str):
        """When employee name changes, look up attendance if Type A."""
        if not text or len(text) < 2:
            self._matched_officer = None
            self.s1_attendance_card.setVisible(False)
            return

        # Try to match an officer
        try:
            matches = search_officers(text)
        except Exception:
            matches = []

        self._matched_officer = None
        for m in matches:
            if m.get("name", "").lower() == text.lower():
                self._matched_officer = m
                break

        # If Type A attendance, show attendance card
        self._update_attendance_card()

    def _toggle_date_range(self, checked):
        """Show/hide the end date picker for date ranges (Step 1)."""
        self.s1_date_end_label.setVisible(checked)
        self.s1_date_end.setVisible(checked)

    def _toggle_s5_date_range(self, checked):
        """Show/hide the end date picker for date ranges (Step 5)."""
        self.s5_date_end_label.setVisible(checked)
        self.s5_date_end.setVisible(checked)

    def _get_s5_dates_text(self):
        """Return the Step 5 incident dates as a string."""
        start = self.s5_date_start.date().toString("yyyy-MM-dd")
        if self.s5_date_range_cb.isChecked():
            end = self.s5_date_end.date().toString("yyyy-MM-dd")
            return f"{start} through {end}"
        return start

    def _set_s5_dates_from_text(self, text):
        """Parse a date string and set the Step 5 date pickers."""
        text = text.strip()
        if not text:
            self.s5_date_start.setDate(QDate.currentDate())
            self.s5_date_range_cb.setChecked(False)
            return
        if " through " in text:
            parts = text.split(" through ")
            d1 = QDate.fromString(parts[0].strip(), "yyyy-MM-dd")
            d2 = QDate.fromString(parts[1].strip(), "yyyy-MM-dd")
            if d1.isValid():
                self.s5_date_start.setDate(d1)
            if d2.isValid():
                self.s5_date_end.setDate(d2)
            self.s5_date_range_cb.setChecked(True)
        else:
            d = QDate.fromString(text[:10], "yyyy-MM-dd")
            if d.isValid():
                self.s5_date_start.setDate(d)
            self.s5_date_range_cb.setChecked(False)

    def _get_incident_dates_text(self):
        """Return the incident dates as a string from the date pickers."""
        start = self.s1_date_start.date().toString("yyyy-MM-dd")
        if self.s1_date_range_cb.isChecked():
            end = self.s1_date_end.date().toString("yyyy-MM-dd")
            return f"{start} through {end}"
        return start

    def _set_incident_dates_from_text(self, text):
        """Parse a date string and set the date pickers accordingly."""
        text = text.strip()
        if not text:
            self.s1_date_start.setDate(QDate.currentDate())
            self.s1_date_range_cb.setChecked(False)
            return
        if " through " in text:
            parts = text.split(" through ")
            d1 = QDate.fromString(parts[0].strip(), "yyyy-MM-dd")
            d2 = QDate.fromString(parts[1].strip(), "yyyy-MM-dd")
            if d1.isValid():
                self.s1_date_start.setDate(d1)
            if d2.isValid():
                self.s1_date_end.setDate(d2)
            self.s1_date_range_cb.setChecked(True)
        else:
            d = QDate.fromString(text[:10], "yyyy-MM-dd")
            if d.isValid():
                self.s1_date_start.setDate(d)
            self.s1_date_range_cb.setChecked(False)

    def _on_incident_type_changed(self, idx):
        """Show/hide attendance card based on incident type."""
        self._update_attendance_card()

    def _update_attendance_card(self):
        """Show attendance integration card when Type A and employee matched."""
        is_type_a = "Type A" in self.s1_type.currentText()
        has_match = self._matched_officer is not None

        if is_type_a and has_match:
            self._load_attendance_data()
            self.s1_attendance_card.setVisible(True)
        elif is_type_a and self.s1_employee.currentText().strip():
            # Show card with "no record" badge
            self._show_no_attendance_record()
            self.s1_attendance_card.setVisible(True)
        else:
            self.s1_attendance_card.setVisible(False)

    def _load_attendance_data(self):
        """Load attendance data for the matched officer."""
        if not self._matched_officer:
            return

        officer_id = self._matched_officer.get("officer_id", "")
        if not officer_id:
            self._show_no_attendance_record()
            return

        try:
            from src.modules.attendance.data_manager import get_infractions_for_employee
            from src.modules.attendance.policy_engine import (
                calculate_active_points, determine_discipline_level,
                INFRACTION_TYPES, THRESHOLDS, DISCIPLINE_LABELS,
            )

            infractions = get_infractions_for_employee(officer_id)
            self._attendance_infractions = infractions

            if not infractions:
                self._show_no_attendance_record()
                return

            active_points = calculate_active_points(infractions)
            level = determine_discipline_level(active_points)
            level_label = DISCIPLINE_LABELS.get(level, level)

            # Badge
            self.s1_att_badge.setText("Record Found")
            self.s1_att_badge.setStyleSheet(f"""
                background: {COLORS['success']}; color: white;
                border-radius: 13px; padding: 2px 14px; font-weight: bold; font-size: 12px;
            """)

            # Summary
            self.s1_att_summary.setText(
                f"<b>Active Points:</b> {active_points} &nbsp;&nbsp;|&nbsp;&nbsp; "
                f"<b>Discipline Level:</b> {level_label} &nbsp;&nbsp;|&nbsp;&nbsp; "
                f"<b>Total Infractions:</b> {len(infractions)}"
            )

            # Populate table
            self.s1_att_table.setRowCount(len(infractions))
            for row_idx, inf in enumerate(infractions):
                inf_type_key = inf.get("infraction_type", "")
                type_info = INFRACTION_TYPES.get(inf_type_key, {})
                type_label = type_info.get("label", inf_type_key)

                self.s1_att_table.setItem(row_idx, 0, QTableWidgetItem(inf.get("infraction_date", "")))
                self.s1_att_table.setItem(row_idx, 1, QTableWidgetItem(type_label))
                self.s1_att_table.setItem(row_idx, 2, QTableWidgetItem(str(inf.get("points_assigned", 0))))
                active_text = "Yes" if inf.get("points_active", 0) else "No"
                self.s1_att_table.setItem(row_idx, 3, QTableWidgetItem(active_text))
                self.s1_att_table.setItem(row_idx, 4, QTableWidgetItem(inf.get("notes", "")))

            # Auto-populate prior discipline checkboxes from attendance data
            self._auto_populate_prior_discipline(active_points, level)

        except ImportError:
            self._show_no_attendance_record()
        except Exception:
            self._show_no_attendance_record()

    def _show_no_attendance_record(self):
        """Display 'No Record' state in attendance card."""
        self.s1_att_badge.setText("No Record")
        self.s1_att_badge.setStyleSheet(f"""
            background: {COLORS['warning']}; color: white;
            border-radius: 13px; padding: 2px 14px; font-weight: bold; font-size: 12px;
        """)
        self.s1_att_summary.setText("No attendance record found for this employee. Manual entry will be used.")
        self.s1_att_table.setRowCount(0)
        self.s1_att_table.setVisible(False)
        self.s1_att_table_toggle.setText("Show Infraction History")
        self._attendance_infractions = []

    def _auto_populate_prior_discipline(self, active_points: float, level: str):
        """Auto-check prior discipline boxes based on attendance record."""
        # If they have points indicating prior verbal
        if active_points >= 1.5:
            self.s1_prior_verbal_same.setChecked(True)
        # If they have points indicating prior written
        if active_points >= 6:
            self.s1_prior_written_same.setChecked(True)
        # If they have points indicating final/review
        if active_points >= 8:
            self.s1_prior_final_same.setChecked(True)

    def _toggle_att_table(self):
        """Toggle infraction history table visibility."""
        visible = not self.s1_att_table.isVisible()
        self.s1_att_table.setVisible(visible)
        self.s1_att_table_toggle.setText(
            "Hide Infraction History" if visible else "Show Infraction History"
        )

    def _on_coaching_changed(self, idx):
        """Show/hide coaching detail fields."""
        self.s1_coaching_frame.setVisible(idx == 1)

    def _on_post_orders_changed(self, idx):
        """Show/hide post order details."""
        self.s4_post_order_details.setVisible(idx == 1)

    # ═════════════════════════════════════════════════════════════════
    #  Navigation
    # ═════════════════════════════════════════════════════════════════

    def _update_nav(self):
        """Update navigation buttons and step indicator for current step."""
        step = self._current_step
        self.step_indicator.set_step(step)
        self.stack.setCurrentIndex(step)

        # Back button
        self.btn_back.setVisible(step > 0)

        # Next button text and visibility
        if step == 0:
            self.btn_next.setText("Submit Intake")
            self.btn_next.setVisible(True)
        elif step == 1:
            self.btn_next.setText("Submit Answers")
            self.btn_next.setVisible(True)
        elif step == 2:
            self.btn_next.setText("Continue")
            self.btn_next.setVisible(True)
        elif step == 3:
            self.btn_next.setText("Continue")
            self.btn_next.setVisible(True)
        elif step == 4:
            self.btn_next.setVisible(False)

    def _go_back(self):
        """Navigate to previous step."""
        if self._current_step > 0:
            self._current_step -= 1
            self._update_nav()

    def _go_next(self):
        """Navigate to next step with validation."""
        step = self._current_step

        if step == 0:
            if not self._validate_step1():
                return
            self._save_step1_data()
            self._current_step = 1
            self._update_nav()
            self._enter_step2()

        elif step == 1:
            self._save_step2_data()
            self._current_step = 2
            self._update_nav()
            self._enter_step3()

        elif step == 2:
            self._current_step = 3
            self._update_nav()

        elif step == 3:
            self._process_step4()

    # ═════════════════════════════════════════════════════════════════
    #  Step 1 validation & save
    # ═════════════════════════════════════════════════════════════════

    def _validate_step1(self) -> bool:
        """Validate required fields in step 1."""
        errors = []
        if not self.s1_employee.currentText().strip():
            errors.append("Employee Name is required.")
        if not self._get_incident_dates_text().strip():
            errors.append("Date(s) of Incident is required.")
        if not self.s1_narrative.toPlainText().strip():
            errors.append("Incident Narrative is required.")

        if errors:
            QMessageBox.warning(self, "Missing Required Fields", "\n".join(errors))
            return False
        return True

    def _save_step1_data(self):
        """Collect Step 1 data and save draft to DB."""
        coaching_occurred = self.s1_coaching.currentIndex() == 1

        self.da_data.update({
            "employee_name": self.s1_employee.currentText().strip(),
            "employee_position": self.s1_position.currentText(),
            "employee_officer_id": self._matched_officer.get("officer_id", "") if self._matched_officer else "",
            "site": self.s1_site.currentText().strip(),
            "security_director": self.s1_director.text().strip(),
            "incident_dates": self._get_incident_dates_text(),
            "violation_type": self.s1_type.currentText(),
            "incident_narrative": self.s1_narrative.toPlainText().strip(),
            "prior_verbal_same": int(self.s1_prior_verbal_same.isChecked()),
            "prior_written_same": int(self.s1_prior_written_same.isChecked()),
            "prior_final_same": int(self.s1_prior_final_same.isChecked()),
            "prior_verbal_other": int(self.s1_prior_verbal_other.isChecked()),
            "prior_written_other": int(self.s1_prior_written_other.isChecked()),
            "prior_final_other": int(self.s1_prior_final_other.isChecked()),
            "coaching_occurred": int(coaching_occurred),
            "coaching_date": self.s1_coaching_date.date().toString("yyyy-MM-dd") if coaching_occurred else "",
            "coaching_content": self.s1_coaching_content.toPlainText().strip() if coaching_occurred else "",
            "coaching_outcome": self.s1_coaching_outcome.toPlainText().strip() if coaching_occurred else "",
            "has_victim_statement": int(self.s1_victim_stmt.isChecked()),
            "has_subject_statement": int(self.s1_subject_stmt.isChecked()),
            "has_witness_statements": int(self.s1_witness_stmt.isChecked()),
            "current_step": 1,
            "status": "draft",
        })

        # Attendance data if Type A
        if "Type A" in self.da_data.get("violation_type", "") and self._attendance_infractions:
            from src.modules.attendance.policy_engine import calculate_active_points
            self.da_data["attendance_points_at_da"] = calculate_active_points(self._attendance_infractions)
            self.da_data["attendance_record_json"] = json.dumps([
                {
                    "date": inf.get("infraction_date", ""),
                    "type": inf.get("infraction_type", ""),
                    "points": inf.get("points_assigned", 0),
                    "active": inf.get("points_active", 0),
                }
                for inf in self._attendance_infractions
            ])

        # Check for duplicate DA before creating a new one
        if not self.da_id:
            dup = data_manager.check_duplicate_da(
                self.da_data.get("employee_name", ""),
                self.da_data.get("incident_dates", ""),
                self.da_data.get("violation_type", ""),
            )
            if dup:
                dup_id = dup.get("da_id", "unknown")
                dup_status = (dup.get("status", "") or "").replace("_", " ").title()
                reply = QMessageBox.warning(
                    self, "Possible Duplicate DA",
                    f"A DA already exists for this employee with the same incident "
                    f"date(s) and violation type.\n\n"
                    f"Existing DA: {dup_id}  (Status: {dup_status})\n\n"
                    f"Do you want to create a new DA anyway?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    return

        # Create or update DA in DB
        try:
            if self.da_id:
                data_manager.update_da(self.da_id, self.da_data, updated_by=self.app_state.get("username", "system"))
            else:
                self.da_id = data_manager.create_da(self.da_data, created_by=self.app_state.get("username", "system"))
                audit.log_event(
                    "DA Generator", "da_created", self.app_state.get("username", "system"),
                    details=f"New DA draft created: {self.da_id}",
                    table_name="da_records", record_id=self.da_id, action="create",
                    employee_id=self.da_data.get("employee_officer_id", ""),
                )
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Could not save DA draft: {e}")

    # ═════════════════════════════════════════════════════════════════
    #  Step 2 — Clarifying Questions
    # ═════════════════════════════════════════════════════════════════

    def _enter_step2(self):
        """Called when navigating to step 2. Use local engine for clarifying questions."""
        self.s2_success_frame.setVisible(False)
        self.s2_error_label.setVisible(False)
        self._clear_layout(self.s2_questions_layout)
        self.s2_questions_layout.addStretch()
        self._clarifying_questions = []
        self._clarifying_answers = []

        self.loading.show_with_message("Analyzing Intake")
        QTimer.singleShot(300, self._run_local_clarifying)

    def _on_clarifying_result(self, result: dict):
        """Handle API response for clarifying questions."""
        self.loading.hide_overlay()

        if not result.get("success"):
            self.s2_error_label.setText(f"API Error: {result.get('error', 'Unknown error')}")
            self.s2_error_label.setVisible(True)
            return

        content = result.get("content", "").strip()

        # Check for NO_GAPS_FOUND
        if "NO_GAPS_FOUND" in content:
            self.s2_success_frame.setVisible(True)
            self.s2_success_label.setText(
                "\u2705  No clarifying questions needed \u2014 intake is complete.\n"
                "Advancing to CEIS Engine..."
            )
            # Auto-advance to step 3 after a short delay
            QTimer.singleShot(1500, self._auto_advance_to_step3)
            return

        # Parse numbered questions
        questions = self._parse_questions(content)
        if not questions:
            # Treat the entire response as a single question
            questions = [content]

        self._clarifying_questions = questions
        self._clarifying_answers = [""] * len(questions)

        # Build question UI
        self._clear_layout(self.s2_questions_layout)

        for i, q in enumerate(questions):
            card = _card_frame()
            card_layout = QVBoxLayout(card)

            q_label = QLabel(f"Question {i + 1}")
            q_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
            q_label.setStyleSheet(f"color: {COLORS['accent']}; border: none; background: transparent;")
            card_layout.addWidget(q_label)

            q_text = QLabel(q)
            q_text.setWordWrap(True)
            q_text.setStyleSheet(f"color: {tc('text')}; font-size: 13px; border: none; background: transparent;")
            card_layout.addWidget(q_text)

            answer = QTextEdit()
            answer.setMinimumHeight(100)
            answer.setMaximumHeight(160)
            answer.setPlaceholderText("Type your answer here...")
            answer.setStyleSheet(f"font-size: 14px; padding: 6px;")
            answer.setProperty("question_idx", i)
            card_layout.addWidget(answer)

            self.s2_questions_layout.insertWidget(i, card)

        self.s2_questions_layout.addStretch()

    def _run_local_clarifying(self):
        """Run the local rule-based clarifying questions engine (offline mode)."""
        self.loading.hide_overlay()
        try:
            questions = generate_clarifying_questions(self.da_data)
        except Exception as e:
            self.s2_error_label.setText(f"Local engine error: {e}")
            self.s2_error_label.setVisible(True)
            return

        if not questions:
            # No gaps found — auto-advance
            result = {"success": True, "content": "NO_GAPS_FOUND"}
            self._on_clarifying_result(result)
        else:
            # Format as numbered list for the standard handler
            numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
            result = {"success": True, "content": numbered}
            self._on_clarifying_result(result)

    def _parse_questions(self, text: str) -> list:
        """Parse numbered questions from API response."""
        lines = text.strip().split("\n")
        questions = []
        current = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Check for numbered question pattern
            stripped = line.lstrip()
            is_numbered = False
            for prefix_len in range(1, 4):
                if len(stripped) > prefix_len + 1:
                    candidate = stripped[:prefix_len]
                    next_char = stripped[prefix_len] if prefix_len < len(stripped) else ""
                    if candidate.isdigit() and next_char in ".):":
                        is_numbered = True
                        line = stripped[prefix_len + 1:].strip()
                        break

            if is_numbered:
                if current.strip():
                    questions.append(current.strip())
                current = line
            else:
                if current:
                    current += " " + line
                else:
                    current = line

        if current.strip():
            questions.append(current.strip())

        return questions

    def _auto_advance_to_step3(self):
        """Auto-advance from step 2 to step 3."""
        self._current_step = 2
        self._update_nav()
        self._enter_step3()

    def _save_step2_data(self):
        """Collect answers from step 2 question fields."""
        answers = []
        for i in range(self.s2_questions_layout.count()):
            item = self.s2_questions_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, QFrame):
                    # Find QTextEdit inside the card
                    for child in widget.findChildren(QTextEdit):
                        answers.append(child.toPlainText().strip())

        self._clarifying_answers = answers

        # Build Q&A pairs
        qa_pairs = []
        for i, q in enumerate(self._clarifying_questions):
            a = answers[i] if i < len(answers) else ""
            qa_pairs.append({"question": q, "answer": a})

        self.da_data["clarifying_qa"] = qa_pairs
        self.da_data["current_step"] = 2

        # Save to DB
        try:
            if self.da_id:
                data_manager.update_da(self.da_id, {
                    "clarifying_qa": qa_pairs,
                    "current_step": 2,
                }, updated_by=self.app_state.get("username", "system"))
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════
    #  Step 3 — CEIS Engine Output
    # ═════════════════════════════════════════════════════════════════

    def _enter_step3(self):
        """Called when navigating to step 3. Use local engine for CEIS analysis."""
        self.s3_error_label.setVisible(False)
        self._clear_layout(self.s3_sections_layout)
        self.s3_sections_layout.addStretch()

        self.loading.show_with_message("Running CEIS Engine")
        QTimer.singleShot(300, self._run_local_ceis)

    def _run_local_ceis(self):
        """Run the local rule-based CEIS engine (offline mode)."""
        self.loading.hide_overlay()
        try:
            # Build clarifying answers list
            qa_pairs = []
            for i, q in enumerate(self._clarifying_questions):
                a = self._clarifying_answers[i] if i < len(self._clarifying_answers) else ""
                qa_pairs.append({"question": q, "answer": a})

            sections = generate_ceis_output(self.da_data, qa_pairs)

            # Convert to display-friendly format with proper section titles
            display_sections = {
                "Section 1: Incident Narrative": sections.get("narrative", ""),
                "Section 2: Policy Citations": sections.get("citations", ""),
                "Section 3: Violation Analysis": sections.get("violation_analysis", ""),
                "Section 4: Discipline Determination": sections.get("discipline_determination", ""),
                "Section 5: Risk Assessment": sections.get("risk_assessment", ""),
                "Section 6: Final Recommendation": sections.get("recommendation", ""),
            }

            self._ceis_sections = sections

            # Store in da_data
            self.da_data["ceis_narrative"] = sections.get("narrative", "")
            self.da_data["ceis_citations"] = sections.get("citations", "")
            self.da_data["ceis_violation_analysis"] = sections.get("violation_analysis", "")
            self.da_data["ceis_discipline_determination"] = sections.get("discipline_determination", "")
            self.da_data["ceis_risk_assessment"] = sections.get("risk_assessment", "")
            self.da_data["ceis_recommendation"] = sections.get("recommendation", "")
            self.da_data["current_step"] = 3

            # Save to DB
            try:
                if self.da_id:
                    update_fields = {
                        "ceis_narrative": self.da_data["ceis_narrative"],
                        "ceis_citations": self.da_data["ceis_citations"],
                        "ceis_violation_analysis": self.da_data["ceis_violation_analysis"],
                        "ceis_discipline_determination": self.da_data["ceis_discipline_determination"],
                        "ceis_risk_assessment": self.da_data["ceis_risk_assessment"],
                        "ceis_recommendation": self.da_data["ceis_recommendation"],
                        "current_step": 3,
                    }
                    data_manager.update_da(self.da_id, update_fields, updated_by=self.app_state.get("username", "system"))
            except Exception:
                pass

            # Display sections
            self._display_ceis_sections(display_sections)

        except Exception as e:
            self.s3_error_label.setText(f"Local engine error: {e}")
            self.s3_error_label.setVisible(True)

    def _display_ceis_sections(self, sections: dict):
        """Render parsed CEIS sections as cards."""
        self._clear_layout(self.s3_sections_layout)

        section_colors = [
            COLORS["accent"], COLORS["primary"], tc("info"),
            COLORS["warning"], COLORS["success"], COLORS["danger"],
        ]

        for i, (title, content) in enumerate(sections.items()):
            card = _card_frame()
            card_layout = QVBoxLayout(card)

            color = section_colors[i % len(section_colors)]

            hdr = QLabel(title)
            hdr.setFont(QFont("Segoe UI", 13, QFont.Bold))
            hdr.setStyleSheet(f"color: {color}; border: none; background: transparent;")
            card_layout.addWidget(hdr)

            browser = QTextBrowser()
            browser.setOpenExternalLinks(False)
            browser.setPlainText(content)
            browser.setMinimumHeight(100)
            browser.setMaximumHeight(300)
            browser.setStyleSheet(f"""
                QTextBrowser {{
                    background: {tc('bg')};
                    border: 1px solid {tc('border')};
                    border-radius: 4px;
                    padding: 8px;
                    color: {tc('text')};
                    font-size: 13px;
                }}
            """)
            card_layout.addWidget(browser)

            self.s3_sections_layout.insertWidget(
                self.s3_sections_layout.count() - 1, card
            )

    # ═════════════════════════════════════════════════════════════════
    #  Step 4 — Additional Policy
    # ═════════════════════════════════════════════════════════════════

    def _process_step4(self):
        """Process step 4 — check if additional policy is needed."""
        uof_yes = self.s4_uof.currentIndex() == 1
        post_yes = self.s4_post_orders.currentIndex() == 1
        post_details = self.s4_post_order_details.toPlainText().strip() if post_yes else ""
        additional_text = self.s4_additional.toPlainText().strip()

        # Save step 4 data
        self.da_data["use_of_force_applies"] = int(uof_yes)
        self.da_data["post_orders_apply"] = int(post_yes)
        self.da_data["post_order_details"] = post_details
        self.da_data["additional_violations"] = additional_text
        self.da_data["current_step"] = 4

        try:
            if self.da_id:
                data_manager.update_da(self.da_id, {
                    "use_of_force_applies": int(uof_yes),
                    "post_orders_apply": int(post_yes),
                    "post_order_details": post_details,
                    "additional_violations": additional_text,
                    "current_step": 4,
                }, updated_by=self.app_state.get("username", "system"))
        except Exception:
            pass

        if uof_yes or post_yes or additional_text:
            # Re-run API with additional policy prompt
            self._run_additional_policy(uof_yes, post_yes, post_details, additional_text)
        else:
            # Skip directly to step 5
            self._current_step = 4
            self._update_nav()
            self._populate_step5()

    def _run_additional_policy(self, uof: bool, post: bool, post_details: str, additional: str):
        """Re-run with additional policy context using local engine."""
        self.s4_error_label.setVisible(False)
        self.loading.show_with_message("Applying Additional Policies")
        QTimer.singleShot(300, lambda: self._run_local_additional_policy(uof, post, post_details, additional))

    def _run_local_additional_policy(self, uof, post, post_details, additional):
        """Apply additional policies using the local engine."""
        self.loading.hide_overlay()
        try:
            updated = generate_additional_policy_output(
                self._ceis_sections, uof, post, post_details, additional
            )
            self._ceis_sections = updated

            # Update da_data
            self.da_data["ceis_narrative"] = updated.get("narrative", "")
            self.da_data["ceis_citations"] = updated.get("citations", "")
            self.da_data["ceis_violation_analysis"] = updated.get("violation_analysis", "")
            self.da_data["ceis_risk_assessment"] = updated.get("risk_assessment", "")

            # Save and advance
            try:
                if self.da_id:
                    data_manager.update_da(self.da_id, {
                        "ceis_narrative": self.da_data["ceis_narrative"],
                        "ceis_citations": self.da_data["ceis_citations"],
                        "ceis_violation_analysis": self.da_data["ceis_violation_analysis"],
                        "ceis_risk_assessment": self.da_data["ceis_risk_assessment"],
                    }, updated_by=self.app_state.get("username", "system"))
            except Exception:
                pass

            self._current_step = 4
            self._update_nav()
            self._populate_step5()
        except Exception as e:
            self.s4_error_label.setText(f"Local engine error: {e}")
            self.s4_error_label.setVisible(True)

    # ═════════════════════════════════════════════════════════════════
    #  Step 5 — DA Draft Editor
    # ═════════════════════════════════════════════════════════════════

    def _populate_step5(self):
        """Pre-populate all Step 5 fields from accumulated da_data and CEIS output."""
        d = self.da_data

        # Employee info
        self.s5_employee.setText(d.get("employee_name", ""))
        self.s5_position.setText(d.get("employee_position", ""))
        self.s5_site.setText(d.get("site", ""))
        self.s5_director.setText(d.get("security_director", ""))
        self._set_s5_dates_from_text(d.get("incident_dates", ""))

        # CEIS sections
        self.s5_narrative.setPlainText(d.get("ceis_narrative", ""))
        self.s5_citations.setPlainText(d.get("ceis_citations", ""))

        # Prior discipline summary
        prior_parts = []
        if d.get("prior_verbal_same"):
            prior_parts.append("Verbal Warning (same issue)")
        if d.get("prior_written_same"):
            prior_parts.append("Written Warning (same issue)")
        if d.get("prior_final_same"):
            prior_parts.append("Final Warning (same issue)")
        if d.get("prior_verbal_other"):
            prior_parts.append("Verbal Warning (other issue)")
        if d.get("prior_written_other"):
            prior_parts.append("Written Warning (other issue)")
        if d.get("prior_final_other"):
            prior_parts.append("Final Warning (other issue)")

        if prior_parts:
            self.s5_prior.setPlainText("Prior discipline on record:\n- " + "\n- ".join(prior_parts))
        else:
            self.s5_prior.setPlainText("No prior discipline on record.")

        # Coaching
        if d.get("coaching_occurred"):
            coaching_text = f"Coaching occurred on {d.get('coaching_date', 'N/A')}.\n"
            coaching_text += f"Content: {d.get('coaching_content', 'N/A')}\n"
            coaching_text += f"Outcome: {d.get('coaching_outcome', 'N/A')}"
            self.s5_coaching.setPlainText(coaching_text)
        else:
            self.s5_coaching.setPlainText("No management coaching on record for this incident.")

        # Discipline level from CEIS determination
        determination = d.get("ceis_discipline_determination", "").lower()
        disc_level = ""
        if "termination" in determination:
            self._level_radios["Termination"].setChecked(True)
            disc_level = "Termination"
        elif "final" in determination:
            self._level_radios["Final Warning"].setChecked(True)
            disc_level = "Final Warning"
        elif "written" in determination:
            self._level_radios["Written Warning"].setChecked(True)
            disc_level = "Written Warning"
        elif "verbal" in determination:
            self._level_radios["Verbal Warning"].setChecked(True)
            disc_level = "Verbal Warning"

        # Required improvements — generate conduct-specific language
        violation_type = d.get("violation_type", "")
        improvements = generate_required_improvements(disc_level, violation_type)
        self.s5_improvements.setPlainText(improvements)

        # Additional comments
        self.s5_comments.setPlainText("")

    # ═════════════════════════════════════════════════════════════════
    #  Generate Final DA
    # ═════════════════════════════════════════════════════════════════

    def _collect_step5_fields(self):
        """Collect current Step 5 field values and discipline level.
        Returns (final_data, discipline_level) or (None, None) on validation failure."""
        level_map = {0: "Verbal Warning", 1: "Written Warning", 2: "Final Warning", 3: "Termination"}
        checked_id = self.s5_level_group.checkedId()
        if checked_id < 0:
            QMessageBox.warning(self, "Missing Field", "Please select a Discipline Level.")
            return None, None

        discipline_level = level_map.get(checked_id, "")
        discipline_level_db = _LEVEL_DISPLAY_TO_DB.get(discipline_level, discipline_level.lower().replace(" ", "_"))
        final_data = {
            "employee_name": self.s5_employee.text().strip(),
            "employee_position": self.s5_position.text().strip(),
            "site": self.s5_site.text().strip(),
            "security_director": self.s5_director.text().strip(),
            "incident_dates": self._get_s5_dates_text(),
            "discipline_level": discipline_level_db,
            "final_narrative": self.s5_narrative.toPlainText().strip(),
            "final_citations": self.s5_citations.toPlainText().strip(),
            "final_prior_discipline": self.s5_prior.toPlainText().strip(),
            "final_coaching": self.s5_coaching.toPlainText().strip(),
            "required_improvements": self.s5_improvements.toPlainText().strip(),
            "additional_comments": self.s5_comments.toPlainText().strip(),
        }
        return final_data, discipline_level

    # ── Preview Dialog ───────────────────────────────────────────────

    def _show_preview_dialog(self):
        """Show a formatted text preview of the DA fields before PDF generation."""
        final_data, discipline_level = self._collect_step5_fields()
        if final_data is None:
            return

        # Parse prior discipline into same/other
        prior_same_parts = []
        prior_other_parts = []
        prior_text = final_data.get("final_prior_discipline", "")
        for line in prior_text.split("\n"):
            line_s = line.strip().lstrip("- ")
            if not line_s:
                continue
            if "other" in line_s.lower():
                prior_other_parts.append(line_s)
            else:
                prior_same_parts.append(line_s)

        prior_same = "; ".join(prior_same_parts) if prior_same_parts else "None"
        prior_other = "; ".join(prior_other_parts) if prior_other_parts else "None"

        dlg = QDialog(self)
        dlg.setWindowTitle("DA Document Preview")
        dlg.resize(800, 900)
        dlg.setStyleSheet(build_dialog_stylesheet())

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title bar area
        title_bar = QWidget()
        title_bar.setStyleSheet(f"background: {COLORS['accent']}; padding: 12px;")
        title_layout = QVBoxLayout(title_bar)
        title_layout.setContentsMargins(20, 14, 20, 14)
        title_lbl = QLabel("DA Document Preview")
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_lbl.setStyleSheet("color: white; background: transparent; border: none;")
        title_layout.addWidget(title_lbl)
        outer.addWidget(title_bar)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background: {tc('bg')};")

        content = QWidget()
        clayout = QVBoxLayout(content)
        clayout.setContentsMargins(24, 16, 24, 16)
        clayout.setSpacing(14)

        def _preview_section(title_text):
            hdr = QLabel(title_text)
            hdr.setFont(QFont("Segoe UI", 12, QFont.Bold))
            hdr.setStyleSheet(f"""
                color: {COLORS['accent']}; background: transparent;
                border: none; border-bottom: 2px solid {COLORS['accent']};
                padding-bottom: 4px; margin-top: 8px;
            """)
            clayout.addWidget(hdr)

        def _preview_field(label_text, value_text):
            row = QHBoxLayout()
            lbl = QLabel(f"{label_text}")
            lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
            lbl.setStyleSheet(f"color: {tc('text_light')}; background: transparent; border: none; min-width: 140px;")
            lbl.setFixedWidth(160)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
            row.addWidget(lbl)

            val = QLabel(value_text if value_text else "(empty)")
            val.setFont(QFont("Segoe UI", 11))
            val.setStyleSheet(f"color: {tc('text')}; background: transparent; border: none;")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(val, 1)
            clayout.addLayout(row)

        def _preview_block(value_text):
            txt = QTextBrowser()
            txt.setPlainText(value_text if value_text else "(empty)")
            txt.setReadOnly(True)
            txt.setFont(QFont("Segoe UI", 11))
            txt.setStyleSheet(f"""
                QTextBrowser {{
                    background: {tc('card')}; color: {tc('text')};
                    border: 1px solid {tc('border')}; border-radius: 6px;
                    padding: 10px;
                }}
            """)
            txt.setMinimumHeight(80)
            line_count = max(4, min(15, value_text.count("\n") + 2 if value_text else 3))
            txt.setFixedHeight(line_count * 20 + 20)
            clayout.addWidget(txt)

        # ── Employee Info ──
        _preview_section("EMPLOYEE INFORMATION")
        _preview_field("Name:", final_data["employee_name"])
        _preview_field("Position:", final_data["employee_position"])
        _preview_field("Site:", final_data["site"])
        _preview_field("Supervisor:", final_data["security_director"])
        _preview_field("Date Occurred:", final_data["incident_dates"])

        # ── Discipline Level ──
        _preview_section("DISCIPLINE LEVEL")
        level_display = QLabel(f"  {discipline_level}")
        level_display.setFont(QFont("Segoe UI", 13, QFont.Bold))
        level_display.setStyleSheet(f"""
            color: white; background: {COLORS['accent']};
            border: none; border-radius: 4px; padding: 6px 14px;
        """)
        level_display.setFixedWidth(level_display.sizeHint().width() + 20)
        clayout.addWidget(level_display)

        # ── Narrative ──
        _preview_section("INCIDENT NARRATIVE")
        _preview_block(final_data["final_narrative"])

        # ── Citations ──
        _preview_section("POLICY CITATIONS")
        _preview_block(final_data["final_citations"])

        # ── Prior Discipline ──
        _preview_section("PRIOR DISCIPLINE")
        _preview_field("Same Issue:", prior_same)
        _preview_field("Other Issues:", prior_other)

        # ── Required Improvements ──
        _preview_section("REQUIRED IMPROVEMENTS")
        _preview_block(final_data["required_improvements"])

        # ── Additional Comments ──
        _preview_section("ADDITIONAL COMMENTS")
        _preview_block(final_data["additional_comments"])

        # ── Footer note ──
        note = QLabel(
            "This preview shows the text that will be filled into the Cerasus DA form. "
            "Click 'Generate PDF' to create the final document."
        )
        note.setFont(QFont("Segoe UI", 10))
        note.setStyleSheet(f"color: {tc('text_light')}; background: transparent; border: none; font-style: italic; padding-top: 10px;")
        note.setWordWrap(True)
        clayout.addWidget(note)

        clayout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # ── Bottom button bar ──
        btn_bar = QWidget()
        btn_bar.setStyleSheet(f"background: {tc('card')}; border-top: 1px solid {tc('border')};")
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(20, 12, 20, 12)

        btn_close = QPushButton("Close")
        btn_close.setFont(QFont("Segoe UI", 12))
        btn_close.setFixedHeight(42)
        btn_close.setMinimumWidth(120)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: {tc('card')}; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 6px;
                padding: 8px 24px;
            }}
            QPushButton:hover {{
                background: {tc('border')};
            }}
        """)
        btn_close.clicked.connect(dlg.reject)

        btn_gen = QPushButton("  Generate PDF  ")
        btn_gen.setFont(QFont("Segoe UI", 13, QFont.Bold))
        btn_gen.setFixedHeight(42)
        btn_gen.setMinimumWidth(180)
        btn_gen.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                border-radius: 6px; padding: 8px 28px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {COLORS['accent_hover']};
            }}
        """)
        btn_gen.clicked.connect(lambda: (dlg.accept(),))

        btn_layout.addWidget(btn_close)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_gen)
        outer.addWidget(btn_bar)

        result = dlg.exec()
        if result == QDialog.Accepted:
            self._generate_final_da()

    def _generate_final_da(self):
        """Collect all fields, save, generate PDF, and write back to attendance module."""
        # Determine discipline level from radio buttons
        level_map = {0: "Verbal Warning", 1: "Written Warning", 2: "Final Warning", 3: "Termination"}
        checked_id = self.s5_level_group.checkedId()
        if checked_id < 0:
            QMessageBox.warning(self, "Missing Field", "Please select a Discipline Level.")
            return

        discipline_level = level_map.get(checked_id, "")
        discipline_level_db = _LEVEL_DISPLAY_TO_DB.get(discipline_level, discipline_level.lower().replace(" ", "_"))

        # Collect all field values into payload
        final_data = {
            "employee_name": self.s5_employee.text().strip(),
            "employee_position": self.s5_position.text().strip(),
            "site": self.s5_site.text().strip(),
            "security_director": self.s5_director.text().strip(),
            "incident_dates": self._get_s5_dates_text(),
            "discipline_level": discipline_level_db,
            "final_narrative": self.s5_narrative.toPlainText().strip(),
            "final_citations": self.s5_citations.toPlainText().strip(),
            "final_prior_discipline": self.s5_prior.toPlainText().strip(),
            "final_coaching": self.s5_coaching.toPlainText().strip(),
            "required_improvements": self.s5_improvements.toPlainText().strip(),
            "additional_comments": self.s5_comments.toPlainText().strip(),
            "status": "completed",
            "current_step": 5,
        }

        # Build JSON payload
        cerasus_da_payload = {
            "CERASUS_DA_PAYLOAD": {
                "da_id": self.da_id,
                "generated_at": datetime.now().isoformat(),
                "employee": {
                    "name": final_data["employee_name"],
                    "position": final_data["employee_position"],
                    "officer_id": self.da_data.get("employee_officer_id", ""),
                },
                "incident": {
                    "site": final_data["site"],
                    "security_director": final_data["security_director"],
                    "dates": final_data["incident_dates"],
                    "type": self.da_data.get("violation_type", ""),
                    "narrative": final_data["final_narrative"],
                },
                "discipline": {
                    "level": discipline_level,
                    "citations": final_data["final_citations"],
                    "prior_discipline": final_data["final_prior_discipline"],
                    "coaching": final_data["final_coaching"],
                    "required_improvements": final_data["required_improvements"],
                    "additional_comments": final_data["additional_comments"],
                },
                "attendance_data": {
                    "points_at_da": self.da_data.get("attendance_points_at_da", 0),
                    "record_json": self.da_data.get("attendance_record_json", ""),
                },
            }
        }

        final_data["da_payload"] = json.dumps(cerasus_da_payload)

        # Update DA record
        try:
            if self.da_id:
                data_manager.update_da(self.da_id, final_data, updated_by=self.app_state.get("username", "system"))
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save DA record: {e}")
            return

        # Generate PDF
        pdf_path = self._generate_pdf(final_data, discipline_level)
        if not pdf_path:
            return

        # Save PDF filename to record
        try:
            if self.da_id:
                data_manager.update_da(self.da_id, {
                    "pdf_filename": os.path.basename(pdf_path),
                }, updated_by=self.app_state.get("username", "system"))
        except Exception:
            pass

        # Log to audit
        try:
            audit.log_event(
                "DA Generator", "da_completed", self.app_state.get("username", "system"),
                details=f"DA completed: {self.da_id}, Level: {discipline_level}, PDF: {os.path.basename(pdf_path)}",
                table_name="da_records", record_id=self.da_id or "", action="complete",
                employee_id=self.da_data.get("employee_officer_id", ""),
            )
        except Exception:
            pass

        # Write back to attendance module if Type A
        self._writeback_attendance(discipline_level)

        # Show success dialog with Send Email option
        msg = QMessageBox(self)
        msg.setWindowTitle("DA Generated Successfully")
        msg.setIcon(QMessageBox.Information)
        msg.setText(
            f"Disciplinary Action document has been generated.\n\n"
            f"DA ID: {self.da_id}\n"
            f"Discipline Level: {discipline_level}\n"
            f"PDF saved to:\n{pdf_path}"
        )
        msg.addButton(QMessageBox.Ok)
        email_btn = msg.addButton("Send via Email", QMessageBox.ActionRole)
        email_btn.setStyleSheet(btn_style(COLORS["info"]))
        email_btn.setCursor(Qt.PointingHandCursor)
        msg.exec()

        if msg.clickedButton() == email_btn:
            self._send_da_email(
                employee_name=final_data.get("employee_name", ""),
                discipline_level=discipline_level,
                site=final_data.get("site", ""),
                incident_dates=final_data.get("incident_dates", ""),
                pdf_path=pdf_path,
            )

    def _send_da_email(self, employee_name: str, discipline_level: str,
                       site: str, incident_dates: str, pdf_path: str):
        """Open the default email client with DA details pre-filled and copy PDF path to clipboard."""
        from urllib.parse import quote

        subject = f"Disciplinary Action - {employee_name} - {discipline_level}"
        body = (
            f"Please find the attached Disciplinary Action document for {employee_name}.\n\n"
            f"Discipline Level: {discipline_level}\n"
            f"Date: {incident_dates}\n"
            f"Site: {site}\n\n"
            f"This document requires review and signature."
        )

        mailto_url = f"mailto:?subject={quote(subject)}&body={quote(body)}"
        QDesktopServices.openUrl(QUrl(mailto_url))

        # Copy PDF path to clipboard
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(pdf_path)

        QMessageBox.information(
            self, "Email Client Opened",
            f"Email client opened. Please attach the PDF file from:\n\n"
            f"{pdf_path}\n\n"
            f"The file path has been copied to your clipboard.",
        )

    def _generate_pdf(self, final_data: dict, discipline_level: str) -> str:
        """Fill the official Cerasus DA PDF form. Returns file path or empty string on failure."""
        try:
            from src.modules.da_generator.pdf_filler import fill_da_pdf, generate_da_filename
            from src.config import REPORTS_DIR, ensure_directories

            ensure_directories()

            # Build the issue tag for filename
            violation_type = self.da_data.get("violation_type", "")
            if "Type A" in violation_type:
                issue = "Attendance"
            elif "Type B" in violation_type:
                issue = "Conduct"
            elif "Type C" in violation_type:
                issue = "Review"
            else:
                issue = "DA"

            filename = generate_da_filename(
                final_data.get("employee_name", "Unknown"),
                discipline_level,
                issue,
            )
            output_path = os.path.join(REPORTS_DIR, filename)

            # Build the prior discipline text for same vs other
            prior_same_parts = []
            prior_other_parts = []
            prior_text = final_data.get("final_prior_discipline", "")
            for line in prior_text.split("\n"):
                line = line.strip().lstrip("- ")
                if not line:
                    continue
                if "same issue" in line.lower():
                    prior_same_parts.append(line)
                elif "other" in line.lower():
                    prior_other_parts.append(line)
                else:
                    prior_same_parts.append(line)

            # Map final_data to PDF field format
            pdf_data = {
                "employee_name": final_data.get("employee_name", ""),
                "position": final_data.get("employee_position", ""),
                "site": final_data.get("site", ""),
                "supervisor": final_data.get("security_director", ""),
                "date_occurred": final_data.get("incident_dates", ""),
                "discipline_level": discipline_level,
                "narrative": final_data.get("final_narrative", ""),
                "citations": final_data.get("final_citations", ""),
                "prior_same": "; ".join(prior_same_parts) if prior_same_parts else "None",
                "prior_other": "; ".join(prior_other_parts) if prior_other_parts else "None",
                "improvements": final_data.get("required_improvements", ""),
                "additional_comments": final_data.get("additional_comments", ""),
            }

            filepath = fill_da_pdf(output_path, pdf_data)
            return filepath

        except Exception as e:
            QMessageBox.critical(self, "PDF Error", f"Could not generate PDF: {e}")
            return ""

    def _writeback_attendance(self, discipline_level: str):
        """Write DA results back to attendance module for Type A incidents."""
        violation_type = self.da_data.get("violation_type", "")
        officer_id = self.da_data.get("employee_officer_id", "")

        if "Type A" not in violation_type or not officer_id:
            return

        try:
            # Map discipline level to attendance module format
            level_map = {
                "Verbal Warning": "Verbal Warning",
                "Written Warning": "Written Warning",
                "Final Warning": "Final Warning",
                "Termination": "Termination Eligible",
            }
            att_level = level_map.get(discipline_level, discipline_level)

            # Update officer's discipline info
            update_officer(officer_id, {
                "discipline_level": att_level,
            }, updated_by="DA Generator")

            # Log the DA action in audit
            audit.log_event(
                "DA Generator", "attendance_writeback", self.app_state.get("username", "system"),
                details=f"Updated officer {officer_id} discipline to '{att_level}' via DA {self.da_id}",
                table_name="officers", record_id=officer_id, action="update",
                employee_id=officer_id,
            )

        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════
    #  Utility
    # ═════════════════════════════════════════════════════════════════

    def _clear_layout(self, layout):
        """Remove all widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def resizeEvent(self, event):
        """Keep loading overlay sized to this widget."""
        super().resizeEvent(event)
        if hasattr(self, "loading"):
            self.loading.setGeometry(self.rect())

    # ═════════════════════════════════════════════════════════════════
    #  refresh() — called by hub shell
    # ═════════════════════════════════════════════════════════════════

    def refresh(self):
        """Reset the wizard to step 1 for a fresh DA."""
        # Reset state
        self.da_data = {}
        self.da_id = None
        self._matched_officer = None
        self._attendance_infractions = []
        self._clarifying_questions = []
        self._clarifying_answers = []
        self._ceis_sections = {}
        self._current_step = 0

        # Reset step 1 fields
        self._populate_step1_combos()
        self.s1_employee.setCurrentText("")
        self.s1_position.setCurrentIndex(0)
        self.s1_site.setCurrentText("")
        self.s1_director.clear()
        self.s1_date_start.setDate(QDate.currentDate())
        self.s1_date_end.setDate(QDate.currentDate())
        self.s1_date_range_cb.setChecked(False)
        self.s1_type.setCurrentIndex(0)
        self.s1_narrative.clear()

        self.s1_prior_verbal_same.setChecked(False)
        self.s1_prior_written_same.setChecked(False)
        self.s1_prior_final_same.setChecked(False)
        self.s1_prior_verbal_other.setChecked(False)
        self.s1_prior_written_other.setChecked(False)
        self.s1_prior_final_other.setChecked(False)

        self.s1_coaching.setCurrentIndex(0)
        self.s1_coaching_frame.setVisible(False)
        self.s1_coaching_content.clear()
        self.s1_coaching_outcome.clear()

        self.s1_victim_stmt.setChecked(False)
        self.s1_subject_stmt.setChecked(False)
        self.s1_witness_stmt.setChecked(False)

        self.s1_attendance_card.setVisible(False)
        self.s1_att_table.setRowCount(0)
        self.s1_att_table.setVisible(False)
        self.s1_att_table_toggle.setText("Show Infraction History")
        self.s1_att_override.setChecked(False)

        # Reset step 2
        self.s2_success_frame.setVisible(False)
        self.s2_error_label.setVisible(False)
        self._clear_layout(self.s2_questions_layout)
        self.s2_questions_layout.addStretch()

        # Reset step 3
        self.s3_error_label.setVisible(False)
        self._clear_layout(self.s3_sections_layout)
        self.s3_sections_layout.addStretch()

        # Reset step 4
        self.s4_uof.setCurrentIndex(0)
        self.s4_post_orders.setCurrentIndex(0)
        self.s4_post_order_details.clear()
        self.s4_post_order_details.setVisible(False)
        self.s4_additional.clear()
        self.s4_error_label.setVisible(False)

        # Reset step 5
        self.s5_employee.clear()
        self.s5_position.clear()
        self.s5_site.clear()
        self.s5_director.clear()
        self.s5_date_start.setDate(QDate.currentDate())
        self.s5_date_end.setDate(QDate.currentDate())
        self.s5_date_range_cb.setChecked(False)
        self.s5_narrative.clear()
        self.s5_citations.clear()
        self.s5_prior.clear()
        self.s5_coaching.clear()
        self.s5_improvements.clear()
        self.s5_comments.clear()
        checked = self.s5_level_group.checkedButton()
        if checked:
            self.s5_level_group.setExclusive(False)
            checked.setChecked(False)
            self.s5_level_group.setExclusive(True)

        # Navigate to step 1
        self._current_step = 0
        self._update_nav()

    def pre_populate_from_attendance(self, officer_data: dict, infraction_data: dict, active_points: float):
        """Pre-populate wizard Step 1 from attendance module infraction data.

        Called when a new infraction crosses a discipline threshold and the user
        chooses to generate a DA document.

        Args:
            officer_data: Officer record dict (name, officer_id, job_title, site, etc.)
            infraction_data: Dict with infraction_type, infraction_date, type_label, points.
            active_points: The employee's current active point total.
        """
        # Populate combos first so employee names and sites are available
        self._populate_step1_combos()

        # Reset wizard state for a fresh DA (without calling full refresh which clears combos)
        self.da_data = {}
        self.da_id = None
        self._clarifying_questions = []
        self._clarifying_answers = []
        self._ceis_sections = {}
        self._current_step = 0

        # Set employee name
        officer_name = officer_data.get("name", "")
        idx = self.s1_employee.findText(officer_name)
        if idx >= 0:
            self.s1_employee.setCurrentIndex(idx)
        else:
            self.s1_employee.setCurrentText(officer_name)

        # Set the matched officer so attendance card loads
        self._matched_officer = officer_data

        # Set position
        job_title = officer_data.get("job_title", "")
        if job_title:
            pos_idx = self.s1_position.findText(job_title)
            if pos_idx >= 0:
                self.s1_position.setCurrentIndex(pos_idx)

        # Set site
        site = officer_data.get("site", "")
        if site:
            site_idx = self.s1_site.findText(site)
            if site_idx >= 0:
                self.s1_site.setCurrentIndex(site_idx)
            else:
                self.s1_site.setCurrentText(site)

        # Set incident type to Type A -- Attendance
        type_idx = self.s1_type.findText("Type A \u2014 Attendance")
        if type_idx >= 0:
            self.s1_type.setCurrentIndex(type_idx)

        # Set incident date
        inf_date = infraction_data.get("infraction_date", "")
        if inf_date:
            self._set_incident_dates_from_text(inf_date)

        # Build a narrative from the infraction
        type_label = infraction_data.get("type_label", infraction_data.get("infraction_type", ""))
        pts = infraction_data.get("points", 0)
        from src.modules.attendance.policy_engine import determine_discipline_level, DISCIPLINE_LABELS
        level = determine_discipline_level(active_points)
        level_label = DISCIPLINE_LABELS.get(level, level)
        self.s1_narrative.setPlainText(
            f"Attendance infraction: {type_label} ({pts} points) on {inf_date}.\n"
            f"Employee currently has {active_points:.1f} active points, "
            f"triggering {level_label} under the progressive discipline policy."
        )

        # Load attendance data into the attendance card
        self._update_attendance_card()

        # Ensure we are on step 1
        self._current_step = 0
        self._update_nav()

    # ═════════════════════════════════════════════════════════════════
    #  load_from_record — Resume a saved draft
    # ═════════════════════════════════════════════════════════════════

    def load_from_record(self, da_record: dict):
        """Load a saved DA record into the wizard and jump to the last completed step.

        Called by the history page's Resume Draft action to continue editing a
        previously saved draft.
        """
        # Reset wizard state
        self.da_data = dict(da_record)
        self.da_id = da_record.get("da_id")
        self._matched_officer = None
        self._clarifying_questions = []
        self._clarifying_answers = []
        self._ceis_sections = {}

        # Populate step-1 combos so names/sites are available
        self._populate_step1_combos()

        # ── Populate Step 1 fields from the record ──
        emp_name = da_record.get("employee_name", "")
        idx = self.s1_employee.findText(emp_name)
        if idx >= 0:
            self.s1_employee.setCurrentIndex(idx)
        else:
            self.s1_employee.setCurrentText(emp_name)

        position = da_record.get("employee_position", "")
        if position:
            pos_idx = self.s1_position.findText(position)
            if pos_idx >= 0:
                self.s1_position.setCurrentIndex(pos_idx)

        site = da_record.get("site", "")
        if site:
            site_idx = self.s1_site.findText(site)
            if site_idx >= 0:
                self.s1_site.setCurrentIndex(site_idx)
            else:
                self.s1_site.setCurrentText(site)

        self.s1_director.setText(da_record.get("security_director", ""))

        dates_text = da_record.get("incident_dates", "")
        if dates_text:
            self._set_incident_dates_from_text(dates_text)

        # Incident type
        vtype = da_record.get("violation_type", "")
        if vtype:
            type_idx = self.s1_type.findText(vtype)
            if type_idx >= 0:
                self.s1_type.setCurrentIndex(type_idx)

        self.s1_narrative.setPlainText(da_record.get("incident_narrative", ""))

        # Prior discipline checkboxes
        self.s1_prior_verbal_same.setChecked(bool(da_record.get("prior_verbal_same", 0)))
        self.s1_prior_written_same.setChecked(bool(da_record.get("prior_written_same", 0)))
        self.s1_prior_final_same.setChecked(bool(da_record.get("prior_final_same", 0)))
        self.s1_prior_verbal_other.setChecked(bool(da_record.get("prior_verbal_other", 0)))
        self.s1_prior_written_other.setChecked(bool(da_record.get("prior_written_other", 0)))
        self.s1_prior_final_other.setChecked(bool(da_record.get("prior_final_other", 0)))

        # Coaching
        coaching = bool(da_record.get("coaching_occurred", 0))
        self.s1_coaching.setCurrentIndex(1 if coaching else 0)
        self.s1_coaching_frame.setVisible(coaching)
        if coaching:
            cdate = da_record.get("coaching_date", "")
            if cdate:
                d = QDate.fromString(cdate[:10], "yyyy-MM-dd")
                if d.isValid():
                    self.s1_coaching_date.setDate(d)
            self.s1_coaching_content.setPlainText(da_record.get("coaching_content", ""))
            self.s1_coaching_outcome.setPlainText(da_record.get("coaching_outcome", ""))

        # Statements
        self.s1_victim_stmt.setChecked(bool(da_record.get("has_victim_statement", 0)))
        self.s1_subject_stmt.setChecked(bool(da_record.get("has_subject_statement", 0)))
        self.s1_witness_stmt.setChecked(bool(da_record.get("has_witness_statements", 0)))

        # ── Populate Step 5 fields if CEIS output exists ──
        if da_record.get("ceis_narrative") or da_record.get("final_narrative"):
            self.s5_employee.setText(emp_name)
            self.s5_position.setText(position)
            self.s5_site.setText(site)
            self.s5_director.setText(da_record.get("security_director", ""))
            if dates_text:
                self._set_s5_dates_from_text(dates_text)
            self.s5_narrative.setPlainText(
                da_record.get("final_narrative", "") or da_record.get("ceis_narrative", ""))
            self.s5_citations.setPlainText(
                da_record.get("final_citations", "") or da_record.get("ceis_citations", ""))
            self.s5_prior.setPlainText(da_record.get("final_prior_discipline", ""))
            self.s5_coaching.setPlainText(da_record.get("final_coaching", ""))
            self.s5_improvements.setPlainText(da_record.get("required_improvements", ""))
            self.s5_comments.setPlainText(da_record.get("additional_comments", ""))

            # Set discipline level radio
            level_db = da_record.get("discipline_level", "")
            level_display_map = {v: k for k, v in _LEVEL_DISPLAY_TO_DB.items()}
            level_display = level_display_map.get(level_db, "")
            if level_display and level_display in self._level_radios:
                self._level_radios[level_display].setChecked(True)

        # ── Jump to the last completed step ──
        saved_step = int(da_record.get("current_step", 1))
        # current_step in DB is 1-indexed (1..5), _current_step is 0-indexed (0..4)
        # Jump to the saved step minus 1, capped at step 4 (step 5 in DB)
        target_step = max(0, min(saved_step - 1, 4))
        self._current_step = target_step
        self._update_nav()
