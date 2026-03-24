"""
Cerasus Hub -- Attendance Module: Dashboard Page
Summary cards, recent infractions, top at-risk officers, and infraction breakdown chart.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QGroupBox, QScrollArea, QSizePolicy,
    QMessageBox,
)
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QFontMetrics

from datetime import date, timedelta

from src.config import COLORS, tc, _is_dark, btn_style
from src.shared_widgets import make_stat_card, BarChartWidget
from src.modules.attendance import data_manager
from src.modules.attendance.policy_engine import (
    INFRACTION_TYPES, DISCIPLINE_LABELS, POINT_WINDOW_DAYS,
    determine_discipline_level, calculate_active_points,
)
from src.modules.attendance.risk_engine import get_at_risk_officers
from src import audit

# ── Attrition risk level colors ──────────────────────────────────────
RISK_LEVEL_COLORS = {
    "low": "#059669",       # green
    "moderate": "#D97706",  # amber
    "high": "#EA580C",      # orange
    "critical": "#C8102E",  # red
}

# Try to import QtCharts for a nicer look; fall back to custom QPainter widget
_HAS_QTCHARTS = False
try:
    from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis
    _HAS_QTCHARTS = True
except ImportError:
    pass


# ════════════════════════════════════════════════════════════════════════
# Infraction Trends Chart Widget (vertical bar chart via QPainter)
# ════════════════════════════════════════════════════════════════════════

class _PainterTrendsChart(QWidget):
    """Custom vertical bar chart drawn with QPainter.
    Takes data as [(label, value), ...].
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[str, int]] = []
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, data: list[tuple[str, int]]):
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = tc('card')
        painter.fillRect(self.rect(), QColor(bg_color))

        w = self.width()
        h = self.height()
        margin_left = 50
        margin_right = 20
        margin_top = 20
        margin_bottom = 50

        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        if chart_w <= 0 or chart_h <= 0:
            painter.end()
            return

        n = len(self._data)
        max_val = max(v for _, v in self._data) if self._data else 1
        if max_val == 0:
            max_val = 1

        bar_spacing = max(4, chart_w // (n * 6)) if n > 0 else 4
        bar_width = max(12, (chart_w - bar_spacing * (n + 1)) // max(n, 1))
        total_bars_w = n * bar_width + (n + 1) * bar_spacing
        x_offset = margin_left + (chart_w - total_bars_w) // 2

        # Accent color with transparency
        accent = QColor(COLORS['accent'] if not _is_dark() else COLORS['accent'])
        accent.setAlpha(200)

        # Y-axis gridlines
        painter.setPen(QPen(QColor(tc('border')), 1, Qt.DashLine))
        grid_steps = 4
        for i in range(grid_steps + 1):
            y = margin_top + chart_h - int(chart_h * i / grid_steps)
            painter.drawLine(margin_left, y, w - margin_right, y)
            # Y-axis label
            val = int(max_val * i / grid_steps)
            painter.setPen(QPen(QColor(tc('text_light'))))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(QRectF(0, y - 10, margin_left - 6, 20),
                             Qt.AlignRight | Qt.AlignVCenter, str(val))
            painter.setPen(QPen(QColor(tc('border')), 1, Qt.DashLine))

        # Bars
        for i, (label, value) in enumerate(self._data):
            bx = x_offset + bar_spacing + i * (bar_width + bar_spacing)
            bar_h = int((value / max_val) * chart_h) if max_val > 0 else 0
            by = margin_top + chart_h - bar_h

            # Bar fill
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawRoundedRect(QRectF(bx, by, bar_width, bar_h), 3, 3)

            # Value on top of bar
            painter.setPen(QPen(QColor(tc('text'))))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(QRectF(bx, by - 18, bar_width, 16),
                             Qt.AlignCenter, str(value))

            # X-axis label
            painter.setPen(QPen(QColor(tc('text_light'))))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(QRectF(bx - 4, margin_top + chart_h + 6, bar_width + 8, 36),
                             Qt.AlignHCenter | Qt.AlignTop, label)

        painter.end()


def _make_qtcharts_bar(data: list[tuple[str, int]]):
    """Build a QChartView with QBarSeries from data. Returns QChartView."""
    bar_set = QBarSet("Infractions")
    accent = QColor(COLORS['accent'] if not _is_dark() else COLORS['accent'])
    accent.setAlpha(200)
    bar_set.setColor(accent)

    categories = []
    for label, value in data:
        bar_set.append(value)
        categories.append(label)

    series = QBarSeries()
    series.append(bar_set)

    chart = QChart()
    chart.addSeries(series)
    chart.setAnimationOptions(QChart.SeriesAnimations)
    chart.legend().setVisible(False)
    chart.setBackgroundBrush(QBrush(QColor(tc('card'))))
    chart.setMargins(QRect(4, 4, 4, 4))

    axis_x = QBarCategoryAxis()
    axis_x.append(categories)
    axis_x.setLabelsColor(QColor(tc('text_light')))
    chart.addAxis(axis_x, Qt.AlignBottom)
    series.attachAxis(axis_x)

    max_val = max((v for _, v in data), default=1) or 1
    axis_y = QValueAxis()
    axis_y.setRange(0, max_val + 1)
    axis_y.setLabelFormat("%d")
    axis_y.setLabelsColor(QColor(tc('text_light')))
    chart.addAxis(axis_y, Qt.AlignLeft)
    series.attachAxis(axis_y)

    view = QChartView(chart)
    view.setRenderHint(QPainter.Antialiasing)
    view.setMinimumHeight(220)
    return view


class TrendsChartWidget(QWidget):
    """Vertical bar chart for infraction trends.
    Uses QtCharts if available, otherwise falls back to QPainter.
    Supports swapping data via set_data().
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._child = None
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, data: list[tuple[str, int]]):
        # Remove old child
        if self._child is not None:
            self._layout.removeWidget(self._child)
            self._child.deleteLater()
            self._child = None

        if _HAS_QTCHARTS:
            self._child = _make_qtcharts_bar(data)
        else:
            self._child = _PainterTrendsChart()
            self._child.set_data(data)

        self._layout.addWidget(self._child)


# ════════════════════════════════════════════════════════════════════════
# Pie Chart Widget (for infraction breakdown)
# ════════════════════════════════════════════════════════════════════════

class PieChartWidget(QWidget):
    """Simple pie/donut chart drawn with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self.setMinimumHeight(200)
        self.setMinimumWidth(280)

    def set_data(self, data):
        """data: [(label, value, color_hex), ...]"""
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        total = sum(v for _, v, _ in self._data)
        if total == 0:
            painter.end()
            return

        size = min(self.width() // 2, self.height()) - 20
        cx = size // 2 + 10
        cy = self.height() // 2
        rect = QRect(cx - size // 2, cy - size // 2, size, size)

        start_angle = 90 * 16
        for label, value, color in self._data:
            span = int((value / total) * 360 * 16)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(color)))
            painter.drawPie(rect, start_angle, span)
            start_angle += span

        # Donut hole
        inner_size = size * 55 // 100
        center_color = tc('card')
        painter.setBrush(QBrush(QColor(center_color)))
        painter.drawEllipse(cx - inner_size // 2, cy - inner_size // 2,
                            inner_size, inner_size)

        # Total in center
        painter.setPen(QPen(QColor(tc('text'))))
        painter.setFont(QFont("Segoe UI", 16, QFont.Bold))
        painter.drawText(QRect(cx - inner_size // 2, cy - 14, inner_size, 28),
                         Qt.AlignCenter, str(total))

        # Legend on right
        legend_x = size + 30
        legend_y = 20
        for label, value, color in self._data:
            pct = (value / total * 100) if total > 0 else 0
            painter.setBrush(QBrush(QColor(color)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(legend_x, legend_y + 2, 10, 10)
            painter.setPen(QPen(QColor(tc('text'))))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(legend_x + 16, legend_y + 12,
                             f"{label}: {value} ({pct:.0f}%)")
            legend_y += 22

        painter.end()


# ════════════════════════════════════════════════════════════════════════
# Dashboard Page
# ════════════════════════════════════════════════════════════════════════

class DashboardPage(QWidget):
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
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(16)

        # ── Header
        hdr = QLabel("Attendance Tracking System")
        hdr.setFont(QFont("Segoe UI", 22, QFont.Bold))
        hdr.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(hdr)

        # ── Quick Actions row
        qa_row = QHBoxLayout()
        qa_row.setSpacing(12)

        btn_log = QPushButton("Log Infraction")
        btn_log.setStyleSheet(self._qa_btn_style(COLORS['accent'], COLORS.get('accent_hover', COLORS['accent'])))
        btn_log.setFixedHeight(38)
        btn_log.setCursor(Qt.PointingHandCursor)
        btn_log.clicked.connect(self._qa_log_infraction)
        qa_row.addWidget(btn_log)

        btn_roster = QPushButton("View Roster")
        btn_roster.setStyleSheet(self._qa_btn_style(COLORS['info'], COLORS.get('info', COLORS['info'])))
        btn_roster.setFixedHeight(38)
        btn_roster.setCursor(Qt.PointingHandCursor)
        btn_roster.clicked.connect(self._qa_view_roster)
        qa_row.addWidget(btn_roster)

        btn_scan = QPushButton("Run Review Scan")
        btn_scan.setStyleSheet(self._qa_btn_style(COLORS['warning'], COLORS.get('warning', COLORS['warning'])))
        btn_scan.setFixedHeight(38)
        btn_scan.setCursor(Qt.PointingHandCursor)
        btn_scan.clicked.connect(self._qa_review_scan)
        qa_row.addWidget(btn_scan)

        qa_row.addStretch()
        layout.addLayout(qa_row)

        # ── Stat cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        self.card_officers = make_stat_card("Active Officers", "0", tc('info'))
        self.card_at_risk = make_stat_card("At-Risk (5+ pts)", "0", tc('warning'))
        self.card_reviews = make_stat_card("Pending Reviews", "0", tc('accent'))
        self.card_termination = make_stat_card("Termination Eligible", "0", tc('danger'))
        self.card_infractions = make_stat_card("Infractions This Month", "0", tc('warning'))
        cards_row.addWidget(self.card_officers)
        cards_row.addWidget(self.card_at_risk)
        cards_row.addWidget(self.card_reviews)
        cards_row.addWidget(self.card_termination)
        cards_row.addWidget(self.card_infractions)
        layout.addLayout(cards_row)

        # ── Additional KPI cards row (#24)
        kpi_row2 = QHBoxLayout()
        kpi_row2.setSpacing(16)
        self.card_clean_slate = make_stat_card("Clean Slate (90+ days)", "0", COLORS.get('success', '#22C55E'))
        self.card_avg_points = make_stat_card("Avg Points / Officer", "0.0", tc('info'))
        self.card_highest_risk = make_stat_card("Highest Risk Officer", "--", COLORS.get('danger', '#EF4444'))
        kpi_row2.addWidget(self.card_clean_slate)
        kpi_row2.addWidget(self.card_avg_points)
        kpi_row2.addWidget(self.card_highest_risk)
        layout.addLayout(kpi_row2)

        # ── Two-column: Recent infractions + Top at-risk
        mid_row = QHBoxLayout()
        mid_row.setSpacing(16)

        # Recent infractions table
        recent_group = QGroupBox("Recent Infractions")
        recent_group.setStyleSheet(self._group_style())
        recent_lay = QVBoxLayout(recent_group)
        self.recent_table = QTableWidget(0, 5)
        self.recent_table.setHorizontalHeaderLabels([
            "Date", "Officer", "Type", "Points", "Discipline"
        ])
        hdr = self.recent_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setStyleSheet(self._header_style())
        self.recent_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setMinimumHeight(280)
        recent_lay.addWidget(self.recent_table)
        mid_row.addWidget(recent_group, 3)

        # Top at-risk officers
        risk_group = QGroupBox("Top 5 At-Risk Officers")
        risk_group.setStyleSheet(self._group_style())
        risk_lay = QVBoxLayout(risk_group)
        self.risk_chart = BarChartWidget()
        risk_lay.addWidget(self.risk_chart)
        mid_row.addWidget(risk_group, 2)

        layout.addLayout(mid_row)

        # ── Site Attendance Overview
        site_group = QGroupBox("Site Attendance Overview")
        site_group.setStyleSheet(self._group_style())
        site_lay = QVBoxLayout(site_group)
        self.site_table = QTableWidget(0, 5)
        self.site_table.setHorizontalHeaderLabels(["Site", "Officers", "Total Points", "Avg Points", "Risk Level"])
        site_hdr = self.site_table.horizontalHeader()
        site_hdr.setSectionResizeMode(QHeaderView.Stretch)
        site_hdr.setStyleSheet(self._header_style())
        self.site_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.site_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.site_table.verticalHeader().setVisible(False)
        self.site_table.setAlternatingRowColors(True)
        self.site_table.setMinimumHeight(200)
        site_lay.addWidget(self.site_table)
        layout.addWidget(site_group)

        # ── Attrition Risk Section ───────────────────────────────────
        RISK_BORDER = "#EA580C"
        RISK_BG = tc('card')
        attrition_group = QGroupBox("\u26A0  Officers at Risk — Predictive Attrition")
        attrition_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {RISK_BORDER};
                border: 2px solid {RISK_BORDER}; border-radius: 8px;
                margin-top: 12px; padding-top: 24px; background: {RISK_BG};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        attrition_lay = QVBoxLayout(attrition_group)

        # Summary count
        self.attrition_count_label = QLabel("0 officers at moderate+ risk")
        self.attrition_count_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.attrition_count_label.setStyleSheet(f"color: {RISK_BORDER}; padding: 4px 0;")
        attrition_lay.addWidget(self.attrition_count_label)

        # Table: Name | Site | Risk Score | Risk Level | Top Factor
        self.attrition_table = QTableWidget(0, 5)
        self.attrition_table.setHorizontalHeaderLabels([
            "Officer", "Site", "Risk Score", "Risk Level", "Top Factor"
        ])
        att_hdr = self.attrition_table.horizontalHeader()
        att_hdr.setSectionResizeMode(QHeaderView.Stretch)
        att_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {RISK_BORDER};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid #C2410C;
            }}
        """)
        self.attrition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.attrition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.attrition_table.verticalHeader().setVisible(False)
        self.attrition_table.setAlternatingRowColors(True)
        self.attrition_table.setMinimumHeight(220)
        attrition_lay.addWidget(self.attrition_table)

        # Empty state
        self.attrition_empty_label = QLabel("No officers at moderate or higher attrition risk")
        self.attrition_empty_label.setAlignment(Qt.AlignCenter)
        self.attrition_empty_label.setFont(QFont("Segoe UI", 11))
        self.attrition_empty_label.setStyleSheet(f"color: {tc('text_light')}; padding: 16px;")
        self.attrition_empty_label.setVisible(False)
        attrition_lay.addWidget(self.attrition_empty_label)

        layout.addWidget(attrition_group)

        # ── Infraction Trends Chart
        trends_group = QGroupBox("Infraction Trends")
        trends_group.setStyleSheet(self._group_style())
        trends_lay = QVBoxLayout(trends_group)

        # Tab toggle row
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self._trends_monthly_btn = QPushButton("Monthly Trend")
        self._trends_bytype_btn = QPushButton("By Type")
        for btn in (self._trends_monthly_btn, self._trends_bytype_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
            btn.setFixedHeight(34)
            btn.setMinimumWidth(120)
        self._trends_monthly_btn.setStyleSheet(self._trends_tab_style(active=True))
        self._trends_bytype_btn.setStyleSheet(self._trends_tab_style(active=False))
        self._trends_monthly_btn.clicked.connect(lambda: self._switch_trends("monthly"))
        self._trends_bytype_btn.clicked.connect(lambda: self._switch_trends("bytype"))
        tab_row.addWidget(self._trends_monthly_btn)
        tab_row.addWidget(self._trends_bytype_btn)
        tab_row.addStretch()
        trends_lay.addLayout(tab_row)

        self._trends_mode = "monthly"
        self.trends_chart = TrendsChartWidget()
        trends_lay.addWidget(self.trends_chart)
        layout.addWidget(trends_group)

        # ── Expiring Points Alert Card
        AMBER = "#F59E0B"
        AMBER_BORDER = "#D97706"
        AMBER_BG = "#FEF3C7" if not _is_dark() else "#422006"
        expiry_group = QGroupBox("Points Expiring Soon (Next 30 Days)")
        expiry_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {AMBER};
                border: 2px solid {AMBER_BORDER}; border-radius: 8px;
                margin-top: 12px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        expiry_lay = QVBoxLayout(expiry_group)

        # Count label at top
        self.expiry_count_label = QLabel("0 officers with expiring points")
        self.expiry_count_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.expiry_count_label.setStyleSheet(f"color: {AMBER}; padding: 4px 0;")
        expiry_lay.addWidget(self.expiry_count_label)

        # Table for expiring points details
        self.expiry_table = QTableWidget(0, 5)
        self.expiry_table.setHorizontalHeaderLabels([
            "Officer", "Expiring Pts", "Expiry Date", "Current Level", "Level After Expiry"
        ])
        exp_hdr = self.expiry_table.horizontalHeader()
        exp_hdr.setSectionResizeMode(QHeaderView.Stretch)
        exp_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {AMBER};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid {AMBER_BORDER};
            }}
        """)
        self.expiry_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.expiry_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.expiry_table.verticalHeader().setVisible(False)
        self.expiry_table.setAlternatingRowColors(True)
        self.expiry_table.setMinimumHeight(180)
        expiry_lay.addWidget(self.expiry_table)

        # Empty state label (shown when no expiring points)
        self.expiry_empty_label = QLabel("No points expiring in the next 30 days")
        self.expiry_empty_label.setAlignment(Qt.AlignCenter)
        self.expiry_empty_label.setFont(QFont("Segoe UI", 11))
        self.expiry_empty_label.setStyleSheet(f"color: {tc('text_light')}; padding: 16px;")
        self.expiry_empty_label.setVisible(False)
        expiry_lay.addWidget(self.expiry_empty_label)

        layout.addWidget(expiry_group)

        # ── Infraction breakdown pie chart
        pie_group = QGroupBox("Infraction Breakdown by Category")
        pie_group.setStyleSheet(self._group_style())
        pie_lay = QVBoxLayout(pie_group)
        self.pie_chart = PieChartWidget()
        pie_lay.addWidget(self.pie_chart)
        layout.addWidget(pie_group)

        # ── Infraction Type Breakdown Table (#25)
        type_group = QGroupBox("Infraction Counts by Type (Current Period)")
        type_group.setStyleSheet(self._group_style())
        type_lay = QVBoxLayout(type_group)
        self.type_breakdown_table = QTableWidget(0, 3)
        self.type_breakdown_table.setHorizontalHeaderLabels(["Infraction Type", "Count", "Total Points"])
        tb_hdr = self.type_breakdown_table.horizontalHeader()
        tb_hdr.setSectionResizeMode(QHeaderView.Stretch)
        tb_hdr.setStyleSheet(self._header_style())
        self.type_breakdown_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.type_breakdown_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.type_breakdown_table.verticalHeader().setVisible(False)
        self.type_breakdown_table.setAlternatingRowColors(True)
        self.type_breakdown_table.setMinimumHeight(200)
        type_lay.addWidget(self.type_breakdown_table)
        layout.addWidget(type_group)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _group_style(self):
        return f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 12px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """

    def _trends_tab_style(self, active=False):
        if active:
            return f"""
                QPushButton {{
                    background: {COLORS['accent']}; color: white;
                    border: none; border-radius: 4px;
                    padding: 6px 18px;
                }}
                QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
            """
        else:
            return f"""
                QPushButton {{
                    background: {tc('card')}; color: {tc('text_light')};
                    border: 1px solid {tc('border')}; border-radius: 4px;
                    padding: 6px 18px;
                }}
                QPushButton:hover {{ background: {tc('border')}; }}
            """

    def _switch_trends(self, mode):
        self._trends_mode = mode
        self._trends_monthly_btn.setStyleSheet(self._trends_tab_style(active=(mode == "monthly")))
        self._trends_bytype_btn.setStyleSheet(self._trends_tab_style(active=(mode == "bytype")))
        self._refresh_trends()

    def _refresh_trends(self):
        if self._trends_mode == "monthly":
            data = data_manager.get_monthly_infraction_counts(6)
        else:
            data = data_manager.get_current_month_by_type()
        if not data:
            data = [("No data", 0)]
        self.trends_chart.set_data(data)

    def _header_style(self):
        return f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """

    def _update_card_value(self, card, value):
        """Update the value label inside a stat card."""
        labels = card.findChildren(QLabel)
        if len(labels) >= 2:
            labels[1].setText(str(value))

    def refresh(self):
        from src.shared_data import filter_by_user_sites

        summary = data_manager.get_dashboard_summary()

        # Apply site-based access filtering
        role = self.app_state.get("role", "")
        assigned_sites = self.app_state.get("assigned_sites", [])
        has_site_filter = assigned_sites and role != "admin"

        if has_site_filter:
            # Re-count stats from filtered officers
            all_officers = data_manager.get_active_officers()
            filtered = filter_by_user_sites(self.app_state, all_officers)
            officer_count = len(filtered)
            at_risk = sum(1 for o in filtered if float(o.get("active_points", 0)) >= 5)
            termination = sum(1 for o in filtered if float(o.get("active_points", 0)) >= 10)
            self._update_card_value(self.card_officers, officer_count)
            self._update_card_value(self.card_at_risk, at_risk)
            self._update_card_value(self.card_reviews, summary["pending_reviews"])
            self._update_card_value(self.card_termination, termination)
            self._update_card_value(self.card_infractions, summary.get("infractions_this_month", 0))

            # Filter top at-risk
            summary["top_at_risk"] = [o for o in summary["top_at_risk"] if o.get("site", "") in assigned_sites]
        else:
            # Update stat cards (unfiltered)
            self._update_card_value(self.card_officers, summary["active_officers"])
            self._update_card_value(self.card_at_risk, summary["at_risk"])
            self._update_card_value(self.card_reviews, summary["pending_reviews"])
            self._update_card_value(self.card_termination, summary["termination_eligible"])
            self._update_card_value(self.card_infractions, summary.get("infractions_this_month", 0))

        # ── Additional KPIs (#24): Clean Slate, Avg Points, Highest Risk ──
        all_active = data_manager.get_active_officers()
        if has_site_filter:
            from src.shared_data import filter_by_user_sites as _filt
            all_active = _filt(self.app_state, all_active)

        clean_slate_count = 0
        total_points = 0.0
        highest_name = "--"
        highest_pts = 0.0
        for off in all_active:
            pts = float(off.get("active_points", 0))
            total_points += pts
            if pts > highest_pts:
                highest_pts = pts
                highest_name = off.get("name", off.get("employee_id", "Unknown"))
            last_inf = off.get("last_infraction_date", "")
            if not last_inf:
                clean_slate_count += 1
            else:
                try:
                    from datetime import date as _d2, datetime as _dt2
                    d = _dt2.fromisoformat(last_inf).date() if "T" in last_inf else _d2.fromisoformat(last_inf)
                    if (_d2.today() - d).days >= 90:
                        clean_slate_count += 1
                except (ValueError, TypeError):
                    pass

        avg_pts = (total_points / len(all_active)) if all_active else 0.0
        self._update_card_value(self.card_clean_slate, clean_slate_count)
        self._update_card_value(self.card_avg_points, f"{avg_pts:.1f}")
        highest_display = f"{highest_name} ({highest_pts:.1f})" if highest_pts > 0 else "--"
        self._update_card_value(self.card_highest_risk, highest_display)

        # Recent infractions table (filtered by site)
        recent = summary["recent_infractions"]
        if has_site_filter:
            recent = [r for r in recent if r.get("site", "") in assigned_sites]
        self.recent_table.setRowCount(len(recent))
        for i, inf in enumerate(recent):
            itype = inf.get("infraction_type", "")
            type_info = INFRACTION_TYPES.get(itype, {})

            date_item = QTableWidgetItem(inf.get("infraction_date", ""))
            self.recent_table.setItem(i, 0, date_item)

            # Look up officer name
            officer_name = self._get_officer_name(inf.get("employee_id", ""))
            self.recent_table.setItem(i, 1, QTableWidgetItem(officer_name))

            self.recent_table.setItem(i, 2, QTableWidgetItem(type_info.get("label", itype)))

            pts_item = QTableWidgetItem(str(inf.get("points_assigned", 0)))
            pts_item.setTextAlignment(Qt.AlignCenter)
            pts = float(inf.get("points_assigned", 0))
            if pts >= 6:
                pts_item.setForeground(QColor(COLORS["danger"]))
            elif pts >= 3:
                pts_item.setForeground(QColor(COLORS["warning"]))
            self.recent_table.setItem(i, 3, pts_item)

            disc = inf.get("discipline_triggered", "")
            self.recent_table.setItem(i, 4, QTableWidgetItem(
                DISCIPLINE_LABELS.get(disc, disc)))

        # Top at-risk officers bar chart
        top_risk = summary["top_at_risk"]
        risk_colors = []
        for off in top_risk:
            pts = float(off.get("active_points", 0))
            if pts >= 10:
                color = COLORS["danger"]
            elif pts >= 8:
                color = "#9333EA"  # purple
            elif pts >= 6:
                color = COLORS["warning"]
            else:
                color = COLORS["info"]
            risk_colors.append((off.get("name", "Unknown"), pts, color))
        self.risk_chart.set_data(risk_colors)

        # Infraction breakdown pie chart
        breakdown = summary["infraction_breakdown"]
        category_colors = {
            "Tardiness": COLORS["warning"],
            "Call-Off": COLORS["info"],
            "NCNS": COLORS["danger"],
            "Emergency": COLORS["success"],
        }
        # Group by category
        category_counts = {}
        for itype, count in breakdown.items():
            cat = INFRACTION_TYPES.get(itype, {}).get("category", "Other")
            category_counts[cat] = category_counts.get(cat, 0) + count

        pie_data = [
            (cat, count, category_colors.get(cat, "#6b7280"))
            for cat, count in sorted(category_counts.items(), key=lambda x: -x[1])
        ]
        self.pie_chart.set_data(pie_data)

        # Infraction trends chart
        self._refresh_trends()

        # Expiring Points Alert
        self._refresh_expiring_points()

        # Site Attendance Overview table (filtered by user's assigned sites)
        site_data = data_manager.get_site_attendance_summary()
        if has_site_filter:
            site_data = [s for s in site_data if s.get("site", "") in assigned_sites]
        self.site_table.setRowCount(len(site_data))
        for i, site in enumerate(site_data):
            self.site_table.setItem(i, 0, QTableWidgetItem(site.get("site", "")))

            officers_item = QTableWidgetItem(str(site.get("officer_count", 0)))
            officers_item.setTextAlignment(Qt.AlignCenter)
            self.site_table.setItem(i, 1, officers_item)

            total_pts = float(site.get("total_points", 0) or 0)
            total_item = QTableWidgetItem(f"{total_pts:.1f}")
            total_item.setTextAlignment(Qt.AlignCenter)
            self.site_table.setItem(i, 2, total_item)

            avg_pts = float(site.get("avg_points", 0) or 0)
            avg_item = QTableWidgetItem(f"{avg_pts:.1f}")
            avg_item.setTextAlignment(Qt.AlignCenter)
            self.site_table.setItem(i, 3, avg_item)

            # Risk level based on avg points
            if avg_pts >= 6:
                risk_label, risk_color = "High", COLORS["danger"]
            elif avg_pts >= 3:
                risk_label, risk_color = "Medium", COLORS["warning"]
            else:
                risk_label, risk_color = "Low", COLORS["success"]
            risk_item = QTableWidgetItem(risk_label)
            risk_item.setTextAlignment(Qt.AlignCenter)
            risk_item.setForeground(QColor(risk_color))
            risk_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.site_table.setItem(i, 4, risk_item)

        # ── Infraction Type Breakdown Table (#25) ──
        breakdown = summary["infraction_breakdown"]
        type_rows = []
        for itype, count in breakdown.items():
            type_info = INFRACTION_TYPES.get(itype, {})
            label = type_info.get("label", itype)
            pts_per = type_info.get("points", 0)
            total_type_pts = count * pts_per
            type_rows.append((label, count, total_type_pts))
        type_rows.sort(key=lambda r: -r[1])

        self.type_breakdown_table.setRowCount(len(type_rows))
        for i, (label, cnt, tot_pts) in enumerate(type_rows):
            self.type_breakdown_table.setItem(i, 0, QTableWidgetItem(label))
            cnt_item = QTableWidgetItem(str(cnt))
            cnt_item.setTextAlignment(Qt.AlignCenter)
            self.type_breakdown_table.setItem(i, 1, cnt_item)
            pts_item = QTableWidgetItem(f"{tot_pts:.1f}")
            pts_item.setTextAlignment(Qt.AlignCenter)
            self.type_breakdown_table.setItem(i, 2, pts_item)

        # Attrition Risk section
        self._refresh_attrition_risk()

    def _refresh_attrition_risk(self):
        """Populate the Predictive Attrition Risk table."""
        at_risk = get_at_risk_officers(min_level="moderate", limit=10)

        count = len(at_risk)
        self.attrition_count_label.setText(
            f"{count} officer{'s' if count != 1 else ''} at moderate+ risk"
        )

        if count == 0:
            self.attrition_table.setVisible(False)
            self.attrition_empty_label.setVisible(True)
            self.attrition_table.setRowCount(0)
        else:
            self.attrition_table.setVisible(True)
            self.attrition_empty_label.setVisible(False)
            self.attrition_table.setRowCount(count)

            for i, risk in enumerate(at_risk):
                # Officer name
                self.attrition_table.setItem(i, 0, QTableWidgetItem(risk.get("name", "")))

                # Site
                self.attrition_table.setItem(i, 1, QTableWidgetItem(risk.get("site", "")))

                # Risk Score (0-100)
                score = risk.get("score", 0)
                score_item = QTableWidgetItem(str(score))
                score_item.setTextAlignment(Qt.AlignCenter)
                score_item.setFont(QFont("Segoe UI", 11, QFont.Bold))
                level = risk.get("level", "low")
                score_color = RISK_LEVEL_COLORS.get(level, COLORS["info"])
                score_item.setForeground(QColor(score_color))
                self.attrition_table.setItem(i, 2, score_item)

                # Risk Level badge
                level_display = level.capitalize()
                level_item = QTableWidgetItem(level_display)
                level_item.setTextAlignment(Qt.AlignCenter)
                level_item.setForeground(QColor(score_color))
                level_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                self.attrition_table.setItem(i, 3, level_item)

                # Top Factor
                top_factor = risk.get("top_factor", "")
                self.attrition_table.setItem(i, 4, QTableWidgetItem(top_factor))

    def _refresh_expiring_points(self):
        """Find officers with points expiring in the next 30 days."""
        AMBER = "#F59E0B"
        today = date.today()
        horizon = today + timedelta(days=30)
        cutoff_active = (today - timedelta(days=POINT_WINDOW_DAYS)).isoformat()

        from src.shared_data import filter_by_user_sites
        active_officers = data_manager.get_active_officers()
        active_officers = filter_by_user_sites(self.app_state, active_officers)
        expiring_rows = []  # (name, expiring_pts, earliest_expiry, current_level, new_level)

        for off in active_officers:
            oid = off.get("officer_id", "") or off.get("employee_id", "")
            if not oid:
                continue
            name = off.get("name", oid)

            infractions = data_manager.get_infractions_for_employee(oid)
            current_active = calculate_active_points(infractions)
            current_level = determine_discipline_level(current_active)

            # Find infractions whose points expire within the next 30 days
            expiring_pts = 0.0
            earliest_expiry = None
            for inf in infractions:
                if not inf.get("points_active", 1):
                    continue
                inf_date_str = inf.get("infraction_date", "")
                if not inf_date_str:
                    continue
                try:
                    d = date.fromisoformat(inf_date_str[:10])
                except (ValueError, TypeError):
                    continue

                expiry_date = d + timedelta(days=POINT_WINDOW_DAYS)
                # Must be currently active (not already expired) and expiring within 30 days
                if today <= expiry_date <= horizon:
                    pts = float(inf.get("points_assigned", 0))
                    expiring_pts += pts
                    if earliest_expiry is None or expiry_date < earliest_expiry:
                        earliest_expiry = expiry_date

            if expiring_pts > 0 and earliest_expiry is not None:
                new_active = round(current_active - expiring_pts, 2)
                if new_active < 0:
                    new_active = 0.0
                new_level = determine_discipline_level(new_active)
                expiring_rows.append((
                    name, expiring_pts, earliest_expiry.isoformat(),
                    current_level, new_level
                ))

        # Sort by earliest expiry date
        expiring_rows.sort(key=lambda r: r[2])

        # Update UI
        count = len(expiring_rows)
        self.expiry_count_label.setText(
            f"{count} officer{'s' if count != 1 else ''} with expiring points"
        )

        if count == 0:
            self.expiry_table.setVisible(False)
            self.expiry_empty_label.setVisible(True)
            self.expiry_table.setRowCount(0)
        else:
            self.expiry_table.setVisible(True)
            self.expiry_empty_label.setVisible(False)
            self.expiry_table.setRowCount(count)

            for i, (name, exp_pts, exp_date, cur_lvl, new_lvl) in enumerate(expiring_rows):
                self.expiry_table.setItem(i, 0, QTableWidgetItem(name))

                pts_item = QTableWidgetItem(f"{exp_pts:.1f}")
                pts_item.setTextAlignment(Qt.AlignCenter)
                pts_item.setForeground(QColor(AMBER))
                pts_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                self.expiry_table.setItem(i, 1, pts_item)

                self.expiry_table.setItem(i, 2, QTableWidgetItem(exp_date))

                cur_label = DISCIPLINE_LABELS.get(cur_lvl, cur_lvl)
                self.expiry_table.setItem(i, 3, QTableWidgetItem(cur_label))

                new_label = DISCIPLINE_LABELS.get(new_lvl, new_lvl)
                arrow_item = QTableWidgetItem(new_label)
                if new_lvl != cur_lvl:
                    arrow_item.setForeground(QColor(COLORS["success"]))
                    arrow_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                self.expiry_table.setItem(i, 4, arrow_item)

    # ── Quick Action helpers ────────────────────────────────────────

    def _qa_btn_style(self, bg, hover_bg):
        return f"""
            QPushButton {{
                background: {bg}; color: white;
                font-family: 'Segoe UI'; font-size: 13px; font-weight: 600;
                border: none; border-radius: 6px; padding: 6px 18px;
            }}
            QPushButton:hover {{ background: {hover_bg}; }}
        """

    def _navigate_to_page(self, page_index):
        """Navigate to a sibling page by its index in the shell's nav_buttons."""
        shell = self.parent()
        while shell is not None:
            if hasattr(shell, '_nav_to') and hasattr(shell, 'nav_buttons'):
                shell._nav_to(page_index)
                return True
            shell = shell.parent() if hasattr(shell, 'parent') else None
        return False

    def _qa_log_infraction(self):
        """Navigate to the Log Infraction page (index 4 in sidebar)."""
        shell = self.parent()
        while shell is not None:
            if hasattr(shell, '_nav_to') and hasattr(shell, 'nav_buttons'):
                # Find the infraction page by name
                for i, (btn, btn_idx, name) in enumerate(shell.nav_buttons):
                    if "infraction" in name.lower():
                        shell._nav_to(i)
                        return
                break
            shell = shell.parent() if hasattr(shell, 'parent') else None

    def _qa_view_roster(self):
        """Navigate to the Officer Roster page."""
        shell = self.parent()
        while shell is not None:
            if hasattr(shell, '_nav_to') and hasattr(shell, 'nav_buttons'):
                for i, (btn, btn_idx, name) in enumerate(shell.nav_buttons):
                    if "roster" in name.lower():
                        shell._nav_to(i)
                        return
                break
            shell = shell.parent() if hasattr(shell, 'parent') else None

    def _qa_review_scan(self):
        """Scan all active officers for 8+ points and show results."""
        from src.modules.attendance.policy_engine import REVIEW_TRIGGER_POINTS
        officers = data_manager.get_active_officers()
        flagged = []
        for off in officers:
            pts = float(off.get("active_points", 0))
            if pts >= REVIEW_TRIGGER_POINTS:
                flagged.append(off)

        if not flagged:
            QMessageBox.information(
                self, "Review Scan",
                f"No officers at or above {REVIEW_TRIGGER_POINTS} points. No reviews needed."
            )
            return

        lines = [f"Officers at {REVIEW_TRIGGER_POINTS}+ points:\n"]
        for off in sorted(flagged, key=lambda o: -float(o.get("active_points", 0))):
            name = off.get("name", off.get("employee_id", ""))
            pts = float(off.get("active_points", 0))
            level = off.get("discipline_level", "")
            lines.append(f"  {name}  --  {pts:.1f} pts  --  {level}")

        QMessageBox.information(
            self, "Review Scan Results",
            "\n".join(lines),
        )

    def _get_officer_name(self, employee_id: str) -> str:
        """Look up officer name by employee_id (officer_id)."""
        if not employee_id:
            return ""
        off = data_manager.get_officer(employee_id)
        return off.get("name", employee_id) if off else employee_id
