"""
Cerasus Hub -- Custom Report Builder
QDialog that lets admins build ad-hoc reports from any data source,
preview results, and export to CSV or PDF.
"""

import csv
import os
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QGridLayout, QCheckBox, QScrollArea, QWidget, QFileDialog, QMessageBox,
    QSizePolicy, QAbstractItemView,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont

from src.config import tc, btn_style, REPORTS_DIR, ensure_directories, _is_dark
from src.database import get_conn


# ── Data source definitions ───────────────────────────────────────────
# Each source maps to a table, a display name, available columns,
# and optional date/site/status column names for filtering.

DATA_SOURCES = {
    "Officers": {
        "table": "officers",
        "columns": [
            ("officer_id", "Officer ID"),
            ("name", "Name"),
            ("employee_id", "Employee ID"),
            ("first_name", "First Name"),
            ("last_name", "Last Name"),
            ("email", "Email"),
            ("phone", "Phone"),
            ("job_title", "Job Title"),
            ("role", "Role"),
            ("site", "Site"),
            ("hire_date", "Hire Date"),
            ("status", "Status"),
            ("weekly_hours", "Weekly Hours"),
            ("active_points", "Active Points"),
            ("discipline_level", "Discipline Level"),
            ("created_at", "Created At"),
        ],
        "date_col": "hire_date",
        "site_col": "site",
        "status_col": "status",
        "status_values": ["Active", "Inactive", "Terminated"],
    },
    "Infractions": {
        "table": "ats_infractions",
        "columns": [
            ("id", "ID"),
            ("employee_id", "Employee ID"),
            ("infraction_type", "Infraction Type"),
            ("infraction_date", "Infraction Date"),
            ("points_assigned", "Points Assigned"),
            ("description", "Description"),
            ("site", "Site"),
            ("entered_by", "Entered By"),
            ("discipline_triggered", "Discipline Triggered"),
            ("is_emergency_exemption", "Emergency Exemption"),
            ("points_active", "Points Active"),
            ("created_at", "Created At"),
        ],
        "date_col": "infraction_date",
        "site_col": "site",
        "status_col": None,
        "status_values": [],
    },
    "Issuances": {
        "table": "uni_issuances",
        "columns": [
            ("issuance_id", "Issuance ID"),
            ("officer_name", "Officer Name"),
            ("item_name", "Item Name"),
            ("size", "Size"),
            ("quantity", "Quantity"),
            ("condition_issued", "Condition"),
            ("date_issued", "Date Issued"),
            ("issued_by", "Issued By"),
            ("status", "Status"),
            ("date_returned", "Date Returned"),
            ("location", "Location"),
            ("notes", "Notes"),
        ],
        "date_col": "date_issued",
        "site_col": None,
        "status_col": "status",
        "status_values": ["Outstanding", "Returned", "Lost", "Damaged"],
    },
    "Assignments": {
        "table": "ops_assignments",
        "columns": [
            ("assignment_id", "Assignment ID"),
            ("officer_name", "Officer Name"),
            ("site_name", "Site Name"),
            ("date", "Date"),
            ("start_time", "Start Time"),
            ("end_time", "End Time"),
            ("hours", "Hours"),
            ("assignment_type", "Type"),
            ("status", "Status"),
            ("notes", "Notes"),
            ("created_at", "Created At"),
        ],
        "date_col": "date",
        "site_col": "site_name",
        "status_col": "status",
        "status_values": ["Scheduled", "Confirmed", "Completed", "Cancelled"],
    },
    "Training Progress": {
        "table": "trn_certificates",
        "columns": [
            ("cert_id", "Certificate ID"),
            ("officer_id", "Officer ID"),
            ("course_id", "Course ID"),
            ("issued_date", "Issued Date"),
            ("expiry_date", "Expiry Date"),
            ("status", "Status"),
            ("points_earned", "Points Earned"),
            ("created_at", "Created At"),
        ],
        "date_col": "issued_date",
        "site_col": None,
        "status_col": "status",
        "status_values": ["Active", "Expired", "Revoked"],
    },
}


