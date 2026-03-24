"""
Cerasus Hub — Operations Module: Dashboard Page
Main dashboard with summary cards, officer utilization, charts, and activity feed.
"""

from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QGroupBox, QScrollArea, QApplication,
    QDateEdit,
)
from PySide6.QtCore import Qt, QRect, QDate
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush

from src.config import COLORS, DARK_COLORS, ROLE_ADMIN, build_dialog_stylesheet, tc, _is_dark, btn_style
from src.shared_widgets import BarChartWidget
from src.modules.operations import data_manager
from src import audit


class PieChartWidget(QWidget):
    """A simple pie/donut chart drawn with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # list of (label, value, color)
        self.setMinimumHeight(180)
        self.setMinimumWidth(200)

    def set_data(self, data):
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        total = sum(v for _, v, _ in self._data)
        if total == 0:
            return

        # Draw donut chart on left
        size = min(self.width() // 2, self.height()) - 20
        cx = size // 2 + 10
        cy = self.height() // 2
        rect = QRect(cx - size // 2, cy - size // 2, size, size)

        start_angle = 90 * 16  # start from top
        for label, value, color in self._data:
            span = int((value / total) * 360 * 16)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(color)))
            painter.drawPie(rect, start_angle, span)
            start_angle += span

        # Inner circle for donut effect
        inner_size = size * 55 // 100
        # Use theme-aware background for donut center
        center_color = "white"
        try:
            app = QApplication.instance()
            for toplevel in app.topLevelWidgets():
                if hasattr(toplevel, 'app_state') and toplevel.app_state.get("dark_mode"):
                    center_color = DARK_COLORS["card"]
                    break
        except Exception:
            pass
        painter.setBrush(QBrush(QColor(center_color)))
        painter.drawEllipse(cx - inner_size // 2, cy - inner_size // 2,
                            inner_size, inner_size)

        # Total in center
        painter.setPen(QPen(QColor(tc('primary'))))
        painter.setFont(QFont("Segoe UI", 16, QFont.Bold))
        painter.drawText(QRect(cx - inner_size // 2, cy - 14, inner_size, 28),
                         Qt.AlignCenter, str(total))

        # Legend on right
        legend_x = size + 30
        legend_y = 20
        for label, value, color in self._data:
            pct = (value / total * 100) if total > 0 else 0
            # Color dot
            painter.setBrush(QBrush(QColor(color)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(legend_x, legend_y + 2, 10, 10)
            # Label
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
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # ── Date range selector row
        date_range_row = QHBoxLayout()
        date_range_lbl = QLabel("Dashboard Date Range:")
        date_range_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        date_range_lbl.setStyleSheet(f"color: {tc('text_light')};")
        date_range_row.addWidget(date_range_lbl)

        date_range_row.addWidget(QLabel("From:"))
        self.dash_date_from = QDateEdit()
        self.dash_date_from.setCalendarPopup(True)
        self.dash_date_from.setDisplayFormat("yyyy-MM-dd")
        self.dash_date_from.setSpecialValueText("All Time")
        # Default to 1st of current month
        today = QDate.currentDate()
        self.dash_date_from.setDate(QDate(today.year(), today.month(), 1))
        date_range_row.addWidget(self.dash_date_from)

        date_range_row.addWidget(QLabel("To:"))
        self.dash_date_to = QDateEdit()
        self.dash_date_to.setCalendarPopup(True)
        self.dash_date_to.setDisplayFormat("yyyy-MM-dd")
        self.dash_date_to.setSpecialValueText("All Time")
        self.dash_date_to.setDate(today)
        date_range_row.addWidget(self.dash_date_to)

        btn_apply = QPushButton("Apply")
        btn_apply.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS.get("accent_hover", COLORS["accent"])))
        btn_apply.clicked.connect(self.refresh)
        date_range_row.addWidget(btn_apply)

        btn_reset = QPushButton("Reset")
        btn_reset.setStyleSheet(btn_style(tc("info"), "white", tc("primary")))
        btn_reset.clicked.connect(self._reset_date_range)
        date_range_row.addWidget(btn_reset)

        date_range_row.addStretch()
        layout.addLayout(date_range_row)

        # ── Top summary cards (Control Tower style)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        self.card_scheduled = self._make_big_card("Total Scheduled", "0.0", "This Week", COLORS["info"], "\u23F0")
        self.card_billable = self._make_big_card("Billable Hours", "0.0", "of Total", COLORS["success"], "\U0001F4B2")
        self.card_flex_capacity = self._make_big_card("Flex Capacity", "0.0", "0 hrs remaining this week", COLORS["warning"], "\u2693")
        self.card_requests = self._make_big_card("Pending PTO", "0", "Awaiting Approval", COLORS["warning"], "\u26A0")
        cards_row.addWidget(self.card_scheduled)
        cards_row.addWidget(self.card_billable)
        cards_row.addWidget(self.card_flex_capacity)
        cards_row.addWidget(self.card_requests)
        layout.addLayout(cards_row)

        # ── Staffing / Open Positions KPI cards
        pos_row = QHBoxLayout()
        pos_row.setSpacing(16)
        self.card_open_pos = self._make_big_card("Open Positions", "0", "Total unfilled", tc("info"), "\U0001F4CB")
        self.card_open_hrs = self._make_big_card("Open Hours/Wk", "0", "Weekly hours to fill", COLORS["warning"], "\u23F1")
        self.card_ot_exposure = self._make_big_card("Weekly OT Exposure", "$0", "Estimated OT cost", COLORS["danger"], "\U0001F4B0")
        self.card_avg_fill = self._make_big_card("Avg Days to Fill", "0", "Historical average", COLORS["success"], "\U0001F4C5")
        pos_row.addWidget(self.card_open_pos)
        pos_row.addWidget(self.card_open_hrs)
        pos_row.addWidget(self.card_ot_exposure)
        pos_row.addWidget(self.card_avg_fill)
        layout.addLayout(pos_row)

        # ── Officer Utilization table
        util_group = QGroupBox("Flex Team Utilization \u2014 Current Week")
        util_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {COLORS['info']};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 12px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        util_lay = QVBoxLayout(util_group)
        self.util_table = QTableWidget(0, 6)
        self.util_table.setHorizontalHeaderLabels([
            "Officer", "Scheduled", "Billable", "Anchor", "To 40hrs", "Alerts"
        ])
        self.util_table.setToolTip("View assignments on the Flex Board page")
        util_hdr = self.util_table.horizontalHeader()
        util_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            util_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self.util_table.setColumnWidth(c, 100)
        util_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['info']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid #3b82f6;
                min-height: 32px;
            }}
        """)
        self.util_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.util_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.util_table.verticalHeader().setVisible(False)
        self.util_table.setShowGrid(False)
        self.util_table.setAlternatingRowColors(True)
        self.util_table.setMinimumHeight(200)
        util_lay.addWidget(self.util_table)
        layout.addWidget(util_group)

        # ── Analytics section header
        analytics_lbl = QLabel("Analytics")
        analytics_lbl.setFont(QFont("Segoe UI", 16, QFont.Bold))
        analytics_lbl.setStyleSheet(f"color: {tc('text_light')}; margin-top: 4px;")
        layout.addWidget(analytics_lbl)

        # ── Charts row
        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        pto_status_group = QGroupBox("PTO Status")
        pto_status_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 16px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        pto_status_lay = QVBoxLayout(pto_status_group)
        self.pto_status_pie = PieChartWidget()
        pto_status_lay.addWidget(self.pto_status_pie)
        charts_row.addWidget(pto_status_group)

        site_group = QGroupBox("Assignments by Site")
        site_group.setStyleSheet(pto_status_group.styleSheet())
        site_lay = QVBoxLayout(site_group)
        self.site_chart = BarChartWidget()
        site_lay.addWidget(self.site_chart)
        charts_row.addWidget(site_group)
        layout.addLayout(charts_row)

        # ── Weekly Hours by Site bar chart
        weekly_hours_group = QGroupBox("Weekly Hours by Site (Current Week)")
        weekly_hours_group.setStyleSheet(pto_status_group.styleSheet())
        wh_lay = QVBoxLayout(weekly_hours_group)
        self.weekly_hours_chart = BarChartWidget()
        self.weekly_hours_chart.setMinimumHeight(200)
        wh_lay.addWidget(self.weekly_hours_chart)
        layout.addWidget(weekly_hours_group)

        # ── Recent activity
        grp = QGroupBox("Recent Activity")
        grp.setStyleSheet(pto_status_group.styleSheet())
        grp_layout = QVBoxLayout(grp)
        self.activity_table = QTableWidget(0, 4)
        self.activity_table.setHorizontalHeaderLabels(["Time", "Event", "User", "Details"])
        hdr = self.activity_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.activity_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.activity_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.activity_table.setAlternatingRowColors(True)
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.setMaximumHeight(220)
        grp_layout.addWidget(self.activity_table)
        layout.addWidget(grp)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _make_big_card(self, title, value, subtitle, color, icon_text):
        """Control Tower-style dashboard card with big number and subtitle."""
        frame = QFrame()
        frame.setFixedHeight(120)
        frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border-radius: 10px;
                border-left: 5px solid {color};
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(18, 14, 18, 14)

        # Left: text
        text_lay = QVBoxLayout()
        text_lay.setSpacing(2)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px; font-weight: 600;")
        lbl_val = QLabel(value)
        lbl_val.setFont(QFont("Segoe UI", 32, QFont.Bold))
        lbl_val.setStyleSheet(f"color: {tc('text')};")
        lbl_val.setObjectName("card_value")
        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        lbl_sub.setObjectName("card_sub")
        text_lay.addWidget(lbl_title)
        text_lay.addWidget(lbl_val)
        text_lay.addWidget(lbl_sub)
        lay.addLayout(text_lay)

        lay.addStretch()

        # Right: icon
        lbl_icon = QLabel(icon_text)
        lbl_icon.setFont(QFont("Segoe UI", 28))
        lbl_icon.setStyleSheet(f"color: {color};")
        lbl_icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl_icon)

        return frame

    def _reset_date_range(self):
        """Clear date range back to all-time (use minimum dates as sentinel)."""
        self.dash_date_from.setDate(self.dash_date_from.minimumDate())
        self.dash_date_to.setDate(self.dash_date_to.minimumDate())
        self.refresh()

    def _get_dash_date_range(self):
        """Return (start_str, end_str) or ('', '') if reset to all-time."""
        min_from = self.dash_date_from.minimumDate()
        min_to = self.dash_date_to.minimumDate()
        d_from = self.dash_date_from.date()
        d_to = self.dash_date_to.date()
        if d_from == min_from and d_to == min_to:
            return "", ""
        return d_from.toString("yyyy-MM-dd"), d_to.toString("yyyy-MM-dd")

    def refresh(self):
        """Reload dashboard data, optionally filtered by the date range selector."""
        from datetime import date as dt_date, timedelta as td

        # Calculate current Sun-Sat week (for utilization table)
        today = dt_date.today()
        days_since_sun = (today.weekday() + 1) % 7
        week_start = today - td(days=days_since_sun)
        week_end = week_start + td(days=6)
        start_str = week_start.strftime("%Y-%m-%d")
        end_str = week_end.strftime("%Y-%m-%d")

        # Dashboard date range for summary stats
        dash_start, dash_end = self._get_dash_date_range()
        has_range = bool(dash_start and dash_end)

        # All assignments (used for utilization + stats)
        all_assignments = data_manager.get_all_assignments()

        # Filter assignments for summary cards based on dashboard date range
        if has_range:
            range_assignments = [
                a for a in all_assignments
                if dash_start <= a.get("date", "") <= dash_end
            ]
        else:
            # Default: current week
            range_assignments = [
                a for a in all_assignments
                if start_str <= a.get("date", "") <= end_str
            ]

        # Week assignments for utilization table (always current week)
        week_assignments = [
            a for a in all_assignments
            if start_str <= a.get("date", "") <= end_str
        ]

        # Calculate hours from the selected range
        total_hours = 0.0
        billable_hours = 0.0
        for a in range_assignments:
            h = float(a.get("hours", 0))
            total_hours += h
            if a.get("assignment_type") == "Billable":
                billable_hours += h

        # Flex capacity: total flex officers x 40 minus total scheduled hours
        active_officers = data_manager.get_ops_officers()
        flex_officers = [
            o for o in active_officers
            if "flex" in (o.get("job_title") or "").lower()
            or "flex" in (o.get("role") or "").lower()
        ]
        flex_total_capacity = len(flex_officers) * 40
        flex_scheduled = 0.0
        for a in range_assignments:
            if a.get("officer_name", "") in [f.get("name", "") for f in flex_officers]:
                flex_scheduled += float(a.get("hours", 0))
        flex_remaining = max(0, flex_total_capacity - flex_scheduled)

        # Pending PTO count (filtered by date range if set)
        all_pto = data_manager.get_all_pto()
        if has_range:
            all_pto_filtered = [
                p for p in all_pto
                if dash_start <= p.get("start_date", "") <= dash_end
                or dash_start <= p.get("end_date", "") <= dash_end
            ]
        else:
            all_pto_filtered = all_pto
        pending_pto = sum(1 for p in all_pto_filtered if p.get("status") == "Pending")

        # Update cards
        range_label = f"{dash_start} to {dash_end}" if has_range else "This Week"
        self.card_scheduled.findChild(QLabel, "card_value").setText(f"{total_hours:.1f}")
        self.card_scheduled.findChild(QLabel, "card_sub").setText(range_label)

        self.card_billable.findChild(QLabel, "card_value").setText(f"{billable_hours:.1f}")
        pct_b = f"{(billable_hours / total_hours * 100):.1f}% of Total" if total_hours > 0 else "0.0% of Total"
        self.card_billable.findChild(QLabel, "card_sub").setText(pct_b)

        self.card_flex_capacity.findChild(QLabel, "card_value").setText(f"{flex_remaining:.1f}")
        flex_sub = f"{flex_remaining:.0f} hrs remaining" if has_range else f"{flex_remaining:.0f} hrs remaining this week"
        self.card_flex_capacity.findChild(QLabel, "card_sub").setText(flex_sub)

        self.card_requests.findChild(QLabel, "card_value").setText(str(pending_pto))

        # PTO Status pie chart (Pending/Approved/Denied from ops_pto_entries)
        pto_status_counts = {"Pending": 0, "Approved": 0, "Denied": 0}
        for p in all_pto_filtered:
            status = p.get("status", "")
            if status in pto_status_counts:
                pto_status_counts[status] += 1
        pto_status_colors = {
            "Pending": COLORS["warning"],
            "Approved": COLORS["success"],
            "Denied": COLORS["danger"],
        }
        pto_pie_data = [
            (s, c, pto_status_colors.get(s, "#6b7280"))
            for s, c in pto_status_counts.items()
            if c > 0
        ]
        self.pto_status_pie.set_data(pto_pie_data)

        # Site bar chart — aggregate assignment counts per site
        site_counts = {}
        for a in range_assignments:
            sn = a.get("site_name", "")
            if sn:
                site_counts[sn] = site_counts.get(sn, 0) + 1
        site_data = [(site, count, tc("info"))
                     for site, count in sorted(site_counts.items(), key=lambda x: -x[1])[:10]]
        self.site_chart.set_data(site_data)

        # Weekly Hours by Site bar chart (always current week)
        site_hours = {}
        for a in week_assignments:
            sn = a.get("site_name", "")
            if sn:
                site_hours[sn] = site_hours.get(sn, 0.0) + float(a.get("hours", 0))
        weekly_hours_data = [
            (site, round(hrs, 1), COLORS["success"])
            for site, hrs in sorted(site_hours.items(), key=lambda x: -x[1])[:10]
        ]
        self.weekly_hours_chart.set_data(weekly_hours_data)

        # Officer Utilization table
        self.util_table.setRowCount(len(active_officers))
        for i, off in enumerate(active_officers):
            name = off.get("name", "")
            role = off.get("role", "")
            guaranteed = float(off.get("weekly_hours", 40))

            # Calculate hours for current week
            off_asn = [a for a in week_assignments if a.get("officer_name") == name]
            sched = sum(float(a.get("hours", 0)) for a in off_asn)
            bill = sum(float(a.get("hours", 0)) for a in off_asn if a.get("assignment_type") == "Billable")
            anch = sum(float(a.get("hours", 0)) for a in off_asn if "Anchor" in a.get("assignment_type", ""))
            to_40 = max(0, guaranteed - sched)

            # Officer name + role
            name_widget = QWidget()
            name_lay = QVBoxLayout(name_widget)
            name_lay.setContentsMargins(8, 4, 4, 4)
            name_lay.setSpacing(0)
            n_lbl = QLabel(name)
            n_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
            n_lbl.setStyleSheet(f"color: {tc('text')};")
            r_lbl = QLabel(role)
            r_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
            name_lay.addWidget(n_lbl)
            name_lay.addWidget(r_lbl)
            self.util_table.setCellWidget(i, 0, name_widget)

            # Scheduled — heat map: green >80%, yellow 50-80%, red <50%
            s_item = QTableWidgetItem(f"{sched:.1f}")
            s_item.setTextAlignment(Qt.AlignCenter)
            s_item.setFont(QFont("Segoe UI", 14, QFont.Bold))
            sched_pct = (sched / guaranteed * 100) if guaranteed > 0 else 0
            if sched_pct >= 80:
                s_item.setBackground(QColor(COLORS["success"]))
                s_item.setForeground(QColor("white"))
            elif sched_pct >= 50:
                s_item.setBackground(QColor(COLORS["warning"]))
                s_item.setForeground(QColor("white"))
            elif sched > 0:
                s_item.setBackground(QColor(COLORS["danger"]))
                s_item.setForeground(QColor("white"))
            self.util_table.setItem(i, 1, s_item)

            # Billable — heat map: green >80%, yellow 50-80%, red <50%
            b_item = QTableWidgetItem(f"{bill:.1f}")
            b_item.setTextAlignment(Qt.AlignCenter)
            b_item.setFont(QFont("Segoe UI", 14, QFont.Bold))
            bill_pct = (bill / guaranteed * 100) if guaranteed > 0 else 0
            if bill_pct >= 80:
                b_item.setBackground(QColor(COLORS["success"]))
                b_item.setForeground(QColor("white"))
            elif bill_pct >= 50:
                b_item.setBackground(QColor(COLORS["warning"]))
                b_item.setForeground(QColor("white"))
            elif bill > 0:
                b_item.setBackground(QColor(COLORS["danger"]))
                b_item.setForeground(QColor("white"))
            self.util_table.setItem(i, 2, b_item)

            # Anchor
            a_item = QTableWidgetItem(f"{anch:.1f}")
            a_item.setTextAlignment(Qt.AlignCenter)
            a_item.setFont(QFont("Segoe UI", 14, QFont.Bold))
            self.util_table.setItem(i, 3, a_item)

            # To 40hrs
            t_item = QTableWidgetItem(f"{to_40:.1f}")
            t_item.setTextAlignment(Qt.AlignCenter)
            t_item.setFont(QFont("Segoe UI", 14, QFont.Bold))
            if to_40 > 0:
                t_item.setForeground(QColor(COLORS["success"]))
            self.util_table.setItem(i, 4, t_item)

            # Alerts
            if sched > 40:
                alert_item = QTableWidgetItem("OT")
                alert_item.setBackground(QColor(COLORS["warning"]))
                alert_item.setForeground(QColor("white"))
                alert_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            elif sched == 0:
                alert_item = QTableWidgetItem("\u2014")
                alert_item.setForeground(QColor(tc("text_light")))
            else:
                alert_item = QTableWidgetItem("\u2014")
                alert_item.setForeground(QColor(COLORS["info"]))
            alert_item.setTextAlignment(Qt.AlignCenter)
            self.util_table.setItem(i, 5, alert_item)
            self.util_table.setRowHeight(i, 64)

        # ── Open Positions KPIs
        pos_kpis = data_manager.get_position_kpis()
        self.card_open_pos.findChild(QLabel, "card_value").setText(str(pos_kpis.get("total_open", 0)))
        self.card_open_hrs.findChild(QLabel, "card_value").setText(f"{pos_kpis.get('total_hours', 0):.1f}")
        ot_val = pos_kpis.get("ot_cost", 0)
        self.card_ot_exposure.findChild(QLabel, "card_value").setText(f"${ot_val:,.0f}")
        avg_fill = pos_kpis.get("avg_days_to_fill", 0)
        self.card_avg_fill.findChild(QLabel, "card_value").setText(f"{avg_fill:.0f}" if avg_fill else "N/A")

        # Recent activity
        events = audit.get_log("operations", limit=10)
        self.activity_table.setRowCount(len(events))
        for i, ev in enumerate(events):
            ts = ev.get("timestamp", "")[:19].replace("T", " ")
            self.activity_table.setItem(i, 0, QTableWidgetItem(ts))
            self.activity_table.setItem(i, 1, QTableWidgetItem(ev.get("event_type", "")))
            self.activity_table.setItem(i, 2, QTableWidgetItem(ev.get("username", "")))
            self.activity_table.setItem(i, 3, QTableWidgetItem(ev.get("details", "")))
