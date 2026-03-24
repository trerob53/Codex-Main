"""
Cerasus Hub -- DLS & Overtime Module: Dashboard Page
KPI cards, hours-by-site chart, top overtime officers table.
"""

from datetime import date, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QGroupBox, QScrollArea,
)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush

from src.config import COLORS, tc, _is_dark, btn_style
from src.modules.overtime import data_manager


# ════════════════════════════════════════════════════════════════════════
# Stacked Bar Chart Widget (Regular vs OT hours by site)
# ════════════════════════════════════════════════════════════════════════

class StackedBarChartWidget(QWidget):
    """Horizontal stacked bar chart: regular (blue) + overtime (red)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # list of (label, regular, overtime)
        self.setMinimumHeight(180)
        self.setMaximumHeight(320)

    def set_data(self, data):
        """data: [(label, regular_hours, overtime_hours), ...]"""
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        max_val = max((r + o) for _, r, o in self._data) if self._data else 1
        if max_val == 0:
            max_val = 1

        bar_height = min(28, max(16, (h - 40) // max(len(self._data), 1) - 6))
        label_width = 120
        value_width = 80
        chart_width = w - label_width - value_width - 20

        # Legend
        legend_y = 4
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(COLORS["info"])))
        painter.drawRoundedRect(label_width, legend_y, 12, 12, 2, 2)
        painter.setPen(QPen(QColor(tc('text_light'))))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(label_width + 16, legend_y + 10, "Regular")

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(COLORS["danger"])))
        painter.drawRoundedRect(label_width + 80, legend_y, 12, 12, 2, 2)
        painter.setPen(QPen(QColor(tc('text_light'))))
        painter.drawText(label_width + 96, legend_y + 10, "Overtime")

        y = 24
        for label, regular, overtime in self._data:
            # Label
            painter.setPen(QPen(QColor(tc('text'))))
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.drawText(QRect(4, y, label_width - 8, bar_height),
                             Qt.AlignRight | Qt.AlignVCenter, label[:16])

            bar_x = label_width

            # Background
            bar_bg = "#45475a" if _is_dark() else "#f3f4f6"
            painter.setBrush(QBrush(QColor(bar_bg)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_x, y + 2, chart_width, bar_height - 4, 4, 4)

            total = regular + overtime
            # Regular bar
            reg_width = int((regular / max_val) * chart_width) if max_val > 0 else 0
            reg_width = max(reg_width, 2) if regular > 0 else 0
            if reg_width > 0:
                painter.setBrush(QBrush(QColor(COLORS["info"])))
                painter.drawRoundedRect(bar_x, y + 2, reg_width, bar_height - 4, 4, 4)

            # Overtime bar (stacked)
            ot_width = int((overtime / max_val) * chart_width) if max_val > 0 else 0
            ot_width = max(ot_width, 2) if overtime > 0 else 0
            if ot_width > 0:
                painter.setBrush(QBrush(QColor(COLORS["danger"])))
                painter.drawRoundedRect(bar_x + reg_width, y + 2, ot_width, bar_height - 4, 4, 4)

            # Value text
            painter.setPen(QPen(QColor(tc('text_light'))))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                QRect(bar_x + chart_width + 4, y, value_width, bar_height),
                Qt.AlignLeft | Qt.AlignVCenter, f"{total:.1f}")

            y += bar_height + 6

        painter.end()


# ════════════════════════════════════════════════════════════════════════
# Dashboard Page
# ════════════════════════════════════════════════════════════════════════

class DashboardPage(QWidget):
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

        # ── Week navigation
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
        self.lbl_week.setFont(QFont("Segoe UI", 18, QFont.Bold))
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

        # ── KPI Cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.card_total_hrs = self._make_kpi_card("Total Hours", "0", COLORS["info"], "\u23F0")
        self.card_ot_hrs = self._make_kpi_card("Overtime Hours", "0", COLORS["warning"], "\u26A1")
        self.card_ot_pct = self._make_kpi_card("OT %", "0%", COLORS["danger"], "\U0001F4CA")
        self.card_labor_cost = self._make_kpi_card("Total Labor Cost", "$0", COLORS["success"], "\U0001F4B2")
        self.card_dls = self._make_kpi_card("DLS %", "0%", COLORS["info"], "\U0001F4C8")
        self.card_over40 = self._make_kpi_card("Officers Over 40hrs", "0", COLORS["danger"], "\u26A0")
        cards_row.addWidget(self.card_total_hrs)
        cards_row.addWidget(self.card_ot_hrs)
        cards_row.addWidget(self.card_ot_pct)
        cards_row.addWidget(self.card_labor_cost)
        cards_row.addWidget(self.card_dls)
        cards_row.addWidget(self.card_over40)
        layout.addLayout(cards_row)

        # ── Hours by Site chart
        chart_group = QGroupBox("Hours by Site (Regular vs Overtime)")
        chart_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        chart_lay = QVBoxLayout(chart_group)
        self.site_chart = StackedBarChartWidget()
        chart_lay.addWidget(self.site_chart)
        layout.addWidget(chart_group)

        # ── Top 10 Overtime Officers
        ot_group = QGroupBox("Top 10 Overtime Officers")
        ot_group.setStyleSheet(chart_group.styleSheet())
        ot_lay = QVBoxLayout(ot_group)

        self.ot_table = QTableWidget(0, 6)
        self.ot_table.setHorizontalHeaderLabels([
            "Name", "Site", "Regular", "OT", "Total", "OT %"
        ])
        hdr = self.ot_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, 6):
            hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self.ot_table.setColumnWidth(c, 100)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.ot_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ot_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ot_table.verticalHeader().setVisible(False)
        self.ot_table.setShowGrid(False)
        self.ot_table.setAlternatingRowColors(True)
        self.ot_table.setMinimumHeight(200)
        ot_lay.addWidget(self.ot_table)
        layout.addWidget(ot_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _make_kpi_card(self, title, value, color, icon_text):
        """Dashboard KPI card."""
        frame = QFrame()
        frame.setFixedHeight(110)
        frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border-radius: 10px;
                border-left: 5px solid {color};
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)

        text_lay = QVBoxLayout()
        text_lay.setSpacing(2)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; font-weight: 600;")
        lbl_val = QLabel(value)
        lbl_val.setFont(QFont("Segoe UI", 24, QFont.Bold))
        lbl_val.setStyleSheet(f"color: {tc('text')};")
        lbl_val.setObjectName("card_value")
        text_lay.addWidget(lbl_title)
        text_lay.addWidget(lbl_val)
        lay.addLayout(text_lay)
        lay.addStretch()

        lbl_icon = QLabel(icon_text)
        lbl_icon.setFont(QFont("Segoe UI", 22))
        lbl_icon.setStyleSheet(f"color: {color};")
        lbl_icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl_icon)

        return frame

    def _prev_week(self):
        d = date.fromisoformat(self._week_ending)
        self._week_ending = (d - timedelta(weeks=1)).isoformat()
        self.refresh()

    def _next_week(self):
        d = date.fromisoformat(self._week_ending)
        self._week_ending = (d + timedelta(weeks=1)).isoformat()
        self.refresh()

    def _ot_color(self, total_hours, threshold=40):
        """Return color based on OT threshold: green < 80%, yellow 80-100%, red > 100%."""
        pct = (total_hours / threshold * 100) if threshold > 0 else 0
        if pct > 100:
            return COLORS["danger"]
        elif pct >= 80:
            return COLORS["warning"]
        return COLORS["success"]

    def refresh(self):
        """Reload dashboard data."""
        we = self._week_ending
        self.lbl_week.setText(f"Week Ending: {we}")

        summary = data_manager.get_dashboard_summary(we)

        # Update KPI cards
        self.card_total_hrs.findChild(QLabel, "card_value").setText(
            f"{summary['total_hours']:.1f}")
        self.card_ot_hrs.findChild(QLabel, "card_value").setText(
            f"{summary['overtime_hours']:.1f}")
        self.card_ot_pct.findChild(QLabel, "card_value").setText(
            f"{summary['ot_percentage']:.1f}%")
        self.card_labor_cost.findChild(QLabel, "card_value").setText(
            f"${summary['total_pay']:,.0f}")
        self.card_dls.findChild(QLabel, "card_value").setText(
            f"{summary['dls_percentage']:.1f}%")
        self.card_over40.findChild(QLabel, "card_value").setText(
            str(summary['officers_over_40']))

        # Site chart
        site_bd = summary.get("site_breakdown", {})
        chart_data = sorted(
            [(s, d["regular_hours"], d["overtime_hours"]) for s, d in site_bd.items()],
            key=lambda x: -(x[1] + x[2])
        )[:12]
        self.site_chart.set_data(chart_data)

        # Top OT officers table
        top = summary.get("top_ot_officers", [])
        self.ot_table.setRowCount(len(top))
        for i, o in enumerate(top):
            self.ot_table.setItem(i, 0, QTableWidgetItem(o.get("officer_name", "")))
            self.ot_table.setItem(i, 1, QTableWidgetItem(o.get("site", "")))

            reg_item = QTableWidgetItem(f"{o.get('regular_hours', 0):.1f}")
            reg_item.setTextAlignment(Qt.AlignCenter)
            self.ot_table.setItem(i, 2, reg_item)

            ot_item = QTableWidgetItem(f"{o.get('overtime_hours', 0):.1f}")
            ot_item.setTextAlignment(Qt.AlignCenter)
            ot_val = o.get("overtime_hours", 0)
            if ot_val > 0:
                ot_item.setForeground(QColor(COLORS["danger"]))
                ot_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.ot_table.setItem(i, 3, ot_item)

            total = o.get("total_hours", 0)
            total_item = QTableWidgetItem(f"{total:.1f}")
            total_item.setTextAlignment(Qt.AlignCenter)
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            color = self._ot_color(total)
            total_item.setForeground(QColor(color))
            self.ot_table.setItem(i, 4, total_item)

            ot_pct = (o.get("overtime_hours", 0) / total * 100) if total > 0 else 0
            pct_item = QTableWidgetItem(f"{ot_pct:.1f}%")
            pct_item.setTextAlignment(Qt.AlignCenter)
            if ot_pct > 20:
                pct_item.setForeground(QColor(COLORS["danger"]))
                pct_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.ot_table.setItem(i, 5, pct_item)

            self.ot_table.setRowHeight(i, 42)
