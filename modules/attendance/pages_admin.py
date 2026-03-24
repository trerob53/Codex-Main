"""
Cerasus Hub -- Attendance Module: Admin Pages
AuditTrailPage, UserManagementPage, SiteManagementPage, PolicySettingsPage.
"""

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QAbstractItemView, QGroupBox, QMessageBox,
    QDialog, QFormLayout, QDialogButtonBox, QSpinBox, QDoubleSpinBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import (
    COLORS, ROLE_ADMIN, ROLE_STANDARD, build_dialog_stylesheet, tc, _is_dark,
    btn_style,
)
from src.shared_widgets import confirm_action
from src.modules.attendance import data_manager
from src.modules.attendance.policy_engine import (
    calculate_active_points, determine_discipline_level,
    count_emergency_exemptions, DISCIPLINE_LABELS,
    THRESHOLDS, POINT_WINDOW_DAYS,
)
from src import audit, auth


# ════════════════════════════════════════════════════════════════════════
# Audit Trail Page
# ════════════════════════════════════════════════════════════════════════

class AuditTrailPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(12)

        # Header
        hdr_row = QHBoxLayout()
        title = QLabel("Audit Trail")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()

        btn_recalc = QPushButton("Recalculate All Points")
        btn_recalc.setStyleSheet(btn_style(COLORS['warning']))
        btn_recalc.clicked.connect(self._recalculate_all_points)
        hdr_row.addWidget(btn_recalc)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(btn_style(tc('info')))
        btn_refresh.clicked.connect(self.refresh)
        hdr_row.addWidget(btn_refresh)
        layout.addLayout(hdr_row)

        # Audit table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Timestamp", "Event", "User", "Action", "Record ID", "Details"
        ])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        for c in range(5):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 14px; padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        layout.addWidget(self.table)

    def _recalculate_all_points(self):
        """Iterate through all officers and recalculate active_points from infractions."""
        officers = data_manager.get_all_officers()
        updated_count = 0

        for off in officers:
            oid = off.get("officer_id", "") or off.get("employee_id", "")
            if not oid:
                continue

            infractions = data_manager.get_infractions_for_employee(oid)
            new_pts = calculate_active_points(infractions)
            new_level = determine_discipline_level(new_pts)
            new_level_label = DISCIPLINE_LABELS.get(new_level, new_level)
            exemptions = count_emergency_exemptions(infractions)

            old_pts = float(off.get("active_points", 0))
            old_level = off.get("discipline_level", "")

            # Last infraction date
            last_date = ""
            if infractions:
                last_date = infractions[0].get("infraction_date", "")

            if abs(new_pts - old_pts) > 0.001 or old_level != new_level_label:
                data_manager.update_officer(oid, {
                    "active_points": new_pts,
                    "discipline_level": new_level_label,
                    "last_infraction_date": last_date,
                    "emergency_exemptions_used": exemptions,
                })
                updated_count += 1

        username = self.app_state.get("username", "")
        audit.log_event(
            "attendance", "points_recalculated", username,
            details=f"Recalculated points for all officers. {updated_count} updated.",
        )

        QMessageBox.information(
            self, "Recalculation Complete",
            f"Recalculated points for {len(officers)} officer(s).\n"
            f"{updated_count} officer(s) had their points or level updated.",
        )

    def refresh(self):
        events = audit.get_log("attendance", limit=500)
        self.table.setRowCount(len(events))
        for i, ev in enumerate(events):
            ts = ev.get("timestamp", "")[:19].replace("T", " ")
            self.table.setItem(i, 0, QTableWidgetItem(ts))
            self.table.setItem(i, 1, QTableWidgetItem(ev.get("event_type", "")))
            self.table.setItem(i, 2, QTableWidgetItem(ev.get("username", "")))
            self.table.setItem(i, 3, QTableWidgetItem(ev.get("action", "")))
            self.table.setItem(i, 4, QTableWidgetItem(ev.get("record_id", "")))
            self.table.setItem(i, 5, QTableWidgetItem(ev.get("details", "")))
            self.table.setRowHeight(i, 36)


