"""
Cerasus Hub -- Hub Audit Viewer
Unified audit trail across all modules in a single timeline.
"""

import csv
import os
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QComboBox, QDateEdit, QLineEdit,
    QFileDialog, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont

from src.config import COLORS, tc, btn_style
from src.database import get_conn


class HubAuditViewer(QWidget):
    """Full-page audit trail viewer for all CerasusHub modules."""

    def __init__(self, on_back=None, parent=None):
        super().__init__(parent)
        self._on_back = on_back
        self._build()
        self._load_data()

    # ── Build UI ──────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"""
            QFrame {{ background: {tc('card')}; border-bottom: 1px solid {tc('border')}; }}
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(24, 0, 24, 0)

        if self._on_back:
            back_btn = QPushButton("Back to Hub")
            back_btn.setCursor(Qt.PointingHandCursor)
            back_btn.setFixedHeight(36)
            back_btn.setStyleSheet(btn_style(tc('info'), "white", tc('text')))
            back_btn.clicked.connect(self._on_back)
            h_lay.addWidget(back_btn)
            h_lay.addSpacing(16)

        title = QLabel("Hub Audit Trail")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        h_lay.addWidget(title)
        h_lay.addStretch()

        export_btn = QPushButton("Export CSV")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setFixedHeight(36)
        export_btn.setStyleSheet(btn_style(COLORS['accent'], "white", COLORS['accent_hover']))
        export_btn.clicked.connect(self._export_csv)
        h_lay.addWidget(export_btn)

        outer.addWidget(header)

        # ── Filter row ────────────────────────────────────────────────
        filter_frame = QFrame()
        filter_frame.setStyleSheet(f"""
            QFrame {{ background: {tc('card')}; border-bottom: 1px solid {tc('border')}; }}
        """)
        f_lay = QHBoxLayout(filter_frame)
        f_lay.setContentsMargins(24, 8, 24, 8)
        f_lay.setSpacing(12)

        # Module filter
        f_lay.addWidget(QLabel("Module:"))
        self.module_combo = QComboBox()
        self.module_combo.addItems(["All", "Operations", "Uniforms", "Attendance", "Training", "Hub"])
        self.module_combo.setFixedWidth(140)
        f_lay.addWidget(self.module_combo)

        # Date range
        f_lay.addWidget(QLabel("From:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.setFixedWidth(130)
        f_lay.addWidget(self.date_from)

        f_lay.addWidget(QLabel("To:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setFixedWidth(130)
        f_lay.addWidget(self.date_to)

        # User filter
        f_lay.addWidget(QLabel("User:"))
        self.user_combo = QComboBox()
        self.user_combo.addItem("All")
        self.user_combo.setFixedWidth(140)
        self._populate_users()
        f_lay.addWidget(self.user_combo)

        # Search text
        f_lay.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by details...")
        self.search_input.setFixedWidth(200)
        f_lay.addWidget(self.search_input)

        # Apply button
        apply_btn = QPushButton("Apply")
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.setFixedHeight(34)
        apply_btn.setStyleSheet(btn_style(tc('info'), "white"))
        apply_btn.clicked.connect(self._load_data)
        f_lay.addWidget(apply_btn)

        f_lay.addStretch()
        outer.addWidget(filter_frame)

        # ── Audit table ───────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Module", "Event Type", "User", "Details"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        outer.addWidget(self.table, 1)

        # ── Status bar ────────────────────────────────────────────────
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"""
            color: {tc('text_light')}; padding: 6px 24px;
            font-size: 13px; background: {tc('card')};
            border-top: 1px solid {tc('border')};
        """)
        outer.addWidget(self.status_label)

    # ── Data loading ──────────────────────────────────────────────────

    def _populate_users(self):
        """Load distinct usernames from audit_log into the user filter combo."""
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT DISTINCT username FROM audit_log WHERE username != '' ORDER BY username"
            ).fetchall()
            conn.close()
            for row in rows:
                self.user_combo.addItem(row["username"])
        except Exception:
            pass

    def _load_data(self):
        """Query audit_log with current filters and populate the table."""
        conditions = []
        params = []

        # Module filter
        module_text = self.module_combo.currentText()
        if module_text != "All":
            conditions.append("LOWER(module_name) = LOWER(?)")
            params.append(module_text)

        # Date range
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().addDays(1).toString("yyyy-MM-dd")
        conditions.append("timestamp >= ?")
        params.append(date_from)
        conditions.append("timestamp < ?")
        params.append(date_to)

        # User filter
        user_text = self.user_combo.currentText()
        if user_text != "All":
            conditions.append("username = ?")
            params.append(user_text)

        # Search text
        search_text = self.search_input.text().strip()
        if search_text:
            conditions.append("(details LIKE ? OR event_type LIKE ? OR action LIKE ?)")
            like = f"%{search_text}%"
            params.extend([like, like, like])

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM audit_log WHERE {where} ORDER BY id DESC LIMIT 500"

        try:
            conn = get_conn()
            rows = conn.execute(sql, params).fetchall()
            conn.close()
        except Exception:
            rows = []

        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(str(row["timestamp"] or "")))
            self.table.setItem(i, 1, QTableWidgetItem(str(row["module_name"] or "")))
            self.table.setItem(i, 2, QTableWidgetItem(str(row["event_type"] or "")))
            self.table.setItem(i, 3, QTableWidgetItem(str(row["username"] or "")))
            details = str(row["details"] or "")
            if not details and row["action"]:
                details = str(row["action"])
            self.table.setItem(i, 4, QTableWidgetItem(details))

        self.status_label.setText(f"Showing {len(rows)} audit events")

    # ── Export ─────────────────────────────────────────────────────────

    def _export_csv(self):
        """Export the current table contents to a CSV file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Audit Trail", "audit_trail.csv", "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                headers = ["Timestamp", "Module", "Event Type", "User", "Details"]
                writer.writerow(headers)
                for row_idx in range(self.table.rowCount()):
                    row_data = []
                    for col_idx in range(self.table.columnCount()):
                        item = self.table.item(row_idx, col_idx)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)
            QMessageBox.information(self, "Export Complete", f"Exported {self.table.rowCount()} records to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export: {e}")
