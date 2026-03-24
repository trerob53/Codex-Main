"""
Cerasus Hub -- Attendance Module: Officer Roster Page
Officer table with color-coded point badges, filters, search, and profile panel.
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QAbstractItemView, QGroupBox, QScrollArea,
    QDialog, QFormLayout, QDialogButtonBox, QTextEdit,
    QFileDialog, QDateEdit, QMessageBox,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, tc, _is_dark, btn_style, build_dialog_stylesheet, REPORTS_DIR, ensure_directories
from src.shared_widgets import confirm_action, export_table_to_csv
from src.modules.attendance import data_manager
from src.modules.attendance.policy_engine import INFRACTION_TYPES, DISCIPLINE_LABELS, CLEAN_SLATE_DAYS
from src.modules.attendance.pages_infractions import DisciplineProgressBar
from src import audit


# ════════════════════════════════════════════════════════════════════════
# Edit Infraction Dialog
# ════════════════════════════════════════════════════════════════════════

class EditInfractionDialog(QDialog):
    """Dialog for editing an existing infraction with audit justification."""

    def __init__(self, parent, infraction: dict):
        super().__init__(parent)
        self.infraction = infraction
        self.setWindowTitle("Edit Infraction")
        self.setMinimumWidth(520)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Original values (read-only)
        orig_grp = QGroupBox("Original Values")
        orig_grp.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 13px; color: {tc('text_light')};
                border: 1px solid {tc('border')}; border-radius: 6px;
                margin-top: 8px; padding-top: 18px; background: {tc('card')};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
        """)
        orig_lay = QFormLayout(orig_grp)
        itype = self.infraction.get("infraction_type", "")
        type_info = INFRACTION_TYPES.get(itype, {})
        orig_lay.addRow("Date:", QLabel(self.infraction.get("infraction_date", "")))
        orig_lay.addRow("Type:", QLabel(type_info.get("label", itype)))
        orig_lay.addRow("Points:", QLabel(str(self.infraction.get("points_assigned", 0))))
        orig_lay.addRow("Site:", QLabel(self.infraction.get("site", "")))
        orig_lay.addRow("Notes:", QLabel(self.infraction.get("description", "")))
        layout.addWidget(orig_grp)

        # Editable fields
        edit_grp = QGroupBox("New Values")
        edit_grp.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 13px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 6px;
                margin-top: 8px; padding-top: 18px; background: {tc('card')};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
        """)
        form = QFormLayout(edit_grp)
        form.setSpacing(8)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        orig_date = self.infraction.get("infraction_date", "")
        if orig_date:
            qd = QDate.fromString(orig_date, "yyyy-MM-dd")
            if qd.isValid():
                self.date_edit.setDate(qd)
            else:
                self.date_edit.setDate(QDate.currentDate())
        else:
            self.date_edit.setDate(QDate.currentDate())
        form.addRow("Infraction Date:", self.date_edit)

        self.type_combo = QComboBox()
        type_keys = list(INFRACTION_TYPES.keys())
        for key in type_keys:
            self.type_combo.addItem(INFRACTION_TYPES[key].get("label", key), key)
        # Select current type
        current_idx = type_keys.index(itype) if itype in type_keys else 0
        self.type_combo.setCurrentIndex(current_idx)
        form.addRow("Infraction Type:", self.type_combo)

        self.site_combo = QComboBox()
        sites = data_manager.get_site_names()
        for s in sites:
            self.site_combo.addItem(s.get("name", ""))
        current_site = self.infraction.get("site", "")
        idx = self.site_combo.findText(current_site)
        if idx >= 0:
            self.site_combo.setCurrentIndex(idx)
        form.addRow("Site:", self.site_combo)

        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        self.notes_edit.setPlainText(self.infraction.get("description", ""))
        form.addRow("Description / Notes:", self.notes_edit)

        self.points_edit = QLineEdit()
        self.points_edit.setPlaceholderText("Leave blank to use type default")
        pts = self.infraction.get("points_assigned")
        if pts is not None:
            self.points_edit.setText(str(pts))
        form.addRow("Points Override:", self.points_edit)

        layout.addWidget(edit_grp)

        # Justification (required)
        just_lbl = QLabel("Edit Justification (required for audit trail):")
        just_lbl.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 13px;")
        layout.addWidget(just_lbl)

        self.justification_edit = QTextEdit()
        self.justification_edit.setMaximumHeight(80)
        self.justification_edit.setPlaceholderText("Minimum 10 characters required...")
        layout.addWidget(self.justification_edit)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _validate_and_accept(self):
        justification = self.justification_edit.toPlainText().strip()
        if len(justification) < 10:
            QMessageBox.warning(
                self, "Justification Required",
                "Please provide a justification of at least 10 characters for the audit trail."
            )
            return
        pts_text = self.points_edit.text().strip()
        if pts_text:
            try:
                float(pts_text)
            except ValueError:
                QMessageBox.warning(self, "Validation", "Points override must be a number.")
                return
        self.accept()

    def get_fields(self) -> dict:
        """Return dict of edited fields."""
        fields = {
            "infraction_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "infraction_type": self.type_combo.currentData(),
            "site": self.site_combo.currentText(),
            "description": self.notes_edit.toPlainText().strip(),
        }
        pts_text = self.points_edit.text().strip()
        if pts_text:
            fields["points_assigned"] = float(pts_text)
        return fields

    def get_justification(self) -> str:
        return self.justification_edit.toPlainText().strip()


# ════════════════════════════════════════════════════════════════════════
# Officer Profile Dialog
# ════════════════════════════════════════════════════════════════════════

class OfficerProfileDialog(QDialog):
    """Detail view for an officer showing infraction history."""

    def __init__(self, parent, officer, app_state):
        super().__init__(parent)
        self.officer = officer
        self.app_state = app_state
        self.setWindowTitle(f"Officer Profile - {officer.get('name', '')}")
        self.setMinimumSize(700, 500)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        off = self.officer

        # Header info
        name_lbl = QLabel(off.get("name", ""))
        name_lbl.setFont(QFont("Segoe UI", 18, QFont.Bold))
        name_lbl.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(name_lbl)

        info_row = QHBoxLayout()
        for label, key in [("Employee ID", "employee_id"), ("Site", "site"),
                           ("Status", "status"), ("Hire Date", "hire_date")]:
            lbl = QLabel(f"{label}: {off.get(key, 'N/A')}")
            lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
            info_row.addWidget(lbl)
        info_row.addStretch()

        btn_360 = QPushButton("Full Profile (All Modules)")
        btn_360.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS.get('accent_hover', COLORS['accent'])))
        btn_360.clicked.connect(self._open_360)
        info_row.addWidget(btn_360)

        layout.addLayout(info_row)

        # Points summary
        pts = float(off.get("active_points", 0))
        pts_color = self._pts_color(pts)
        pts_row = QHBoxLayout()
        pts_lbl = QLabel(f"Active Points: {pts}")
        pts_lbl.setFont(QFont("Segoe UI", 16, QFont.Bold))
        pts_lbl.setStyleSheet(f"color: {pts_color};")
        pts_row.addWidget(pts_lbl)

        level_lbl = QLabel(f"Discipline Level: {off.get('discipline_level', 'None')}")
        level_lbl.setFont(QFont("Segoe UI", 14))
        level_lbl.setStyleSheet(f"color: {tc('text_light')};")
        pts_row.addWidget(level_lbl)
        pts_row.addStretch()
        layout.addLayout(pts_row)

        # Discipline progression bar
        progress_bar = DisciplineProgressBar(pts)
        layout.addWidget(progress_bar)

        # Infraction history
        grp = QGroupBox("Infraction History")
        grp.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 14px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 20px; background: {tc('card')};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 6px; }}
        """)
        grp_lay = QVBoxLayout(grp)

        self.inf_table = QTableWidget(0, 5)
        self.inf_table.setHorizontalHeaderLabels(["Date", "Type", "Points", "Discipline", "Notes"])
        hdr = self.inf_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 13px; padding: 6px; border: none;
            }}
        """)
        self.inf_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.inf_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.inf_table.verticalHeader().setVisible(False)
        self.inf_table.setAlternatingRowColors(True)
        grp_lay.addWidget(self.inf_table)

        # Action row for infractions
        inf_btn_row = QHBoxLayout()
        inf_btn_row.addStretch()

        btn_edit_inf = QPushButton("Edit Infraction")
        btn_edit_inf.setStyleSheet(btn_style(COLORS['info']))
        btn_edit_inf.clicked.connect(self._edit_infraction)
        inf_btn_row.addWidget(btn_edit_inf)

        btn_delete_inf = QPushButton("Delete Infraction")
        btn_delete_inf.setStyleSheet(btn_style(COLORS['danger']))
        btn_delete_inf.clicked.connect(self._delete_infraction)
        inf_btn_row.addWidget(btn_delete_inf)

        grp_lay.addLayout(inf_btn_row)
        layout.addWidget(grp)

        # Load infraction data
        self._infractions = []
        self._refresh_infractions()

        # Close button
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _open_360(self):
        officer_id = self.officer.get("officer_id", "")
        if officer_id:
            try:
                from src.officer_360 import show_officer_profile
                show_officer_profile(self, officer_id, self.app_state)
            except Exception:
                pass

    def _pts_color(self, pts):
        if pts >= 10:
            return "#9333EA"
        elif pts >= 8:
            return COLORS["danger"]
        elif pts >= 6:
            return COLORS["warning"]
        elif pts >= 1.5:
            return COLORS["warning"]
        else:
            return COLORS["success"]

    # ── Infraction table helpers ──────────────────────────────────────

    def _refresh_infractions(self):
        """Reload infraction data into the table."""
        oid = self.officer.get("officer_id", "")
        self._infractions = data_manager.get_infractions_for_employee(oid)
        self.inf_table.setRowCount(len(self._infractions))
        for i, inf in enumerate(self._infractions):
            itype = inf.get("infraction_type", "")
            type_info = INFRACTION_TYPES.get(itype, {})
            self.inf_table.setItem(i, 0, QTableWidgetItem(inf.get("infraction_date", "")))
            self.inf_table.setItem(i, 1, QTableWidgetItem(type_info.get("label", itype)))
            pts_item = QTableWidgetItem(str(inf.get("points_assigned", 0)))
            pts_item.setTextAlignment(Qt.AlignCenter)
            self.inf_table.setItem(i, 2, pts_item)
            disc = inf.get("discipline_triggered", "")
            self.inf_table.setItem(i, 3, QTableWidgetItem(DISCIPLINE_LABELS.get(disc, disc)))
            self.inf_table.setItem(i, 4, QTableWidgetItem(inf.get("description", "")))

    def _get_selected_infraction(self):
        """Return the selected infraction dict or None."""
        rows = self.inf_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "No Selection", "Please select an infraction row first.")
            return None
        row_idx = rows[0].row()
        if 0 <= row_idx < len(self._infractions):
            return self._infractions[row_idx]
        return None

    def _edit_infraction(self):
        """Open the edit dialog for the selected infraction."""
        inf = self._get_selected_infraction()
        if inf is None:
            return

        dlg = EditInfractionDialog(self, inf)
        if dlg.exec() != QDialog.Accepted:
            return

        fields = dlg.get_fields()
        justification = dlg.get_justification()
        inf_id = inf.get("id")
        username = self.app_state.get("username", "system")
        employee_id = inf.get("employee_id", "")

        # Build before/after for audit
        before_parts = []
        after_parts = []
        field_labels = {
            "infraction_date": "Date",
            "infraction_type": "Type",
            "site": "Site",
            "description": "Notes",
            "points_assigned": "Points",
        }
        for key, label in field_labels.items():
            old_val = str(inf.get(key, ""))
            new_val = str(fields.get(key, old_val))
            if old_val != new_val:
                before_parts.append(f"{label}: {old_val}")
                after_parts.append(f"{label}: {new_val}")

        data_manager.update_infraction(inf_id, fields)

        audit.log_event(
            module_name="attendance",
            event_type="infraction_edited",
            username=username,
            details=f"Edited infraction #{inf_id}",
            table_name="ats_infractions",
            record_id=str(inf_id),
            action="update",
            before_value="; ".join(before_parts) if before_parts else "",
            after_value="; ".join(after_parts) if after_parts else "",
            justification=justification,
            employee_id=employee_id,
        )

        self._refresh_infractions()

    def _delete_infraction(self):
        """Delete the selected infraction after requiring justification."""
        inf = self._get_selected_infraction()
        if inf is None:
            return

        inf_id = inf.get("id")
        itype = inf.get("infraction_type", "")
        type_info = INFRACTION_TYPES.get(itype, {})
        type_label = type_info.get("label", itype)

        # Custom confirmation dialog requiring justification
        dlg = QDialog(self)
        dlg.setWindowTitle("Confirm Deletion")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        warn_lbl = QLabel(
            f"Delete infraction #{inf_id}?\n"
            f"Type: {type_label}\n"
            f"Date: {inf.get('infraction_date', '')}\n"
            f"Points: {inf.get('points_assigned', 0)}"
        )
        warn_lbl.setStyleSheet(f"color: {COLORS['danger']}; font-size: 13px;")
        lay.addWidget(warn_lbl)

        just_lbl = QLabel("Deletion Justification (required for audit trail):")
        just_lbl.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 13px;")
        lay.addWidget(just_lbl)

        just_edit = QTextEdit()
        just_edit.setMaximumHeight(80)
        just_edit.setPlaceholderText("Minimum 10 characters required...")
        lay.addWidget(just_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(btn_box)

        def validate_and_accept():
            if len(just_edit.toPlainText().strip()) < 10:
                QMessageBox.warning(
                    dlg, "Justification Required",
                    "Please provide a justification of at least 10 characters."
                )
                return
            dlg.accept()

        btn_box.accepted.connect(validate_and_accept)
        btn_box.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.Accepted:
            return

        justification = just_edit.toPlainText().strip()
        username = self.app_state.get("username", "system")
        employee_id = inf.get("employee_id", "")

        # Build before value for audit
        before_value = (
            f"Date: {inf.get('infraction_date', '')}; "
            f"Type: {type_label}; "
            f"Points: {inf.get('points_assigned', 0)}; "
            f"Notes: {inf.get('description', '')}"
        )

        data_manager.delete_infraction(inf_id)

        audit.log_event(
            module_name="attendance",
            event_type="infraction_deleted",
            username=username,
            details=f"Deleted infraction #{inf_id}",
            table_name="ats_infractions",
            record_id=str(inf_id),
            action="delete",
            before_value=before_value,
            after_value="",
            justification=justification,
            employee_id=employee_id,
        )

        self._refresh_infractions()


# ════════════════════════════════════════════════════════════════════════
# Add Officer Dialog
# ════════════════════════════════════════════════════════════════════════

class AddOfficerDialog(QDialog):
    """Form dialog for adding a new officer to the roster."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Officer")
        self.setMinimumWidth(450)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.first_name = QLineEdit()
        self.first_name.setPlaceholderText("Required")
        form.addRow("First Name:", self.first_name)

        self.last_name = QLineEdit()
        self.last_name.setPlaceholderText("Required")
        form.addRow("Last Name:", self.last_name)

        self.employee_id = QLineEdit()
        self.employee_id.setPlaceholderText("Required")
        form.addRow("Employee ID:", self.employee_id)

        self.job_title = QComboBox()
        self.job_title.addItems([
            "Security Officer", "Lead Officer",
            "Field Supervisor", "Security Director",
        ])
        form.addRow("Job Title:", self.job_title)

        self.site = QComboBox()
        sites = data_manager.get_site_names()
        for s in sites:
            self.site.addItem(s.get("name", ""))
        form.addRow("Site:", self.site)

        self.hire_date = QDateEdit()
        self.hire_date.setCalendarPopup(True)
        self.hire_date.setDate(QDate.currentDate())
        form.addRow("Hire Date:", self.hire_date)

        self.email = QLineEdit()
        form.addRow("Email:", self.email)

        self.phone = QLineEdit()
        form.addRow("Phone:", self.phone)

        self.notes = QTextEdit()
        self.notes.setMaximumHeight(80)
        form.addRow("Notes:", self.notes)

        layout.addLayout(form)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _validate_and_accept(self):
        if not self.first_name.text().strip():
            QMessageBox.warning(self, "Validation", "First name is required.")
            return
        if not self.last_name.text().strip():
            QMessageBox.warning(self, "Validation", "Last name is required.")
            return
        if not self.employee_id.text().strip():
            QMessageBox.warning(self, "Validation", "Employee ID is required.")
            return
        self.accept()

    def get_fields(self):
        return {
            "first_name": self.first_name.text().strip(),
            "last_name": self.last_name.text().strip(),
            "employee_id": self.employee_id.text().strip(),
            "job_title": self.job_title.currentText(),
            "site": self.site.currentText(),
            "hire_date": self.hire_date.date().toString("yyyy-MM-dd"),
            "email": self.email.text().strip(),
            "phone": self.phone.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Roster Page
# ════════════════════════════════════════════════════════════════════════

class RosterPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(12)

        # Header row
        hdr_row = QHBoxLayout()
        title = QLabel("Officer Roster")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or ID...")
        self.search_input.setFixedWidth(250)
        self.search_input.textChanged.connect(self._on_filter_changed)
        hdr_row.addWidget(self.search_input)

        btn_add = QPushButton("+ Add Officer")
        btn_add.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        btn_add.clicked.connect(self._add_officer)
        hdr_row.addWidget(btn_add)

        layout.addLayout(hdr_row)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Site:"))
        self.site_filter = QComboBox()
        self.site_filter.setFixedWidth(200)
        self.site_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.site_filter)

        filter_row.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Active", "Inactive", "Terminated"])
        self.status_filter.setFixedWidth(150)
        self.status_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.status_filter)

        filter_row.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(btn_style(tc('info')))
        btn_refresh.clicked.connect(self.refresh)
        filter_row.addWidget(btn_refresh)

        layout.addLayout(filter_row)

        # Officer table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Name", "Employee ID", "Site", "Active Points",
            "Discipline Level", "Status", "Last Infraction", "Clean Slate"
        ])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 8):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 14px; padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._on_row_double_click)
        layout.addWidget(self.table)

        # Import / Export button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_import = QPushButton("Import CSV")
        btn_import.setStyleSheet(btn_style(COLORS['info']))
        btn_import.clicked.connect(self._import_csv)
        btn_row.addWidget(btn_import)

        btn_export = QPushButton("Export CSV")
        btn_export.setStyleSheet(btn_style(tc('text_light')))
        btn_export.clicked.connect(self._export_csv)
        btn_row.addWidget(btn_export)

        btn_export_table = QPushButton("Export Table CSV")
        btn_export_table.setStyleSheet(btn_style(COLORS['info']))
        btn_export_table.clicked.connect(self._export_table_csv)
        btn_row.addWidget(btn_export_table)
        layout.addLayout(btn_row)

        # Store officers for click lookup
        self._officers = []

    def refresh(self):
        from src.shared_data import filter_by_user_sites, get_sites_for_user

        # Populate site filter (filtered by user's assigned sites)
        current_site = self.site_filter.currentText()
        self.site_filter.blockSignals(True)
        self.site_filter.clear()
        self.site_filter.addItem("All Sites")
        sites = get_sites_for_user(self.app_state)
        for s in sites:
            self.site_filter.addItem(s.get("name", ""))
        if current_site:
            idx = self.site_filter.findText(current_site)
            if idx >= 0:
                self.site_filter.setCurrentIndex(idx)
        self.site_filter.blockSignals(False)

        self._load_officers()

    def _on_filter_changed(self):
        self._load_officers()

    def _load_officers(self):
        from src.shared_data import filter_by_user_sites

        search = self.search_input.text().strip().lower()
        site_filter = self.site_filter.currentText()
        status_filter = self.status_filter.currentText()

        if search:
            officers = data_manager.search_officers(search)
        else:
            officers = data_manager.get_all_officers()

        # Apply site-based access control
        officers = filter_by_user_sites(self.app_state, officers)

        # Apply UI filters
        if site_filter and site_filter != "All Sites":
            officers = [o for o in officers if o.get("site", "") == site_filter]
        if status_filter and status_filter != "All":
            officers = [o for o in officers if o.get("status", "") == status_filter]

        self._officers = officers
        self.table.setRowCount(len(officers))

        for i, off in enumerate(officers):
            # Name
            name_item = QTableWidgetItem(off.get("name", ""))
            name_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(i, 0, name_item)

            # Employee ID
            self.table.setItem(i, 1, QTableWidgetItem(off.get("employee_id", "")))

            # Site
            self.table.setItem(i, 2, QTableWidgetItem(off.get("site", "")))

            # Active Points (color-coded badge)
            pts = float(off.get("active_points", 0))
            pts_item = QTableWidgetItem(f"{pts:.1f}")
            pts_item.setTextAlignment(Qt.AlignCenter)
            pts_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            color, fg = self._pts_badge_colors(pts)
            pts_item.setBackground(QColor(color))
            pts_item.setForeground(QColor(fg))
            self.table.setItem(i, 3, pts_item)

            # Discipline Level
            level = off.get("discipline_level", "None")
            level_item = QTableWidgetItem(level)
            level_item.setTextAlignment(Qt.AlignCenter)
            if level in ("Termination Eligible", "termination_eligible"):
                level_item.setForeground(QColor(COLORS["danger"]))
                level_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            elif level in ("Employment Review", "employment_review"):
                level_item.setForeground(QColor("#9333EA"))
            elif level in ("Written Warning", "written_warning"):
                level_item.setForeground(QColor(COLORS["warning"]))
            self.table.setItem(i, 4, level_item)

            # Status
            status = off.get("status", "Active")
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "Terminated":
                status_item.setForeground(QColor(COLORS["danger"]))
            elif status == "Inactive":
                status_item.setForeground(QColor(tc("text_light")))
            else:
                status_item.setForeground(QColor(COLORS["success"]))
            self.table.setItem(i, 5, status_item)

            # Last Infraction
            self.table.setItem(i, 6, QTableWidgetItem(off.get("last_infraction_date", "")))

            # Clean Slate badge (90+ days without infraction)
            last_inf_date = off.get("last_infraction_date", "")
            is_clean = False
            if not last_inf_date:
                is_clean = True
            else:
                try:
                    from datetime import date as _date, datetime as _datetime
                    d = _datetime.fromisoformat(last_inf_date).date() if "T" in last_inf_date else _date.fromisoformat(last_inf_date)
                    is_clean = (_date.today() - d).days >= CLEAN_SLATE_DAYS
                except (ValueError, TypeError):
                    is_clean = False

            if is_clean:
                cs_item = QTableWidgetItem("CLEAN SLATE")
                cs_item.setTextAlignment(Qt.AlignCenter)
                cs_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                cs_item.setBackground(QColor(COLORS["success_light"]))
                cs_item.setForeground(QColor(COLORS["success"]))
            else:
                cs_item = QTableWidgetItem("")
                cs_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 7, cs_item)

            self.table.setRowHeight(i, 44)

    def _pts_badge_colors(self, pts):
        """Return (background, foreground) for point badge."""
        if pts >= 10:
            return "#9333EA", "white"  # purple
        elif pts >= 8:
            return COLORS["danger"], "white"
        elif pts >= 6:
            return COLORS["warning"], "white"
        elif pts >= 1.5:
            return "#FEF3C7", COLORS["warning"]  # yellow bg
        else:
            return COLORS["success_light"], COLORS["success"]  # green

    def _on_row_double_click(self, index):
        row = index.row()
        if 0 <= row < len(self._officers):
            officer = self._officers[row]
            dlg = OfficerProfileDialog(self, officer, self.app_state)
            dlg.exec()

    # ── Add Officer ──────────────────────────────────────────────────

    def _add_officer(self):
        dlg = AddOfficerDialog(self)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            username = self.app_state.get("username", "system")
            data_manager.create_officer(fields, created_by=username)
            audit.log_event(
                "attendance", "officer_added", username,
                details=f"Added officer {fields['first_name']} {fields['last_name']} ({fields['employee_id']})",
            )
            self.refresh()

    # ── Import CSV ───────────────────────────────────────────────────

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                csv_text = fh.read()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not read file:\n{exc}")
            return

        username = self.app_state.get("username", "system")
        result = data_manager.import_employees_csv(csv_text, entered_by=username)
        imported = result.get("imported", 0)
        skipped = result.get("skipped", 0)
        errors = result.get("errors", [])
        msg = f"Imported: {imported}\nSkipped: {skipped}"
        if errors:
            msg += f"\n\nErrors:\n" + "\n".join(str(e) for e in errors[:20])
        QMessageBox.information(self, "Import Results", msg)
        self.refresh()

    # ── Export Table CSV ─────────────────────────────────────────────

    def _export_table_csv(self):
        """Export the current table view to CSV."""
        export_table_to_csv(self.table, parent=self, default_name="roster_table_export.csv")

    # ── Export CSV ───────────────────────────────────────────────────

    def _export_csv(self):
        csv_text = data_manager.export_discipline_csv()
        ensure_directories()
        default_path = os.path.join(REPORTS_DIR, "roster_export.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", default_path, "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(csv_text)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{exc}")
            return

        username = self.app_state.get("username", "system")
        audit.log_event(
            "attendance", "roster_exported", username,
            details=f"Exported roster CSV to {path}",
        )
