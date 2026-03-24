"""
Cerasus Hub -- DA Generator Module: History Page
Searchable table of all generated DAs with summary cards, detail view, and PDF export.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QComboBox,
    QAbstractItemView, QMessageBox, QDialog, QScrollArea, QFormLayout,
    QTextBrowser, QDialogButtonBox, QTextEdit, QDateEdit, QCheckBox,
)
from PySide6.QtCore import Qt, QUrl, Signal, QDate
from PySide6.QtGui import QFont, QColor, QDesktopServices
from datetime import datetime, timezone
from urllib.parse import quote

from src.config import COLORS, tc, btn_style, build_dialog_stylesheet, _is_dark, REPORTS_DIR
from src.shared_widgets import confirm_action, export_table_to_csv
from src.modules.da_generator import data_manager
from src.pdf_export import PDFDocument, save_pdf_dialog
from src import audit


# ── Status / discipline-level labels ──────────────────────────────────
STATUS_OPTIONS = ["All", "Draft", "Pending Review", "Delivered", "Signed", "Completed", "Pending Acknowledgments"]

# Map display label -> database value for the status filter
_STATUS_DISPLAY_TO_DB = {
    "All": "All",
    "Draft": "draft",
    "Pending Review": "pending_review",
    "Delivered": "delivered",
    "Signed": "signed",
    "Completed": "completed",
    "Pending Acknowledgments": "_pending_ack",
}

STATUS_BADGE_COLORS = {
    "draft": "#6B7280",
    "pending_review": "#F59E0B",
    "delivered": "#3B82F6",
    "signed": "#10B981",
    "completed": "#10B981",
}

# Workflow ordering used by the "Change Status" action
STATUS_WORKFLOW_ORDER = ["draft", "pending_review", "delivered", "signed", "completed"]

DISCIPLINE_LABELS = {
    "verbal_warning": "Verbal Warning",
    "written_warning": "Written Warning",
    "final_warning": "Final Warning",
    "termination": "Termination",
}


# ── Turnaround time helpers ───────────────────────────────────────────

def _format_turnaround(hours: float) -> str:
    """Format hours into a human-readable turnaround string."""
    if hours <= 0:
        return "—"
    days = hours / 24.0
    if days >= 1:
        whole_days = int(days)
        remaining_hours = int(hours - whole_days * 24)
        if remaining_hours > 0:
            return f"{whole_days}d {remaining_hours}h"
        return f"{whole_days}d"
    return f"{int(hours)}h"


def _turnaround_color(avg_hours: float) -> str:
    """Return green/yellow/red hex color based on average turnaround."""
    days = avg_hours / 24.0
    if days < 3:
        return COLORS["success"]
    elif days <= 7:
        return COLORS["warning"]
    return COLORS["danger"]


def _calc_record_turnaround(rec: dict) -> tuple[float | None, str]:
    """Calculate turnaround hours and display string for a single DA record.

    Returns (hours_or_None, display_string).
    """
    created_str = rec.get("created_at", "")
    if not created_str:
        return None, "—"

    try:
        created_dt = datetime.fromisoformat(created_str)
    except (ValueError, TypeError):
        return None, "—"

    status = rec.get("status", "")
    completed_statuses = {"signed", "completed", "delivered"}

    if status in completed_statuses:
        # Pick the best end timestamp
        end_str = ""
        for key in ("signed_at", "delivered_at", "updated_at"):
            val = rec.get(key, "")
            if val:
                end_str = val
                break
        if not end_str:
            return None, "—"
        try:
            end_dt = datetime.fromisoformat(end_str)
            hours = (end_dt - created_dt).total_seconds() / 3600.0
            return hours, _format_turnaround(hours) if hours >= 0 else "—"
        except (ValueError, TypeError):
            return None, "—"
    else:
        # Still open — show "In Progress (Xd)"
        now = datetime.now(timezone.utc)
        try:
            hours = (now - created_dt).total_seconds() / 3600.0
            return None, f"In Progress ({_format_turnaround(hours)})"
        except Exception:
            return None, "In Progress"


class DAHistoryPage(QWidget):
    """Page listing all generated DAs in a searchable, filterable table."""

    # Emitted when user clicks "Resume Draft" with a valid draft record.
    # The dict is the full DA record from the database.
    resume_draft_requested = Signal(dict)

    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._records: list[dict] = []

        # Card value labels (set in _build, updated in _update_cards)
        self._card_total_lbl: QLabel | None = None
        self._card_verbal_lbl: QLabel | None = None
        self._card_written_lbl: QLabel | None = None
        self._card_final_lbl: QLabel | None = None
        self._card_term_lbl: QLabel | None = None

        # KPI turnaround card labels
        self._kpi_avg_lbl: QLabel | None = None
        self._kpi_avg_card: QFrame | None = None
        self._kpi_open_lbl: QLabel | None = None
        self._kpi_month_lbl: QLabel | None = None
        self._kpi_range_lbl: QLabel | None = None

        # Extended stats labels
        self._stat_dtd_lbl: QLabel | None = None
        self._stat_violation_lbl: QLabel | None = None
        self._monthly_table: QTableWidget | None = None

        self._build()

    # ── Layout ────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # -- Header row: title + search + status filter --------------------
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title = QLabel("DA History")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; background: transparent; border: none;")
        header_row.addWidget(title)

        header_row.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search employee, site, ID...")
        self.search_box.setFixedWidth(260)
        self.search_box.textChanged.connect(self._apply_filters)
        header_row.addWidget(self.search_box)

        self.status_filter = QComboBox()
        self.status_filter.addItems(STATUS_OPTIONS)
        self.status_filter.setFixedWidth(200)
        self.status_filter.currentTextChanged.connect(self._apply_filters)
        header_row.addWidget(self.status_filter)

        root.addLayout(header_row)

        # -- Date range filter row -----------------------------------------
        date_row = QHBoxLayout()
        date_row.setSpacing(8)
        date_row.addStretch()

        from_lbl = QLabel("From:")
        from_lbl.setStyleSheet(f"color: {tc('text')}; font-size: 13px; background: transparent; border: none;")
        date_row.addWidget(from_lbl)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setDate(QDate.currentDate().addMonths(-6))
        self.date_from.setFixedWidth(140)
        self.date_from.dateChanged.connect(self._apply_filters)
        date_row.addWidget(self.date_from)

        to_lbl = QLabel("To:")
        to_lbl.setStyleSheet(f"color: {tc('text')}; font-size: 13px; background: transparent; border: none;")
        date_row.addWidget(to_lbl)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setFixedWidth(140)
        self.date_to.dateChanged.connect(self._apply_filters)
        date_row.addWidget(self.date_to)

        self.date_filter_enabled = QCheckBox("Filter by date")
        self.date_filter_enabled.setStyleSheet(f"color: {tc('text')}; font-size: 13px; background: transparent; border: none;")
        self.date_filter_enabled.stateChanged.connect(self._apply_filters)
        date_row.addWidget(self.date_filter_enabled)

        root.addLayout(date_row)

        # -- Summary cards -------------------------------------------------
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)

        card_total, self._card_total_lbl = self._make_card("Total DAs", 0, COLORS["info"])
        card_verbal, self._card_verbal_lbl = self._make_card("Verbal Warnings", 0, COLORS["warning"])
        card_written, self._card_written_lbl = self._make_card("Written Warnings", 0, COLORS["accent"])
        card_final, self._card_final_lbl = self._make_card("Final Warnings", 0, COLORS["danger"])
        card_term, self._card_term_lbl = self._make_card("Terminations", 0, COLORS["primary"])

        for card in (card_total, card_verbal, card_written, card_final, card_term):
            cards_row.addWidget(card)

        root.addLayout(cards_row)

        # -- KPI turnaround stats row --------------------------------------
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        kpi_avg_card, self._kpi_avg_lbl = self._make_card("Avg Turnaround", "—", COLORS["success"])
        self._kpi_avg_card = kpi_avg_card
        kpi_open_card, self._kpi_open_lbl = self._make_card("Open DAs", "0", COLORS["info"])
        kpi_month_card, self._kpi_month_lbl = self._make_card("Completed This Month", "0", COLORS["success"])
        kpi_range_card, self._kpi_range_lbl = self._make_card("Fastest / Slowest", "—", COLORS["accent"])

        for card in (kpi_avg_card, kpi_open_card, kpi_month_card, kpi_range_card):
            kpi_row.addWidget(card)

        root.addLayout(kpi_row)

        # -- Extended stats row: avg draft-to-delivery, most common violation ---
        ext_row = QHBoxLayout()
        ext_row.setSpacing(12)

        stat_dtd_card, self._stat_dtd_lbl = self._make_card("Avg Draft \u2192 Delivery", "\u2014", COLORS["info"])
        stat_viol_card, self._stat_violation_lbl = self._make_card("Most Common Violation", "\u2014", COLORS["warning"])
        ext_row.addWidget(stat_dtd_card)
        ext_row.addWidget(stat_viol_card)

        # DAs by month mini-table (last 6 months)
        month_frame = QFrame()
        month_frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border-radius: 8px;
                border-left: 4px solid {COLORS['accent']}; padding: 12px;
            }}
        """)
        month_lay = QVBoxLayout(month_frame)
        month_lay.setContentsMargins(12, 8, 12, 8)
        month_title = QLabel("DAs by Month (Last 6)")
        month_title.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; background: transparent; border: none;")
        month_lay.addWidget(month_title)

        self._monthly_table = QTableWidget()
        self._monthly_table.setColumnCount(6)
        self._monthly_table.setRowCount(1)
        self._monthly_table.verticalHeader().setVisible(False)
        self._monthly_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._monthly_table.setFixedHeight(60)
        self._monthly_table.setStyleSheet(f"background: {tc('card')}; color: {tc('text')}; border: none; font-size: 13px;")
        self._monthly_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        month_lay.addWidget(self._monthly_table)

        ext_row.addWidget(month_frame, 2)

        root.addLayout(ext_row)

        # -- Table ---------------------------------------------------------
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "DA ID", "Employee", "Site", "Date", "Type",
            "Discipline Level", "Status", "Ack", "Created", "Turnaround",
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # DA ID
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)            # Employee
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)   # Site
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)   # Date
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)   # Type
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)   # Discipline Level
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)   # Status
        hdr.setSectionResizeMode(7, QHeaderView.ResizeToContents)   # Ack
        hdr.setSectionResizeMode(8, QHeaderView.ResizeToContents)   # Created
        hdr.setSectionResizeMode(9, QHeaderView.ResizeToContents)   # Turnaround
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 14px; padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)

        root.addWidget(self.table, 1)

        # -- Action buttons ------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.btn_view = QPushButton("View Details")
        self.btn_view.setStyleSheet(btn_style(COLORS["info"]))
        self.btn_view.setCursor(Qt.PointingHandCursor)
        self.btn_view.clicked.connect(self._view_details)
        btn_row.addWidget(self.btn_view)

        self.btn_change_status = QPushButton("Change Status \u25B6")
        self.btn_change_status.setStyleSheet(btn_style(COLORS["primary"]))
        self.btn_change_status.setCursor(Qt.PointingHandCursor)
        self.btn_change_status.clicked.connect(self._change_status)
        btn_row.addWidget(self.btn_change_status)

        self.btn_batch_status = QPushButton("Batch Update Status")
        self.btn_batch_status.setStyleSheet(btn_style(COLORS["primary"]))
        self.btn_batch_status.setCursor(Qt.PointingHandCursor)
        self.btn_batch_status.clicked.connect(self._batch_update_status)
        btn_row.addWidget(self.btn_batch_status)

        self.btn_resume = QPushButton("Resume Draft")
        self.btn_resume.setStyleSheet(btn_style(COLORS["warning"]))
        self.btn_resume.setCursor(Qt.PointingHandCursor)
        self.btn_resume.clicked.connect(self._resume_draft)
        btn_row.addWidget(self.btn_resume)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setStyleSheet(btn_style(COLORS["danger"]))
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.clicked.connect(self._delete_da)
        btn_row.addWidget(self.btn_delete)

        self.btn_export = QPushButton("Export PDF")
        self.btn_export.setStyleSheet(btn_style(COLORS["success"]))
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self._export_pdf)
        btn_row.addWidget(self.btn_export)

        self.btn_send_email = QPushButton("Send Email")
        self.btn_send_email.setStyleSheet(btn_style(COLORS["info"]))
        self.btn_send_email.setCursor(Qt.PointingHandCursor)
        self.btn_send_email.clicked.connect(self._send_email)
        btn_row.addWidget(self.btn_send_email)

        self.btn_acknowledge = QPushButton("Acknowledge")
        self.btn_acknowledge.setStyleSheet(btn_style(COLORS["success"]))
        self.btn_acknowledge.setCursor(Qt.PointingHandCursor)
        self.btn_acknowledge.clicked.connect(self._acknowledge_da)
        btn_row.addWidget(self.btn_acknowledge)

        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_csv.setStyleSheet(btn_style(COLORS["info"]))
        self.btn_export_csv.setCursor(Qt.PointingHandCursor)
        self.btn_export_csv.clicked.connect(self._export_table_csv)
        btn_row.addWidget(self.btn_export_csv)

        root.addLayout(btn_row)

        # Initial load
        self._load_data()

    # ── Card helper ───────────────────────────────────────────────────
    def _make_card(self, label: str, value: int, color: str):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border-radius: 8px;
                border-left: 4px solid {color}; padding: 12px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        val_lbl = QLabel(str(value))
        val_lbl.setFont(QFont("Segoe UI", 22, QFont.Bold))
        val_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        lay.addWidget(val_lbl)
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; background: transparent; border: none;")
        lay.addWidget(name_lbl)
        return card, val_lbl

    # ── Data loading / filtering ──────────────────────────────────────
    def refresh(self):
        self._load_data()

    def _load_data(self):
        """Fetch all DAs and apply current filters."""
        display_status = self.status_filter.currentText()
        db_status = _STATUS_DISPLAY_TO_DB.get(display_status, display_status)
        if db_status == "All":
            self._records = data_manager.get_all_das()
        elif db_status == "_pending_ack":
            self._records = data_manager.get_pending_acknowledgments()
        else:
            self._records = data_manager.get_all_das(status_filter=db_status)
        self._apply_filters()

    def _apply_filters(self):
        """Filter the cached records by search text, date range, and repopulate."""
        query = self.search_box.text().strip().lower()
        use_date_range = self.date_filter_enabled.isChecked()
        date_from = self.date_from.date().toString("yyyy-MM-dd") if use_date_range else ""
        date_to = self.date_to.date().toString("yyyy-MM-dd") if use_date_range else ""

        filtered = []
        for rec in self._records:
            # Text search: employee, site, ID, violation type, AND CEIS narrative
            if query:
                haystack = " ".join([
                    rec.get("da_id", ""),
                    rec.get("employee_name", ""),
                    rec.get("site", ""),
                    rec.get("violation_type", ""),
                    rec.get("ceis_narrative", ""),
                    rec.get("incident_narrative", ""),
                ]).lower()
                if query not in haystack:
                    continue

            # Date range filter on created_at
            if use_date_range:
                created = (rec.get("created_at") or "")[:10]
                if created:
                    if date_from and created < date_from:
                        continue
                    if date_to and created > date_to:
                        continue

            filtered.append(rec)

        self._populate_table(filtered)
        self._update_cards(filtered)

    def _populate_table(self, records: list):
        self.table.setRowCount(0)
        self.table.setRowCount(len(records))

        for row_idx, rec in enumerate(records):
            da_id = rec.get("da_id", "")
            employee = rec.get("employee_name", "")
            site = rec.get("site", "")
            incident_dates = rec.get("incident_dates", "")
            violation_type = rec.get("violation_type", "")
            discipline_raw = rec.get("discipline_level", "")
            discipline = DISCIPLINE_LABELS.get(discipline_raw, discipline_raw.replace("_", " ").title() if discipline_raw else "")
            status = rec.get("status", "")
            created = rec.get("created_at", "")
            if created and len(created) >= 10:
                created = created[:10]

            # Calculate turnaround for this record
            _ta_hours, ta_display = _calc_record_turnaround(rec)

            # Ack column indicator
            ack_flag = rec.get("acknowledged", 0)

            items = [da_id, employee, site, incident_dates, violation_type, discipline, status, "", created, ta_display]
            for col_idx, text in enumerate(items):
                item = QTableWidgetItem(str(text))
                item.setData(Qt.UserRole, da_id)
                self.table.setItem(row_idx, col_idx, item)

            # Status color badge
            status_item = self.table.item(row_idx, 6)
            if status_item:
                badge_color = STATUS_BADGE_COLORS.get(status)
                if badge_color:
                    status_item.setForeground(QColor(badge_color))
                # Show a friendlier display label
                display_label = status.replace("_", " ").title() if status else ""
                status_item.setText(display_label)

            # Ack column: green checkmark or red X
            ack_item = self.table.item(row_idx, 7)
            if ack_item:
                if ack_flag:
                    ack_item.setText("\u2714")
                    ack_item.setForeground(QColor(COLORS["success"]))
                else:
                    ack_item.setText("\u2718")
                    ack_item.setForeground(QColor(COLORS["danger"]))
                ack_item.setTextAlignment(Qt.AlignCenter)

            # Turnaround column color
            ta_item = self.table.item(row_idx, 9)
            if ta_item and _ta_hours is not None:
                ta_item.setForeground(QColor(_turnaround_color(_ta_hours)))

        if not records:
            from src.shared_widgets import set_table_empty_state
            set_table_empty_state(self.table, "No disciplinary actions found.")

    def _update_cards(self, records: list):
        total = len(records)
        verbal = sum(1 for r in records if r.get("discipline_level", "") == "verbal_warning")
        written = sum(1 for r in records if r.get("discipline_level", "") == "written_warning")
        final = sum(1 for r in records if r.get("discipline_level", "") == "final_warning")
        term = sum(1 for r in records if r.get("discipline_level", "") == "termination")

        self._card_total_lbl.setText(str(total))
        self._card_verbal_lbl.setText(str(verbal))
        self._card_written_lbl.setText(str(written))
        self._card_final_lbl.setText(str(final))
        self._card_term_lbl.setText(str(term))

        # Update KPI turnaround cards from the database (unfiltered)
        self._update_kpi_cards()

    def _update_kpi_cards(self):
        """Refresh the turnaround KPI stat cards."""
        stats = data_manager.get_da_turnaround_stats()

        avg_h = stats["avg_hours"]
        min_h = stats["min_hours"]
        max_h = stats["max_hours"]

        # Average turnaround
        avg_text = _format_turnaround(avg_h) if avg_h > 0 else "\u2014"
        self._kpi_avg_lbl.setText(avg_text)

        # Recolor the avg card based on threshold
        avg_color = _turnaround_color(avg_h) if avg_h > 0 else COLORS["success"]
        self._kpi_avg_lbl.setStyleSheet(f"color: {avg_color}; background: transparent; border: none;")
        self._kpi_avg_card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border-radius: 8px;
                border-left: 4px solid {avg_color}; padding: 12px;
            }}
        """)

        # Open DAs
        self._kpi_open_lbl.setText(str(stats["open_count"]))

        # Completed this month
        self._kpi_month_lbl.setText(str(stats["completed_this_month"]))

        # Fastest / Slowest
        if min_h > 0 and max_h > 0:
            self._kpi_range_lbl.setText(f"{_format_turnaround(min_h)} / {_format_turnaround(max_h)}")
        else:
            self._kpi_range_lbl.setText("\u2014")

        # Extended stats
        self._update_extended_stats()

    def _update_extended_stats(self):
        """Refresh the extended statistics cards and monthly table."""
        try:
            ext = data_manager.get_da_extended_stats()
        except Exception:
            return

        # Avg draft-to-delivery
        dtd_h = ext.get("avg_draft_to_delivery_hours", 0.0)
        if dtd_h > 0:
            self._stat_dtd_lbl.setText(_format_turnaround(dtd_h))
        else:
            self._stat_dtd_lbl.setText("\u2014")

        # Most common violation
        mcv = ext.get("most_common_violation", "")
        if mcv:
            # Shorten long labels: "Type A — Attendance" -> "Type A"
            short = mcv.split("\u2014")[0].strip() if "\u2014" in mcv else mcv.split("—")[0].strip() if "—" in mcv else mcv
            self._stat_violation_lbl.setText(short)
        else:
            self._stat_violation_lbl.setText("\u2014")

        # Monthly table
        months = ext.get("das_by_month", [])
        if months and self._monthly_table:
            headers = [m[0] for m in months]
            self._monthly_table.setHorizontalHeaderLabels(headers)
            for col, (_label, count) in enumerate(months):
                item = QTableWidgetItem(str(count))
                item.setTextAlignment(Qt.AlignCenter)
                self._monthly_table.setItem(0, col, item)

    # ── Selected record helper ────────────────────────────────────────
    def _selected_da_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "No Selection", "Please select a DA from the table first.")
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item else None

    def _selected_da_ids(self) -> list[str]:
        """Return all selected DA IDs from the table (for multi-select operations)."""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return []
        ids = []
        for idx in rows:
            item = self.table.item(idx.row(), 0)
            if item:
                da_id = item.data(Qt.UserRole)
                if da_id:
                    ids.append(da_id)
        return ids

    # ── Actions ───────────────────────────────────────────────────────
    def _view_details(self):
        da_id = self._selected_da_id()
        if not da_id:
            return
        rec = data_manager.get_da(da_id)
        if not rec:
            QMessageBox.warning(self, "Not Found", f"DA {da_id} not found in database.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"DA Details \u2014 {da_id}")
        dlg.setMinimumSize(640, 560)
        dlg.setStyleSheet(build_dialog_stylesheet(_is_dark()))

        outer = QVBoxLayout(dlg)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)

        # -- Employee info --
        self._add_section(form, "Employee Information")
        self._add_field(form, "Employee Name", rec.get("employee_name", ""))
        self._add_field(form, "Position", rec.get("employee_position", ""))
        self._add_field(form, "Officer ID", rec.get("employee_officer_id", ""))
        self._add_field(form, "Site", rec.get("site", ""))
        self._add_field(form, "Security Director", rec.get("security_director", ""))

        # -- Incident info --
        self._add_section(form, "Incident Details")
        self._add_field(form, "Incident Date(s)", rec.get("incident_dates", ""))
        self._add_field(form, "Violation Type", rec.get("violation_type", ""))
        self._add_field(form, "Narrative", rec.get("incident_narrative", ""))

        # -- Prior discipline --
        self._add_section(form, "Prior Discipline (Same Category)")
        self._add_field(form, "Verbal", str(rec.get("prior_verbal_same", 0)))
        self._add_field(form, "Written", str(rec.get("prior_written_same", 0)))
        self._add_field(form, "Final", str(rec.get("prior_final_same", 0)))

        self._add_section(form, "Prior Discipline (Other Categories)")
        self._add_field(form, "Verbal", str(rec.get("prior_verbal_other", 0)))
        self._add_field(form, "Written", str(rec.get("prior_written_other", 0)))
        self._add_field(form, "Final", str(rec.get("prior_final_other", 0)))

        # -- Coaching --
        self._add_section(form, "Coaching / Counseling")
        self._add_field(form, "Coaching Occurred", "Yes" if rec.get("coaching_occurred") else "No")
        if rec.get("coaching_occurred"):
            self._add_field(form, "Coaching Date", rec.get("coaching_date", ""))
            self._add_field(form, "Content", rec.get("coaching_content", ""))
            self._add_field(form, "Outcome", rec.get("coaching_outcome", ""))

        # -- CEIS output sections --
        self._add_section(form, "CEIS Engine Output")
        self._add_field(form, "Narrative", rec.get("ceis_narrative", ""))
        self._add_field(form, "Citations", rec.get("ceis_citations", ""))
        self._add_field(form, "Violation Analysis", rec.get("ceis_violation_analysis", ""))
        self._add_field(form, "Discipline Determination", rec.get("ceis_discipline_determination", ""))
        self._add_field(form, "Risk Assessment", rec.get("ceis_risk_assessment", ""))
        self._add_field(form, "Recommendation", rec.get("ceis_recommendation", ""))

        # -- Final output --
        self._add_section(form, "Final DA Output")
        self._add_field(form, "Discipline Level", DISCIPLINE_LABELS.get(
            rec.get("discipline_level", ""), rec.get("discipline_level", "")))
        status_raw = rec.get("status", "")
        status_display = status_raw.replace("_", " ").title() if status_raw else ""
        self._add_field(form, "Status", status_display)
        self._add_field(form, "Final Narrative", rec.get("final_narrative", ""))
        self._add_field(form, "Final Citations", rec.get("final_citations", ""))
        self._add_field(form, "Required Improvements", rec.get("required_improvements", ""))
        self._add_field(form, "Additional Comments", rec.get("additional_comments", ""))

        # -- Acknowledgment --
        self._add_section(form, "Acknowledgment")
        ack_flag = rec.get("acknowledged", 0)
        ack_at = rec.get("acknowledged_at", "")
        if ack_flag:
            self._add_field(form, "Acknowledged", f"Yes ({ack_at})" if ack_at else "Yes")
        else:
            self._add_field(form, "Acknowledged", "No")
        self._add_field(form, "Employee Response", rec.get("employee_response", ""))
        self._add_field(form, "Acknowledged By", rec.get("acknowledged_by", ""))
        witness = rec.get("witness_name", "")
        witness_signed = rec.get("witness_signed", 0)
        witness_at = rec.get("witness_signed_at", "")
        if witness:
            witness_display = witness
            if witness_signed and witness_at:
                witness_display += f" (signed at {witness_at})"
            elif witness_signed:
                witness_display += " (signed)"
            self._add_field(form, "Witness", witness_display)
        else:
            self._add_field(form, "Witness", "")

        # -- Metadata --
        self._add_section(form, "Record Metadata")
        self._add_field(form, "Created", rec.get("created_at", ""))
        self._add_field(form, "Updated", rec.get("updated_at", ""))
        self._add_field(form, "Created By", rec.get("created_by", ""))
        delivered_at = rec.get("delivered_at", "")
        if delivered_at:
            self._add_field(form, "Delivered At", delivered_at)
        signed_at = rec.get("signed_at", "")
        if signed_at:
            self._add_field(form, "Signed At", signed_at)

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(dlg.reject)
        outer.addWidget(btn_box)

        dlg.exec()

    @staticmethod
    def _add_section(form: QFormLayout, title: str):
        lbl = QLabel(f"\n{title}")
        lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl.setStyleSheet(f"color: {COLORS['primary']}; background: transparent; border: none;")
        form.addRow(lbl)

    @staticmethod
    def _add_field(form: QFormLayout, label: str, value: str):
        lbl = QLabel(f"{label}:")
        lbl.setStyleSheet(f"color: {tc('text_light')}; font-weight: 600; font-size: 13px; background: transparent; border: none;")
        val = QLabel(str(value) if value else "\u2014")
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        val.setStyleSheet(f"color: {tc('text')}; font-size: 13px; background: transparent; border: none;")
        form.addRow(lbl, val)

    def _change_status(self):
        """Advance the selected DA to the next status in the workflow."""
        da_id = self._selected_da_id()
        if not da_id:
            return
        rec = data_manager.get_da(da_id)
        if not rec:
            QMessageBox.warning(self, "Not Found", f"DA {da_id} not found.")
            return

        current = rec.get("status", "draft")
        if current not in STATUS_WORKFLOW_ORDER:
            QMessageBox.information(
                self, "Cannot Change Status",
                f"Current status '{current}' is not part of the standard workflow.",
            )
            return

        idx = STATUS_WORKFLOW_ORDER.index(current)
        if idx >= len(STATUS_WORKFLOW_ORDER) - 1:
            QMessageBox.information(
                self, "Already Completed",
                f"DA {da_id} is already at the final status (completed).",
            )
            return

        next_status = STATUS_WORKFLOW_ORDER[idx + 1]
        next_label = next_status.replace("_", " ").title()
        current_label = current.replace("_", " ").title()

        if not confirm_action(
            self, "Change Status",
            f"Move DA {da_id} from '{current_label}' to '{next_label}'?",
        ):
            return

        username = getattr(self.app_state, "username", "")
        ok = data_manager.update_da_status(da_id, next_status, updated_by=username)
        if ok:
            audit.log_event(
                module_name="da_generator",
                event_type="status_change",
                username=username,
                details=f"Changed DA {da_id} status from {current} to {next_status}",
                table_name="da_records",
                record_id=da_id,
                action="status_change",
            )
            self._load_data()
        else:
            QMessageBox.warning(self, "Error", "Failed to update DA status.")

    def _batch_update_status(self):
        """Advance all selected DAs to their next workflow status."""
        da_ids = self._selected_da_ids()
        if not da_ids:
            QMessageBox.information(self, "No Selection", "Please select one or more DAs from the table first.")
            return

        # Gather eligible records
        eligible = []
        skipped = []
        for da_id in da_ids:
            rec = data_manager.get_da(da_id)
            if not rec:
                skipped.append(f"{da_id} (not found)")
                continue
            current = rec.get("status", "draft")
            if current not in STATUS_WORKFLOW_ORDER:
                skipped.append(f"{da_id} (status '{current}' not in workflow)")
                continue
            idx = STATUS_WORKFLOW_ORDER.index(current)
            if idx >= len(STATUS_WORKFLOW_ORDER) - 1:
                skipped.append(f"{da_id} (already completed)")
                continue
            next_status = STATUS_WORKFLOW_ORDER[idx + 1]
            eligible.append((da_id, current, next_status))

        if not eligible:
            msg = "No selected DAs can be advanced."
            if skipped:
                msg += "\n\nSkipped:\n" + "\n".join(skipped)
            QMessageBox.information(self, "Batch Update", msg)
            return

        # Build confirmation message
        summary_lines = []
        for da_id, current, next_s in eligible:
            summary_lines.append(
                f"  {da_id}: {current.replace('_', ' ').title()} -> {next_s.replace('_', ' ').title()}"
            )
        confirm_msg = f"Advance {len(eligible)} DA(s) to their next status?\n\n" + "\n".join(summary_lines)
        if skipped:
            confirm_msg += f"\n\n{len(skipped)} DA(s) skipped (already completed or invalid)."

        if not confirm_action(self, "Batch Status Update", confirm_msg):
            return

        username = getattr(self.app_state, "username", "")
        success_count = 0
        for da_id, current, next_status in eligible:
            ok = data_manager.update_da_status(da_id, next_status, updated_by=username)
            if ok:
                success_count += 1
                audit.log_event(
                    module_name="da_generator",
                    event_type="status_change",
                    username=username,
                    details=f"Batch: Changed DA {da_id} status from {current} to {next_status}",
                    table_name="da_records",
                    record_id=da_id,
                    action="status_change",
                )

        self._load_data()
        QMessageBox.information(
            self, "Batch Update Complete",
            f"Successfully advanced {success_count} of {len(eligible)} DA(s).",
        )

    def _resume_draft(self):
        da_id = self._selected_da_id()
        if not da_id:
            return
        rec = data_manager.get_da(da_id)
        if not rec:
            QMessageBox.warning(self, "Not Found", f"DA {da_id} not found.")
            return
        if rec.get("status") not in ("draft", "in_progress"):
            QMessageBox.information(
                self, "Cannot Resume",
                "Only DAs with status 'draft' or 'in_progress' can be resumed.",
            )
            return
        # Emit signal so the module shell can switch to the wizard with this record
        self.resume_draft_requested.emit(rec)

    def _delete_da(self):
        da_id = self._selected_da_id()
        if not da_id:
            return
        if not confirm_action(
            self, "Delete DA",
            f"Are you sure you want to permanently delete DA {da_id}?\nThis action cannot be undone.",
        ):
            return

        username = getattr(self.app_state, "username", "")
        data_manager.delete_da(da_id)
        audit.log_event(
            module_name="da_generator",
            event_type="delete",
            username=username,
            details=f"Deleted DA record {da_id}",
            table_name="da_records",
            record_id=da_id,
            action="delete",
        )
        self._load_data()

    def _export_pdf(self):
        da_id = self._selected_da_id()
        if not da_id:
            return
        rec = data_manager.get_da(da_id)
        if not rec:
            QMessageBox.warning(self, "Not Found", f"DA {da_id} not found.")
            return

        employee = rec.get("employee_name", "Unknown")
        default_name = f"DA_{da_id}_{employee.replace(' ', '_')}.pdf"

        path = save_pdf_dialog(self, default_name)
        if not path:
            return

        try:
            import os
            filename = os.path.basename(path)
            pdf = PDFDocument(filename=filename, title=f"Disciplinary Action \u2014 {da_id}")

            # Point the printer at the user-chosen path
            pdf.printer.setOutputFileName(path)
            pdf.begin()

            # KPI row
            discipline = DISCIPLINE_LABELS.get(
                rec.get("discipline_level", ""), rec.get("discipline_level", ""))
            pdf.add_kpi_row([
                ("Employee", employee, COLORS["info"]),
                ("Site", rec.get("site", ""), COLORS["primary"]),
                ("Discipline", discipline, COLORS["danger"]),
                ("Status", rec.get("status", ""), COLORS["success"]),
            ])
            pdf.add_spacing(8)

            # Employee info
            pdf.add_section_title("Employee Information")
            pdf.add_text(f"Name: {employee}")
            pdf.add_text(f"Position: {rec.get('employee_position', '')}")
            pdf.add_text(f"Officer ID: {rec.get('employee_officer_id', '')}")
            pdf.add_text(f"Site: {rec.get('site', '')}")
            pdf.add_text(f"Security Director: {rec.get('security_director', '')}")
            pdf.add_spacing(6)

            # Incident details
            pdf.add_section_title("Incident Details")
            pdf.add_text(f"Date(s): {rec.get('incident_dates', '')}")
            pdf.add_text(f"Violation Type: {rec.get('violation_type', '')}")
            pdf.add_spacing(4)
            narrative = rec.get("incident_narrative", "")
            if narrative:
                for line in narrative.split("\n"):
                    pdf.add_text(line.strip(), size=9)
            pdf.add_spacing(6)

            # CEIS output
            pdf.add_section_title("CEIS Engine Analysis")
            ceis_sections = [
                ("Narrative", rec.get("ceis_narrative", "")),
                ("Citations", rec.get("ceis_citations", "")),
                ("Violation Analysis", rec.get("ceis_violation_analysis", "")),
                ("Discipline Determination", rec.get("ceis_discipline_determination", "")),
                ("Risk Assessment", rec.get("ceis_risk_assessment", "")),
                ("Recommendation", rec.get("ceis_recommendation", "")),
            ]
            for section_title, content in ceis_sections:
                if content:
                    pdf.add_text(f"{section_title}:", bold=True, size=10)
                    for line in content.split("\n"):
                        pdf.add_text(line.strip(), size=9)
                    pdf.add_spacing(4)

            # Final output
            pdf.add_section_title("Final DA Document")
            if rec.get("final_narrative"):
                pdf.add_text("Narrative:", bold=True, size=10)
                for line in rec["final_narrative"].split("\n"):
                    pdf.add_text(line.strip(), size=9)
                pdf.add_spacing(4)
            if rec.get("final_citations"):
                pdf.add_text("Citations:", bold=True, size=10)
                pdf.add_text(rec["final_citations"], size=9)
            if rec.get("required_improvements"):
                pdf.add_text("Required Improvements:", bold=True, size=10)
                pdf.add_text(rec["required_improvements"], size=9)
            if rec.get("additional_comments"):
                pdf.add_text("Additional Comments:", bold=True, size=10)
                pdf.add_text(rec["additional_comments"], size=9)

            filepath = pdf.finish()

            QMessageBox.information(self, "PDF Exported", f"PDF saved to:\n{filepath}")

            # Audit
            username = getattr(self.app_state, "username", "")
            audit.log_event(
                module_name="da_generator",
                event_type="export",
                username=username,
                details=f"Exported DA {da_id} to PDF",
                table_name="da_records",
                record_id=da_id,
                action="export_pdf",
            )

        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not generate PDF:\n{exc}")

    def _export_table_csv(self):
        """Export the current DA history table view to CSV."""
        export_table_to_csv(self.table, parent=self, default_name="da_history_export.csv")

    def _send_email(self):
        """Open default email client with DA details pre-filled for the selected record."""
        da_id = self._selected_da_id()
        if not da_id:
            return
        rec = data_manager.get_da(da_id)
        if not rec:
            QMessageBox.warning(self, "Not Found", f"DA {da_id} not found.")
            return

        employee = rec.get("employee_name", "Unknown")
        discipline_raw = rec.get("discipline_level", "")
        discipline = DISCIPLINE_LABELS.get(discipline_raw, discipline_raw.replace("_", " ").title() if discipline_raw else "")
        site = rec.get("site", "")
        incident_dates = rec.get("incident_dates", "")
        pdf_filename = rec.get("pdf_filename", "")

        subject = f"Disciplinary Action - {employee} - {discipline}"
        body = (
            f"Please find the attached Disciplinary Action document for {employee}.\n\n"
            f"Discipline Level: {discipline}\n"
            f"Date: {incident_dates}\n"
            f"Site: {site}\n\n"
            f"This document requires review and signature."
        )

        mailto_url = f"mailto:?subject={quote(subject)}&body={quote(body)}"
        QDesktopServices.openUrl(QUrl(mailto_url))

        # Build PDF path hint and copy to clipboard if available
        import os
        pdf_path = ""
        if pdf_filename:
            pdf_path = os.path.join(REPORTS_DIR, pdf_filename)

        clipboard = QApplication.clipboard()
        if clipboard and pdf_path:
            clipboard.setText(pdf_path)

        if pdf_path:
            QMessageBox.information(
                self, "Email Client Opened",
                f"Email client opened. Please attach the PDF file from:\n\n"
                f"{pdf_path}\n\n"
                f"The file path has been copied to your clipboard.",
            )
        else:
            QMessageBox.information(
                self, "Email Client Opened",
                "Email client opened with DA details pre-filled.\n\n"
                "No PDF file was found on record. You may need to export the PDF first.",
            )

    def _acknowledge_da(self):
        """Open the Acknowledge dialog for the selected DA."""
        da_id = self._selected_da_id()
        if not da_id:
            return
        rec = data_manager.get_da(da_id)
        if not rec:
            QMessageBox.warning(self, "Not Found", f"DA {da_id} not found.")
            return

        status = rec.get("status", "")
        if status not in ("delivered", "signed"):
            QMessageBox.information(
                self, "Cannot Acknowledge",
                "Only DAs with status 'Delivered' or 'Signed' can be acknowledged.",
            )
            return

        if rec.get("acknowledged", 0):
            QMessageBox.information(
                self, "Already Acknowledged",
                f"DA {da_id} has already been acknowledged.",
            )
            return

        # -- Build the Acknowledge dialog --
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Acknowledge DA \u2014 {da_id}")
        dlg.setMinimumWidth(460)
        dlg.setStyleSheet(build_dialog_stylesheet(_is_dark()))

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Title
        title_lbl = QLabel(f"Acknowledge DA for {rec.get('employee_name', '')}")
        title_lbl.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {tc('text')}; background: transparent; border: none;")
        layout.addWidget(title_lbl)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Employee Response dropdown
        response_lbl = QLabel("Employee Response:")
        response_lbl.setStyleSheet(f"color: {tc('text_light')}; font-weight: 600; font-size: 13px; background: transparent; border: none;")
        response_combo = QComboBox()
        response_combo.addItems(["Acknowledged", "Acknowledged Under Protest", "Refused to Sign"])
        form.addRow(response_lbl, response_combo)

        # Witness Name
        witness_lbl = QLabel("Witness Name:")
        witness_lbl.setStyleSheet(f"color: {tc('text_light')}; font-weight: 600; font-size: 13px; background: transparent; border: none;")
        witness_input = QLineEdit()
        witness_input.setPlaceholderText("Enter witness name (optional)")
        form.addRow(witness_lbl, witness_input)

        # Notes/comments
        notes_lbl = QLabel("Notes / Comments:")
        notes_lbl.setStyleSheet(f"color: {tc('text_light')}; font-weight: 600; font-size: 13px; background: transparent; border: none;")
        notes_input = QTextEdit()
        notes_input.setPlaceholderText("Optional notes or comments...")
        notes_input.setMaximumHeight(100)
        form.addRow(notes_lbl, notes_input)

        layout.addLayout(form)

        # Save / Cancel buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(btn_style(COLORS["border"], fg=tc("text")))
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Save Acknowledgment")
        btn_save.setStyleSheet(btn_style(COLORS["success"]))
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

        def _on_save():
            employee_response = response_combo.currentText()
            witness_name = witness_input.text().strip()
            username = getattr(self.app_state, "username", "")

            ok = data_manager.acknowledge_da(da_id, acknowledged_by=username, employee_response=employee_response)
            if not ok:
                QMessageBox.warning(dlg, "Error", "Failed to save acknowledgment.")
                return

            # Record witness if provided
            if witness_name:
                data_manager.witness_sign_da(da_id, witness_name)

            audit.log_event(
                module_name="da_generator",
                event_type="acknowledge",
                username=username,
                details=f"Acknowledged DA {da_id} - Response: {employee_response}"
                        + (f", Witness: {witness_name}" if witness_name else ""),
                table_name="da_records",
                record_id=da_id,
                action="acknowledge",
            )

            dlg.accept()
            self._load_data()

        btn_save.clicked.connect(_on_save)
        dlg.exec()