class ReportBuilderDialog(QDialog):
    """Custom report builder dialog for ad-hoc queries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Report Builder")
        self.setMinimumSize(900, 650)
        self.resize(1050, 720)
        self._column_checks = []
        self._preview_data = []
        self._preview_headers = []
        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 16, 20, 16)

        # Title
        title = QLabel("Custom Report Builder")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        root.addWidget(title)

        # ── Source selection ───────────────────────────────────────────
        src_group = QGroupBox("Data Source")
        src_lay = QHBoxLayout(src_group)

        src_lay.addWidget(QLabel("Source:"))
        self.cmb_source = QComboBox()
        self.cmb_source.addItems(list(DATA_SOURCES.keys()))
        self.cmb_source.currentTextChanged.connect(self._on_source_changed)
        self.cmb_source.setMinimumWidth(200)
        src_lay.addWidget(self.cmb_source)
        src_lay.addStretch()
        root.addWidget(src_group)

        # ── Columns selection ─────────────────────────────────────────
        col_group = QGroupBox("Columns")
        col_outer = QVBoxLayout(col_group)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(self._select_all_columns)
        btn_all.setStyleSheet(btn_style(tc('info'), "white"))
        btn_none = QPushButton("Deselect All")
        btn_none.clicked.connect(self._deselect_all_columns)
        btn_none.setStyleSheet(btn_style(tc('border'), tc('text')))
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        col_outer.addLayout(btn_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(120)
        self._col_container = QWidget()
        self._col_layout = QGridLayout(self._col_container)
        self._col_layout.setSpacing(6)
        scroll.setWidget(self._col_container)
        col_outer.addWidget(scroll)
        root.addWidget(col_group)

        # ── Filters ───────────────────────────────────────────────────
        filt_group = QGroupBox("Filters")
        filt_lay = QGridLayout(filt_group)

        filt_lay.addWidget(QLabel("Date From:"), 0, 0)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        filt_lay.addWidget(self.date_from, 0, 1)

        filt_lay.addWidget(QLabel("Date To:"), 0, 2)
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        filt_lay.addWidget(self.date_to, 0, 3)

        filt_lay.addWidget(QLabel("Site:"), 1, 0)
        self.cmb_site = QComboBox()
        self.cmb_site.addItem("(All Sites)")
        self.cmb_site.setMinimumWidth(180)
        filt_lay.addWidget(self.cmb_site, 1, 1)

        filt_lay.addWidget(QLabel("Status:"), 1, 2)
        self.cmb_status = QComboBox()
        self.cmb_status.addItem("(All)")
        self.cmb_status.setMinimumWidth(160)
        filt_lay.addWidget(self.cmb_status, 1, 3)

        root.addWidget(filt_group)

        # ── Action buttons ────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        self.btn_preview = QPushButton("Preview")
        self.btn_preview.setStyleSheet(btn_style(tc('info'), "white"))
        self.btn_preview.clicked.connect(self._run_preview)
        btn_bar.addWidget(self.btn_preview)

        self.btn_csv = QPushButton("Export CSV")
        self.btn_csv.setStyleSheet(btn_style(tc('success'), "white"))
        self.btn_csv.clicked.connect(self._export_csv)
        self.btn_csv.setEnabled(False)
        btn_bar.addWidget(self.btn_csv)

        self.btn_pdf = QPushButton("Export PDF")
        self.btn_pdf.setStyleSheet(btn_style(tc('accent'), "white"))
        self.btn_pdf.clicked.connect(self._export_pdf)
        self.btn_pdf.setEnabled(False)
        btn_bar.addWidget(self.btn_pdf)

        btn_bar.addStretch()

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        btn_bar.addWidget(self.lbl_count)

        root.addLayout(btn_bar)

        # ── Preview table ─────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(self.table, 1)

        # Populate initial source
        self._load_sites()
        self._on_source_changed(self.cmb_source.currentText())

    # ── Helpers ────────────────────────────────────────────────────────

    def _load_sites(self):
        """Populate site combo from database."""
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT name FROM sites WHERE status = 'Active' ORDER BY name"
            ).fetchall()
            conn.close()
            for r in rows:
                self.cmb_site.addItem(r["name"])
        except Exception:
            pass

    def _on_source_changed(self, source_name: str):
        """Rebuild column checkboxes and filter options for the selected source."""
        src = DATA_SOURCES.get(source_name)
        if not src:
            return

        # Clear old checkboxes
        for cb in self._column_checks:
            cb.setParent(None)
        self._column_checks.clear()

        # Create new checkboxes in a grid (4 per row)
        for idx, (col_key, col_label) in enumerate(src["columns"]):
            cb = QCheckBox(col_label)
            cb.setChecked(True)
            cb.setProperty("col_key", col_key)
            self._col_layout.addWidget(cb, idx // 4, idx % 4)
            self._column_checks.append(cb)

        # Update status filter
        self.cmb_status.clear()
        self.cmb_status.addItem("(All)")
        for sv in src.get("status_values", []):
            self.cmb_status.addItem(sv)

        # Enable/disable site filter
        has_site = src.get("site_col") is not None
        self.cmb_site.setEnabled(has_site)

        # Enable/disable date filters
        has_date = src.get("date_col") is not None
        self.date_from.setEnabled(has_date)
        self.date_to.setEnabled(has_date)

    def _select_all_columns(self):
        for cb in self._column_checks:
            cb.setChecked(True)

    def _deselect_all_columns(self):
        for cb in self._column_checks:
            cb.setChecked(False)

    def _selected_columns(self):
        """Return list of (col_key, col_label) for checked columns."""
        result = []
        for cb in self._column_checks:
            if cb.isChecked():
                result.append((cb.property("col_key"), cb.text()))
        return result

    # ── Query Builder ─────────────────────────────────────────────────

    def _build_query(self):
        """Build SQL query from current selections. Returns (sql, params, headers)."""
        source_name = self.cmb_source.currentText()
        src = DATA_SOURCES.get(source_name)
        if not src:
            return None, [], []

        selected = self._selected_columns()
        if not selected:
            QMessageBox.warning(self, "No Columns", "Please select at least one column.")
            return None, [], []

        col_keys = [c[0] for c in selected]
        col_labels = [c[1] for c in selected]

        table = src["table"]
        sql = f"SELECT {', '.join(col_keys)} FROM {table}"
        params = []
        conditions = []

        # Date filter
        date_col = src.get("date_col")
        if date_col and self.date_from.isEnabled():
            d_from = self.date_from.date().toString("yyyy-MM-dd")
            d_to = self.date_to.date().toString("yyyy-MM-dd")
            conditions.append(f"{date_col} BETWEEN ? AND ?")
            params.extend([d_from, d_to])

        # Site filter
        site_col = src.get("site_col")
        if site_col and self.cmb_site.isEnabled():
            site_val = self.cmb_site.currentText()
            if site_val and site_val != "(All Sites)":
                conditions.append(f"{site_col} = ?")
                params.append(site_val)

        # Status filter
        status_col = src.get("status_col")
        if status_col:
            status_val = self.cmb_status.currentText()
            if status_val and status_val != "(All)":
                conditions.append(f"{status_col} = ?")
                params.append(status_val)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        # Order by first column
        sql += f" ORDER BY {col_keys[0]}"
        sql += " LIMIT 5000"

        return sql, params, col_labels

    # ── Preview ───────────────────────────────────────────────────────

    def _run_preview(self):
        """Execute query and display results in the table."""
        sql, params, headers = self._build_query()
        if sql is None:
            return

        try:
            conn = get_conn()
            rows = conn.execute(sql, params).fetchall()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Query Error", f"Failed to run query:\n{e}")
            return

        self._preview_headers = headers
        self._preview_data = [list(r) for r in rows]

        self.table.setRowCount(len(rows))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        for r_idx, row in enumerate(rows):
            for c_idx in range(len(headers)):
                val = str(row[c_idx]) if row[c_idx] is not None else ""
                item = QTableWidgetItem(val)
                self.table.setItem(r_idx, c_idx, item)

        self.table.resizeColumnsToContents()
        count = len(rows)
        limit_note = " (limit 5000)" if count >= 5000 else ""
        self.lbl_count.setText(f"{count} record(s){limit_note}")

        has_data = count > 0
        self.btn_csv.setEnabled(has_data)
        self.btn_pdf.setEnabled(has_data)

    # ── Export CSV ────────────────────────────────────────────────────

    def _export_csv(self):
        """Export preview data to a CSV file."""
        if not self._preview_data:
            return

        ensure_directories()
        source = self.cmb_source.currentText().replace(" ", "_").lower()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"report_{source}_{ts}.csv"
        default_path = os.path.join(REPORTS_DIR, default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV Report", default_path, "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(self._preview_headers)
                for row in self._preview_data:
                    writer.writerow([str(v) if v is not None else "" for v in row])
            QMessageBox.information(self, "Export Complete", f"CSV saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to save CSV:\n{e}")

    # ── Export PDF ────────────────────────────────────────────────────

    def _export_pdf(self):
        """Export preview data to a PDF file using the pdf_export module."""
        if not self._preview_data:
            return

        try:
            from src.pdf_export import PDFDocument
        except ImportError:
            QMessageBox.critical(self, "Error", "PDF export module not available.")
            return

        source = self.cmb_source.currentText()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = source.replace(" ", "_").lower()
        filename = f"report_{safe}_{ts}.pdf"

        try:
            doc = PDFDocument(
                filename=filename,
                title=f"Custom Report -- {source}",
                orientation="landscape",
            )
            doc.begin()
            doc.add_text(f"Custom Report: {source}", bold=True, size=14)
            doc.add_text(
                f"Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}",
                size=10, color="#6B7280",
            )

            d_from = self.date_from.date().toString("yyyy-MM-dd")
            d_to = self.date_to.date().toString("yyyy-MM-dd")
            doc.add_text(f"Date Range: {d_from} to {d_to}", size=10, color="#6B7280")

            site_val = self.cmb_site.currentText()
            if site_val and site_val != "(All Sites)":
                doc.add_text(f"Site: {site_val}", size=10, color="#6B7280")

            status_val = self.cmb_status.currentText()
            if status_val and status_val != "(All)":
                doc.add_text(f"Status: {status_val}", size=10, color="#6B7280")

            doc.add_spacing(8)

            # Build table rows as list of list of strings
            table_rows = []
            for row in self._preview_data:
                table_rows.append([str(v) if v is not None else "" for v in row])

            doc.add_table(self._preview_headers, table_rows)
            doc.add_spacing(6)
            doc.add_text(
                f"{len(self._preview_data)} record(s)", size=10, color="#6B7280"
            )

            filepath = doc.finish()
            QMessageBox.information(
                self, "Export Complete", f"PDF saved to:\n{filepath}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to generate PDF:\n{e}")
