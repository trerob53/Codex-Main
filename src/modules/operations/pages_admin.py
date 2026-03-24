"""
Cerasus Hub — Operations Module: Admin Pages
ReportsPage, AuditLogPage, SettingsPage, UserManagementPage.
"""

import csv
import os
from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QMessageBox, QFileDialog, QFormLayout,
    QGroupBox, QAbstractItemView, QDialog, QDialogButtonBox,
    QScrollArea, QCheckBox, QDateEdit, QApplication,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from src.config import (
    COLORS, ROLE_ADMIN, ROLE_STANDARD, build_dialog_stylesheet, tc, _is_dark,
    btn_style, APP_NAME, APP_VERSION, REPORTS_DIR, ensure_directories,
    ROOT_DIR, DATA_DIR, set_dark_mode,
)
from src.modules.operations import data_manager
from src.shared_widgets import BarChartWidget
from src import audit, auth


# ════════════════════════════════════════════════════════════════════════
# Reports Page — CSV export, printable reports, charts
# ════════════════════════════════════════════════════════════════════════

class ReportsPage(QWidget):
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
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        header = QLabel("Reports & Analytics")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setStyleSheet(f"color: {tc('primary')};")
        layout.addWidget(header)

        # Export buttons row
        btn_row = QHBoxLayout()
        btn_assignments_csv = QPushButton("Export Assignments CSV")
        btn_assignments_csv.setStyleSheet(btn_style(COLORS["primary"], "white", COLORS["primary_light"]))
        btn_assignments_csv.clicked.connect(self._export_assignments_csv)
        btn_row.addWidget(btn_assignments_csv)

        btn_pto_csv = QPushButton("Export PTO Entries CSV")
        btn_pto_csv.setStyleSheet(btn_style(COLORS["primary"], "white", COLORS["primary_light"]))
        btn_pto_csv.clicked.connect(self._export_pto_csv)
        btn_row.addWidget(btn_pto_csv)

        btn_audit_csv = QPushButton("Export Audit Log CSV")
        btn_audit_csv.setStyleSheet(btn_style(COLORS["primary_light"], "white"))
        btn_audit_csv.clicked.connect(self._export_audit_csv)
        btn_row.addWidget(btn_audit_csv)

        btn_print = QPushButton("Generate Printable Report")
        btn_print.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        btn_print.clicked.connect(self._generate_printable_report)
        btn_row.addWidget(btn_print)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Analytics row — charts
        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        # Assignments by site chart
        self.grp_site = QGroupBox("Assignments by Site")
        self.site_layout = QVBoxLayout(self.grp_site)
        self.site_chart = BarChartWidget()
        self.site_layout.addWidget(self.site_chart)
        charts_row.addWidget(self.grp_site)

        # PTO by type chart
        self.grp_pto = QGroupBox("PTO by Type")
        self.pto_layout = QVBoxLayout(self.grp_pto)
        self.pto_chart = BarChartWidget()
        self.pto_layout.addWidget(self.pto_chart)
        charts_row.addWidget(self.grp_pto)

        layout.addLayout(charts_row)

        # Assignments preview table
        grp_asn = QGroupBox("Recent Assignments")
        asn_layout = QVBoxLayout(grp_asn)
        self.asn_table = QTableWidget(0, 5)
        self.asn_table.setHorizontalHeaderLabels(["Officer", "Site", "Date", "Shift", "Status"])
        self.asn_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.asn_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.asn_table.verticalHeader().setVisible(False)
        self.asn_table.setAlternatingRowColors(True)
        asn_layout.addWidget(self.asn_table)
        layout.addWidget(grp_asn)

        # PTO preview table
        grp_pto = QGroupBox("Recent PTO Entries")
        pto_layout = QVBoxLayout(grp_pto)
        self.pto_table = QTableWidget(0, 5)
        self.pto_table.setHorizontalHeaderLabels(["Officer", "Type", "Start", "End", "Status"])
        self.pto_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pto_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pto_table.verticalHeader().setVisible(False)
        self.pto_table.setAlternatingRowColors(True)
        pto_layout.addWidget(self.pto_table)
        layout.addWidget(grp_pto)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self):
        all_assignments = data_manager.get_all_assignments()
        all_pto = data_manager.get_all_pto()

        # Site chart — aggregate assignment counts per site
        site_counts = {}
        for a in all_assignments:
            sn = a.get("site_name", "")
            if sn:
                site_counts[sn] = site_counts.get(sn, 0) + 1
        site_data = [(site, count, tc("info"))
                     for site, count in sorted(site_counts.items(), key=lambda x: -x[1])[:10]]
        self.site_chart.set_data(site_data)

        # PTO chart — aggregate by type
        pto_type_counts = {}
        for p in all_pto:
            pt = p.get("pto_type", "Other")
            pto_type_counts[pt] = pto_type_counts.get(pt, 0) + 1
        pto_colors = {
            "Vacation": COLORS["info"], "Sick": COLORS["warning"],
            "Personal": COLORS["accent"], "FMLA": COLORS["danger"],
        }
        pto_data = [(t, c, pto_colors.get(t, "#6b7280"))
                    for t, c in sorted(pto_type_counts.items(), key=lambda x: -x[1])]
        self.pto_chart.set_data(pto_data)

        # Assignments preview table (most recent 50)
        recent_asn = all_assignments[:50]
        self.asn_table.setRowCount(len(recent_asn))
        for i, asn in enumerate(recent_asn):
            self.asn_table.setItem(i, 0, QTableWidgetItem(asn.get("officer_name", "")))
            self.asn_table.setItem(i, 1, QTableWidgetItem(asn.get("site_name", "")))
            self.asn_table.setItem(i, 2, QTableWidgetItem(asn.get("date", "")))
            shift = f"{asn.get('start_time', '')} - {asn.get('end_time', '')}".strip(" -")
            self.asn_table.setItem(i, 3, QTableWidgetItem(shift))
            self.asn_table.setItem(i, 4, QTableWidgetItem(asn.get("status", "")))

        # PTO preview table (most recent 50)
        recent_pto = all_pto[:50]
        self.pto_table.setRowCount(len(recent_pto))
        for i, p in enumerate(recent_pto):
            self.pto_table.setItem(i, 0, QTableWidgetItem(p.get("officer_name", "")))
            self.pto_table.setItem(i, 1, QTableWidgetItem(p.get("pto_type", "")))
            self.pto_table.setItem(i, 2, QTableWidgetItem(p.get("start_date", "")))
            self.pto_table.setItem(i, 3, QTableWidgetItem(p.get("end_date", "")))
            self.pto_table.setItem(i, 4, QTableWidgetItem(p.get("status", "")))

    def _export_assignments_csv(self):
        ensure_directories()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(REPORTS_DIR, f"assignments_export_{ts}.csv")
        assignments = data_manager.get_all_assignments()
        if not assignments:
            QMessageBox.information(self, "No Data", "No assignments to export.")
            return
        keys = list(assignments[0].keys())
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(assignments)
        audit.log_event("operations", "report_export", self.app_state["user"]["username"],
                        f"Exported assignments CSV: {filename}")
        QMessageBox.information(self, "Export Complete", f"Saved to:\n{filename}")

    def _export_pto_csv(self):
        ensure_directories()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(REPORTS_DIR, f"pto_export_{ts}.csv")
        entries = data_manager.get_all_pto()
        if not entries:
            QMessageBox.information(self, "No Data", "No PTO entries to export.")
            return
        keys = list(entries[0].keys())
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(entries)
        audit.log_event("operations", "report_export", self.app_state["user"]["username"],
                        f"Exported PTO CSV: {filename}")
        QMessageBox.information(self, "Export Complete", f"Saved to:\n{filename}")

    def _export_audit_csv(self):
        ensure_directories()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(REPORTS_DIR, f"audit_log_export_{ts}.csv")
        entries = audit.get_log("operations", limit=10000)
        if not entries:
            QMessageBox.information(self, "No Data", "No audit entries to export.")
            return
        keys = list(entries[0].keys())
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(entries)
        audit.log_event("operations", "report_export", self.app_state["user"]["username"],
                        f"Exported audit CSV: {filename}")
        QMessageBox.information(self, "Export Complete", f"Saved to:\n{filename}")

    def _generate_printable_report(self):
        """Generate a formatted text report that can be printed or saved."""
        ensure_directories()
        all_assignments = data_manager.get_all_assignments()
        all_pto = data_manager.get_all_pto()
        officers = data_manager.get_ops_officers(active_only=False)

        # Compute site counts from assignments
        site_counts = {}
        for a in all_assignments:
            sn = a.get("site_name", "")
            if sn:
                site_counts[sn] = site_counts.get(sn, 0) + 1

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ts_display = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = os.path.join(REPORTS_DIR, f"report_{ts}.txt")

        lines = []
        lines.append("=" * 72)
        lines.append(f"  {APP_NAME}")
        lines.append(f"  Operations Report")
        lines.append(f"  Generated: {ts_display}")
        lines.append(f"  Generated by: {self.app_state['user']['username']}")
        lines.append("=" * 72)
        lines.append("")
        lines.append("SUMMARY")
        lines.append("-" * 40)
        lines.append(f"  Total Officers: {len(officers)}")
        lines.append(f"  Total Assignments: {len(all_assignments)}")
        lines.append(f"  Total PTO Entries: {len(all_pto)}")
        lines.append("")
        lines.append("ASSIGNMENTS BY SITE")
        lines.append("-" * 40)
        for site, count in sorted(site_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {site}: {count}")
        lines.append("")
        lines.append("RECENT ASSIGNMENTS")
        lines.append("-" * 72)
        lines.append(f"  {'Officer':<20} {'Site':<15} {'Date':<12} {'Shift':<15} {'Status':<10}")
        lines.append("  " + "-" * 67)
        for asn in all_assignments[:50]:
            shift = f"{asn.get('start_time', '')}-{asn.get('end_time', '')}".strip("-")
            lines.append(
                f"  {asn.get('officer_name', ''):<20} "
                f"{asn.get('site_name', ''):<15} "
                f"{asn.get('date', ''):<12} "
                f"{shift:<15} "
                f"{asn.get('status', ''):<10}"
            )
        lines.append("")
        lines.append("PTO ENTRIES")
        lines.append("-" * 72)
        lines.append(f"  {'Officer':<20} {'Type':<12} {'Start':<12} {'End':<12} {'Status':<10}")
        lines.append("  " + "-" * 67)
        for p in all_pto[:50]:
            lines.append(
                f"  {p.get('officer_name', ''):<20} "
                f"{p.get('pto_type', ''):<12} "
                f"{p.get('start_date', ''):<12} "
                f"{p.get('end_date', ''):<12} "
                f"{p.get('status', ''):<10}"
            )
        lines.append("")
        lines.append("=" * 72)
        lines.append(f"  End of Report")
        lines.append("=" * 72)

        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        audit.log_event("operations", "report_export", self.app_state["user"]["username"],
                        f"Generated printable report: {filename}")
        QMessageBox.information(self, "Report Generated",
                                f"Printable report saved to:\n{filename}\n\n"
                                f"You can open this file and print it from Notepad or any text editor.")


# ════════════════════════════════════════════════════════════════════════
# Audit Log Page
# ════════════════════════════════════════════════════════════════════════

class AuditLogPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)

        header = QLabel("Audit Log")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setStyleSheet(f"color: {tc('primary')};")
        layout.addWidget(header)

        # Filter row
        filter_row = QHBoxLayout()
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Filter by user, event type, or details...")
        self.txt_filter.textChanged.connect(self.refresh)
        filter_row.addWidget(self.txt_filter)

        self.cmb_event = QComboBox()
        self.cmb_event.addItems([
            "All Events", "login", "login_failed", "logout",
            "assignment_create", "assignment_edit", "assignment_delete",
            "pto_create", "pto_edit", "pto_import",
            "officer_create", "officer_edit", "officer_delete",
            "report_export", "user_create", "user_update",
        ])
        self.cmb_event.currentTextChanged.connect(self.refresh)
        self.cmb_event.setFixedWidth(180)
        filter_row.addWidget(self.cmb_event)
        layout.addLayout(filter_row)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Event", "Username", "Computer", "Details"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        self.lbl_count = QLabel("0 entries")
        self.lbl_count.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px;")
        layout.addWidget(self.lbl_count)

    def refresh(self):
        entries = audit.get_log("operations", limit=500)
        text_filter = self.txt_filter.text().strip().lower()
        event_filter = self.cmb_event.currentText()

        if event_filter != "All Events":
            entries = [e for e in entries if e.get("event_type") == event_filter]
        if text_filter:
            entries = [e for e in entries if
                       text_filter in e.get("username", "").lower() or
                       text_filter in e.get("details", "").lower() or
                       text_filter in e.get("event_type", "").lower()]

        self.table.setRowCount(len(entries))
        for i, ev in enumerate(entries):
            ts = ev.get("timestamp", "")[:19].replace("T", " ")
            self.table.setItem(i, 0, QTableWidgetItem(ts))

            event_item = QTableWidgetItem(ev.get("event_type", ""))
            event_type = ev.get("event_type", "")
            # Color-code event types
            if "create" in event_type or "login" == event_type:
                event_item.setForeground(QColor(COLORS["success"]))
            elif "delete" in event_type or "failed" in event_type:
                event_item.setForeground(QColor(COLORS["danger"]))
            elif "edit" in event_type or "update" in event_type:
                event_item.setForeground(QColor(COLORS["warning"]))
            elif "export" in event_type:
                event_item.setForeground(QColor(COLORS["primary"]))
            self.table.setItem(i, 1, event_item)

            self.table.setItem(i, 2, QTableWidgetItem(ev.get("username", "")))
            self.table.setItem(i, 3, QTableWidgetItem(ev.get("computer", "")))
            self.table.setItem(i, 4, QTableWidgetItem(ev.get("details", "")))
        self.lbl_count.setText(f"{len(entries)} entries")


