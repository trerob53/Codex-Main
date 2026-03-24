"""
Cerasus Hub -- Attendance Module: Import Infractions Page
CSV import with preview diagnostics, fuzzy officer matching, and infraction type mapping.
"""

import csv
import io
import os
from difflib import SequenceMatcher

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QScrollArea, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, REPORTS_DIR, ensure_directories, tc, _is_dark, btn_style
from src.modules.attendance import data_manager
from src.modules.attendance.policy_engine import INFRACTION_TYPES
from src import audit


# ── Infraction type mapping rules ────────────────────────────────────

_TYPE_MAP = {
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

TEMPLATE_HEADERS = ["employee_id", "employee_name", "infraction_date", "infraction_type", "site", "notes"]


# ── Row status constants ─────────────────────────────────────────────

STATUS_READY = "Ready"
STATUS_UNMATCHED = "Unmatched"
STATUS_ERROR = "Error"


def _fuzzy_match_officer(csv_name, csv_eid, officers):
    """Try to match a CSV row to an officer. Returns (officer_id, display_name) or (None, None)."""
    csv_name_lower = csv_name.strip().lower()
    csv_eid_stripped = csv_eid.strip()

    # Exact employee_id match first
    if csv_eid_stripped:
        for off in officers:
            if off.get("employee_id", "").strip() == csv_eid_stripped:
                return off.get("officer_id", ""), off.get("name", "")

    # Exact name match
    for off in officers:
        if off.get("name", "").strip().lower() == csv_name_lower:
            return off.get("officer_id", ""), off.get("name", "")

    # Fuzzy name match (threshold 0.8)
    if csv_name_lower:
        best_score = 0.0
        best_officer = None
        for off in officers:
            off_name = off.get("name", "").strip().lower()
            score = SequenceMatcher(None, csv_name_lower, off_name).ratio()
            if score > best_score:
                best_score = score
                best_officer = off
        if best_score >= 0.8 and best_officer:
            return best_officer.get("officer_id", ""), best_officer.get("name", "")

    return None, None


def _map_infraction_type(csv_type):
    """Map a CSV infraction type string to a policy engine key. Returns (key, label) or (None, None)."""
    raw = csv_type.strip()
    raw_lower = raw.lower()

    # Exact match to INFRACTION_TYPES key
    if raw in INFRACTION_TYPES:
        return raw, INFRACTION_TYPES[raw]["label"]
    if raw_lower in INFRACTION_TYPES:
        return raw_lower, INFRACTION_TYPES[raw_lower]["label"]

    # Mapping rules
    if raw_lower in _TYPE_MAP:
        key = _TYPE_MAP[raw_lower]
        return key, INFRACTION_TYPES[key]["label"]

    return None, None


class ImportInfractionsPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._rows = []        # list of dicts with parsed + matched data
        self._filter = "all"   # all | ready | unmatched | errors
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

        # ── Header
        title = QLabel("Import Attendance Data")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        subtitle = QLabel("Import infractions from a CSV file with preview and diagnostics.")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        layout.addWidget(subtitle)

        # ── Step 1: File Selection card
        step1_card = QFrame()
        step1_card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 8px;
            }}
        """)
        step1_lay = QVBoxLayout(step1_card)
        step1_lay.setContentsMargins(24, 16, 24, 16)
        step1_lay.setSpacing(10)

        step1_title = QLabel("Step 1: Select CSV File")
        step1_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        step1_title.setStyleSheet(f"color: {tc('text')};")
        step1_lay.addWidget(step1_title)

        file_row = QHBoxLayout()
        self.btn_select = QPushButton("Select CSV File")
        self.btn_select.setStyleSheet(btn_style(COLORS['info']))
        self.btn_select.setFixedHeight(40)
        self.btn_select.clicked.connect(self._select_file)
        file_row.addWidget(self.btn_select)

        self.lbl_filepath = QLabel("No file selected")
        self.lbl_filepath.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        file_row.addWidget(self.lbl_filepath, 1)

        self.btn_template = QPushButton("Download Template")
        self.btn_template.setStyleSheet(btn_style(COLORS['primary_light']))
        self.btn_template.setFixedHeight(40)
        self.btn_template.clicked.connect(self._download_template)
        file_row.addWidget(self.btn_template)

        step1_lay.addLayout(file_row)
        layout.addWidget(step1_card)

        # ── Step 2: Preview & Diagnostics card
        step2_card = QFrame()
        step2_card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 8px;
            }}
        """)
        step2_lay = QVBoxLayout(step2_card)
        step2_lay.setContentsMargins(24, 16, 24, 16)
        step2_lay.setSpacing(10)

        step2_title = QLabel("Step 2: Preview & Diagnostics")
        step2_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        step2_title.setStyleSheet(f"color: {tc('text')};")
        step2_lay.addWidget(step2_title)

        # Filter buttons row
        filter_row = QHBoxLayout()
        self._filter_btns = {}
        for key, label in [("all", "All Rows"), ("ready", "Ready"), ("unmatched", "Unmatched"), ("errors", "Errors")]:
            btn = QPushButton(label)
            btn.setFixedHeight(34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._set_filter(k))
            self._filter_btns[key] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch()
        step2_lay.addLayout(filter_row)
        self._update_filter_styles()

        # Summary counts
        self.lbl_summary = QLabel("Ready: 0  |  Unmatched: 0  |  Errors: 0  |  Total: 0")
        self.lbl_summary.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        step2_lay.addWidget(self.lbl_summary)

        # Preview table
        self.preview_table = QTableWidget(0, 9)
        self.preview_table.setHorizontalHeaderLabels([
            "Row#", "Date", "Employee (CSV)", "Matched Officer",
            "Site", "Infraction Type (CSV)", "Mapped Type", "Points", "Status",
        ])
        hdr = self.preview_table.horizontalHeader()
        for c in range(9):
            if c in (2, 3, 5, 6):
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
        self.preview_table.setMinimumHeight(300)
        step2_lay.addWidget(self.preview_table)

        layout.addWidget(step2_card)

        # ── Step 3: Import card
        step3_card = QFrame()
        step3_card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 8px;
            }}
        """)
        step3_lay = QVBoxLayout(step3_card)
        step3_lay.setContentsMargins(24, 16, 24, 16)
        step3_lay.setSpacing(10)

        step3_title = QLabel("Step 3: Import")
        step3_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        step3_title.setStyleSheet(f"color: {tc('text')};")
        step3_lay.addWidget(step3_title)

        import_row = QHBoxLayout()
        self.btn_import = QPushButton("Import Ready Rows (0)")
        self.btn_import.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        self.btn_import.setFixedHeight(44)
        self.btn_import.setFixedWidth(240)
        self.btn_import.clicked.connect(self._do_import)
        import_row.addWidget(self.btn_import)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setStyleSheet(btn_style(tc('border'), fg=tc('text')))
        self.btn_clear.setFixedHeight(44)
        self.btn_clear.setFixedWidth(100)
        self.btn_clear.clicked.connect(self._clear)
        import_row.addWidget(self.btn_clear)

        import_row.addStretch()
        step3_lay.addLayout(import_row)

        self.lbl_result = QLabel("")
        self.lbl_result.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        step3_lay.addWidget(self.lbl_result)

        layout.addWidget(step3_card)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Refresh (called when page becomes visible) ───────────────────

    def refresh(self):
        pass  # Data loaded on file select

    # ── File selection ───────────────────────────────────────────────

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        self.lbl_filepath.setText(path)
        self._parse_csv(path)

    def _download_template(self):
        ensure_directories()
        default_path = os.path.join(REPORTS_DIR, "infraction_import_template.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Template CSV", default_path, "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(TEMPLATE_HEADERS)
                writer.writerow(["EMP001", "John Doe", "2025-01-15", "tardiness", "Main Campus", "Late 10 min"])
            QMessageBox.information(self, "Template Saved", f"Template saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save template:\n{exc}")

    # ── CSV Parsing & Matching ───────────────────────────────────────

    def _parse_csv(self, path):
        self._rows.clear()
        self.lbl_result.setText("")

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except Exception as exc:
            QMessageBox.critical(self, "File Error", f"Could not read file:\n{exc}")
            return

        officers = data_manager.get_all_officers()
        reader = csv.DictReader(io.StringIO(text))

        for i, row in enumerate(reader, start=2):
            csv_name = row.get("employee_name", "").strip()
            csv_eid = row.get("employee_id", "").strip()
            csv_date = row.get("infraction_date", "").strip()
            csv_type = row.get("infraction_type", "").strip()
            csv_site = row.get("site", "").strip()
            csv_notes = row.get("notes", "").strip()

            # Match officer
            matched_id, matched_name = _fuzzy_match_officer(csv_name, csv_eid, officers)

            # Map infraction type
            mapped_key, mapped_label = _map_infraction_type(csv_type)
            points = INFRACTION_TYPES[mapped_key]["points"] if mapped_key else ""

            # Determine status
            errors = []
            if not matched_id:
                errors.append("officer")
            if not mapped_key:
                errors.append("type")
            if not csv_date:
                errors.append("date")

            if not errors:
                status = STATUS_READY
            elif "date" in errors or ("officer" in errors and "type" in errors):
                status = STATUS_ERROR
            else:
                status = STATUS_UNMATCHED

            self._rows.append({
                "row_num": i,
                "csv_name": csv_name,
                "csv_eid": csv_eid,
                "csv_date": csv_date,
                "csv_type": csv_type,
                "csv_site": csv_site,
                "csv_notes": csv_notes,
                "matched_id": matched_id,
                "matched_name": matched_name or "",
                "mapped_key": mapped_key,
                "mapped_label": mapped_label or "",
                "points": points,
                "status": status,
            })

        self._update_table()

    # ── Table display ────────────────────────────────────────────────

    def _set_filter(self, key):
        self._filter = key
        self._update_filter_styles()
        self._update_table()

    def _update_filter_styles(self):
        for key, btn in self._filter_btns.items():
            if key == self._filter:
                btn.setStyleSheet(btn_style(COLORS['info']))
            else:
                btn.setStyleSheet(btn_style(tc('border'), fg=tc('text')))

    def _update_table(self):
        # Filter rows
        if self._filter == "ready":
            visible = [r for r in self._rows if r["status"] == STATUS_READY]
        elif self._filter == "unmatched":
            visible = [r for r in self._rows if r["status"] == STATUS_UNMATCHED]
        elif self._filter == "errors":
            visible = [r for r in self._rows if r["status"] == STATUS_ERROR]
        else:
            visible = self._rows

        self.preview_table.setRowCount(len(visible))

        for i, row in enumerate(visible):
            self.preview_table.setItem(i, 0, QTableWidgetItem(str(row["row_num"])))
            self.preview_table.setItem(i, 1, QTableWidgetItem(row["csv_date"]))
            self.preview_table.setItem(i, 2, QTableWidgetItem(
                f"{row['csv_name']} ({row['csv_eid']})" if row["csv_eid"] else row["csv_name"]
            ))
            self.preview_table.setItem(i, 3, QTableWidgetItem(row["matched_name"]))
            self.preview_table.setItem(i, 4, QTableWidgetItem(row["csv_site"]))
            self.preview_table.setItem(i, 5, QTableWidgetItem(row["csv_type"]))
            self.preview_table.setItem(i, 6, QTableWidgetItem(row["mapped_label"]))

            pts_item = QTableWidgetItem(str(row["points"]) if row["points"] != "" else "")
            pts_item.setTextAlignment(Qt.AlignCenter)
            self.preview_table.setItem(i, 7, pts_item)

            status_item = QTableWidgetItem(row["status"])
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            if row["status"] == STATUS_READY:
                status_item.setForeground(QColor(COLORS["success"]))
            elif row["status"] == STATUS_UNMATCHED:
                status_item.setForeground(QColor(COLORS["warning"]))
            else:
                status_item.setForeground(QColor(COLORS["danger"]))
            self.preview_table.setItem(i, 8, status_item)

            self.preview_table.setRowHeight(i, 38)

        # Summary counts
        ready_count = sum(1 for r in self._rows if r["status"] == STATUS_READY)
        unmatched_count = sum(1 for r in self._rows if r["status"] == STATUS_UNMATCHED)
        error_count = sum(1 for r in self._rows if r["status"] == STATUS_ERROR)
        total = len(self._rows)

        self.lbl_summary.setText(
            f"Ready: {ready_count}  |  Unmatched: {unmatched_count}  |  "
            f"Errors: {error_count}  |  Total: {total}"
        )
        self.btn_import.setText(f"Import Ready Rows ({ready_count})")

    # ── Import ───────────────────────────────────────────────────────

    def _do_import(self):
        ready = [r for r in self._rows if r["status"] == STATUS_READY]
        if not ready:
            QMessageBox.information(self, "Import", "No ready rows to import.")
            return

        reply = QMessageBox.question(
            self, "Confirm Import",
            f"Import {len(ready)} infraction(s)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        username = self.app_state.get("username", "")
        imported = 0
        errors = []

        for row in ready:
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
                    "attendance", "infraction_imported", username,
                    details=(
                        f"CSV import: {row['mapped_label']} for "
                        f"{row['matched_name']} (row {row['row_num']})"
                    ),
                    table_name="ats_infractions",
                    record_id=str(infraction_id),
                    action="create",
                    employee_id=row["matched_id"],
                )
                imported += 1
            except Exception as exc:
                errors.append(f"Row {row['row_num']}: {exc}")

        result_parts = [f"Imported: {imported}"]
        if errors:
            result_parts.append(f"Errors: {len(errors)}")
        self.lbl_result.setText("  |  ".join(result_parts))
        self.lbl_result.setStyleSheet(
            f"color: {COLORS['success']}; font-size: 13px; font-weight: 600;"
        )

        if errors:
            QMessageBox.warning(
                self, "Import Warnings",
                f"Imported {imported} rows with {len(errors)} error(s):\n" + "\n".join(errors[:10]),
            )
        else:
            QMessageBox.information(self, "Import Complete", f"Successfully imported {imported} infraction(s).")

        # Remove imported rows from preview
        self._rows = [r for r in self._rows if r["status"] != STATUS_READY]
        self._update_table()

    # ── Clear ────────────────────────────────────────────────────────

    def _clear(self):
        self._rows.clear()
        self._filter = "all"
        self._update_filter_styles()
        self._update_table()
        self.lbl_filepath.setText("No file selected")
        self.lbl_result.setText("")
        self.lbl_result.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
