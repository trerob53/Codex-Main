"""
Cerasus Hub -- Incidents Module: Admin Pages
ReportsPage (export, type breakdown, site summary) and SettingsPage (incident type/severity management).
"""

import csv
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QMessageBox, QFileDialog, QFormLayout,
    QGroupBox, QAbstractItemView, QDialog, QDialogButtonBox,
    QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import (
    COLORS, ROLE_ADMIN, tc, _is_dark, btn_style,
    build_dialog_stylesheet, REPORTS_DIR, ensure_directories,
)
from src.shared_widgets import BarChartWidget
from src.modules.incidents import data_manager
from src import audit


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
        header_row = QHBoxLayout()
        title = QLabel("Reports & Export")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        header_row.addWidget(title)
        header_row.addStretch()

        btn_export = QPushButton("Export All Incidents CSV")
        btn_export.setCursor(Qt.PointingHandCursor)
        btn_export.setFixedHeight(38)
        btn_export.setStyleSheet(btn_style(tc("info"), "white"))
        btn_export.clicked.connect(self._export_csv)
        header_row.addWidget(btn_export)
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

        # ── Incident Type Breakdown ───────────────────────────────────
        type_group = QGroupBox("Incident Type Breakdown")
        type_group.setStyleSheet(group_style)
        type_lay = QVBoxLayout(type_group)

        self.type_chart = BarChartWidget()
        type_lay.addWidget(self.type_chart)

        self.type_table = QTableWidget(0, 3)
        self.type_table.setHorizontalHeaderLabels(["Type", "Count", "% of Total"])
        t_hdr = self.type_table.horizontalHeader()
        t_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        t_hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        t_hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        self.type_table.setColumnWidth(1, 100)
        self.type_table.setColumnWidth(2, 120)
        t_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.type_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.type_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.type_table.verticalHeader().setVisible(False)
        self.type_table.setShowGrid(False)
        self.type_table.setAlternatingRowColors(True)
        self.type_table.setMaximumHeight(320)
        type_lay.addWidget(self.type_table)
        layout.addWidget(type_group)

        # ── Site Summary ──────────────────────────────────────────────
        site_group = QGroupBox("Site Summary")
        site_group.setStyleSheet(group_style)
        site_lay = QVBoxLayout(site_group)

        self.site_chart = BarChartWidget()
        site_lay.addWidget(self.site_chart)

        self.site_table = QTableWidget(0, 4)
        self.site_table.setHorizontalHeaderLabels(["Site", "Total", "Open", "Critical"])
        s_hdr = self.site_table.horizontalHeader()
        s_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in [1, 2, 3]:
            s_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
        self.site_table.setColumnWidth(1, 80)
        self.site_table.setColumnWidth(2, 80)
        self.site_table.setColumnWidth(3, 80)
        s_hdr.setStyleSheet(t_hdr.styleSheet())
        self.site_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.site_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.site_table.verticalHeader().setVisible(False)
        self.site_table.setShowGrid(False)
        self.site_table.setAlternatingRowColors(True)
        self.site_table.setMaximumHeight(320)
        site_lay.addWidget(self.site_table)
        layout.addWidget(site_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _export_csv(self):
        ensure_directories()
        csv_text = data_manager.export_incidents_csv()
        if not csv_text:
            QMessageBox.information(self, "No Data", "No incidents to export.")
            return
        path = os.path.join(REPORTS_DIR, "incidents_full_export.csv")
        try:
            with open(path, "w", newline="") as f:
                f.write(csv_text)
            QMessageBox.information(self, "Exported", f"Incidents exported to:\n{path}")
            audit.log_event("incidents", "report_exported", self._get_username(),
                            f"Path: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def refresh(self):
        summary = data_manager.get_dashboard_summary()
        total = summary["total"] or 1  # avoid div by zero

        # Type breakdown
        type_counts = summary["type_counts"]
        sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])

        chart_data = [(t[:16], c, tc("info")) for t, c in sorted_types[:10]]
        self.type_chart.set_data(chart_data)

        self.type_table.setRowCount(len(sorted_types))
        for i, (t, c) in enumerate(sorted_types):
            self.type_table.setItem(i, 0, QTableWidgetItem(t))
            cnt_item = QTableWidgetItem(str(c))
            cnt_item.setTextAlignment(Qt.AlignCenter)
            cnt_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.type_table.setItem(i, 1, cnt_item)

            pct = (c / total * 100) if total > 0 else 0
            pct_item = QTableWidgetItem(f"{pct:.1f}%")
            pct_item.setTextAlignment(Qt.AlignCenter)
            self.type_table.setItem(i, 2, pct_item)

        # Site summary - need more detail per site
        all_incidents = data_manager.get_all_incidents()
        site_stats = {}
        for inc in all_incidents:
            site = inc.get("site", "") or "(No Site)"
            if site not in site_stats:
                site_stats[site] = {"total": 0, "open": 0, "critical": 0}
            site_stats[site]["total"] += 1
            if inc.get("status") in ("Open", "Under Investigation"):
                site_stats[site]["open"] += 1
            if inc.get("severity") == "Critical":
                site_stats[site]["critical"] += 1

        sorted_sites = sorted(site_stats.items(), key=lambda x: -x[1]["total"])

        site_chart_data = [(s[:16], d["total"], tc("accent")) for s, d in sorted_sites[:10]]
        self.site_chart.set_data(site_chart_data)

        self.site_table.setRowCount(len(sorted_sites))
        for i, (site, stats) in enumerate(sorted_sites):
            self.site_table.setItem(i, 0, QTableWidgetItem(site))

            total_item = QTableWidgetItem(str(stats["total"]))
            total_item.setTextAlignment(Qt.AlignCenter)
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.site_table.setItem(i, 1, total_item)

            open_item = QTableWidgetItem(str(stats["open"]))
            open_item.setTextAlignment(Qt.AlignCenter)
            if stats["open"] > 0:
                open_item.setForeground(QColor(tc("warning")))
                open_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.site_table.setItem(i, 2, open_item)

            crit_item = QTableWidgetItem(str(stats["critical"]))
            crit_item.setTextAlignment(Qt.AlignCenter)
            if stats["critical"] > 0:
                crit_item.setForeground(QColor(tc("danger")))
                crit_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.site_table.setItem(i, 3, crit_item)


