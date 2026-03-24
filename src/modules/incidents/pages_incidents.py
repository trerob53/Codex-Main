"""
Cerasus Hub -- Incidents Module: Incident Log, New Report, and Investigation Queue pages.
"""

import csv
import json
import os
from datetime import datetime, date as dt_date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QMessageBox, QFileDialog, QFormLayout,
    QGroupBox, QAbstractItemView, QDialog, QDialogButtonBox,
    QScrollArea, QCheckBox, QDateEdit, QTimeEdit,
)
from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtGui import QFont, QColor

from src.config import (
    COLORS, ROLE_ADMIN, tc, _is_dark, btn_style,
    build_dialog_stylesheet, REPORTS_DIR, ensure_directories,
)
from src.shared_widgets import confirm_action
from src.modules.incidents import data_manager
from src import audit


# ── Severity color helpers ────────────────────────────────────────────

SEVERITY_COLORS = {
    "Low": "#059669",
    "Medium": "#D97706",
    "High": "#EA580C",
    "Critical": "#DC2626",
}

STATUS_COLORS = {
    "Open": "#2563EB",
    "Under Investigation": "#D97706",
    "Resolved": "#059669",
    "Closed": "#6B7280",
}


# ════════════════════════════════════════════════════════════════════════
# Incident Detail / Edit Dialog
# ════════════════════════════════════════════════════════════════════════

