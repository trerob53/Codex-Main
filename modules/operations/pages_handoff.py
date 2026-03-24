"""
Cerasus Hub -- Operations Module: Shift Handoff Notes Page
Allows officers/supervisors to log and acknowledge shift handoff notes
tied to a site and date.
"""

from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QTextEdit, QScrollArea, QFrame,
    QDialog, QFormLayout, QDialogButtonBox, QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont

from src.config import COLORS, build_dialog_stylesheet, tc, _is_dark, btn_style
from src.modules.operations import data_manager


# ════════════════════════════════════════════════════════════════════════
# New Note Dialog
# ════════════════════════════════════════════════════════════════════════

class NewNoteDialog(QDialog):
    """Dialog for creating a new shift handoff note."""

    def __init__(self, parent=None, site="", app_state=None):
        super().__init__(parent)
        self.setWindowTitle("New Handoff Note")
        self.setMinimumWidth(520)
        self.setMinimumHeight(380)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._site = site
        self.app_state = app_state or {}
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Site (pre-filled, read-only)
        self.cmb_site = QComboBox()
        sites = data_manager.get_active_sites()
        site_names = [s.get("name", "") for s in sites if s.get("name")]
        self.cmb_site.addItems(site_names)
        if self._site and self._site in site_names:
            self.cmb_site.setCurrentText(self._site)
        layout.addRow("Site:", self.cmb_site)

        # Shift type
        self.cmb_shift = QComboBox()
        self.cmb_shift.addItems(["Day", "Swing", "Night", "Other"])
        layout.addRow("Shift Type:", self.cmb_shift)

        # Priority
        self.cmb_priority = QComboBox()
        self.cmb_priority.addItems(["Normal", "Important", "Critical"])
        layout.addRow("Priority:", self.cmb_priority)

        # Content
        self.txt_content = QTextEdit()
        self.txt_content.setPlaceholderText("Enter handoff notes here...")
        self.txt_content.setMinimumHeight(140)
        layout.addRow("Notes:", self.txt_content)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _on_save(self):
        content = self.txt_content.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "Validation", "Note content cannot be empty.")
            return
        site = self.cmb_site.currentText().strip()
        if not site:
            QMessageBox.warning(self, "Validation", "Please select a site.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "site": self.cmb_site.currentText().strip(),
            "shift_type": self.cmb_shift.currentText(),
            "priority": self.cmb_priority.currentText().lower(),
            "content": self.txt_content.toPlainText().strip(),
        }


# ════════════════════════════════════════════════════════════════════════
# Note Card Widget
# ════════════════════════════════════════════════════════════════════════

