"""
Cerasus Hub -- DLS & Overtime Module: Admin Pages
ImportDataPage (Tractic, WinTeam, Generic CSV import) and ReportsPage (export).
"""

import csv
import io
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QMessageBox, QFileDialog, QFormLayout,
    QGroupBox, QAbstractItemView, QScrollArea, QDateEdit, QTabWidget,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from src.config import (
    COLORS, ROLE_ADMIN, tc, _is_dark, btn_style,
    build_dialog_stylesheet, REPORTS_DIR, ensure_directories,
)
from src.modules.overtime import data_manager
from src import audit


# ════════════════════════════════════════════════════════════════════════
# Import Data Page
# ════════════════════════════════════════════════════════════════════════

class ImportDataPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._csv_text = ""
        self._parsed_rows = []
        self._import_source = "generic"
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
        title = QLabel("Import Labor Data")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        # Source tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {tc('border')};
                border-radius: 6px;
                background: {tc('card')};
                padding: 16px;
            }}
            QTabBar::tab {{
                background: {tc('bg')};
                color: {tc('text')};
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 600;
                border: 1px solid {tc('border')};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background: {tc('card')};
                color: {COLORS['info']};
                border-bottom: 2px solid {COLORS['info']};
            }}
        """)

        # Tractic tab
        tractic_tab = self._make_import_tab(
            "Tractic Export",
            "Expected columns: Employee ID, Employee Name, Site, Week Ending, "
            "Regular Hours, OT Hours, DT Hours, Regular Rate, OT Rate",
            "tractic",
        )
        self.tabs.addTab(tractic_tab, "Tractic")

        # WinTeam tab
        winteam_tab = self._make_import_tab(
            "WinTeam Export",
            "Expected columns: EmpID, Name, Location, WeekEnd, RegHrs, OTHrs, DTHrs, PayRate",
            "winteam",
        )
        self.tabs.addTab(winteam_tab, "WinTeam")

        # Generic CSV tab
        generic_tab = self._make_import_tab(
            "Generic CSV",
            "Expected columns: officer_id, officer_name, site, week_ending, "
            "regular_hours, overtime_hours, double_time_hours, regular_rate, overtime_rate",
            "generic",
        )
        self.tabs.addTab(generic_tab, "Generic CSV")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)

        # Column mapping display
        mapping_group = QGroupBox("Column Mapping")
        mapping_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        map_lay = QVBoxLayout(mapping_group)
        self.mapping_label = QLabel("")
        self.mapping_label.setWordWrap(True)
        self.mapping_label.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        map_lay.addWidget(self.mapping_label)
        layout.addWidget(mapping_group)

        # Preview table
        preview_group = QGroupBox("Preview (First 20 Rows)")
        preview_group.setStyleSheet(mapping_group.styleSheet())
        preview_lay = QVBoxLayout(preview_group)

        self.preview_table = QTableWidget(0, 8)
        self.preview_table.setHorizontalHeaderLabels([
            "Officer ID", "Name", "Site", "Week Ending",
            "Regular Hrs", "OT Hrs", "DT Hrs", "Source"
        ])
        p_hdr = self.preview_table.horizontalHeader()
        for c in range(8):
            p_hdr.setSectionResizeMode(c, QHeaderView.Stretch if c in [1, 2] else QHeaderView.Fixed)
        self.preview_table.setColumnWidth(0, 90)
        self.preview_table.setColumnWidth(3, 100)
        self.preview_table.setColumnWidth(4, 90)
        self.preview_table.setColumnWidth(5, 80)
        self.preview_table.setColumnWidth(6, 80)
        self.preview_table.setColumnWidth(7, 80)
        p_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 13px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setShowGrid(False)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setMaximumHeight(350)
        preview_lay.addWidget(self.preview_table)
        layout.addWidget(preview_group)

        # Import button + results
        import_row = QHBoxLayout()
        self.btn_import = QPushButton("Import Data")
        self.btn_import.setCursor(Qt.PointingHandCursor)
        self.btn_import.setFixedHeight(42)
        self.btn_import.setFixedWidth(180)
        self.btn_import.setStyleSheet(btn_style(COLORS["success"], "white"))
        self.btn_import.clicked.connect(self._do_import)
        self.btn_import.setEnabled(False)
        import_row.addWidget(self.btn_import)

        self.lbl_result = QLabel("")
        self.lbl_result.setStyleSheet(f"color: {tc('text')}; font-size: 14px; font-weight: 600;")
        import_row.addWidget(self.lbl_result)
        import_row.addStretch()
        layout.addLayout(import_row)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._update_mapping_label()

    def _make_import_tab(self, title_text: str, help_text: str, source: str) -> QWidget:
        """Create an import source tab with file picker and help text."""
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setSpacing(12)

        desc = QLabel(help_text)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        lay.addWidget(desc)

        file_row = QHBoxLayout()
        btn_file = QPushButton("Select CSV File")
        btn_file.setCursor(Qt.PointingHandCursor)
        btn_file.setFixedHeight(38)
        btn_file.setStyleSheet(btn_style(tc("info"), "white"))
        btn_file.clicked.connect(lambda: self._select_file(source))
        file_row.addWidget(btn_file)

        self._file_label = QLabel("No file selected")
        self._file_label.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        file_row.addWidget(self._file_label)
        file_row.addStretch()
        lay.addLayout(file_row)

        return tab

    def _on_tab_changed(self, index):
        sources = ["tractic", "winteam", "generic"]
        if 0 <= index < len(sources):
            self._import_source = sources[index]
        self._update_mapping_label()

    def _update_mapping_label(self):
        mappings = {
            "tractic": (
                "Tractic Mapping: Employee ID -> officer_id, Employee Name -> officer_name, "
                "Site -> site, Week Ending -> week_ending, Regular Hours -> regular_hours, "
                "OT Hours -> overtime_hours, DT Hours -> double_time_hours, "
                "Regular Rate -> regular_rate, OT Rate -> overtime_rate"
            ),
            "winteam": (
                "WinTeam Mapping: EmpID -> officer_id, Name -> officer_name, "
                "Location -> site, WeekEnd -> week_ending, RegHrs -> regular_hours, "
                "OTHrs -> overtime_hours, DTHrs -> double_time_hours, PayRate -> regular_rate"
            ),
            "generic": (
                "Generic Mapping: Columns map directly by name: officer_id, officer_name, "
                "site, week_ending, regular_hours, overtime_hours, double_time_hours, "
                "regular_rate, overtime_rate"
            ),
        }
        self.mapping_label.setText(mappings.get(self._import_source, ""))

    def _select_file(self, source: str):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                self._csv_text = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read file: {e}")
            return

        self._file_label.setText(os.path.basename(path))
        self._import_source = source
        self._preview_data()

    def _preview_data(self):
        """Parse CSV and show preview."""
        if not self._csv_text:
            return

        try:
            reader = csv.DictReader(io.StringIO(self._csv_text))
            rows = list(reader)
        except Exception as e:
            QMessageBox.critical(self, "Parse Error", f"Failed to parse CSV: {e}")
            return

        self._parsed_rows = rows
        preview = rows[:20]

        # Map columns based on source
        self.preview_table.setRowCount(len(preview))
        for i, row in enumerate(preview):
            if self._import_source == "tractic":
                vals = [
                    row.get("Employee ID", ""), row.get("Employee Name", ""),
                    row.get("Site", ""), row.get("Week Ending", ""),
                    row.get("Regular Hours", ""), row.get("OT Hours", ""),
                    row.get("DT Hours", ""), "tractic",
                ]
            elif self._import_source == "winteam":
                vals = [
                    row.get("EmpID", ""), row.get("Name", ""),
                    row.get("Location", ""), row.get("WeekEnd", ""),
                    row.get("RegHrs", ""), row.get("OTHrs", ""),
                    row.get("DTHrs", ""), "winteam",
                ]
            else:
                vals = [
                    row.get("officer_id", ""), row.get("officer_name", ""),
                    row.get("site", ""), row.get("week_ending", ""),
                    row.get("regular_hours", ""), row.get("overtime_hours", ""),
                    row.get("double_time_hours", ""), "generic",
                ]

            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if c >= 4:
                    item.setTextAlignment(Qt.AlignCenter)
                self.preview_table.setItem(i, c, item)
            self.preview_table.setRowHeight(i, 36)

        self.btn_import.setEnabled(True)
        self.lbl_result.setText(f"{len(rows)} rows found in file")

    def _do_import(self):
        if not self._csv_text:
            return

        reply = QMessageBox.question(
            self, "Confirm Import",
            f"Import {len(self._parsed_rows)} rows from {self._import_source} source?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        importers = {
            "tractic": data_manager.import_tractic_csv,
            "winteam": data_manager.import_winteam_csv,
            "generic": data_manager.import_generic_csv,
        }

        importer = importers.get(self._import_source, data_manager.import_generic_csv)
        result = importer(self._csv_text, created_by=self._get_username())

        imported = result.get("imported", 0)
        skipped = result.get("skipped", 0)
        errors = result.get("errors", [])

        msg = f"Imported: {imported} | Skipped: {skipped} | Errors: {len(errors)}"
        self.lbl_result.setText(msg)

        if errors:
            error_text = "\n".join(errors[:10])
            if len(errors) > 10:
                error_text += f"\n... and {len(errors) - 10} more errors"
            QMessageBox.warning(self, "Import Errors", error_text)

        audit.log_event("overtime", "data_imported", self._get_username(),
                         f"Source: {self._import_source}, Imported: {imported}, "
                         f"Skipped: {skipped}, Errors: {len(errors)}")

        # Reset
        self._csv_text = ""
        self._parsed_rows = []
        self.btn_import.setEnabled(False)

    def refresh(self):
        pass


# ════════════════════════════════════════════════════════════════════════
# Reports & Export Page
# ════════════════════════════════════════════════════════════════════════

class ReportsPage(QWidget):
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
        layout.setSpacing(20)

        # Header
        title = QLabel("Reports & Export")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        # Date range filters
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)

        lbl_from = QLabel("From:")
        lbl_from.setStyleSheet(f"color: {tc('text')}; font-weight: 600;")
        filter_row.addWidget(lbl_from)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-56))
        self.date_from.setFixedHeight(38)
        filter_row.addWidget(self.date_from)

        lbl_to = QLabel("To:")
        lbl_to.setStyleSheet(f"color: {tc('text')}; font-weight: 600;")
        filter_row.addWidget(lbl_to)
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setFixedHeight(38)
        filter_row.addWidget(self.date_to)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Export buttons row
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

        # Full Labor Export
        labor_group = QGroupBox("Full Labor Export")
        labor_group.setStyleSheet(group_style)
        labor_lay = QVBoxLayout(labor_group)
        labor_desc = QLabel("Export all labor entries for the selected date range.")
        labor_desc.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        labor_lay.addWidget(labor_desc)

        self.labor_preview = QTableWidget(0, 7)
        self.labor_preview.setHorizontalHeaderLabels([
            "Officer", "Site", "Week", "Regular", "OT", "Total", "Pay"
        ])
        self._setup_preview_table(self.labor_preview)
        labor_lay.addWidget(self.labor_preview)

        btn_labor = QPushButton("Export Full Labor CSV")
        btn_labor.setCursor(Qt.PointingHandCursor)
        btn_labor.setFixedHeight(38)
        btn_labor.setStyleSheet(btn_style(COLORS["info"], "white"))
        btn_labor.clicked.connect(lambda: self._export_report("labor"))
        labor_lay.addWidget(btn_labor)
        layout.addWidget(labor_group)

        # OT Summary
        ot_group = QGroupBox("Overtime Summary")
        ot_group.setStyleSheet(group_style)
        ot_lay = QVBoxLayout(ot_group)
        ot_desc = QLabel("Summary of overtime hours and costs by officer.")
        ot_desc.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        ot_lay.addWidget(ot_desc)

        self.ot_preview = QTableWidget(0, 5)
        self.ot_preview.setHorizontalHeaderLabels([
            "Officer", "Site", "Total OT Hrs", "OT Cost", "Weeks"
        ])
        self._setup_preview_table(self.ot_preview)
        ot_lay.addWidget(self.ot_preview)

        btn_ot = QPushButton("Export OT Summary CSV")
        btn_ot.setCursor(Qt.PointingHandCursor)
        btn_ot.setFixedHeight(38)
        btn_ot.setStyleSheet(btn_style(COLORS["warning"], "white"))
        btn_ot.clicked.connect(lambda: self._export_report("ot_summary"))
        ot_lay.addWidget(btn_ot)
        layout.addWidget(ot_group)

        # Site Summary
        site_group = QGroupBox("Site Summary")
        site_group.setStyleSheet(group_style)
        site_lay = QVBoxLayout(site_group)
        site_desc = QLabel("Aggregate hours and costs by site.")
        site_desc.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        site_lay.addWidget(site_desc)

        self.site_preview = QTableWidget(0, 5)
        self.site_preview.setHorizontalHeaderLabels([
            "Site", "Total Hours", "OT Hours", "Total Pay", "Officers"
        ])
        self._setup_preview_table(self.site_preview)
        site_lay.addWidget(self.site_preview)

        btn_site = QPushButton("Export Site Summary CSV")
        btn_site.setCursor(Qt.PointingHandCursor)
        btn_site.setFixedHeight(38)
        btn_site.setStyleSheet(btn_style(COLORS["success"], "white"))
        btn_site.clicked.connect(lambda: self._export_report("site_summary"))
        site_lay.addWidget(btn_site)
        layout.addWidget(site_group)

        # DLS Report
        dls_group = QGroupBox("DLS Report")
        dls_group.setStyleSheet(group_style)
        dls_lay = QVBoxLayout(dls_group)
        dls_desc = QLabel("Direct labor spend percentage by site.")
        dls_desc.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        dls_lay.addWidget(dls_desc)

        self.dls_preview = QTableWidget(0, 4)
        self.dls_preview.setHorizontalHeaderLabels([
            "Site", "Total Pay", "Avg DLS %", "Weeks"
        ])
        self._setup_preview_table(self.dls_preview)
        dls_lay.addWidget(self.dls_preview)

        btn_dls = QPushButton("Export DLS Report CSV")
        btn_dls.setCursor(Qt.PointingHandCursor)
        btn_dls.setFixedHeight(38)
        btn_dls.setStyleSheet(btn_style(tc("accent"), "white"))
        btn_dls.clicked.connect(lambda: self._export_report("dls"))
        dls_lay.addWidget(btn_dls)
        layout.addWidget(dls_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _setup_preview_table(self, table: QTableWidget):
        """Apply common styling to preview tables."""
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 13px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setMaximumHeight(200)

    def _get_entries_in_range(self) -> list:
        """Get all entries within the selected date range."""
        d_from = self.date_from.date().toString("yyyy-MM-dd")
        d_to = self.date_to.date().toString("yyyy-MM-dd")

        all_entries = data_manager.get_all_entries()
        return [
            e for e in all_entries
            if d_from <= e.get("week_ending", "") <= d_to
        ]

    def _export_report(self, report_type: str):
        ensure_directories()
        entries = self._get_entries_in_range()
        if not entries:
            QMessageBox.information(self, "No Data", "No data in the selected date range.")
            return

        d_from = self.date_from.date().toString("yyyy-MM-dd")
        d_to = self.date_to.date().toString("yyyy-MM-dd")

        try:
            if report_type == "labor":
                path = os.path.join(REPORTS_DIR, f"labor_export_{d_from}_to_{d_to}.csv")
                csv_text = data_manager.export_labor_csv()
                if csv_text:
                    with open(path, "w", newline="") as f:
                        f.write(csv_text)

            elif report_type == "ot_summary":
                path = os.path.join(REPORTS_DIR, f"ot_summary_{d_from}_to_{d_to}.csv")
                rows = self._build_ot_summary(entries)
                self._write_csv(path, rows)

            elif report_type == "site_summary":
                path = os.path.join(REPORTS_DIR, f"site_summary_{d_from}_to_{d_to}.csv")
                rows = self._build_site_summary(entries)
                self._write_csv(path, rows)

            elif report_type == "dls":
                path = os.path.join(REPORTS_DIR, f"dls_report_{d_from}_to_{d_to}.csv")
                rows = self._build_dls_report(entries)
                self._write_csv(path, rows)
            else:
                return

            QMessageBox.information(self, "Exported", f"Report saved to:\n{path}")
            audit.log_event("overtime", f"{report_type}_exported",
                             self._get_username(), f"Range: {d_from} to {d_to}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def _write_csv(self, path: str, rows: list):
        if not rows:
            return
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def _build_ot_summary(self, entries: list) -> list:
        """Build OT summary report data."""
        officer_data = {}
        for e in entries:
            key = e.get("officer_id") or e.get("officer_name", "")
            if key not in officer_data:
                officer_data[key] = {
                    "officer_name": e.get("officer_name", ""),
                    "site": e.get("site", ""),
                    "total_ot_hours": 0,
                    "ot_cost": 0,
                    "weeks": set(),
                }
            officer_data[key]["total_ot_hours"] += e.get("overtime_hours", 0) + e.get("double_time_hours", 0)
            officer_data[key]["ot_cost"] += e.get("overtime_pay", 0)
            officer_data[key]["weeks"].add(e.get("week_ending", ""))

        result = []
        for o in sorted(officer_data.values(), key=lambda x: -x["total_ot_hours"]):
            if o["total_ot_hours"] > 0:
                result.append({
                    "officer_name": o["officer_name"],
                    "site": o["site"],
                    "total_ot_hours": round(o["total_ot_hours"], 2),
                    "ot_cost": round(o["ot_cost"], 2),
                    "weeks": len(o["weeks"]),
                })
        return result

    def _build_site_summary(self, entries: list) -> list:
        """Build site summary report data."""
        site_data = {}
        for e in entries:
            s = e.get("site", "Unknown")
            if s not in site_data:
                site_data[s] = {
                    "site": s,
                    "total_hours": 0,
                    "ot_hours": 0,
                    "total_pay": 0,
                    "officers": set(),
                }
            site_data[s]["total_hours"] += e.get("total_hours", 0)
            site_data[s]["ot_hours"] += e.get("overtime_hours", 0) + e.get("double_time_hours", 0)
            site_data[s]["total_pay"] += e.get("total_pay", 0)
            site_data[s]["officers"].add(e.get("officer_name", ""))

        result = []
        for s in sorted(site_data.values(), key=lambda x: -x["total_hours"]):
            result.append({
                "site": s["site"],
                "total_hours": round(s["total_hours"], 2),
                "ot_hours": round(s["ot_hours"], 2),
                "total_pay": round(s["total_pay"], 2),
                "officers": len(s["officers"]),
            })
        return result

    def _build_dls_report(self, entries: list) -> list:
        """Build DLS report data."""
        site_data = {}
        for e in entries:
            s = e.get("site", "Unknown")
            if s not in site_data:
                site_data[s] = {
                    "site": s,
                    "total_pay": 0,
                    "dls_total": 0,
                    "entry_count": 0,
                    "weeks": set(),
                }
            site_data[s]["total_pay"] += e.get("total_pay", 0)
            site_data[s]["dls_total"] += e.get("dls_percentage", 0)
            site_data[s]["entry_count"] += 1
            site_data[s]["weeks"].add(e.get("week_ending", ""))

        result = []
        for s in sorted(site_data.values(), key=lambda x: x["site"]):
            avg_dls = s["dls_total"] / s["entry_count"] if s["entry_count"] > 0 else 0
            result.append({
                "site": s["site"],
                "total_pay": round(s["total_pay"], 2),
                "avg_dls_percentage": round(avg_dls, 1),
                "weeks": len(s["weeks"]),
            })
        return result

    def _populate_previews(self):
        """Populate preview tables with current data."""
        entries = self._get_entries_in_range()

        # Labor preview (first 10)
        preview = entries[:10]
        self.labor_preview.setRowCount(len(preview))
        for i, e in enumerate(preview):
            self.labor_preview.setItem(i, 0, QTableWidgetItem(e.get("officer_name", "")))
            self.labor_preview.setItem(i, 1, QTableWidgetItem(e.get("site", "")))
            self.labor_preview.setItem(i, 2, QTableWidgetItem(e.get("week_ending", "")))

            for c, key in [(3, "regular_hours"), (4, "overtime_hours"),
                           (5, "total_hours")]:
                item = QTableWidgetItem(f"{e.get(key, 0):.1f}")
                item.setTextAlignment(Qt.AlignCenter)
                self.labor_preview.setItem(i, c, item)

            pay_item = QTableWidgetItem(f"${e.get('total_pay', 0):,.0f}")
            pay_item.setTextAlignment(Qt.AlignCenter)
            self.labor_preview.setItem(i, 6, pay_item)
            self.labor_preview.setRowHeight(i, 36)

        # OT summary preview
        ot_data = self._build_ot_summary(entries)[:10]
        self.ot_preview.setRowCount(len(ot_data))
        for i, o in enumerate(ot_data):
            self.ot_preview.setItem(i, 0, QTableWidgetItem(o["officer_name"]))
            self.ot_preview.setItem(i, 1, QTableWidgetItem(o["site"]))

            ot_item = QTableWidgetItem(f"{o['total_ot_hours']:.1f}")
            ot_item.setTextAlignment(Qt.AlignCenter)
            self.ot_preview.setItem(i, 2, ot_item)

            cost_item = QTableWidgetItem(f"${o['ot_cost']:,.0f}")
            cost_item.setTextAlignment(Qt.AlignCenter)
            self.ot_preview.setItem(i, 3, cost_item)

            wk_item = QTableWidgetItem(str(o["weeks"]))
            wk_item.setTextAlignment(Qt.AlignCenter)
            self.ot_preview.setItem(i, 4, wk_item)
            self.ot_preview.setRowHeight(i, 36)

        # Site summary preview
        site_data = self._build_site_summary(entries)[:10]
        self.site_preview.setRowCount(len(site_data))
        for i, s in enumerate(site_data):
            self.site_preview.setItem(i, 0, QTableWidgetItem(s["site"]))

            hrs_item = QTableWidgetItem(f"{s['total_hours']:.1f}")
            hrs_item.setTextAlignment(Qt.AlignCenter)
            self.site_preview.setItem(i, 1, hrs_item)

            ot_item = QTableWidgetItem(f"{s['ot_hours']:.1f}")
            ot_item.setTextAlignment(Qt.AlignCenter)
            self.site_preview.setItem(i, 2, ot_item)

            pay_item = QTableWidgetItem(f"${s['total_pay']:,.0f}")
            pay_item.setTextAlignment(Qt.AlignCenter)
            self.site_preview.setItem(i, 3, pay_item)

            off_item = QTableWidgetItem(str(s["officers"]))
            off_item.setTextAlignment(Qt.AlignCenter)
            self.site_preview.setItem(i, 4, off_item)
            self.site_preview.setRowHeight(i, 36)

        # DLS preview
        dls_data = self._build_dls_report(entries)[:10]
        self.dls_preview.setRowCount(len(dls_data))
        for i, d in enumerate(dls_data):
            self.dls_preview.setItem(i, 0, QTableWidgetItem(d["site"]))

            pay_item = QTableWidgetItem(f"${d['total_pay']:,.0f}")
            pay_item.setTextAlignment(Qt.AlignCenter)
            self.dls_preview.setItem(i, 1, pay_item)

            dls_item = QTableWidgetItem(f"{d['avg_dls_percentage']:.1f}%")
            dls_item.setTextAlignment(Qt.AlignCenter)
            dls_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.dls_preview.setItem(i, 2, dls_item)

            wk_item = QTableWidgetItem(str(d["weeks"]))
            wk_item.setTextAlignment(Qt.AlignCenter)
            self.dls_preview.setItem(i, 3, wk_item)
            self.dls_preview.setRowHeight(i, 36)

    def refresh(self):
        self._populate_previews()