class IncidentDialog(QDialog):
    """Dialog for viewing / editing an existing incident."""

    def __init__(self, parent=None, incident=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Incident" if incident else "Incident Details")
        self.setMinimumWidth(620)
        self.setMinimumHeight(500)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.incident = incident or {}
        self._build()

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("border: none;")

        container = QWidget()
        layout = QFormLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Status
        self.status_input = QComboBox()
        self.status_input.addItems(data_manager.STATUS_OPTIONS)
        idx = self.status_input.findText(self.incident.get("status", "Open"))
        if idx >= 0:
            self.status_input.setCurrentIndex(idx)
        layout.addRow("Status:", self.status_input)

        # Severity
        self.severity_input = QComboBox()
        self.severity_input.addItems(data_manager.SEVERITY_LEVELS)
        idx = self.severity_input.findText(self.incident.get("severity", "Low"))
        if idx >= 0:
            self.severity_input.setCurrentIndex(idx)
        layout.addRow("Severity:", self.severity_input)

        # Title
        self.title_input = QLineEdit()
        self.title_input.setText(self.incident.get("title", ""))
        layout.addRow("Title:", self.title_input)

        # Assigned To
        self.assigned_input = QComboBox()
        self.assigned_input.setEditable(True)
        officer_names = data_manager.get_officer_names()
        self.assigned_input.addItem("")
        self.assigned_input.addItems(officer_names)
        assigned = self.incident.get("assigned_to", "")
        aidx = self.assigned_input.findText(assigned)
        if aidx >= 0:
            self.assigned_input.setCurrentIndex(aidx)
        else:
            self.assigned_input.setEditText(assigned)
        layout.addRow("Assigned To:", self.assigned_input)

        # Resolution
        self.resolution_input = QTextEdit()
        self.resolution_input.setMaximumHeight(100)
        self.resolution_input.setPlainText(self.incident.get("resolution", ""))
        layout.addRow("Resolution:", self.resolution_input)

        # Resolved by
        self.resolved_by_input = QLineEdit()
        self.resolved_by_input.setText(self.incident.get("resolved_by", ""))
        layout.addRow("Resolved By:", self.resolved_by_input)

        # Follow-up
        self.follow_up_check = QCheckBox("Follow-up Required")
        self.follow_up_check.setChecked(bool(self.incident.get("follow_up_required", 0)))
        layout.addRow("", self.follow_up_check)

        self.follow_up_notes_input = QTextEdit()
        self.follow_up_notes_input.setMaximumHeight(80)
        self.follow_up_notes_input.setPlainText(self.incident.get("follow_up_notes", ""))
        layout.addRow("Follow-up Notes:", self.follow_up_notes_input)

        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.addWidget(scroll)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

    def get_data(self) -> dict:
        resolved_date = ""
        if self.status_input.currentText() in ("Resolved", "Closed"):
            resolved_date = datetime.now().strftime("%Y-%m-%d")
        return {
            "status": self.status_input.currentText(),
            "severity": self.severity_input.currentText(),
            "title": self.title_input.text().strip(),
            "assigned_to": self.assigned_input.currentText().strip(),
            "resolution": self.resolution_input.toPlainText().strip(),
            "resolved_by": self.resolved_by_input.text().strip(),
            "resolved_date": resolved_date,
            "follow_up_required": 1 if self.follow_up_check.isChecked() else 0,
            "follow_up_notes": self.follow_up_notes_input.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Incident Log Page
# ════════════════════════════════════════════════════════════════════════

class IncidentLogPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _get_username(self) -> str:
        return self.app_state.get("username", "admin")

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Incident Log")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        header_row.addWidget(title)
        header_row.addStretch()

        btn_export = QPushButton("Export CSV")
        btn_export.setCursor(Qt.PointingHandCursor)
        btn_export.setFixedHeight(38)
        btn_export.setStyleSheet(btn_style(tc("info"), "white"))
        btn_export.clicked.connect(self._export_csv)
        header_row.addWidget(btn_export)
        layout.addLayout(header_row)

        # Filters row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search incidents...")
        self.search_input.setFixedHeight(36)
        self.search_input.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.search_input)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Statuses"] + data_manager.STATUS_OPTIONS)
        self.status_filter.setFixedHeight(36)
        self.status_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.status_filter)

        self.severity_filter = QComboBox()
        self.severity_filter.addItems(["All Severities"] + data_manager.SEVERITY_LEVELS)
        self.severity_filter.setFixedHeight(36)
        self.severity_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.severity_filter)

        self.site_filter = QComboBox()
        self.site_filter.addItems(["All Sites"])
        self.site_filter.setFixedHeight(36)
        self.site_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.site_filter)

        layout.addLayout(filter_row)

        # Date range
        date_row = QHBoxLayout()
        date_row.setSpacing(12)
        lbl_from = QLabel("From:")
        lbl_from.setStyleSheet(f"color: {tc('text')}; font-size: 14px;")
        date_row.addWidget(lbl_from)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-3))
        self.date_from.setFixedHeight(36)
        self.date_from.dateChanged.connect(self._apply_filters)
        date_row.addWidget(self.date_from)

        lbl_to = QLabel("To:")
        lbl_to.setStyleSheet(f"color: {tc('text')}; font-size: 14px;")
        date_row.addWidget(lbl_to)
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setFixedHeight(36)
        self.date_to.dateChanged.connect(self._apply_filters)
        date_row.addWidget(self.date_to)

        date_row.addStretch()
        layout.addLayout(date_row)

        # Table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Date", "Type", "Site", "Severity", "Status", "Officer", "Title"
        ])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed)
        hdr.setSectionResizeMode(6, QHeaderView.Fixed)
        hdr.setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(6, 120)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Internal data cache
        self._all_incidents = []

    def _apply_filters(self):
        """Filter the cached incidents and repopulate the table."""
        search = self.search_input.text().strip().lower()
        status = self.status_filter.currentText()
        severity = self.severity_filter.currentText()
        site = self.site_filter.currentText()
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")

        filtered = []
        for inc in self._all_incidents:
            # Date range
            d = inc.get("incident_date", "")
            if d and (d < date_from or d > date_to):
                continue
            # Status
            if status != "All Statuses" and inc.get("status", "") != status:
                continue
            # Severity
            if severity != "All Severities" and inc.get("severity", "") != severity:
                continue
            # Site
            if site != "All Sites" and inc.get("site", "") != site:
                continue
            # Search
            if search:
                haystack = " ".join(str(v) for v in inc.values()).lower()
                if search not in haystack:
                    continue
            filtered.append(inc)

        self._populate_table(filtered)

    def _populate_table(self, incidents: list):
        self.table.setRowCount(len(incidents))
        for i, inc in enumerate(incidents):
            self.table.setItem(i, 0, QTableWidgetItem(inc.get("incident_id", "")))
            self.table.setItem(i, 1, QTableWidgetItem(inc.get("incident_date", "")))
            self.table.setItem(i, 2, QTableWidgetItem(inc.get("incident_type", "")))
            self.table.setItem(i, 3, QTableWidgetItem(inc.get("site", "")))

            # Severity with color
            sev = inc.get("severity", "")
            sev_item = QTableWidgetItem(sev)
            sev_item.setTextAlignment(Qt.AlignCenter)
            sev_item.setForeground(QColor(SEVERITY_COLORS.get(sev, "#6B7280")))
            sev_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(i, 4, sev_item)

            # Status with color
            status = inc.get("status", "")
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QColor(STATUS_COLORS.get(status, "#6B7280")))
            status_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(i, 5, status_item)

            self.table.setItem(i, 6, QTableWidgetItem(inc.get("officer_name", "")))
            self.table.setItem(i, 7, QTableWidgetItem(inc.get("title", "")))

    def _on_double_click(self, index):
        row = index.row()
        iid_item = self.table.item(row, 0)
        if not iid_item:
            return
        iid = iid_item.text()
        incident = data_manager.get_incident(iid)
        if not incident:
            return
        dlg = IncidentDialog(self, incident)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_data()
            data_manager.update_incident(iid, fields, self._get_username())
            audit.log_event("incidents", "incident_updated", self._get_username(),
                            f"Incident {iid} updated", record_id=iid)
            self.refresh()

    def _export_csv(self):
        ensure_directories()
        csv_text = data_manager.export_incidents_csv()
        if not csv_text:
            QMessageBox.information(self, "No Data", "No incidents to export.")
            return
        path = os.path.join(REPORTS_DIR, "incidents_export.csv")
        try:
            with open(path, "w", newline="") as f:
                f.write(csv_text)
            QMessageBox.information(self, "Exported", f"Incidents exported to:\n{path}")
            audit.log_event("incidents", "csv_exported", self._get_username(),
                            f"Path: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def refresh(self):
        self._all_incidents = data_manager.get_all_incidents()

        # Update site filter options
        sites = sorted(set(inc.get("site", "") for inc in self._all_incidents if inc.get("site")))
        current_site = self.site_filter.currentText()
        self.site_filter.blockSignals(True)
        self.site_filter.clear()
        self.site_filter.addItems(["All Sites"] + sites)
        idx = self.site_filter.findText(current_site)
        if idx >= 0:
            self.site_filter.setCurrentIndex(idx)
        self.site_filter.blockSignals(False)

        self._apply_filters()


# ════════════════════════════════════════════════════════════════════════
# New Report Page
# ════════════════════════════════════════════════════════════════════════

class NewReportPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _get_username(self) -> str:
        return self.app_state.get("username", "admin")

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("New Incident Report")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        header_row.addWidget(title)
        header_row.addStretch()
        layout.addLayout(header_row)

        group_style = f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """

        # ── Section 1: Incident Details ───────────────────────────────
        details_group = QGroupBox("Incident Details")
        details_group.setStyleSheet(group_style)
        details_form = QFormLayout(details_group)
        details_form.setSpacing(10)
        details_form.setContentsMargins(16, 28, 16, 16)

        self.type_input = QComboBox()
        self.type_input.addItems(data_manager.INCIDENT_TYPES)
        details_form.addRow("Type:", self.type_input)

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())
        details_form.addRow("Date:", self.date_input)

        self.time_input = QTimeEdit()
        self.time_input.setDisplayFormat("HH:mm")
        self.time_input.setTime(QTime.currentTime())
        details_form.addRow("Time:", self.time_input)

        self.site_input = QComboBox()
        self.site_input.setEditable(True)
        site_names = data_manager.get_site_names()
        self.site_input.addItems([s["name"] for s in site_names])
        details_form.addRow("Site:", self.site_input)

        self.severity_input = QComboBox()
        self.severity_input.addItems(data_manager.SEVERITY_LEVELS)
        details_form.addRow("Severity:", self.severity_input)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Brief incident title")
        details_form.addRow("Title:", self.title_input)

        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Detailed description of the incident...")
        self.description_input.setMaximumHeight(120)
        details_form.addRow("Description:", self.description_input)

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("Specific area within site (e.g. Lobby, Parking Lot B)")
        details_form.addRow("Location Detail:", self.location_input)

        layout.addWidget(details_group)

        # ── Section 2: People Involved ────────────────────────────────
        people_group = QGroupBox("People Involved")
        people_group.setStyleSheet(group_style)
        people_form = QFormLayout(people_group)
        people_form.setSpacing(10)
        people_form.setContentsMargins(16, 28, 16, 16)

        self.officer_input = QComboBox()
        self.officer_input.setEditable(True)
        officer_names = data_manager.get_officer_names()
        self.officer_input.addItems(officer_names)
        # Auto-populate to current user
        current_user = self.app_state.get("username", "")
        cidx = self.officer_input.findText(current_user)
        if cidx >= 0:
            self.officer_input.setCurrentIndex(cidx)
        people_form.addRow("Reporting Officer:", self.officer_input)

        self.persons_input = QTextEdit()
        self.persons_input.setPlaceholderText("Names and descriptions of persons involved (one per line)")
        self.persons_input.setMaximumHeight(80)
        people_form.addRow("Persons Involved:", self.persons_input)

        self.witnesses_input = QTextEdit()
        self.witnesses_input.setPlaceholderText("Witness names and contact info")
        self.witnesses_input.setMaximumHeight(80)
        people_form.addRow("Witnesses:", self.witnesses_input)

        layout.addWidget(people_group)

        # ── Section 3: Response ───────────────────────────────────────
        response_group = QGroupBox("Response")
        response_group.setStyleSheet(group_style)
        response_form = QFormLayout(response_group)
        response_form.setSpacing(10)
        response_form.setContentsMargins(16, 28, 16, 16)

        self.police_check = QCheckBox("Police Called")
        response_form.addRow("", self.police_check)

        self.police_report_input = QLineEdit()
        self.police_report_input.setPlaceholderText("Police report number (if applicable)")
        response_form.addRow("Police Report #:", self.police_report_input)

        self.injuries_check = QCheckBox("Injuries Reported")
        response_form.addRow("", self.injuries_check)

        self.injury_details_input = QTextEdit()
        self.injury_details_input.setPlaceholderText("Describe injuries and medical response")
        self.injury_details_input.setMaximumHeight(80)
        response_form.addRow("Injury Details:", self.injury_details_input)

        self.damage_check = QCheckBox("Property Damage")
        response_form.addRow("", self.damage_check)

        self.damage_desc_input = QTextEdit()
        self.damage_desc_input.setPlaceholderText("Describe property damage")
        self.damage_desc_input.setMaximumHeight(80)
        response_form.addRow("Damage Description:", self.damage_desc_input)

        self.action_input = QTextEdit()
        self.action_input.setPlaceholderText("Immediate action taken by responding officer")
        self.action_input.setMaximumHeight(100)
        response_form.addRow("Immediate Action:", self.action_input)

        layout.addWidget(response_group)

        # ── Action buttons ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.addStretch()

        btn_clear = QPushButton("Clear Form")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setFixedHeight(42)
        btn_clear.setFixedWidth(140)
        btn_clear.setStyleSheet(btn_style(tc("border"), tc("text")))
        btn_clear.clicked.connect(self._clear_form)
        btn_row.addWidget(btn_clear)

        btn_submit = QPushButton("Submit Report")
        btn_submit.setCursor(Qt.PointingHandCursor)
        btn_submit.setFixedHeight(42)
        btn_submit.setFixedWidth(180)
        btn_submit.setStyleSheet(btn_style(tc("accent"), "white", tc("accent_hover")))
        btn_submit.clicked.connect(self._submit_report)
        btn_row.addWidget(btn_submit)

        layout.addLayout(btn_row)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _clear_form(self):
        self.type_input.setCurrentIndex(0)
        self.date_input.setDate(QDate.currentDate())
        self.time_input.setTime(QTime.currentTime())
        if self.site_input.count() > 0:
            self.site_input.setCurrentIndex(0)
        self.severity_input.setCurrentIndex(0)
        self.title_input.clear()
        self.description_input.clear()
        self.location_input.clear()
        if self.officer_input.count() > 0:
            self.officer_input.setCurrentIndex(0)
        self.persons_input.clear()
        self.witnesses_input.clear()
        self.police_check.setChecked(False)
        self.police_report_input.clear()
        self.injuries_check.setChecked(False)
        self.injury_details_input.clear()
        self.damage_check.setChecked(False)
        self.damage_desc_input.clear()
        self.action_input.clear()

    def _submit_report(self):
        title = self.title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing Title", "Please enter an incident title.")
            return

        description = self.description_input.toPlainText().strip()
        if not description:
            QMessageBox.warning(self, "Missing Description", "Please describe the incident.")
            return

        # Build persons_involved as JSON array
        persons_text = self.persons_input.toPlainText().strip()
        persons_list = [p.strip() for p in persons_text.split("\n") if p.strip()] if persons_text else []

        fields = {
            "incident_type": self.type_input.currentText(),
            "incident_date": self.date_input.date().toString("yyyy-MM-dd"),
            "incident_time": self.time_input.time().toString("HH:mm"),
            "site": self.site_input.currentText().strip(),
            "severity": self.severity_input.currentText(),
            "title": title,
            "description": description,
            "location_detail": self.location_input.text().strip(),
            "officer_name": self.officer_input.currentText().strip(),
            "officer_id": self.app_state.get("officer_id", self.app_state.get("user_id", "")),
            "persons_involved": json.dumps(persons_list),
            "witnesses": self.witnesses_input.toPlainText().strip(),
            "police_called": 1 if self.police_check.isChecked() else 0,
            "police_report_number": self.police_report_input.text().strip(),
            "injuries_reported": 1 if self.injuries_check.isChecked() else 0,
            "injury_details": self.injury_details_input.toPlainText().strip(),
            "property_damage": 1 if self.damage_check.isChecked() else 0,
            "damage_description": self.damage_desc_input.toPlainText().strip(),
            "immediate_action": self.action_input.toPlainText().strip(),
            "status": "Open",
        }

        username = self._get_username()
        iid = data_manager.create_incident(fields, created_by=username)
        audit.log_event("incidents", "incident_created", username,
                        f"Incident {iid}: {title}", record_id=iid)

        QMessageBox.information(self, "Report Submitted",
                                f"Incident report created successfully.\n\nID: {iid}")
        self._clear_form()

    def refresh(self):
        # Refresh site and officer dropdowns
        site_names = data_manager.get_site_names()
        current_site = self.site_input.currentText()
        self.site_input.blockSignals(True)
        self.site_input.clear()
        self.site_input.addItems([s["name"] for s in site_names])
        idx = self.site_input.findText(current_site)
        if idx >= 0:
            self.site_input.setCurrentIndex(idx)
        self.site_input.blockSignals(False)

        officer_names = data_manager.get_officer_names()
        current_officer = self.officer_input.currentText()
        self.officer_input.blockSignals(True)
        self.officer_input.clear()
        self.officer_input.addItems(officer_names)
        oidx = self.officer_input.findText(current_officer)
        if oidx >= 0:
            self.officer_input.setCurrentIndex(oidx)
        self.officer_input.blockSignals(False)


# ════════════════════════════════════════════════════════════════════════
# Resolution Dialog (for Investigation Queue quick-resolve)
# ════════════════════════════════════════════════════════════════════════

class ResolutionDialog(QDialog):
    """Quick-resolve dialog for the investigation queue."""

    def __init__(self, parent=None, incident=None):
        super().__init__(parent)
        self.setWindowTitle("Resolve Incident")
        self.setMinimumWidth(480)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.incident = incident or {}
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl = QLabel(f"Resolving: {self.incident.get('incident_id', '')} - {self.incident.get('title', '')}")
        lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl.setWordWrap(True)
        layout.addRow(lbl)

        self.resolution_input = QTextEdit()
        self.resolution_input.setPlaceholderText("Describe how the incident was resolved...")
        self.resolution_input.setMaximumHeight(120)
        layout.addRow("Resolution:", self.resolution_input)

        self.resolved_by_input = QLineEdit()
        layout.addRow("Resolved By:", self.resolved_by_input)

        self.follow_up_check = QCheckBox("Follow-up Required")
        layout.addRow("", self.follow_up_check)

        self.follow_up_notes_input = QTextEdit()
        self.follow_up_notes_input.setPlaceholderText("Follow-up notes...")
        self.follow_up_notes_input.setMaximumHeight(80)
        layout.addRow("Follow-up Notes:", self.follow_up_notes_input)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_data(self) -> dict:
        return {
            "status": "Resolved",
            "resolution": self.resolution_input.toPlainText().strip(),
            "resolved_by": self.resolved_by_input.text().strip(),
            "resolved_date": datetime.now().strftime("%Y-%m-%d"),
            "follow_up_required": 1 if self.follow_up_check.isChecked() else 0,
            "follow_up_notes": self.follow_up_notes_input.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Investigation Queue Page
# ════════════════════════════════════════════════════════════════════════

class InvestigationPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _get_username(self) -> str:
        return self.app_state.get("username", "admin")

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        self.main_layout = QVBoxLayout(container)
        self.main_layout.setContentsMargins(30, 24, 30, 24)
        self.main_layout.setSpacing(16)

        # Header
        header = QLabel("Investigation Queue")
        header.setFont(QFont("Segoe UI", 22, QFont.Bold))
        header.setStyleSheet(f"color: {tc('text')};")
        self.main_layout.addWidget(header)

        subtitle = QLabel("Open and Under Investigation incidents, sorted by severity (Critical first)")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px;")
        self.main_layout.addWidget(subtitle)

        # Cards container
        self.cards_container = QVBoxLayout()
        self.cards_container.setSpacing(12)
        self.main_layout.addLayout(self.cards_container)

        self.main_layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _clear_cards(self):
        while self.cards_container.count():
            item = self.cards_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _make_incident_card(self, inc: dict) -> QFrame:
        iid = inc.get("incident_id", "")
        sev = inc.get("severity", "Low")
        status = inc.get("status", "Open")

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-left: 5px solid {SEVERITY_COLORS.get(sev, '#6B7280')};
                border-radius: 8px;
            }}
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(16, 12, 16, 12)
        card_lay.setSpacing(8)

        # Top row: ID, severity badge, status badge
        top_row = QHBoxLayout()
        lbl_id = QLabel(iid)
        lbl_id.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl_id.setStyleSheet(f"color: {tc('text')}; border: none;")
        top_row.addWidget(lbl_id)

        sev_badge = QLabel(f"  {sev}  ")
        sev_badge.setStyleSheet(f"""
            background: {SEVERITY_COLORS.get(sev, '#6B7280')}; color: white;
            border-radius: 4px; font-size: 12px; font-weight: 700; padding: 2px 8px;
        """)
        top_row.addWidget(sev_badge)

        status_badge = QLabel(f"  {status}  ")
        status_badge.setStyleSheet(f"""
            background: {STATUS_COLORS.get(status, '#6B7280')}; color: white;
            border-radius: 4px; font-size: 12px; font-weight: 700; padding: 2px 8px;
        """)
        top_row.addWidget(status_badge)

        top_row.addStretch()

        # Date
        date_lbl = QLabel(f"{inc.get('incident_date', '')} {inc.get('incident_time', '')}")
        date_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; border: none;")
        top_row.addWidget(date_lbl)
        card_lay.addLayout(top_row)

        # Title and type
        title_lbl = QLabel(f"{inc.get('incident_type', '')} - {inc.get('title', '')}")
        title_lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {tc('text')}; border: none;")
        title_lbl.setWordWrap(True)
        card_lay.addWidget(title_lbl)

        # Info line
        info_parts = []
        if inc.get("site"):
            info_parts.append(f"Site: {inc['site']}")
        if inc.get("officer_name"):
            info_parts.append(f"Reported by: {inc['officer_name']}")
        if inc.get("assigned_to"):
            info_parts.append(f"Assigned to: {inc['assigned_to']}")
        if info_parts:
            info_lbl = QLabel("  |  ".join(info_parts))
            info_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; border: none;")
            card_lay.addWidget(info_lbl)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        # Assign To
        assign_combo = QComboBox()
        assign_combo.setEditable(True)
        assign_combo.setFixedWidth(160)
        assign_combo.setFixedHeight(32)
        assign_combo.addItem("")
        assign_combo.addItems(data_manager.get_officer_names())
        if inc.get("assigned_to"):
            aidx = assign_combo.findText(inc["assigned_to"])
            if aidx >= 0:
                assign_combo.setCurrentIndex(aidx)
            else:
                assign_combo.setEditText(inc["assigned_to"])
        btn_row.addWidget(assign_combo)

        btn_assign = QPushButton("Assign")
        btn_assign.setCursor(Qt.PointingHandCursor)
        btn_assign.setFixedSize(70, 32)
        btn_assign.setStyleSheet(btn_style(tc("info"), "white"))
        btn_assign.clicked.connect(
            lambda checked, i=iid, c=assign_combo: self._assign_incident(i, c.currentText().strip())
        )
        btn_row.addWidget(btn_assign)

        if status == "Open":
            btn_investigate = QPushButton("Start Investigation")
            btn_investigate.setCursor(Qt.PointingHandCursor)
            btn_investigate.setFixedSize(140, 32)
            btn_investigate.setStyleSheet(btn_style(tc("warning"), "white"))
            btn_investigate.clicked.connect(lambda checked, i=iid: self._start_investigation(i))
            btn_row.addWidget(btn_investigate)

        btn_resolve = QPushButton("Resolve")
        btn_resolve.setCursor(Qt.PointingHandCursor)
        btn_resolve.setFixedSize(80, 32)
        btn_resolve.setStyleSheet(btn_style(tc("success"), "white"))
        btn_resolve.clicked.connect(lambda checked, i=iid, inc_data=inc: self._resolve_incident(i, inc_data))
        btn_row.addWidget(btn_resolve)

        btn_close = QPushButton("Close")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setFixedSize(60, 32)
        btn_close.setStyleSheet(btn_style(tc("border"), tc("text")))
        btn_close.clicked.connect(lambda checked, i=iid: self._close_incident(i))
        btn_row.addWidget(btn_close)

        card_lay.addLayout(btn_row)
        return card

    def _assign_incident(self, incident_id: str, assignee: str):
        if not assignee:
            QMessageBox.warning(self, "No Assignee", "Please select an officer to assign.")
            return
        data_manager.update_incident(incident_id, {"assigned_to": assignee}, self._get_username())
        audit.log_event("incidents", "incident_assigned", self._get_username(),
                        f"Incident {incident_id} assigned to {assignee}", record_id=incident_id)
        self.refresh()

    def _start_investigation(self, incident_id: str):
        data_manager.update_incident(
            incident_id, {"status": "Under Investigation"}, self._get_username()
        )
        audit.log_event("incidents", "investigation_started", self._get_username(),
                        f"Incident {incident_id}", record_id=incident_id)
        self.refresh()

    def _resolve_incident(self, incident_id: str, incident: dict):
        dlg = ResolutionDialog(self, incident)
        dlg.resolved_by_input.setText(self._get_username())
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_data()
            data_manager.update_incident(incident_id, fields, self._get_username())
            audit.log_event("incidents", "incident_resolved", self._get_username(),
                            f"Incident {incident_id} resolved", record_id=incident_id)
            self.refresh()

    def _close_incident(self, incident_id: str):
        if not confirm_action(self, "Close Incident",
                              f"Close incident {incident_id}? This marks it as Closed."):
            return
        data_manager.update_incident(
            incident_id, {"status": "Closed"}, self._get_username()
        )
        audit.log_event("incidents", "incident_closed", self._get_username(),
                        f"Incident {incident_id}", record_id=incident_id)
        self.refresh()

    def refresh(self):
        self._clear_cards()
        queue = data_manager.get_investigation_queue()

        if not queue:
            lbl = QLabel("No open or under investigation incidents.")
            lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 15px; padding: 20px;")
            lbl.setAlignment(Qt.AlignCenter)
            self.cards_container.addWidget(lbl)
        else:
            for inc in queue:
                card = self._make_incident_card(inc)
                self.cards_container.addWidget(card)
