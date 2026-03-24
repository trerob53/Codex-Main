"""
Cerasus Hub -- Operations Module: Flex Board Page
Real-time weekly dispatch grid showing where every flex officer is assigned.
"""

from datetime import date as dt_date, datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QComboBox, QMessageBox, QAbstractItemView, QScrollArea,
    QTimeEdit, QDateEdit, QDialog, QFormLayout, QDialogButtonBox,
)
from PySide6.QtCore import Qt, QDate, QTime, QTimer
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, tc, _is_dark, btn_style
from src.modules.operations import data_manager
from src import audit


# -- Site color palette --------------------------------------------------------

SITE_COLORS = [
    "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
    "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1",
]


def _site_color(site_name: str) -> str:
    """Deterministic color for a site name."""
    return SITE_COLORS[hash(site_name) % len(SITE_COLORS)]


DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


# ==============================================================================
# Cell Widget -- renders assignment/PTO/available state inside grid
# ==============================================================================

class FlexCellWidget(QWidget):
    """
    Renders the content for a single officer-day cell in the grid.
    States: available, assigned (one or more), PTO.
    """

    def __init__(self, assignments: list, pto_entries: list, parent=None):
        super().__init__(parent)
        self._build(assignments, pto_entries)

    def _build(self, assignments: list, pto_entries: list):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        # PTO entries
        for pto in pto_entries:
            pto_type = pto.get("pto_type", "PTO")
            status = pto.get("status", "")
            badge = QLabel(f"\u274C PTO ({pto_type})")
            badge.setAlignment(Qt.AlignCenter)
            badge.setFont(QFont("Segoe UI", 11, QFont.Bold))
            badge.setStyleSheet(f"""
                QLabel {{
                    background: {COLORS['danger_light'] if not _is_dark() else '#3D1C22'};
                    color: {COLORS['danger']};
                    border-radius: 4px;
                    padding: 4px 8px;
                }}
            """)
            badge.setWordWrap(True)
            layout.addWidget(badge)

            # Tooltip for PTO cell
            start_date = pto.get("start_date", "")
            end_date = pto.get("end_date", "")
            self.setToolTip(f"PTO: {pto_type}\n{start_date} to {end_date}")

        # Assignments
        for asn in assignments:
            site = asn.get("site_name", "Unknown")
            start = asn.get("start_time", "")
            end = asn.get("end_time", "")
            color = _site_color(site)
            time_str = f"{start}-{end}" if start and end else ""

            # Calculate hours for tooltip
            hours_str = ""
            if start and end:
                try:
                    t1 = datetime.strptime(start, "%H:%M")
                    t2 = datetime.strptime(end, "%H:%M")
                    diff = (t2 - t1).total_seconds() / 3600
                    if diff < 0:
                        diff += 24
                    hours_str = f"{diff:.1f}"
                except Exception:
                    hours_str = ""

            container = QWidget()
            container.setStyleSheet(f"""
                QWidget {{
                    background: {color};
                    border-radius: 4px;
                }}
            """)
            c_lay = QVBoxLayout(container)
            c_lay.setContentsMargins(6, 4, 6, 4)
            c_lay.setSpacing(1)

            site_lbl = QLabel(site)
            site_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
            site_lbl.setStyleSheet("color: white; background: transparent;")
            site_lbl.setAlignment(Qt.AlignCenter)
            site_lbl.setWordWrap(True)
            c_lay.addWidget(site_lbl)

            if time_str:
                time_lbl = QLabel(time_str)
                time_lbl.setFont(QFont("Segoe UI", 10))
                time_lbl.setStyleSheet("color: rgba(255,255,255,0.85); background: transparent;")
                time_lbl.setAlignment(Qt.AlignCenter)
                c_lay.addWidget(time_lbl)

            layout.addWidget(container)

            # Tooltip for assigned cell
            tip = f"Site: {site}\nTime: {time_str}"
            if hours_str:
                tip += f"\nHours: {hours_str}"
            self.setToolTip(tip)

        # Available (no PTO and no assignments)
        if not assignments and not pto_entries:
            avail = QLabel("\u2714 Available")
            avail.setAlignment(Qt.AlignCenter)
            avail.setFont(QFont("Segoe UI", 11, QFont.Bold))
            avail.setStyleSheet(f"""
                QLabel {{
                    background: {COLORS['success_light'] if not _is_dark() else '#1A3D2E'};
                    color: {COLORS['success']};
                    border-radius: 4px;
                    padding: 4px 8px;
                }}
            """)
            layout.addWidget(avail)
            self.setToolTip("Double-click to assign")

        layout.addStretch()


# ==============================================================================
# Flex Board Page
# ==============================================================================

class FlexBoardPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._week_offset = 0
        self._build()

        # Auto-refresh timer (60 seconds)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(60_000)

    # -- Layout ----------------------------------------------------------------

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(30, 24, 30, 24)
        main_layout.setSpacing(16)

        # -- Header row -------------------------------------------------------
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title = QLabel("Flex Board \u2014 Live Dispatch")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        header_row.addWidget(title)

        header_row.addStretch()

        self.lbl_date = QLabel(dt_date.today().strftime("%A, %B %d, %Y"))
        self.lbl_date.setFont(QFont("Segoe UI", 14))
        self.lbl_date.setStyleSheet(f"color: {tc('text_light')};")
        header_row.addWidget(self.lbl_date)

        btn_refresh = QPushButton("\u21BB  Refresh")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.setStyleSheet(btn_style(COLORS["info"], "white", COLORS["primary_light"]))
        btn_refresh.setFixedHeight(38)
        btn_refresh.clicked.connect(self.refresh)
        header_row.addWidget(btn_refresh)

        main_layout.addLayout(header_row)

        # -- Quick Stats Row ---------------------------------------------------
        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)

        self.card_total = self._make_stat_card(
            "Total Flex Officers", "0", COLORS["info"])
        self.card_deployed = self._make_stat_card(
            "Deployed Today", "0", COLORS["warning"])
        self.card_available = self._make_stat_card(
            "Available Today", "0", COLORS["success"])
        self.card_pending = self._make_stat_card(
            "Pending PTO", "0", COLORS["danger"])

        stats_row.addWidget(self.card_total)
        stats_row.addWidget(self.card_deployed)
        stats_row.addWidget(self.card_available)
        stats_row.addWidget(self.card_pending)
        main_layout.addLayout(stats_row)

        # -- Week Navigation ---------------------------------------------------
        week_row = QHBoxLayout()
        week_row.setSpacing(12)

        self.btn_prev = QPushButton("\u2039  Previous Week")
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

        main_layout.addLayout(week_row)

        # -- The Grid ----------------------------------------------------------
        self.grid = QTableWidget()
        self.grid.setColumnCount(8)  # Name + 7 days
        self.grid.setHorizontalHeaderLabels(["Officer"] + DAY_NAMES)
        self.grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.grid.setSelectionMode(QAbstractItemView.NoSelection)
        self.grid.verticalHeader().setVisible(False)
        self.grid.setShowGrid(True)
        self.grid.setAlternatingRowColors(False)
        self.grid.setMinimumHeight(300)

        hdr = self.grid.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.grid.setColumnWidth(0, 200)
        for col in range(1, 8):
            hdr.setSectionResizeMode(col, QHeaderView.Stretch)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 700; font-size: 14px;
                padding: 10px 8px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
                min-height: 34px;
            }}
        """)

        # Connect double-click for quick cell assignment
        self.grid.cellDoubleClicked.connect(self._on_cell_double_click)

        main_layout.addWidget(self.grid, 1)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _make_stat_card(self, title: str, value: str, accent: str) -> QFrame:
        """Create a compact stat card with accent left border."""
        frame = QFrame()
        frame.setFixedHeight(90)
        frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border-radius: 8px;
                border-left: 4px solid {accent};
            }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Segoe UI", 12))
        lbl_title.setStyleSheet(f"color: {tc('text_light')}; font-weight: 600;")
        lay.addWidget(lbl_title)

        lbl_val = QLabel(value)
        lbl_val.setObjectName("stat_value")
        lbl_val.setFont(QFont("Segoe UI", 26, QFont.Bold))
        lbl_val.setStyleSheet(f"color: {tc('text')};")
        lay.addWidget(lbl_val)

        return frame

    # -- Week helpers ----------------------------------------------------------

    def _week_start(self) -> dt_date:
        """Return the Sunday of the current display week."""
        today = dt_date.today()
        # weekday(): Monday=0 ... Sunday=6 -> offset to Sunday start
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

    # -- Double-click cell assignment ------------------------------------------

    def _on_cell_double_click(self, row, col):
        """Double-click an empty cell to quickly assign an officer."""
        if col < 1:  # Ignore officer name column
            return

        # Get officer name from row
        name_widget = self.grid.cellWidget(row, 0)
        if not name_widget:
            return
        # Find the QLabel with the officer name (first bold label)
        name_label = None
        for child in name_widget.findChildren(QLabel):
            if child.font().bold():
                name_label = child
                break
        if not name_label:
            return
        officer_name = name_label.text()

        # Get date from column header
        week_dates = self._week_dates()
        day_idx = col - 1
        if day_idx >= len(week_dates):
            return
        target_date = week_dates[day_idx]
        date_str = target_date.strftime("%Y-%m-%d")

        # Check if officer already has PTO
        pto = data_manager.get_officer_pto_for_date(officer_name, date_str)
        if pto:
            QMessageBox.information(self, "PTO", f"{officer_name} is on PTO that day.")
            return

        # Open a quick assignment dialog pre-filled with officer + date
        self._quick_assign_from_cell(officer_name, date_str)

    def _quick_assign_from_cell(self, officer_name, date_str):
        """Open a minimal assignment dialog pre-filled with officer and date."""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Assign {officer_name}")
        dlg.setMinimumWidth(400)
        try:
            from src.config import build_dialog_stylesheet
            dlg.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        except Exception:
            pass

        layout = QFormLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Officer (read-only)
        officer_lbl = QLabel(officer_name)
        officer_lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
        officer_lbl.setStyleSheet(f"color: {tc('primary')};")
        layout.addRow("Officer:", officer_lbl)

        # Date (read-only)
        date_lbl = QLabel(date_str)
        date_lbl.setFont(QFont("Segoe UI", 13))
        layout.addRow("Date:", date_lbl)

        # Site dropdown
        site_combo = QComboBox()
        sites = data_manager.get_active_sites()
        site_names = [s.get("name", "") for s in sites if s.get("name")]
        site_combo.addItems(site_names)
        layout.addRow("Site:", site_combo)

        # Start/End time
        start_time = QTimeEdit()
        start_time.setDisplayFormat("HH:mm")
        start_time.setTime(QTime(6, 0))
        layout.addRow("Start:", start_time)

        end_time = QTimeEdit()
        end_time.setDisplayFormat("HH:mm")
        end_time.setTime(QTime(14, 0))
        layout.addRow("End:", end_time)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() == QDialog.Accepted:
            site = site_combo.currentText()
            st = start_time.time().toString("HH:mm")
            et = end_time.time().toString("HH:mm")

            # Conflict check
            conflicts = data_manager.detect_conflicts(officer_name, date_str, st, et)
            if conflicts:
                sites_list = ", ".join(c.get("site_name", "") for c in conflicts)
                if QMessageBox.question(
                    self, "Conflict",
                    f"{officer_name} already assigned to {sites_list} on {date_str}.\nAssign anyway?",
                    QMessageBox.Yes | QMessageBox.No
                ) != QMessageBox.Yes:
                    return

            username = self.app_state.get("user", {}).get("username", "")
            data_manager.create_assignment({
                "officer_name": officer_name,
                "site_name": site,
                "date": date_str,
                "start_time": st,
                "end_time": et,
                "assignment_type": "Billable",
                "status": "Scheduled",
            }, username)
            audit.log_event("operations", "flex_assign", username,
                            f"Assigned {officer_name} to {site} on {date_str} {st}-{et}")
            self.refresh()

    # -- Data helpers ----------------------------------------------------------

    def _get_flex_officers(self) -> list:
        """Return active ops officers (flex officers and field service supervisors)."""
        return data_manager.get_ops_officers()

    def _get_pending_pto_count(self) -> int:
        """Count PTO entries with status = 'Pending'."""
        all_pto = data_manager.get_all_pto()
        return sum(1 for p in all_pto if p.get("status") == "Pending")

    # -- Refresh / populate ----------------------------------------------------

    def refresh(self):
        """Reload all data and repopulate the board."""
        dates = self._week_dates()
        start_str = dates[0].strftime("%Y-%m-%d")
        end_str = dates[6].strftime("%Y-%m-%d")
        today_str = dt_date.today().strftime("%Y-%m-%d")

        # Update header date
        self.lbl_date.setText(dt_date.today().strftime("%A, %B %d, %Y"))

        # Update week label
        self.lbl_week.setText(
            f"{dates[0].strftime('%b %d')} \u2013 {dates[6].strftime('%b %d, %Y')}"
        )

        # Fetch data
        flex_officers = self._get_flex_officers()
        week_assignments = data_manager.get_assignments_for_week(start_str, end_str)
        all_pto = data_manager.get_all_pto()

        # -- Quick Stats -------------------------------------------------------
        total_flex = len(flex_officers)
        deployed_today = set()
        available_today = 0

        for off in flex_officers:
            name = off.get("name", "")
            today_asn = [
                a for a in week_assignments
                if a.get("officer_name") == name and a.get("date") == today_str
            ]
            if today_asn:
                deployed_today.add(name)

        # Check PTO for today
        on_pto_today = set()
        for off in flex_officers:
            name = off.get("name", "")
            pto_today = data_manager.get_officer_pto_for_date(name, today_str)
            approved = [p for p in pto_today if p.get("status") in ("Approved", "Pending")]
            if approved:
                on_pto_today.add(name)

        available_today = total_flex - len(deployed_today) - len(
            on_pto_today - deployed_today
        )
        available_today = max(0, available_today)

        pending_pto = self._get_pending_pto_count()

        self.card_total.findChild(QLabel, "stat_value").setText(str(total_flex))
        self.card_deployed.findChild(QLabel, "stat_value").setText(str(len(deployed_today)))
        self.card_available.findChild(QLabel, "stat_value").setText(str(available_today))
        self.card_pending.findChild(QLabel, "stat_value").setText(str(pending_pto))

        # Badge the pending PTO card red if > 0
        if pending_pto > 0:
            self.card_pending.setStyleSheet(f"""
                QFrame {{
                    background: {tc('card')};
                    border-radius: 8px;
                    border-left: 4px solid {COLORS['danger']};
                    border-top: 1px solid {COLORS['danger']};
                }}
            """)
        else:
            self.card_pending.setStyleSheet(f"""
                QFrame {{
                    background: {tc('card')};
                    border-radius: 8px;
                    border-left: 4px solid {COLORS['danger']};
                }}
            """)

        # -- Build Grid --------------------------------------------------------
        # Build lookup dicts for fast access
        # assignments_by_officer_date[(name, date_str)] = [assignment, ...]
        asn_lookup = {}
        for a in week_assignments:
            key = (a.get("officer_name", ""), a.get("date", ""))
            asn_lookup.setdefault(key, []).append(a)

        # PTO lookup: we need to check each date
        # pto_by_officer_date[(name, date_str)] = [pto, ...]
        pto_lookup = {}
        for off in flex_officers:
            name = off.get("name", "")
            for d in dates:
                d_str = d.strftime("%Y-%m-%d")
                matching = []
                for p in all_pto:
                    if p.get("officer_name") != name:
                        continue
                    if p.get("status") not in ("Approved", "Pending"):
                        continue
                    p_start = p.get("start_date", "")
                    p_end = p.get("end_date", "")
                    if p_start <= d_str <= p_end:
                        matching.append(p)
                if matching:
                    pto_lookup[(name, d_str)] = matching

        # Sort officers alphabetically
        flex_officers.sort(key=lambda o: o.get("name", "").lower())

        self.grid.setRowCount(len(flex_officers))
        for row, off in enumerate(flex_officers):
            name = off.get("name", "")
            phone = off.get("phone", "") or off.get("phone_number", "") or ""

            # Officer name cell
            name_widget = QWidget()
            name_widget.setStyleSheet(f"background: {tc('card')};")
            n_lay = QVBoxLayout(name_widget)
            n_lay.setContentsMargins(10, 6, 6, 6)
            n_lay.setSpacing(1)

            n_lbl = QLabel(name)
            n_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
            n_lbl.setStyleSheet(f"color: {tc('text')}; background: transparent;")
            n_lay.addWidget(n_lbl)

            if phone:
                p_lbl = QLabel(phone)
                p_lbl.setFont(QFont("Segoe UI", 11))
                p_lbl.setStyleSheet(f"color: {tc('text_light')}; background: transparent;")
                n_lay.addWidget(p_lbl)

            self.grid.setCellWidget(row, 0, name_widget)

            # Day cells
            max_items = 1
            for col, d in enumerate(dates, start=1):
                d_str = d.strftime("%Y-%m-%d")
                day_asn = asn_lookup.get((name, d_str), [])
                day_pto = pto_lookup.get((name, d_str), [])

                cell_widget = FlexCellWidget(day_asn, day_pto)

                # Highlight today column
                if d_str == today_str:
                    cell_widget.setStyleSheet(f"""
                        QWidget {{
                            background: {'#252540' if _is_dark() else '#F0F7FF'};
                        }}
                    """)

                self.grid.setCellWidget(row, col, cell_widget)
                max_items = max(max_items, len(day_asn) + len(day_pto), 1)

            # Adjust row height based on content
            row_height = max(60, 40 + max_items * 44)
            self.grid.setRowHeight(row, row_height)

        # Highlight today column header
        for col, d in enumerate(dates, start=1):
            d_str = d.strftime("%Y-%m-%d")
            header_text = f"{DAY_NAMES[col - 1]}\n{d.strftime('%m/%d')}"
            if d_str == today_str:
                header_text += " \u25CF"
            item = QTableWidgetItem(header_text)
            item.setTextAlignment(Qt.AlignCenter)
            self.grid.setHorizontalHeaderItem(col, item)

        # Officer column header
        officer_header = QTableWidgetItem("Officer")
        officer_header.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.grid.setHorizontalHeaderItem(0, officer_header)
