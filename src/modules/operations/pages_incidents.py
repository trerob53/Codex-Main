"""
Cerasus Hub -- Operations Module: Incident Report Page
Log incidents and browse incident history with filtering and detail dialogs.
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QComboBox, QMessageBox, QFormLayout, QTextEdit, QLineEdit,
    QAbstractItemView, QDialog, QDialogButtonBox, QDateEdit,
    QTimeEdit, QCheckBox, QScrollArea, QTabWidget, QCompleter,
    QGroupBox, QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, build_dialog_stylesheet, tc, _is_dark, btn_style
from src.modules.operations import data_manager
from src import audit


# ── Constants ─────────────────────────────────────────────────────────

INCIDENT_TYPES = [
    "Trespass", "Theft/Larceny", "Vandalism", "Assault",
    "Medical Emergency", "Fire/Alarm", "Suspicious Activity",
    "Vehicle Incident", "Workplace Injury", "Policy Violation", "Other",
]

SEVERITY_LEVELS = ["Low", "Medium", "High", "Critical"]

STATUS_WORKFLOW = ["Open", "Under Review", "Escalated", "Resolved", "Closed"]

SEVERITY_COLORS = {
    "Low": COLORS["success"],
    "Medium": COLORS["warning"],
    "High": "#E65100",
    "Critical": COLORS["danger"],
}


# ════════════════════════════════════════════════════════════════════════
# Incident Detail Dialog
# ════════════════════════════════════════════════════════════════════════

class IncidentDetailDialog(QDialog):
    """Read-only detail view of a single incident with status update."""

    def __init__(self, parent, incident: dict, editable: bool = False):
        super().__init__(parent)
        self.setWindowTitle(f"Incident {incident.get('incident_id', '')}")
        self.setMinimumSize(620, 700)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.incident = incident
        self.editable = editable
        self._build()

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        inc = self.incident

        # Header
        sev = inc.get("severity", "Low")
        sev_color = SEVERITY_COLORS.get(sev, tc("text"))
        hdr = QLabel(f"{inc.get('incident_type', '')}  —  {sev} Severity")
        hdr.setFont(QFont("Segoe UI", 18, QFont.Bold))
        hdr.setStyleSheet(f"color: {sev_color};")
        layout.addWidget(hdr)

        # Info grid
        info_grid = QGridLayout()
        info_grid.setSpacing(8)
        fields = [
            ("Incident ID:", inc.get("incident_id", "")),
            ("Site:", inc.get("site", "")),
            ("Date:", inc.get("incident_date", "")),
            ("Time:", inc.get("incident_time", "")),
            ("Reporting Officer:", inc.get("reporting_officer", "")),
            ("Status:", inc.get("status", "")),
            ("Created By:", inc.get("created_by", "")),
            ("Created At:", inc.get("created_at", "")),
        ]
        for i, (label, value) in enumerate(fields):
            lbl = QLabel(label)
            lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
            lbl.setStyleSheet(f"color: {tc('text_light')};")
            val = QLabel(str(value))
            val.setFont(QFont("Segoe UI", 13))
            val.setStyleSheet(f"color: {tc('text')}; padding: 2px 0;")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            info_grid.addWidget(lbl, i, 0)
            info_grid.addWidget(val, i, 1)
        layout.addLayout(info_grid)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {tc('border')};")
        layout.addWidget(sep)

        # Text blocks
        for title, key in [
            ("Description", "description"),
            ("Persons Involved", "persons_involved"),
            ("Actions Taken", "actions_taken"),
            ("Witness Names", "witness_names"),
            ("Resolution", "resolution"),
        ]:
            text = inc.get(key, "")
            if text:
                t_lbl = QLabel(title)
                t_lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
                t_lbl.setStyleSheet(f"color: {tc('primary')};")
                layout.addWidget(t_lbl)
                v_lbl = QLabel(text)
                v_lbl.setWordWrap(True)
                v_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                v_lbl.setStyleSheet(f"""
                    background: {tc('card')}; border: 1px solid {tc('border')};
                    border-radius: 6px; padding: 10px; color: {tc('text')};
                """)
                layout.addWidget(v_lbl)

        # Boolean flags
        flags_row = QHBoxLayout()
        bool_flags = [
            ("Police Called", inc.get("police_called", 0)),
            ("Medical Required", inc.get("medical_required", 0)),
            ("Property Damage", inc.get("property_damage", 0)),
            ("Supervisor Notified", inc.get("supervisor_notified", 0)),
        ]
        for label, val in bool_flags:
            icon = "YES" if val else "NO"
            color = COLORS["danger"] if val else tc("text_light")
            flag_lbl = QLabel(f"{label}: {icon}")
            flag_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
            flag_lbl.setStyleSheet(f"color: {color};")
            flags_row.addWidget(flag_lbl)
        flags_row.addStretch()
        layout.addLayout(flags_row)

        if inc.get("police_report_number"):
            pr_lbl = QLabel(f"Police Report #: {inc['police_report_number']}")
            pr_lbl.setFont(QFont("Segoe UI", 13))
            pr_lbl.setStyleSheet(f"color: {tc('text')};")
            layout.addWidget(pr_lbl)

        if inc.get("supervisor_name"):
            sn_lbl = QLabel(f"Supervisor: {inc['supervisor_name']}")
            sn_lbl.setFont(QFont("Segoe UI", 13))
            sn_lbl.setStyleSheet(f"color: {tc('text')};")
            layout.addWidget(sn_lbl)

        # Status update section
        if self.editable:
            sep2 = QFrame()
            sep2.setFrameShape(QFrame.HLine)
            sep2.setStyleSheet(f"color: {tc('border')};")
            layout.addWidget(sep2)

            status_lbl = QLabel("Update Status")
            status_lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
            status_lbl.setStyleSheet(f"color: {tc('primary')};")
            layout.addWidget(status_lbl)

            status_row = QHBoxLayout()
            self.cmb_status = QComboBox()
            self.cmb_status.addItems(STATUS_WORKFLOW)
            idx = self.cmb_status.findText(inc.get("status", "Open"))
            if idx >= 0:
                self.cmb_status.setCurrentIndex(idx)
            status_row.addWidget(self.cmb_status)

            res_lbl = QLabel("Resolution:")
            res_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
            status_row.addWidget(res_lbl)
            layout.addLayout(status_row)

            self.txt_resolution = QTextEdit(inc.get("resolution", ""))
            self.txt_resolution.setMaximumHeight(80)
            layout.addWidget(self.txt_resolution)

        layout.addStretch()
        scroll.setWidget(content)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(24, 8, 24, 16)
        if self.editable:
            btn_save = QPushButton("Save Changes")
            btn_save.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
            btn_save.clicked.connect(self.accept)
            btn_row.addWidget(btn_save)
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(btn_style(tc("info"), "white", tc("primary")))
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        btn_row.addStretch()
        main_layout.addLayout(btn_row)

    def get_updates(self) -> dict:
        """Return status/resolution updates if editable."""
        if not self.editable:
            return {}
        return {
            "status": self.cmb_status.currentText(),
            "resolution": self.txt_resolution.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Log Incident Tab
# ════════════════════════════════════════════════════════════════════════

class LogIncidentTab(QWidget):
    """Form for logging a new incident."""

    def __init__(self, app_state, on_saved=None):
        super().__init__()
        self.app_state = app_state
        self.on_saved = on_saved
        self._build()

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        form_layout = QVBoxLayout(content)
        form_layout.setSpacing(16)
        form_layout.setContentsMargins(24, 24, 24, 24)

        # Title
        title = QLabel("Log Incident Report")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('primary')};")
        form_layout.addWidget(title)

        # ── Basic Info Group ──
        basic_group = QGroupBox("Incident Details")
        basic_lay = QFormLayout()
        basic_lay.setSpacing(10)

        # Site
        self.cmb_site = QComboBox()
        self.cmb_site.setEditable(True)
        sites = data_manager.get_site_names()
        self.cmb_site.addItems([s["name"] for s in sites])
        self.cmb_site.setCurrentIndex(-1)
        basic_lay.addRow("Site:", self.cmb_site)

        # Date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        basic_lay.addRow("Date:", self.date_edit)

        # Time
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime.currentTime())
        basic_lay.addRow("Time:", self.time_edit)

        # Incident Type
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(INCIDENT_TYPES)
        basic_lay.addRow("Incident Type:", self.cmb_type)

        # Severity
        self.cmb_severity = QComboBox()
        self.cmb_severity.addItems(SEVERITY_LEVELS)
        basic_lay.addRow("Severity:", self.cmb_severity)

        # Reporting Officer (autocomplete)
        self.txt_officer = QLineEdit()
        self.txt_officer.setPlaceholderText("Start typing officer name...")
        officer_names = data_manager.get_ops_officer_names()
        completer = QCompleter(officer_names)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.txt_officer.setCompleter(completer)
        basic_lay.addRow("Reporting Officer:", self.txt_officer)

        basic_group.setLayout(basic_lay)
        form_layout.addWidget(basic_group)

        # ── Description Group ──
        desc_group = QGroupBox("Description & Details")
        desc_lay = QFormLayout()
        desc_lay.setSpacing(10)

        self.txt_description = QTextEdit()
        self.txt_description.setPlaceholderText("Describe the incident in detail...")
        self.txt_description.setMinimumHeight(100)
        desc_lay.addRow("Description:", self.txt_description)

        self.txt_persons = QTextEdit()
        self.txt_persons.setPlaceholderText("Names and descriptions of persons involved...")
        self.txt_persons.setMaximumHeight(80)
        desc_lay.addRow("Persons Involved:", self.txt_persons)

        self.txt_actions = QTextEdit()
        self.txt_actions.setPlaceholderText("Actions taken in response to the incident...")
        self.txt_actions.setMaximumHeight(80)
        desc_lay.addRow("Actions Taken:", self.txt_actions)

        self.txt_witnesses = QLineEdit()
        self.txt_witnesses.setPlaceholderText("Witness names (comma-separated)")
        desc_lay.addRow("Witness Names:", self.txt_witnesses)

        desc_group.setLayout(desc_lay)
        form_layout.addWidget(desc_group)

        # ── Flags Group ──
        flags_group = QGroupBox("Additional Flags")
        flags_lay = QVBoxLayout()
        flags_lay.setSpacing(10)

        # Checkboxes row
        cb_row = QHBoxLayout()
        self.chk_police = QCheckBox("Police Called")
        self.chk_police.setStyleSheet(f"color: {tc('text')}; font-size: 14px;")
        self.chk_police.toggled.connect(self._on_police_toggled)
        cb_row.addWidget(self.chk_police)

        self.chk_medical = QCheckBox("Medical Required")
        self.chk_medical.setStyleSheet(f"color: {tc('text')}; font-size: 14px;")
        cb_row.addWidget(self.chk_medical)

        self.chk_damage = QCheckBox("Property Damage")
        self.chk_damage.setStyleSheet(f"color: {tc('text')}; font-size: 14px;")
        cb_row.addWidget(self.chk_damage)

        self.chk_supervisor = QCheckBox("Supervisor Notified")
        self.chk_supervisor.setStyleSheet(f"color: {tc('text')}; font-size: 14px;")
        cb_row.addWidget(self.chk_supervisor)

        cb_row.addStretch()
        flags_lay.addLayout(cb_row)

        # Police report # (conditionally shown)
        self.police_row = QHBoxLayout()
        self.lbl_police_report = QLabel("Police Report #:")
        self.lbl_police_report.setFont(QFont("Segoe UI", 13))
        self.txt_police_report = QLineEdit()
        self.txt_police_report.setPlaceholderText("Report number")
        self.police_row.addWidget(self.lbl_police_report)
        self.police_row.addWidget(self.txt_police_report)
        self.police_row.addStretch()
        self.lbl_police_report.setVisible(False)
        self.txt_police_report.setVisible(False)
        flags_lay.addLayout(self.police_row)

        flags_group.setLayout(flags_lay)
        form_layout.addWidget(flags_group)

        # ── Save Button ──
        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("Save Incident Report")
        self.btn_save.setFixedHeight(44)
        self.btn_save.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        self.btn_save.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.btn_save.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_save)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        form_layout.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _on_police_toggled(self, checked):
        self.lbl_police_report.setVisible(checked)
        self.txt_police_report.setVisible(checked)

    def refresh(self):
        pass  # No gating needed; save button always enabled

    def _save(self):
        site = self.cmb_site.currentText().strip()
        description = self.txt_description.toPlainText().strip()
        if not site:
            QMessageBox.warning(self, "Validation", "Site is required.")
            return
        if not description:
            QMessageBox.warning(self, "Validation", "Description is required.")
            return

        fields = {
            "site": site,
            "incident_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "incident_time": self.time_edit.time().toString("HH:mm"),
            "incident_type": self.cmb_type.currentText(),
            "severity": self.cmb_severity.currentText(),
            "reporting_officer": self.txt_officer.text().strip(),
            "description": description,
            "persons_involved": self.txt_persons.toPlainText().strip(),
            "actions_taken": self.txt_actions.toPlainText().strip(),
            "police_called": self.chk_police.isChecked(),
            "police_report_number": self.txt_police_report.text().strip() if self.chk_police.isChecked() else "",
            "medical_required": self.chk_medical.isChecked(),
            "property_damage": self.chk_damage.isChecked(),
            "witness_names": self.txt_witnesses.text().strip(),
            "supervisor_notified": self.chk_supervisor.isChecked(),
            "status": "Open",
        }

        username = self.app_state.get("user", {}).get("username", "")
        iid = data_manager.create_incident(fields, created_by=username)
        audit.log_event(
            "operations", "incident_create", username,
            f"Logged incident {iid}: {fields['incident_type']} at {site}",
        )

        QMessageBox.information(self, "Saved", f"Incident {iid} logged successfully.")
        self._reset_form()
        if self.on_saved:
            self.on_saved()

    def _reset_form(self):
        self.cmb_site.setCurrentIndex(-1)
        self.date_edit.setDate(QDate.currentDate())
        self.time_edit.setTime(QTime.currentTime())
        self.cmb_type.setCurrentIndex(0)
        self.cmb_severity.setCurrentIndex(0)
        self.txt_officer.clear()
        self.txt_description.clear()
        self.txt_persons.clear()
        self.txt_actions.clear()
        self.txt_witnesses.clear()
        self.chk_police.setChecked(False)
        self.chk_medical.setChecked(False)
        self.chk_damage.setChecked(False)
        self.chk_supervisor.setChecked(False)
        self.txt_police_report.clear()


# ════════════════════════════════════════════════════════════════════════
# Incident History Tab
# ════════════════════════════════════════════════════════════════════════

class IncidentHistoryTab(QWidget):
    """Filterable table of all incidents with detail drill-down."""

    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel("Incident History")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('primary')};")
        layout.addWidget(title)

        # Filters row 1: Status, Site, Severity
        filter_row = QHBoxLayout()

        filter_row.addWidget(QLabel("Status:"))
        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItems(["All"] + STATUS_WORKFLOW)
        self.cmb_filter_status.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.cmb_filter_status)

        filter_row.addWidget(QLabel("Site:"))
        self.cmb_filter_site = QComboBox()
        self.cmb_filter_site.addItems(["All"])
        sites = data_manager.get_site_names()
        self.cmb_filter_site.addItems([s["name"] for s in sites])
        self.cmb_filter_site.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.cmb_filter_site)

        filter_row.addWidget(QLabel("Severity:"))
        self.cmb_filter_severity = QComboBox()
        self.cmb_filter_severity.addItems(["All"] + SEVERITY_LEVELS)
        self.cmb_filter_severity.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.cmb_filter_severity)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(btn_style(tc("info"), "white", tc("primary")))
        btn_refresh.clicked.connect(self.refresh)
        filter_row.addWidget(btn_refresh)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Filters row 2: Date range
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("From:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setSpecialValueText(" ")  # blank when cleared
        self.date_from.setDate(self.date_from.minimumDate())  # start cleared
        self.date_from.dateChanged.connect(self._apply_filters)
        date_row.addWidget(self.date_from)

        date_row.addWidget(QLabel("To:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setSpecialValueText(" ")
        self.date_to.setDate(self.date_to.minimumDate())
        self.date_to.dateChanged.connect(self._apply_filters)
        date_row.addWidget(self.date_to)

        btn_clear_dates = QPushButton("Clear Dates")
        btn_clear_dates.setStyleSheet(btn_style(tc("info"), "white", tc("primary")))
        btn_clear_dates.clicked.connect(self._clear_dates)
        date_row.addWidget(btn_clear_dates)

        date_row.addStretch()
        layout.addLayout(date_row)

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Date", "Site", "Type", "Severity", "Officer", "Status", "ID"
        ])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        for c in [0, 3, 5, 6]:
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {tc('primary')};
                color: white; font-weight: 600; font-size: 14px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._view_detail)
        layout.addWidget(self.table)

        # Bottom buttons
        btn_row = QHBoxLayout()
        self.btn_view = QPushButton("View Details")
        self.btn_view.setStyleSheet(btn_style(tc("info"), "white", tc("primary")))
        self.btn_view.clicked.connect(self._view_detail)
        btn_row.addWidget(self.btn_view)

        self.btn_escalate = QPushButton("Escalate")
        self.btn_escalate.setStyleSheet(btn_style(COLORS["danger"], "white", "#b71c1c"))
        self.btn_escalate.clicked.connect(self._escalate_incident)
        btn_row.addWidget(self.btn_escalate)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _clear_dates(self):
        """Reset date range filters to unset."""
        self.date_from.setDate(self.date_from.minimumDate())
        self.date_to.setDate(self.date_to.minimumDate())
        self._apply_filters()

    def refresh(self):
        status_filter = self.cmb_filter_status.currentText()
        if status_filter == "All":
            status_filter = ""
        site_filter = self.cmb_filter_site.currentText()
        if site_filter == "All":
            site_filter = ""

        # Date range: only pass if not at minimum (cleared) value
        date_from = ""
        date_to = ""
        if self.date_from.date() != self.date_from.minimumDate():
            date_from = self.date_from.date().toString("yyyy-MM-dd")
        if self.date_to.date() != self.date_to.minimumDate():
            date_to = self.date_to.date().toString("yyyy-MM-dd")

        incidents = data_manager.get_all_incidents(
            status_filter=status_filter, site_filter=site_filter,
            date_from=date_from, date_to=date_to,
        )

        # Apply severity filter client-side
        sev_filter = self.cmb_filter_severity.currentText()
        if sev_filter != "All":
            incidents = [i for i in incidents if i.get("severity", "") == sev_filter]

        self.table.setRowCount(len(incidents))
        for row, inc in enumerate(incidents):
            is_critical = inc.get("severity", "") in ("Critical", "Emergency")
            row_bg = QColor("#4d0000") if is_critical else None

            # Date
            date_item = QTableWidgetItem(inc.get("incident_date", ""))
            if row_bg:
                date_item.setBackground(row_bg)
            self.table.setItem(row, 0, date_item)

            # Site
            site_item = QTableWidgetItem(inc.get("site", ""))
            if row_bg:
                site_item.setBackground(row_bg)
            self.table.setItem(row, 1, site_item)

            # Type
            type_item = QTableWidgetItem(inc.get("incident_type", ""))
            if row_bg:
                type_item.setBackground(row_bg)
            self.table.setItem(row, 2, type_item)

            # Severity (color-coded)
            sev = inc.get("severity", "Low")
            sev_item = QTableWidgetItem(sev)
            sev_color = SEVERITY_COLORS.get(sev, tc("text"))
            sev_item.setForeground(QColor(sev_color))
            sev_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            if row_bg:
                sev_item.setBackground(row_bg)
            self.table.setItem(row, 3, sev_item)

            # Officer
            officer_item = QTableWidgetItem(inc.get("reporting_officer", ""))
            if row_bg:
                officer_item.setBackground(row_bg)
            self.table.setItem(row, 4, officer_item)

            # Status (color-coded)
            status = inc.get("status", "Open")
            status_item = QTableWidgetItem(status)
            status_colors = {
                "Open": COLORS["warning"],
                "Under Review": COLORS["info"],
                "Escalated": COLORS["danger"],
                "Resolved": COLORS["success"],
                "Closed": tc("text_light"),
            }
            s_color = status_colors.get(status, tc("text"))
            status_item.setForeground(QColor(s_color))
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            if row_bg:
                status_item.setBackground(row_bg)
            self.table.setItem(row, 5, status_item)

            # ID
            id_item = QTableWidgetItem(inc.get("incident_id", ""))
            id_item.setForeground(QColor(tc("text_light")))
            id_item.setFont(QFont("Consolas", 11))
            if row_bg:
                id_item.setBackground(row_bg)
            self.table.setItem(row, 6, id_item)

    def _apply_filters(self):
        self.refresh()

    def _get_selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 6)
        return item.text() if item else None

    def _escalate_incident(self):
        """Escalate the selected incident: set status to Escalated and log to audit."""
        iid = self._get_selected_id()
        if not iid:
            QMessageBox.information(self, "Select", "Please select an incident to escalate.")
            return
        inc = data_manager.get_incident(iid)
        if not inc:
            QMessageBox.warning(self, "Not Found", f"Incident {iid} not found.")
            return
        if inc.get("status") == "Escalated":
            QMessageBox.information(self, "Already Escalated",
                                    f"Incident {iid} is already escalated.")
            return

        reply = QMessageBox.question(
            self, "Confirm Escalation",
            f"Escalate incident {iid} ({inc.get('incident_type', '')}, "
            f"{inc.get('severity', '')} severity)?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        username = self.app_state.get("user", {}).get("username", "")
        data_manager.update_incident(iid, {"status": "Escalated"}, updated_by=username)
        audit.log_event(
            "operations", "incident_escalate", username,
            f"Escalated incident {iid}: {inc.get('incident_type', '')} "
            f"({inc.get('severity', '')} severity) at {inc.get('site', '')}",
        )
        QMessageBox.information(self, "Escalated", f"Incident {iid} has been escalated.")
        self.refresh()

    def _view_detail(self):
        iid = self._get_selected_id()
        if not iid:
            QMessageBox.information(self, "Select", "Please select an incident to view.")
            return
        inc = data_manager.get_incident(iid)
        if not inc:
            QMessageBox.warning(self, "Not Found", f"Incident {iid} not found.")
            return

        dlg = IncidentDetailDialog(self, inc, editable=True)
        if dlg.exec() == QDialog.Accepted:
            updates = dlg.get_updates()
            if updates:
                username = self.app_state.get("user", {}).get("username", "")
                data_manager.update_incident(iid, updates, updated_by=username)
                audit.log_event(
                    "operations", "incident_update", username,
                    f"Updated incident {iid} status to {updates.get('status', '')}",
                )
                self.refresh()


# ════════════════════════════════════════════════════════════════════════
# Main Incidents Page (Tab container)
# ════════════════════════════════════════════════════════════════════════

class IncidentsPage(QWidget):
    """Single-page incident management with Log / History tabs."""

    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {tc('bg')};
            }}
            QTabBar::tab {{
                background: {tc('card')};
                color: {tc('text_light')};
                padding: 10px 28px;
                font-size: 15px;
                font-weight: 600;
                border: 1px solid {tc('border')};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {tc('bg')};
                color: {COLORS['accent']};
                border-bottom: 3px solid {COLORS['accent']};
            }}
            QTabBar::tab:hover {{
                color: {tc('text')};
            }}
        """)

        self.log_tab = LogIncidentTab(self.app_state, on_saved=self._on_incident_saved)
        self.history_tab = IncidentHistoryTab(self.app_state)

        self.tabs.addTab(self.log_tab, "Log Incident")
        self.tabs.addTab(self.history_tab, "Incident History")

        layout.addWidget(self.tabs)

    def _on_incident_saved(self):
        """Switch to history tab and refresh after saving."""
        self.history_tab.refresh()

    def refresh(self):
        self.log_tab.refresh()
        self.history_tab.refresh()
