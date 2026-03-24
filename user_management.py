"""
Cerasus Hub — User Site Access Management Dialog
Admin dialog for assigning site-based access to users.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QCheckBox, QGroupBox,
    QScrollArea, QWidget, QFrame, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.config import COLORS, tc, _is_dark, btn_style, build_dialog_stylesheet, ROLE_ADMIN
from src.auth import get_all_users, get_user_sites, set_user_sites
from src.shared_data import get_site_names


class UserSiteAccessDialog(QDialog):
    """Admin dialog for managing which sites each user can access."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage User Site Access")
        self.setMinimumSize(720, 520)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._current_username = ""
        self._site_checkboxes = []
        self._build()
        self._load_users()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── Left panel: user list ──
        left_panel = QVBoxLayout()
        left_panel.setSpacing(8)

        users_label = QLabel("USERS")
        users_label.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; font-weight: 600;
            letter-spacing: 2px;
        """)
        left_panel.addWidget(users_label)

        self.user_list = QListWidget()
        self.user_list.setFixedWidth(220)
        self.user_list.setStyleSheet(f"""
            QListWidget {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 6px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                color: {tc('text')};
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-bottom: 1px solid {tc('border')};
            }}
            QListWidget::item:selected {{
                background: {COLORS['accent']};
                color: white;
            }}
            QListWidget::item:hover {{
                background: {tc('border')};
            }}
        """)
        self.user_list.currentRowChanged.connect(self._on_user_selected)
        left_panel.addWidget(self.user_list)

        layout.addLayout(left_panel)

        # ── Right panel: site assignment ──
        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)

        self.user_info_label = QLabel("Select a user to manage site access")
        self.user_info_label.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700;
        """)
        right_panel.addWidget(self.user_info_label)

        self.role_label = QLabel("")
        self.role_label.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px;
        """)
        right_panel.addWidget(self.role_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {tc('border')};")
        sep.setFixedHeight(1)
        right_panel.addWidget(sep)

        # "All Sites" checkbox
        self.all_sites_cb = QCheckBox("All Sites (Unrestricted)")
        self.all_sites_cb.setStyleSheet(f"""
            QCheckBox {{
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 600;
                color: {tc('text')};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 20px; height: 20px;
                border: 2px solid {tc('border')};
                border-radius: 4px;
                background: {tc('card')};
            }}
            QCheckBox::indicator:checked {{
                background: {COLORS['accent']};
                border-color: {COLORS['accent']};
            }}
        """)
        self.all_sites_cb.toggled.connect(self._on_all_sites_toggled)
        right_panel.addWidget(self.all_sites_cb)

        # Site checkboxes in a scrollable area
        sites_group = QGroupBox("Assigned Sites")
        sites_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 14px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 10px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 8px;
            }}
        """)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {tc('card')}; border: none; }}")

        self.sites_container = QWidget()
        self.sites_container.setStyleSheet(f"background: {tc('card')};")
        self.sites_layout = QVBoxLayout(self.sites_container)
        self.sites_layout.setContentsMargins(12, 8, 12, 8)
        self.sites_layout.setSpacing(6)

        scroll.setWidget(self.sites_container)

        group_layout = QVBoxLayout(sites_group)
        group_layout.setContentsMargins(4, 4, 4, 4)
        group_layout.addWidget(scroll)

        right_panel.addWidget(sites_group)

        # Save / Cancel buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_save = QPushButton("Save")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setFixedHeight(40)
        btn_save.setMinimumWidth(100)
        btn_save.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS.get('accent_hover', COLORS['accent'])))
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFixedHeight(40)
        btn_cancel.setMinimumWidth(100)
        btn_cancel.setStyleSheet(btn_style(tc('border'), fg=tc('text')))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        right_panel.addLayout(btn_row)

        layout.addLayout(right_panel, 1)

    def _load_users(self):
        """Populate the user list."""
        self.user_list.clear()
        users = get_all_users()
        for u in users:
            display = u.get("display_name", "") or u.get("username", "")
            username = u.get("username", "")
            role = u.get("role", "")
            item = QListWidgetItem(f"{display}  ({role})")
            item.setData(Qt.UserRole, username)
            item.setData(Qt.UserRole + 1, role)
            item.setData(Qt.UserRole + 2, display)
            self.user_list.addItem(item)

    def _on_user_selected(self, row):
        """When a user is selected, load their site assignments."""
        if row < 0:
            return

        item = self.user_list.item(row)
        username = item.data(Qt.UserRole)
        role = item.data(Qt.UserRole + 1)
        display = item.data(Qt.UserRole + 2)
        self._current_username = username

        self.user_info_label.setText(f"{display}")
        role_text = f"Username: {username}  |  Role: {role.upper()}"
        if role == ROLE_ADMIN:
            role_text += "  (Admins always see all sites)"
        self.role_label.setText(role_text)

        # Load sites
        assigned = get_user_sites(username)

        # Rebuild site checkboxes
        self._rebuild_site_checkboxes(assigned)

        # If admin role, show all-sites as checked and disable controls
        if role == ROLE_ADMIN:
            self.all_sites_cb.blockSignals(True)
            self.all_sites_cb.setChecked(True)
            self.all_sites_cb.setEnabled(False)
            self.all_sites_cb.blockSignals(False)
            for cb in self._site_checkboxes:
                cb.setEnabled(False)
                cb.setChecked(False)
        else:
            self.all_sites_cb.setEnabled(True)
            if not assigned:
                self.all_sites_cb.blockSignals(True)
                self.all_sites_cb.setChecked(True)
                self.all_sites_cb.blockSignals(False)
                for cb in self._site_checkboxes:
                    cb.setEnabled(False)
                    cb.setChecked(False)
            else:
                self.all_sites_cb.blockSignals(True)
                self.all_sites_cb.setChecked(False)
                self.all_sites_cb.blockSignals(False)
                for cb in self._site_checkboxes:
                    cb.setEnabled(True)

    def _rebuild_site_checkboxes(self, assigned: list):
        """Create a checkbox for each active site."""
        # Clear existing
        self._site_checkboxes.clear()
        while self.sites_layout.count():
            child = self.sites_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        sites = get_site_names()
        cb_style = f"""
            QCheckBox {{
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; color: {tc('text')};
                spacing: 8px; padding: 4px 0;
            }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border: 2px solid {tc('border')};
                border-radius: 3px;
                background: {tc('card')};
            }}
            QCheckBox::indicator:checked {{
                background: {COLORS['accent']};
                border-color: {COLORS['accent']};
            }}
        """

        for s in sites:
            name = s.get("name", "")
            cb = QCheckBox(name)
            cb.setStyleSheet(cb_style)
            cb.setChecked(name in assigned)
            self._site_checkboxes.append(cb)
            self.sites_layout.addWidget(cb)

        self.sites_layout.addStretch()

    def _on_all_sites_toggled(self, checked):
        """When 'All Sites' is toggled, disable/enable individual site checkboxes."""
        for cb in self._site_checkboxes:
            cb.setEnabled(not checked)
            if checked:
                cb.setChecked(False)

    def _save(self):
        """Save the current user's site assignments."""
        if not self._current_username:
            QMessageBox.information(self, "No User", "Please select a user first.")
            return

        # Check role -- admin always unrestricted
        item = self.user_list.currentItem()
        if item and item.data(Qt.UserRole + 1) == ROLE_ADMIN:
            set_user_sites(self._current_username, [])
            QMessageBox.information(
                self, "Saved",
                f"Admin users always have unrestricted site access."
            )
            return

        if self.all_sites_cb.isChecked():
            # Unrestricted
            set_user_sites(self._current_username, [])
            QMessageBox.information(
                self, "Saved",
                f"User '{self._current_username}' now has unrestricted site access."
            )
        else:
            selected_sites = [cb.text() for cb in self._site_checkboxes if cb.isChecked()]
            if not selected_sites:
                reply = QMessageBox.question(
                    self, "No Sites Selected",
                    "No sites are selected. This will give the user unrestricted access to all sites.\n\n"
                    "To restrict access, select specific sites.\n\n"
                    "Save with unrestricted access?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return
                set_user_sites(self._current_username, [])
            else:
                set_user_sites(self._current_username, selected_sites)
                QMessageBox.information(
                    self, "Saved",
                    f"User '{self._current_username}' now has access to {len(selected_sites)} site(s):\n"
                    + "\n".join(f"  - {s}" for s in selected_sites)
                )