# ════════════════════════════════════════════════════════════════════════
# Settings Page (App Config, Theme, Password Change)
# ════════════════════════════════════════════════════════════════════════

class SettingsPage(QWidget):
    """Settings page with app info, theme toggle, and password change."""

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
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        header = QLabel("Settings")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setStyleSheet(f"color: {tc('primary')};")
        layout.addWidget(header)

        # App Info
        info_grp = QGroupBox("Application Info")
        info_lay = QFormLayout(info_grp)
        info_lay.setSpacing(8)
        info_lay.addRow("Application:", QLabel(APP_NAME))
        info_lay.addRow("Version:", QLabel(APP_VERSION))
        info_lay.addRow("App Root:", QLabel(ROOT_DIR))
        info_lay.addRow("Data Directory:", QLabel(DATA_DIR))
        layout.addWidget(info_grp)

        # Change Password
        pw_grp = QGroupBox("Change Your Password")
        pw_lay = QFormLayout(pw_grp)
        pw_lay.setSpacing(10)
        self.txt_current_pw = QLineEdit()
        self.txt_current_pw.setEchoMode(QLineEdit.Password)
        self.txt_current_pw.setPlaceholderText("Current password")
        pw_lay.addRow("Current:", self.txt_current_pw)
        self.txt_new_pw = QLineEdit()
        self.txt_new_pw.setEchoMode(QLineEdit.Password)
        self.txt_new_pw.setPlaceholderText("New password")
        pw_lay.addRow("New:", self.txt_new_pw)
        self.txt_confirm_pw = QLineEdit()
        self.txt_confirm_pw.setEchoMode(QLineEdit.Password)
        self.txt_confirm_pw.setPlaceholderText("Confirm new password")
        pw_lay.addRow("Confirm:", self.txt_confirm_pw)
        btn_change_pw = QPushButton("Change Password")
        btn_change_pw.setStyleSheet(btn_style(COLORS["primary"], "white", COLORS["primary_light"]))
        btn_change_pw.clicked.connect(self._change_password)
        pw_lay.addRow("", btn_change_pw)
        layout.addWidget(pw_grp)

        # Theme
        theme_grp = QGroupBox("Theme")
        theme_lay = QHBoxLayout(theme_grp)
        self.btn_light = QPushButton("Light Mode")
        self.btn_light.setStyleSheet(btn_style(COLORS["primary"], "white", COLORS["primary_light"]))
        self.btn_light.clicked.connect(lambda: self._set_theme("light"))
        theme_lay.addWidget(self.btn_light)
        self.btn_dark = QPushButton("Dark Mode")
        self.btn_dark.setStyleSheet(btn_style("#1e1e2e", "white", "#2d2d3f"))
        self.btn_dark.clicked.connect(lambda: self._set_theme("dark"))
        theme_lay.addWidget(self.btn_dark)
        layout.addWidget(theme_grp)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self):
        pass  # No dynamic state to refresh

    def _change_password(self):
        username = self.app_state["user"]["username"]
        current = self.txt_current_pw.text().strip()
        new_pw = self.txt_new_pw.text().strip()
        confirm = self.txt_confirm_pw.text().strip()

        if not current or not new_pw:
            QMessageBox.warning(self, "Validation", "All fields are required.")
            return
        if new_pw != confirm:
            QMessageBox.warning(self, "Mismatch", "New passwords do not match.")
            return
        # Verify current password
        user = auth.authenticate(username, current)
        if not user:
            QMessageBox.warning(self, "Incorrect", "Current password is incorrect.")
            return
        auth.update_user(username, new_password=new_pw)
        audit.log_event("operations", "user_update", username, "Changed own password")
        QMessageBox.information(self, "Done", "Password changed successfully.")
        self.txt_current_pw.clear()
        self.txt_new_pw.clear()
        self.txt_confirm_pw.clear()

    def _set_theme(self, mode):
        dark = mode == "dark"
        self.app_state["dark_mode"] = dark
        # Update the config cache
        set_dark_mode(dark)
        # Try to find main window and apply theme (no-op if not found)
        app = QApplication.instance()
        if app:
            for w in app.topLevelWidgets():
                if hasattr(w, 'apply_theme'):
                    w.apply_theme(dark)
                    break


