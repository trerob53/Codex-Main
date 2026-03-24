"""
Cerasus Hub -- Operations Module: Open Requests (Coverage Dispatch) Page
Manages coverage requests when a site needs a shift filled (call-off, PTO,
vacancy).  Dispatchers create requests here and assign flex officers.
"""

from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QTimeEdit, QTextEdit, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QDialog, QFormLayout, QDialogButtonBox, QMessageBox,
    QAbstractItemView, QSizePolicy,
)
from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtGui import QFont

from src.config import COLORS, build_dialog_stylesheet, tc, _is_dark, btn_style
from src.modules.operations.data_manager import (
    get_all_requests, create_request, update_request, delete_request,
    fill_request, get_request_summary, get_ops_officers, get_all_assignments,
    calculate_shift_hours, detect_conflicts, get_officer_pto_for_date,
)
from src.shared_data import get_site_names
from src import audit


# ════════════════════════════════════════════════════════════════════════
# Helper: stat card widget
# ════════════════════════════════════════════════════════════════════════

def _stat_card(label: str, value, accent: str = "") -> QFrame:
    """Build a small stat card frame with a value and label."""
    card = QFrame()
    card.setFixedHeight(72)
    card.setMinimumWidth(130)
    border_color = accent if accent else tc("border")
    card.setStyleSheet(f"""
        QFrame {{
            background: {tc('card')};
            border: 1px solid {border_color};
            border-radius: 8px;
        }}
    """)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 8, 14, 8)
    layout.setSpacing(2)

    val_lbl = QLabel(str(value))
    val_lbl.setFont(QFont("Segoe UI", 18, QFont.Bold))
    val_lbl.setAlignment(Qt.AlignCenter)
    val_color = accent if accent else tc("text")
    val_lbl.setStyleSheet(f"color: {val_color}; background: transparent; border: none;")
    layout.addWidget(val_lbl)

    txt_lbl = QLabel(label)
    txt_lbl.setAlignment(Qt.AlignCenter)
    txt_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; background: transparent; border: none;")
    layout.addWidget(txt_lbl)

    return card


# ════════════════════════════════════════════════════════════════════════
# New / Edit Request Dialog
# ════════════════════════════════════════════════════════════════════════

