"""
Cerasus Hub -- DLS & Overtime Module: Analysis Pages
WeeklySummaryPage, BySitePage, ByOfficerPage, OvertimeAlertsPage.
"""

import csv
import io
import os
from datetime import date, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QMessageBox, QFileDialog,
    QGroupBox, QAbstractItemView, QScrollArea, QDateEdit,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from src.config import (
    COLORS, tc, _is_dark, btn_style, REPORTS_DIR, ensure_directories,
)
from src.shared_widgets import BarChartWidget
from src.modules.overtime import data_manager
from src import audit


# ════════════════════════════════════════════════════════════════════════
# Weekly Summary Page
# ════════════════════════════════════════════════════════════════════════

class WeeklySummaryPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._week_ending = data_manager.get_current_week_ending()
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
        title = QLabel("Weekly Summary")
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

        # Week navigation
        week_nav = QHBoxLayout()
        self.btn_prev = QPushButton("\u2039 Previous Week")
        self.btn_prev.setCursor(Qt.PointingHandCursor)
        self.btn_prev.setStyleSheet(f"""
            QPushButton {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 6px; padding: 8px 16px;
                font-size: 14px; font-weight: 600; color: {tc('text')};
            }}
            QPushButton:hover {{ background: {tc('bg')}; }}
        """)
        self.btn_prev.clicked.connect(self._prev_week)
        week_nav.addWidget(self.btn_prev)

        week_nav.addStretch()
        self.lbl_week = QLabel("")
        self.lbl_week.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.lbl_week.setStyleSheet(f"color: {tc('text')};")
        self.lbl_week.setAlignment(Qt.AlignCenter)
        week_nav.addWidget(self.lbl_week)
        week_nav.addStretch()

        self.btn_next = QPushButton("Next Week \u203A")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setStyleSheet(self.btn_prev.styleSheet())
        self.btn_next.clicked.connect(self._next_week)
        week_nav.addWidget(self.btn_next)
        layout.addLayout(week_nav)

        # Summary table
        self.summary_table = QTableWidget(0, 7)
        self.summary_table.setHorizontalHeaderLabels([
            "Site", "Budget Hrs", "Actual Hrs", "Variance", "OT Hrs", "OT Cost", "DLS %"
        ])
        hdr = self.summary_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 7):
            hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self.summary_table.setColumnWidth(c, 110)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.summary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setShowGrid(False)
        self.summary_table.setAlternatingRowColors(True)
        layout.addWidget(self.summary_table)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _prev_week(self):
        d = date.fromisoformat(self._week_ending)
        self._week_ending = (d - timedelta(weeks=1)).isoformat()
        self.refresh()

    def _next_week(self):
        d = date.fromisoformat(self._week_ending)
        self._week_ending = (d + timedelta(weeks=1)).isoformat()
        self.refresh()

    def _export_csv(self):
        ensure_directories()
        rows = data_manager.get_weekly_summary(self._week_ending)
        if not rows:
            QMessageBox.information(self, "No Data", "No data to export for this week.")
            return

        path = os.path.join(REPORTS_DIR, f"weekly_summary_{self._week_ending}.csv")
        try:
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            QMessageBox.information(self, "Exported", f"Report saved to:\n{path}")
            audit.log_event("overtime", "weekly_summary_exported",
                             self._get_username(), f"Week: {self._week_ending}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def refresh(self):
        self.lbl_week.setText(f"Week Ending: {self._week_ending}")
        rows = data_manager.get_weekly_summary(self._week_ending)
        self.summary_table.setRowCount(len(rows))

        for i, r in enumerate(rows):
            self.summary_table.setItem(i, 0, QTableWidgetItem(r["site"]))

            budget_item = QTableWidgetItem(f"{r['budget_hours']:.1f}" if r["budget_hours"] > 0 else "\u2014")
            budget_item.setTextAlignment(Qt.AlignCenter)
            self.summary_table.setItem(i, 1, budget_item)

            actual_item = QTableWidgetItem(f"{r['actual_hours']:.1f}")
            actual_item.setTextAlignment(Qt.AlignCenter)
            actual_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.summary_table.setItem(i, 2, actual_item)

            # Variance colored
            variance = r["variance"]
            var_item = QTableWidgetItem(f"{variance:+.1f}" if r["budget_hours"] > 0 else "\u2014")
            var_item.setTextAlignment(Qt.AlignCenter)
            var_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            if variance > 0:
                var_item.setForeground(QColor(COLORS["danger"]))
            elif variance < 0:
                var_item.setForeground(QColor(COLORS["success"]))
            self.summary_table.setItem(i, 3, var_item)

            ot_item = QTableWidgetItem(f"{r['ot_hours']:.1f}")
            ot_item.setTextAlignment(Qt.AlignCenter)
            if r["ot_hours"] > 0:
                ot_item.setForeground(QColor(COLORS["warning"]))
                ot_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.summary_table.setItem(i, 4, ot_item)

            cost_item = QTableWidgetItem(f"${r['ot_cost']:,.0f}")
            cost_item.setTextAlignment(Qt.AlignCenter)
            self.summary_table.setItem(i, 5, cost_item)

            dls_item = QTableWidgetItem(f"{r['dls_percentage']:.1f}%")
            dls_item.setTextAlignment(Qt.AlignCenter)
            dls_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.summary_table.setItem(i, 6, dls_item)

            self.summary_table.setRowHeight(i, 42)


# ════════════════════════════════════════════════════════════════════════
# By Site Page
# ════════════════════════════════════════════════════════════════════════

class BySitePage(QWidget):
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
        layout.setSpacing(16)

        # Header
        title = QLabel("Analysis by Site")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        # Filters
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)

        lbl_site = QLabel("Site:")
        lbl_site.setStyleSheet(f"color: {tc('text')}; font-weight: 600;")
        filter_row.addWidget(lbl_site)
        self.site_combo = QComboBox()
        self.site_combo.setMinimumWidth(200)
        self.site_combo.setFixedHeight(38)
        filter_row.addWidget(self.site_combo)

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

        btn_apply = QPushButton("Apply")
        btn_apply.setCursor(Qt.PointingHandCursor)
        btn_apply.setFixedHeight(38)
        btn_apply.setStyleSheet(btn_style(tc("info"), "white"))
        btn_apply.clicked.connect(self._apply_filter)
        filter_row.addWidget(btn_apply)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Weekly trend chart
        trend_group = QGroupBox("Weekly Hours Trend (Last 8 Weeks)")
        trend_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        trend_lay = QVBoxLayout(trend_group)
        self.trend_chart = BarChartWidget()
        trend_lay.addWidget(self.trend_chart)
        layout.addWidget(trend_group)

        # Budget vs Actual
        budget_group = QGroupBox("Budget vs Actual")
        budget_group.setStyleSheet(trend_group.styleSheet())
        budget_lay = QVBoxLayout(budget_group)
        self.budget_table = QTableWidget(0, 4)
        self.budget_table.setHorizontalHeaderLabels([
            "Metric", "Budget", "Actual", "Variance"
        ])
        b_hdr = self.budget_table.horizontalHeader()
        b_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in [1, 2, 3]:
            b_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self.budget_table.setColumnWidth(c, 140)
        b_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.budget_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.budget_table.verticalHeader().setVisible(False)
        self.budget_table.setShowGrid(False)
        self.budget_table.setMaximumHeight(120)
        budget_lay.addWidget(self.budget_table)
        layout.addWidget(budget_group)

        # Officer breakdown table
        officer_group = QGroupBox("Officer Breakdown")
        officer_group.setStyleSheet(trend_group.styleSheet())
        off_lay = QVBoxLayout(officer_group)

        self.officer_table = QTableWidget(0, 6)
        self.officer_table.setHorizontalHeaderLabels([
            "Officer", "Week Ending", "Regular", "OT", "Total", "Pay"
        ])
        o_hdr = self.officer_table.horizontalHeader()
        o_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            o_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self.officer_table.setColumnWidth(c, 110)
        o_hdr.setStyleSheet(b_hdr.styleSheet())
        self.officer_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.officer_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.officer_table.verticalHeader().setVisible(False)
        self.officer_table.setShowGrid(False)
        self.officer_table.setAlternatingRowColors(True)
        off_lay.addWidget(self.officer_table)
        layout.addWidget(officer_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _apply_filter(self):
        self._load_data()

    def _load_data(self):
        site = self.site_combo.currentText()
        if not site:
            return

        d_from = self.date_from.date().toString("yyyy-MM-dd")
        d_to = self.date_to.date().toString("yyyy-MM-dd")

        entries = data_manager.get_site_analysis(site, d_from, d_to)

        # Officer breakdown
        self.officer_table.setRowCount(len(entries))
        for i, e in enumerate(entries):
            self.officer_table.setItem(i, 0, QTableWidgetItem(e.get("officer_name", "")))
            self.officer_table.setItem(i, 1, QTableWidgetItem(e.get("week_ending", "")))

            reg_item = QTableWidgetItem(f"{e.get('regular_hours', 0):.1f}")
            reg_item.setTextAlignment(Qt.AlignCenter)
            self.officer_table.setItem(i, 2, reg_item)

            ot_item = QTableWidgetItem(f"{e.get('overtime_hours', 0):.1f}")
            ot_item.setTextAlignment(Qt.AlignCenter)
            if e.get("overtime_hours", 0) > 0:
                ot_item.setForeground(QColor(COLORS["warning"]))
            self.officer_table.setItem(i, 3, ot_item)

            total_item = QTableWidgetItem(f"{e.get('total_hours', 0):.1f}")
            total_item.setTextAlignment(Qt.AlignCenter)
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.officer_table.setItem(i, 4, total_item)

            pay_item = QTableWidgetItem(f"${e.get('total_pay', 0):,.0f}")
            pay_item.setTextAlignment(Qt.AlignCenter)
            self.officer_table.setItem(i, 5, pay_item)

            self.officer_table.setRowHeight(i, 40)

        # Weekly trend (aggregate by week)
        week_totals = {}
        for e in entries:
            we = e.get("week_ending", "")
            if we not in week_totals:
                week_totals[we] = 0
            week_totals[we] += e.get("total_hours", 0)

        trend_data = sorted(week_totals.items())[-8:]
        chart_data = [(we[-5:], round(h, 1), tc("info")) for we, h in trend_data]
        self.trend_chart.set_data(chart_data)

        # Budget vs Actual
        budget = data_manager.get_site_budget(site)
        total_actual = sum(e.get("total_hours", 0) for e in entries)
        budget_hrs = budget.get("weekly_budget_hours", 0) if budget else 0

        self.budget_table.setRowCount(1)
        self.budget_table.setItem(0, 0, QTableWidgetItem("Weekly Hours"))
        b_item = QTableWidgetItem(f"{budget_hrs:.1f}" if budget_hrs > 0 else "\u2014")
        b_item.setTextAlignment(Qt.AlignCenter)
        self.budget_table.setItem(0, 1, b_item)
        a_item = QTableWidgetItem(f"{total_actual:.1f}")
        a_item.setTextAlignment(Qt.AlignCenter)
        a_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.budget_table.setItem(0, 2, a_item)
        var = total_actual - budget_hrs if budget_hrs > 0 else 0
        v_item = QTableWidgetItem(f"{var:+.1f}" if budget_hrs > 0 else "\u2014")
        v_item.setTextAlignment(Qt.AlignCenter)
        v_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        if var > 0:
            v_item.setForeground(QColor(COLORS["danger"]))
        elif var < 0:
            v_item.setForeground(QColor(COLORS["success"]))
        self.budget_table.setItem(0, 3, v_item)
        self.budget_table.setRowHeight(0, 40)

    def refresh(self):
        # Populate site dropdown
        current = self.site_combo.currentText()
        self.site_combo.clear()
        sites = [s["name"] for s in data_manager.get_site_names()]
        self.site_combo.addItems(sites)
        if current and current in sites:
            self.site_combo.setCurrentText(current)
        self._load_data()


# ════════════════════════════════════════════════════════════════════════
# By Officer Page
# ════════════════════════════════════════════════════════════════════════

class ByOfficerPage(QWidget):
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
        layout.setSpacing(16)

        # Header
        title = QLabel("Analysis by Officer")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        # Filters
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)

        lbl_off = QLabel("Officer:")
        lbl_off.setStyleSheet(f"color: {tc('text')}; font-weight: 600;")
        filter_row.addWidget(lbl_off)
        self.officer_combo = QComboBox()
        self.officer_combo.setEditable(True)
        self.officer_combo.setMinimumWidth(220)
        self.officer_combo.setFixedHeight(38)
        self.officer_combo.setInsertPolicy(QComboBox.NoInsert)
        filter_row.addWidget(self.officer_combo)

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

        btn_apply = QPushButton("Apply")
        btn_apply.setCursor(Qt.PointingHandCursor)
        btn_apply.setFixedHeight(38)
        btn_apply.setStyleSheet(btn_style(tc("info"), "white"))
        btn_apply.clicked.connect(self._apply_filter)
        filter_row.addWidget(btn_apply)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # OT Trend chart
        trend_group = QGroupBox("Overtime Trend")
        trend_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        trend_lay = QVBoxLayout(trend_group)
        self.ot_trend_chart = BarChartWidget()
        trend_lay.addWidget(self.ot_trend_chart)
        layout.addWidget(trend_group)

        # Weekly hours history
        history_group = QGroupBox("Weekly Hours History")
        history_group.setStyleSheet(trend_group.styleSheet())
        hist_lay = QVBoxLayout(history_group)

        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels([
            "Week Ending", "Site", "Regular", "OT", "Total", "Pay"
        ])
        h_hdr = self.history_table.horizontalHeader()
        h_hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.history_table.setColumnWidth(0, 120)
        h_hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, 6):
            h_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self.history_table.setColumnWidth(c, 100)
        h_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setShowGrid(False)
        self.history_table.setAlternatingRowColors(True)
        hist_lay.addWidget(self.history_table)
        layout.addWidget(history_group)

        # Site distribution
        dist_group = QGroupBox("Site Distribution")
        dist_group.setStyleSheet(trend_group.styleSheet())
        dist_lay = QVBoxLayout(dist_group)
        self.site_dist_chart = BarChartWidget()
        dist_lay.addWidget(self.site_dist_chart)
        layout.addWidget(dist_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _apply_filter(self):
        self._load_data()

    def _load_data(self):
        # Find selected officer's ID
        officer_name = self.officer_combo.currentText()
        if not officer_name:
            return

        # Look up officer_id
        officers = data_manager.get_all_officers()
        officer_id = ""
        for o in officers:
            if o.get("name") == officer_name:
                officer_id = o.get("officer_id", "")
                break

        d_from = self.date_from.date().toString("yyyy-MM-dd")
        d_to = self.date_to.date().toString("yyyy-MM-dd")

        if officer_id:
            entries = data_manager.get_officer_analysis(officer_id, d_from, d_to)
        else:
            entries = []

        # History table
        self.history_table.setRowCount(len(entries))
        for i, e in enumerate(entries):
            self.history_table.setItem(i, 0, QTableWidgetItem(e.get("week_ending", "")))
            self.history_table.setItem(i, 1, QTableWidgetItem(e.get("site", "")))

            reg_item = QTableWidgetItem(f"{e.get('regular_hours', 0):.1f}")
            reg_item.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(i, 2, reg_item)

            ot_val = e.get("overtime_hours", 0)
            ot_item = QTableWidgetItem(f"{ot_val:.1f}")
            ot_item.setTextAlignment(Qt.AlignCenter)
            if ot_val > 0:
                ot_item.setForeground(QColor(COLORS["warning"]))
                ot_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.history_table.setItem(i, 3, ot_item)

            total_item = QTableWidgetItem(f"{e.get('total_hours', 0):.1f}")
            total_item.setTextAlignment(Qt.AlignCenter)
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.history_table.setItem(i, 4, total_item)

            pay_item = QTableWidgetItem(f"${e.get('total_pay', 0):,.0f}")
            pay_item.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(i, 5, pay_item)

            self.history_table.setRowHeight(i, 40)

        # OT trend chart (OT hours per week)
        week_ot = {}
        for e in entries:
            we = e.get("week_ending", "")
            if we not in week_ot:
                week_ot[we] = 0
            week_ot[we] += e.get("overtime_hours", 0)

        ot_data = sorted(week_ot.items())[-8:]
        self.ot_trend_chart.set_data(
            [(we[-5:], round(h, 1), COLORS["warning"]) for we, h in ot_data]
        )

        # Site distribution
        site_hours = {}
        for e in entries:
            s = e.get("site", "Unknown")
            if s not in site_hours:
                site_hours[s] = 0
            site_hours[s] += e.get("total_hours", 0)

        dist_data = sorted(site_hours.items(), key=lambda x: -x[1])[:10]
        self.site_dist_chart.set_data(
            [(s[:16], round(h, 1), tc("info")) for s, h in dist_data]
        )

    def refresh(self):
        current = self.officer_combo.currentText()
        self.officer_combo.clear()
        names = data_manager.get_officer_names()
        self.officer_combo.addItems(names)
        if current and current in names:
            self.officer_combo.setCurrentText(current)
        self._load_data()


# ════════════════════════════════════════════════════════════════════════
# Overtime Alerts Page
# ════════════════════════════════════════════════════════════════════════

class OvertimeAlertsPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._week_ending = data_manager.get_current_week_ending()
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
        title = QLabel("Overtime Alerts")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        header_row.addWidget(title)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Week display
        self.lbl_week = QLabel("")
        self.lbl_week.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.lbl_week.setStyleSheet(f"color: {tc('text_light')};")
        layout.addWidget(self.lbl_week)

        # Filters
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)

        lbl_site = QLabel("Filter by Site:")
        lbl_site.setStyleSheet(f"color: {tc('text')}; font-weight: 600;")
        filter_row.addWidget(lbl_site)
        self.site_filter = QComboBox()
        self.site_filter.setMinimumWidth(200)
        self.site_filter.setFixedHeight(38)
        self.site_filter.addItem("All Sites")
        self.site_filter.currentTextChanged.connect(lambda: self._populate_table())
        filter_row.addWidget(self.site_filter)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Legend
        legend_row = QHBoxLayout()
        legend_row.setSpacing(20)
        for level, color, desc in [
            ("Warning", COLORS["warning"], "32 - 39.99 hrs"),
            ("Over", COLORS["danger"], "40+ hrs"),
            ("Critical", "#7C2D12", "48+ hrs"),
        ]:
            dot = QLabel(f"\u25CF {level}: {desc}")
            dot.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 13px;")
            legend_row.addWidget(dot)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        # Alerts table
        self.alerts_table = QTableWidget(0, 7)
        self.alerts_table.setHorizontalHeaderLabels([
            "Level", "Officer", "Site", "Regular Hrs", "OT Hrs", "Total Hrs", "Action"
        ])
        hdr = self.alerts_table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in [0, 3, 4, 5, 6]:
            hdr.setSectionResizeMode(c, QHeaderView.Fixed)
        self.alerts_table.setColumnWidth(0, 90)
        self.alerts_table.setColumnWidth(3, 100)
        self.alerts_table.setColumnWidth(4, 100)
        self.alerts_table.setColumnWidth(5, 100)
        self.alerts_table.setColumnWidth(6, 110)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.alerts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.alerts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.alerts_table.verticalHeader().setVisible(False)
        self.alerts_table.setShowGrid(False)
        self.alerts_table.setAlternatingRowColors(True)
        layout.addWidget(self.alerts_table)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _send_alert(self, officer_name: str):
        """Placeholder for future alert sending."""
        audit.log_event("overtime", "alert_sent", self._get_username(),
                         f"OT alert for: {officer_name}")
        QMessageBox.information(self, "Alert Logged",
                                f"Alert logged for {officer_name}.\n(Notification sending not yet implemented.)")

    def _populate_table(self):
        """Fill the alerts table with current data."""
        alerts = data_manager.get_overtime_alerts(self._week_ending)
        site_filter = self.site_filter.currentText()

        if site_filter and site_filter != "All Sites":
            alerts = [a for a in alerts if a.get("site") == site_filter]

        level_colors = {
            "Warning": COLORS["warning"],
            "Over": COLORS["danger"],
            "Critical": "#7C2D12",
        }
        level_bg = {
            "Warning": COLORS["warning_light"],
            "Over": COLORS["danger_light"],
            "Critical": "#FEE2E2",
        }

        self.alerts_table.setRowCount(len(alerts))
        for i, a in enumerate(alerts):
            level = a.get("level", "Warning")
            color = level_colors.get(level, tc("text"))
            bg = level_bg.get(level, tc("card"))

            # Level badge
            level_item = QTableWidgetItem(level)
            level_item.setTextAlignment(Qt.AlignCenter)
            level_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            level_item.setForeground(QColor(color))
            level_item.setBackground(QColor(bg))
            self.alerts_table.setItem(i, 0, level_item)

            self.alerts_table.setItem(i, 1, QTableWidgetItem(a.get("officer_name", "")))
            self.alerts_table.setItem(i, 2, QTableWidgetItem(a.get("site", "")))

            reg_item = QTableWidgetItem(f"{a.get('regular_hours', 0):.1f}")
            reg_item.setTextAlignment(Qt.AlignCenter)
            self.alerts_table.setItem(i, 3, reg_item)

            ot_item = QTableWidgetItem(f"{a.get('overtime_hours', 0):.1f}")
            ot_item.setTextAlignment(Qt.AlignCenter)
            ot_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            ot_item.setForeground(QColor(COLORS["warning"]))
            self.alerts_table.setItem(i, 4, ot_item)

            total_item = QTableWidgetItem(f"{a.get('total_hours', 0):.1f}")
            total_item.setTextAlignment(Qt.AlignCenter)
            total_item.setFont(QFont("Segoe UI", 14, QFont.Bold))
            total_item.setForeground(QColor(color))
            self.alerts_table.setItem(i, 5, total_item)

            # Send Alert button
            actions = QWidget()
            a_lay = QHBoxLayout(actions)
            a_lay.setContentsMargins(4, 2, 4, 2)
            btn = QPushButton("Send Alert")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(90, 30)
            btn.setStyleSheet(btn_style(COLORS["warning"], "white"))
            officer_name = a.get("officer_name", "")
            btn.clicked.connect(lambda checked, n=officer_name: self._send_alert(n))
            a_lay.addWidget(btn)
            self.alerts_table.setCellWidget(i, 6, actions)

            self.alerts_table.setRowHeight(i, 44)

    def refresh(self):
        self._week_ending = data_manager.get_current_week_ending()
        self.lbl_week.setText(f"Current Week Ending: {self._week_ending}")

        # Populate site filter
        current = self.site_filter.currentText()
        self.site_filter.clear()
        self.site_filter.addItem("All Sites")
        sites = [s["name"] for s in data_manager.get_site_names()]
        self.site_filter.addItems(sites)
        if current and current in sites:
            self.site_filter.setCurrentText(current)

        self._populate_table()