# ════════════════════════════════════════════════════════════════════════
# User Management Page (Admin Only)
# ════════════════════════════════════════════════════════════════════════

class UserManagementPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        header = QLabel("User Management")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setStyleSheet(f"color: {tc('primary')};")
        header_row.addWidget(header)
        header_row.addStretch()

        btn_add = QPushButton("+ Add User")
        btn_add.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        btn_add.clicked.connect(self._add_user)
        header_row.addWidget(btn_add)
        layout.addLayout(header_row)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Username", "Display Name", "Role", "Active", "Created"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_edit = QPushButton("Edit User")
        btn_edit.setStyleSheet(btn_style(COLORS["primary"], "white", COLORS["primary_light"]))
        btn_edit.clicked.connect(self._edit_user)
        btn_row.addWidget(btn_edit)

        btn_reset = QPushButton("Reset Password")
        btn_reset.setStyleSheet(btn_style(COLORS["warning"], "white"))
        btn_reset.clicked.connect(self._reset_password)
        btn_row.addWidget(btn_reset)

        btn_toggle = QPushButton("Toggle Active")
        btn_toggle.setStyleSheet(btn_style(COLORS["danger"], "white"))
        btn_toggle.clicked.connect(self._toggle_active)
        btn_row.addWidget(btn_toggle)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def refresh(self):
        users = auth.get_all_users()
        self.table.setRowCount(len(users))
        for i, u in enumerate(users):
            self.table.setItem(i, 0, QTableWidgetItem(u["username"]))
            self.table.setItem(i, 1, QTableWidgetItem(u["display_name"]))

            role_item = QTableWidgetItem(u["role"].upper())
            if u["role"] == ROLE_ADMIN:
                role_item.setForeground(QColor(COLORS["accent"]))
                role_item.setFont(QFont("Segoe UI", 14, QFont.Bold))
            self.table.setItem(i, 2, role_item)

            active_item = QTableWidgetItem("Yes" if u["active"] else "No")
            active_item.setForeground(
                QColor(COLORS["success"]) if u["active"] else QColor(COLORS["danger"])
            )
            self.table.setItem(i, 3, active_item)
            self.table.setItem(i, 4, QTableWidgetItem(u.get("created_at", "")[:10]))

    def _get_selected_username(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _add_user(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add User")
        dlg.setMinimumWidth(350)
        form = QFormLayout(dlg)
        form.setSpacing(12)
        form.setContentsMargins(24, 24, 24, 24)

        txt_uname = QLineEdit()
        txt_uname.setPlaceholderText("Username")
        form.addRow("Username:", txt_uname)
        txt_display = QLineEdit()
        txt_display.setPlaceholderText("Display Name")
        form.addRow("Display Name:", txt_display)
        txt_pass = QLineEdit()
        txt_pass.setEchoMode(QLineEdit.Password)
        txt_pass.setPlaceholderText("Password")
        form.addRow("Password:", txt_pass)
        cmb_role = QComboBox()
        cmb_role.addItems(["Standard", "Admin"])
        form.addRow("Role:", cmb_role)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec() == QDialog.Accepted:
            uname = txt_uname.text().strip()
            pw = txt_pass.text().strip()
            if not uname or not pw:
                QMessageBox.warning(self, "Validation", "Username and password are required.")
                return
            ok = auth.create_user(uname, pw, cmb_role.currentText().lower(), txt_display.text().strip())
            if ok:
                admin = self.app_state["user"]["username"]
                audit.log_event("operations", "user_create", admin, f"Created user: {uname}")
                self.refresh()
            else:
                QMessageBox.warning(self, "Error", f"Username '{uname}' already exists.")

    def _edit_user(self):
        uname = self._get_selected_username()
        if not uname:
            QMessageBox.information(self, "Select", "Please select a user.")
            return
        users = auth.get_all_users()
        user = next((u for u in users if u["username"] == uname), None)
        if not user:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit User: {uname}")
        dlg.setMinimumWidth(350)
        form = QFormLayout(dlg)
        form.setSpacing(12)
        form.setContentsMargins(24, 24, 24, 24)

        txt_display = QLineEdit(user["display_name"])
        form.addRow("Display Name:", txt_display)
        cmb_role = QComboBox()
        cmb_role.addItems(["Standard", "Admin"])
        cmb_role.setCurrentText(user["role"].capitalize())
        form.addRow("Role:", cmb_role)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec() == QDialog.Accepted:
            auth.update_user(uname, new_display_name=txt_display.text().strip(),
                             new_role=cmb_role.currentText().lower())
            admin = self.app_state["user"]["username"]
            audit.log_event("operations", "user_update", admin, f"Updated user: {uname}")
            self.refresh()

    def _reset_password(self):
        uname = self._get_selected_username()
        if not uname:
            QMessageBox.information(self, "Select", "Please select a user.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Reset Password: {uname}")
        form = QFormLayout(dlg)
        form.setContentsMargins(24, 24, 24, 24)
        txt_pass = QLineEdit()
        txt_pass.setEchoMode(QLineEdit.Password)
        txt_pass.setPlaceholderText("New password")
        form.addRow("New Password:", txt_pass)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec() == QDialog.Accepted:
            pw = txt_pass.text().strip()
            if pw:
                auth.update_user(uname, new_password=pw)
                admin = self.app_state["user"]["username"]
                audit.log_event("operations", "user_update", admin, f"Reset password for: {uname}")
                QMessageBox.information(self, "Done", f"Password reset for {uname}.")

    def _toggle_active(self):
        uname = self._get_selected_username()
        if not uname:
            return
        users = auth.get_all_users()
        user = next((u for u in users if u["username"] == uname), None)
        if not user:
            return
        new_active = 0 if user["active"] else 1
        auth.update_user(uname, new_active=new_active)
        admin = self.app_state["user"]["username"]
        audit.log_event("operations", "user_update", admin,
                        f"{'Activated' if new_active else 'Deactivated'} user: {uname}")
        self.refresh()