class RequestDialog(QDialog):
    """Dialog for creating or editing a coverage request."""

    def __init__(self, parent=None, existing: dict = None):
        super().__init__(parent)
        self._existing = existing
        title = "Edit Request" if existing else "New Coverage Request"
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.setMinimumHeight(420)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()
        if existing:
            self._populate(existing)

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Site
        self.cmb_site = QComboBox()
        sites = get_site_names()
        self._site_names = [s.get("name", "") for s in sites if s.get("name")]
        self.cmb_site.addItems(self._site_names)
        layout.addRow("Site:", self.cmb_site)

        # Date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        layout.addRow("Date:", self.date_edit)

        # Start Time
        self.time_start = QTimeEdit()
        self.time_start.setDisplayFormat("HH:mm")
        self.time_start.setTime(QTime(7, 0))
        layout.addRow("Start Time:", self.time_start)

        # End Time
        self.time_end = QTimeEdit()
        self.time_end.setDisplayFormat("HH:mm")
        self.time_end.setTime(QTime(15, 0))
        layout.addRow("End Time:", self.time_end)

        # Reason
        self.cmb_reason = QComboBox()
        self.cmb_reason.addItems(["Coverage", "PTO", "Vacancy", "Event", "Other"])
        layout.addRow("Reason:", self.cmb_reason)

        # Priority
        self.cmb_priority = QComboBox()
        self.cmb_priority.addItems(["Normal", "Urgent", "Emergency"])
        layout.addRow("Priority:", self.cmb_priority)

        # Requested By
        self.txt_requested_by = QLineEdit()
        self.txt_requested_by.setPlaceholderText("Dispatcher or supervisor name")
        layout.addRow("Requested By:", self.txt_requested_by)

        # Notes
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Additional details...")
        self.txt_notes.setMaximumHeight(90)
        layout.addRow("Notes:", self.txt_notes)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _populate(self, data: dict):
        site = data.get("site_name", "")
        if site in self._site_names:
            self.cmb_site.setCurrentText(site)
        d = data.get("date", "")
        if d:
            self.date_edit.setDate(QDate.fromString(d, "yyyy-MM-dd"))
        st = data.get("start_time", "")
        if st:
            self.time_start.setTime(QTime.fromString(st, "HH:mm"))
        et = data.get("end_time", "")
        if et:
            self.time_end.setTime(QTime.fromString(et, "HH:mm"))
        reason = data.get("reason", "")
        if reason:
            idx = self.cmb_reason.findText(reason)
            if idx >= 0:
                self.cmb_reason.setCurrentIndex(idx)
        priority = data.get("priority", "")
        if priority:
            idx = self.cmb_priority.findText(priority)
            if idx >= 0:
                self.cmb_priority.setCurrentIndex(idx)
        self.txt_requested_by.setText(data.get("requested_by", ""))
        self.txt_notes.setPlainText(data.get("notes", ""))

    def _on_save(self):
        if not self.cmb_site.currentText().strip():
            QMessageBox.warning(self, "Validation", "Please select a site.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "site_name": self.cmb_site.currentText().strip(),
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
            "start_time": self.time_start.time().toString("HH:mm"),
            "end_time": self.time_end.time().toString("HH:mm"),
            "reason": self.cmb_reason.currentText(),
            "priority": self.cmb_priority.currentText(),
            "requested_by": self.txt_requested_by.text().strip(),
            "notes": self.txt_notes.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Assign Officer Dialog
# ════════════════════════════════════════════════════════════════════════

class AssignOfficerDialog(QDialog):
    """Dialog to pick a flex officer and assign them to a coverage request."""

    def __init__(self, request: dict, parent=None):
        super().__init__(parent)
        self._request = request
        self.setWindowTitle("Assign Officer")
        self.setMinimumWidth(640)
        self.setMinimumHeight(440)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._selected_officer = ""
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Request summary
        req = self._request
        site = req.get("site_name", "")
        date = req.get("date", "")
        start = req.get("start_time", "")
        end = req.get("end_time", "")
        reason = req.get("reason", "")
        priority = req.get("priority", "")

        summary_lbl = QLabel(
            f"<b>Request:</b> {site} on {date}  |  {start} - {end}  |  "
            f"{reason}  |  Priority: {priority}"
        )
        summary_lbl.setWordWrap(True)
        summary_lbl.setStyleSheet(f"""
            QLabel {{
                color: {tc('text')};
                font-size: 13px;
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 6px;
                padding: 10px 14px;
            }}
        """)
        layout.addWidget(summary_lbl)

        # Officer table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Phone", "Weekly Hours", "Conflict", "Select"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self._load_officers()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_assign = QPushButton("Assign && Fill")
        self.btn_assign.setCursor(Qt.PointingHandCursor)
        self.btn_assign.setFixedHeight(38)
        self.btn_assign.setStyleSheet(btn_style(tc("accent"), "white", tc("accent_hover")))
        self.btn_assign.setEnabled(False)
        self.btn_assign.clicked.connect(self._on_assign)
        btn_row.addWidget(self.btn_assign)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFixedHeight(38)
        btn_cancel.setStyleSheet(btn_style(tc("border"), tc("text")))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        layout.addLayout(btn_row)

    def _load_officers(self):
        officers = get_ops_officers()
        req_date = self._request.get("date", "")
        req_start = self._request.get("start_time", "")
        req_end = self._request.get("end_time", "")

        self.table.setRowCount(len(officers))
        self._officer_names = []

        for row, officer in enumerate(officers):
            name = officer.get("name", "")
            self._officer_names.append(name)

            # Name
            item_name = QTableWidgetItem(name)
            self.table.setItem(row, 0, item_name)

            # Phone
            phone = officer.get("phone", "")
            self.table.setItem(row, 1, QTableWidgetItem(phone))

            # Weekly hours
            weekly = officer.get("weekly_hours", "40")
            self.table.setItem(row, 2, QTableWidgetItem(str(weekly)))

            # Conflict check
            conflicts = detect_conflicts(name, req_date, req_start, req_end)
            pto = get_officer_pto_for_date(name, req_date)
            conflict_text = ""
            if pto:
                conflict_text = "PTO"
            elif conflicts:
                conflict_text = "Overlap"
            else:
                conflict_text = "None"

            conflict_item = QTableWidgetItem(conflict_text)
            if conflict_text == "PTO":
                conflict_item.setForeground(Qt.red)
            elif conflict_text == "Overlap":
                conflict_item.setForeground(Qt.darkYellow)
            self.table.setItem(row, 3, conflict_item)

            # Select button
            btn = QPushButton("Select")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet(btn_style(tc("primary_light"), "white", tc("primary_mid")))
            btn.clicked.connect(lambda checked, n=name: self._select_officer(n))
            self.table.setCellWidget(row, 4, btn)

    def _select_officer(self, name: str):
        self._selected_officer = name
        self.btn_assign.setEnabled(True)
        self.btn_assign.setText(f"Assign {name} && Fill")

    def _on_assign(self):
        if not self._selected_officer:
            return
        self.accept()

    def get_selected_officer(self) -> str:
        return self._selected_officer


# ════════════════════════════════════════════════════════════════════════
# Open Requests Page
# ════════════════════════════════════════════════════════════════════════

class OpenRequestsPage(QWidget):
    """Coverage dispatch page — create requests and assign flex officers."""

    COLUMNS = ["Site", "Date", "Time", "Hours", "Reason", "Priority", "Status", "Assigned To", "Actions"]

    def __init__(self, app_state=None):
        super().__init__()
        self.app_state = app_state or {}
        self._requests: list[dict] = []
        self._build()

    # ── Hub shell entry point ──────────────────────────────────────────
    def _init_page(self, app_state):
        """Called by the hub shell when loading this page."""
        self.app_state = app_state
        self._refresh()

    # ── Build UI ───────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── Header row ─────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("Open Requests \u2014 Coverage Dispatch")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        header.addWidget(title)

        header.addStretch()

        self.btn_new = QPushButton("+ New Request")
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.setFixedHeight(38)
        self.btn_new.setStyleSheet(btn_style(tc("accent"), "white", tc("accent_hover")))
        self.btn_new.clicked.connect(self._on_new_request)
        header.addWidget(self.btn_new)

        root.addLayout(header)

        # ── Stat cards ─────────────────────────────────────────────────
        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(12)
        # Placeholder cards — filled in _refresh
        self._stat_open = _stat_card("Open", 0, COLORS["accent"])
        self._stat_urgent = _stat_card("Urgent", 0, COLORS["warning"])
        self._stat_filled = _stat_card("Filled Today", 0, COLORS["success"])
        self._stat_rate = _stat_card("Fill Rate", "0%")
        self.stats_row.addWidget(self._stat_open)
        self.stats_row.addWidget(self._stat_urgent)
        self.stats_row.addWidget(self._stat_filled)
        self.stats_row.addWidget(self._stat_rate)
        self.stats_row.addStretch()
        root.addLayout(self.stats_row)

        # ── Filter bar ─────────────────────────────────────────────────
        filt = QHBoxLayout()
        filt.setSpacing(10)

        lbl_site = QLabel("Site:")
        lbl_site.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 14px; background: transparent;")
        filt.addWidget(lbl_site)

        self.cmb_site = QComboBox()
        self.cmb_site.setMinimumWidth(180)
        sites = get_site_names()
        self._site_names = [s.get("name", "") for s in sites if s.get("name")]
        self.cmb_site.addItems(["All Sites"] + self._site_names)
        self.cmb_site.currentIndexChanged.connect(self._refresh)
        filt.addWidget(self.cmb_site)

        lbl_status = QLabel("Status:")
        lbl_status.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 14px; background: transparent;")
        filt.addWidget(lbl_status)

        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["All", "Open", "Assigned", "Filled", "Cancelled"])
        self.cmb_status.currentIndexChanged.connect(self._refresh)
        filt.addWidget(self.cmb_status)

        lbl_priority = QLabel("Priority:")
        lbl_priority.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 14px; background: transparent;")
        filt.addWidget(lbl_priority)

        self.cmb_priority = QComboBox()
        self.cmb_priority.addItems(["All", "Normal", "Urgent", "Emergency"])
        self.cmb_priority.currentIndexChanged.connect(self._refresh)
        filt.addWidget(self.cmb_priority)

        filt.addStretch()

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.setStyleSheet(btn_style(tc("primary_light"), "white", tc("primary_mid")))
        self.btn_refresh.clicked.connect(self._refresh)
        filt.addWidget(self.btn_refresh)

        root.addLayout(filt)

        # ── Separator ──────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {tc('border')};")
        root.addWidget(sep)

        # ── Main table ─────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)  # Site
        for col in range(1, len(self.COLUMNS) - 1):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(len(self.COLUMNS) - 1, QHeaderView.Fixed)
        self.table.horizontalHeader().resizeSection(len(self.COLUMNS) - 1, 220)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_double_click)
        root.addWidget(self.table, 1)

    # ── Data Loading ───────────────────────────────────────────────────
    def _refresh(self):
        """Reload data from database and repopulate UI."""
        self._load_stats()
        self._load_table()

    def _load_stats(self):
        """Refresh stat card values."""
        try:
            summary = get_request_summary()
        except Exception:
            summary = {"open": 0, "urgent": 0, "filled_today": 0, "fill_rate": 0}

        # Replace stat cards
        self._replace_stat(self._stat_open, "Open", summary.get("open", 0), COLORS["accent"])
        self._replace_stat(self._stat_urgent, "Urgent", summary.get("urgent", 0), COLORS["warning"])
        self._replace_stat(self._stat_filled, "Filled Today", summary.get("filled_today", 0), COLORS["success"])
        self._replace_stat(self._stat_rate, "Fill Rate", f"{summary.get('fill_rate', 0)}%")

    def _replace_stat(self, old_card: QFrame, label: str, value, accent: str = ""):
        """Update an existing stat card's displayed values in-place."""
        layout = old_card.layout()
        if not layout:
            return
        # Update value label (first widget)
        val_widget = layout.itemAt(0).widget()
        if val_widget:
            val_widget.setText(str(value))
            val_color = accent if accent else tc("text")
            val_widget.setStyleSheet(f"color: {val_color}; background: transparent; border: none;")
        # Update border accent
        border_color = accent if accent else tc("border")
        old_card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)

    def _get_filters(self) -> tuple:
        """Return (site, status, priority) filter values."""
        site = self.cmb_site.currentText()
        site = "" if site == "All Sites" else site
        status = self.cmb_status.currentText()
        status = "" if status == "All" else status
        priority = self.cmb_priority.currentText()
        priority = "" if priority == "All" else priority
        return site, status, priority

    def _load_table(self):
        """Reload the requests table."""
        site, status, priority = self._get_filters()
        try:
            self._requests = get_all_requests(
                site_filter=site, status_filter=status, priority_filter=priority
            )
        except Exception:
            self._requests = []

        self.table.setRowCount(len(self._requests))

        for row, req in enumerate(self._requests):
            # Site
            self.table.setItem(row, 0, QTableWidgetItem(req.get("site_name", "")))

            # Date
            self.table.setItem(row, 1, QTableWidgetItem(req.get("date", "")))

            # Time
            start = req.get("start_time", "")
            end = req.get("end_time", "")
            time_str = f"{start} - {end}" if start and end else ""
            self.table.setItem(row, 2, QTableWidgetItem(time_str))

            # Hours
            hours = req.get("hours", "0")
            self.table.setItem(row, 3, QTableWidgetItem(str(hours)))

            # Reason
            self.table.setItem(row, 4, QTableWidgetItem(req.get("reason", "")))

            # Priority badge
            pri = req.get("priority", "Normal")
            pri_item = QTableWidgetItem(pri)
            if pri == "Emergency":
                pri_item.setForeground(Qt.white)
                pri_item.setBackground(Qt.red)
            elif pri == "Urgent":
                pri_item.setForeground(Qt.black)
                pri_item.setBackground(Qt.yellow)
            self.table.setItem(row, 5, pri_item)

            # Status badge
            st = req.get("status", "Open")
            st_item = QTableWidgetItem(st)
            if st == "Open":
                st_item.setForeground(Qt.white)
                st_item.setBackground(Qt.blue)
            elif st == "Assigned":
                st_item.setForeground(Qt.black)
                st_item.setBackground(Qt.yellow)
            elif st == "Filled":
                st_item.setForeground(Qt.white)
                st_item.setBackground(Qt.darkGreen)
            elif st == "Cancelled":
                st_item.setForeground(Qt.white)
                st_item.setBackground(Qt.gray)
            self.table.setItem(row, 6, st_item)

            # Assigned To
            self.table.setItem(row, 7, QTableWidgetItem(req.get("assigned_officer", "")))

            # Actions cell — buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(4)

            if st == "Open":
                btn_assign = QPushButton("Assign")
                btn_assign.setCursor(Qt.PointingHandCursor)
                btn_assign.setFixedHeight(26)
                btn_assign.setStyleSheet(btn_style(tc("accent"), "white", tc("accent_hover")))
                btn_assign.clicked.connect(lambda checked, r=row: self._on_assign(r))
                actions_layout.addWidget(btn_assign)

            btn_edit = QPushButton("Edit")
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.setFixedHeight(26)
            btn_edit.setStyleSheet(btn_style(tc("primary_light"), "white", tc("primary_mid")))
            btn_edit.clicked.connect(lambda checked, r=row: self._on_edit(r))
            actions_layout.addWidget(btn_edit)

            btn_del = QPushButton("Delete")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedHeight(26)
            btn_del.setStyleSheet(btn_style(tc("danger"), "white", tc("accent_hover")))
            btn_del.clicked.connect(lambda checked, r=row: self._on_delete(r))
            actions_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 8, actions_widget)

        self.table.resizeRowsToContents()

    # ── Actions ────────────────────────────────────────────────────────

    def _get_username(self) -> str:
        return (
            self.app_state.get("user", {}).get("display_name", "")
            or self.app_state.get("user", {}).get("username", "Unknown")
        )

    def _on_new_request(self):
        dlg = RequestDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            username = self._get_username()
            rid = create_request(data, created_by=username)
            audit.log_event(
                "operations", "create_request", username,
                details=f"Created coverage request {rid} for {data.get('site_name', '')}",
                table_name="ops_open_requests", record_id=rid, action="create",
            )
            self._refresh()

    def _on_edit(self, row: int):
        if row < 0 or row >= len(self._requests):
            return
        req = self._requests[row]
        dlg = RequestDialog(self, existing=req)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            rid = req.get("request_id", "")
            username = self._get_username()
            update_request(rid, data, updated_by=username)
            audit.log_event(
                "operations", "update_request", username,
                details=f"Updated coverage request {rid}",
                table_name="ops_open_requests", record_id=rid, action="update",
            )
            self._refresh()

    def _on_double_click(self, index):
        self._on_edit(index.row())

    def _on_delete(self, row: int):
        if row < 0 or row >= len(self._requests):
            return
        req = self._requests[row]
        rid = req.get("request_id", "")
        site = req.get("site_name", "")
        ans = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete coverage request for {site} on {req.get('date', '')}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            username = self._get_username()
            delete_request(rid)
            audit.log_event(
                "operations", "delete_request", username,
                details=f"Deleted coverage request {rid} ({site})",
                table_name="ops_open_requests", record_id=rid, action="delete",
            )
            self._refresh()

    def _on_assign(self, row: int):
        if row < 0 or row >= len(self._requests):
            return
        req = self._requests[row]
        rid = req.get("request_id", "")

        dlg = AssignOfficerDialog(req, parent=self)
        if dlg.exec() == QDialog.Accepted:
            officer = dlg.get_selected_officer()
            if officer:
                username = self._get_username()
                aid = fill_request(rid, officer, updated_by=username)
                audit.log_event(
                    "operations", "fill_request", username,
                    details=f"Assigned {officer} to request {rid}, assignment {aid}",
                    table_name="ops_open_requests", record_id=rid, action="fill",
                )
                self._refresh()

    def refresh(self):
        """External refresh hook (e.g. tab switch)."""
        self._refresh()
