"""
Cerasus Hub -- Operations Module: Anchor Schedules Page
Manages baseline weekly work patterns for each flex officer — their "home"
schedule showing which days they work and at which site.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QFormLayout, QDialogButtonBox, QMessageBox,
    QComboBox, QLineEdit, QTextEdit, QCheckBox, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from src.modules.operations.data_manager import (
    get_all_anchor_schedules,
    get_anchor_schedule,
    create_anchor_schedule,
    update_anchor_schedule,
    delete_anchor_schedule,
    get_ops_officers,
    calculate_shift_hours,
    DAYS_OF_WEEK,
)
from src.shared_data import get_site_names
from src.config import COLORS, tc, btn_style, build_dialog_stylesheet, _is_dark
from src import audit


DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
COLUMNS = ["Officer", "Position", "Site"] + DAY_LABELS + ["Hours", "Actions"]


# ════════════════════════════════════════════════════════════════════════
# Add / Edit Schedule Dialog
# ════════════════════════════════════════════════════════════════════════

class AnchorScheduleDialog(QDialog):
    """Dialog for creating or editing an anchor schedule."""

    def __init__(self, parent=None, schedule=None, app_state=None):
        super().__init__(parent)
        self._schedule = schedule  # None for add, dict for edit
        self.app_state = app_state or {}
        self.setWindowTitle("Edit Anchor Schedule" if schedule else "Add Anchor Schedule")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._day_inputs = {}
        self._build()
        if schedule:
            self._populate(schedule)

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Officer dropdown
        self.cmb_officer = QComboBox()
        officers = get_ops_officers()
        self._officer_names = [o.get("name", "") for o in officers if o.get("name")]
        self.cmb_officer.addItems(self._officer_names)
        layout.addRow("Officer:", self.cmb_officer)

        # Position Title
        self.txt_position = QLineEdit()
        self.txt_position.setPlaceholderText("e.g. Flex Officer, Site Lead")
        layout.addRow("Position Title:", self.txt_position)

        # Anchor Site
        self.cmb_site = QComboBox()
        sites = get_site_names()
        self.cmb_site.addItems([s["name"] for s in sites])
        layout.addRow("Anchor Site:", self.cmb_site)

        # Pay Rate
        self.txt_pay_rate = QLineEdit()
        self.txt_pay_rate.setPlaceholderText("0.00")
        layout.addRow("Pay Rate ($/hr):", self.txt_pay_rate)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {tc('border')};")
        layout.addRow(sep)

        # Tips label
        tips = QLabel(
            "Schedule format:  OFF for days off  |  0800-1600 for 8am-4pm  |  2300-0700 for overnight"
        )
        tips.setWordWrap(True)
        tips.setStyleSheet(f"""
            QLabel {{
                color: {tc('text_light')};
                font-size: 12px;
                font-style: italic;
                padding: 4px 0;
                background: transparent;
                border: none;
            }}
        """)
        layout.addRow(tips)

        # Day fields (Sun-Sat)
        for i, day_key in enumerate(DAYS_OF_WEEK):
            inp = QLineEdit()
            inp.setPlaceholderText("OFF or 0800-1600")
            inp.textChanged.connect(self._recalculate_hours)
            self._day_inputs[day_key] = inp
            layout.addRow(f"{DAY_LABELS[i]}:", inp)

        # Total Hours (read-only)
        self.txt_total = QLineEdit()
        self.txt_total.setReadOnly(True)
        self.txt_total.setText("0.0")
        self.txt_total.setStyleSheet(f"""
            QLineEdit {{
                background: {tc('info_light')};
                font-weight: 700;
            }}
        """)
        layout.addRow("Total Hours:", self.txt_total)

        # Active checkbox
        self.chk_active = QCheckBox("Active")
        self.chk_active.setChecked(True)
        self.chk_active.setStyleSheet(f"QCheckBox {{ color: {tc('text')}; font-size: 14px; }}")
        layout.addRow("", self.chk_active)

        # Notes
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Optional notes...")
        self.txt_notes.setMaximumHeight(80)
        layout.addRow("Notes:", self.txt_notes)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _populate(self, s):
        """Fill fields from an existing schedule dict."""
        if s.get("officer_name") in self._officer_names:
            self.cmb_officer.setCurrentText(s["officer_name"])
        self.txt_position.setText(s.get("position_title", ""))
        site = s.get("anchor_site", "")
        if self.cmb_site.findText(site) >= 0:
            self.cmb_site.setCurrentText(site)
        self.txt_pay_rate.setText(str(s.get("pay_rate", "")))
        for day_key in DAYS_OF_WEEK:
            val = s.get(day_key, "OFF")
            self._day_inputs[day_key].setText(val if val else "OFF")
        self.chk_active.setChecked(bool(s.get("active", 1)))
        self.txt_notes.setPlainText(s.get("notes", ""))
        self._recalculate_hours()

    def _recalculate_hours(self):
        total = 0.0
        for day_key in DAYS_OF_WEEK:
            text = self._day_inputs[day_key].text().strip().upper()
            if text and text != "OFF" and "-" in text:
                parts = text.split("-")
                if len(parts) == 2:
                    total += calculate_shift_hours(parts[0], parts[1])
        self.txt_total.setText(str(round(total, 2)))

    def _on_save(self):
        officer = self.cmb_officer.currentText().strip()
        if not officer:
            QMessageBox.warning(self, "Validation", "Please select an officer.")
            return
        site = self.cmb_site.currentText().strip()
        if not site:
            QMessageBox.warning(self, "Validation", "Please select an anchor site.")
            return
        self.accept()

    def get_data(self) -> dict:
        data = {
            "officer_name": self.cmb_officer.currentText().strip(),
            "position_title": self.txt_position.text().strip(),
            "anchor_site": self.cmb_site.currentText().strip(),
            "pay_rate": self.txt_pay_rate.text().strip() or "0.00",
            "active": self.chk_active.isChecked(),
            "notes": self.txt_notes.toPlainText().strip(),
        }
        for day_key in DAYS_OF_WEEK:
            val = self._day_inputs[day_key].text().strip().upper()
            data[day_key] = val if val else "OFF"
        return data


# ════════════════════════════════════════════════════════════════════════
# Anchor Schedules Page
# ════════════════════════════════════════════════════════════════════════

class AnchorSchedulesPage(QWidget):
    """Manages baseline weekly work patterns for flex officers."""

    def __init__(self, app_state=None):
        super().__init__()
        self.app_state = app_state or {}
        self._build()

    # ── Public interface ──────────────────────────────────────────────

    def _init_page(self, app_state):
        """Called by the module host when the page becomes visible."""
        self.app_state = app_state
        self._load_schedules()

    def refresh(self):
        """External refresh hook."""
        self._load_schedules()

    # ── UI Construction ───────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── Title ──
        title = QLabel("Anchor Schedules \u2014 Baseline Weekly Patterns")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        root.addWidget(title)

        subtitle = QLabel(
            "Define each flex officer\u2019s regular weekly schedule. "
            "The auto-scheduler uses these to optimize assignments."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color: {tc('text_light')}; font-size: 13px; background: transparent;"
        )
        root.addWidget(subtitle)

        # ── Top bar ──
        bar = QHBoxLayout()
        bar.setSpacing(12)
        bar.addStretch()

        self.btn_add = QPushButton("+ Add Schedule")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setFixedHeight(38)
        self.btn_add.setStyleSheet(btn_style(tc("accent"), "white", tc("accent_hover")))
        self.btn_add.clicked.connect(self._on_add)
        bar.addWidget(self.btn_add)

        root.addLayout(bar)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {tc('border')};")
        root.addWidget(sep)

        # ── Table ──
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

    # ── Data Loading ──────────────────────────────────────────────────

    def _load_schedules(self):
        schedules = get_all_anchor_schedules(active_only=False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(schedules))

        for row_idx, sched in enumerate(schedules):
            col = 0

            # Officer
            self.table.setItem(row_idx, col, QTableWidgetItem(sched.get("officer_name", "")))
            col += 1

            # Position
            self.table.setItem(row_idx, col, QTableWidgetItem(sched.get("position_title", "")))
            col += 1

            # Site
            self.table.setItem(row_idx, col, QTableWidgetItem(sched.get("anchor_site", "")))
            col += 1

            # Day columns (Sun - Sat)
            for day_key in DAYS_OF_WEEK:
                shift = sched.get(day_key, "OFF").strip().upper()
                item = QTableWidgetItem(shift)
                item.setTextAlignment(Qt.AlignCenter)

                if shift == "OFF":
                    item.setBackground(QColor(tc("info_light")))
                    item.setForeground(QColor(tc("text_light")))
                else:
                    item.setForeground(QColor(tc("accent")))

                self.table.setItem(row_idx, col, item)
                col += 1

            # Hours
            total = sched.get("total_hours", "0")
            hours_item = QTableWidgetItem(str(total))
            hours_item.setTextAlignment(Qt.AlignCenter)
            hours_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(row_idx, col, hours_item)
            col += 1

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)

            schedule_id = sched.get("schedule_id", "")

            btn_edit = QPushButton("Edit")
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.setFixedHeight(28)
            btn_edit.setStyleSheet(btn_style(tc("primary_light"), "white", tc("primary_mid")))
            btn_edit.clicked.connect(lambda checked=False, sid=schedule_id: self._on_edit(sid))
            actions_layout.addWidget(btn_edit)

            btn_del = QPushButton("Delete")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedHeight(28)
            btn_del.setStyleSheet(btn_style(tc("danger"), "white", tc("accent_hover")))
            btn_del.clicked.connect(lambda checked=False, sid=schedule_id: self._on_delete(sid))
            actions_layout.addWidget(btn_del)

            self.table.setCellWidget(row_idx, col, actions_widget)

    # ── Actions ───────────────────────────────────────────────────────

    def _get_username(self) -> str:
        user = self.app_state.get("user", {})
        return user.get("display_name", "") or user.get("username", "System")

    def _on_add(self):
        dlg = AnchorScheduleDialog(self, schedule=None, app_state=self.app_state)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            username = self._get_username()
            create_anchor_schedule(data, created_by=username)
            audit.log_event(
                "operations", "anchor_create", username,
                f"Created anchor schedule for {data['officer_name']} at {data['anchor_site']}"
            )
            self._load_schedules()

    def _on_edit(self, schedule_id: str):
        sched = get_anchor_schedule(schedule_id)
        if not sched:
            QMessageBox.warning(self, "Not Found", "Schedule not found.")
            return
        dlg = AnchorScheduleDialog(self, schedule=sched, app_state=self.app_state)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            username = self._get_username()
            update_anchor_schedule(schedule_id, data, updated_by=username)
            audit.log_event(
                "operations", "anchor_update", username,
                f"Updated anchor schedule for {data['officer_name']} at {data['anchor_site']}"
            )
            self._load_schedules()

    def _on_delete(self, schedule_id: str):
        sched = get_anchor_schedule(schedule_id)
        if not sched:
            return
        name = sched.get("officer_name", "Unknown")
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete the anchor schedule for {name}?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            username = self._get_username()
            delete_anchor_schedule(schedule_id)
            audit.log_event(
                "operations", "anchor_delete", username,
                f"Deleted anchor schedule for {name}"
            )
            self._load_schedules()