class NoteCard(QFrame):
    """A single handoff note displayed as a styled card."""

    def __init__(self, note: dict, app_state: dict, on_acknowledge=None, parent=None):
        super().__init__(parent)
        self.note = note
        self.app_state = app_state
        self._on_acknowledge = on_acknowledge
        self._build()

    def _build(self):
        priority = self.note.get("priority", "normal").lower()
        acknowledged = bool(self.note.get("acknowledged_by", ""))

        # Card border color based on priority and ack status
        if not acknowledged:
            if priority == "critical":
                border_color = tc("danger")
                bg_tint = tc("danger_light")
            elif priority == "important":
                border_color = tc("warning")
                bg_tint = tc("warning_light")
            else:
                border_color = tc("border")
                bg_tint = tc("card")
        else:
            border_color = tc("border")
            bg_tint = tc("card")

        border_width = "2px" if not acknowledged else "1px"

        self.setStyleSheet(f"""
            NoteCard {{
                background: {bg_tint};
                border: {border_width} solid {border_color};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # ── Header row: priority badge + author + timestamp ──
        header = QHBoxLayout()
        header.setSpacing(10)

        # Priority badge
        badge_colors = {
            "normal": (tc("info_light"), tc("text")),
            "important": (tc("warning"), "#FFFFFF"),
            "critical": (tc("danger"), "#FFFFFF"),
        }
        badge_bg, badge_fg = badge_colors.get(priority, badge_colors["normal"])

        badge = QLabel(priority.upper())
        badge.setFixedHeight(26)
        badge.setStyleSheet(f"""
            QLabel {{
                background: {badge_bg};
                color: {badge_fg};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 2px 10px;
                border-radius: 4px;
                border: none;
            }}
        """)
        header.addWidget(badge)

        # Acknowledgment status indicator
        if acknowledged:
            ack_indicator = QLabel("\u2705 Acknowledged")
            ack_indicator.setFixedHeight(26)
            ack_indicator.setStyleSheet(f"""
                QLabel {{
                    background: {tc('success')};
                    color: #FFFFFF;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 2px 10px;
                    border-radius: 4px;
                    border: none;
                }}
            """)
            header.addWidget(ack_indicator)
        else:
            pending_indicator = QLabel("\u23F3 Pending")
            pending_indicator.setFixedHeight(26)
            pending_indicator.setStyleSheet(f"""
                QLabel {{
                    background: {tc('warning')};
                    color: #FFFFFF;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 2px 10px;
                    border-radius: 4px;
                    border: none;
                }}
            """)
            header.addWidget(pending_indicator)

        # Shift type label
        shift_type = self.note.get("shift_type", "")
        if shift_type:
            shift_lbl = QLabel(f"[{shift_type}]")
            shift_lbl.setStyleSheet(f"""
                QLabel {{
                    color: {tc('text_light')};
                    font-size: 12px;
                    font-weight: 600;
                    border: none;
                    background: transparent;
                }}
            """)
            header.addWidget(shift_lbl)

        # Author
        author_lbl = QLabel(self.note.get("author", "Unknown"))
        author_lbl.setStyleSheet(f"""
            QLabel {{
                color: {tc('text')};
                font-size: 13px;
                font-weight: 600;
                border: none;
                background: transparent;
            }}
        """)
        header.addWidget(author_lbl)

        # Timestamp
        created = self.note.get("created_at", "")
        display_time = ""
        if created:
            try:
                dt = datetime.fromisoformat(created)
                display_time = dt.strftime("%I:%M %p")
            except (ValueError, TypeError):
                display_time = created[:16]

        time_lbl = QLabel(display_time)
        time_lbl.setStyleSheet(f"""
            QLabel {{
                color: {tc('text_light')};
                font-size: 12px;
                border: none;
                background: transparent;
            }}
        """)
        header.addWidget(time_lbl)
        header.addStretch()

        layout.addLayout(header)

        # ── Content ──
        content_lbl = QLabel(self.note.get("content", ""))
        content_lbl.setWordWrap(True)
        content_lbl.setStyleSheet(f"""
            QLabel {{
                color: {tc('text')};
                font-size: 14px;
                line-height: 1.5;
                padding: 4px 0;
                border: none;
                background: transparent;
            }}
        """)
        layout.addWidget(content_lbl)

        # ── Footer: acknowledge status / button ──
        footer = QHBoxLayout()
        footer.setSpacing(8)

        if acknowledged:
            ack_by = self.note.get("acknowledged_by", "")
            ack_at = self.note.get("acknowledged_at", "")
            ack_time = ""
            if ack_at:
                try:
                    dt = datetime.fromisoformat(ack_at)
                    ack_time = dt.strftime("%m/%d %I:%M %p")
                except (ValueError, TypeError):
                    ack_time = ack_at[:16]
            ack_lbl = QLabel(f"Acknowledged by {ack_by} at {ack_time}")
            ack_lbl.setStyleSheet(f"""
                QLabel {{
                    color: {tc('success')};
                    font-size: 12px;
                    font-style: italic;
                    border: none;
                    background: transparent;
                }}
            """)
            footer.addWidget(ack_lbl)
        else:
            ack_btn = QPushButton("Acknowledge")
            ack_btn.setCursor(Qt.PointingHandCursor)
            ack_btn.setFixedHeight(30)
            ack_btn.setStyleSheet(btn_style(tc("primary_light"), "white", tc("primary_mid")))
            ack_btn.clicked.connect(self._handle_acknowledge)
            footer.addWidget(ack_btn)

        footer.addStretch()
        layout.addLayout(footer)

    def _handle_acknowledge(self):
        if self._on_acknowledge:
            self._on_acknowledge(self.note.get("note_id", ""))


# ════════════════════════════════════════════════════════════════════════
# Handoff Notes Page
# ════════════════════════════════════════════════════════════════════════

class HandoffNotesPage(QWidget):
    """Shift handoff notes management page."""

    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()
        self._load_notes()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── Title ──
        title = QLabel("Shift Handoff Notes")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        root.addWidget(title)

        subtitle = QLabel("Log and review shift handoff notes by site and date")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; background: transparent;")
        root.addWidget(subtitle)

        # ── Top bar: site selector + date + new note button ──
        bar = QHBoxLayout()
        bar.setSpacing(12)

        # Site selector
        site_label = QLabel("Site:")
        site_label.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 14px; background: transparent;")
        bar.addWidget(site_label)

        self.cmb_site = QComboBox()
        self.cmb_site.setMinimumWidth(200)
        sites = data_manager.get_active_sites()
        self._site_names = [s.get("name", "") for s in sites if s.get("name")]
        self.cmb_site.addItems(["All Sites"] + self._site_names)

        # Default to user's assigned site if available
        user = self.app_state.get("user", {})
        user_sites = user.get("assigned_sites", "")
        if user_sites and isinstance(user_sites, str):
            try:
                import json
                user_site_list = json.loads(user_sites)
                if user_site_list and user_site_list[0] in self._site_names:
                    self.cmb_site.setCurrentText(user_site_list[0])
            except (ValueError, TypeError):
                pass

        self.cmb_site.currentIndexChanged.connect(self._load_notes)
        bar.addWidget(self.cmb_site)

        # Date selector
        date_label = QLabel("Date:")
        date_label.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 14px; background: transparent;")
        bar.addWidget(date_label)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.dateChanged.connect(self._load_notes)
        bar.addWidget(self.date_edit)

        bar.addStretch()

        # New Note button
        self.btn_new = QPushButton("+ New Note")
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.setFixedHeight(38)
        self.btn_new.setStyleSheet(btn_style(tc("accent"), "white", tc("accent_hover")))
        self.btn_new.clicked.connect(self._on_new_note)
        bar.addWidget(self.btn_new)

        root.addLayout(bar)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {tc('border')};")
        root.addWidget(sep)

        # ── Notes feed (scrollable) ──
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"QScrollArea {{ background: {tc('bg')}; border: none; }}")

        self.feed_widget = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_widget)
        self.feed_layout.setContentsMargins(0, 0, 0, 0)
        self.feed_layout.setSpacing(12)
        self.feed_layout.addStretch()

        self.scroll.setWidget(self.feed_widget)
        root.addWidget(self.scroll, 1)

    def _get_selected_site(self) -> str:
        text = self.cmb_site.currentText()
        return "" if text == "All Sites" else text

    def _get_selected_date(self) -> str:
        return self.date_edit.date().toString("yyyy-MM-dd")

    def _load_notes(self):
        """Reload notes for the current site + date selection."""
        # Clear existing cards
        while self.feed_layout.count() > 1:
            item = self.feed_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        site = self._get_selected_site()
        date = self._get_selected_date()

        if site:
            notes = data_manager.get_notes_for_site_date(site, date)
        else:
            # All sites for the date — query each site
            notes = []
            for sn in self._site_names:
                notes.extend(data_manager.get_notes_for_site_date(sn, date))
            # Sort newest first
            notes.sort(key=lambda n: n.get("created_at", ""), reverse=True)

        if not notes:
            empty_lbl = QLabel("No handoff notes for this site and date.")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet(f"""
                color: {tc('text_light')};
                font-size: 15px;
                padding: 40px;
                background: transparent;
            """)
            self.feed_layout.insertWidget(0, empty_lbl)
        else:
            for note in notes:
                card = NoteCard(note, self.app_state, on_acknowledge=self._on_acknowledge)
                self.feed_layout.insertWidget(self.feed_layout.count() - 1, card)

    def _on_new_note(self):
        site = self._get_selected_site()
        dlg = NewNoteDialog(self, site=site, app_state=self.app_state)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            data["shift_date"] = self._get_selected_date()
            username = self.app_state.get("user", {}).get("display_name", "") or \
                       self.app_state.get("user", {}).get("username", "Unknown")
            data_manager.create_handoff_note(data, author=username)
            self._load_notes()

    def _on_acknowledge(self, note_id: str):
        username = self.app_state.get("user", {}).get("display_name", "") or \
                   self.app_state.get("user", {}).get("username", "Unknown")
        data_manager.acknowledge_note(note_id, username)
        self._load_notes()

    def refresh(self):
        """Called externally to refresh the page data."""
        self._load_notes()
