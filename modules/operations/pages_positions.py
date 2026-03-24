"""
Cerasus Hub -- Operations Module: Open Positions Tracker Page
Full-featured position pipeline tracker with KPI cards, pipeline visualization,
sortable table, candidate management, and CSV export.
"""

import csv
import io
import secrets
from datetime import datetime, date as dt_date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QComboBox, QMessageBox, QFormLayout, QTextEdit, QLineEdit,
    QAbstractItemView, QDialog, QDialogButtonBox, QCheckBox,
    QScrollArea, QGroupBox, QGridLayout, QFileDialog, QSizePolicy,
    QDateEdit,
)
from PySide6.QtCore import Qt, QSize, QDate
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush

from src.config import (
    COLORS, DARK_COLORS, ROLE_ADMIN, ROLE_STANDARD,
    build_dialog_stylesheet, tc, _is_dark, btn_style,
)
from src.modules.operations import data_manager
from src import audit


# ── Constants ─────────────────────────────────────────────────────────

PIPELINE_STAGES = data_manager.POSITION_PIPELINE  # ["Open", "Background Check", ...]

PIPELINE_COLORS = {
    "Open": "#EF4444",
    "Background Check": "#F59E0B",
    "Training (OJT)": "#3B82F6",
    "Job Offer": "#8B5CF6",
    "Company Orientation": "#06B6D4",
    "Filled": "#10B981",
}

SHIFT_OPTIONS = ["1st Shift", "2nd Shift", "3rd Shift", "Weekend", "Flex"]

CANDIDATE_SOURCES = ["Indeed", "Referral", "Walk-in", "Other"]

CANDIDATE_STAGES = [
    "Applied", "Phone Screen", "Interview", "Offer", "Hired", "Rejected",
]

DAYS_OF_WEEK = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


# ════════════════════════════════════════════════════════════════════════
# Pipeline Stage Visual Widget
# ════════════════════════════════════════════════════════════════════════

