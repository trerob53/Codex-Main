"""
Cerasus Hub -- People & Sites Management Page
Centralized officer and site management accessible from the module picker.
"""

import csv
import io

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox, QLineEdit,
    QDialog, QDialogButtonBox, QFormLayout, QTextEdit,
    QDateEdit, QMessageBox, QFileDialog, QSizePolicy,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont

from src.config import (
    COLORS, tc, btn_style, build_dialog_stylesheet, _is_dark, ROLE_ADMIN,
)
from src import shared_data, audit


# =========================================================================
# Officer Dialog
# =========================================================================

class OfficerDialog(QDialog):
    """Add / Edit officer dialog."""

    JOB_TITLES = [
        "Security Officer",
        "Flex Officer",
        "Site Supervisor",
        "Field Supervisor",
        "Operations Manager",
        "Account Manager",
        "Director",
    ]

    def __init__(self, parent=None, officer: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Officer" if officer else "Add Officer")
        self.setMinimumWidth(480)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._officer = officer or {}
        self._sites = shared_data.get_site_names()
        self._build()
        if officer:
            self._populate(officer)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self.first_name = QLineEdit()
        self.first_name.setPlaceholderText("Required")
        form.addRow("First Name:", self.first_name)

        self.last_name = QLineEdit()
        self.last_name.setPlaceholderText("Required")
        form.addRow("Last Name:", self.last_name)

        self.employee_id = QLineEdit()
        form.addRow("Employee ID:", self.employee_id)

        self.job_title = QComboBox()
        self.job_title.addItems(self.JOB_TITLES)
        form.addRow("Job Title:", self.job_title)

        self.site_combo = QComboBox()
        self.site_combo.addItem("(None)", "")
        for s in self._sites:
            self.site_combo.addItem(s["name"], s["name"])
        form.addRow("Site:", self.site_combo)

        self.hire_date = QDateEdit()
        self.hire_date.setCalendarPopup(True)
        self.hire_date.setDate(QDate.currentDate())
        self.hire_date.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Hire Date:", self.hire_date)

        self.email = QLineEdit()
        form.addRow("Email:", self.email)

        self.phone = QLineEdit()
        form.addRow("Phone:", self.phone)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["Active", "Inactive", "Terminated"])
        form.addRow("Status:", self.status_combo)

        self.notes = QTextEdit()
        self.notes.setFixedHeight(80)
        form.addRow("Notes:", self.notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate(self, o: dict):
        self.first_name.setText(o.get("first_name", ""))
        self.last_name.setText(o.get("last_name", ""))
        self.employee_id.setText(o.get("employee_id", ""))

        jt = o.get("job_title", "")
        idx = self.job_title.findText(jt)
        if idx >= 0:
            self.job_title.setCurrentIndex(idx)

        site = o.get("site", "")
        sidx = self.site_combo.findText(site)
        if sidx >= 0:
            self.site_combo.setCurrentIndex(sidx)

        hd = o.get("hire_date", "")
        if hd:
            qd = QDate.fromString(hd, "yyyy-MM-dd")
            if qd.isValid():
                self.hire_date.setDate(qd)

        self.email.setText(o.get("email", ""))
        self.phone.setText(o.get("phone", ""))

        st = o.get("status", "Active")
        stidx = self.status_combo.findText(st)
        if stidx >= 0:
            self.status_combo.setCurrentIndex(stidx)

        self.notes.setPlainText(o.get("notes", ""))

    def _validate_and_accept(self):
        if not self.first_name.text().strip():
            QMessageBox.warning(self, "Validation", "First name is required.")
            self.first_name.setFocus()
            return
        if not self.last_name.text().strip():
            QMessageBox.warning(self, "Validation", "Last name is required.")
            self.last_name.setFocus()
            return
        self.accept()

    def get_fields(self) -> dict:
        fn = self.first_name.text().strip()
        ln = self.last_name.text().strip()
        return {
            "first_name": fn,
            "last_name": ln,
            "name": f"{fn} {ln}".strip(),
            "employee_id": self.employee_id.text().strip(),
            "job_title": self.job_title.currentText(),
            "site": self.site_combo.currentData() or "",
            "hire_date": self.hire_date.date().toString("yyyy-MM-dd"),
            "email": self.email.text().strip(),
            "phone": self.phone.text().strip(),
            "status": self.status_combo.currentText(),
            "notes": self.notes.toPlainText().strip(),
        }


# =========================================================================
# Site Dialog
# =========================================================================

class SiteDialog(QDialog):
    """Add / Edit site dialog."""

    def __init__(self, parent=None, site: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Site" if site else "Add Site")
        self.setMinimumWidth(460)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._site = site or {}
        self._build()
        if site:
            self._populate(site)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Required")
        form.addRow("Name:", self.name_edit)

        self.address = QLineEdit()
        form.addRow("Address:", self.address)

        self.city = QLineEdit()
        form.addRow("City:", self.city)

        self.state = QLineEdit()
        form.addRow("State:", self.state)

        self.billing_code = QLineEdit()
        form.addRow("Billing Code:", self.billing_code)

        self.market = QLineEdit()
        form.addRow("Market:", self.market)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["Active", "Inactive"])
        form.addRow("Status:", self.status_combo)

        self.notes = QTextEdit()
        self.notes.setFixedHeight(80)
        form.addRow("Notes:", self.notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate(self, s: dict):
        self.name_edit.setText(s.get("name", ""))
        self.address.setText(s.get("address", ""))
        self.city.setText(s.get("city", ""))
        self.state.setText(s.get("state", ""))
        self.billing_code.setText(s.get("billing_code", ""))
        self.market.setText(s.get("market", ""))

        st = s.get("status", "Active")
        sidx = self.status_combo.findText(st)
        if sidx >= 0:
            self.status_combo.setCurrentIndex(sidx)

        self.notes.setPlainText(s.get("notes", ""))

    def _validate_and_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Site name is required.")
            self.name_edit.setFocus()
            return
        self.accept()

    def get_fields(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "address": self.address.text().strip(),
            "city": self.city.text().strip(),
            "state": self.state.text().strip(),
            "billing_code": self.billing_code.text().strip(),
            "market": self.market.text().strip(),
            "status": self.status_combo.currentText(),
            "notes": self.notes.toPlainText().strip(),
        }


# =========================================================================
# Hub People & Sites Page
# =========================================================================

class HubPeoplePage(QWidget):
    """Full-page People & Sites management for Cerasus Hub."""

    def __init__(self, app_state: dict, on_back=None, parent=None):
        super().__init__(parent)
        self._app_state = app_state
        self._on_back = on_back
        self._build()
        self._refresh_officers()
        self._refresh_sites()

    # ── helpers ────────────────────────────────────────────────────────

    def _username(self) -> str:
        user = self._app_state.get("user", {})
        return user.get("username", "")

    def _is_admin(self) -> bool:
        user = self._app_state.get("user", {})
        return user.get("role") == ROLE_ADMIN

    # ── build UI ──────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"""
            QFrame {{ background: {tc('card')}; border-bottom: 1px solid {tc('border')}; }}
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(24, 0, 24, 0)

        if self._on_back:
            back_btn = QPushButton("Back to Hub")
            back_btn.setCursor(Qt.PointingHandCursor)
            back_btn.setFixedHeight(36)
            back_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {tc('text_light')};
                    font-size: 13px; font-weight: 600; border: none; padding: 0 12px;
                }}
                QPushButton:hover {{ color: {COLORS['accent']}; }}
            """)
            back_btn.clicked.connect(self._on_back)
            h_lay.addWidget(back_btn)

        title = QLabel("People and Sites")
        title.setStyleSheet(f"""
            color: {tc('text')}; font-size: 20px; font-weight: 300;
            letter-spacing: 2px; background: transparent; border: none;
        """)
        h_lay.addWidget(title)
        h_lay.addStretch()

        outer.addWidget(header)

        # ── Tab widget ────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {tc('bg')};
            }}
            QTabBar::tab {{
                background: {tc('card')};
                color: {tc('text_light')};
                border: 1px solid {tc('border')};
                border-bottom: none;
                padding: 10px 28px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background: {tc('bg')};
                color: {tc('text')};
                border-bottom: 2px solid {COLORS['accent']};
            }}
            QTabBar::tab:hover {{
                color: {COLORS['accent']};
            }}
        """)

        self.tabs.addTab(self._build_officers_tab(), "Officers")
        self.tabs.addTab(self._build_sites_tab(), "Sites")
        outer.addWidget(self.tabs)

    # ── Officers Tab ──────────────────────────────────────────────────

    def _build_officers_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet(f"background: {tc('bg')};")
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(10)

        # Header row
        header_row = QHBoxLayout()
        self._officer_count_label = QLabel("Officer Roster (0)")
        self._officer_count_label.setStyleSheet(f"""
            color: {tc('text')}; font-size: 16px; font-weight: 600;
            letter-spacing: 1px; background: transparent;
        """)
        header_row.addWidget(self._officer_count_label)
        header_row.addStretch()

        add_btn = QPushButton("Add Officer")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedHeight(36)
        add_btn.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        add_btn.clicked.connect(self._add_officer)
        header_row.addWidget(add_btn)

        import_btn = QPushButton("Import CSV")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.setFixedHeight(36)
        import_btn.setStyleSheet(btn_style(COLORS["info"], "white", COLORS["primary_light"]))
        import_btn.clicked.connect(self._import_officers_csv)
        header_row.addWidget(import_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setFixedHeight(36)
        export_btn.setStyleSheet(btn_style(COLORS["info"], "white", COLORS["primary_light"]))
        export_btn.clicked.connect(self._export_officers_csv)
        header_row.addWidget(export_btn)

        lay.addLayout(header_row)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.officer_search = QLineEdit()
        self.officer_search.setPlaceholderText("Search name, employee ID, site...")
        self.officer_search.setFixedHeight(36)
        self.officer_search.setStyleSheet(f"""
            QLineEdit {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 4px; padding: 0 12px; font-size: 14px; color: {tc('text')};
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        self.officer_search.textChanged.connect(self._refresh_officers)
        filter_row.addWidget(self.officer_search, 3)

        self.officer_status_filter = QComboBox()
        self.officer_status_filter.addItems(["All", "Active", "Inactive", "Terminated"])
        self.officer_status_filter.setFixedHeight(36)
        self.officer_status_filter.setFixedWidth(140)
        self.officer_status_filter.currentIndexChanged.connect(self._refresh_officers)
        filter_row.addWidget(self.officer_status_filter)

        self.officer_site_filter = QComboBox()
        self.officer_site_filter.addItem("All Sites", "")
        for s in shared_data.get_site_names():
            self.officer_site_filter.addItem(s["name"], s["name"])
        self.officer_site_filter.setFixedHeight(36)
        self.officer_site_filter.setFixedWidth(180)
        self.officer_site_filter.currentIndexChanged.connect(self._refresh_officers)
        filter_row.addWidget(self.officer_site_filter)

        lay.addLayout(filter_row)

        # Table
        self.officer_table = QTableWidget()
        self.officer_table.setColumnCount(8)
        self.officer_table.setHorizontalHeaderLabels([
            "Name", "Employee ID", "Job Title", "Site",
            "Status", "Hire Date", "Email", "Phone",
        ])
        self.officer_table.horizontalHeader().setStretchLastSection(True)
        self.officer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.officer_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.officer_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.officer_table.setAlternatingRowColors(True)
        self.officer_table.doubleClicked.connect(self._officer_double_click)
        lay.addWidget(self.officer_table)

        # Action row
        action_row = QHBoxLayout()
        action_row.addStretch()

        edit_btn = QPushButton("Edit")
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setFixedHeight(36)
        edit_btn.setStyleSheet(btn_style(COLORS["info"], "white", COLORS["primary_light"]))
        edit_btn.clicked.connect(self._edit_officer)
        action_row.addWidget(edit_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setFixedHeight(36)
        delete_btn.setStyleSheet(btn_style(COLORS["danger"], "white", COLORS["accent_hover"]))
        delete_btn.clicked.connect(self._delete_officer)
        action_row.addWidget(delete_btn)

        lay.addLayout(action_row)

        return tab

    # ── Sites Tab ─────────────────────────────────────────────────────

    def _build_sites_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet(f"background: {tc('bg')};")
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(10)

        # Header row
        header_row = QHBoxLayout()
        self._site_count_label = QLabel("Site Roster (0)")
        self._site_count_label.setStyleSheet(f"""
            color: {tc('text')}; font-size: 16px; font-weight: 600;
            letter-spacing: 1px; background: transparent;
        """)
        header_row.addWidget(self._site_count_label)
        header_row.addStretch()

        add_btn = QPushButton("Add Site")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedHeight(36)
        add_btn.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        add_btn.clicked.connect(self._add_site)
        header_row.addWidget(add_btn)

        import_btn = QPushButton("Import CSV")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.setFixedHeight(36)
        import_btn.setStyleSheet(btn_style(COLORS["success"], "white", COLORS["accent_hover"]))
        import_btn.clicked.connect(self._import_sites_csv)
        header_row.addWidget(import_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setFixedHeight(36)
        export_btn.setStyleSheet(btn_style(COLORS["info"], "white", COLORS["primary_light"]))
        export_btn.clicked.connect(self._export_sites_csv)
        header_row.addWidget(export_btn)

        lay.addLayout(header_row)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.site_search = QLineEdit()
        self.site_search.setPlaceholderText("Search sites...")
        self.site_search.setFixedHeight(36)
        self.site_search.setStyleSheet(f"""
            QLineEdit {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 4px; padding: 0 12px; font-size: 14px; color: {tc('text')};
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        self.site_search.textChanged.connect(self._refresh_sites)
        filter_row.addWidget(self.site_search, 3)

        self.site_status_filter = QComboBox()
        self.site_status_filter.addItems(["All", "Active", "Inactive"])
        self.site_status_filter.setFixedHeight(36)
        self.site_status_filter.setFixedWidth(140)
        self.site_status_filter.currentIndexChanged.connect(self._refresh_sites)
        filter_row.addWidget(self.site_status_filter)

        lay.addLayout(filter_row)

        # Table
        self.site_table = QTableWidget()
        self.site_table.setColumnCount(7)
        self.site_table.setHorizontalHeaderLabels([
            "Name", "Address", "City", "State",
            "Status", "Billing Code", "Market",
        ])
        self.site_table.horizontalHeader().setStretchLastSection(True)
        self.site_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.site_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.site_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.site_table.setAlternatingRowColors(True)
        lay.addWidget(self.site_table)

        # Action row
        action_row = QHBoxLayout()
        action_row.addStretch()

        edit_btn = QPushButton("Edit")
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setFixedHeight(36)
        edit_btn.setStyleSheet(btn_style(COLORS["info"], "white", COLORS["primary_light"]))
        edit_btn.clicked.connect(self._edit_site)
        action_row.addWidget(edit_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setFixedHeight(36)
        delete_btn.setStyleSheet(btn_style(COLORS["danger"], "white", COLORS["accent_hover"]))
        delete_btn.clicked.connect(self._delete_site)
        action_row.addWidget(delete_btn)

        lay.addLayout(action_row)

        return tab

    # ── Officer data operations ───────────────────────────────────────

    def _get_filtered_officers(self) -> list:
        """Return officers matching current search / filter state."""
        query = self.officer_search.text().strip()
        status = self.officer_status_filter.currentText()
        site = self.officer_site_filter.currentData()

        if query:
            officers = shared_data.search_officers(query)
        else:
            officers = shared_data.get_all_officers()

        if status != "All":
            officers = [o for o in officers if o.get("status") == status]
        if site:
            officers = [o for o in officers if o.get("site") == site]

        return officers

    def _refresh_officers(self):
        officers = self._get_filtered_officers()
        self._officer_count_label.setText(f"Officer Roster ({len(officers)})")
        self.officer_table.setRowCount(len(officers))

        for row, o in enumerate(officers):
            cols = [
                o.get("name", ""),
                o.get("employee_id", ""),
                o.get("job_title", ""),
                o.get("site", ""),
                o.get("status", ""),
                o.get("hire_date", ""),
                o.get("email", ""),
                o.get("phone", ""),
            ]
            for col, val in enumerate(cols):
                item = QTableWidgetItem(str(val))
                item.setData(Qt.UserRole, o.get("officer_id", ""))
                self.officer_table.setItem(row, col, item)

    def _selected_officer_id(self) -> str | None:
        row = self.officer_table.currentRow()
        if row < 0:
            return None
        item = self.officer_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _add_officer(self):
        dlg = OfficerDialog(self)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            oid = shared_data.create_officer(fields, created_by=self._username())
            audit.log_event(
                "hub", "CREATE", self._username(),
                details=f"Created officer: {fields.get('name', '')}",
                table_name="officers", record_id=oid, action="create",
            )
            self._refresh_officers()

    def _edit_officer(self):
        oid = self._selected_officer_id()
        if not oid:
            QMessageBox.information(self, "Select", "Select an officer to edit.")
            return
        officer = shared_data.get_officer(oid)
        if not officer:
            return
        dlg = OfficerDialog(self, officer=officer)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            shared_data.update_officer(oid, fields, updated_by=self._username())
            audit.log_event(
                "hub", "UPDATE", self._username(),
                details=f"Updated officer: {fields.get('name', '')}",
                table_name="officers", record_id=oid, action="update",
            )
            self._refresh_officers()

    def _delete_officer(self):
        if not self._is_admin():
            QMessageBox.warning(self, "Permission Denied", "Only admins can delete officers.")
            return
        oid = self._selected_officer_id()
        if not oid:
            QMessageBox.information(self, "Select", "Select an officer to delete.")
            return
        officer = shared_data.get_officer(oid)
        name = officer.get("name", "") if officer else oid
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete officer '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            shared_data.delete_officer(oid)
            audit.log_event(
                "hub", "DELETE", self._username(),
                details=f"Deleted officer: {name}",
                table_name="officers", record_id=oid, action="delete",
            )
            self._refresh_officers()

    def _officer_double_click(self, index):
        oid = self._selected_officer_id()
        if not oid:
            return
        try:
            from src.officer_360 import show_officer_profile
            show_officer_profile(self, oid, self._app_state)
        except Exception:
            pass

    def _import_officers_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Officers CSV", "", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []

                # Auto-detect TrackTik format
                tracktik_cols = {"Staffr Id", "Name", "Last Name", "Title"}
                is_tracktik = tracktik_cols.issubset(set(fieldnames))

                count = 0
                skipped = 0
                existing_ids = {
                    o.get("employee_id") for o in shared_data.get_all_officers()
                    if o.get("employee_id")
                }

                for row in reader:
                    if is_tracktik:
                        fields = self._normalize_tracktik_row(row)
                    else:
                        fields = {}
                        for key in [
                            "first_name", "last_name", "employee_id", "job_title",
                            "site", "hire_date", "email", "phone", "status", "notes",
                        ]:
                            if key in row:
                                fields[key] = row[key].strip()
                        # Build name from first/last if not provided
                        if "name" in row and row["name"].strip():
                            fields["name"] = row["name"].strip()
                        elif fields.get("first_name") or fields.get("last_name"):
                            fields["name"] = f"{fields.get('first_name', '')} {fields.get('last_name', '')}".strip()

                    name = fields.get("name", "").strip()
                    if not name:
                        skipped += 1
                        continue

                    # Skip system accounts
                    first = (fields.get("first_name") or name.split()[0] if name else "").lower()
                    if first in ("tracktik", "review"):
                        skipped += 1
                        continue

                    # Skip duplicate employee IDs
                    emp_id = fields.get("employee_id", "").strip()
                    if emp_id and emp_id in existing_ids:
                        skipped += 1
                        continue

                    if not fields.get("status"):
                        fields["status"] = "Active"

                    shared_data.create_officer(fields, created_by=self._username())
                    if emp_id:
                        existing_ids.add(emp_id)
                    count += 1

            audit.log_event(
                "hub", "IMPORT", self._username(),
                details=f"Imported {count} officer(s) from CSV ({skipped} skipped)",
                table_name="officers", action="import",
            )
            msg = f"Imported {count} officer(s)."
            if skipped:
                msg += f"\n{skipped} row(s) skipped (system accounts, duplicates, or missing names)."
            QMessageBox.information(self, "Import Complete", msg)
            self._refresh_officers()
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to import CSV:\n{e}")

    @staticmethod
    def _normalize_tracktik_row(row: dict) -> dict:
        """Convert a TrackTik CSV row to our standard officer fields."""
        first = row.get("Name", "").strip()
        middle = row.get("Middle Name", "").strip()
        last = row.get("Last Name", "").strip()
        name_parts = [first]
        if middle:
            name_parts.append(middle)
        name_parts.append(last)
        name = " ".join(p for p in name_parts if p).strip()

        phone = row.get("Phone", "").strip()
        if phone.upper() == "NO NUMBER":
            phone = ""

        email = row.get("Email", "").strip()

        title = row.get("Title", "").strip() or "Security Officer"
        hire_date = row.get("Hiredate", "").strip()
        term_date = row.get("Termination Date", "").strip()
        staffr_id = row.get("Staffr Id", "").strip()

        if term_date and term_date != "N/A":
            status = "Terminated"
        else:
            status = "Active"

        # Resolve site from address
        from src.modules.uniforms.data_manager import _resolve_site_from_address
        address = row.get("Address", "").strip()
        site = _resolve_site_from_address(address)

        gender = row.get("Gender", "").strip()
        tt_role = row.get("Role", "").strip()

        # Map TrackTik role to a hub role
        tt_lower = tt_role.lower()
        if "administrator" in tt_lower:
            role = "Administrator"
        elif "manager" in tt_lower or "security director" in tt_lower:
            role = "Management"
        elif "supervisor" in tt_lower:
            role = "Supervisor"
        else:
            role = "Guard"

        notes_parts = []
        if gender:
            notes_parts.append(f"Gender: {gender}")
        if tt_role:
            notes_parts.append(f"TrackTik Role: {tt_role}")

        return {
            "name": name,
            "first_name": first,
            "last_name": last,
            "employee_id": staffr_id,
            "job_title": title,
            "site": site,
            "hire_date": hire_date,
            "email": email,
            "phone": phone,
            "status": status,
            "role": role,
            "notes": "; ".join(notes_parts),
        }

    def _export_officers_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Officers CSV", "officers_export.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            officers = shared_data.get_all_officers()
            headers = [
                "name", "employee_id", "first_name", "last_name",
                "job_title", "site", "status", "hire_date", "email", "phone", "notes",
            ]
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for o in officers:
                writer.writerow(o)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(buf.getvalue())
            audit.log_event(
                "hub", "EXPORT", self._username(),
                details=f"Exported {len(officers)} officer(s) to CSV",
                table_name="officers", action="export",
            )
            QMessageBox.information(self, "Export Complete", f"Exported {len(officers)} officer(s).")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export CSV:\n{e}")

    # ── Site data operations ──────────────────────────────────────────

    def _get_filtered_sites(self) -> list:
        """Return sites matching current search / filter state."""
        query = self.site_search.text().strip().lower()
        status = self.site_status_filter.currentText()

        if status != "All":
            sites = shared_data.get_all_sites(status_filter=status)
        else:
            sites = shared_data.get_all_sites()

        if query:
            sites = [
                s for s in sites
                if query in s.get("name", "").lower()
                or query in s.get("address", "").lower()
                or query in s.get("city", "").lower()
                or query in s.get("market", "").lower()
                or query in s.get("billing_code", "").lower()
            ]

        return sites

    def _refresh_sites(self):
        sites = self._get_filtered_sites()
        self._site_count_label.setText(f"Site Roster ({len(sites)})")
        self.site_table.setRowCount(len(sites))

        for row, s in enumerate(sites):
            cols = [
                s.get("name", ""),
                s.get("address", ""),
                s.get("city", ""),
                s.get("state", ""),
                s.get("status", ""),
                s.get("billing_code", ""),
                s.get("market", ""),
            ]
            for col, val in enumerate(cols):
                item = QTableWidgetItem(str(val))
                item.setData(Qt.UserRole, s.get("site_id", ""))
                self.site_table.setItem(row, col, item)

    def _selected_site_id(self) -> str | None:
        row = self.site_table.currentRow()
        if row < 0:
            return None
        item = self.site_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _add_site(self):
        dlg = SiteDialog(self)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            sid = shared_data.create_site(fields, created_by=self._username())
            audit.log_event(
                "hub", "CREATE", self._username(),
                details=f"Created site: {fields.get('name', '')}",
                table_name="sites", record_id=sid, action="create",
            )
            self._refresh_sites()
            # Also refresh the officer site filter dropdown
            self._rebuild_site_filter()

    def _edit_site(self):
        sid = self._selected_site_id()
        if not sid:
            QMessageBox.information(self, "Select", "Select a site to edit.")
            return
        site = shared_data.get_site(sid)
        if not site:
            return
        dlg = SiteDialog(self, site=site)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            shared_data.update_site(sid, fields, updated_by=self._username())
            audit.log_event(
                "hub", "UPDATE", self._username(),
                details=f"Updated site: {fields.get('name', '')}",
                table_name="sites", record_id=sid, action="update",
            )
            self._refresh_sites()
            self._rebuild_site_filter()

    def _delete_site(self):
        if not self._is_admin():
            QMessageBox.warning(self, "Permission Denied", "Only admins can delete sites.")
            return
        sid = self._selected_site_id()
        if not sid:
            QMessageBox.information(self, "Select", "Select a site to delete.")
            return
        site = shared_data.get_site(sid)
        name = site.get("name", "") if site else sid
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete site '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            shared_data.delete_site(sid)
            audit.log_event(
                "hub", "DELETE", self._username(),
                details=f"Deleted site: {name}",
                table_name="sites", record_id=sid, action="delete",
            )
            self._refresh_sites()
            self._rebuild_site_filter()

    def _import_sites_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Sites CSV", "", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []

                # Auto-detect TrackTik client/company format
                tracktik_site_cols = {"Company", "Address", "City", "State"}
                is_tracktik = tracktik_site_cols.issubset(set(fieldnames))

                # Build lookup of existing sites by name
                all_sites = shared_data.get_all_sites()
                existing_by_name = {}
                for s in all_sites:
                    n = s.get("name", "").lower()
                    if n:
                        existing_by_name[n] = s

                # Internal/region names to skip
                skip_names = {"indy region", "cerasus llc", "cerasus", ""}

                count = 0
                updated = 0
                skipped = 0

                for row in reader:
                    if is_tracktik:
                        fields = self._normalize_tracktik_site_row(row)
                    else:
                        fields = {}
                        for key in [
                            "name", "address", "city", "state",
                            "billing_code", "market", "style",
                            "overtime_sensitivity", "status", "notes",
                        ]:
                            if key in row:
                                fields[key] = row[key].strip()

                    name = fields.get("name", "").strip()
                    if not name or name.lower() in skip_names:
                        skipped += 1
                        continue

                    # If site exists, update missing fields (city, state, market, notes)
                    existing = existing_by_name.get(name.lower())
                    if existing:
                        update_fields = {}
                        for key in ("address", "city", "state", "market", "notes"):
                            if fields.get(key) and not existing.get(key, "").strip():
                                update_fields[key] = fields[key]
                        if update_fields:
                            shared_data.update_site(
                                existing["site_id"], update_fields,
                                updated_by=self._username(),
                            )
                            updated += 1
                        else:
                            skipped += 1
                        continue

                    if not fields.get("status"):
                        fields["status"] = "Active"

                    shared_data.create_site(fields, created_by=self._username())
                    existing_by_name[name.lower()] = fields
                    count += 1

            audit.log_event(
                "hub", "IMPORT", self._username(),
                details=f"Imported {count} site(s), updated {updated}, skipped {skipped} from CSV",
                table_name="sites", action="import",
            )
            msg = f"Imported {count} new site(s)."
            if updated:
                msg += f"\n{updated} existing site(s) updated with new data."
            if skipped:
                msg += f"\n{skipped} row(s) skipped (already complete, internal, or missing names)."
            QMessageBox.information(self, "Import Complete", msg)
            self._refresh_sites()
            self._rebuild_site_filter()
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to import CSV:\n{e}")

    @staticmethod
    def _normalize_tracktik_site_row(row: dict) -> dict:
        """Convert a TrackTik Clients/Companies CSV row to hub site fields.

        TrackTik columns: Staffr Id, Company, First Name, Last Name, Title,
        Address, Address Suite, City, State, Zip, Phone Main, Email, Status,
        Region, Creation Date, Closed Date, Remarks, etc.
        """
        name = row.get("Company", "").strip()
        address = row.get("Address", "").strip()
        suite = row.get("Address Suite", "").strip()
        if suite:
            address = f"{address}, {suite}".strip(", ")
        city = row.get("City", "").strip()
        state = row.get("State", "").strip()
        zipcode = row.get("Zip", "").strip()

        # Build full address with zip
        if zipcode and address:
            full_address = address
        else:
            full_address = address

        status_raw = row.get("Status", "").strip()
        closed = row.get("Closed Date", "").strip()
        if closed:
            status = "Inactive"
        elif status_raw.lower() in ("active", ""):
            status = "Active"
        else:
            status = status_raw or "Active"

        # Contact info as notes
        contact_first = row.get("First Name", "").strip()
        contact_last = row.get("Last Name", "").strip()
        contact_title = row.get("Title", "").strip()
        phone = row.get("Phone Main", "").strip()
        email = row.get("Email", "").strip()
        remarks = row.get("Remarks", "").strip()

        notes_parts = []
        if contact_first or contact_last:
            contact_name = f"{contact_first} {contact_last}".strip()
            line = f"Contact: {contact_name}"
            if contact_title:
                line += f" ({contact_title})"
            notes_parts.append(line)
        if phone:
            notes_parts.append(f"Phone: {phone}")
        if email:
            notes_parts.append(f"Email: {email}")
        if remarks:
            notes_parts.append(f"Notes: {remarks}")
        notes = "\n".join(notes_parts)

        # Determine market from state
        market = ""
        if state.upper() == "IN":
            market = "Indianapolis"
        elif state.upper() == "OH":
            market = "Cincinnati"

        return {
            "name": name,
            "address": full_address,
            "city": city,
            "state": state,
            "market": market,
            "status": status,
            "notes": notes,
        }

    def _export_sites_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Sites CSV", "sites_export.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            sites = shared_data.get_all_sites()
            headers = [
                "name", "address", "city", "state",
                "billing_code", "market", "status", "notes",
            ]
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for s in sites:
                writer.writerow(s)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(buf.getvalue())
            audit.log_event(
                "hub", "EXPORT", self._username(),
                details=f"Exported {len(sites)} site(s) to CSV",
                table_name="sites", action="export",
            )
            QMessageBox.information(self, "Export Complete", f"Exported {len(sites)} site(s).")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export CSV:\n{e}")

    def _rebuild_site_filter(self):
        """Rebuild the officer tab site filter dropdown after site changes."""
        current = self.officer_site_filter.currentData()
        self.officer_site_filter.blockSignals(True)
        self.officer_site_filter.clear()
        self.officer_site_filter.addItem("All Sites", "")
        for s in shared_data.get_site_names():
            self.officer_site_filter.addItem(s["name"], s["name"])
        # Restore selection
        if current:
            idx = self.officer_site_filter.findData(current)
            if idx >= 0:
                self.officer_site_filter.setCurrentIndex(idx)
        self.officer_site_filter.blockSignals(False)
