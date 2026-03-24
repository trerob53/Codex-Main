"""
Cerasus Hub -- Operations Module: Coverage Map Page
Visual weekly overview showing which sites are covered, partially covered, or uncovered.
"""

from datetime import date as dt_date, datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.config import COLORS, tc, _is_dark, btn_style
from src.modules.operations import data_manager
from src import shared_data


DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

# Coverage status colors
STATUS_COLORS = {
    "covered":   {"light": "#059669", "dark": "#40C790", "bg_light": "#D1FAE5", "bg_dark": "#1A3D2E"},
    "partial":   {"light": "#D97706", "dark": "#F0A030", "bg_light": "#FEF3C7", "bg_dark": "#3D3020"},
    "uncovered": {"light": "#C8102E", "dark": "#E8384F", "bg_light": "#FDE8EB", "bg_dark": "#3D1C22"},
    "none":      {"light": "#9CA3AF", "dark": "#6B7280", "bg_light": "#F3F4F6", "bg_dark": "#252540"},
}


def _status_fg(status_key: str) -> str:
    c = STATUS_COLORS[status_key]
    return c["dark"] if _is_dark() else c["light"]


def _status_bg(status_key: str) -> str:
    c = STATUS_COLORS[status_key]
    return c["bg_dark"] if _is_dark() else c["bg_light"]


# ==============================================================================
# Coverage Map Page
# ==============================================================================

class CoverageMapPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._week_offset = 0
        self._build()

    # -- Layout ----------------------------------------------------------------

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(30, 24, 30, 24)
        self._main_layout.setSpacing(16)

        # -- Header row -------------------------------------------------------
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title = QLabel("Coverage Map \u2014 Weekly Overview")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        header_row.addWidget(title)
        header_row.addStretch()

        self._main_layout.addLayout(header_row)

        # -- Week Navigation ---------------------------------------------------
        week_row = QHBoxLayout()
        week_row.setSpacing(12)

        self.btn_prev = QPushButton("\u2039  Prev Week")
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
        week_row.addWidget(self.btn_prev)

        week_row.addStretch()

        self.lbl_week = QLabel("")
        self.lbl_week.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.lbl_week.setStyleSheet(f"color: {tc('text')};")
        self.lbl_week.setAlignment(Qt.AlignCenter)
        week_row.addWidget(self.lbl_week)

        btn_today = QPushButton("Today")
        btn_today.setCursor(Qt.PointingHandCursor)
        btn_today.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        btn_today.setFixedHeight(34)
        btn_today.clicked.connect(self._go_today)
        week_row.addWidget(btn_today)

        week_row.addStretch()

        self.btn_next = QPushButton("Next Week  \u203A")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setStyleSheet(self.btn_prev.styleSheet())
        self.btn_next.clicked.connect(self._next_week)
        week_row.addWidget(self.btn_next)

        self._main_layout.addLayout(week_row)

        # -- Legend row --------------------------------------------------------
        legend_row = QHBoxLayout()
        legend_row.setSpacing(20)
        legend_row.addStretch()

        for label_text, status_key in [
            ("Fully Covered", "covered"),
            ("Partial Coverage", "partial"),
            ("No Coverage", "uncovered"),
            ("No Requests", "none"),
        ]:
            dot = QLabel("\u25CF")
            dot.setFont(QFont("Segoe UI", 14))
            dot.setStyleSheet(f"color: {_status_fg(status_key)};")
            legend_row.addWidget(dot)

            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 13))
            lbl.setStyleSheet(f"color: {tc('text_light')};")
            legend_row.addWidget(lbl)

        legend_row.addStretch()
        self._main_layout.addLayout(legend_row)

        # -- Grid container (cards go here) ------------------------------------
        self._grid_container = QVBoxLayout()
        self._grid_container.setSpacing(16)
        self._main_layout.addLayout(self._grid_container)

        self._main_layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # -- Week helpers ----------------------------------------------------------

    def _week_start(self) -> dt_date:
        """Return the Sunday of the current display week."""
        today = dt_date.today()
        days_since_sun = (today.weekday() + 1) % 7
        sunday = today - timedelta(days=days_since_sun)
        return sunday + timedelta(weeks=self._week_offset)

    def _week_dates(self) -> list:
        """Return list of 7 date objects (Sun-Sat) for current display week."""
        start = self._week_start()
        return [start + timedelta(days=i) for i in range(7)]

    def _prev_week(self):
        self._week_offset -= 1
        self.refresh()

    def _next_week(self):
        self._week_offset += 1
        self.refresh()

    def _go_today(self):
        self._week_offset = 0
        self.refresh()

    # -- _init_page (called by framework on page show) -------------------------

    def _init_page(self, app_state):
        self.app_state = app_state
        self.refresh()

    # -- Refresh / populate ----------------------------------------------------

    def refresh(self):
        """Reload all data and rebuild the site cards."""
        dates = self._week_dates()
        today_str = dt_date.today().strftime("%Y-%m-%d")

        # Update week label
        self.lbl_week.setText(
            f"{dates[0].strftime('%b %d')} \u2013 {dates[6].strftime('%b %d, %Y')}"
        )

        # Fetch data
        sites = shared_data.get_site_names()
        all_assignments = data_manager.get_all_assignments()
        all_requests = data_manager.get_all_requests()

        date_strs = [d.strftime("%Y-%m-%d") for d in dates]
        start_str = date_strs[0]
        end_str = date_strs[6]

        # Filter assignments to this week
        week_assignments = [
            a for a in all_assignments
            if start_str <= a.get("date", "") <= end_str
        ]

        # Filter requests to this week
        week_requests = [
            r for r in all_requests
            if start_str <= r.get("date", "") <= end_str
        ]

        # Build lookups: (site_name, date) -> [items]
        asn_lookup = {}
        for a in week_assignments:
            key = (a.get("site_name", ""), a.get("date", ""))
            asn_lookup.setdefault(key, []).append(a)

        req_lookup = {}
        for r in week_requests:
            key = (r.get("site_name", ""), r.get("date", ""))
            req_lookup.setdefault(key, []).append(r)

        # Clear existing cards
        while self._grid_container.count():
            item = self._grid_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Build a card per site
        for site in sites:
            site_name = site.get("name", "")
            if not site_name:
                continue
            card = self._build_site_card(
                site_name, dates, date_strs, today_str,
                asn_lookup, req_lookup,
            )
            self._grid_container.addWidget(card)

        # If no sites at all
        if not sites:
            empty_lbl = QLabel("No active sites found.")
            empty_lbl.setFont(QFont("Segoe UI", 14))
            empty_lbl.setStyleSheet(f"color: {tc('text_light')};")
            empty_lbl.setAlignment(Qt.AlignCenter)
            self._grid_container.addWidget(empty_lbl)

    # -- Build a single site card ----------------------------------------------

    def _build_site_card(
        self, site_name, dates, date_strs, today_str, asn_lookup, req_lookup
    ) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame#siteCard {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 10px;
            }}
        """)
        card.setObjectName("siteCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        card_layout.setSpacing(10)

        # Site name header
        name_lbl = QLabel(site_name)
        name_lbl.setFont(QFont("Segoe UI", 16, QFont.Bold))
        name_lbl.setStyleSheet(f"color: {tc('text')};")
        card_layout.addWidget(name_lbl)

        # Day grid
        grid = QGridLayout()
        grid.setSpacing(6)

        total_hours = 0.0

        # Header row: day names
        for col, d in enumerate(dates):
            d_str = date_strs[col]
            day_name = DAY_NAMES[col]
            header_text = f"{day_name}\n{d.strftime('%m/%d')}"
            hdr = QLabel(header_text)
            hdr.setFont(QFont("Segoe UI", 11, QFont.Bold))
            hdr.setAlignment(Qt.AlignCenter)

            if d_str == today_str:
                hdr.setStyleSheet(f"""
                    color: {COLORS['accent']};
                    background: {_status_bg('none')};
                    border-radius: 4px; padding: 4px 2px;
                """)
            else:
                hdr.setStyleSheet(f"color: {tc('text_light')}; padding: 4px 2px;")
            grid.addWidget(hdr, 0, col)

        # Status cells row
        for col, d in enumerate(dates):
            d_str = date_strs[col]
            day_assignments = asn_lookup.get((site_name, d_str), [])
            day_requests = req_lookup.get((site_name, d_str), [])

            # Determine coverage status
            status_key, cell_text = self._compute_status(
                day_assignments, day_requests
            )

            # Accumulate hours from assignments
            for a in day_assignments:
                total_hours += self._calc_hours(
                    a.get("start_time", ""), a.get("end_time", "")
                )

            cell = QFrame()
            cell.setMinimumHeight(52)
            cell.setStyleSheet(f"""
                QFrame {{
                    background: {_status_bg(status_key)};
                    border: 1px solid {_status_fg(status_key)};
                    border-radius: 6px;
                }}
            """)

            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(4, 4, 4, 4)
            cell_layout.setSpacing(1)

            # Main status text
            main_lbl = QLabel(cell_text)
            main_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
            main_lbl.setStyleSheet(f"color: {_status_fg(status_key)}; background: transparent; border: none;")
            main_lbl.setAlignment(Qt.AlignCenter)
            main_lbl.setWordWrap(True)
            cell_layout.addWidget(main_lbl)

            # Tooltip with detail
            tooltip = self._build_tooltip(site_name, d_str, day_assignments, day_requests)
            cell.setToolTip(tooltip)

            grid.addWidget(cell, 1, col)

        # Make columns stretch equally
        for col in range(7):
            grid.setColumnStretch(col, 1)

        card_layout.addLayout(grid)

        # Total hours footer
        hours_lbl = QLabel(f"Total Scheduled: {total_hours:.1f} hrs this week")
        hours_lbl.setFont(QFont("Segoe UI", 12))
        hours_lbl.setStyleSheet(f"color: {tc('text_light')};")
        hours_lbl.setAlignment(Qt.AlignRight)
        card_layout.addWidget(hours_lbl)

        return card

    # -- Status computation ----------------------------------------------------

    def _compute_status(self, assignments: list, requests: list) -> tuple:
        """
        Return (status_key, display_text) for a site-day cell.

        Logic:
        - No requests AND no assignments -> ("none", "")
        - Has assignment(s) -> ("covered", officer name(s))
        - Has open request with assigned_officer -> ("covered", officer name)
        - Has open request status 'Open' (unfilled) -> ("uncovered", "OPEN")
        - Has request + some assignments but not all filled -> ("partial", "PARTIAL")
        """
        has_assignments = len(assignments) > 0
        open_requests = [r for r in requests if r.get("status", "") == "Open"]
        filled_requests = [
            r for r in requests
            if r.get("status", "") in ("Filled", "Closed", "Assigned")
        ]

        if not assignments and not requests:
            return ("none", "")

        if has_assignments and not open_requests:
            # Fully covered
            names = list({a.get("officer_name", "?") for a in assignments})
            display = "\n".join(names[:3])
            if len(names) > 3:
                display += f"\n+{len(names) - 3} more"
            return ("covered", display)

        if open_requests and has_assignments:
            # Some filled, some still open -> partial
            names = list({a.get("officer_name", "?") for a in assignments})
            display = "\n".join(names[:2])
            display += f"\n+{len(open_requests)} OPEN"
            return ("partial", display)

        if open_requests and not has_assignments:
            # Requests exist but nothing assigned
            if filled_requests:
                return ("partial", "PARTIAL")
            return ("uncovered", "OPEN")

        if filled_requests and not has_assignments:
            # Requests were filled (maybe via other mechanism)
            return ("covered", "Filled")

        # Fallback: has requests but no open ones and no assignments
        return ("none", "")

    # -- Helpers ---------------------------------------------------------------

    @staticmethod
    def _calc_hours(start: str, end: str) -> float:
        if not start or not end:
            return 0.0
        try:
            t1 = datetime.strptime(start, "%H:%M")
            t2 = datetime.strptime(end, "%H:%M")
            diff = (t2 - t1).total_seconds() / 3600
            if diff < 0:
                diff += 24
            return diff
        except Exception:
            return 0.0

    @staticmethod
    def _build_tooltip(site_name, date_str, assignments, requests) -> str:
        lines = [f"{site_name} — {date_str}"]
        if assignments:
            lines.append("")
            lines.append("Assignments:")
            for a in assignments:
                officer = a.get("officer_name", "?")
                st = a.get("start_time", "")
                et = a.get("end_time", "")
                time_str = f"{st}-{et}" if st and et else ""
                lines.append(f"  {officer}  {time_str}")
        if requests:
            lines.append("")
            lines.append("Requests:")
            for r in requests:
                status = r.get("status", "")
                reason = r.get("reason", "")
                assigned = r.get("assigned_officer", "")
                detail = f"  [{status}] {reason}"
                if assigned:
                    detail += f" -> {assigned}"
                lines.append(detail)
        if not assignments and not requests:
            lines.append("No activity scheduled.")
        return "\n".join(lines)
