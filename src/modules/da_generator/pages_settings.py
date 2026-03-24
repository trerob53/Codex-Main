"""
Cerasus Hub -- DA Generator Module: Settings Page
Default settings and CEIS engine info.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QComboBox, QFormLayout, QMessageBox, QGroupBox, QTextBrowser,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.config import COLORS, tc, btn_style, _is_dark
from src.shared_data import get_all_sites
from src.modules.da_generator import data_manager
from src import audit


class DASettingsPage(QWidget):
    """Configuration page for the DA Generator module."""

    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    # ── Layout ────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(20)

        # Page title
        title = QLabel("DA Generator Configuration")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; background: transparent; border: none;")
        root.addWidget(title)

        # ── Card 1: Default Settings ──────────────────────────────────
        defaults_card = self._make_card()
        defaults_lay = QVBoxLayout(defaults_card)
        defaults_lay.setContentsMargins(20, 18, 20, 18)
        defaults_lay.setSpacing(12)

        defaults_title = QLabel("Default Settings")
        defaults_title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        defaults_title.setStyleSheet(f"color: {tc('text')}; background: transparent; border: none;")
        defaults_lay.addWidget(defaults_title)

        defaults_form = QFormLayout()
        defaults_form.setSpacing(8)
        defaults_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.default_director = QLineEdit()
        self.default_director.setPlaceholderText("e.g. John Smith")
        self.default_director.setMinimumWidth(300)
        lbl_director = QLabel("Default Security Director:")
        lbl_director.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 14px; background: transparent; border: none;")
        defaults_form.addRow(lbl_director, self.default_director)

        self.default_site = QComboBox()
        self.default_site.addItem("")  # blank option
        try:
            sites = get_all_sites(status_filter="Active")
            for s in sites:
                self.default_site.addItem(s.get("name", ""))
        except Exception:
            pass
        self.default_site.setMinimumWidth(300)
        lbl_site = QLabel("Default Site:")
        lbl_site.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 14px; background: transparent; border: none;")
        defaults_form.addRow(lbl_site, self.default_site)

        defaults_lay.addLayout(defaults_form)

        save_defaults_row = QHBoxLayout()
        self.btn_save_defaults = QPushButton("Save Defaults")
        self.btn_save_defaults.setCursor(Qt.PointingHandCursor)
        self.btn_save_defaults.setStyleSheet(btn_style(COLORS["success"]))
        self.btn_save_defaults.clicked.connect(self._save_defaults)
        save_defaults_row.addWidget(self.btn_save_defaults)
        save_defaults_row.addStretch()

        self.defaults_status = QLabel("")
        self.defaults_status.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; background: transparent; border: none;")
        save_defaults_row.addWidget(self.defaults_status)

        defaults_lay.addLayout(save_defaults_row)

        root.addWidget(defaults_card)

        # ── Card 2: About CEIS Engine ─────────────────────────────────
        about_card = self._make_card()
        about_lay = QVBoxLayout(about_card)
        about_lay.setContentsMargins(20, 18, 20, 18)
        about_lay.setSpacing(12)

        about_title = QLabel("About CEIS Engine")
        about_title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        about_title.setStyleSheet(f"color: {tc('text')}; background: transparent; border: none;")
        about_lay.addWidget(about_title)

        about_text = QTextBrowser()
        about_text.setOpenExternalLinks(False)
        about_text.setMaximumHeight(220)
        _text_color = tc('text')
        _muted_color = tc('text_light')
        _accent = COLORS['accent']
        about_text.setStyleSheet(f"""
            QTextBrowser {{
                background: transparent; border: none;
                color: {_text_color}; font-size: 13px;
            }}
        """)
        about_text.setHtml(f"""
        <div style="color: {_text_color}; font-family: 'Segoe UI'; font-size: 13px; line-height: 1.6;">
            <p><b style="color: {_accent};">CEIS Discipline Engine v5.6</b></p>
            <p>The Cerasus Employee Infraction System (CEIS) uses rule-based analysis to generate
            disciplinary action documents following Cerasus Security's progressive discipline framework.</p>

            <p><b>Policy Hierarchy:</b></p>
            <ul>
                <li>Cerasus Security Employee Handbook (primary authority)</li>
                <li>Site-specific Post Orders (supplemental)</li>
                <li>Client-specific requirements</li>
                <li>State/federal regulatory requirements</li>
            </ul>

            <p><b>Key Handbook Sections:</b></p>
            <ul>
                <li>Section 4 &mdash; Code of Conduct &amp; Professional Standards</li>
                <li>Section 5 &mdash; Attendance &amp; Scheduling Policies</li>
                <li>Section 6 &mdash; Use of Force Policy</li>
                <li>Section 7 &mdash; Progressive Discipline Framework</li>
                <li>Section 8 &mdash; Reporting &amp; Documentation Requirements</li>
            </ul>

            <p style="color: {_muted_color};">The engine analyzes incident details, prior discipline history,
            and coaching records to recommend an appropriate discipline level in accordance with
            the progressive discipline framework.</p>
        </div>
        """)
        about_lay.addWidget(about_text)

        root.addWidget(about_card)

        # Spacer at bottom
        root.addStretch()

        # Load saved settings
        self._load_settings()

    # ── Card helper ───────────────────────────────────────────────────
    @staticmethod
    def _make_card() -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border-radius: 10px;
                border: 1px solid {tc('border')};
            }}
        """)
        return card

    # ── Load / save ───────────────────────────────────────────────────
    def refresh(self):
        self._load_settings()

    def _load_settings(self):
        # Default director
        director = data_manager.get_setting("da_default_director")
        if director:
            self.default_director.setText(director)

        # Default site
        site = data_manager.get_setting("da_default_site")
        if site:
            idx = self.default_site.findText(site)
            if idx >= 0:
                self.default_site.setCurrentIndex(idx)

    def _save_defaults(self):
        director = self.default_director.text().strip()
        site = self.default_site.currentText().strip()

        data_manager.save_setting("da_default_director", director)
        data_manager.save_setting("da_default_site", site)

        username = getattr(self.app_state, "username", "")
        audit.log_event(
            module_name="da_generator",
            event_type="config_change",
            username=username,
            details=f"Updated DA defaults: director='{director}', site='{site}'",
            table_name="settings",
            record_id="da_defaults",
            action="update",
        )

        self.defaults_status.setText("Defaults saved")
        self.defaults_status.setStyleSheet(f"color: {COLORS['success']}; font-size: 13px; background: transparent; border: none;")
