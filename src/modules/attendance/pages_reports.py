"""
Cerasus Hub -- Attendance Module: Reports & Export Page
CSV exports and site summary table.
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QGroupBox, QMessageBox, QFileDialog,
    QComboBox, QScrollArea, QStackedWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, REPORTS_DIR, ensure_directories, tc, _is_dark, btn_style
from src.modules.attendance import data_manager
from src import audit


class ReportsPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _group_style(self):
        return f"""
            QGroupBox {{
                font-weight: 600; font-size: 14px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 20px; background: {tc('card')};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 6px; }}
        """

    def _header_style(self):
        return f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 14px; padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """

    def _make_table(self, columns, headers):
        table = QTableWidget(0, columns)
        table.setHorizontalHeaderLabels(headers)
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, columns):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(self._header_style())
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        return table

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # Header
        title = QLabel("Reports & Export")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        # ── Export buttons
        export_group = QGroupBox("Export Data")
        export_group.setStyleSheet(self._group_style())
        export_lay = QHBoxLayout(export_group)
        export_lay.setSpacing(12)

        btn_discipline = QPushButton("Discipline Summary CSV")
        btn_discipline.setStyleSheet(btn_style(COLORS['info']))
        btn_discipline.setFixedHeight(40)
        btn_discipline.clicked.connect(self._export_discipline)
        export_lay.addWidget(btn_discipline)

        btn_infractions = QPushButton("Infraction History CSV")
        btn_infractions.setStyleSheet(btn_style(COLORS['warning']))
        btn_infractions.setFixedHeight(40)
        btn_infractions.clicked.connect(self._export_infractions)
        export_lay.addWidget(btn_infractions)

        btn_reviews = QPushButton("Employment Reviews CSV")
        btn_reviews.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        btn_reviews.setFixedHeight(40)
        btn_reviews.clicked.connect(self._export_reviews)
        export_lay.addWidget(btn_reviews)

        btn_pdf = QPushButton("Export PDF Summary")
        btn_pdf.setStyleSheet(btn_style(COLORS['primary_light'], hover_bg=COLORS['primary_mid']))
        btn_pdf.setFixedHeight(40)
        btn_pdf.clicked.connect(self._export_pdf)
        export_lay.addWidget(btn_pdf)

        export_lay.addStretch()
        layout.addWidget(export_group)

        # ── Report Type Selector
        selector_row = QHBoxLayout()
        selector_row.setSpacing(12)
        lbl = QLabel("Report:")
        lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl.setStyleSheet(f"color: {tc('text')};")
        selector_row.addWidget(lbl)

        self.report_combo = QComboBox()
        self.report_combo.addItems([
            "Site Summary",
            "Officer Summary (Top 10)",
            "Monthly Trend (12 Months)",
        ])
        self.report_combo.setFixedHeight(36)
        self.report_combo.setMinimumWidth(280)
        self.report_combo.currentIndexChanged.connect(self._on_report_changed)
        selector_row.addWidget(self.report_combo)
        selector_row.addStretch()
        layout.addLayout(selector_row)

        # ── Stacked report views
        self.report_stack = QStackedWidget()

        # Page 0: Site Summary
        site_page = QWidget()
        site_lay = QVBoxLayout(site_page)
        site_lay.setContentsMargins(0, 0, 0, 0)

        self.site_table = self._make_table(5, [
            "Site", "Infraction Count", "Total Active Points", "Officer Count", "Risk Level"
        ])
        site_lay.addWidget(self.site_table)
        self.report_stack.addWidget(site_page)

        # Page 1: Officer Summary
        officer_page = QWidget()
        officer_lay = QVBoxLayout(officer_page)
        officer_lay.setContentsMargins(0, 0, 0, 0)

        self.officer_table = self._make_table(4, [
            "Officer", "Site", "Active Points", "Discipline Level"
        ])
        officer_lay.addWidget(self.officer_table)

        # Discipline level distribution sub-table
        dist_label = QLabel("Discipline Level Distribution")
        dist_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        dist_label.setStyleSheet(f"color: {tc('text')}; padding-top: 12px;")
        officer_lay.addWidget(dist_label)

        self.dist_table = self._make_table(2, ["Discipline Level", "Count"])
        self.dist_table.setMaximumHeight(200)
        officer_lay.addWidget(self.dist_table)
        self.report_stack.addWidget(officer_page)

        # Page 2: Monthly Trend
        trend_page = QWidget()
        trend_lay = QVBoxLayout(trend_page)
        trend_lay.setContentsMargins(0, 0, 0, 0)

        self.trend_table = self._make_table(2, ["Month", "Infractions"])
        trend_lay.addWidget(self.trend_table)
        self.report_stack.addWidget(trend_page)

        report_group = QGroupBox("Report Data")
        report_group.setStyleSheet(self._group_style())
        rg_lay = QVBoxLayout(report_group)
        rg_lay.addWidget(self.report_stack)
        layout.addWidget(report_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _on_report_changed(self, index):
        self.report_stack.setCurrentIndex(index)
        self._load_current_report()

    def refresh(self):
        self._load_current_report()

    def _load_current_report(self):
        idx = self.report_combo.currentIndex()
        if idx == 0:
            self._load_site_summary()
        elif idx == 1:
            self._load_officer_summary()
        elif idx == 2:
            self._load_monthly_trend()

    def _load_site_summary(self):
        """Site summary report: infractions per site, total active points."""
        site_infr = data_manager.get_site_infraction_summary()
        site_att = data_manager.get_site_attendance_summary()

        # Merge: use infraction data as base, enrich with officer count from attendance
        att_map = {s.get("site", ""): s for s in site_att}
        rows = []
        for s in site_infr:
            site_name = s.get("site", "") or "Unassigned"
            att = att_map.get(site_name, {})
            rows.append({
                "site": site_name,
                "infraction_count": s.get("infraction_count", 0),
                "total_active_points": float(s.get("total_active_points", 0) or 0),
                "officer_count": att.get("officer_count", 0),
            })

        self.site_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.site_table.setItem(i, 0, QTableWidgetItem(r["site"]))

            cnt_item = QTableWidgetItem(str(r["infraction_count"]))
            cnt_item.setTextAlignment(Qt.AlignCenter)
            self.site_table.setItem(i, 1, cnt_item)

            pts_item = QTableWidgetItem(f"{r['total_active_points']:.1f}")
            pts_item.setTextAlignment(Qt.AlignCenter)
            self.site_table.setItem(i, 2, pts_item)

            off_item = QTableWidgetItem(str(r["officer_count"]))
            off_item.setTextAlignment(Qt.AlignCenter)
            self.site_table.setItem(i, 3, off_item)

            # Risk level
            oc = r["officer_count"]
            avg = r["total_active_points"] / oc if oc > 0 else 0
            if avg >= 6:
                risk, risk_color = "High", COLORS["danger"]
            elif avg >= 3:
                risk, risk_color = "Medium", COLORS["warning"]
            else:
                risk, risk_color = "Low", COLORS["success"]
            risk_item = QTableWidgetItem(risk)
            risk_item.setTextAlignment(Qt.AlignCenter)
            risk_item.setForeground(QColor(risk_color))
            risk_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.site_table.setItem(i, 4, risk_item)
            self.site_table.setRowHeight(i, 40)

    def _load_officer_summary(self):
        """Officer summary report: top 10 by points + discipline level distribution."""
        top = data_manager.get_officer_points_summary(limit=10)
        self.officer_table.setRowCount(len(top))
        for i, off in enumerate(top):
            self.officer_table.setItem(i, 0, QTableWidgetItem(off.get("name", "")))
            self.officer_table.setItem(i, 1, QTableWidgetItem(off.get("site", "")))

            pts_item = QTableWidgetItem(f"{float(off.get('active_points', 0)):.1f}")
            pts_item.setTextAlignment(Qt.AlignCenter)
            pts = float(off.get("active_points", 0))
            if pts >= 10:
                pts_item.setForeground(QColor(COLORS["danger"]))
            elif pts >= 6:
                pts_item.setForeground(QColor(COLORS["warning"]))
            self.officer_table.setItem(i, 2, pts_item)

            self.officer_table.setItem(i, 3, QTableWidgetItem(off.get("discipline_level", "")))
            self.officer_table.setRowHeight(i, 40)

        # Distribution
        dist = data_manager.get_discipline_level_distribution()
        self.dist_table.setRowCount(len(dist))
        for i, (level, count) in enumerate(dist):
            self.dist_table.setItem(i, 0, QTableWidgetItem(level))
            cnt_item = QTableWidgetItem(str(count))
            cnt_item.setTextAlignment(Qt.AlignCenter)
            self.dist_table.setItem(i, 1, cnt_item)
            self.dist_table.setRowHeight(i, 36)

    def _load_monthly_trend(self):
        """Monthly trend report: infractions by month for last 12 months."""
        data = data_manager.get_monthly_infraction_counts(12)
        self.trend_table.setRowCount(len(data))
        for i, (label, count) in enumerate(data):
            self.trend_table.setItem(i, 0, QTableWidgetItem(label))
            cnt_item = QTableWidgetItem(str(count))
            cnt_item.setTextAlignment(Qt.AlignCenter)
            self.trend_table.setItem(i, 1, cnt_item)
            self.trend_table.setRowHeight(i, 36)

    def _export_discipline(self):
        csv_text = data_manager.export_discipline_csv()
        self._save_csv(csv_text, "discipline_summary.csv", "Discipline Summary")

    def _export_infractions(self):
        csv_text = data_manager.export_infractions_csv()
        self._save_csv(csv_text, "infraction_history.csv", "Infraction History")

    def _export_reviews(self):
        csv_text = data_manager.export_reviews_csv()
        self._save_csv(csv_text, "employment_reviews.csv", "Employment Reviews")

    def _export_pdf(self):
        """Export attendance summary to PDF using PDFDocument."""
        try:
            from src.pdf_export import PDFDocument
            from datetime import datetime as dt

            summary = data_manager.get_dashboard_summary()
            site_data = data_manager.get_site_attendance_summary()

            ts = dt.now().strftime("%Y%m%d_%H%M%S")
            doc = PDFDocument(f"attendance_summary_{ts}.pdf", "Attendance Summary Report")
            doc.begin()

            # KPI cards
            doc.add_kpi_row([
                ("Active Officers", summary.get("active_officers", 0), "#0F1A2E"),
                ("At-Risk (5+ pts)", summary.get("at_risk", 0), "#D97706"),
                ("Pending Reviews", summary.get("pending_reviews", 0), "#2563EB"),
                ("Termination Eligible", summary.get("termination_eligible", 0), "#DC2626"),
            ])
            doc.add_spacing(8)

            # Site summary table
            if site_data:
                doc.add_section_title("Site Summary")
                headers = ["Site", "Officers", "Total Points", "Avg Points"]
                rows = []
                for s in site_data:
                    avg = s.get("avg_points", 0) or 0
                    rows.append([
                        s.get("site", ""),
                        str(s.get("officer_count", 0)),
                        f"{s.get('total_points', 0):.1f}",
                        f"{avg:.1f}",
                    ])
                doc.add_table(headers, rows)

            # Top at-risk officers
            top_risk = summary.get("top_at_risk", [])
            if top_risk:
                doc.add_section_title("Top At-Risk Officers")
                headers = ["Name", "Employee ID", "Site", "Points", "Discipline Level"]
                rows = []
                for o in top_risk:
                    rows.append([
                        o.get("name", ""),
                        o.get("employee_id", ""),
                        o.get("site", ""),
                        str(o.get("active_points", 0)),
                        o.get("discipline_level", ""),
                    ])
                doc.add_table(headers, rows)

            path = doc.finish()

            username = self.app_state.get("username", "")
            audit.log_event(
                "attendance", "pdf_export", username,
                details=f"Exported attendance summary PDF to {path}",
            )
            QMessageBox.information(self, "PDF Exported", f"Saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Failed to generate PDF:\n{exc}")

    def _save_csv(self, csv_text, default_name, title):
        if not csv_text:
            QMessageBox.information(self, title, "No data to export.")
            return

        ensure_directories()
        default_path = os.path.join(REPORTS_DIR, default_name)
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {title}", default_path, "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                f.write(csv_text)

            username = self.app_state.get("username", "")
            audit.log_event(
                "attendance", "csv_export", username,
                details=f"Exported {title} to {path}",
            )
            QMessageBox.information(self, "Export Complete", f"{title} saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Failed to save file:\n{exc}")
