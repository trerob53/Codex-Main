"""
Cerasus Hub -- Attendance Module: Bulk Infraction Import Page
Paste or browse CSV with employee_name, infraction_date, infraction_type, site, notes.
Fuzzy-match officers, map infraction types, preview, then bulk-import.
"""

import csv
import io
from difflib import SequenceMatcher

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QScrollArea, QMessageBox, QFileDialog,
    QTextEdit, QComboBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, tc, btn_style, _is_dark
from src.modules.attendance import data_manager
from src.modules.attendance.policy_engine import INFRACTION_TYPES
from src.shared_data import get_all_officers
from src import audit


# ── Constants ────────────────────────────────────────────────────────

EXPECTED_HEADERS = ["employee_name", "infraction_date", "infraction_type", "site", "notes"]

STATUS_READY = "Ready"
STATUS_WARNING = "Warning"
STATUS_ERROR = "Error"

# Row background colors for validation states
_ROW_BG_ERROR = "#FEE2E2"       # light red
_ROW_BG_WARNING = "#FEF3C7"     # light yellow
_ROW_BG_ERROR_DARK = "#451A1A"
_ROW_BG_WARNING_DARK = "#422D08"

# Convenience alias map: common free-text values -> INFRACTION_TYPES keys
_TYPE_ALIASES = {
    "tardiness": "tardiness_additional",
    "late": "tardiness_additional",
    "ncns": "ncns_1st",
    "no call no show": "ncns_1st",
    "no-call": "ncns_1st",
    "call off": "calloff_proper_notice_additional",
    "call-off": "calloff_proper_notice_additional",
    "calloff": "calloff_proper_notice_additional",
    "abandonment": "post_abandonment",
    "post abandonment": "post_abandonment",
}


# ── Matching helpers ─────────────────────────────────────────────────

def _fuzzy_match_officer(csv_name: str, officers: list):
    """Match csv employee_name to an officer.

    Returns (officer_id, display_name, exact_match_bool).
    If no match at all: (None, None, False).
    """
    name_lower = csv_name.strip().lower()
    if not name_lower:
        return None, None, False

    # Exact name match (case-insensitive)
    for off in officers:
        if off.get("name", "").strip().lower() == name_lower:
            return off.get("officer_id", ""), off.get("name", ""), True

    # Partial / contains match
    for off in officers:
        off_name = off.get("name", "").strip().lower()
        if name_lower in off_name or off_name in name_lower:
            return off.get("officer_id", ""), off.get("name", ""), False

    # Fuzzy match (SequenceMatcher >= 0.7)
    best_score = 0.0
    best_officer = None
    for off in officers:
        off_name = off.get("name", "").strip().lower()
        score = SequenceMatcher(None, name_lower, off_name).ratio()
        if score > best_score:
            best_score = score
            best_officer = off
    if best_score >= 0.7 and best_officer:
        return best_officer.get("officer_id", ""), best_officer.get("name", ""), False

    return None, None, False


def _map_infraction_type(csv_type: str):
    """Map a CSV infraction type string to (key, label) or (None, None).

    Checks: exact key match, label match (case-insensitive), alias map.
    """
    raw = csv_type.strip()
    raw_lower = raw.lower()

    # Exact key match
    if raw in INFRACTION_TYPES:
        return raw, INFRACTION_TYPES[raw]["label"]
    if raw_lower in INFRACTION_TYPES:
        return raw_lower, INFRACTION_TYPES[raw_lower]["label"]

    # Label match (case-insensitive)
    for key, info in INFRACTION_TYPES.items():
        if info["label"].lower() == raw_lower:
            return key, info["label"]

    # Alias map
    if raw_lower in _TYPE_ALIASES:
        key = _TYPE_ALIASES[raw_lower]
        return key, INFRACTION_TYPES[key]["label"]

    return None, None


# ── Page widget ──────────────────────────────────────────────────────

class BulkImportPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._rows = []       # parsed row dicts
        self._officers = []   # cached officer list
        self._officer_combos = {}  # row_index -> QComboBox for unmatched rows
        self._build()

    # ── Build UI ─────────────────────────────────────────────────────

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # ── Header
        title = QLabel("Bulk Infraction Import")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        subtitle = QLabel(
            "Paste CSV data or browse a file. Expected columns: "
            "employee_name, infraction_date, infraction_type, site, notes"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        layout.addWidget(subtitle)

        # ── Card 1: CSV Input
        input_card = self._card()
        input_lay = QVBoxLayout(input_card)
        input_lay.setContentsMargins(24, 16, 24, 16)
        input_lay.setSpacing(10)

        input_title = QLabel("CSV Data")
        input_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        input_title.setStyleSheet(f"color: {tc('text')};")
        input_lay.addWidget(input_title)

        hint = QLabel("Paste CSV text below (with header row), or use Browse to load a file.")
        hint.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
        input_lay.addWidget(hint)

        self.text_area = QTextEdit()
        self.text_area.setPlaceholderText(
            "employee_name,infraction_date,infraction_type,site,notes\n"
            "John Doe,2025-06-15,tardiness,Main Campus,Late 10 min"
        )
        self.text_area.setMinimumHeight(140)
        self.text_area.setMaximumHeight(220)
        self.text_area.setStyleSheet(f"""
            QTextEdit {{
                background: {tc('bg')}; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 6px;
                padding: 8px; font-family: Consolas, monospace; font-size: 12px;
            }}
        """)
        input_lay.addWidget(self.text_area)

        btn_row = QHBoxLayout()
        self.btn_browse = QPushButton("Browse CSV File")
        self.btn_browse.setStyleSheet(btn_style(COLORS['info']))
        self.btn_browse.setFixedHeight(40)
        self.btn_browse.clicked.connect(self._browse_file)
        btn_row.addWidget(self.btn_browse)

        self.btn_parse = QPushButton("Parse")
        self.btn_parse.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        self.btn_parse.setFixedHeight(40)
        self.btn_parse.setFixedWidth(140)
        self.btn_parse.clicked.connect(self._parse)
        btn_row.addWidget(self.btn_parse)

        btn_row.addStretch()
        input_lay.addLayout(btn_row)
        layout.addWidget(input_card)

        # ── Card 2: Preview Table
        preview_card = self._card()
        preview_lay = QVBoxLayout(preview_card)
        preview_lay.setContentsMargins(24, 16, 24, 16)
        preview_lay.setSpacing(10)

        preview_title = QLabel("Preview")
        preview_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        preview_title.setStyleSheet(f"color: {tc('text')};")
        preview_lay.addWidget(preview_title)

        self.lbl_summary = QLabel("No data parsed yet.")
        self.lbl_summary.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        preview_lay.addWidget(self.lbl_summary)

        self.preview_table = QTableWidget(0, 7)
        self.preview_table.setHorizontalHeaderLabels([
            "Employee Name", "Matched Officer", "Date",
            "Type", "Site", "Notes", "Status",
        ])
        hdr = self.preview_table.horizontalHeader()
        for c in range(7):
            if c in (0, 1, 5):
                hdr.setSectionResizeMode(c, QHeaderView.Stretch)
            else:
                hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 13px; padding: 8px 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setShowGrid(False)
        self.preview_table.setMinimumHeight(280)
        preview_lay.addWidget(self.preview_table)

        layout.addWidget(preview_card)

        # ── Card 3: Import Actions
        import_card = self._card()
        import_lay = QVBoxLayout(import_card)
        import_lay.setContentsMargins(24, 16, 24, 16)
        import_lay.setSpacing(10)

        import_title = QLabel("Confirm Import")
        import_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        import_title.setStyleSheet(f"color: {tc('text')};")
        import_lay.addWidget(import_title)

        # Validation summary panel
        self.validation_frame = QFrame()
        self.validation_frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('bg')}; border: 1px solid {tc('border')};
                border-radius: 6px; padding: 8px;
            }}
        """)
        val_lay = QVBoxLayout(self.validation_frame)
        val_lay.setContentsMargins(12, 8, 12, 8)
        val_lay.setSpacing(4)
        self.lbl_val_ready = QLabel("Ready: 0")
        self.lbl_val_ready.setStyleSheet(f"color: {COLORS['success']}; font-size: 13px; font-weight: 600;")
        val_lay.addWidget(self.lbl_val_ready)
        self.lbl_val_warnings = QLabel("Warnings: 0")
        self.lbl_val_warnings.setStyleSheet(f"color: {COLORS['warning']}; font-size: 13px; font-weight: 600;")
        val_lay.addWidget(self.lbl_val_warnings)
        self.lbl_val_errors = QLabel("Errors: 0 (will be skipped)")
        self.lbl_val_errors.setStyleSheet(f"color: {COLORS['danger']}; font-size: 13px; font-weight: 600;")
        val_lay.addWidget(self.lbl_val_errors)
        self.lbl_val_total = QLabel("Total rows: 0")
        self.lbl_val_total.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
        val_lay.addWidget(self.lbl_val_total)
        import_lay.addWidget(self.validation_frame)

        action_row = QHBoxLayout()
        self.btn_import = QPushButton("Confirm Import (0)")
        self.btn_import.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        self.btn_import.setFixedHeight(44)
        self.btn_import.setFixedWidth(260)
        self.btn_import.clicked.connect(self._do_import)
        self.btn_import.setEnabled(False)
        action_row.addWidget(self.btn_import)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setStyleSheet(btn_style(tc('border'), fg=tc('text')))
        self.btn_clear.setFixedHeight(44)
        self.btn_clear.setFixedWidth(100)
        self.btn_clear.clicked.connect(self._clear)
        action_row.addWidget(self.btn_clear)

        action_row.addStretch()
        import_lay.addLayout(action_row)

        self.lbl_result = QLabel("")
        self.lbl_result.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        import_lay.addWidget(self.lbl_result)

        layout.addWidget(import_card)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Helper: card frame ────────────────────────────────────────────

    def _card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 8px;
            }}
        """)
        return card

    # ── Refresh (called when page becomes visible) ────────────────────

    def refresh(self):
        self._officers = get_all_officers()

    # ── Browse file ───────────────────────────────────────────────────

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                self.text_area.setPlainText(f.read())
        except Exception as exc:
            QMessageBox.critical(self, "File Error", f"Could not read file:\n{exc}")

    # ── Parse ─────────────────────────────────────────────────────────

    def _parse(self):
        csv_text = self.text_area.toPlainText().strip()
        if not csv_text:
            QMessageBox.information(self, "Parse", "No CSV data to parse. Paste data or browse a file first.")
            return

        self._rows.clear()
        self._officer_combos.clear()
        self._officers = get_all_officers()

        reader = csv.DictReader(io.StringIO(csv_text))

        # First pass: collect all rows
        raw_rows = []
        for i, row in enumerate(reader, start=2):
            csv_name = row.get("employee_name", "").strip()
            csv_date = row.get("infraction_date", "").strip()
            csv_type = row.get("infraction_type", "").strip()
            csv_site = row.get("site", "").strip()
            csv_notes = row.get("notes", "").strip()

            # Match officer
            matched_id, matched_name, exact = _fuzzy_match_officer(csv_name, self._officers)

            # Map infraction type
            mapped_key, mapped_label = _map_infraction_type(csv_type)

            raw_rows.append({
                "row_num": i,
                "csv_name": csv_name,
                "csv_date": csv_date,
                "csv_type": csv_type,
                "csv_site": csv_site,
                "csv_notes": csv_notes,
                "matched_id": matched_id,
                "matched_name": matched_name or "",
                "exact_match": exact,
                "mapped_key": mapped_key,
                "mapped_label": mapped_label or "",
            })

        # Build a set of (officer_id, date) pairs to detect duplicates within the CSV
        seen_pairs = {}  # (officer_id, date) -> row_num
        # Also check existing infractions in DB for duplicate dates
        existing_dates = {}  # officer_id -> set of dates
        for row in raw_rows:
            oid = row["matched_id"]
            if oid and oid not in existing_dates:
                existing_inf = data_manager.get_infractions_for_employee(oid)
                existing_dates[oid] = {inf.get("infraction_date", "") for inf in existing_inf}

        # Second pass: validate with duplicate detection
        for row in raw_rows:
            errors = []
            warnings = []

            if not row["csv_name"]:
                errors.append("missing employee_name")
            elif not row["matched_id"]:
                errors.append("officer not found")

            if row["matched_id"] and not row["exact_match"]:
                warnings.append("fuzzy match")

            if not row["csv_date"]:
                errors.append("missing date")
            else:
                # Check for duplicate date within CSV
                pair_key = (row["matched_id"], row["csv_date"])
                if row["matched_id"] and pair_key in seen_pairs:
                    warnings.append(f"duplicate date (same as row {seen_pairs[pair_key]})")
                elif row["matched_id"]:
                    seen_pairs[pair_key] = row["row_num"]

                # Check for duplicate date in existing DB records
                if row["matched_id"] and row["csv_date"] in existing_dates.get(row["matched_id"], set()):
                    warnings.append("date exists in DB")

            if not row["csv_type"]:
                errors.append("missing type")
            elif not row["mapped_key"]:
                errors.append("unknown infraction type")

            if errors:
                status = STATUS_ERROR
            elif warnings:
                status = STATUS_WARNING
            else:
                status = STATUS_READY

            row["status"] = status
            row["status_detail"] = "; ".join(errors or warnings)
            self._rows.append(row)

        self._update_table()

    # ── Table display ─────────────────────────────────────────────────

    def _update_table(self):
        self._officer_combos.clear()
        self.preview_table.setRowCount(len(self._rows))

        for i, row in enumerate(self._rows):
            # Col 0: Employee Name (from CSV)
            self.preview_table.setItem(i, 0, QTableWidgetItem(row["csv_name"]))

            # Col 1: Matched Officer — if warning/no-exact, use combo; otherwise label
            if row["matched_id"] and row["exact_match"]:
                self.preview_table.setItem(i, 1, QTableWidgetItem(row["matched_name"]))
            elif row["status"] == STATUS_ERROR and not row["matched_id"]:
                item = QTableWidgetItem("-- not found --")
                item.setForeground(QColor(COLORS["danger"]))
                self.preview_table.setItem(i, 1, item)

                # Put a combo in column 1 so user can manually pick
                combo = self._make_officer_combo(row["matched_id"])
                self._officer_combos[i] = combo
                self.preview_table.setCellWidget(i, 1, combo)
            else:
                # Fuzzy / partial match — show combo pre-selected
                combo = self._make_officer_combo(row["matched_id"])
                self._officer_combos[i] = combo
                self.preview_table.setCellWidget(i, 1, combo)

            # Col 2: Date
            self.preview_table.setItem(i, 2, QTableWidgetItem(row["csv_date"]))

            # Col 3: Type (mapped label or raw)
            type_text = row["mapped_label"] if row["mapped_label"] else row["csv_type"]
            type_item = QTableWidgetItem(type_text)
            if not row["mapped_key"]:
                type_item.setForeground(QColor(COLORS["danger"]))
            self.preview_table.setItem(i, 3, type_item)

            # Col 4: Site
            self.preview_table.setItem(i, 4, QTableWidgetItem(row["csv_site"]))

            # Col 5: Notes
            self.preview_table.setItem(i, 5, QTableWidgetItem(row["csv_notes"]))

            # Col 6: Status
            status_text = row["status"]
            if row["status"] != STATUS_READY and row["status_detail"]:
                status_text = f"{row['status']} ({row['status_detail']})"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setFont(QFont("Segoe UI", 11, QFont.Bold))
            if row["status"] == STATUS_READY:
                status_item.setForeground(QColor(COLORS["success"]))
            elif row["status"] == STATUS_WARNING:
                status_item.setForeground(QColor(COLORS["warning"]))
            else:
                status_item.setForeground(QColor(COLORS["danger"]))
            self.preview_table.setItem(i, 6, status_item)

            # Apply row background color based on status
            dark = _is_dark()
            if row["status"] == STATUS_ERROR:
                bg_color = QColor(_ROW_BG_ERROR_DARK if dark else _ROW_BG_ERROR)
                for col in range(7):
                    item = self.preview_table.item(i, col)
                    if item:
                        item.setBackground(bg_color)
            elif row["status"] == STATUS_WARNING:
                bg_color = QColor(_ROW_BG_WARNING_DARK if dark else _ROW_BG_WARNING)
                for col in range(7):
                    item = self.preview_table.item(i, col)
                    if item:
                        item.setBackground(bg_color)

            self.preview_table.setRowHeight(i, 40)

        # Summary counts
        ready_count = sum(1 for r in self._rows if r["status"] == STATUS_READY)
        warning_count = sum(1 for r in self._rows if r["status"] == STATUS_WARNING)
        error_count = sum(1 for r in self._rows if r["status"] == STATUS_ERROR)
        total = len(self._rows)
        valid_count = ready_count + warning_count  # ready + warning rows are importable

        self.lbl_summary.setText(
            f"Ready: {ready_count}  |  Warnings: {warning_count}  |  "
            f"Errors: {error_count}  |  Total: {total}"
        )

        # Update validation summary panel
        self.lbl_val_ready.setText(f"Ready: {ready_count}")
        self.lbl_val_warnings.setText(f"Warnings: {warning_count} (will import with caution)")
        self.lbl_val_errors.setText(f"Errors: {error_count} (will be skipped)")
        self.lbl_val_total.setText(f"Total rows: {total}  |  Will import: {valid_count}")

        # Update import button
        self.btn_import.setText(f"Confirm Import ({valid_count})")
        self.btn_import.setEnabled(valid_count > 0)

    def _make_officer_combo(self, preselect_id: str | None) -> QComboBox:
        combo = QComboBox()
        combo.addItem("-- select officer --", "")
        selected_idx = 0
        for idx, off in enumerate(self._officers, start=1):
            oid = off.get("officer_id", "")
            name = off.get("name", "")
            combo.addItem(name, oid)
            if preselect_id and oid == preselect_id:
                selected_idx = idx
        combo.setCurrentIndex(selected_idx)
        combo.setStyleSheet(f"""
            QComboBox {{
                background: {tc('bg')}; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 4px;
                padding: 2px 6px; font-size: 12px;
            }}
        """)
        combo.currentIndexChanged.connect(self._on_combo_changed)
        return combo

    def _on_combo_changed(self):
        """Re-evaluate row statuses after the user manually picks an officer."""
        for row_idx, combo in self._officer_combos.items():
            oid = combo.currentData()
            name = combo.currentText() if oid else ""
            row = self._rows[row_idx]
            row["matched_id"] = oid or None
            row["matched_name"] = name if oid else ""
            row["exact_match"] = bool(oid)

            # Re-evaluate status
            errors = []
            if not row["csv_name"] and not oid:
                errors.append("missing employee_name")
            elif not oid:
                errors.append("officer not found")
            if not row["csv_date"]:
                errors.append("missing date")
            if not row["csv_type"]:
                errors.append("missing type")
            elif not row["mapped_key"]:
                errors.append("unknown infraction type")

            if errors:
                row["status"] = STATUS_ERROR
                row["status_detail"] = "; ".join(errors)
            else:
                row["status"] = STATUS_READY
                row["status_detail"] = ""

            # Update status cell
            status_text = row["status"]
            if row["status"] != STATUS_READY and row["status_detail"]:
                status_text = f"{row['status']} ({row['status_detail']})"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setFont(QFont("Segoe UI", 11, QFont.Bold))
            if row["status"] == STATUS_READY:
                status_item.setForeground(QColor(COLORS["success"]))
            elif row["status"] == STATUS_WARNING:
                status_item.setForeground(QColor(COLORS["warning"]))
            else:
                status_item.setForeground(QColor(COLORS["danger"]))
            self.preview_table.setItem(row_idx, 6, status_item)

        # Update summary
        ready_count = sum(1 for r in self._rows if r["status"] == STATUS_READY)
        warning_count = sum(1 for r in self._rows if r["status"] == STATUS_WARNING)
        error_count = sum(1 for r in self._rows if r["status"] == STATUS_ERROR)
        total = len(self._rows)
        valid_count = ready_count + warning_count
        self.lbl_summary.setText(
            f"Ready: {ready_count}  |  Warnings: {warning_count}  |  "
            f"Errors: {error_count}  |  Total: {total}"
        )
        self.lbl_val_ready.setText(f"Ready: {ready_count}")
        self.lbl_val_warnings.setText(f"Warnings: {warning_count} (will import with caution)")
        self.lbl_val_errors.setText(f"Errors: {error_count} (will be skipped)")
        self.lbl_val_total.setText(f"Total rows: {total}  |  Will import: {valid_count}")
        self.btn_import.setText(f"Confirm Import ({valid_count})")
        self.btn_import.setEnabled(valid_count > 0)

    # ── Import ────────────────────────────────────────────────────────

    def _do_import(self):
        importable = [r for r in self._rows if r["status"] in (STATUS_READY, STATUS_WARNING)]

        # Resolve officer IDs from combos for warning rows
        for idx, row in enumerate(self._rows):
            if idx in self._officer_combos:
                combo = self._officer_combos[idx]
                oid = combo.currentData()
                if oid:
                    row["matched_id"] = oid
                    row["matched_name"] = combo.currentText()

        importable = [r for r in self._rows if r["status"] in (STATUS_READY, STATUS_WARNING) and r["matched_id"] and r["mapped_key"]]

        if not importable:
            QMessageBox.information(self, "Import", "No valid rows to import.")
            return

        reply = QMessageBox.question(
            self, "Confirm Bulk Import",
            f"Import {len(importable)} infraction(s)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        username = self.app_state.get("username", "")
        imported = 0
        skipped = 0
        errors = []

        for row in importable:
            try:
                fields = {
                    "employee_id": row["matched_id"],
                    "infraction_type": row["mapped_key"],
                    "infraction_date": row["csv_date"],
                    "description": row["csv_notes"],
                    "site": row["csv_site"],
                }
                infraction_id = data_manager.create_infraction(fields, entered_by=username)

                audit.log_event(
                    "attendance", "infraction_bulk_imported", username,
                    details=(
                        f"Bulk import: {row['mapped_label']} for "
                        f"{row['matched_name']} (row {row['row_num']})"
                    ),
                    table_name="ats_infractions",
                    record_id=str(infraction_id),
                    action="create",
                    employee_id=row["matched_id"],
                )
                imported += 1
                row["status"] = "Imported"
            except Exception as exc:
                errors.append(f"Row {row['row_num']}: {exc}")

        skipped = len(self._rows) - imported - len(errors)

        result_text = f"Imported: {imported}  |  Skipped: {skipped}  |  Errors: {len(errors)}"
        self.lbl_result.setText(result_text)
        self.lbl_result.setStyleSheet(
            f"color: {COLORS['success']}; font-size: 13px; font-weight: 600;"
        )

        if errors:
            QMessageBox.warning(
                self, "Import Warnings",
                f"Imported {imported} with {len(errors)} error(s):\n" + "\n".join(errors[:10]),
            )
        else:
            QMessageBox.information(
                self, "Import Complete",
                f"Successfully imported {imported} infraction(s).\n"
                f"Skipped: {skipped}  |  Errors: {len(errors)}",
            )

        # Remove imported rows from preview, keep errors/skipped
        self._rows = [r for r in self._rows if r["status"] != "Imported"]
        self._update_table()

    # ── Clear ─────────────────────────────────────────────────────────

    def _clear(self):
        self._rows.clear()
        self._officer_combos.clear()
        self.text_area.clear()
        self.preview_table.setRowCount(0)
        self.lbl_summary.setText("No data parsed yet.")
        self.lbl_result.setText("")
        self.lbl_result.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        self.btn_import.setText("Confirm Import (0)")
        self.btn_import.setEnabled(False)
        self.lbl_val_ready.setText("Ready: 0")
        self.lbl_val_warnings.setText("Warnings: 0")
        self.lbl_val_errors.setText("Errors: 0 (will be skipped)")
        self.lbl_val_total.setText("Total rows: 0")
