"""
Cerasus Hub -- Incidents Module: Dashboard Page
KPI cards, charts by type/site, severity breakdown, and recent incidents table.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QGroupBox, QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, tc, _is_dark, btn_style
from src.shared_widgets import make_stat_card, BarChartWidget
from src.modules.incidents import data_manager


# ── Severity color helper ─────────────────────────────────────────────

SEVERITY_COLORS = {
    "Low": "#059669",       # green / success
    "Medium": "#D97706",    # warning / amber
    "High": "#EA580C",      # orange
    "Critical": "#DC2626",  # red / danger
}

STATUS_COLORS = {
    "Open": "#2563EB",
    "Under Investigation": "#D97706",
    "Resolved": "#059669",
    "Closed": "#6B7280",
}


def _severity_color(severity: str) -> str:
    return SEVERITY_COLORS.get(severity, "#6B7280")


def _status_color(status: str) -> str:
    return STATUS_COLORS.get(status, "#6B7280")


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
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(20)

        # ── Header
        header = QLabel("Incident Dashboard")
        header.setFont(QFont("Segoe UI", 22, QFont.Bold))
        header.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(header)

        # ── KPI stat cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        self.card_total = make_stat_card("Total Incidents", "0", tc("info"))
        self.card_open = make_stat_card("Open", "0", tc("warning"))
        self.card_investigating = make_stat_card("Under Investigation", "0", tc("accent"))
        self.card_critical = make_stat_card("Critical", "0", tc("danger"))
        cards_row.addWidget(self.card_total)
        cards_row.addWidget(self.card_open)
        cards_row.addWidget(self.card_investigating)
        cards_row.addWidget(self.card_critical)
        layout.addLayout(cards_row)

        # ── Charts row
        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        # Incidents by Type
        type_group = QGroupBox("Incidents by Type")
        type_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        type_lay = QVBoxLayout(type_group)
        self.type_chart = BarChartWidget()
        type_lay.addWidget(self.type_chart)
        charts_row.addWidget(type_group)

        # Incidents by Site
        site_group = QGroupBox("Incidents by Site")
        site_group.setStyleSheet(type_group.styleSheet())
        site_lay = QVBoxLayout(site_group)
        self.site_chart = BarChartWidget()
        site_lay.addWidget(self.site_chart)
        charts_row.addWidget(site_group)
        layout.addLayout(charts_row)

        # ── Severity Breakdown
        sev_group = QGroupBox("Severity Breakdown")
        sev_group.setStyleSheet(type_group.styleSheet())
        sev_lay = QHBoxLayout(sev_group)
        sev_lay.setSpacing(16)
        self.sev_labels = {}
        for sev in ["Low", "Medium", "High", "Critical"]:
            card = QFrame()
            card.setFixedHeight(80)
            card.setStyleSheet(f"""
                QFrame {{
                    background: {tc('card')};
                    border-radius: 8px;
                    border-left: 5px solid {_severity_color(sev)};
                    border: 1px solid {tc('border')};
                    border-left: 5px solid {_severity_color(sev)};
                }}
            """)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(14, 8, 14, 8)
            c_lay.setSpacing(2)
            lbl_title = QLabel(sev)
            lbl_title.setStyleSheet(f"color: {_severity_color(sev)}; font-size: 13px; font-weight: 600; border: none;")
            lbl_val = QLabel("0")
            lbl_val.setFont(QFont("Segoe UI", 24, QFont.Bold))
            lbl_val.setStyleSheet(f"color: {tc('text')}; border: none;")
            c_lay.addWidget(lbl_title)
            c_lay.addWidget(lbl_val)
            self.sev_labels[sev] = lbl_val
            sev_lay.addWidget(card)
        layout.addWidget(sev_group)

        # ── Recent Incidents table
        recent_group = QGroupBox("Recent Incidents")
        recent_group.setStyleSheet(type_group.styleSheet())
        recent_lay = QVBoxLayout(recent_group)

        self.recent_table = QTableWidget(0, 5)
        self.recent_table.setHorizontalHeaderLabels([
            "Date", "Type", "Site", "Severity", "Status"
        ])
        hdr = self.recent_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self.recent_table.setColumnWidth(0, 110)
        self.recent_table.setColumnWidth(3, 100)
        self.recent_table.setColumnWidth(4, 140)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.recent_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setShowGrid(False)
        self.recent_table.setMaximumHeight(320)
        recent_lay.addWidget(self.recent_table)
        layout.addWidget(recent_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _update_card(self, card: QFrame, value: str):
        """Update the value label inside a stat card."""
        for child in card.findChildren(QLabel):
            try:
                font = child.font()
                if font.pointSize() >= 24 or font.pixelSize() >= 24:
                    child.setText(value)
                    return
            except Exception:
                pass
        labels = card.findChildren(QLabel)
        if len(labels) >= 2:
            labels[1].setText(value)

    def refresh(self):
        summary = data_manager.get_dashboard_summary()

        # KPI cards
        self._update_card(self.card_total, str(summary["total"]))
        self._update_card(self.card_open, str(summary["status_counts"].get("Open", 0)))
        self._update_card(self.card_investigating, str(summary["status_counts"].get("Under Investigation", 0)))
        self._update_card(self.card_critical, str(summary["severity_counts"].get("Critical", 0)))

        # Severity breakdown
        for sev in ["Low", "Medium", "High", "Critical"]:
            self.sev_labels[sev].setText(str(summary["severity_counts"].get(sev, 0)))

        # Type bar chart
        type_data = [
            (t[:16], c, tc("info"))
            for t, c in sorted(summary["type_counts"].items(), key=lambda x: -x[1])[:10]
        ]
        self.type_chart.set_data(type_data)

        # Site bar chart
        site_data = [
            (s[:16], c, tc("accent"))
            for s, c in sorted(summary["site_counts"].items(), key=lambda x: -x[1])[:10]
        ]
        self.site_chart.set_data(site_data)

        # Recent incidents table
        recent = summary["recent"][:15]
        self.recent_table.setRowCount(len(recent))
        for i, inc in enumerate(recent):
            date_str = inc.get("incident_date", "")
            self.recent_table.setItem(i, 0, QTableWidgetItem(date_str))
            self.recent_table.setItem(i, 1, QTableWidgetItem(inc.get("incident_type", "")))
            self.recent_table.setItem(i, 2, QTableWidgetItem(inc.get("site", "")))

            # Severity with color
            sev = inc.get("severity", "")
            sev_item = QTableWidgetItem(sev)
            sev_item.setTextAlignment(Qt.AlignCenter)
            sev_item.setForeground(QColor(_severity_color(sev)))
            sev_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.recent_table.setItem(i, 3, sev_item)

            # Status with color
            status = inc.get("status", "")
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QColor(_status_color(status)))
            status_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.recent_table.setItem(i, 4, status_item)
