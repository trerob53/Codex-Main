"""
Cerasus Operations Manager — Operations Pages
Officers, Sites, and Assignments management pages.
"""

import csv
import os
from datetime import date, datetime, timezone, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QComboBox, QMessageBox, QFileDialog,
    QFormLayout, QGroupBox, QAbstractItemView, QDialog,
    QDialogButtonBox, QScrollArea, QDateEdit, QTimeEdit,
    QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, ROLE_ADMIN, REPORTS_DIR, build_dialog_stylesheet, tc, _is_dark, btn_style, ensure_directories
from src.modules.operations import data_manager
from src import audit


# ════════════════════════════════════════════════════════════════════════
# Officer Dialog
# ════════════════════════════════════════════════════════════════════════

class OfficerDialog(QDialog):
    def __init__(self, parent=None, officer=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Officer" if officer else "New Officer")
        self.setMinimumWidth(480)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.officer = officer
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        self.txt_emp_id = QLineEdit(self.officer.get("employee_id", "") if self.officer else "")
        self.txt_emp_id.setPlaceholderText("e.g. EMP-001, badge number, etc.")
        layout.addRow("Employee ID:", self.txt_emp_id)

        self.txt_name = QLineEdit(self.officer.get("name", "") if self.officer else "")
        self.txt_name.setPlaceholderText("Full name")
        layout.addRow("Name:", self.txt_name)

        self.cmb_role = QComboBox()
        self.cmb_role.addItems(["Flex Officer", "Field Service Supervisor"])
        if self.officer:
            idx = self.cmb_role.findText(self.officer.get("role", "Flex Officer"))
            if idx >= 0:
                self.cmb_role.setCurrentIndex(idx)
        layout.addRow("Role:", self.cmb_role)

        self.cmb_hours = QComboBox()
        self.cmb_hours.setEditable(True)
        self.cmb_hours.addItems(["8", "16", "20", "24", "32", "36", "40", "48"])
        self.cmb_hours.setCurrentText(self.officer.get("weekly_hours", "40") if self.officer else "40")
        layout.addRow("Weekly Hours:", self.cmb_hours)

        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["Active", "Inactive", "On Leave"])
        if self.officer:
            idx = self.cmb_status.findText(self.officer.get("status", "Active"))
            if idx >= 0:
                self.cmb_status.setCurrentIndex(idx)
        layout.addRow("Status:", self.cmb_status)

        self.list_trained = QListWidget()
        self.list_trained.setMaximumHeight(100)
        active_sites = data_manager.get_active_sites()
        site_names = [s.get("name", "") for s in active_sites if s.get("name")]
        existing = self.officer.get("trained_sites", []) if self.officer else []
        if site_names:
            for site in site_names:
                item = QListWidgetItem(site)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if site in existing else Qt.Unchecked)
                self.list_trained.addItem(item)
        else:
            item = QListWidgetItem("-- Add sites first under Sites tab --")
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(QColor(tc("text_light")))
            self.list_trained.addItem(item)
        layout.addRow("Trained Sites:", self.list_trained)

        self.txt_notes = QTextEdit(self.officer.get("notes", "") if self.officer else "")
        self.txt_notes.setMaximumHeight(80)
        layout.addRow("Notes:", self.txt_notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _validate_and_accept(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        hours = self.cmb_hours.currentText().strip()
        try:
            hours_val = float(hours)
            if hours_val < 0 or hours_val > 168:
                QMessageBox.warning(self, "Validation", "Weekly hours must be between 0 and 168.")
                return
        except ValueError:
            QMessageBox.warning(self, "Validation", "Weekly hours must be a number.")
            return
        self.accept()

    def get_data(self) -> dict:
        trained = []
        for i in range(self.list_trained.count()):
            item = self.list_trained.item(i)
            if item.checkState() == Qt.Checked:
                trained.append(item.text())
        return {
            "employee_id": self.txt_emp_id.text().strip(),
            "name": self.txt_name.text().strip(),
            "role": self.cmb_role.currentText(),
            "weekly_hours": self.cmb_hours.currentText().strip(),
            "status": self.cmb_status.currentText(),
            "trained_sites": trained,
            "notes": self.txt_notes.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Officers Page
# ════════════════════════════════════════════════════════════════════════

class OfficersPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)

        # Header
        header_row = QHBoxLayout()
        header = QLabel("Flex Team")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setStyleSheet(f"color: {tc('primary')};")
        header_row.addWidget(header)
        header_row.addStretch()

        btn_template = QPushButton("Download Template")
        btn_template.setStyleSheet(btn_style(tc("text_light"), "white"))
        btn_template.clicked.connect(self._download_template)
        header_row.addWidget(btn_template)

        self.btn_import = QPushButton("Import CSV")
        self.btn_import.setStyleSheet(btn_style(COLORS["primary_light"], "white"))
        self.btn_import.clicked.connect(self._import_csv)
        header_row.addWidget(self.btn_import)

        self.btn_add = QPushButton("+ Add Officer")
        self.btn_add.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        self.btn_add.clicked.connect(self._add_officer)
        header_row.addWidget(self.btn_add)
        layout.addLayout(header_row)

        # Search
        search_row = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search officers by name, role, site...")
        self.txt_search.textChanged.connect(self._do_search)
        search_row.addWidget(self.txt_search)

        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems(["Active", "All"])
        self.cmb_filter.currentTextChanged.connect(self._do_search)
        self.cmb_filter.setFixedWidth(120)
        search_row.addWidget(self.cmb_filter)
        layout.addLayout(search_row)

        # Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Employee ID", "Name", "Role", "Status", "Today", "Trained Sites"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._edit_selected)
        layout.addWidget(self.table)

        # Action buttons
        btn_row = QHBoxLayout()
        self.btn_edit = QPushButton("Edit Selected")
        self.btn_edit.setStyleSheet(btn_style(tc("primary"), "white", COLORS["primary_light"]))
        self.btn_edit.clicked.connect(self._edit_selected)
        btn_row.addWidget(self.btn_edit)

        self.btn_view = QPushButton("View Details")
        self.btn_view.setStyleSheet(btn_style(COLORS["primary_light"], "white"))
        self.btn_view.clicked.connect(self._view_selected)
        btn_row.addWidget(self.btn_view)

        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.setStyleSheet(btn_style(COLORS["danger"], "white"))
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()
        self.lbl_count = QLabel("0 officers")
        self.lbl_count.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px;")
        btn_row.addWidget(self.lbl_count)
        layout.addLayout(btn_row)

    def refresh(self):
        self._do_search()
        is_admin = self.app_state.get("user", {}).get("role") == ROLE_ADMIN
        self.btn_delete.setEnabled(is_admin)
        self.btn_delete.setVisible(is_admin)

    def _do_search(self):
        query = self.txt_search.text().strip()
        status_filter = self.cmb_filter.currentText()
        active_only = status_filter == "Active"
        if query:
            officers = data_manager.search_officers(query)
            # Filter search results to ops officers only
            officers = [o for o in officers if data_manager._is_ops_officer(o)]
            if active_only:
                officers = [o for o in officers if o.get("status") == "Active"]
        else:
            officers = data_manager.get_ops_officers(active_only=active_only)
        self._populate_table(officers)

    def _populate_table(self, officers):
        # Pre-fetch today's assignments and build a lookup by officer name
        today_str = date.today().strftime("%Y-%m-%d")
        all_assignments = data_manager.get_all_assignments()
        today_asn_map = {}  # officer_name -> site_name
        for a in all_assignments:
            if a.get("date") == today_str:
                name = a.get("officer_name", "")
                if name:
                    today_asn_map[name] = a.get("site_name", "Assigned")

        self.table.setRowCount(len(officers))
        for i, off in enumerate(officers):
            emp_id = off.get("employee_id", "") or off.get("officer_id", "")[:8]
            id_item = QTableWidgetItem(emp_id)
            id_item.setData(Qt.UserRole, off.get("officer_id", ""))
            self.table.setItem(i, 0, id_item)
            self.table.setItem(i, 1, QTableWidgetItem(off.get("name", "")))
            self.table.setItem(i, 2, QTableWidgetItem(off.get("role", "")))

            status_item = QTableWidgetItem(off.get("status", ""))
            status = off.get("status", "")
            if status == "Active":
                status_item.setForeground(QColor(COLORS["success"]))
            elif status == "Inactive":
                status_item.setForeground(QColor(COLORS["danger"]))
            else:
                status_item.setForeground(QColor(COLORS["warning"]))
            self.table.setItem(i, 3, status_item)

            # Today column — PTO, assigned site, or available
            name = off.get("name", "")
            today_pto = data_manager.get_officer_pto_for_date(name, today_str)
            if today_pto:
                today_item = QTableWidgetItem("\U0001f534 PTO")
                today_item.setForeground(QColor(COLORS["danger"]))
                today_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            elif name in today_asn_map:
                today_item = QTableWidgetItem(today_asn_map[name])
                today_item.setForeground(QColor(COLORS["info"]))
                today_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            else:
                today_item = QTableWidgetItem("\u2705 Available")
                today_item.setForeground(QColor(COLORS["success"]))
                today_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(i, 4, today_item)

            sites = off.get("trained_sites", [])
            self.table.setItem(i, 5, QTableWidgetItem(", ".join(sites) if sites else "\u2014"))
        self.lbl_count.setText(f"{len(officers)} officer(s)")

    def _get_selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        # Prefer the internal officer_id stored in UserRole
        oid = item.data(Qt.UserRole)
        return oid if oid else item.text()

    def _add_officer(self):
        dlg = OfficerDialog(self)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            if not d["name"]:
                QMessageBox.warning(self, "Validation", "Officer name is required.")
                return
            username = self.app_state["user"]["username"]
            off = data_manager.create_officer(d, username)
            audit.log_event("operations", "officer_create", username, f"Created officer: {d['name']}")
            self.refresh()

    def _edit_selected(self):
        oid = self._get_selected_id()
        if not oid:
            QMessageBox.information(self, "Select", "Please select an officer.")
            return
        off = data_manager.get_officer(oid)
        if not off:
            return
        dlg = OfficerDialog(self, officer=off)
        if dlg.exec() == QDialog.Accepted:
            username = self.app_state["user"]["username"]
            data_manager.update_officer(oid, dlg.get_data(), username)
            audit.log_event("operations", "officer_edit", username, f"Updated officer {oid}")
            self.refresh()

    def _view_selected(self):
        oid = self._get_selected_id()
        if not oid:
            return
        off = data_manager.get_officer(oid)
        if not off:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Officer: {off.get('name', '')}")
        dlg.setMinimumWidth(450)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 24, 24, 24)
        fields = [
            ("Employee ID", off.get("employee_id", "") or off.get("officer_id", "")[:8]),
            ("Name", off.get("name", "")),
            ("Role", off.get("role", "")),
            ("Weekly Hours", off.get("weekly_hours", "40")),
            ("Status", off.get("status", "")),
            ("Trained Sites", ", ".join(off.get("trained_sites", [])) or "\u2014"),
            ("Notes", off.get("notes", "")),
        ]
        for label, value in fields:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(120)
            lbl.setStyleSheet(f"font-weight: 600; color: {tc('text_light')};")
            val = QLabel(str(value))
            val.setStyleSheet(f"color: {tc('text')};")
            val.setWordWrap(True)
            row.addWidget(lbl)
            row.addWidget(val, 1)
            lay.addLayout(row)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(btn_style(tc("primary"), "white"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def _delete_selected(self):
        oid = self._get_selected_id()
        if not oid:
            QMessageBox.information(self, "Select", "Please select an officer.")
            return
        off = data_manager.get_officer(oid)
        name = off.get("name", oid) if off else oid
        confirm = QMessageBox.question(
            self, "Confirm Delete", f"Delete officer '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            username = self.app_state["user"]["username"]
            data_manager.delete_officer(oid)
            audit.log_event("operations", "officer_delete", username, f"Deleted officer: {name}")
            self.refresh()

    def _download_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Officer Template", "officers_template.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "role", "weekly_hours", "status", "trained_sites"])
            writer.writerow(["John Doe", "Flex Officer", "40", "Active", "Site A; Site B"])
        QMessageBox.information(self, "Template Saved", f"Officer import template saved to:\n{path}")

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Officers CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        username = self.app_state["user"]["username"]
        result = data_manager.import_officers_csv(text, username)
        imported = result["imported"]
        errors = result["errors"]
        msg = f"Imported {imported} officer(s)."
        if errors:
            msg += f"\n\nErrors ({len(errors)}):\n" + "\n".join(errors[:10])
        audit.log_event("operations", "officer_import", username, f"Imported {imported} officers from CSV")
        QMessageBox.information(self, "Import Complete", msg)
        self.refresh()


# ════════════════════════════════════════════════════════════════════════
# Site Dialog
# ════════════════════════════════════════════════════════════════════════

class SiteDialog(QDialog):
    def __init__(self, parent=None, site=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Site" if site else "New Site")
        self.setMinimumWidth(480)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.site = site
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        self.txt_name = QLineEdit(self.site.get("name", "") if self.site else "")
        self.txt_name.setPlaceholderText("Site name")
        layout.addRow("Site Name:", self.txt_name)

        self.txt_code = QLineEdit(self.site.get("billing_code", "") if self.site else "")
        self.txt_code.setPlaceholderText("Job/Billing code")
        layout.addRow("Billing Code:", self.txt_code)

        self.cmb_market = QComboBox()
        self.cmb_market.setEditable(True)
        self.cmb_market.setPlaceholderText("Select or type a market...")
        # Populate with unique markets from existing sites
        existing_markets = sorted(set(
            s.get("market", "") for s in data_manager.get_all_sites() if s.get("market")
        ))
        if existing_markets:
            self.cmb_market.addItems(existing_markets)
        if self.site and self.site.get("market"):
            self.cmb_market.setCurrentText(self.site["market"])
        layout.addRow("Market:", self.cmb_market)

        self.txt_address = QLineEdit(self.site.get("address", "") if self.site else "")
        self.txt_address.setPlaceholderText("Full address")
        layout.addRow("Address:", self.txt_address)

        self.cmb_ot = QComboBox()
        self.cmb_ot.addItems(["Normal", "Low", "High", "None"])
        if self.site:
            idx = self.cmb_ot.findText(self.site.get("overtime_sensitivity", "Normal"))
            if idx >= 0:
                self.cmb_ot.setCurrentIndex(idx)
        layout.addRow("OT Sensitivity:", self.cmb_ot)

        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["Active", "Inactive", "Pending"])
        if self.site:
            idx = self.cmb_status.findText(self.site.get("status", "Active"))
            if idx >= 0:
                self.cmb_status.setCurrentIndex(idx)
        layout.addRow("Status:", self.cmb_status)

        self.txt_notes = QTextEdit(self.site.get("notes", "") if self.site else "")
        self.txt_notes.setMaximumHeight(80)
        layout.addRow("Notes:", self.txt_notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self) -> dict:
        return {
            "name": self.txt_name.text().strip(),
            "billing_code": self.txt_code.text().strip(),
            "market": self.cmb_market.currentText().strip(),
            "address": self.txt_address.text().strip(),
            "overtime_sensitivity": self.cmb_ot.currentText(),
            "status": self.cmb_status.currentText(),
            "notes": self.txt_notes.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Sites Page
# ════════════════════════════════════════════════════════════════════════

class SitesPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        header = QLabel("Sites Management")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setStyleSheet(f"color: {tc('primary')};")
        header_row.addWidget(header)
        header_row.addStretch()

        btn_template = QPushButton("Download Template")
        btn_template.setStyleSheet(btn_style(tc("text_light"), "white"))
        btn_template.clicked.connect(self._download_template)
        header_row.addWidget(btn_template)

        self.btn_import = QPushButton("Import CSV")
        self.btn_import.setStyleSheet(btn_style(COLORS["primary_light"], "white"))
        self.btn_import.clicked.connect(self._import_csv)
        header_row.addWidget(self.btn_import)

        self.btn_add = QPushButton("+ Add Site")
        self.btn_add.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        self.btn_add.clicked.connect(self._add_site)
        header_row.addWidget(self.btn_add)
        layout.addLayout(header_row)

        # Search
        search_row = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search sites by name, code, market...")
        self.txt_search.textChanged.connect(self._do_search)
        search_row.addWidget(self.txt_search)

        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems(["All Statuses", "Active", "Inactive", "Pending"])
        self.cmb_filter.currentTextChanged.connect(self._do_search)
        self.cmb_filter.setFixedWidth(150)
        search_row.addWidget(self.cmb_filter)
        layout.addLayout(search_row)

        # Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Site Name", "Billing Code", "Market", "OT Sensitivity", "Status"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._edit_selected)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_edit = QPushButton("Edit Selected")
        self.btn_edit.setStyleSheet(btn_style(tc("primary"), "white", COLORS["primary_light"]))
        self.btn_edit.clicked.connect(self._edit_selected)
        btn_row.addWidget(self.btn_edit)

        self.btn_view = QPushButton("View Details")
        self.btn_view.setStyleSheet(btn_style(COLORS["primary_light"], "white"))
        self.btn_view.clicked.connect(self._view_selected)
        btn_row.addWidget(self.btn_view)

        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.setStyleSheet(btn_style(COLORS["danger"], "white"))
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()
        self.lbl_count = QLabel("0 sites")
        self.lbl_count.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px;")
        btn_row.addWidget(self.lbl_count)
        layout.addLayout(btn_row)

    def refresh(self):
        self._do_search()
        is_admin = self.app_state.get("user", {}).get("role") == ROLE_ADMIN
        self.btn_delete.setEnabled(is_admin)
        self.btn_delete.setVisible(is_admin)

    def _do_search(self):
        query = self.txt_search.text().strip()
        sites = data_manager.search_sites(query)
        status_filter = self.cmb_filter.currentText()
        if status_filter != "All Statuses":
            sites = [s for s in sites if s.get("status") == status_filter]
        self._populate_table(sites)

    def _populate_table(self, sites):
        self.table.setRowCount(len(sites))
        for i, site in enumerate(sites):
            self.table.setItem(i, 0, QTableWidgetItem(site.get("site_id", "")))
            self.table.setItem(i, 1, QTableWidgetItem(site.get("name", "")))
            self.table.setItem(i, 2, QTableWidgetItem(site.get("billing_code", "")))
            self.table.setItem(i, 3, QTableWidgetItem(site.get("market", "")))
            self.table.setItem(i, 4, QTableWidgetItem(site.get("overtime_sensitivity", "")))

            status_item = QTableWidgetItem(site.get("status", ""))
            status = site.get("status", "")
            if status == "Active":
                status_item.setForeground(QColor(COLORS["success"]))
            elif status == "Inactive":
                status_item.setForeground(QColor(COLORS["danger"]))
            else:
                status_item.setForeground(QColor(COLORS["warning"]))
            self.table.setItem(i, 5, status_item)
        self.lbl_count.setText(f"{len(sites)} site(s)")

    def _get_selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _add_site(self):
        dlg = SiteDialog(self)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            if not d["name"]:
                QMessageBox.warning(self, "Validation", "Site name is required.")
                return
            username = self.app_state["user"]["username"]
            data_manager.create_site(d, username)
            audit.log_event("operations", "site_create", username, f"Created site: {d['name']}")
            self.refresh()

    def _edit_selected(self):
        sid = self._get_selected_id()
        if not sid:
            QMessageBox.information(self, "Select", "Please select a site.")
            return
        site = data_manager.get_site(sid)
        if not site:
            return
        dlg = SiteDialog(self, site=site)
        if dlg.exec() == QDialog.Accepted:
            username = self.app_state["user"]["username"]
            data_manager.update_site(sid, dlg.get_data(), username)
            audit.log_event("operations", "site_edit", username, f"Updated site {sid}")
            self.refresh()

    def _view_selected(self):
        sid = self._get_selected_id()
        if not sid:
            return
        site = data_manager.get_site(sid)
        if not site:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Site: {site.get('name', '')}")
        dlg.setMinimumWidth(450)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 24, 24, 24)
        fields = [
            ("ID", site.get("site_id", "")),
            ("Name", site.get("name", "")),
            ("Billing Code", site.get("billing_code", "")),
            ("Market", site.get("market", "")),
            ("Address", site.get("address", "")),
            ("OT Sensitivity", site.get("overtime_sensitivity", "")),
            ("Status", site.get("status", "")),
            ("Notes", site.get("notes", "")),
        ]
        for label, value in fields:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(120)
            lbl.setStyleSheet(f"font-weight: 600; color: {tc('text_light')};")
            val = QLabel(str(value))
            val.setStyleSheet(f"color: {tc('text')};")
            val.setWordWrap(True)
            row.addWidget(lbl)
            row.addWidget(val, 1)
            lay.addLayout(row)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(btn_style(tc("primary"), "white"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def _delete_selected(self):
        sid = self._get_selected_id()
        if not sid:
            QMessageBox.information(self, "Select", "Please select a site.")
            return
        site = data_manager.get_site(sid)
        name = site.get("name", sid) if site else sid
        confirm = QMessageBox.question(
            self, "Confirm Delete", f"Delete site '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            username = self.app_state["user"]["username"]
            data_manager.delete_site(sid)
            audit.log_event("operations", "site_delete", username, f"Deleted site: {name}")
            self.refresh()

    def _download_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Site Template", "sites_template.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["site_name", "address", "billing_code", "market", "status", "notes"])
            writer.writerow(["Main Office", "123 Main St, City, ST 12345", "BIL-001", "Indianapolis", "Active", ""])
        QMessageBox.information(self, "Template Saved", f"Site import template saved to:\n{path}")

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Sites CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        username = self.app_state["user"]["username"]
        result = data_manager.import_sites_csv(text, username)
        imported = result["imported"]
        errors = result["errors"]
        msg = f"Imported {imported} site(s)."
        if errors:
            msg += f"\n\nErrors ({len(errors)}):\n" + "\n".join(errors[:10])
        audit.log_event("operations", "site_import", username, f"Imported {imported} sites from CSV")
        QMessageBox.information(self, "Import Complete", msg)
        self.refresh()


# ════════════════════════════════════════════════════════════════════════
# Assignment Dialog
# ════════════════════════════════════════════════════════════════════════

class AssignmentDialog(QDialog):
    def __init__(self, parent=None, assignment=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Assignment" if assignment else "New Assignment")
        self.setMinimumWidth(480)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.assignment = assignment
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Officer dropdown (ops officers only)
        self.cmb_officer = QComboBox()
        self.cmb_officer.setEditable(False)
        officer_names = data_manager.get_ops_officer_names()
        if officer_names:
            self.cmb_officer.addItems(officer_names)
        else:
            self.cmb_officer.addItem("-- Add officers first --")
        if self.assignment:
            idx = self.cmb_officer.findText(self.assignment.get("officer_name", ""))
            if idx >= 0:
                self.cmb_officer.setCurrentIndex(idx)
        layout.addRow("Officer:", self.cmb_officer)

        # Site dropdown
        self.cmb_site = QComboBox()
        self.cmb_site.setEditable(False)
        active_sites = data_manager.get_active_sites()
        site_names = [s.get("name", "") for s in active_sites if s.get("name")]
        if site_names:
            self.cmb_site.addItems(site_names)
        else:
            self.cmb_site.addItem("-- Add sites first --")
        if self.assignment:
            idx = self.cmb_site.findText(self.assignment.get("site_name", ""))
            if idx >= 0:
                self.cmb_site.setCurrentIndex(idx)
        layout.addRow("Site:", self.cmb_site)

        # Date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        if self.assignment and self.assignment.get("date"):
            d = QDate.fromString(self.assignment["date"], "yyyy-MM-dd")
            if d.isValid():
                self.date_edit.setDate(d)
            else:
                self.date_edit.setDate(QDate.currentDate())
        else:
            self.date_edit.setDate(QDate.currentDate())
        layout.addRow("Date:", self.date_edit)

        # Start time
        self.time_start = QTimeEdit()
        self.time_start.setDisplayFormat("HH:mm")
        if self.assignment and self.assignment.get("start_time"):
            t = QTime.fromString(self.assignment["start_time"], "HH:mm")
            if t.isValid():
                self.time_start.setTime(t)
            else:
                self.time_start.setTime(QTime(8, 0))
        else:
            self.time_start.setTime(QTime(8, 0))
        layout.addRow("Start Time:", self.time_start)

        # End time
        self.time_end = QTimeEdit()
        self.time_end.setDisplayFormat("HH:mm")
        if self.assignment and self.assignment.get("end_time"):
            t = QTime.fromString(self.assignment["end_time"], "HH:mm")
            if t.isValid():
                self.time_end.setTime(t)
            else:
                self.time_end.setTime(QTime(16, 0))
        else:
            self.time_end.setTime(QTime(16, 0))
        layout.addRow("End Time:", self.time_end)

        # Assignment type
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["Billable", "Anchor/Shadow", "Training", "PTO Coverage"])
        if self.assignment:
            idx = self.cmb_type.findText(self.assignment.get("assignment_type", "Billable"))
            if idx >= 0:
                self.cmb_type.setCurrentIndex(idx)
        layout.addRow("Type:", self.cmb_type)

        # Status
        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["Scheduled", "Completed", "Cancelled", "No Show"])
        if self.assignment:
            idx = self.cmb_status.findText(self.assignment.get("status", "Scheduled"))
            if idx >= 0:
                self.cmb_status.setCurrentIndex(idx)
        layout.addRow("Status:", self.cmb_status)

        # Notes
        self.txt_notes = QTextEdit(self.assignment.get("notes", "") if self.assignment else "")
        self.txt_notes.setMaximumHeight(80)
        layout.addRow("Notes:", self.txt_notes)

        # Hours preview
        self.lbl_hours = QLabel("8.0 hours")
        self.lbl_hours.setStyleSheet(f"font-weight: 600; color: {tc('primary')};")
        layout.addRow("Calculated Hours:", self.lbl_hours)

        # Officer availability
        self.lbl_avail = QLabel("")
        self.lbl_avail.setWordWrap(True)
        self.lbl_avail.setStyleSheet(f"font-size: 14px; color: {tc('text_light')};")
        layout.addRow("Availability:", self.lbl_avail)

        self.time_start.timeChanged.connect(self._update_hours)
        self.time_end.timeChanged.connect(self._update_hours)
        self.cmb_officer.currentTextChanged.connect(self._update_availability)
        self.date_edit.dateChanged.connect(self._update_availability)
        self._update_hours()
        self._update_availability()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _update_hours(self):
        start = self.time_start.time().toString("HH:mm")
        end = self.time_end.time().toString("HH:mm")
        hours = data_manager.calculate_shift_hours(start, end)
        self.lbl_hours.setText(f"{hours} hours")

    def _update_availability(self):
        officer = self.cmb_officer.currentText().strip()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        if not officer or officer.startswith("--"):
            self.lbl_avail.setText("")
            return
        existing = data_manager.detect_conflicts(officer, date, "00:00", "23:59")
        if existing:
            lines = []
            for c in existing:
                # Skip self when editing
                if self.assignment and c.get("assignment_id") == self.assignment.get("assignment_id"):
                    continue
                lines.append(f"  {c['site_name']}  {c['start_time']}-{c['end_time']}")
            if lines:
                self.lbl_avail.setText(f"Already scheduled:\n" + "\n".join(lines))
                self.lbl_avail.setStyleSheet(f"font-size: 14px; color: {COLORS['warning']}; font-weight: 600;")
            else:
                self.lbl_avail.setText("Available all day")
                self.lbl_avail.setStyleSheet(f"font-size: 14px; color: {COLORS['success']}; font-weight: 600;")
        else:
            self.lbl_avail.setText("Available all day")
            self.lbl_avail.setStyleSheet(f"font-size: 14px; color: {COLORS['success']}; font-weight: 600;")

    def get_data(self) -> dict:
        return {
            "officer_name": self.cmb_officer.currentText().strip(),
            "site_name": self.cmb_site.currentText().strip(),
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
            "start_time": self.time_start.time().toString("HH:mm"),
            "end_time": self.time_end.time().toString("HH:mm"),
            "assignment_type": self.cmb_type.currentText(),
            "status": self.cmb_status.currentText(),
            "notes": self.txt_notes.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Bulk Assignment Dialog
# ════════════════════════════════════════════════════════════════════════

class BulkAssignmentDialog(QDialog):
    """Create recurring assignments across multiple days."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Add Assignments")
        self.setMinimumWidth(520)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Officer (ops officers only)
        self.cmb_officer = QComboBox()
        self.cmb_officer.setEditable(False)
        officer_names = data_manager.get_ops_officer_names()
        if officer_names:
            self.cmb_officer.addItems(officer_names)
        else:
            self.cmb_officer.addItem("-- Add officers first --")
        layout.addRow("Officer:", self.cmb_officer)

        # Site
        self.cmb_site = QComboBox()
        self.cmb_site.setEditable(False)
        active_sites = data_manager.get_active_sites()
        site_names = [s.get("name", "") for s in active_sites if s.get("name")]
        if site_names:
            self.cmb_site.addItems(site_names)
        else:
            self.cmb_site.addItem("-- Add sites first --")
        layout.addRow("Site:", self.cmb_site)

        # Date range
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setDate(QDate.currentDate())
        layout.addRow("Start Date:", self.date_start)

        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setDate(QDate.currentDate().addDays(4))
        layout.addRow("End Date:", self.date_end)

        # Days of week checkboxes
        self.day_checks = QListWidget()
        self.day_checks.setMaximumHeight(110)
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            item = QListWidgetItem(day)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"] else Qt.Unchecked)
            self.day_checks.addItem(item)
        layout.addRow("Days:", self.day_checks)

        # Shift times
        self.time_start = QTimeEdit()
        self.time_start.setDisplayFormat("HH:mm")
        self.time_start.setTime(QTime(8, 0))
        layout.addRow("Start Time:", self.time_start)

        self.time_end = QTimeEdit()
        self.time_end.setDisplayFormat("HH:mm")
        self.time_end.setTime(QTime(16, 0))
        layout.addRow("End Time:", self.time_end)

        # Type
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["Billable", "Anchor/Shadow", "Training", "PTO Coverage"])
        layout.addRow("Type:", self.cmb_type)

        # Preview count
        self.lbl_preview = QLabel("5 assignments will be created")
        self.lbl_preview.setStyleSheet(f"font-weight: 600; color: {tc('primary')};")
        layout.addRow("Preview:", self.lbl_preview)

        self.date_start.dateChanged.connect(self._update_preview)
        self.date_end.dateChanged.connect(self._update_preview)
        self.day_checks.itemChanged.connect(self._update_preview)
        self._update_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _get_selected_days(self):
        days = []
        day_map = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7}  # Qt: Mon=1
        for i in range(self.day_checks.count()):
            item = self.day_checks.item(i)
            if item.checkState() == Qt.Checked:
                days.append(day_map[i])
        return days

    def _update_preview(self):
        dates = self._get_dates()
        self.lbl_preview.setText(f"{len(dates)} assignment(s) will be created")

    def _get_dates(self):
        selected_days = self._get_selected_days()
        dates = []
        d = self.date_start.date()
        end = self.date_end.date()
        while d <= end:
            if d.dayOfWeek() in selected_days:
                dates.append(d.toString("yyyy-MM-dd"))
            d = d.addDays(1)
        return dates

    def get_data(self):
        return {
            "officer_name": self.cmb_officer.currentText().strip(),
            "site_name": self.cmb_site.currentText().strip(),
            "dates": self._get_dates(),
            "start_time": self.time_start.time().toString("HH:mm"),
            "end_time": self.time_end.time().toString("HH:mm"),
            "assignment_type": self.cmb_type.currentText(),
            "status": "Scheduled",
        }


# ════════════════════════════════════════════════════════════════════════
# Schedules / Assignments Page
# ════════════════════════════════════════════════════════════════════════

class CoverageCell(QWidget):
    """Widget for a single cell in the coverage map grid."""

    def __init__(self, assignments, requests, parent=None):
        super().__init__(parent)
        self.assignments = assignments
        self.requests = requests
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        if not assignments and not requests:
            # Empty -- dash
            lbl = QLabel("\u2014")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px;")
            layout.addWidget(lbl)
        else:
            # Show "No requests" label if there are assignments but no open requests
            has_open = any(r.get("status") == "Open" for r in requests)
            if assignments and not has_open:
                tag = QLabel("No requests")
                tag.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
                layout.addWidget(tag)

            # Assignment cards -- green
            for asn in assignments:
                card = QFrame()
                card.setStyleSheet(f"""
                    QFrame {{
                        background: {COLORS['success']};
                        border-radius: 4px;
                        padding: 3px 6px;
                    }}
                """)
                card_lay = QVBoxLayout(card)
                card_lay.setContentsMargins(6, 5, 6, 5)
                card_lay.setSpacing(1)
                name_lbl = QLabel(asn.get("officer_name", ""))
                name_lbl.setStyleSheet("color: white; font-size: 12px; font-weight: 600;")
                name_lbl.setWordWrap(True)
                time_lbl = QLabel(f"{asn.get('start_time', '')} - {asn.get('end_time', '')}")
                time_lbl.setStyleSheet("color: white; font-size: 11px;")
                card_lay.addWidget(name_lbl)
                card_lay.addWidget(time_lbl)
                layout.addWidget(card)

            # Open request slots -- red "OPEN" cards
            for req in requests:
                if req.get("status") == "Open":
                    card = QFrame()
                    card.setStyleSheet(f"""
                        QFrame {{
                            background: {COLORS['danger']};
                            border-radius: 4px;
                        }}
                    """)
                    card_lay = QVBoxLayout(card)
                    card_lay.setContentsMargins(6, 4, 6, 4)
                    card_lay.setSpacing(0)
                    lbl = QLabel(f"OPEN")
                    lbl.setStyleSheet("color: white; font-size: 12px; font-weight: 700;")
                    card_lay.addWidget(lbl)
                    layout.addWidget(card)

        layout.addStretch()


class SchedulesPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._week_offset = 0  # 0 = current week
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # -- Header row with title + action buttons
        header_row = QHBoxLayout()
        header = QLabel("Coverage Map")
        header.setFont(QFont("Segoe UI", 20, QFont.Bold))
        header.setStyleSheet(f"color: {tc('primary')};")
        header_row.addWidget(header)
        header_row.addStretch()

        # Legend
        for color, label in [
            (COLORS["success"], "Covered"),
            (COLORS["danger"], "Open/No Coverage"),
            ("#D1D5DB", "No Requests"),
        ]:
            dot = QLabel("  ")
            dot.setFixedSize(14, 14)
            dot.setStyleSheet(f"background: {color}; border-radius: 3px;")
            header_row.addWidget(dot)
            leg_lbl = QLabel(label)
            leg_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; margin-right: 10px;")
            header_row.addWidget(leg_lbl)

        layout.addLayout(header_row)

        # -- Action buttons row
        action_row = QHBoxLayout()

        self.btn_prev = QPushButton("< Prev Week")
        self.btn_prev.setStyleSheet(btn_style(COLORS["primary_light"], "white", COLORS["primary_mid"]))
        self.btn_prev.clicked.connect(self._prev_week)
        action_row.addWidget(self.btn_prev)

        self.lbl_week = QLabel("")
        self.lbl_week.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.lbl_week.setStyleSheet(f"color: {tc('primary')};")
        self.lbl_week.setAlignment(Qt.AlignCenter)
        action_row.addWidget(self.lbl_week)

        self.btn_next = QPushButton("Next Week >")
        self.btn_next.setStyleSheet(btn_style(COLORS["primary_light"], "white", COLORS["primary_mid"]))
        self.btn_next.clicked.connect(self._next_week)
        action_row.addWidget(self.btn_next)

        action_row.addSpacing(20)

        self.btn_export_pdf = QPushButton("Export PDF")
        self.btn_export_pdf.setStyleSheet(btn_style("#6b7280", "white", "#4b5563"))
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        action_row.addWidget(self.btn_export_pdf)

        self.btn_export_week = QPushButton("Export Week")
        self.btn_export_week.setStyleSheet(btn_style("#6b7280", "white", "#4b5563"))
        self.btn_export_week.setToolTip("Export current week's schedule to PDF")
        self.btn_export_week.clicked.connect(self._export_week_pdf)
        action_row.addWidget(self.btn_export_week)

        btn_csv = QPushButton("Export CSV")
        btn_csv.setStyleSheet(btn_style("#6b7280", "white", "#4b5563"))
        btn_csv.clicked.connect(self._export_csv)
        action_row.addWidget(btn_csv)

        btn_import_csv = QPushButton("Import CSV")
        btn_import_csv.setStyleSheet(btn_style(COLORS["primary_light"], "white", COLORS.get("primary_mid", COLORS["primary_light"])))
        btn_import_csv.setToolTip("Import assignments from CSV (officer_name, site_name, date, start_time, end_time, assignment_type)")
        btn_import_csv.clicked.connect(self._import_assignments_csv)
        action_row.addWidget(btn_import_csv)

        self.btn_bulk = QPushButton("+ Bulk Add")
        self.btn_bulk.setStyleSheet(btn_style(COLORS["primary_light"], "white", COLORS["primary_mid"]))
        self.btn_bulk.clicked.connect(self._bulk_add)
        action_row.addWidget(self.btn_bulk)

        self.btn_add = QPushButton("+ New Assignment")
        self.btn_add.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        self.btn_add.clicked.connect(self._add_assignment)
        action_row.addWidget(self.btn_add)

        layout.addLayout(action_row)

        # -- Coverage map grid
        self.grid = QTableWidget()
        self.grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.grid.setSelectionMode(QAbstractItemView.NoSelection)
        self.grid.verticalHeader().setVisible(False)
        self.grid.setShowGrid(True)
        self.grid.setStyleSheet(f"""
            QTableWidget {{
                gridline-color: {tc('border')};
                background: {tc('bg')};
            }}
            QHeaderView::section {{
                background: {tc('primary')};
                color: white;
                font-weight: 600;
                font-size: 14px;
                padding: 8px 6px;
                border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        layout.addWidget(self.grid)

        # -- Bottom row
        bottom_row = QHBoxLayout()
        self.btn_edit = QPushButton("Edit Selected")
        self.btn_edit.setStyleSheet(btn_style(tc("primary"), "white", COLORS["primary_light"]))
        self.btn_edit.clicked.connect(self._edit_selected)
        bottom_row.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.setStyleSheet(btn_style(COLORS["danger"], "white"))
        self.btn_delete.clicked.connect(self._delete_selected)
        bottom_row.addWidget(self.btn_delete)

        self.btn_clone = QPushButton("Clone to Date")
        self.btn_clone.setStyleSheet(btn_style(COLORS["primary_light"], "white", COLORS.get("primary_mid", COLORS["primary_light"])))
        self.btn_clone.setToolTip("Duplicate the selected assignment to a new date")
        self.btn_clone.clicked.connect(self._clone_assignment)
        bottom_row.addWidget(self.btn_clone)

        bottom_row.addStretch()
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px;")
        bottom_row.addWidget(self.lbl_count)
        layout.addLayout(bottom_row)

        # Track assignment_id per grid cell for edit/delete
        self._cell_assignment_ids = {}

    def _get_week_dates(self):
        """Return 7 date strings (Sun-Sat) for the current week offset."""
        from datetime import date as dt_date
        today = dt_date.today()
        # Start of week (Sunday)
        start = today - timedelta(days=today.weekday() + 1) + timedelta(weeks=self._week_offset)
        if today.weekday() == 6:  # Sunday
            start = today + timedelta(weeks=self._week_offset)
        return [(start + timedelta(days=i)) for i in range(7)]

    def _prev_week(self):
        self._week_offset -= 1
        self.refresh()

    def _next_week(self):
        self._week_offset += 1
        self.refresh()

    def refresh(self):
        week_dates = self._get_week_dates()
        date_strs = [d.strftime("%Y-%m-%d") for d in week_dates]

        # Week label
        self.lbl_week.setText(
            f"{week_dates[0].strftime('%b %d')} \u2014 {week_dates[6].strftime('%b %d, %Y')}"
        )

        # Get data
        sites = data_manager.get_all_sites()
        active_sites = [s for s in sites if s.get("status") == "Active"]
        all_assignments = data_manager.get_all_assignments()
        all_records = data_manager.get_all_records()

        # Build lookup: (site_name, date) -> [assignments]
        asn_lookup = {}
        for a in all_assignments:
            key = (a.get("site_name", ""), a.get("date", ""))
            asn_lookup.setdefault(key, []).append(a)

        # Build lookup: (site_name, date) -> [requests]
        req_lookup = {}
        for r in all_records:
            key = (r.get("site_name", ""), r.get("date", ""))
            req_lookup.setdefault(key, []).append(r)

        # Day headers
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        col_headers = ["Site / Job #"] + [
            f"{day_names[i]}\n{week_dates[i].month}/{week_dates[i].day}"
            for i in range(7)
        ]

        self.grid.setColumnCount(8)
        self.grid.setHorizontalHeaderLabels(col_headers)
        self.grid.setRowCount(len(active_sites))

        hdr = self.grid.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.grid.setColumnWidth(0, 150)
        for c in range(1, 8):
            hdr.setSectionResizeMode(c, QHeaderView.Stretch)

        self._cell_assignment_ids = {}
        total_assignments = 0

        for row, site in enumerate(active_sites):
            site_name = site.get("name", "")
            billing_code = site.get("billing_code", "")

            # Site label cell
            site_widget = QWidget()
            site_lay = QVBoxLayout(site_widget)
            site_lay.setContentsMargins(8, 8, 8, 8)
            site_lay.setSpacing(0)
            name_lbl = QLabel(site_name)
            name_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
            name_lbl.setStyleSheet(f"color: {tc('text')};")
            name_lbl.setWordWrap(True)
            site_lay.addWidget(name_lbl)
            if billing_code:
                code_lbl = QLabel(billing_code)
                code_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
                site_lay.addWidget(code_lbl)
            site_lay.addStretch()
            site_widget.setStyleSheet(f"background: {tc('card')}; border-right: 2px solid {tc('border')};")
            self.grid.setCellWidget(row, 0, site_widget)

            for col, date_str in enumerate(date_strs):
                day_col = col + 1
                cell_asn = asn_lookup.get((site_name, date_str), [])
                cell_req = req_lookup.get((site_name, date_str), [])
                total_assignments += len(cell_asn)

                # Store assignment IDs for this cell
                for a in cell_asn:
                    self._cell_assignment_ids[(row, day_col)] = a.get("assignment_id", "")

                cell = CoverageCell(cell_asn, cell_req)
                cell.setStyleSheet(f"background: {tc('card')};")
                self.grid.setCellWidget(row, day_col, cell)

            # Auto row height
            self.grid.setRowHeight(row, max(90, 45 + 40 * max(1, max(
                len(asn_lookup.get((site_name, d), [])) +
                len([r for r in req_lookup.get((site_name, d), []) if r.get("status") == "Open"])
                for d in date_strs
            ))))

        self.lbl_count.setText(f"{total_assignments} assignment(s) this week  |  {len(active_sites)} active site(s)")

    def _get_selected_id(self):
        """Get assignment ID from the currently selected grid cell."""
        row = self.grid.currentRow()
        col = self.grid.currentColumn()
        return self._cell_assignment_ids.get((row, col))

    def _add_assignment(self):
        dlg = AssignmentDialog(self)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            if not d["officer_name"] or not d["site_name"]:
                QMessageBox.warning(self, "Validation", "Officer and site are required.")
                return
            # Check for conflicts
            conflicts = data_manager.detect_conflicts(
                d["officer_name"], d["date"], d["start_time"], d["end_time"]
            )
            if conflicts:
                msg = f"Conflict detected! {d['officer_name']} already has:\n"
                for c in conflicts:
                    msg += f"  - {c['site_name']} {c['start_time']}-{c['end_time']}\n"
                msg += "\nSave anyway?"
                if QMessageBox.question(self, "Conflict", msg,
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    return
            username = self.app_state["user"]["username"]
            asn = data_manager.create_assignment(d, username)
            audit.log_event("operations", "assignment_create", username,
                            f"Assigned {d['officer_name']} to {d['site_name']} on {d['date']}")
            self.refresh()

    def _bulk_add(self):
        dlg = BulkAssignmentDialog(self)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            if not d["officer_name"] or not d["site_name"] or d["officer_name"].startswith("--"):
                QMessageBox.warning(self, "Validation", "Officer and site are required.")
                return
            if not d["dates"]:
                QMessageBox.warning(self, "Validation", "No dates match the selected day range.")
                return
            username = self.app_state["user"]["username"]
            created = 0
            for date in d["dates"]:
                asn_data = {
                    "officer_name": d["officer_name"],
                    "site_name": d["site_name"],
                    "date": date,
                    "start_time": d["start_time"],
                    "end_time": d["end_time"],
                    "assignment_type": d["assignment_type"],
                    "status": d["status"],
                    "notes": "",
                }
                data_manager.create_assignment(asn_data, username)
                created += 1
            audit.log_event("operations", "assignment_bulk_create", username,
                            f"Bulk created {created} assignments for {d['officer_name']} at {d['site_name']}")
            QMessageBox.information(self, "Success", f"Created {created} assignments.")
            self.refresh()

    def _edit_selected(self):
        aid = self._get_selected_id()
        if not aid:
            QMessageBox.information(self, "Select", "Please select an assignment.")
            return
        asn = data_manager.get_assignment(aid)
        if not asn:
            return
        dlg = AssignmentDialog(self, assignment=asn)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            conflicts = data_manager.detect_conflicts(
                d["officer_name"], d["date"], d["start_time"], d["end_time"],
                exclude_id=aid
            )
            if conflicts:
                msg = f"Conflict detected! {d['officer_name']} already has:\n"
                for c in conflicts:
                    msg += f"  - {c['site_name']} {c['start_time']}-{c['end_time']}\n"
                msg += "\nSave anyway?"
                if QMessageBox.question(self, "Conflict", msg,
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    return
            username = self.app_state["user"]["username"]
            data_manager.update_assignment(aid, d, username)
            audit.log_event("operations", "assignment_edit", username, f"Updated assignment {aid}")
            self.refresh()

    def _delete_selected(self):
        aid = self._get_selected_id()
        if not aid:
            QMessageBox.information(self, "Select", "Please select an assignment.")
            return
        confirm = QMessageBox.question(
            self, "Confirm Delete", f"Delete assignment {aid}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            username = self.app_state["user"]["username"]
            data_manager.delete_assignment(aid)
            audit.log_event("operations", "assignment_delete", username, f"Deleted assignment {aid}")
            self.refresh()

    def _clone_assignment(self):
        """Clone the selected assignment to a new date via date picker."""
        aid = self._get_selected_id()
        if not aid:
            QMessageBox.information(self, "Select", "Please select an assignment to clone.")
            return
        asn = data_manager.get_assignment(aid)
        if not asn:
            return

        # Prompt for new date
        dlg = QDialog(self)
        dlg.setWindowTitle("Clone Assignment to Date")
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        info = QLabel(
            f"Cloning: {asn.get('officer_name', '')} at {asn.get('site_name', '')}\n"
            f"Original date: {asn.get('date', '')}"
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {tc('text')}; font-size: 14px;")
        lay.addWidget(info)

        lbl = QLabel("Select new date:")
        lbl.setStyleSheet(f"font-weight: 600; color: {tc('text')};")
        lay.addWidget(lbl)

        date_pick = QDateEdit()
        date_pick.setCalendarPopup(True)
        date_pick.setDisplayFormat("yyyy-MM-dd")
        date_pick.setDate(QDate.currentDate())
        lay.addWidget(date_pick)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return

        new_date = date_pick.date().toString("yyyy-MM-dd")
        clone_data = {
            "officer_name": asn.get("officer_name", ""),
            "site_name": asn.get("site_name", ""),
            "date": new_date,
            "start_time": asn.get("start_time", ""),
            "end_time": asn.get("end_time", ""),
            "assignment_type": asn.get("assignment_type", "Billable"),
            "status": "Scheduled",
            "notes": asn.get("notes", ""),
        }

        # Check conflicts
        conflicts = data_manager.detect_conflicts(
            clone_data["officer_name"], new_date,
            clone_data["start_time"], clone_data["end_time"],
        )
        if conflicts:
            msg = f"Conflict on {new_date}! {clone_data['officer_name']} already has:\n"
            for c in conflicts:
                msg += f"  - {c['site_name']} {c['start_time']}-{c['end_time']}\n"
            msg += "\nClone anyway?"
            if QMessageBox.question(self, "Conflict", msg,
                                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return

        username = self.app_state["user"]["username"]
        new_id = data_manager.create_assignment(clone_data, username)
        audit.log_event(
            "operations", "assignment_clone", username,
            f"Cloned assignment {aid} to {new_date} as {new_id}"
        )
        QMessageBox.information(
            self, "Cloned",
            f"Assignment cloned to {new_date}."
        )
        self.refresh()

    def _export_pdf(self):
        """Export current schedule view to a formatted PDF using PDFDocument."""
        assignments = data_manager.get_all_assignments()
        if not assignments:
            QMessageBox.information(self, "No Data", "No assignments to export.")
            return
        try:
            from src.pdf_export import PDFDocument

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            doc = PDFDocument(f"schedule_{ts}.pdf", "Cerasus Operations \u2014 Schedule Report")
            doc.begin()

            doc.add_text(f"Total Assignments: {len(assignments)}", bold=True, size=10)
            doc.add_spacing(6)

            headers = ["Officer", "Site", "Date", "Time", "Hours", "Type", "Status"]
            rows = []
            for asn in assignments:
                start = asn.get("start_time", "")
                end = asn.get("end_time", "")
                hours = data_manager.calculate_shift_hours(start, end) if start and end else ""
                rows.append([
                    asn.get("officer_name", ""),
                    asn.get("site_name", ""),
                    asn.get("date", ""),
                    f"{start} - {end}",
                    str(hours),
                    asn.get("assignment_type", ""),
                    asn.get("status", ""),
                ])

            pw = doc.page_width
            col_widths = [pw * w for w in [0.20, 0.18, 0.14, 0.16, 0.08, 0.12, 0.12]]
            doc.add_table(headers, rows, col_widths)

            path = doc.finish()
            username = self.app_state["user"]["username"]
            audit.log_event("operations", "report_export", username, f"Exported schedule PDF: {path}")
            QMessageBox.information(self, "Export Complete", f"Schedule PDF saved to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to generate PDF:\n{str(e)}")

    def _export_week_pdf(self):
        """Export the current week's schedule to a PDF with Officer, Site, Date, Start, End, Hours, Type columns."""
        week_dates = self._get_week_dates()
        start_str = week_dates[0].strftime("%Y-%m-%d")
        end_str = week_dates[6].strftime("%Y-%m-%d")
        assignments = data_manager.get_assignments_for_week(start_str, end_str)

        if not assignments:
            QMessageBox.information(self, "No Data", "No assignments this week to export.")
            return

        try:
            from src.pdf_export import PDFDocument

            week_label = f"{week_dates[0].strftime('%b %d')} - {week_dates[6].strftime('%b %d, %Y')}"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            doc = PDFDocument(
                f"weekly_schedule_{ts}.pdf",
                f"Weekly Schedule: {week_label}",
                orientation="landscape",
            )
            doc.begin()

            doc.add_text(f"Assignments: {len(assignments)}", bold=True, size=10)
            doc.add_spacing(6)

            headers = ["Officer", "Site", "Date", "Start", "End", "Hours", "Type"]
            rows = []
            for asn in sorted(assignments, key=lambda a: (a.get("date", ""), a.get("officer_name", ""))):
                start = asn.get("start_time", "")
                end = asn.get("end_time", "")
                hours = data_manager.calculate_shift_hours(start, end) if start and end else asn.get("hours", "")
                rows.append([
                    asn.get("officer_name", ""),
                    asn.get("site_name", ""),
                    asn.get("date", ""),
                    start,
                    end,
                    str(hours),
                    asn.get("assignment_type", ""),
                ])

            pw = doc.page_width
            col_widths = [pw * w for w in [0.20, 0.20, 0.14, 0.10, 0.10, 0.10, 0.16]]
            doc.add_table(headers, rows, col_widths)

            path = doc.finish()
            username = self.app_state["user"]["username"]
            audit.log_event("operations", "report_export", username, f"Exported weekly schedule PDF: {path}")
            QMessageBox.information(self, "Export Complete", f"Weekly schedule PDF saved to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to generate PDF:\n{str(e)}")

    def _export_csv(self):
        ensure_directories()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(REPORTS_DIR, f"assignments_export_{ts}.csv")
        assignments = data_manager.get_all_assignments()
        if not assignments:
            QMessageBox.information(self, "No Data", "No assignments to export.")
            return
        keys = list(assignments[0].keys())
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(assignments)
        username = self.app_state["user"]["username"]
        audit.log_event("operations", "report_export", username, f"Exported assignments CSV: {filename}")
        QMessageBox.information(self, "Export Complete", f"Saved to:\n{filename}")

    def _import_assignments_csv(self):
        """Import assignments from a CSV file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Assignments CSV", "",
            "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            QMessageBox.warning(self, "File Error", f"Could not read file:\n{e}")
            return

        username = self.app_state["user"]["username"]
        result = data_manager.import_assignments_csv(text, username)
        imported = result["imported"]
        skipped = result["skipped"]
        errors = result["errors"]

        msg = f"Imported {imported} assignment(s)."
        if skipped:
            msg += f"\nSkipped {skipped} row(s)."
        if errors:
            msg += f"\n\nErrors ({len(errors)}):\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n... and {len(errors) - 10} more"

        audit.log_event("operations", "assignment_import", username,
                        f"Imported {imported} assignments from CSV")
        QMessageBox.information(self, "Import Complete", msg)
        self.refresh()


# ════════════════════════════════════════════════════════════════════════
# Weekly Schedule Grid — Read-only visual board (#25)
# ════════════════════════════════════════════════════════════════════════

# Color map for assignment types
_ASSGN_TYPE_COLORS = {
    "Billable":       "#22c55e",   # green
    "Anchor/Shadow":  "#3b82f6",   # blue
    "Anchor":         "#3b82f6",
    "Training":       "#a855f7",   # purple
    "PTO Coverage":   "#f59e0b",   # amber
    "Coverage":       "#f97316",   # orange
}


class WeeklyScheduleGrid(QWidget):
    """Read-only weekly grid: officers (rows) x days (columns), showing assignments."""

    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._week_offset = 0
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # Header row
        header_row = QHBoxLayout()
        header = QLabel("Weekly Schedule Board")
        header.setFont(QFont("Segoe UI", 20, QFont.Bold))
        header.setStyleSheet(f"color: {tc('primary')};")
        header_row.addWidget(header)
        header_row.addStretch()

        # Legend
        for atype, color in [
            ("Billable", "#22c55e"), ("Anchor", "#3b82f6"),
            ("Training", "#a855f7"), ("Coverage", "#f97316"),
        ]:
            dot = QLabel("  ")
            dot.setFixedSize(14, 14)
            dot.setStyleSheet(f"background: {color}; border-radius: 3px;")
            header_row.addWidget(dot)
            leg = QLabel(atype)
            leg.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; margin-right: 10px;")
            header_row.addWidget(leg)

        layout.addLayout(header_row)

        # Navigation row
        nav_row = QHBoxLayout()
        btn_prev = QPushButton("< Prev Week")
        btn_prev.setStyleSheet(btn_style(COLORS["primary_light"], "white", COLORS.get("primary_mid", COLORS["primary_light"])))
        btn_prev.clicked.connect(self._prev_week)
        nav_row.addWidget(btn_prev)

        self.lbl_week = QLabel("")
        self.lbl_week.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.lbl_week.setStyleSheet(f"color: {tc('primary')};")
        self.lbl_week.setAlignment(Qt.AlignCenter)
        nav_row.addWidget(self.lbl_week)

        btn_next = QPushButton("Next Week >")
        btn_next.setStyleSheet(btn_style(COLORS["primary_light"], "white", COLORS.get("primary_mid", COLORS["primary_light"])))
        btn_next.clicked.connect(self._next_week)
        nav_row.addWidget(btn_next)

        layout.addLayout(nav_row)

        # Grid table
        self.grid = QTableWidget()
        self.grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.grid.setSelectionMode(QAbstractItemView.NoSelection)
        self.grid.verticalHeader().setVisible(False)
        self.grid.setShowGrid(True)
        self.grid.setStyleSheet(f"""
            QTableWidget {{
                gridline-color: {tc('border')};
                background: {tc('bg')};
            }}
            QHeaderView::section {{
                background: {tc('primary')};
                color: white;
                font-weight: 600;
                font-size: 14px;
                padding: 8px 6px;
                border: none;
                border-right: 1px solid {COLORS.get('primary_light', '#60a5fa')};
            }}
        """)
        layout.addWidget(self.grid)

        # Count label
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px;")
        layout.addWidget(self.lbl_count)

    def _get_week_dates(self):
        today = date.today()
        start = today - timedelta(days=(today.weekday() + 1) % 7) + timedelta(weeks=self._week_offset)
        if today.weekday() == 6:  # Sunday
            start = today + timedelta(weeks=self._week_offset)
        return [start + timedelta(days=i) for i in range(7)]

    def _prev_week(self):
        self._week_offset -= 1
        self.refresh()

    def _next_week(self):
        self._week_offset += 1
        self.refresh()

    def refresh(self):
        week_dates = self._get_week_dates()
        date_strs = [d.strftime("%Y-%m-%d") for d in week_dates]

        self.lbl_week.setText(
            f"{week_dates[0].strftime('%b %d')} \u2014 {week_dates[6].strftime('%b %d, %Y')}"
        )

        # Fetch data
        officers = data_manager.get_ops_officers()
        all_assignments = data_manager.get_assignments_for_week(date_strs[0], date_strs[6])

        # Build lookup: (officer_name, date) -> [assignments]
        asn_lookup = {}
        for a in all_assignments:
            key = (a.get("officer_name", ""), a.get("date", ""))
            asn_lookup.setdefault(key, []).append(a)

        # Setup grid: Officer col + 7 day columns
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        col_headers = ["Officer"] + [
            f"{day_names[i]}\n{week_dates[i].month}/{week_dates[i].day}"
            for i in range(7)
        ]
        self.grid.setColumnCount(8)
        self.grid.setHorizontalHeaderLabels(col_headers)
        self.grid.setRowCount(len(officers))

        hdr = self.grid.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.grid.setColumnWidth(0, 160)
        for c in range(1, 8):
            hdr.setSectionResizeMode(c, QHeaderView.Stretch)

        total_asn = 0
        for row, off in enumerate(officers):
            name = off.get("name", "")
            role = off.get("role", "")

            # Officer name cell
            name_w = QWidget()
            name_lay = QVBoxLayout(name_w)
            name_lay.setContentsMargins(8, 6, 4, 6)
            name_lay.setSpacing(0)
            n_lbl = QLabel(name)
            n_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
            n_lbl.setStyleSheet(f"color: {tc('text')};")
            r_lbl = QLabel(role)
            r_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px;")
            name_lay.addWidget(n_lbl)
            name_lay.addWidget(r_lbl)
            name_w.setStyleSheet(f"background: {tc('card')}; border-right: 2px solid {tc('border')};")
            self.grid.setCellWidget(row, 0, name_w)

            for col, ds in enumerate(date_strs):
                day_col = col + 1
                cell_asns = asn_lookup.get((name, ds), [])
                total_asn += len(cell_asns)

                cell_w = QWidget()
                cell_lay = QVBoxLayout(cell_w)
                cell_lay.setContentsMargins(4, 4, 4, 4)
                cell_lay.setSpacing(3)

                if not cell_asns:
                    dash = QLabel("\u2014")
                    dash.setAlignment(Qt.AlignCenter)
                    dash.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
                    cell_lay.addWidget(dash)
                else:
                    for asn in cell_asns:
                        atype = asn.get("assignment_type", "Billable")
                        bg_color = _ASSGN_TYPE_COLORS.get(atype, "#6b7280")
                        card = QFrame()
                        card.setStyleSheet(f"""
                            QFrame {{
                                background: {bg_color};
                                border-radius: 4px;
                                padding: 2px 4px;
                            }}
                        """)
                        card_lay = QVBoxLayout(card)
                        card_lay.setContentsMargins(5, 3, 5, 3)
                        card_lay.setSpacing(1)
                        site_lbl = QLabel(asn.get("site_name", ""))
                        site_lbl.setStyleSheet("color: white; font-size: 11px; font-weight: 600;")
                        site_lbl.setWordWrap(True)
                        time_lbl = QLabel(f"{asn.get('start_time', '')}-{asn.get('end_time', '')}")
                        time_lbl.setStyleSheet("color: white; font-size: 10px;")
                        card_lay.addWidget(site_lbl)
                        card_lay.addWidget(time_lbl)
                        cell_lay.addWidget(card)

                cell_lay.addStretch()
                cell_w.setStyleSheet(f"background: {tc('card')};")
                self.grid.setCellWidget(row, day_col, cell_w)

            # Row height
            max_cards = max(len(asn_lookup.get((name, d), [])) for d in date_strs) if date_strs else 1
            self.grid.setRowHeight(row, max(60, 30 + 38 * max(1, max_cards)))

        self.lbl_count.setText(f"{total_asn} assignment(s)  |  {len(officers)} officer(s)")