class PipelineVisualWidget(QWidget):
    """Horizontal bar showing pipeline stages as connected colored segments."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts = {}  # stage -> count
        self.setMinimumHeight(64)
        self.setMaximumHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_counts(self, counts: dict):
        self._counts = counts
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width() - 20
        h = self.height()
        x_start = 10
        bar_h = 36
        bar_y = (h - bar_h) // 2

        total = sum(self._counts.get(s, 0) for s in PIPELINE_STAGES)
        n_stages = len(PIPELINE_STAGES)

        # Draw each segment with equal width (visual clarity over proportionality)
        seg_w = w / n_stages if n_stages else w

        for i, stage in enumerate(PIPELINE_STAGES):
            count = self._counts.get(stage, 0)
            color = PIPELINE_COLORS.get(stage, "#6B7280")
            x = x_start + i * seg_w

            # Draw segment rectangle
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(color)))

            if i == 0:
                # First segment: rounded left corners
                painter.drawRoundedRect(int(x), bar_y, int(seg_w) + 1, bar_h, 6, 6)
                # Cover right rounding
                painter.drawRect(int(x + seg_w - 6), bar_y, 7, bar_h)
            elif i == n_stages - 1:
                # Last segment: rounded right corners
                painter.drawRoundedRect(int(x), bar_y, int(seg_w), bar_h, 6, 6)
                # Cover left rounding
                painter.drawRect(int(x), bar_y, 7, bar_h)
            else:
                painter.drawRect(int(x), bar_y, int(seg_w) + 1, bar_h)

            # Draw stage name + count centered in segment
            painter.setPen(QPen(QColor("white")))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            text = f"{stage}\n{count}"
            text_rect = painter.boundingRect(
                int(x), bar_y, int(seg_w), bar_h, Qt.AlignCenter, stage
            )
            # Draw name
            painter.drawText(
                int(x), bar_y + 2, int(seg_w), bar_h // 2,
                Qt.AlignCenter, stage,
            )
            # Draw count
            painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
            painter.drawText(
                int(x), bar_y + bar_h // 2 - 2, int(seg_w), bar_h // 2,
                Qt.AlignCenter, str(count),
            )

        painter.end()


# ════════════════════════════════════════════════════════════════════════
# Candidate Tracker Dialog
# ════════════════════════════════════════════════════════════════════════

class CandidateDialog(QDialog):
    """Dialog for managing candidates for a specific position."""

    def __init__(self, parent, position: dict, can_edit: bool = False):
        super().__init__(parent)
        self.position = position
        self.can_edit = can_edit
        self.position_id = position.get("position_id", "")
        self.setWindowTitle(
            f"Candidates - {position.get('position_title', '')} @ {position.get('site_name', '')}"
        )
        self.setMinimumSize(820, 560)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        hdr = QLabel(f"Candidates for: {self.position.get('position_title', '')}")
        hdr.setFont(QFont("Segoe UI", 16, QFont.Bold))
        hdr.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(hdr)

        # Candidate table
        self.cand_table = QTableWidget(0, 8)
        self.cand_table.setHorizontalHeaderLabels([
            "Name", "Phone", "Email", "Source", "Stage",
            "Interview Date", "Notes", "Actions",
        ])
        hdr_view = self.cand_table.horizontalHeader()
        hdr_view.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 8):
            hdr_view.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr_view.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['info']};
                color: white; font-weight: 600; font-size: 13px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS.get('primary_light', '#252540')};
            }}
        """)
        self.cand_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cand_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cand_table.setAlternatingRowColors(True)
        self.cand_table.verticalHeader().setVisible(False)
        layout.addWidget(self.cand_table)

        # Add candidate form (only if editable)
        if self.can_edit:
            form_group = QGroupBox("Add Candidate")
            form_group.setStyleSheet(f"""
                QGroupBox {{
                    font-weight: 600; font-size: 14px; color: {tc('text')};
                    border: 1px solid {tc('border')}; border-radius: 8px;
                    margin-top: 8px; padding-top: 20px; background: {tc('card')};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin; left: 16px; padding: 0 6px;
                }}
            """)
            form_lay = QGridLayout(form_group)
            form_lay.setSpacing(8)

            form_lay.addWidget(QLabel("Name:"), 0, 0)
            self.cand_name = QLineEdit()
            self.cand_name.setPlaceholderText("Candidate name")
            form_lay.addWidget(self.cand_name, 0, 1)

            form_lay.addWidget(QLabel("Phone:"), 0, 2)
            self.cand_phone = QLineEdit()
            self.cand_phone.setPlaceholderText("Phone number")
            form_lay.addWidget(self.cand_phone, 0, 3)

            form_lay.addWidget(QLabel("Email:"), 1, 0)
            self.cand_email = QLineEdit()
            self.cand_email.setPlaceholderText("Email address")
            form_lay.addWidget(self.cand_email, 1, 1)

            form_lay.addWidget(QLabel("Source:"), 1, 2)
            self.cand_source = QComboBox()
            self.cand_source.addItems(CANDIDATE_SOURCES)
            form_lay.addWidget(self.cand_source, 1, 3)

            form_lay.addWidget(QLabel("Stage:"), 2, 0)
            self.cand_stage = QComboBox()
            self.cand_stage.addItems(CANDIDATE_STAGES)
            form_lay.addWidget(self.cand_stage, 2, 1)

            form_lay.addWidget(QLabel("Interview Date:"), 2, 2)
            self.cand_interview = QLineEdit()
            self.cand_interview.setPlaceholderText("YYYY-MM-DD")
            form_lay.addWidget(self.cand_interview, 2, 3)

            form_lay.addWidget(QLabel("Notes:"), 3, 0)
            self.cand_notes = QLineEdit()
            self.cand_notes.setPlaceholderText("Optional notes")
            form_lay.addWidget(self.cand_notes, 3, 1, 1, 3)

            btn_add = QPushButton("Add Candidate")
            btn_add.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS.get("accent_hover", COLORS["accent"])))
            btn_add.clicked.connect(self._add_candidate)
            form_lay.addWidget(btn_add, 4, 0, 1, 4)

            layout.addWidget(form_group)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(btn_style(tc("info"), "white", tc("primary")))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def _load(self):
        candidates = data_manager.get_candidates(self.position_id)
        self.cand_table.setRowCount(len(candidates))
        for i, c in enumerate(candidates):
            self.cand_table.setItem(i, 0, QTableWidgetItem(c.get("candidate_name", "")))
            self.cand_table.setItem(i, 1, QTableWidgetItem(c.get("phone", "")))
            self.cand_table.setItem(i, 2, QTableWidgetItem(c.get("email", "")))
            self.cand_table.setItem(i, 3, QTableWidgetItem(c.get("source", "")))

            # Stage badge
            stage = c.get("stage", "Applied")
            stage_item = QTableWidgetItem(stage)
            stage_item.setTextAlignment(Qt.AlignCenter)
            stage_color = _candidate_stage_color(stage)
            stage_item.setForeground(QColor(stage_color))
            stage_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.cand_table.setItem(i, 4, stage_item)

            self.cand_table.setItem(i, 5, QTableWidgetItem(c.get("interview_date", "")))
            self.cand_table.setItem(i, 6, QTableWidgetItem(c.get("notes", "")))

            # Actions
            if self.can_edit:
                actions_w = QWidget()
                actions_lay = QHBoxLayout(actions_w)
                actions_lay.setContentsMargins(4, 2, 4, 2)
                actions_lay.setSpacing(4)

                btn_edit = QPushButton("Edit")
                btn_edit.setFixedSize(52, 28)
                btn_edit.setStyleSheet(btn_style(tc("info"), "white"))
                cid = c.get("candidate_id", "")
                btn_edit.clicked.connect(lambda checked, _cid=cid: self._edit_candidate(_cid))
                actions_lay.addWidget(btn_edit)

                btn_del = QPushButton("Del")
                btn_del.setFixedSize(44, 28)
                btn_del.setStyleSheet(btn_style(COLORS["danger"], "white"))
                btn_del.clicked.connect(lambda checked, _cid=cid: self._delete_candidate(_cid))
                actions_lay.addWidget(btn_del)

                self.cand_table.setCellWidget(i, 7, actions_w)
            else:
                self.cand_table.setItem(i, 7, QTableWidgetItem(""))

            self.cand_table.setRowHeight(i, 40)

    def _add_candidate(self):
        name = self.cand_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Info", "Candidate name is required.")
            return
        username = _get_username(self)
        data_manager.create_candidate({
            "position_id": self.position_id,
            "candidate_name": name,
            "phone": self.cand_phone.text().strip(),
            "email": self.cand_email.text().strip(),
            "source": self.cand_source.currentText(),
            "stage": self.cand_stage.currentText(),
            "interview_date": self.cand_interview.text().strip(),
            "notes": self.cand_notes.text().strip(),
            "created_by": username,
        })
        audit.log("operations", "candidate_created", username,
                  f"Candidate '{name}' added to position '{self.position.get('position_title', '')}'")
        # Clear form
        self.cand_name.clear()
        self.cand_phone.clear()
        self.cand_email.clear()
        self.cand_interview.clear()
        self.cand_notes.clear()
        self.cand_source.setCurrentIndex(0)
        self.cand_stage.setCurrentIndex(0)
        self._load()

    def _edit_candidate(self, candidate_id: str):
        candidates = data_manager.get_candidates(self.position_id)
        cand = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
        if not cand:
            return
        dlg = EditCandidateDialog(self, cand)
        if dlg.exec() == QDialog.Accepted:
            updates = dlg.get_data()
            data_manager.update_candidate(candidate_id, updates)
            username = _get_username(self)
            audit.log("operations", "candidate_updated", username,
                      f"Candidate '{cand.get('candidate_name', '')}' updated")
            self._load()

    def _delete_candidate(self, candidate_id: str):
        reply = QMessageBox.question(
            self, "Delete Candidate",
            "Are you sure you want to delete this candidate?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            data_manager.delete_candidate(candidate_id)
            username = _get_username(self)
            audit.log("operations", "candidate_deleted", username,
                      f"Candidate deleted from position '{self.position.get('position_title', '')}'")
            self._load()


class EditCandidateDialog(QDialog):
    """Simple edit dialog for a candidate record."""

    def __init__(self, parent, candidate: dict):
        super().__init__(parent)
        self.setWindowTitle("Edit Candidate")
        self.setMinimumWidth(440)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.candidate = candidate
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        self.name_edit = QLineEdit(self.candidate.get("candidate_name", ""))
        layout.addRow("Name:", self.name_edit)

        self.phone_edit = QLineEdit(self.candidate.get("phone", ""))
        layout.addRow("Phone:", self.phone_edit)

        self.email_edit = QLineEdit(self.candidate.get("email", ""))
        layout.addRow("Email:", self.email_edit)

        self.source_combo = QComboBox()
        self.source_combo.addItems(CANDIDATE_SOURCES)
        idx = CANDIDATE_SOURCES.index(self.candidate.get("source", "Other")) if self.candidate.get("source", "Other") in CANDIDATE_SOURCES else 0
        self.source_combo.setCurrentIndex(idx)
        layout.addRow("Source:", self.source_combo)

        self.stage_combo = QComboBox()
        self.stage_combo.addItems(CANDIDATE_STAGES)
        sidx = CANDIDATE_STAGES.index(self.candidate.get("stage", "Applied")) if self.candidate.get("stage", "Applied") in CANDIDATE_STAGES else 0
        self.stage_combo.setCurrentIndex(sidx)
        layout.addRow("Stage:", self.stage_combo)

        self.interview_edit = QLineEdit(self.candidate.get("interview_date", ""))
        self.interview_edit.setPlaceholderText("YYYY-MM-DD")
        layout.addRow("Interview Date:", self.interview_edit)

        self.notes_edit = QLineEdit(self.candidate.get("notes", ""))
        layout.addRow("Notes:", self.notes_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_data(self) -> dict:
        return {
            "candidate_name": self.name_edit.text().strip(),
            "phone": self.phone_edit.text().strip(),
            "email": self.email_edit.text().strip(),
            "source": self.source_combo.currentText(),
            "stage": self.stage_combo.currentText(),
            "interview_date": self.interview_edit.text().strip(),
            "notes": self.notes_edit.text().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Add / Edit Position Dialog
# ════════════════════════════════════════════════════════════════════════

class PositionDialog(QDialog):
    """Dialog for creating or editing a position."""

    def __init__(self, parent, position: dict | None = None):
        super().__init__(parent)
        self.position = position or {}
        self.editing = bool(position)
        self.setWindowTitle("Edit Position" if self.editing else "Add Position")
        self.setMinimumSize(600, 620)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QFormLayout(content)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)

        # Site
        self.site_combo = QComboBox()
        site_names = [s["name"] for s in data_manager.get_site_names()]
        self.site_combo.addItems(site_names)
        current_site = self.position.get("site_name", "")
        if current_site in site_names:
            self.site_combo.setCurrentText(current_site)
        layout.addRow("Site:", self.site_combo)

        # Position Title
        self.title_edit = QLineEdit(self.position.get("position_title", ""))
        self.title_edit.setPlaceholderText("e.g. Security Officer, Shift Supervisor")
        layout.addRow("Position Title:", self.title_edit)

        # Shift
        self.shift_combo = QComboBox()
        self.shift_combo.addItems(SHIFT_OPTIONS)
        current_shift = self.position.get("shift", "")
        if current_shift in SHIFT_OPTIONS:
            self.shift_combo.setCurrentText(current_shift)
        layout.addRow("Shift:", self.shift_combo)

        # Pay Rate
        self.pay_edit = QLineEdit(self.position.get("pay_rate", ""))
        self.pay_edit.setPlaceholderText("e.g. 18.50")
        layout.addRow("Pay Rate ($):", self.pay_edit)

        # Weekly Schedule (Sun-Sat)
        schedule_group = QGroupBox("Weekly Schedule")
        schedule_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 13px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 6px;
                margin-top: 8px; padding-top: 18px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 12px; padding: 0 4px;
            }}
        """)
        sched_grid = QGridLayout(schedule_group)
        sched_grid.setSpacing(6)

        self.day_inputs = {}
        for i, (day_key, day_label) in enumerate(zip(DAYS_OF_WEEK, DAY_LABELS)):
            lbl = QLabel(day_label)
            lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
            lbl.setAlignment(Qt.AlignCenter)
            sched_grid.addWidget(lbl, 0, i)

            inp = QLineEdit(self.position.get(day_key, "OFF"))
            inp.setPlaceholderText("OFF")
            inp.setAlignment(Qt.AlignCenter)
            inp.setMinimumWidth(90)
            inp.textChanged.connect(self._recalc_hours)
            sched_grid.addWidget(inp, 1, i)
            self.day_inputs[day_key] = inp

        layout.addRow(schedule_group)

        # Total Hours (auto-calculated)
        hours_row = QHBoxLayout()
        self.hours_edit = QLineEdit(str(self.position.get("total_hours", "0")))
        self.hours_edit.setPlaceholderText("Auto-calculated or manual override")
        hours_row.addWidget(self.hours_edit)
        self.hours_auto_lbl = QLabel("(auto)")
        self.hours_auto_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
        hours_row.addWidget(self.hours_auto_lbl)
        layout.addRow("Total Hours/Wk:", hours_row)

        # Pipeline Stage
        self.stage_combo = QComboBox()
        self.stage_combo.addItems(PIPELINE_STAGES)
        current_stage = self.position.get("pipeline_stage", "Open")
        if current_stage in PIPELINE_STAGES:
            self.stage_combo.setCurrentText(current_stage)
        layout.addRow("Pipeline Stage:", self.stage_combo)

        # Stage Date
        self.stage_date_label = QLabel("Stage Date:")
        self.stage_date_edit = QDateEdit()
        self.stage_date_edit.setCalendarPopup(True)
        self.stage_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.stage_date_edit.setSpecialValueText("")  # show blank when no date
        stage_date_val = self._get_stage_date_value(current_stage)
        if stage_date_val:
            self.stage_date_edit.setDate(QDate.fromString(stage_date_val, "yyyy-MM-dd"))
        else:
            self.stage_date_edit.setDate(QDate.currentDate())
        layout.addRow(self.stage_date_label, self.stage_date_edit)

        # Expected Completion Date (only for Orientation / Training OJT)
        self.expected_end_label = QLabel("Expected Completion:")
        self.expected_end_edit = QDateEdit()
        self.expected_end_edit.setCalendarPopup(True)
        self.expected_end_edit.setDisplayFormat("yyyy-MM-dd")
        self.expected_end_edit.setSpecialValueText("")
        expected_val = self._get_expected_end_value(current_stage)
        if expected_val:
            self.expected_end_edit.setDate(QDate.fromString(expected_val, "yyyy-MM-dd"))
        else:
            self.expected_end_edit.setDate(QDate.currentDate())
        layout.addRow(self.expected_end_label, self.expected_end_edit)

        # Connect stage combo to show/hide expected completion
        self.stage_combo.currentTextChanged.connect(self._on_stage_changed)
        self._on_stage_changed(current_stage)

        # Notes
        self.notes_edit = QTextEdit(self.position.get("notes", ""))
        self.notes_edit.setMaximumHeight(100)
        self.notes_edit.setPlaceholderText("Optional notes about this position...")
        layout.addRow("Notes:", self.notes_edit)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _recalc_hours(self):
        """Auto-calculate total weekly hours from schedule inputs."""
        total = 0.0
        for day_key in DAYS_OF_WEEK:
            val = self.day_inputs[day_key].text().strip().upper()
            if val and val != "OFF" and "-" in val:
                parts = val.split("-")
                if len(parts) == 2:
                    total += data_manager.calculate_shift_hours(
                        _normalize_time(parts[0]),
                        _normalize_time(parts[1]),
                    )
        self.hours_edit.setText(str(round(total, 1)))
        self.hours_auto_lbl.setText("(auto)")

    # ── Stage date helpers ──────────────────────────────────────────

    _STAGE_DATE_MAP = {
        "Job Offer": "date_job_offer",
        "Background Check": "date_background_check",
        "Company Orientation": "date_orientation",
        "Training (OJT)": "date_training_ojt",
        "Filled": "date_filled",
    }

    _EXPECTED_END_MAP = {
        "Company Orientation": "expected_orientation_end",
        "Training (OJT)": "expected_training_end",
    }

    def _get_stage_date_value(self, stage: str) -> str:
        col = self._STAGE_DATE_MAP.get(stage, "")
        return self.position.get(col, "") if col else ""

    def _get_expected_end_value(self, stage: str) -> str:
        col = self._EXPECTED_END_MAP.get(stage, "")
        return self.position.get(col, "") if col else ""

    def _on_stage_changed(self, stage: str):
        """Show/hide date fields based on current pipeline stage."""
        has_stage_date = stage in self._STAGE_DATE_MAP
        self.stage_date_label.setVisible(has_stage_date)
        self.stage_date_edit.setVisible(has_stage_date)

        # Pre-fill stage date from position data if available
        if has_stage_date:
            existing = self._get_stage_date_value(stage)
            if existing:
                self.stage_date_edit.setDate(QDate.fromString(existing, "yyyy-MM-dd"))
            else:
                self.stage_date_edit.setDate(QDate.currentDate())

        has_expected = stage in self._EXPECTED_END_MAP
        self.expected_end_label.setVisible(has_expected)
        self.expected_end_edit.setVisible(has_expected)

        if has_expected:
            existing_exp = self._get_expected_end_value(stage)
            if existing_exp:
                self.expected_end_edit.setDate(QDate.fromString(existing_exp, "yyyy-MM-dd"))
            else:
                self.expected_end_edit.setDate(QDate.currentDate())

    def _on_save(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing Info", "Position title is required.")
            return
        pay = self.pay_edit.text().strip().replace("$", "").replace(",", "")
        try:
            float(pay or "0")
        except ValueError:
            QMessageBox.warning(self, "Invalid Pay Rate", "Pay rate must be a number.")
            return
        self.accept()

    def get_data(self) -> dict:
        pay = self.pay_edit.text().strip().replace("$", "").replace(",", "")
        stage = self.stage_combo.currentText()
        result = {
            "site_name": self.site_combo.currentText(),
            "position_title": self.title_edit.text().strip(),
            "shift": self.shift_combo.currentText(),
            "pay_rate": pay or "0.00",
            "total_hours": self.hours_edit.text().strip() or "0",
            "pipeline_stage": stage,
            "notes": self.notes_edit.toPlainText().strip(),
        }
        for day_key in DAYS_OF_WEEK:
            result[day_key] = self.day_inputs[day_key].text().strip() or "OFF"

        # Include stage date if visible
        if stage in self._STAGE_DATE_MAP:
            date_col = self._STAGE_DATE_MAP[stage]
            result[date_col] = self.stage_date_edit.date().toString("yyyy-MM-dd")

        # Include expected completion date if visible
        if stage in self._EXPECTED_END_MAP:
            exp_col = self._EXPECTED_END_MAP[stage]
            result[exp_col] = self.expected_end_edit.date().toString("yyyy-MM-dd")

        return result


# ════════════════════════════════════════════════════════════════════════
# Helper Functions
# ════════════════════════════════════════════════════════════════════════

def _normalize_time(t: str) -> str:
    """Ensure time is in HH:MM format (handles both 0800 and 08:00)."""
    t = t.strip()
    if ":" not in t and len(t) == 4 and t.isdigit():
        return f"{t[:2]}:{t[2:]}"
    return t


def _compress_schedule(pos: dict) -> str:
    """Build a compressed schedule string like 'M-F 0700-1500' from day columns."""
    day_abbrev = ["Su", "M", "Tu", "W", "Th", "F", "Sa"]
    shifts = []
    for day_key, abbrev in zip(DAYS_OF_WEEK, day_abbrev):
        val = (pos.get(day_key, "") or "OFF").strip().upper()
        if val and val != "OFF":
            shifts.append((abbrev, val))

    if not shifts:
        return "No Schedule"

    # Check if all working days have the same shift
    unique_times = set(s[1] for s in shifts)
    if len(unique_times) == 1:
        time_str = shifts[0][1]
        days = [s[0] for s in shifts]
        # Check for consecutive weekday range
        day_order = ["Su", "M", "Tu", "W", "Th", "F", "Sa"]
        indices = [day_order.index(d) for d in days]
        if indices == list(range(indices[0], indices[-1] + 1)) and len(indices) > 1:
            return f"{days[0]}-{days[-1]} {time_str}"
        return f"{','.join(days)} {time_str}"

    # Different shifts on different days
    parts = [f"{abbrev}:{val}" for abbrev, val in shifts]
    return " | ".join(parts)


def _days_open(pos: dict) -> int:
    """Calculate days since position was opened."""
    opened = pos.get("date_opened", "")
    if not opened:
        return 0
    try:
        d = dt_date.fromisoformat(opened)
        return (dt_date.today() - d).days
    except (ValueError, TypeError):
        return 0


def _candidate_stage_color(stage: str) -> str:
    """Return a color for the candidate stage."""
    mapping = {
        "Applied": COLORS["info"],
        "Phone Screen": "#3B82F6",
        "Interview": "#8B5CF6",
        "Offer": "#F59E0B",
        "Hired": COLORS["success"],
        "Rejected": COLORS["danger"],
    }
    return mapping.get(stage, COLORS["info"])


def _get_username(widget) -> str:
    """Walk up widget parents to find app_state username."""
    w = widget
    while w:
        if hasattr(w, 'app_state'):
            return w.app_state.get("username", "")
        w = w.parent()
    return ""


# ════════════════════════════════════════════════════════════════════════
# Open Positions Page
# ════════════════════════════════════════════════════════════════════════

class OpenPositionsPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._sort_col = -1
        self._sort_order = Qt.AscendingOrder
        self._positions_cache = []
        self._build()

    # ── Role helpers ──────────────────────────────────────────────────

    def _can_edit(self) -> bool:
        role = self.app_state.get("role", "viewer")
        return role in ("admin", "manager", ROLE_ADMIN)

    def _username(self) -> str:
        return self.app_state.get("username", "")

    # ── Build UI ──────────────────────────────────────────────────────

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # ── KPI Cards Row ─────────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        self.card_total = self._make_big_card(
            "Total Open Positions", "0", "Across all sites", COLORS["accent"], "\U0001F4CB"
        )
        self.card_hours = self._make_big_card(
            "Total Open Hours/Wk", "0", "Weekly coverage gap", COLORS["warning"], "\u23F1"
        )
        self.card_ot = self._make_big_card(
            "Weekly OT Exposure", "$0", "Overtime cost risk", "#E65100", "\U0001F4B0"
        )
        self.card_days = self._make_big_card(
            "Avg Days to Fill", "0", "Historical average", COLORS["success"], "\U0001F4C5"
        )
        cards_row.addWidget(self.card_total)
        cards_row.addWidget(self.card_hours)
        cards_row.addWidget(self.card_ot)
        cards_row.addWidget(self.card_days)
        layout.addLayout(cards_row)

        # ── Toolbar Row ──────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.site_filter = QComboBox()
        self.site_filter.setMinimumWidth(160)
        self.site_filter.addItem("All Sites")
        self.site_filter.currentIndexChanged.connect(lambda: self.refresh())
        toolbar.addWidget(self.site_filter)

        self.stage_filter = QComboBox()
        self.stage_filter.setMinimumWidth(160)
        self.stage_filter.addItem("All Stages")
        self.stage_filter.addItems(PIPELINE_STAGES)
        self.stage_filter.currentIndexChanged.connect(lambda: self.refresh())
        toolbar.addWidget(self.stage_filter)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search positions...")
        self.search_box.setMinimumWidth(200)
        self.search_box.textChanged.connect(lambda: self._apply_search())
        toolbar.addWidget(self.search_box)

        toolbar.addStretch()

        self.chk_filled = QCheckBox("Show Filled")
        self.chk_filled.stateChanged.connect(lambda: self.refresh())
        toolbar.addWidget(self.chk_filled)

        if self._can_edit():
            btn_add = QPushButton("+ Add Position")
            btn_add.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS.get("accent_hover", COLORS["accent"])))
            btn_add.clicked.connect(self._add_position)
            toolbar.addWidget(btn_add)

        btn_export = QPushButton("Export CSV")
        btn_export.setStyleSheet(btn_style(tc("info"), "white", tc("primary")))
        btn_export.clicked.connect(self._export_csv)
        toolbar.addWidget(btn_export)

        layout.addLayout(toolbar)

        # ── Pipeline Visual ──────────────────────────────────────────
        self.pipeline_widget = PipelineVisualWidget()
        layout.addWidget(self.pipeline_widget)

        # ── Positions Table ──────────────────────────────────────────
        col_headers = [
            "Site", "Position", "Shift", "Pay Rate", "Schedule",
            "Hours/Wk", "Pipeline Stage", "Days Open", "Stage Date",
            "OT Cost/Wk", "Candidates", "Notes", "Actions",
        ]
        self.table = QTableWidget(0, len(col_headers))
        self.table.setHorizontalHeaderLabels(col_headers)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, len(col_headers)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 13px;
                padding: 8px 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
                min-height: 32px;
            }}
        """)
        hdr.sectionClicked.connect(self._on_header_click)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(300)
        layout.addWidget(self.table)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Card Factory (matching DashboardPage pattern) ────────────────

    def _make_big_card(self, title, value, subtitle, color, icon_text):
        frame = QFrame()
        frame.setFixedHeight(120)
        frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border-radius: 10px;
                border-left: 5px solid {color};
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(18, 14, 18, 14)

        text_lay = QVBoxLayout()
        text_lay.setSpacing(2)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px; font-weight: 600;")
        lbl_val = QLabel(value)
        lbl_val.setFont(QFont("Segoe UI", 32, QFont.Bold))
        lbl_val.setStyleSheet(f"color: {tc('text')};")
        lbl_val.setObjectName("card_value")
        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        lbl_sub.setObjectName("card_sub")
        text_lay.addWidget(lbl_title)
        text_lay.addWidget(lbl_val)
        text_lay.addWidget(lbl_sub)
        lay.addLayout(text_lay)

        lay.addStretch()

        lbl_icon = QLabel(icon_text)
        lbl_icon.setFont(QFont("Segoe UI", 28))
        lbl_icon.setStyleSheet(f"color: {color};")
        lbl_icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl_icon)

        return frame

    # ── Refresh / Data Loading ───────────────────────────────────────

    def refresh(self):
        """Reload all data from the database and update the UI."""
        # Rebuild site filter options (preserve current selection)
        current_site = self.site_filter.currentText()
        self.site_filter.blockSignals(True)
        self.site_filter.clear()
        self.site_filter.addItem("All Sites")
        for name in [s["name"] for s in data_manager.get_site_names()]:
            self.site_filter.addItem(name)
        idx = self.site_filter.findText(current_site)
        if idx >= 0:
            self.site_filter.setCurrentIndex(idx)
        self.site_filter.blockSignals(False)

        # Fetch positions with filters
        site = self.site_filter.currentText()
        site_f = "" if site == "All Sites" else site
        stage = self.stage_filter.currentText()
        stage_f = "" if stage == "All Stages" else stage
        include_filled = self.chk_filled.isChecked()

        positions = data_manager.get_all_positions(
            site_filter=site_f,
            status_filter=stage_f,
            include_filled=include_filled,
        )
        self._positions_cache = positions

        # Update KPIs
        kpis = data_manager.get_position_kpis()
        self.card_total.findChild(QLabel, "card_value").setText(str(kpis.get("total_open", 0)))
        self.card_hours.findChild(QLabel, "card_value").setText(f"{kpis.get('total_hours', 0):.0f}")
        ot = kpis.get("ot_cost_exposure", 0)
        self.card_ot.findChild(QLabel, "card_value").setText(f"${ot:,.0f}")
        avg_days = kpis.get("avg_days_to_fill", 0)
        self.card_days.findChild(QLabel, "card_value").setText(
            str(avg_days) if avg_days else "N/A"
        )

        # Update pipeline visual
        pipe_dist = kpis.get("pipeline_distribution", {})
        self.pipeline_widget.set_counts(pipe_dist)

        # Populate table
        self._populate_table(positions)

    def _populate_table(self, positions: list):
        """Fill the table with position data."""
        search_text = self.search_box.text().strip().lower()

        # Filter by search
        if search_text:
            positions = [
                p for p in positions
                if search_text in p.get("site_name", "").lower()
                or search_text in p.get("position_title", "").lower()
                or search_text in p.get("shift", "").lower()
                or search_text in p.get("notes", "").lower()
                or search_text in p.get("pipeline_stage", "").lower()
            ]

        # Sort if active
        if self._sort_col >= 0:
            positions = self._sort_positions(positions, self._sort_col, self._sort_order)

        self.table.setRowCount(len(positions))
        can_edit = self._can_edit()

        for i, pos in enumerate(positions):
            pid = pos.get("position_id", "")

            # Site
            self.table.setItem(i, 0, QTableWidgetItem(pos.get("site_name", "")))

            # Position
            title_item = QTableWidgetItem(pos.get("position_title", ""))
            title_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(i, 1, title_item)

            # Shift
            self.table.setItem(i, 2, QTableWidgetItem(pos.get("shift", "")))

            # Pay Rate
            pay = pos.get("pay_rate", "0")
            try:
                pay_val = float(pay)
                pay_str = f"${pay_val:.2f}"
            except (ValueError, TypeError):
                pay_str = pay
            pay_item = QTableWidgetItem(pay_str)
            pay_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, pay_item)

            # Schedule (compressed)
            sched_str = _compress_schedule(pos)
            sched_item = QTableWidgetItem(sched_str)
            sched_item.setFont(QFont("Consolas", 11))
            self.table.setItem(i, 4, sched_item)

            # Hours/Wk
            hours = pos.get("total_hours", "0")
            hrs_item = QTableWidgetItem(str(hours))
            hrs_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 5, hrs_item)

            # Pipeline Stage (colored badge widget)
            stage = pos.get("pipeline_stage", "Open")
            stage_widget = self._make_stage_badge(stage)
            self.table.setCellWidget(i, 6, stage_widget)

            # Days Open (color coded)
            days = _days_open(pos)
            days_item = QTableWidgetItem(str(days))
            days_item.setTextAlignment(Qt.AlignCenter)
            days_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            if days > 30:
                days_item.setForeground(QColor(COLORS["danger"]))
            elif days > 14:
                days_item.setForeground(QColor(COLORS["warning"]))
            else:
                days_item.setForeground(QColor(COLORS["success"]))
            self.table.setItem(i, 7, days_item)

            # Stage Date — show the date when current pipeline stage was entered
            stage_date_map = {
                "Job Offer": "date_job_offer",
                "Background Check": "date_background_check",
                "Company Orientation": "date_orientation",
                "Training (OJT)": "date_training_ojt",
                "Filled": "date_filled",
            }
            stage_date_col = stage_date_map.get(stage, "")
            stage_date_val = pos.get(stage_date_col, "") if stage_date_col else ""
            stage_date_item = QTableWidgetItem(stage_date_val)
            stage_date_item.setTextAlignment(Qt.AlignCenter)
            # For Orientation/OJT, add expected completion as tooltip
            expected_end_map = {
                "Company Orientation": "expected_orientation_end",
                "Training (OJT)": "expected_training_end",
            }
            exp_col = expected_end_map.get(stage, "")
            exp_val = pos.get(exp_col, "") if exp_col else ""
            if exp_val:
                stage_date_item.setToolTip(f"Expected completion: {exp_val}")
            self.table.setItem(i, 8, stage_date_item)

            # OT Cost/Wk
            ot_cost = data_manager.calculate_position_ot_cost(
                pos.get("pay_rate", "0"), pos.get("total_hours", "0")
            )
            ot_item = QTableWidgetItem(f"${ot_cost:,.2f}")
            ot_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 9, ot_item)

            # Candidates (clickable count)
            candidates = data_manager.get_candidates(pid)
            cand_count = len(candidates)
            cand_widget = QWidget()
            cand_lay = QHBoxLayout(cand_widget)
            cand_lay.setContentsMargins(4, 2, 4, 2)
            cand_lay.setAlignment(Qt.AlignCenter)
            btn_cand = QPushButton(f"{cand_count} candidate{'s' if cand_count != 1 else ''}")
            btn_cand.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {COLORS.get('info', '#374151')};
                    border: none; font-weight: 600; text-decoration: underline;
                    font-size: 13px;
                }}
                QPushButton:hover {{ color: {COLORS['accent']}; }}
            """)
            btn_cand.setCursor(Qt.PointingHandCursor)
            btn_cand.clicked.connect(
                lambda checked, _pos=pos: self._show_candidates(_pos)
            )
            cand_lay.addWidget(btn_cand)
            self.table.setCellWidget(i, 10, cand_widget)

            # Notes
            notes = pos.get("notes", "")
            notes_item = QTableWidgetItem(notes[:60] + ("..." if len(notes) > 60 else ""))
            notes_item.setToolTip(notes)
            self.table.setItem(i, 11, notes_item)

            # Actions
            actions_w = QWidget()
            actions_lay = QHBoxLayout(actions_w)
            actions_lay.setContentsMargins(4, 2, 4, 2)
            actions_lay.setSpacing(4)

            if can_edit:
                btn_edit = QPushButton("Edit")
                btn_edit.setFixedSize(48, 28)
                btn_edit.setStyleSheet(btn_style(tc("info"), "white"))
                btn_edit.clicked.connect(
                    lambda checked, _pid=pid: self._edit_position(_pid)
                )
                actions_lay.addWidget(btn_edit)

                # Advance pipeline (only if not Filled)
                if stage != "Filled":
                    next_idx = PIPELINE_STAGES.index(stage) + 1 if stage in PIPELINE_STAGES else -1
                    if 0 <= next_idx < len(PIPELINE_STAGES):
                        next_stage = PIPELINE_STAGES[next_idx]
                        btn_advance = QPushButton("\u25B6")
                        btn_advance.setToolTip(f"Advance to: {next_stage}")
                        btn_advance.setFixedSize(32, 28)
                        btn_advance.setStyleSheet(btn_style(
                            PIPELINE_COLORS.get(next_stage, "#6B7280"), "white"
                        ))
                        btn_advance.clicked.connect(
                            lambda checked, _pid=pid, _ns=next_stage: self._advance_pipeline(_pid, _ns)
                        )
                        actions_lay.addWidget(btn_advance)

                btn_del = QPushButton("Del")
                btn_del.setFixedSize(40, 28)
                btn_del.setStyleSheet(btn_style(COLORS["danger"], "white"))
                btn_del.clicked.connect(
                    lambda checked, _pid=pid: self._delete_position(_pid)
                )
                actions_lay.addWidget(btn_del)
            else:
                # View-only: detail button
                btn_view = QPushButton("View")
                btn_view.setFixedSize(48, 28)
                btn_view.setStyleSheet(btn_style(tc("info"), "white"))
                btn_view.clicked.connect(
                    lambda checked, _pos=pos: self._show_candidates(_pos)
                )
                actions_lay.addWidget(btn_view)

            self.table.setCellWidget(i, 12, actions_w)
            self.table.setRowHeight(i, 48)

    def _make_stage_badge(self, stage: str) -> QWidget:
        """Create a colored badge widget for a pipeline stage."""
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setAlignment(Qt.AlignCenter)

        badge = QLabel(stage)
        badge.setAlignment(Qt.AlignCenter)
        color = PIPELINE_COLORS.get(stage, "#6B7280")
        badge.setStyleSheet(f"""
            QLabel {{
                background: {color};
                color: white;
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
        """)
        lay.addWidget(badge)
        return container

    # ── Sorting ───────────────────────────────────────────────────────

    def _on_header_click(self, col):
        if self._sort_col == col:
            self._sort_order = (
                Qt.DescendingOrder if self._sort_order == Qt.AscendingOrder
                else Qt.AscendingOrder
            )
        else:
            self._sort_col = col
            self._sort_order = Qt.AscendingOrder
        self._populate_table(self._positions_cache)

    def _sort_positions(self, positions: list, col: int, order) -> list:
        """Sort positions list by the given column index."""
        _sd_map = {
            "Job Offer": "date_job_offer",
            "Background Check": "date_background_check",
            "Company Orientation": "date_orientation",
            "Training (OJT)": "date_training_ojt",
            "Filled": "date_filled",
        }
        key_map = {
            0: lambda p: p.get("site_name", "").lower(),
            1: lambda p: p.get("position_title", "").lower(),
            2: lambda p: p.get("shift", "").lower(),
            3: lambda p: _safe_float(p.get("pay_rate", "0")),
            4: lambda p: _compress_schedule(p).lower(),
            5: lambda p: _safe_float(p.get("total_hours", "0")),
            6: lambda p: PIPELINE_STAGES.index(p.get("pipeline_stage", "Open"))
                         if p.get("pipeline_stage", "Open") in PIPELINE_STAGES else 99,
            7: lambda p: _days_open(p),
            8: lambda p: p.get(_sd_map.get(p.get("pipeline_stage", ""), ""), ""),
            9: lambda p: data_manager.calculate_position_ot_cost(
                p.get("pay_rate", "0"), p.get("total_hours", "0")
            ),
            10: lambda p: len(data_manager.get_candidates(p.get("position_id", ""))),
            11: lambda p: p.get("notes", "").lower(),
        }
        key_fn = key_map.get(col)
        if not key_fn:
            return positions
        reverse = order == Qt.DescendingOrder
        try:
            return sorted(positions, key=key_fn, reverse=reverse)
        except Exception:
            return positions

    # ── Search ────────────────────────────────────────────────────────

    def _apply_search(self):
        self._populate_table(self._positions_cache)

    # ── CRUD Actions ─────────────────────────────────────────────────

    def _add_position(self):
        dlg = PositionDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            data["created_by"] = self._username()
            pid = data_manager.create_position(data)
            audit.log(
                "operations", "position_created", self._username(),
                f"Position '{data.get('position_title', '')}' at {data.get('site_name', '')} created",
            )
            self.refresh()

    def _edit_position(self, position_id: str):
        pos = data_manager.get_position(position_id)
        if not pos:
            return
        dlg = PositionDialog(self, position=pos)
        if dlg.exec() == QDialog.Accepted:
            updates = dlg.get_data()
            updates["updated_by"] = self._username()
            data_manager.update_position(position_id, updates)
            audit.log(
                "operations", "position_updated", self._username(),
                f"Position '{updates.get('position_title', '')}' updated",
            )
            self.refresh()

    def _delete_position(self, position_id: str):
        pos = data_manager.get_position(position_id)
        if not pos:
            return
        reply = QMessageBox.question(
            self, "Delete Position",
            f"Delete position '{pos.get('position_title', '')}' at {pos.get('site_name', '')}?\n\n"
            "This will also delete all associated candidates.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            data_manager.delete_position(position_id)
            audit.log(
                "operations", "position_deleted", self._username(),
                f"Position '{pos.get('position_title', '')}' at {pos.get('site_name', '')} deleted",
            )
            self.refresh()

    def _advance_pipeline(self, position_id: str, new_stage: str):
        pos = data_manager.get_position(position_id)
        if not pos:
            return
        reply = QMessageBox.question(
            self, "Advance Pipeline",
            f"Advance '{pos.get('position_title', '')}' to '{new_stage}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            data_manager.advance_position_pipeline(position_id, new_stage)
            audit.log(
                "operations", "position_pipeline_advanced", self._username(),
                f"Position '{pos.get('position_title', '')}' advanced to '{new_stage}'",
            )
            self.refresh()

    def _show_candidates(self, position: dict):
        dlg = CandidateDialog(self, position, can_edit=self._can_edit())
        dlg.exec()
        # Refresh to update candidate counts
        self.refresh()

    # ── Export CSV ────────────────────────────────────────────────────

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Positions CSV", "open_positions.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        # Collect visible rows from cache (with current filters applied)
        positions = self._positions_cache
        search_text = self.search_box.text().strip().lower()
        if search_text:
            positions = [
                p for p in positions
                if search_text in p.get("site_name", "").lower()
                or search_text in p.get("position_title", "").lower()
                or search_text in p.get("shift", "").lower()
                or search_text in p.get("notes", "").lower()
                or search_text in p.get("pipeline_stage", "").lower()
            ]

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Site", "Position", "Shift", "Pay Rate", "Schedule",
                    "Hours/Wk", "Pipeline Stage", "Days Open", "Stage Date",
                    "OT Cost/Wk", "Candidates", "Notes", "Date Opened",
                ])
                _csv_sd_map = {
                    "Job Offer": "date_job_offer",
                    "Background Check": "date_background_check",
                    "Company Orientation": "date_orientation",
                    "Training (OJT)": "date_training_ojt",
                    "Filled": "date_filled",
                }
                for pos in positions:
                    pay = pos.get("pay_rate", "0")
                    ot = data_manager.calculate_position_ot_cost(
                        pay, pos.get("total_hours", "0")
                    )
                    cand_count = len(data_manager.get_candidates(pos.get("position_id", "")))
                    p_stage = pos.get("pipeline_stage", "")
                    sd_col = _csv_sd_map.get(p_stage, "")
                    sd_val = pos.get(sd_col, "") if sd_col else ""
                    writer.writerow([
                        pos.get("site_name", ""),
                        pos.get("position_title", ""),
                        pos.get("shift", ""),
                        f"${float(pay or 0):.2f}",
                        _compress_schedule(pos),
                        pos.get("total_hours", "0"),
                        pos.get("pipeline_stage", ""),
                        _days_open(pos),
                        sd_val,
                        f"${ot:,.2f}",
                        cand_count,
                        pos.get("notes", ""),
                        pos.get("date_opened", ""),
                    ])
            QMessageBox.information(self, "Export Complete", f"Exported {len(positions)} positions to:\n{path}")
            audit.log("operations", "positions_exported", self._username(),
                      f"Exported {len(positions)} positions to CSV")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", f"Could not export: {e}")


# ── Utility ───────────────────────────────────────────────────────────

def _safe_float(val) -> float:
    try:
        return float(str(val).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return 0.0
