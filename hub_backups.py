"""
Cerasus Hub -- Database Backups Page
View, create, and restore database backups from the hub level.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.config import COLORS, tc, btn_style
from src.backup_manager import (
    create_backup, get_backup_list, get_last_backup_time, restore_backup,
)


class HubBackupsPage(QWidget):
    """Full-page backup management view for Cerasus Hub."""

    def __init__(self, on_back=None, parent=None):
        super().__init__(parent)
        self._on_back = on_back
        self._build()
        self._refresh()

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
            back_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {tc('text_light')};
                    font-size: 13px; font-weight: 600; border: none; padding: 0 12px;
                }}
                QPushButton:hover {{ color: {COLORS['accent']}; }}
            """)
            back_btn.clicked.connect(self._on_back)
            h_lay.addWidget(back_btn)

        h_lay.addSpacing(12)

        title = QLabel("DATABASE BACKUPS")
        title.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 18px; font-weight: 700;
            letter-spacing: 2px; background: transparent;
        """)
        h_lay.addWidget(title)
        h_lay.addStretch()

        outer.addWidget(header)

        # ── Scrollable content ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {tc('bg')}; border: none; }}")

        content = QWidget()
        content.setStyleSheet(f"background: {tc('bg')};")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(40, 28, 40, 28)
        content_lay.setSpacing(20)

        # ── Status card ───────────────────────────────────────────────
        status_card = QFrame()
        status_card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
                padding: 20px 24px;
            }}
        """)
        status_lay = QHBoxLayout(status_card)
        status_lay.setSpacing(32)

        # Last backup time
        last_col = QVBoxLayout()
        last_label = QLabel("LAST BACKUP")
        last_label.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; font-weight: 600;
            letter-spacing: 1px; background: transparent;
        """)
        last_col.addWidget(last_label)

        self.last_backup_lbl = QLabel("--")
        self.last_backup_lbl.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700;
            background: transparent;
        """)
        last_col.addWidget(self.last_backup_lbl)
        status_lay.addLayout(last_col)

        # Separator
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {tc('border')};")
        sep.setMinimumHeight(40)
        status_lay.addWidget(sep)

        # Total backups
        count_col = QVBoxLayout()
        count_label = QLabel("TOTAL BACKUPS")
        count_label.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; font-weight: 600;
            letter-spacing: 1px; background: transparent;
        """)
        count_col.addWidget(count_label)

        self.backup_count_lbl = QLabel("0")
        self.backup_count_lbl.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700;
            background: transparent;
        """)
        count_col.addWidget(self.backup_count_lbl)
        status_lay.addLayout(count_col)

        # Separator
        sep2 = QFrame()
        sep2.setFixedWidth(1)
        sep2.setStyleSheet(f"background: {tc('border')};")
        sep2.setMinimumHeight(40)
        status_lay.addWidget(sep2)

        # Total size
        size_col = QVBoxLayout()
        size_label = QLabel("TOTAL SIZE")
        size_label.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; font-weight: 600;
            letter-spacing: 1px; background: transparent;
        """)
        size_col.addWidget(size_label)

        self.total_size_lbl = QLabel("0 MB")
        self.total_size_lbl.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700;
            background: transparent;
        """)
        size_col.addWidget(self.total_size_lbl)
        status_lay.addLayout(size_col)

        status_lay.addStretch()

        # Backup Now button
        self.backup_now_btn = QPushButton("Backup Now")
        self.backup_now_btn.setCursor(Qt.PointingHandCursor)
        self.backup_now_btn.setFixedHeight(40)
        self.backup_now_btn.setFixedWidth(140)
        self.backup_now_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px; font-weight: 700;
                border: none; border-radius: 6px;
                padding: 0 20px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        self.backup_now_btn.clicked.connect(self._on_backup_now)
        status_lay.addWidget(self.backup_now_btn)

        content_lay.addWidget(status_card)

        # ── Backup list table ─────────────────────────────────────────
        table_header_lay = QHBoxLayout()
        table_title = QLabel("AVAILABLE BACKUPS")
        table_title.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px; font-weight: 700;
            letter-spacing: 2px; background: transparent;
        """)
        table_header_lay.addWidget(table_title)
        table_header_lay.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setFixedHeight(30)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {tc('border')}; color: {tc('text')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 600;
                border-radius: 4px; padding: 4px 14px;
            }}
            QPushButton:hover {{ background: {COLORS['accent']}; color: white; }}
        """)
        refresh_btn.clicked.connect(self._refresh)
        table_header_lay.addWidget(refresh_btn)
        content_lay.addLayout(table_header_lay)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Filename", "Date", "Size (MB)", "Reason", "Actions"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(300)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 6px;
                gridline-color: {tc('border')};
            }}
        """)
        content_lay.addWidget(self.table)

        content_lay.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── Refresh data ──────────────────────────────────────────────────

    def _refresh(self):
        backups = get_backup_list()

        # Update status labels
        if backups:
            self.last_backup_lbl.setText(backups[0]["created_at"])
        else:
            self.last_backup_lbl.setText("No backups yet")

        self.backup_count_lbl.setText(str(len(backups)))

        total_mb = sum(b["size_mb"] for b in backups)
        self.total_size_lbl.setText(f"{total_mb:.1f} MB")

        # Populate table
        self.table.setRowCount(len(backups))
        for row_idx, b in enumerate(backups):
            self.table.setItem(row_idx, 0, QTableWidgetItem(b["filename"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(b["created_at"]))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(b["size_mb"])))
            self.table.setItem(row_idx, 3, QTableWidgetItem(b["reason"]))

            # Restore button
            restore_btn = QPushButton("Restore")
            restore_btn.setCursor(Qt.PointingHandCursor)
            restore_btn.setFixedHeight(28)
            restore_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {tc('border')}; color: {tc('text')};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 11px; font-weight: 600;
                    border-radius: 4px; padding: 2px 12px;
                }}
                QPushButton:hover {{ background: {COLORS['danger']}; color: white; }}
            """)
            path = b["path"]
            restore_btn.clicked.connect(lambda checked=False, p=path: self._on_restore(p))
            self.table.setCellWidget(row_idx, 4, restore_btn)

        self.table.resizeRowsToContents()

    # ── Actions ───────────────────────────────────────────────────────

    def _on_backup_now(self):
        self.backup_now_btn.setEnabled(False)
        self.backup_now_btn.setText("Backing up...")

        try:
            path = create_backup("manual")
            if path:
                QMessageBox.information(
                    self, "Backup Complete",
                    f"Backup created successfully.\n\n{path}"
                )
            else:
                QMessageBox.warning(
                    self, "Backup Failed",
                    "Could not create backup. Check that the database file exists."
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Backup Error",
                f"An error occurred while creating the backup:\n{e}"
            )
        finally:
            self.backup_now_btn.setEnabled(True)
            self.backup_now_btn.setText("Backup Now")
            self._refresh()

    def _on_restore(self, backup_path):
        """Restore a backup after double-confirmation."""
        reply = QMessageBox.warning(
            self, "Confirm Restore",
            "WARNING: Restoring a backup will overwrite the current database.\n\n"
            "A safety backup of the current state will be created first.\n\n"
            "Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Second confirmation
        reply2 = QMessageBox.critical(
            self, "Final Confirmation",
            "This action CANNOT be undone (except by using the safety backup).\n\n"
            "The application should be restarted after restoring.\n\n"
            "Proceed with restore?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply2 != QMessageBox.Yes:
            return

        success = restore_backup(backup_path)
        if success:
            QMessageBox.information(
                self, "Restore Complete",
                "Database has been restored successfully.\n\n"
                "Please restart the application for changes to take full effect."
            )
        else:
            QMessageBox.critical(
                self, "Restore Failed",
                "Could not restore the backup. The original database is unchanged."
            )
        self._refresh()
