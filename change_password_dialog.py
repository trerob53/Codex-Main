"""
Cerasus Hub -- Change Password Dialog
Self-service password change for authenticated users.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QMessageBox,
)
from PySide6.QtCore import Qt

from src.config import COLORS, tc, _is_dark, build_dialog_stylesheet
from src import auth, audit


class ChangePasswordDialog(QDialog):
    """Self-service password change dialog."""

    def __init__(self, username: str, parent=None):
        super().__init__(parent)
        self.username = username
        self.setWindowTitle("Change Password")
        self.setFixedWidth(420)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Change Password")
        title.setStyleSheet(f"""
            font-size: 18px; font-weight: 700;
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
        """)
        layout.addWidget(title)

        # Current password
        lbl_current = QLabel("Current Password")
        lbl_current.setStyleSheet(f"font-size: 13px; color: {tc('text_light')};")
        layout.addWidget(lbl_current)
        self.txt_current = QLineEdit()
        self.txt_current.setEchoMode(QLineEdit.Password)
        self.txt_current.setPlaceholderText("Enter current password")
        layout.addWidget(self.txt_current)

        # New password
        lbl_new = QLabel("New Password")
        lbl_new.setStyleSheet(f"font-size: 13px; color: {tc('text_light')};")
        layout.addWidget(lbl_new)
        self.txt_new = QLineEdit()
        self.txt_new.setEchoMode(QLineEdit.Password)
        self.txt_new.setPlaceholderText("Enter new password")
        layout.addWidget(self.txt_new)

        # Confirm new password
        lbl_confirm = QLabel("Confirm New Password")
        lbl_confirm.setStyleSheet(f"font-size: 13px; color: {tc('text_light')};")
        layout.addWidget(lbl_confirm)
        self.txt_confirm = QLineEdit()
        self.txt_confirm.setEchoMode(QLineEdit.Password)
        self.txt_confirm.setPlaceholderText("Re-enter new password")
        layout.addWidget(self.txt_confirm)

        # Requirements label
        req_label = QLabel("Minimum 6 characters")
        req_label.setStyleSheet(f"""
            font-size: 12px; color: {tc('text_light')};
            font-style: italic; padding: 2px 0;
        """)
        layout.addWidget(req_label)

        # Error label (hidden by default)
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"""
            font-size: 13px; color: {COLORS['danger']};
            font-weight: 600; padding: 2px 0;
        """)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        # Buttons
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(38)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 500;
                border: 2px solid {tc('border')};
                border-radius: 6px; padding: 0 20px;
            }}
            QPushButton:hover {{ border-color: {tc('text_light')}; }}
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_lay.addWidget(self.btn_cancel)

        btn_lay.addSpacing(8)

        self.btn_change = QPushButton("Change Password")
        self.btn_change.setFixedHeight(38)
        self.btn_change.setCursor(Qt.PointingHandCursor)
        self.btn_change.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['primary']};
                color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 600;
                border: none; border-radius: 6px;
                padding: 0 24px;
            }}
            QPushButton:hover {{ background: {COLORS['primary_light']}; }}
        """)
        self.btn_change.clicked.connect(self._on_change)
        btn_lay.addWidget(self.btn_change)

        layout.addLayout(btn_lay)

    def _on_change(self):
        current_pw = self.txt_current.text()
        new_pw = self.txt_new.text()
        confirm_pw = self.txt_confirm.text()

        # Validate current password
        if not auth.verify_password(self.username, current_pw):
            self.lbl_error.setText("Current password is incorrect.")
            self.lbl_error.show()
            return

        # Validate new password length
        if len(new_pw) < 6:
            self.lbl_error.setText("New password must be at least 6 characters.")
            self.lbl_error.show()
            return

        # Validate match
        if new_pw != confirm_pw:
            self.lbl_error.setText("New passwords do not match.")
            self.lbl_error.show()
            return

        # Validate different from current
        if current_pw == new_pw:
            self.lbl_error.setText("New password must be different from current password.")
            self.lbl_error.show()
            return

        # Update password
        ok = auth.update_user(self.username, new_password=new_pw)
        if not ok:
            self.lbl_error.setText("Failed to update password. Please try again.")
            self.lbl_error.show()
            return

        # Audit log
        audit.log_event("hub", "password_change", self.username,
                        f"Password changed for user {self.username}")

        QMessageBox.information(self, "Success", "Your password has been changed successfully.")
        self.accept()
