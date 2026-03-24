"""
Cerasus Hub — Operations Module: PTO Coverage & Approval Page
PTO approval workflow with flex coverage matching.
"""

import calendar
from datetime import datetime, timedelta, date as dt_date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QComboBox, QMessageBox, QFormLayout, QTextEdit,
    QAbstractItemView, QDialog, QDialogButtonBox, QDateEdit,
    QLineEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor, QBrush

from src.config import COLORS, ROLE_ADMIN, build_dialog_stylesheet, tc, _is_dark, btn_style
from src.modules.operations import data_manager
from src.shared_data import get_officer
from src import audit


# ════════════════════════════════════════════════════════════════════════
# PTO Dialog (updated – default status Pending, site auto-fill)
# ════════════════════════════════════════════════════════════════════════

class PTODialog(QDialog):
    def __init__(self, parent=None, pto=None):
        super().__init__(parent)
        self.setWindowTitle("Edit PTO" if pto else "Request PTO")
        self.setMinimumWidth(500)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.pto = pto
        self._officers_cache = data_manager.get_ops_officers()
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Officer
        self.cmb_officer = QComboBox()
        self.cmb_officer.setEditable(False)
        names = [o.get("name", "") for o in self._officers_cache if o.get("name")]
        if names:
            self.cmb_officer.addItems(names)
        else:
            self.cmb_officer.addItem("-- Add officers first --")
        if self.pto:
            idx = self.cmb_officer.findText(self.pto.get("officer_name", ""))
            if idx >= 0:
                self.cmb_officer.setCurrentIndex(idx)
        self.cmb_officer.currentIndexChanged.connect(self._on_officer_changed)
        layout.addRow("Officer:", self.cmb_officer)

        # Site (auto-filled from officer record)
        self.txt_site = QLineEdit()
        self.txt_site.setReadOnly(True)
        self.txt_site.setPlaceholderText("Auto-filled from officer record")
        self.txt_site.setStyleSheet(f"background: {tc('bg')}; color: {tc('text_light')}; padding: 6px;")
        layout.addRow("Site:", self.txt_site)

        # Start date
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        if self.pto and self.pto.get("start_date"):
            d = QDate.fromString(self.pto["start_date"], "yyyy-MM-dd")
            self.date_start.setDate(d if d.isValid() else QDate.currentDate())
        else:
            self.date_start.setDate(QDate.currentDate())
        layout.addRow("Start Date:", self.date_start)

        # End date
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        if self.pto and self.pto.get("end_date"):
            d = QDate.fromString(self.pto["end_date"], "yyyy-MM-dd")
            self.date_end.setDate(d if d.isValid() else QDate.currentDate())
        else:
            self.date_end.setDate(QDate.currentDate())
        layout.addRow("End Date:", self.date_end)

        # Type
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["Unavailable", "Vacation", "Sick", "Personal", "FMLA", "Other"])
        if self.pto:
            idx = self.cmb_type.findText(self.pto.get("pto_type", "Unavailable"))
            if idx >= 0:
                self.cmb_type.setCurrentIndex(idx)
        layout.addRow("Type:", self.cmb_type)

        # Status — default Pending for new entries
        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["Pending", "Approved", "Denied"])
        if self.pto:
            idx = self.cmb_status.findText(self.pto.get("status", "Pending"))
            if idx >= 0:
                self.cmb_status.setCurrentIndex(idx)
        layout.addRow("Status:", self.cmb_status)

        # Notes
        self.txt_notes = QTextEdit(self.pto.get("notes", "") if self.pto else "")
        self.txt_notes.setMaximumHeight(80)
        layout.addRow("Notes:", self.txt_notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        # Initialize site field
        self._on_officer_changed()

    def _on_officer_changed(self):
        """Auto-fill the site from the selected officer's record."""
        name = self.cmb_officer.currentText().strip()
        site = ""
        for o in self._officers_cache:
            if o.get("name") == name:
                site = o.get("site", "")
                break
        self.txt_site.setText(site if site else "(No site assigned)")

    def get_data(self):
        return {
            "officer_name": self.cmb_officer.currentText().strip(),
            "start_date": self.date_start.date().toString("yyyy-MM-dd"),
            "end_date": self.date_end.date().toString("yyyy-MM-dd"),
            "pto_type": self.cmb_type.currentText(),
            "status": self.cmb_status.currentText(),
            "notes": self.txt_notes.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Coverage Finder Dialog
# ════════════════════════════════════════════════════════════════════════

class CoverageFinderDialog(QDialog):
    """Shows available flex officers to cover a PTO request and allows assignment."""

    def __init__(self, parent, pto_entry, app_state):
        super().__init__(parent)
        self.setWindowTitle("Assign Flex Coverage")
        self.setMinimumSize(720, 500)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.pto = pto_entry
        self.app_state = app_state
        self.assigned = False
        self._build()
        self._load_flex_officers()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # ── PTO details banner
        detail_frame = QFrame()
        detail_frame.setStyleSheet(f"""
            QFrame {{
                background: {COLORS.get('info_light', '#DBEAFE')};
                border: 1px solid {COLORS['info']};
                border-radius: 8px;
            }}
        """)
        d_lay = QVBoxLayout(detail_frame)
        d_lay.setContentsMargins(16, 12, 16, 12)
        d_lay.setSpacing(4)

        officer_name = self.pto.get("officer_name", "Unknown")
        # Look up officer site
        site = self._get_officer_site(officer_name)
        start = self.pto.get("start_date", "")
        end = self.pto.get("end_date", "")
        pto_type = self.pto.get("pto_type", "")

        title_lbl = QLabel(f"Coverage needed for: {officer_name}")
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {tc('primary')};")
        d_lay.addWidget(title_lbl)

        info_lbl = QLabel(f"Site: {site}  |  Dates: {start} to {end}  |  Type: {pto_type}")
        info_lbl.setFont(QFont("Segoe UI", 13))
        info_lbl.setStyleSheet(f"color: {tc('text')};")
        d_lay.addWidget(info_lbl)
        layout.addWidget(detail_frame)

        # ── Available flex officers table
        flex_label = QLabel("Available Flex Officers")
        flex_label.setFont(QFont("Segoe UI", 15, QFont.Bold))
        flex_label.setStyleSheet(f"color: {COLORS['success']};")
        layout.addWidget(flex_label)

        self.flex_table = QTableWidget(0, 5)
        self.flex_table.setHorizontalHeaderLabels([
            "Name", "Phone", "Weekly Hours", "Conflicts", ""
        ])
        hdr = self.flex_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self.flex_table.setColumnWidth(4, 160)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {tc('primary')};
                color: white; font-weight: 600; font-size: 13px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.flex_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.flex_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.flex_table.verticalHeader().setVisible(False)
        self.flex_table.setAlternatingRowColors(True)
        layout.addWidget(self.flex_table)

        # ── Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(btn_style(tc("primary"), "white", COLORS["primary_light"]))
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _get_officer_site(self, name):
        """Look up the site for an officer by name."""
        officers = data_manager.get_ops_officers(active_only=False)
        for o in officers:
            if o.get("name") == name:
                return o.get("site", "(No site)")
        return "(Unknown)"

    def _get_pto_dates(self):
        """Return list of date strings for each day in the PTO range."""
        start_str = self.pto.get("start_date", "")
        end_str = self.pto.get("end_date", "")
        dates = []
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
            end = datetime.strptime(end_str, "%Y-%m-%d").date()
            current = start
            while current <= end:
                dates.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
        except (ValueError, TypeError):
            pass
        return dates

    def _load_flex_officers(self):
        """Find flex officers and check availability for the PTO date range."""
        flex_officers = [
            o for o in data_manager.get_ops_officers()
            if "flex" in (o.get("job_title") or "").lower()
            or "flex" in (o.get("role") or "").lower()
        ]

        pto_dates = self._get_pto_dates()
        if not pto_dates:
            return

        # Get all assignments for the date range
        all_assignments = data_manager.get_assignments_for_week(pto_dates[0], pto_dates[-1])

        available = []
        for flex in flex_officers:
            fname = flex.get("name", "")
            conflict_days = []
            for d in pto_dates:
                # Check PTO conflicts
                pto_conflicts = data_manager.get_officer_pto_for_date(fname, d)
                if pto_conflicts:
                    conflict_days.append(d)
                    continue
                # Check assignment conflicts
                asn_conflicts = [
                    a for a in all_assignments
                    if a.get("officer_name") == fname and a.get("date") == d
                ]
                if asn_conflicts:
                    conflict_days.append(d)
            available.append((flex, conflict_days))

        # Sort: fully available first, then by conflict count
        available.sort(key=lambda x: len(x[1]))

        self.flex_table.setRowCount(len(available))
        for i, (flex, conflicts) in enumerate(available):
            fname = flex.get("name", "")
            phone = flex.get("phone", "")
            weekly_hrs = flex.get("weekly_hours", "")

            self.flex_table.setItem(i, 0, QTableWidgetItem(fname))
            self.flex_table.setItem(i, 1, QTableWidgetItem(phone))
            self.flex_table.setItem(i, 2, QTableWidgetItem(str(weekly_hrs)))

            # Conflict indicator
            if conflicts:
                conflict_item = QTableWidgetItem(f"{len(conflicts)}/{len(pto_dates)} days busy")
                conflict_item.setForeground(QColor(COLORS["warning"]))
                conflict_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            else:
                conflict_item = QTableWidgetItem("Fully available")
                conflict_item.setForeground(QColor(COLORS["success"]))
                conflict_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.flex_table.setItem(i, 3, conflict_item)

            # Assign & Approve button
            btn = QPushButton("Assign && Approve")
            if conflicts:
                btn.setStyleSheet(btn_style(COLORS["warning"], "white"))
                btn.setToolTip(f"Busy on: {', '.join(conflicts)}")
            else:
                btn.setStyleSheet(btn_style(COLORS["success"], "white"))
            btn.clicked.connect(lambda checked, fn=fname, c=conflicts: self._assign_flex(fn, c))
            self.flex_table.setCellWidget(i, 4, btn)

            self.flex_table.setRowHeight(i, 44)

    def _assign_flex(self, flex_name, conflicts):
        """Create assignments for the flex officer and approve the PTO."""
        pto_dates = self._get_pto_dates()
        officer_name = self.pto.get("officer_name", "")
        site = self._get_officer_site(officer_name)

        if conflicts:
            busy_str = ", ".join(conflicts)
            reply = QMessageBox.warning(
                self, "Partial Availability",
                f"{flex_name} has conflicts on: {busy_str}\n\n"
                f"Only available days will be assigned. Continue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        username = self.app_state["user"]["username"]
        assigned_dates = []

        for d in pto_dates:
            if d in conflicts:
                continue
            data_manager.create_assignment({
                "officer_name": flex_name,
                "site_name": site,
                "date": d,
                "start_time": "",
                "end_time": "",
                "hours": "0",
                "assignment_type": "PTO Coverage",
                "status": "Scheduled",
                "notes": f"Covering PTO for {officer_name}",
            }, username)
            assigned_dates.append(d)

        # Approve the PTO
        pto_id = self.pto.get("pto_id", "")
        data_manager.update_pto(pto_id, {"status": "Approved"}, username)

        audit.log_event(
            "operations", "pto_coverage_assign", username,
            f"Assigned {flex_name} to cover PTO {pto_id} for {officer_name} "
            f"at {site} ({len(assigned_dates)} days). PTO approved.",
        )

        self.assigned = True
        QMessageBox.information(
            self, "Coverage Assigned",
            f"{flex_name} assigned to cover {len(assigned_dates)} day(s) at {site}.\n"
            f"PTO for {officer_name} has been approved.",
        )
        self.accept()


# ════════════════════════════════════════════════════════════════════════
# PTO Coverage & Approval Page
# ════════════════════════════════════════════════════════════════════════

class PTOCoveragePage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._all_pto_visible = False  # collapsed by default
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── Header
        header_row = QHBoxLayout()
        header = QLabel("PTO Coverage & Approval")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setStyleSheet(f"color: {tc('primary')};")
        header_row.addWidget(header)
        header_row.addStretch()

        self.btn_add_pto = QPushButton("+ Request PTO")
        self.btn_add_pto.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        self.btn_add_pto.clicked.connect(self._add_pto)
        header_row.addWidget(self.btn_add_pto)
        layout.addLayout(header_row)

        # ══════════════════════════════════════════════════════════════
        # Pending PTO Requests Section
        # ══════════════════════════════════════════════════════════════

        # Pending banner with Bulk Approve button
        self.pending_banner = QFrame()
        self.pending_banner.setStyleSheet(f"""
            QFrame {{
                background: {COLORS.get('warning_light', '#FEF3C7')};
                border: 2px solid {COLORS['warning']};
                border-radius: 8px;
            }}
        """)
        banner_lay = QHBoxLayout(self.pending_banner)
        banner_lay.setContentsMargins(16, 10, 16, 10)
        self.pending_icon = QLabel("\u26A0")
        self.pending_icon.setFont(QFont("Segoe UI", 18))
        banner_lay.addWidget(self.pending_icon)
        self.pending_count_lbl = QLabel("0 Pending PTO Requests")
        self.pending_count_lbl.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.pending_count_lbl.setStyleSheet(f"color: {COLORS['warning']};")
        banner_lay.addWidget(self.pending_count_lbl)
        banner_lay.addStretch()

        # Bulk Approve button (inside the banner row)
        self.btn_bulk_approve = QPushButton("Bulk Approve All")
        self.btn_bulk_approve.setStyleSheet(btn_style(COLORS["success"], "white"))
        self.btn_bulk_approve.setToolTip("Approve all pending PTO requests without flex coverage")
        self.btn_bulk_approve.clicked.connect(self._bulk_approve)
        self.btn_bulk_approve.setVisible(False)  # hidden when no pending
        banner_lay.addWidget(self.btn_bulk_approve)

        layout.addWidget(self.pending_banner)

        # Pending PTO table
        self.pending_table = QTableWidget(0, 8)
        self.pending_table.setHorizontalHeaderLabels([
            "Officer", "Site", "Start Date", "End Date", "Type",
            "Assign Flex", "Approve", "Deny"
        ])
        p_hdr = self.pending_table.horizontalHeader()
        p_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        p_hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in [2, 3, 4]:
            p_hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        for c in [5, 6, 7]:
            p_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self.pending_table.setColumnWidth(c, 120)
        p_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['warning']};
                color: white; font-weight: 600; font-size: 13px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS.get('warning_light', '#FEF3C7')};
            }}
        """)
        self.pending_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pending_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pending_table.verticalHeader().setVisible(False)
        self.pending_table.setAlternatingRowColors(True)
        self.pending_table.setMaximumHeight(220)
        layout.addWidget(self.pending_table)

        # ══════════════════════════════════════════════════════════════
        # Collapsible All PTO Records Section
        # ══════════════════════════════════════════════════════════════

        # Toggle button for collapsible section
        self.btn_toggle_all_pto = QPushButton("\u25B8 All PTO Records (0)")
        self.btn_toggle_all_pto.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.btn_toggle_all_pto.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {tc('primary')};
                border: none;
                text-align: left;
                padding: 6px 0px;
            }}
            QPushButton:hover {{
                color: {COLORS.get('primary_light', tc('primary'))};
            }}
        """)
        self.btn_toggle_all_pto.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_all_pto.clicked.connect(self._toggle_all_pto)
        layout.addWidget(self.btn_toggle_all_pto)

        # Container widget for the collapsible content
        self.all_pto_container = QWidget()
        all_pto_lay = QVBoxLayout(self.all_pto_container)
        all_pto_lay.setContentsMargins(0, 0, 0, 0)
        all_pto_lay.setSpacing(8)

        self.pto_table = QTableWidget(0, 7)
        self.pto_table.setHorizontalHeaderLabels([
            "Officer", "Start Date", "End Date", "Type", "Status", "Notes", "ID"
        ])
        hdr = self.pto_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        for c in [1, 2, 3, 4, 6]:
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {tc('primary')};
                color: white; font-weight: 600; font-size: 14px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.pto_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pto_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pto_table.verticalHeader().setVisible(False)
        self.pto_table.setAlternatingRowColors(True)
        self.pto_table.setMaximumHeight(180)
        all_pto_lay.addWidget(self.pto_table)

        # PTO action buttons
        pto_btn_row = QHBoxLayout()
        self.btn_edit_pto = QPushButton("Edit Selected")
        self.btn_edit_pto.setStyleSheet(btn_style(tc("primary"), "white", COLORS["primary_light"]))
        self.btn_edit_pto.clicked.connect(self._edit_pto)
        pto_btn_row.addWidget(self.btn_edit_pto)

        self.btn_del_pto = QPushButton("Delete Selected")
        self.btn_del_pto.setStyleSheet(btn_style(COLORS["danger"], "white"))
        self.btn_del_pto.clicked.connect(self._delete_pto)
        pto_btn_row.addWidget(self.btn_del_pto)
        pto_btn_row.addStretch()
        all_pto_lay.addLayout(pto_btn_row)

        # Default collapsed
        self.all_pto_container.setVisible(False)
        layout.addWidget(self.all_pto_container)

        # ══════════════════════════════════════════════════════════════
        # PTO Calendar View (collapsible)
        # ══════════════════════════════════════════════════════════════
        self._cal_visible = False
        self._cal_year = dt_date.today().year
        self._cal_month = dt_date.today().month

        self.btn_toggle_cal = QPushButton("\u25B8 PTO Calendar")
        self.btn_toggle_cal.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.btn_toggle_cal.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {tc('primary')};
                border: none;
                text-align: left;
                padding: 6px 0px;
            }}
            QPushButton:hover {{
                color: {COLORS.get('primary_light', tc('primary'))};
            }}
        """)
        self.btn_toggle_cal.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_cal.clicked.connect(self._toggle_calendar)
        layout.addWidget(self.btn_toggle_cal)

        self.cal_container = QWidget()
        cal_lay = QVBoxLayout(self.cal_container)
        cal_lay.setContentsMargins(0, 0, 0, 0)
        cal_lay.setSpacing(8)

        # Month navigation
        nav_row = QHBoxLayout()
        btn_prev_m = QPushButton("< Prev")
        btn_prev_m.setStyleSheet(btn_style(COLORS.get("primary_light", tc("primary")), "white"))
        btn_prev_m.clicked.connect(self._cal_prev_month)
        nav_row.addWidget(btn_prev_m)

        self.lbl_cal_month = QLabel("")
        self.lbl_cal_month.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.lbl_cal_month.setStyleSheet(f"color: {tc('primary')};")
        self.lbl_cal_month.setAlignment(Qt.AlignCenter)
        nav_row.addWidget(self.lbl_cal_month)

        btn_next_m = QPushButton("Next >")
        btn_next_m.setStyleSheet(btn_style(COLORS.get("primary_light", tc("primary")), "white"))
        btn_next_m.clicked.connect(self._cal_next_month)
        nav_row.addWidget(btn_next_m)
        cal_lay.addLayout(nav_row)

        # Calendar grid (7 cols = Sun..Sat)
        self.cal_grid = QTableWidget()
        self.cal_grid.setColumnCount(7)
        self.cal_grid.setHorizontalHeaderLabels(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
        self.cal_grid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cal_grid.horizontalHeader().setStyleSheet(f"""
            QHeaderView::section {{
                background: {tc('primary')};
                color: white; font-weight: 600; font-size: 13px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS.get('primary_light', tc('primary'))};
            }}
        """)
        self.cal_grid.verticalHeader().setVisible(False)
        self.cal_grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cal_grid.setSelectionMode(QAbstractItemView.NoSelection)
        self.cal_grid.setShowGrid(True)
        self.cal_grid.setMinimumHeight(320)
        cal_lay.addWidget(self.cal_grid)

        self.cal_container.setVisible(False)
        layout.addWidget(self.cal_container)

        # Spacer at bottom to keep pending section toward top
        layout.addStretch()

    # ── Toggle All PTO section ─────────────────────────────────────

    def _toggle_all_pto(self):
        self._all_pto_visible = not self._all_pto_visible
        self.all_pto_container.setVisible(self._all_pto_visible)
        # Update the toggle arrow
        arrow = "\u25BE" if self._all_pto_visible else "\u25B8"
        count = self.pto_table.rowCount()
        self.btn_toggle_all_pto.setText(f"{arrow} All PTO Records ({count})")

    # ── Helpers ────────────────────────────────────────────────────────

    def _get_officer_site(self, name):
        """Look up the site for an officer by name."""
        officers = data_manager.get_ops_officers(active_only=False)
        for o in officers:
            if o.get("name") == name:
                return o.get("site", "")
        return ""

    # ── Refresh ────────────────────────────────────────────────────────

    def refresh(self):
        all_pto = data_manager.get_all_pto()

        # ── Pending PTO Requests Section
        pending = [p for p in all_pto if p.get("status") == "Pending"]
        pending_count = len(pending)
        self.pending_count_lbl.setText(f"{pending_count} Pending PTO Request{'s' if pending_count != 1 else ''}")

        if pending_count == 0:
            self.pending_banner.setStyleSheet(f"""
                QFrame {{
                    background: {COLORS['success_light']};
                    border: 2px solid {COLORS['success']};
                    border-radius: 8px;
                }}
            """)
            self.pending_icon.setText("\u2714")
            self.pending_count_lbl.setText("No Pending PTO Requests")
            self.pending_count_lbl.setStyleSheet(f"color: {COLORS['success']};")
            self.btn_bulk_approve.setVisible(False)
        else:
            self.pending_banner.setStyleSheet(f"""
                QFrame {{
                    background: {COLORS.get('warning_light', '#FEF3C7')};
                    border: 2px solid {COLORS['warning']};
                    border-radius: 8px;
                }}
            """)
            self.pending_icon.setText("\u26A0")
            self.pending_count_lbl.setStyleSheet(f"color: {COLORS['warning']};")
            self.btn_bulk_approve.setVisible(True)

        self.pending_table.setRowCount(pending_count)
        for i, p in enumerate(pending):
            officer_name = p.get("officer_name", "")
            site = self._get_officer_site(officer_name)

            self.pending_table.setItem(i, 0, QTableWidgetItem(officer_name))
            self.pending_table.setItem(i, 1, QTableWidgetItem(site if site else "(No site)"))
            self.pending_table.setItem(i, 2, QTableWidgetItem(p.get("start_date", "")))
            self.pending_table.setItem(i, 3, QTableWidgetItem(p.get("end_date", "")))

            type_item = QTableWidgetItem(p.get("pto_type", ""))
            type_colors = {
                "Unavailable": COLORS["warning"],
                "Vacation": COLORS["info"],
                "Sick": COLORS["danger"],
            }
            type_item.setForeground(QColor(type_colors.get(p.get("pto_type"), tc("text_light"))))
            type_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.pending_table.setItem(i, 4, type_item)

            # Assign Flex button (renamed from "Find Coverage")
            btn_find = QPushButton("Assign Flex")
            btn_find.setStyleSheet(btn_style(COLORS["info"], "white"))
            btn_find.clicked.connect(lambda checked, pto=p: self._find_coverage(pto))
            self.pending_table.setCellWidget(i, 5, btn_find)

            # Approve button
            btn_approve = QPushButton("Approve")
            btn_approve.setStyleSheet(btn_style(COLORS["success"], "white"))
            btn_approve.clicked.connect(lambda checked, pto=p: self._approve_pto(pto))
            self.pending_table.setCellWidget(i, 6, btn_approve)

            # Deny button
            btn_deny = QPushButton("Deny")
            btn_deny.setStyleSheet(btn_style(COLORS["danger"], "white"))
            btn_deny.clicked.connect(lambda checked, pto=p: self._deny_pto(pto))
            self.pending_table.setCellWidget(i, 7, btn_deny)

            self.pending_table.setRowHeight(i, 44)

        # Show/hide pending section based on count
        self.pending_table.setVisible(pending_count > 0)

        # ── All PTO Records Table
        self.pto_table.setRowCount(len(all_pto))
        for i, p in enumerate(all_pto):
            self.pto_table.setItem(i, 0, QTableWidgetItem(p.get("officer_name", "")))
            self.pto_table.setItem(i, 1, QTableWidgetItem(p.get("start_date", "")))
            self.pto_table.setItem(i, 2, QTableWidgetItem(p.get("end_date", "")))

            type_item = QTableWidgetItem(p.get("pto_type", ""))
            type_colors = {
                "Unavailable": COLORS["warning"],
                "Vacation": COLORS["info"],
                "Sick": COLORS["danger"],
            }
            type_color = type_colors.get(p.get("pto_type"), tc("text_light"))
            type_item.setForeground(QColor(type_color))
            type_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.pto_table.setItem(i, 3, type_item)

            status_item = QTableWidgetItem(p.get("status", ""))
            sc = {"Approved": COLORS["success"], "Pending": COLORS["warning"], "Denied": COLORS["danger"]}
            s_color = sc.get(p.get("status"), tc("text_light"))
            status_item.setForeground(QColor(s_color))
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.pto_table.setItem(i, 4, status_item)

            self.pto_table.setItem(i, 5, QTableWidgetItem(p.get("notes", "")))

            id_item = QTableWidgetItem(p.get("pto_id", ""))
            id_item.setForeground(QColor(tc("text_light")))
            id_item.setFont(QFont("Consolas", 11))
            self.pto_table.setItem(i, 6, id_item)

        # Update toggle button text with count
        arrow = "\u25BE" if self._all_pto_visible else "\u25B8"
        self.btn_toggle_all_pto.setText(f"{arrow} All PTO Records ({len(all_pto)})")

        # Refresh calendar if visible
        if self._cal_visible:
            self._refresh_calendar()

    # ── PTO Actions ────────────────────────────────────────────────────

    def _find_coverage(self, pto_entry):
        """Open the CoverageFinderDialog for a pending PTO request."""
        dlg = CoverageFinderDialog(self, pto_entry, self.app_state)
        dlg.exec()
        if dlg.assigned:
            self.refresh()

    def _approve_pto(self, pto_entry):
        """Approve a PTO request — warn if no flex coverage is assigned."""
        pto_id = pto_entry.get("pto_id", "")
        officer_name = pto_entry.get("officer_name", "")

        reply = QMessageBox.warning(
            self, "No Coverage Check",
            f"No flex coverage has been assigned for {officer_name}.\n\n"
            "Approve anyway?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        username = self.app_state["user"]["username"]
        data_manager.update_pto(pto_id, {"status": "Approved"}, username)
        audit.log_event(
            "operations", "pto_approve", username,
            f"Force-approved PTO {pto_id} for {officer_name} without flex coverage.",
        )
        self.refresh()

    def _deny_pto(self, pto_entry):
        """Deny a PTO request with optional reason."""
        pto_id = pto_entry.get("pto_id", "")
        officer_name = pto_entry.get("officer_name", "")

        # Ask for optional denial reason
        from PySide6.QtWidgets import QInputDialog
        reason, ok = QInputDialog.getText(
            self, "Deny PTO",
            f"Deny PTO for {officer_name}?\n\nOptional reason:",
        )
        if not ok:
            return

        username = self.app_state["user"]["username"]
        update_fields = {"status": "Denied"}
        if reason.strip():
            existing_notes = pto_entry.get("notes", "")
            denial_note = f"[DENIED: {reason.strip()}]"
            if existing_notes:
                update_fields["notes"] = f"{existing_notes}\n{denial_note}"
            else:
                update_fields["notes"] = denial_note

        data_manager.update_pto(pto_id, update_fields, username)
        audit.log_event(
            "operations", "pto_deny", username,
            f"Denied PTO {pto_id} for {officer_name}. Reason: {reason.strip() or 'None given'}",
        )
        self.refresh()

    def _bulk_approve(self):
        """Bulk-approve all pending PTO requests without flex coverage."""
        all_pto = data_manager.get_all_pto()
        pending = [p for p in all_pto if p.get("status") == "Pending"]
        count = len(pending)
        if count == 0:
            QMessageBox.information(self, "Bulk Approve", "No pending PTO requests to approve.")
            return

        reply = QMessageBox.warning(
            self, "Bulk Approve",
            f"Approve all {count} pending request{'s' if count != 1 else ''} "
            f"without flex coverage?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        username = self.app_state["user"]["username"]
        for p in pending:
            pto_id = p.get("pto_id", "")
            officer_name = p.get("officer_name", "")
            data_manager.update_pto(pto_id, {"status": "Approved"}, username)
            audit.log_event(
                "operations", "pto_bulk_approve", username,
                f"Bulk-approved PTO {pto_id} for {officer_name} without flex coverage.",
            )
        self.refresh()

    # ── Calendar view helpers ─────────────────────────────────────────

    def _toggle_calendar(self):
        self._cal_visible = not self._cal_visible
        self.cal_container.setVisible(self._cal_visible)
        arrow = "\u25BE" if self._cal_visible else "\u25B8"
        self.btn_toggle_cal.setText(f"{arrow} PTO Calendar")
        if self._cal_visible:
            self._refresh_calendar()

    def _cal_prev_month(self):
        if self._cal_month == 1:
            self._cal_month = 12
            self._cal_year -= 1
        else:
            self._cal_month -= 1
        self._refresh_calendar()

    def _cal_next_month(self):
        if self._cal_month == 12:
            self._cal_month = 1
            self._cal_year += 1
        else:
            self._cal_month += 1
        self._refresh_calendar()

    def _refresh_calendar(self):
        """Build the monthly calendar grid with PTO entries as colored cells."""
        import calendar as cal_mod

        year, month = self._cal_year, self._cal_month
        self.lbl_cal_month.setText(f"{cal_mod.month_name[month]} {year}")

        # Get approved/pending PTO for this month
        all_pto = data_manager.get_all_pto()
        month_start = f"{year:04d}-{month:02d}-01"
        last_day = cal_mod.monthrange(year, month)[1]
        month_end = f"{year:04d}-{month:02d}-{last_day:02d}"

        # Build date -> [officer_name, ...] map for approved PTO
        pto_map = {}  # date_str -> [(officer_name, status)]
        for p in all_pto:
            status = p.get("status", "")
            if status not in ("Approved", "Pending"):
                continue
            try:
                s = datetime.strptime(p.get("start_date", ""), "%Y-%m-%d").date()
                e = datetime.strptime(p.get("end_date", ""), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            current = s
            while current <= e:
                ds = current.strftime("%Y-%m-%d")
                if month_start <= ds <= month_end:
                    pto_map.setdefault(ds, []).append((p.get("officer_name", ""), status))
                current += timedelta(days=1)

        # Build the calendar grid (Sunday-start)
        # calendar module uses Monday=0, Sunday=6
        cal_obj = cal_mod.Calendar(firstweekday=6)  # Sunday first
        weeks = cal_obj.monthdayscalendar(year, month)

        self.cal_grid.setRowCount(len(weeks))
        for row_idx, week in enumerate(weeks):
            self.cal_grid.setRowHeight(row_idx, 60)
            for col_idx, day in enumerate(week):
                if day == 0:
                    # Empty cell (day from adjacent month)
                    item = QTableWidgetItem("")
                    item.setBackground(QColor(tc("bg")))
                    self.cal_grid.setItem(row_idx, col_idx, item)
                    continue

                ds = f"{year:04d}-{month:02d}-{day:02d}"
                entries = pto_map.get(ds, [])

                if entries:
                    names = []
                    has_approved = False
                    has_pending = False
                    for name, status in entries:
                        names.append(name)
                        if status == "Approved":
                            has_approved = True
                        else:
                            has_pending = True

                    text = f"{day}\n" + "\n".join(names[:3])
                    if len(names) > 3:
                        text += f"\n+{len(names) - 3} more"
                    item = QTableWidgetItem(text)

                    if has_approved:
                        item.setBackground(QColor(COLORS.get("danger_light", "#FEE2E2")))
                        item.setForeground(QColor(COLORS["danger"]))
                    elif has_pending:
                        item.setBackground(QColor(COLORS.get("warning_light", "#FEF3C7")))
                        item.setForeground(QColor(COLORS["warning"]))
                    item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                else:
                    item = QTableWidgetItem(str(day))
                    item.setForeground(QColor(tc("text_light")))

                item.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
                self.cal_grid.setItem(row_idx, col_idx, item)

    def _get_selected_pto_id(self):
        row = self.pto_table.currentRow()
        if row < 0:
            return None
        item = self.pto_table.item(row, 6)
        return item.text() if item else None

    def _add_pto(self):
        dlg = PTODialog(self)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            if not d["officer_name"] or d["officer_name"].startswith("--"):
                QMessageBox.warning(self, "Validation", "Officer is required.")
                return
            username = self.app_state["user"]["username"]
            data_manager.create_pto(d, username)
            audit.log_event("operations", "pto_create", username,
                            f"Added PTO for {d['officer_name']} {d['start_date']} to {d['end_date']}")
            self.refresh()

    def _edit_pto(self):
        pid = self._get_selected_pto_id()
        if not pid:
            QMessageBox.information(self, "Select", "Please select a PTO entry.")
            return
        pto = data_manager.get_pto(pid)
        if not pto:
            return
        dlg = PTODialog(self, pto=pto)
        if dlg.exec() == QDialog.Accepted:
            username = self.app_state["user"]["username"]
            data_manager.update_pto(pid, dlg.get_data(), username)
            audit.log_event("operations", "pto_edit", username, f"Updated PTO {pid}")
            self.refresh()

    def _delete_pto(self):
        pid = self._get_selected_pto_id()
        if not pid:
            QMessageBox.information(self, "Select", "Please select a PTO entry.")
            return
        if QMessageBox.question(self, "Confirm", f"Delete PTO entry {pid}?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            username = self.app_state["user"]["username"]
            data_manager.delete_pto(pid)
            audit.log_event("operations", "pto_delete", username, f"Deleted PTO {pid}")
            self.refresh()


# ── Backward compatibility alias
PTOForecastPage = PTOCoveragePage