# ════════════════════════════════════════════════════════════════════════
# Settings Page (Admin only)
# ════════════════════════════════════════════════════════════════════════

class SettingsPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

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
        header = QLabel("Incident Settings")
        header.setFont(QFont("Segoe UI", 22, QFont.Bold))
        header.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(header)

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

        # ── Incident Types ────────────────────────────────────────────
        types_group = QGroupBox("Incident Types")
        types_group.setStyleSheet(group_style)
        types_lay = QVBoxLayout(types_group)
        types_lay.setSpacing(10)

        info_lbl = QLabel(
            "These are the available incident types used when filing reports. "
            "Types are defined in code and can be customized in future versions."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; border: none;")
        types_lay.addWidget(info_lbl)

        self.types_table = QTableWidget(0, 2)
        self.types_table.setHorizontalHeaderLabels(["Type", "Status"])
        ty_hdr = self.types_table.horizontalHeader()
        ty_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        ty_hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        self.types_table.setColumnWidth(1, 100)
        ty_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.types_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.types_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.types_table.verticalHeader().setVisible(False)
        self.types_table.setShowGrid(False)
        self.types_table.setAlternatingRowColors(True)
        self.types_table.setMaximumHeight(320)
        types_lay.addWidget(self.types_table)
        layout.addWidget(types_group)

        # ── Severity Definitions ──────────────────────────────────────
        sev_group = QGroupBox("Severity Definitions")
        sev_group.setStyleSheet(group_style)
        sev_lay = QVBoxLayout(sev_group)
        sev_lay.setSpacing(10)

        severity_defs = {
            "Low": "Minor incidents with no injuries, minimal disruption, and no property damage.",
            "Medium": "Incidents requiring attention but posing no immediate threat to safety.",
            "High": "Significant incidents involving potential injury, property damage, or security breach.",
            "Critical": "Severe incidents requiring immediate response: active threats, serious injury, major damage.",
        }

        sev_colors = {
            "Low": "#059669",
            "Medium": "#D97706",
            "High": "#EA580C",
            "Critical": "#DC2626",
        }

        for sev, desc in severity_defs.items():
            row_frame = QFrame()
            row_frame.setStyleSheet(f"""
                QFrame {{
                    background: {tc('card')};
                    border: 1px solid {tc('border')};
                    border-left: 5px solid {sev_colors[sev]};
                    border-radius: 6px;
                    padding: 10px;
                }}
            """)
            row_lay = QVBoxLayout(row_frame)
            row_lay.setContentsMargins(12, 8, 12, 8)
            row_lay.setSpacing(4)

            sev_lbl = QLabel(sev)
            sev_lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
            sev_lbl.setStyleSheet(f"color: {sev_colors[sev]}; border: none;")
            row_lay.addWidget(sev_lbl)

            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; border: none;")
            row_lay.addWidget(desc_lbl)

            sev_lay.addWidget(row_frame)

        layout.addWidget(sev_group)

        # ── Status Workflow ───────────────────────────────────────────
        status_group = QGroupBox("Status Workflow")
        status_group.setStyleSheet(group_style)
        status_lay = QVBoxLayout(status_group)

        workflow_lbl = QLabel(
            "Open  \u2192  Under Investigation  \u2192  Resolved  \u2192  Closed\n\n"
            "New incidents start as 'Open'. Officers can start investigations, "
            "resolve incidents with notes, and close them when fully handled."
        )
        workflow_lbl.setWordWrap(True)
        workflow_lbl.setStyleSheet(f"color: {tc('text')}; font-size: 14px; border: none; padding: 8px;")
        status_lay.addWidget(workflow_lbl)
        layout.addWidget(status_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self):
        # Populate types table
        types = data_manager.INCIDENT_TYPES
        self.types_table.setRowCount(len(types))
        for i, t in enumerate(types):
            self.types_table.setItem(i, 0, QTableWidgetItem(t))
            status_item = QTableWidgetItem("Active")
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QColor(tc("success")))
            status_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.types_table.setItem(i, 1, status_item)