# ════════════════════════════════════════════════════════════════════════
# User Management Page
# ════════════════════════════════════════════════════════════════════════

class UserDialog(QDialog):
    """Dialog for creating / editing a user."""

    def __init__(self, parent, user=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("Edit User" if user else "New User")
        self.setMinimumWidth(400)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        self.username_edit = QLineEdit(self.user.get("username", "") if self.user else "")
        if self.user:
            self.username_edit.setReadOnly(True)
        layout.addRow("Username:", self.username_edit)

        self.display_edit = QLineEdit(self.user.get("display_name", "") if self.user else "")
        layout.addRow("Display Name:", self.display_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Leave blank to keep current" if self.user else "Required")
        layout.addRow("Password:", self.password_edit)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["Admin", "Standard", "Viewer"])
        if self.user:
            idx = self.role_combo.findText(self.user.get("role", "standard").capitalize())
            if idx >= 0:
                self.role_combo.setCurrentIndex(idx)
        layout.addRow("Role:", self.role_combo)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_fields(self):
        return {
            "username": self.username_edit.text().strip(),
            "display_name": self.display_edit.text().strip(),
            "password": self.password_edit.text(),
            "role": self.role_combo.currentText().lower(),
        }


class UserManagementPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._users = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(12)

        # Header
        hdr_row = QHBoxLayout()
        title = QLabel("User Management")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()

        btn_add = QPushButton("+ New User")
        btn_add.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        btn_add.clicked.connect(self._add_user)
        hdr_row.addWidget(btn_add)
        layout.addLayout(hdr_row)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Username", "Display Name", "Role", "Active", "Created"
        ])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 14px; padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._edit_user)
        layout.addWidget(self.table)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_edit = QPushButton("Edit User")
        btn_edit.setStyleSheet(btn_style(COLORS['info']))
        btn_edit.clicked.connect(self._edit_user)
        btn_row.addWidget(btn_edit)

        btn_delete = QPushButton("Delete User")
        btn_delete.setStyleSheet(btn_style(COLORS['danger']))
        btn_delete.clicked.connect(self._delete_user)
        btn_row.addWidget(btn_delete)

        layout.addLayout(btn_row)

    def refresh(self):
        users = auth.get_all_users()
        self._users = users
        self.table.setRowCount(len(users))
        for i, u in enumerate(users):
            self.table.setItem(i, 0, QTableWidgetItem(u.get("username", "")))
            self.table.setItem(i, 1, QTableWidgetItem(u.get("display_name", "")))

            role_item = QTableWidgetItem(u.get("role", "").capitalize())
            role_item.setTextAlignment(Qt.AlignCenter)
            if u.get("role") == "admin":
                role_item.setForeground(QColor(COLORS["accent"]))
                role_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(i, 2, role_item)

            active = "Yes" if u.get("active") else "No"
            active_item = QTableWidgetItem(active)
            active_item.setTextAlignment(Qt.AlignCenter)
            if not u.get("active"):
                active_item.setForeground(QColor(COLORS["danger"]))
            else:
                active_item.setForeground(QColor(COLORS["success"]))
            self.table.setItem(i, 3, active_item)

            created = u.get("created_at", "")[:10]
            self.table.setItem(i, 4, QTableWidgetItem(created))
            self.table.setRowHeight(i, 40)

    def _get_selected_user(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if 0 <= row < len(self._users):
            return self._users[row]
        return None

    def _add_user(self):
        dlg = UserDialog(self)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            if not fields["username"] or not fields["password"]:
                QMessageBox.warning(self, "Validation", "Username and password are required.")
                return
            ok = auth.create_user(
                fields["username"], fields["password"],
                fields["role"], fields["display_name"],
            )
            if ok:
                username = self.app_state.get("username", "")
                audit.log_event("attendance", "user_created", username,
                                details=f"Created user: {fields['username']}")
                self.refresh()
            else:
                QMessageBox.warning(self, "Error", "Username already exists.")

    def _edit_user(self):
        user = self._get_selected_user()
        if not user:
            QMessageBox.information(self, "Select User", "Please select a user to edit.")
            return

        dlg = UserDialog(self, user)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            auth.update_user(
                fields["username"],
                new_password=fields["password"],
                new_role=fields["role"],
                new_display_name=fields["display_name"],
            )
            username = self.app_state.get("username", "")
            audit.log_event("attendance", "user_updated", username,
                            details=f"Updated user: {fields['username']}")
            self.refresh()

    def _delete_user(self):
        user = self._get_selected_user()
        if not user:
            QMessageBox.information(self, "Select User", "Please select a user to delete.")
            return

        if not confirm_action(self, "Delete User",
                              f"Delete user '{user.get('username', '')}'? This cannot be undone."):
            return

        ok = auth.delete_user(user["username"])
        if ok:
            username = self.app_state.get("username", "")
            audit.log_event("attendance", "user_deleted", username,
                            details=f"Deleted user: {user['username']}")
            self.refresh()
        else:
            QMessageBox.warning(self, "Error", "Cannot delete the last admin user.")


# ════════════════════════════════════════════════════════════════════════
# Site Management Page
# ════════════════════════════════════════════════════════════════════════

class SiteDialog(QDialog):
    """Dialog for creating / editing a site."""

    def __init__(self, parent, site=None):
        super().__init__(parent)
        self.site = site
        self.setWindowTitle("Edit Site" if site else "New Site")
        self.setMinimumWidth(450)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        self.name_edit = QLineEdit(self.site.get("name", "") if self.site else "")
        layout.addRow("Site Name:", self.name_edit)

        self.address_edit = QLineEdit(self.site.get("address", "") if self.site else "")
        layout.addRow("Address:", self.address_edit)

        self.city_edit = QLineEdit(self.site.get("city", "") if self.site else "")
        layout.addRow("City:", self.city_edit)

        self.state_edit = QLineEdit(self.site.get("state", "") if self.site else "")
        layout.addRow("State:", self.state_edit)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["Active", "Inactive"])
        if self.site:
            idx = self.status_combo.findText(self.site.get("status", "Active"))
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)
        layout.addRow("Status:", self.status_combo)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_fields(self):
        return {
            "name": self.name_edit.text().strip(),
            "address": self.address_edit.text().strip(),
            "city": self.city_edit.text().strip(),
            "state": self.state_edit.text().strip(),
            "status": self.status_combo.currentText(),
        }


class SiteManagementPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._sites = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(12)

        # Header
        hdr_row = QHBoxLayout()
        title = QLabel("Site Management")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()

        btn_add = QPushButton("+ New Site")
        btn_add.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        btn_add.clicked.connect(self._add_site)
        hdr_row.addWidget(btn_add)
        layout.addLayout(hdr_row)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Name", "Address", "City", "State", "Status"
        ])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, 5):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 14px; padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._edit_site)
        layout.addWidget(self.table)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_edit = QPushButton("Edit Site")
        btn_edit.setStyleSheet(btn_style(COLORS['info']))
        btn_edit.clicked.connect(self._edit_site)
        btn_row.addWidget(btn_edit)

        btn_delete = QPushButton("Delete Site")
        btn_delete.setStyleSheet(btn_style(COLORS['danger']))
        btn_delete.clicked.connect(self._delete_site)
        btn_row.addWidget(btn_delete)

        layout.addLayout(btn_row)

    def refresh(self):
        sites = data_manager.get_all_sites()
        self._sites = sites
        self.table.setRowCount(len(sites))
        for i, s in enumerate(sites):
            name_item = QTableWidgetItem(s.get("name", ""))
            name_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(i, 0, name_item)
            self.table.setItem(i, 1, QTableWidgetItem(s.get("address", "")))
            self.table.setItem(i, 2, QTableWidgetItem(s.get("city", "")))
            self.table.setItem(i, 3, QTableWidgetItem(s.get("state", "")))

            status = s.get("status", "Active")
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "Active":
                status_item.setForeground(QColor(COLORS["success"]))
            else:
                status_item.setForeground(QColor(tc("text_light")))
            self.table.setItem(i, 4, status_item)
            self.table.setRowHeight(i, 40)

    def _get_selected_site(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if 0 <= row < len(self._sites):
            return self._sites[row]
        return None

    def _add_site(self):
        dlg = SiteDialog(self)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            if not fields["name"]:
                QMessageBox.warning(self, "Validation", "Site name is required.")
                return
            username = self.app_state.get("username", "")
            sid = data_manager.create_site(fields, created_by=username)
            audit.log_event("attendance", "site_created", username,
                            details=f"Created site: {fields['name']}",
                            table_name="sites", record_id=sid)
            self.refresh()

    def _edit_site(self):
        site = self._get_selected_site()
        if not site:
            QMessageBox.information(self, "Select Site", "Please select a site to edit.")
            return

        dlg = SiteDialog(self, site)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            username = self.app_state.get("username", "")
            data_manager.update_site(site["site_id"], fields, updated_by=username)
            audit.log_event("attendance", "site_updated", username,
                            details=f"Updated site: {fields['name']}",
                            table_name="sites", record_id=site["site_id"])
            self.refresh()

    def _delete_site(self):
        site = self._get_selected_site()
        if not site:
            QMessageBox.information(self, "Select Site", "Please select a site to delete.")
            return

        if not confirm_action(self, "Delete Site",
                              f"Delete site '{site.get('name', '')}'? This cannot be undone."):
            return

        username = self.app_state.get("username", "")
        data_manager.delete_site(site["site_id"])
        audit.log_event("attendance", "site_deleted", username,
                        details=f"Deleted site: {site.get('name', '')}",
                        table_name="sites", record_id=site["site_id"])
        self.refresh()


# ════════════════════════════════════════════════════════════════════════
# Policy Settings Page
# ════════════════════════════════════════════════════════════════════════

_SETTINGS_KEY = "ats_policy_thresholds"

# Default thresholds matching policy_engine.py constants
_DEFAULT_THRESHOLDS = {
    "verbal_warning": 1.5,
    "written_warning": 6.0,
    "employment_review": 8.0,
    "termination_eligible": 10.0,
    "point_window_days": 365,
}


class PolicySettingsPage(QWidget):
    """Admin page for viewing/editing discipline policy thresholds."""

    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # Header
        title = QLabel("Policy Settings")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        desc = QLabel(
            "Configure discipline point thresholds and the rolling point window. "
            "Changes here override the built-in defaults and take effect immediately."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        layout.addWidget(desc)

        # Thresholds group
        group = QGroupBox("Discipline Thresholds")
        group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 14px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 20px; background: {tc('card')};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 6px; }}
        """)
        form = QFormLayout(group)
        form.setSpacing(14)
        form.setContentsMargins(24, 24, 24, 24)

        self.spin_verbal = QDoubleSpinBox()
        self.spin_verbal.setRange(0, 100)
        self.spin_verbal.setDecimals(1)
        self.spin_verbal.setSingleStep(0.5)
        form.addRow("Verbal Warning threshold (pts):", self.spin_verbal)

        self.spin_written = QDoubleSpinBox()
        self.spin_written.setRange(0, 100)
        self.spin_written.setDecimals(1)
        self.spin_written.setSingleStep(0.5)
        form.addRow("Written Warning threshold (pts):", self.spin_written)

        self.spin_review = QDoubleSpinBox()
        self.spin_review.setRange(0, 100)
        self.spin_review.setDecimals(1)
        self.spin_review.setSingleStep(0.5)
        form.addRow("Employment Review threshold (pts):", self.spin_review)

        self.spin_termination = QDoubleSpinBox()
        self.spin_termination.setRange(0, 100)
        self.spin_termination.setDecimals(1)
        self.spin_termination.setSingleStep(0.5)
        form.addRow("Termination Eligible threshold (pts):", self.spin_termination)

        self.spin_window = QSpinBox()
        self.spin_window.setRange(30, 730)
        self.spin_window.setSuffix(" days")
        form.addRow("Point Window (rolling):", self.spin_window)

        layout.addWidget(group)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_reset = QPushButton("Reset to Defaults")
        btn_reset.setStyleSheet(btn_style(COLORS['warning']))
        btn_reset.setFixedHeight(40)
        btn_reset.clicked.connect(self._reset_defaults)
        btn_row.addWidget(btn_reset)

        btn_save = QPushButton("Save Settings")
        btn_save.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        btn_save.setFixedHeight(40)
        btn_save.clicked.connect(self._save_settings)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)
        layout.addStretch()

    def refresh(self):
        """Load saved settings or defaults into spin boxes."""
        settings = self._load_settings()
        self.spin_verbal.setValue(settings["verbal_warning"])
        self.spin_written.setValue(settings["written_warning"])
        self.spin_review.setValue(settings["employment_review"])
        self.spin_termination.setValue(settings["termination_eligible"])
        self.spin_window.setValue(int(settings["point_window_days"]))

    def _load_settings(self) -> dict:
        raw = data_manager.get_setting(_SETTINGS_KEY)
        if raw:
            try:
                saved = json.loads(raw)
                # Merge with defaults to handle missing keys
                merged = dict(_DEFAULT_THRESHOLDS)
                merged.update(saved)
                return merged
            except (json.JSONDecodeError, TypeError):
                pass
        return dict(_DEFAULT_THRESHOLDS)

    def _save_settings(self):
        settings = {
            "verbal_warning": self.spin_verbal.value(),
            "written_warning": self.spin_written.value(),
            "employment_review": self.spin_review.value(),
            "termination_eligible": self.spin_termination.value(),
            "point_window_days": self.spin_window.value(),
        }
        data_manager.save_setting(_SETTINGS_KEY, json.dumps(settings))

        # Apply overrides to policy_engine module-level constants
        _apply_policy_overrides(settings)

        username = self.app_state.get("username", "")
        audit.log_event(
            "attendance", "policy_settings_updated", username,
            details=f"Updated policy thresholds: {settings}",
        )
        QMessageBox.information(self, "Saved", "Policy settings saved and applied.")

    def _reset_defaults(self):
        if not confirm_action(self, "Reset Defaults",
                              "Reset all thresholds to factory defaults?"):
            return
        self.spin_verbal.setValue(_DEFAULT_THRESHOLDS["verbal_warning"])
        self.spin_written.setValue(_DEFAULT_THRESHOLDS["written_warning"])
        self.spin_review.setValue(_DEFAULT_THRESHOLDS["employment_review"])
        self.spin_termination.setValue(_DEFAULT_THRESHOLDS["termination_eligible"])
        self.spin_window.setValue(int(_DEFAULT_THRESHOLDS["point_window_days"]))


def _apply_policy_overrides(settings: dict):
    """Push threshold overrides into the policy_engine module constants."""
    from src.modules.attendance import policy_engine

    policy_engine.THRESHOLDS = [
        (settings.get("verbal_warning", 1.5), "verbal_warning"),
        (settings.get("written_warning", 6.0), "written_warning"),
        (settings.get("employment_review", 8.0), "employment_review"),
        (settings.get("termination_eligible", 10.0), "termination_eligible"),
    ]
    policy_engine.POINT_WINDOW_DAYS = int(settings.get("point_window_days", 365))
    policy_engine.REVIEW_TRIGGER_POINTS = settings.get("employment_review", 8.0)
    policy_engine.TERMINATION_POINTS = settings.get("termination_eligible", 10.0)


def load_policy_overrides_on_startup():
    """Called at module init to apply any saved policy overrides."""
    raw = data_manager.get_setting(_SETTINGS_KEY)
    if raw:
        try:
            settings = json.loads(raw)
            _apply_policy_overrides(settings)
        except (json.JSONDecodeError, TypeError):
            pass
