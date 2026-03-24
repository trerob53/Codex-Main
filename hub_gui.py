"""
Cerasus Hub -- Main GUI
LoginScreen -> ModulePickerScreen -> ModuleShellWidget with persistent TopBar.
"""

from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QStackedWidget, QFrame,
    QSizePolicy, QScrollArea, QSpacerItem, QGridLayout, QMessageBox,
    QDialog, QDialogButtonBox, QGroupBox, QCheckBox, QComboBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QShortcut, QKeySequence

from src.config import (
    APP_NAME, APP_VERSION, COLORS, DARK_COLORS,
    ROLE_ADMIN, ROLE_VIEWER, READ_ONLY_REFRESH_MS,
    tc, _is_dark, set_dark_mode, btn_style,
    build_global_style, build_dialog_stylesheet,
    load_all_settings, save_setting, get_setting, load_setting,
)
from src import auth, audit, session_manager
from src.modules import discover_modules
from src.shared_widgets import SidebarButton, SidebarSectionLabel, BreadcrumbBar, AnimatedStackedWidget, apply_card_shadow
from src.web_companion import start_companion_server, stop_companion_server, get_companion_url
from src.hub_analytics import HubAnalyticsPage
from src.hub_people import HubPeoplePage
from src.pages_activity_feed import ActivityFeedPage
from src.pages_task_queue import TaskQueuePage
from src.change_password_dialog import ChangePasswordDialog
from src.announcements import AnnouncementsPage, get_unread_count


# --------------------------------------------------------------------------
# Helper: create a small colored dot QFrame instead of unicode symbols
# --------------------------------------------------------------------------

def _make_dot(color, size=8):
    """Return a small rounded QFrame used as a status dot."""
    dot = QFrame()
    dot.setFixedSize(size, size)
    dot.setStyleSheet(f"""
        background: {color};
        border-radius: {size // 2}px;
        border: none;
    """)
    return dot


# --------------------------------------------------------------------------
# Login Screen
# --------------------------------------------------------------------------

class LoginScreen(QWidget):
    def __init__(self, on_login_success):
        super().__init__()
        self.on_login_success = on_login_success
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {COLORS['primary']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addStretch(2)

        center_row = QHBoxLayout()
        center_row.setAlignment(Qt.AlignCenter)

        # Login card
        card = QFrame()
        card.setFixedSize(420, 480)
        card.setObjectName("loginCard")
        card.setStyleSheet("""
            QFrame#loginCard {
                background: white;
                border-radius: 8px;
            }
        """)

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(40, 36, 40, 36)
        card_lay.setSpacing(0)

        # Cerasus wordmark (lowercase, wide letter-spacing)
        wordmark = QLabel("cerasus")
        wordmark.setAlignment(Qt.AlignCenter)
        wordmark.setStyleSheet(f"""
            color: {COLORS['accent']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 36px; font-weight: 300;
            letter-spacing: 10px;
            background: transparent;
        """)
        card_lay.addWidget(wordmark)

        card_lay.addSpacing(4)

        subtitle = QLabel("MANAGEMENT HUB")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"""
            color: {COLORS['rose']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 12px; font-weight: 400;
            letter-spacing: 4px;
            background: transparent;
        """)
        card_lay.addWidget(subtitle)

        card_lay.addSpacing(32)

        # Username
        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Username")
        self.txt_username.setFixedHeight(44)
        self.txt_username.setStyleSheet(f"""
            QLineEdit {{
                background: #F9FAFB; border: none;
                border-bottom: 2px solid #E5E7EB;
                border-radius: 0; padding: 0 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 300;
                letter-spacing: 1px; color: #1F2937;
            }}
            QLineEdit:focus {{ border-bottom-color: {COLORS['accent']}; }}
        """)
        card_lay.addWidget(self.txt_username)

        card_lay.addSpacing(20)

        # Password
        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Password")
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setFixedHeight(44)
        self.txt_password.setStyleSheet(f"""
            QLineEdit {{
                background: #F9FAFB; border: none;
                border-bottom: 2px solid #E5E7EB;
                border-radius: 0; padding: 0 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 300;
                letter-spacing: 1px; color: #1F2937;
            }}
            QLineEdit:focus {{ border-bottom-color: {COLORS['accent']}; }}
        """)
        self.txt_password.returnPressed.connect(self._do_login)
        card_lay.addWidget(self.txt_password)

        # Error label
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"""
            color: {COLORS['accent']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; background: transparent;
        """)
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setMinimumHeight(32)
        card_lay.addWidget(self.lbl_error)

        # Sign in button (rounded pill)
        sign_btn = QPushButton("Sign In")
        sign_btn.setCursor(Qt.PointingHandCursor)
        sign_btn.setFixedHeight(48)
        sign_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 400;
                letter-spacing: 2px;
                border-radius: 24px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        sign_btn.clicked.connect(self._do_login)
        card_lay.addWidget(sign_btn)

        card_lay.addStretch()

        # Version footer
        ver = QLabel(f"v{APP_VERSION}")
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet("color: #D1D5DB; font-size: 10px; background: transparent;")
        card_lay.addWidget(ver)

        center_row.addWidget(card)
        outer.addLayout(center_row)
        outer.addStretch(3)

    def _do_login(self):
        username = self.txt_username.text().strip()
        password = self.txt_password.text().strip()
        if not username or not password:
            self.lbl_error.setText("Enter username and password")
            return

        user = auth.authenticate(username, password)
        if user:
            self.lbl_error.setText("")
            audit.log_event("hub", "login", username, f"Login from hub")
            self.on_login_success(user)
        else:
            self.lbl_error.setText("Invalid username or password")
            audit.log_event("hub", "login_failed", username)


# --------------------------------------------------------------------------
# Module Picker Screen
# --------------------------------------------------------------------------

MODULE_COLORS = {
    "operations": "#C8102E",  # cerasus red
    "uniforms": "#1A1A2E",    # cerasus navy
    "attendance": "#374151",  # charcoal
    "training": "#059669",    # green
    "da_generator": "#7C3AED",  # purple
}


class ModulePickerScreen(QWidget):
    def __init__(self, modules, on_module_selected, app_state):
        super().__init__()
        self.modules = modules
        self.on_module_selected = on_module_selected
        self.app_state = app_state
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {tc('bg')};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(56)
        header.setStyleSheet(f"""
            QFrame {{ background: {tc('card')}; border-bottom: 1px solid {tc('border')}; }}
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(28, 0, 28, 0)

        brand = QLabel("CERASUS")
        brand.setStyleSheet(f"""
            color: {COLORS['accent']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 600;
            letter-spacing: 3px;
            background: transparent; border: none;
        """)
        h_lay.addWidget(brand)
        h_lay.addStretch()

        user = self.app_state.get("user", {})
        user_label = QLabel(f"{user.get('display_name', '')}  /  {user.get('role', '').upper()}")
        user_label.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; background: transparent; border: none;
        """)
        h_lay.addWidget(user_label)

        h_lay.addSpacing(12)

        # Change Password button
        pw_btn = QPushButton("CHANGE PASSWORD")
        pw_btn.setFixedHeight(36)
        pw_btn.setCursor(Qt.PointingHandCursor)
        pw_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 500;
                letter-spacing: 1px;
                color: {tc('text_light')};
                border: none; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {COLORS['accent']}; }}
        """)
        pw_btn.clicked.connect(self._open_change_password)
        h_lay.addWidget(pw_btn)

        self.dark_btn = QPushButton("DARK" if not self.app_state.get("dark_mode") else "LIGHT")
        self.dark_btn.setFixedHeight(36)
        self.dark_btn.setCursor(Qt.PointingHandCursor)
        self.dark_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 500;
                letter-spacing: 1px;
                color: {tc('text_light')};
                border: none; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {COLORS['accent']}; }}
        """)
        self.dark_btn.clicked.connect(self._toggle_dark)
        h_lay.addWidget(self.dark_btn)

        # Alerts button
        self.bell_btn = QPushButton("ALERTS (0)")
        self.bell_btn.setFixedHeight(36)
        self.bell_btn.setCursor(Qt.PointingHandCursor)
        self.bell_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 500;
                letter-spacing: 1px;
                color: {tc('text_light')}; border: none;
                padding: 0 8px;
            }}
            QPushButton:hover {{ color: {COLORS['accent']}; }}
        """)
        self.bell_btn.clicked.connect(self._toggle_alerts_panel)
        h_lay.addWidget(self.bell_btn)

        outer.addWidget(header)

        # -- Unread Announcements Banner --
        self.announce_banner = QFrame()
        self.announce_banner.setStyleSheet(f"""
            QFrame {{
                background: #3B82F6;
                border: none;
                padding: 8px 28px;
            }}
        """)
        banner_lay = QHBoxLayout(self.announce_banner)
        banner_lay.setContentsMargins(28, 6, 28, 6)
        banner_lay.setSpacing(12)

        self.announce_banner_lbl = QLabel("You have 0 unread announcements")
        self.announce_banner_lbl.setStyleSheet("""
            color: white;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; font-weight: 600;
            background: transparent; border: none;
        """)
        banner_lay.addWidget(self.announce_banner_lbl)
        banner_lay.addStretch()

        banner_view_btn = QPushButton("View")
        banner_view_btn.setCursor(Qt.PointingHandCursor)
        banner_view_btn.setFixedHeight(28)
        banner_view_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.2); color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 600;
                border-radius: 4px; padding: 0 16px;
                border: 1px solid rgba(255,255,255,0.3);
            }
            QPushButton:hover { background: rgba(255,255,255,0.35); }
        """)
        banner_view_btn.clicked.connect(self._open_announcements)
        banner_lay.addWidget(banner_view_btn)

        self.announce_banner.setVisible(False)
        outer.addWidget(self.announce_banner)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {tc('bg')}; border: none; }}")

        content = QWidget()
        content.setStyleSheet(f"background: {tc('bg')};")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(60, 40, 60, 40)
        content_lay.setSpacing(12)

        welcome = QLabel("SELECT A MODULE")
        welcome.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 20px; font-weight: 600;
            letter-spacing: 3px; background: transparent;
        """)
        content_lay.addWidget(welcome)

        sub = QLabel("Choose which system to work in")
        sub.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; font-weight: 300;
            letter-spacing: 1px; background: transparent;
        """)
        content_lay.addWidget(sub)

        content_lay.addSpacing(12)

        # -- Hub-level cross-module search bar --
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("\U0001F50D  Search officers, infractions, DAs, audit logs...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
                padding: 10px 16px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                color: {tc('text')};
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['accent']};
            }}
        """)
        self.search_input.setFixedHeight(42)

        # Debounce timer (300ms)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._do_search)
        self.search_input.textChanged.connect(self._on_search_text_changed)

        content_lay.addWidget(self.search_input)

        # Results dropdown (hidden by default)
        self.search_results_frame = QFrame()
        self.search_results_frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
                padding: 4px;
            }}
        """)
        self.search_results_lay = QVBoxLayout(self.search_results_frame)
        self.search_results_lay.setContentsMargins(8, 8, 8, 8)
        self.search_results_lay.setSpacing(2)
        self.search_results_frame.hide()
        content_lay.addWidget(self.search_results_frame)

        content_lay.addSpacing(16)

        # Quick-glance summary bar
        summary_frame = QFrame()
        summary_frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
                padding: 12px 24px;
            }}
        """)
        summary_lay = QHBoxLayout(summary_frame)
        summary_lay.setSpacing(24)

        self.summary_items = []

        kpis = [
            ("Active Officers", "0", COLORS['info']),
            ("Pending Reviews", "0", COLORS['accent']),
            ("Low Stock Items", "0", COLORS['danger']),
            ("Open Requests", "0", COLORS['info']),
        ]

        for idx, (label, value, color) in enumerate(kpis):
            if idx > 0:
                sep = QFrame()
                sep.setFixedWidth(1)
                sep.setStyleSheet(f"background: {tc('border')};")
                sep.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
                summary_lay.addWidget(sep)
            item = self._make_summary_item(label, value, color)
            self.summary_items.append(item)
            summary_lay.addWidget(item["widget"])

        summary_lay.addStretch()
        content_lay.addWidget(summary_frame)

        content_lay.addSpacing(12)

        # -- Alerts and Notifications panel --
        self.alerts_group = QGroupBox("Alerts and Notifications (0)")
        self.alerts_group.setCheckable(False)
        self.alerts_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Segoe UI', Arial, sans-serif;
                font-weight: 700; font-size: 14px;
                color: {tc('text')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
                margin-top: 10px; padding-top: 24px;
                background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px; padding: 0 8px;
            }}
        """)
        alerts_inner_lay = QVBoxLayout(self.alerts_group)
        alerts_inner_lay.setContentsMargins(8, 4, 8, 8)
        alerts_inner_lay.setSpacing(4)

        # Refresh button row
        alerts_toolbar = QHBoxLayout()
        alerts_toolbar.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setFixedHeight(28)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {tc('border')}; color: {tc('text')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 600;
                border-radius: 4px; padding: 4px 14px;
            }}
            QPushButton:hover {{ background: {COLORS['accent']}; color: white; }}
        """)
        refresh_btn.clicked.connect(self._refresh_alerts)
        alerts_toolbar.addWidget(refresh_btn)
        alerts_inner_lay.addLayout(alerts_toolbar)

        # Scroll area for alert cards
        self.alerts_scroll = QScrollArea()
        self.alerts_scroll.setWidgetResizable(True)
        self.alerts_scroll.setMaximumHeight(200)
        self.alerts_scroll.setStyleSheet(f"""
            QScrollArea {{ background: {tc('card')}; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: {tc('card')}; }}
        """)

        self.alerts_container = QWidget()
        self.alerts_container.setStyleSheet(f"background: {tc('card')};")
        self.alerts_list_lay = QVBoxLayout(self.alerts_container)
        self.alerts_list_lay.setContentsMargins(0, 0, 0, 0)
        self.alerts_list_lay.setSpacing(4)
        self.alerts_list_lay.addStretch()

        self.alerts_scroll.setWidget(self.alerts_container)
        alerts_inner_lay.addWidget(self.alerts_scroll)

        content_lay.addWidget(self.alerts_group)

        # Collapsed by default -- will expand if critical alerts found
        self.alerts_group.setVisible(False)

        content_lay.addSpacing(16)

        # Module cards grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(16)

        user = self.app_state.get("user", {})
        is_admin = user.get("role") == ROLE_ADMIN
        allowed = auth.get_user_modules(user.get("username", ""))

        badges = self._get_module_badges()
        visible_idx = 0
        for mod in self.modules:
            # Admin always sees all; empty allowed list = all modules (backward compat)
            if not is_admin and allowed and mod.module_id not in allowed:
                continue
            badge_count = badges.get(mod.module_id, 0)
            card = self._make_module_card(mod, badge_count)
            row = visible_idx // 2
            col = visible_idx % 2
            grid.addWidget(card, row, col)
            visible_idx += 1

        content_lay.addLayout(grid)

        content_lay.addSpacing(12)

        # -- Task Queue button --
        task_queue_btn = self._hub_card_button("Task Queue", COLORS['warning'], self._open_task_queue)
        content_lay.addWidget(task_queue_btn)

        content_lay.addSpacing(8)

        # -- Manage Module Permissions button (admin only) --
        if is_admin:
            perms_btn = self._hub_card_button("Manage Module Permissions", COLORS['accent'], self._open_module_permissions)
            content_lay.addWidget(perms_btn)
            content_lay.addSpacing(8)

        # -- People & Sites button --
        people_btn = self._hub_card_button("People and Sites", COLORS['accent'], self._open_people)
        content_lay.addWidget(people_btn)

        content_lay.addSpacing(8)

        # -- Site Comparison button --
        site_cmp_btn = self._hub_card_button("Site Comparison", COLORS['accent'], self._open_site_comparison)
        content_lay.addWidget(site_cmp_btn)

        content_lay.addSpacing(8)

        # -- Manage User Site Access button (admin only) --
        if is_admin:
            user_access_btn = self._hub_card_button("Manage User Site Access", COLORS['warning'], self._open_user_site_access)
            content_lay.addWidget(user_access_btn)

            content_lay.addSpacing(8)

            # -- Custom Fields button (admin only) --
            custom_fields_btn = self._hub_card_button("Custom Fields", COLORS['info'], self._open_custom_fields)
            content_lay.addWidget(custom_fields_btn)

            content_lay.addSpacing(8)

        # -- Analytics & Insights button --
        analytics_btn = self._hub_card_button("Analytics and Insights", COLORS['accent'], self._open_analytics)
        content_lay.addWidget(analytics_btn)

        content_lay.addSpacing(8)

        # -- Executive Summary Report button --
        exec_report_btn = self._hub_card_button("Executive Summary Report", COLORS['primary'], self._open_executive_report)
        content_lay.addWidget(exec_report_btn)

        content_lay.addSpacing(8)

        # -- Hub Audit Trail button --
        audit_btn = self._hub_card_button("Hub Audit Trail", COLORS['accent'], self._open_audit)
        content_lay.addWidget(audit_btn)

        content_lay.addSpacing(8)

        # -- Recent Activity button --
        activity_btn = self._hub_card_button("Recent Activity", COLORS['info'], self._open_activity)
        content_lay.addWidget(activity_btn)

        content_lay.addSpacing(8)

        # -- Announcements button with unread badge --
        announce_row = QHBoxLayout()
        announce_row.setSpacing(0)

        self.announce_btn = self._hub_card_button("Announcements", "#3B82F6", self._open_announcements)

        # Build the button text with badge inline
        self.announce_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        announce_row.addWidget(self.announce_btn)

        self.announce_badge = QLabel("")
        self.announce_badge.setAlignment(Qt.AlignCenter)
        self.announce_badge.setFixedSize(26, 26)
        self.announce_badge.setStyleSheet(f"""
            background: #3B82F6; color: white;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; font-weight: 800;
            border-radius: 13px;
        """)
        self.announce_badge.setVisible(False)
        announce_row.addWidget(self.announce_badge)

        content_lay.addLayout(announce_row)

        content_lay.addSpacing(8)

        # -- Database Backups button --
        backup_btn = self._hub_card_button("Database Backups", COLORS['accent'], self._open_backups)
        content_lay.addWidget(backup_btn)

        content_lay.addStretch()

        # -- Mobile companion indicator --
        try:
            companion_url = get_companion_url()
            companion_frame = QFrame()
            companion_frame.setStyleSheet(f"""
                QFrame {{
                    background: {tc('card')};
                    border: 1px solid {tc('border')};
                    border-radius: 8px;
                    padding: 10px 20px;
                }}
            """)
            comp_lay = QHBoxLayout(companion_frame)
            comp_lay.setSpacing(10)

            comp_dot = _make_dot(COLORS['success'], 8)
            comp_lay.addWidget(comp_dot)

            comp_label = QLabel(f"MOBILE COMPANION  {companion_url}")
            comp_label.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px; letter-spacing: 1px;
                background: transparent;
            """)
            comp_lay.addWidget(comp_label)
            comp_lay.addStretch()

            content_lay.addWidget(companion_frame)
        except Exception:
            pass

        # -- Online presence bar --
        online_frame = QFrame()
        online_frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
                padding: 12px 20px;
            }}
        """)
        online_lay = QHBoxLayout(online_frame)
        online_lay.setSpacing(12)

        self._online_dot = _make_dot(COLORS['success'], 10)
        online_lay.addWidget(self._online_dot)

        self.online_label = QLabel("Checking...")
        self.online_label.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; font-weight: 600; background: transparent;
        """)
        online_lay.addWidget(self.online_label)

        self.online_details = QLabel("")
        self.online_details.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 12px; background: transparent; border: none;
        """)
        self.online_details.setVisible(False)
        online_lay.addWidget(self.online_details)
        online_lay.addStretch()

        content_lay.addWidget(online_frame)

        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Online refresh timer
        self._online_timer = QTimer(self)
        self._online_timer.timeout.connect(self.refresh_online)
        self._online_timer.start(30000)  # refresh every 30 seconds
        self.refresh_online()  # initial load

        # Load summary KPIs
        self._refresh_summary()

        # Load alerts
        self._refresh_alerts()

        # Load announcements badge
        self._refresh_announcements_badge()

    def refresh_online(self):
        """Refresh the online users indicator."""
        try:
            users = session_manager.get_online_users()
        except Exception:
            self.online_label.setText("Could not check online status")
            self.online_details.setText("")
            self.online_details.setVisible(False)
            return

        if not users:
            self.online_label.setText("You're the only one here")
            self.online_details.setText("")
            self.online_details.setVisible(False)
            return

        # Filter out current user
        current = self.app_state.get("user", {}).get("username", "")
        others = [u for u in users if u["username"] != current]

        if not others:
            self.online_label.setText("You're the only one online")
            self.online_details.setText("")
            self.online_details.setVisible(False)
            return

        count = len(others)
        names = ", ".join(u["username"] for u in others[:5])
        if count > 5:
            names += f" +{count - 5} more"

        self.online_label.setText(f"{count + 1} online")

        # Show what each user is doing
        details = []
        for u in others[:5]:
            module = u.get("active_module", "")
            if module:
                details.append(f"{u['username']} in {module}")
            else:
                details.append(f"{u['username']} (hub)")
        self.online_details.setText("  |  ".join(details))
        self.online_details.setVisible(True)

    def _on_search_text_changed(self, text):
        """Restart debounce timer on each keystroke."""
        self._search_timer.start()

    def _do_search(self):
        """Execute cross-module search after debounce and populate results dropdown."""
        from src.search_engine import search_all

        # Clear previous results
        while self.search_results_lay.count():
            child = self.search_results_lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        query = self.search_input.text().strip()
        if len(query) < 2:
            self.search_results_frame.hide()
            return

        results = search_all(query, limit=20)

        if not results:
            no_result = QLabel("No results found")
            no_result.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px; padding: 6px 4px;
                background: transparent;
            """)
            self.search_results_lay.addWidget(no_result)
            self.search_results_frame.show()
            return

        for item in results:
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row_lay = QHBoxLayout(row_widget)
            row_lay.setContentsMargins(4, 2, 4, 2)
            row_lay.setSpacing(8)
            color = item.get("color", "#374151")
            dot = _make_dot(color, 8)
            row_lay.addWidget(dot)
            title_text = item.get("title", "")
            subtitle_text = item.get("subtitle", "")
            display = title_text
            if subtitle_text:
                display += f"  \u2014  {subtitle_text}"
            btn = QPushButton(display)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    background: transparent;
                    color: {tc('text')};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 13px;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 4px;
                }}
                QPushButton:hover {{
                    background: {tc('border')};
                }}
            """)
            btn.clicked.connect(
                lambda checked=False, r=item: self._on_search_result_clicked(r)
            )
            row_lay.addWidget(btn, 1)

            self.search_results_lay.addWidget(row_widget)

        self.search_results_frame.show()

    def _on_search_result_clicked(self, result):
        """Navigate to the appropriate module/page when a search result is clicked."""
        module_key = result.get("module", "")
        result_type = result.get("type", "")
        officer_id = result.get("officer_id")

        # For officer results, open the Officer 360 profile dialog
        if result_type == "officer" and officer_id:
            self._open_officer_profile(officer_id)
            return

        # For infraction/DA results with an officer_id, open officer profile
        if officer_id and result_type in ("infraction", "da"):
            self._open_officer_profile(officer_id)
            return

        # For module-specific results, navigate to the module
        for mod in self.modules:
            if mod.module_id == module_key:
                self.search_input.clear()
                self.search_results_frame.hide()
                self.on_module_selected(mod)
                return

        # For audit results, try to navigate to audit viewer
        if module_key == "audit" or result_type == "event":
            self.search_input.clear()
            self.search_results_frame.hide()
            parent = self.window()
            if hasattr(parent, '_show_audit'):
                parent._show_audit()
            return

    def _open_officer_profile(self, officer_id):
        """Open Officer 360 dialog for the selected officer."""
        try:
            from src.officer_360 import show_officer_profile
            show_officer_profile(self, officer_id, self.app_state)
        except Exception:
            pass

    def _make_summary_item(self, label, value, color):
        """Create a small inline KPI for the summary bar."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        dot = _make_dot(color, 8)
        lay.addWidget(dot)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        val_lbl = QLabel(str(value))
        val_lbl.setStyleSheet(f"""
            color: {color};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 18px; font-weight: 800; background: transparent;
        """)
        text_col.addWidget(val_lbl)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; background: transparent;
        """)
        text_col.addWidget(name_lbl)
        lay.addLayout(text_col)

        return {"widget": container, "value": val_lbl}

    def _refresh_summary(self):
        """Query the database and update summary bar KPIs."""
        try:
            from src.database import get_conn
            conn = get_conn()

            officers = 0
            try:
                officers = conn.execute("SELECT COUNT(*) as c FROM officers WHERE status = 'Active'").fetchone()["c"]
            except Exception:
                pass

            reviews = 0
            try:
                reviews = conn.execute("SELECT COUNT(*) as c FROM ats_employment_reviews WHERE review_status = 'Pending'").fetchone()["c"]
            except Exception:
                pass

            low_stock = 0
            try:
                low_stock = conn.execute("SELECT COUNT(*) as c FROM uni_catalog WHERE stock_qty <= reorder_point").fetchone()["c"]
            except Exception:
                pass

            open_requests = 0
            try:
                open_requests = conn.execute("SELECT COUNT(*) as c FROM ops_records WHERE status = 'Open'").fetchone()["c"]
            except Exception:
                pass

            conn.close()

            self.summary_items[0]["value"].setText(str(officers))
            self.summary_items[1]["value"].setText(str(reviews))
            self.summary_items[2]["value"].setText(str(low_stock))
            self.summary_items[3]["value"].setText(str(open_requests))
        except Exception:
            pass

    def _open_change_password(self):
        """Open the change password dialog for the current user."""
        user = self.app_state.get("user", {})
        username = user.get("username", "")
        if username:
            dlg = ChangePasswordDialog(username, self)
            dlg.exec()

    def _toggle_alerts_panel(self):
        """Toggle visibility of the alerts panel."""
        self.alerts_group.setVisible(not self.alerts_group.isVisible())

    def _refresh_alerts(self):
        """Query all modules for alerts and rebuild the notification panel."""
        try:
            from src.notifications import get_all_alerts
            alerts = get_all_alerts()
        except Exception:
            alerts = []

        # Clear existing alert cards
        while self.alerts_list_lay.count() > 0:
            item = self.alerts_list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Severity colors
        SEVERITY_COLORS = {
            "critical": "#C8102E",
            "warning": "#D97706",
            "info": "#9CA3AF",
        }

        has_critical = False
        for alert in alerts:
            sev = alert.get("severity", "info")
            bar_color = SEVERITY_COLORS.get(sev, "#9CA3AF")
            if sev == "critical":
                has_critical = True

            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {tc('card')};
                    border: 1px solid {tc('border')};
                    border-left: 4px solid {bar_color};
                    border-radius: 4px;
                    padding: 6px 10px;
                }}
            """)
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(6, 4, 6, 4)
            card_lay.setSpacing(2)

            # Module label (small, uppercase)
            mod_lbl = QLabel(alert.get("module", "").upper())
            mod_lbl.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10px;
                font-weight: 600; letter-spacing: 2px;
                background: transparent;
            """)
            card_lay.addWidget(mod_lbl)

            # Title (bold)
            title_lbl = QLabel(alert.get("title", ""))
            title_lbl.setWordWrap(True)
            title_lbl.setStyleSheet(f"""
                color: {tc('text')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                font-weight: 700; background: transparent;
            """)
            card_lay.addWidget(title_lbl)

            # Detail (lighter, smaller)
            detail = alert.get("detail", "")
            if detail:
                detail_lbl = QLabel(detail)
                detail_lbl.setWordWrap(True)
                detail_lbl.setStyleSheet(f"""
                    color: {tc('text_light')};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 11px;
                    font-weight: 400; background: transparent;
                """)
                card_lay.addWidget(detail_lbl)

            self.alerts_list_lay.addWidget(card)

        self.alerts_list_lay.addStretch()

        # Update badge counts
        count = len(alerts)
        self.alerts_group.setTitle(f"Alerts and Notifications ({count})")
        self.bell_btn.setText(f"ALERTS ({count})")

        # Style the bell red if there are critical alerts
        if has_critical:
            self.bell_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 12px; font-weight: 700;
                    letter-spacing: 1px;
                    color: {COLORS['accent']}; border: none;
                    padding: 0 8px;
                }}
                QPushButton:hover {{ color: {COLORS['accent_hover']}; }}
            """)
        else:
            self.bell_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 12px; font-weight: 500;
                    letter-spacing: 1px;
                    color: {tc('text_light')}; border: none;
                    padding: 0 8px;
                }}
                QPushButton:hover {{ color: {COLORS['accent']}; }}
            """)

        # Auto-expand if there are critical alerts, keep collapsed otherwise
        if has_critical:
            self.alerts_group.setVisible(True)
        elif count == 0:
            self.alerts_group.setVisible(False)

    def _get_module_badges(self):
        """Get notification counts for each module."""
        badges = {}
        try:
            from src.database import get_conn
            conn = get_conn()

            # Attendance: pending reviews count
            try:
                row = conn.execute("SELECT COUNT(*) as c FROM ats_employment_reviews WHERE review_status = 'Pending'").fetchone()
                badges["attendance"] = row["c"] if row else 0
            except Exception:
                badges["attendance"] = 0

            # Uniforms: low stock count
            try:
                row = conn.execute("SELECT COUNT(*) as c FROM uni_catalog WHERE stock_qty <= reorder_point").fetchone()
                badges["uniforms"] = row["c"] if row else 0
            except Exception:
                badges["uniforms"] = 0

            # Operations: open requests
            try:
                row = conn.execute("SELECT COUNT(*) as c FROM ops_records WHERE status = 'Open'").fetchone()
                badges["operations"] = row["c"] if row else 0
            except Exception:
                badges["operations"] = 0

            # Training: no badge for now
            badges["training"] = 0

            conn.close()
        except Exception:
            pass
        return badges

    def _hub_card_button(self, text, accent_color, on_click):
        """Create a hub picker nav button with left accent bar. Deduplicates ~150 lines."""
        btn = QPushButton(f"  {text}")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(44)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {tc('card')};
                color: {tc('text')};
                border: 1px solid {tc('border')};
                border-left: 4px solid {accent_color};
                border-radius: 8px;
                text-align: left;
                padding-left: 20px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {accent_color};
            }}
        """)
        btn.clicked.connect(on_click)
        return btn

    def _make_module_card(self, mod, badge_count=0):
        accent = MODULE_COLORS.get(mod.module_id, COLORS['accent'])

        card = QPushButton()
        card.setCursor(Qt.PointingHandCursor)
        card.setMinimumHeight(130)
        card.setStyleSheet(f"""
            QPushButton {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-top: 3px solid {accent};
                border-radius: 8px;
                text-align: left;
            }}
            QPushButton:hover {{
                border-color: {accent};
            }}
        """)
        apply_card_shadow(card)

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(24, 20, 24, 16)
        card_lay.setSpacing(4)

        # Name + version on one line
        title_text = f"{mod.name}  "
        name_lbl = QLabel(title_text)
        name_lbl.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 17px; font-weight: 700;
            background: transparent; border: none;
        """)

        ver_lbl = QLabel(f"v{mod.version}")
        ver_lbl.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px;
            background: transparent; border: none;
        """)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(name_lbl)
        top_row.addWidget(ver_lbl)
        top_row.addStretch()

        if badge_count > 0:
            badge = QLabel(str(badge_count))
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(26, 26)
            badge.setStyleSheet(f"""
                background: {COLORS['danger']}; color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px; font-weight: 800;
                border-radius: 13px;
            """)
            top_row.addWidget(badge)

        card_lay.addLayout(top_row)

        desc_lbl = QLabel(mod.description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; background: transparent; border: none;
        """)
        card_lay.addWidget(desc_lbl)
        card_lay.addStretch()

        card.clicked.connect(lambda checked=False, m=mod: self.on_module_selected(m))
        return card

    def _open_people(self):
        hub_window = self.window()
        if hasattr(hub_window, '_show_people'):
            hub_window._show_people()

    def _open_task_queue(self):
        hub_window = self.window()
        if hasattr(hub_window, '_show_task_queue'):
            hub_window._show_task_queue()

    def _open_site_comparison(self):
        hub_window = self.window()
        if hasattr(hub_window, '_show_site_comparison'):
            hub_window._show_site_comparison()

    def _open_analytics(self):
        hub_window = self.window()
        if hasattr(hub_window, '_show_analytics'):
            hub_window._show_analytics()

    def _open_executive_report(self):
        from src.executive_report import show_executive_report
        hub_window = self.window()
        username = ""
        if hasattr(hub_window, 'app_state'):
            username = hub_window.app_state.get("username", "")
        show_executive_report(self, username=username)

    def _open_audit(self):
        hub_window = self.window()
        if hasattr(hub_window, '_show_audit'):
            hub_window._show_audit()

    def _open_activity(self):
        hub_window = self.window()
        if hasattr(hub_window, '_show_activity'):
            hub_window._show_activity()

    def _open_backups(self):
        hub_window = self.window()
        if hasattr(hub_window, '_show_backups'):
            hub_window._show_backups()

    def _open_announcements(self):
        hub_window = self.window()
        if hasattr(hub_window, '_show_announcements'):
            hub_window._show_announcements()

    def _refresh_announcements_badge(self):
        """Update the announcements unread badge and banner visibility."""
        try:
            user = self.app_state.get("user", {})
            username = user.get("username", "")
            user_sites = self.app_state.get("assigned_sites", [])
            count = get_unread_count(username, user_sites)

            if count > 0:
                self.announce_badge.setText(str(count))
                self.announce_badge.setVisible(True)
                self.announce_banner_lbl.setText(f"You have {count} unread announcement{'s' if count != 1 else ''}")
                self.announce_banner.setVisible(True)
            else:
                self.announce_badge.setVisible(False)
                self.announce_banner.setVisible(False)
        except Exception:
            self.announce_badge.setVisible(False)
            self.announce_banner.setVisible(False)

    def _open_user_site_access(self):
        from src.user_management import UserSiteAccessDialog
        dlg = UserSiteAccessDialog(self)
        dlg.exec()

    def _toggle_dark(self):
        hub_window = self.window()
        if hasattr(hub_window, 'toggle_dark_mode'):
            hub_window.toggle_dark_mode()

    def _open_module_permissions(self):
        """Open the module permissions management dialog."""
        dlg = ModulePermissionsDialog(self.modules, self)
        dlg.exec()

    def _open_custom_fields(self):
        """Open the custom fields management dialog."""
        try:
            from src.custom_fields import CustomFieldsAdminDialog
            dlg = CustomFieldsAdminDialog(self)
            dlg.exec()
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Could not open Custom Fields:\n{exc}")


# --------------------------------------------------------------------------
# Module Permissions Dialog
# --------------------------------------------------------------------------

class ModulePermissionsDialog(QDialog):
    """Admin dialog to manage which modules each user can access."""

    def __init__(self, modules, parent=None):
        super().__init__(parent)
        self.all_modules = modules
        self.setWindowTitle("Module Access Permissions")
        self.setMinimumSize(560, 480)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._current_checks = {}
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("MODULE ACCESS PERMISSIONS")
        title.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700;
            letter-spacing: 2px;
        """)
        layout.addWidget(title)

        hint = QLabel(
            "Select which modules each user can access. "
            "Unchecking all boxes gives full access (backward compatible)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 12px;
        """)
        layout.addWidget(hint)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(12)
        sel_label = QLabel("User:")
        sel_label.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px; font-weight: 600;
        """)
        selector_row.addWidget(sel_label)

        self.user_combo = QComboBox()
        self.user_combo.setMinimumWidth(240)
        self.user_combo.setStyleSheet(f"""
            QComboBox {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 6px; padding: 8px 12px;
                font-size: 14px; color: {tc('text')};
            }}
        """)
        selector_row.addWidget(self.user_combo)
        selector_row.addStretch()
        layout.addLayout(selector_row)

        self.modules_group = QGroupBox("Allowed Modules")
        self.modules_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Segoe UI', Arial, sans-serif;
                font-weight: 700; font-size: 14px;
                color: {tc('text')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
                margin-top: 10px; padding-top: 24px;
                background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px; padding: 0 8px;
            }}
        """)
        self.modules_lay = QVBoxLayout(self.modules_group)
        self.modules_lay.setContentsMargins(16, 8, 16, 12)
        self.modules_lay.setSpacing(8)
        layout.addWidget(self.modules_group)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("Save")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 600;
                border-radius: 6px; padding: 0 28px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        save_btn.clicked.connect(self._save_current)
        btn_row.addWidget(save_btn)

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(40)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {tc('border')}; color: {tc('text')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 600;
                border-radius: 6px; padding: 0 28px;
            }}
            QPushButton:hover {{ background: {tc('info_light')}; }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._load_users()
        self.user_combo.currentIndexChanged.connect(self._on_user_changed)
        if self.user_combo.count() > 0:
            self._on_user_changed(0)

    def _load_users(self):
        users = auth.get_all_users()
        for u in users:
            if u.get("role") == ROLE_ADMIN:
                continue
            display = f"{u['display_name'] or u['username']}  ({u['username']})"
            self.user_combo.addItem(display, u["username"])

    def _on_user_changed(self, index):
        while self.modules_lay.count():
            child = self.modules_lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        username = self.user_combo.currentData()
        if not username:
            return

        current_perms = auth.get_user_modules(username)
        self._current_checks = {}

        for mod in self.all_modules:
            cb = QCheckBox(f"  {mod.name}  ({mod.module_id})")
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {tc('text')};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 14px; spacing: 8px; padding: 4px 0;
                }}
                QCheckBox::indicator {{
                    width: 20px; height: 20px;
                    border: 2px solid {tc('border')};
                    border-radius: 4px; background: {tc('card')};
                }}
                QCheckBox::indicator:checked {{
                    background: {COLORS['accent']};
                    border-color: {COLORS['accent']};
                }}
            """)
            if not current_perms:
                cb.setChecked(True)
            else:
                cb.setChecked(mod.module_id in current_perms)
            self._current_checks[mod.module_id] = cb
            self.modules_lay.addWidget(cb)

        toggle_row = QHBoxLayout()
        check_all_btn = QPushButton("Check All")
        check_all_btn.setCursor(Qt.PointingHandCursor)
        check_all_btn.setFixedHeight(30)
        check_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLORS['accent']};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 600;
                border: none; padding: 0 8px;
            }}
        """)
        check_all_btn.clicked.connect(lambda: self._set_all(True))
        toggle_row.addWidget(check_all_btn)

        uncheck_all_btn = QPushButton("Uncheck All")
        uncheck_all_btn.setCursor(Qt.PointingHandCursor)
        uncheck_all_btn.setFixedHeight(30)
        uncheck_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 600;
                border: none; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {COLORS['accent']}; }}
        """)
        uncheck_all_btn.clicked.connect(lambda: self._set_all(False))
        toggle_row.addWidget(uncheck_all_btn)
        toggle_row.addStretch()

        container = QWidget()
        container.setLayout(toggle_row)
        self.modules_lay.addWidget(container)

    def _set_all(self, checked):
        for cb in self._current_checks.values():
            cb.setChecked(checked)

    def _save_current(self):
        username = self.user_combo.currentData()
        if not username:
            return
        selected = [mid for mid, cb in self._current_checks.items() if cb.isChecked()]
        if len(selected) == len(self.all_modules):
            selected = []
        auth.set_user_modules(username, selected)
        QMessageBox.information(
            self, "Saved",
            f"Module permissions updated for {username}.\n"
            "Changes take effect on their next login or hub refresh."
        )


# --------------------------------------------------------------------------
# Module Shell Widget (sidebar + pages)
# --------------------------------------------------------------------------

class ModuleShellWidget(QWidget):
    def __init__(self, module, app_state, on_back_to_hub):
        super().__init__()
        self.module = module
        self.app_state = app_state
        self.on_back_to_hub = on_back_to_hub
        self.nav_buttons = []
        self.pages = []
        self._build()

        # Auto-refresh timer for read-only (viewer) users
        self._auto_refresh_timer = None
        user_role = self.app_state.get("user", {}).get("role", "")
        if user_role == ROLE_VIEWER:
            self._auto_refresh_timer = QTimer(self)
            self._auto_refresh_timer.timeout.connect(self._auto_refresh)
            self._auto_refresh_timer.start(READ_ONLY_REFRESH_MS)

        # Ensure first page loads data on module entry
        if self.pages:
            first = self.pages[0]
            if hasattr(first, 'refresh'):
                try:
                    first.refresh()
                except Exception:
                    pass

        # Wire cross-page signals (e.g., DA history Resume Draft -> wizard)
        self._connect_cross_page_signals()

    def _connect_cross_page_signals(self):
        """Connect signals between module pages (e.g., DA history -> wizard)."""
        try:
            from src.modules.da_generator.pages_history import DAHistoryPage
            from src.modules.da_generator.pages_wizard import DAWizardPage

            history_page = None
            wizard_page = None
            for page in self.pages:
                if isinstance(page, DAHistoryPage):
                    history_page = page
                elif isinstance(page, DAWizardPage):
                    wizard_page = page

            if history_page and wizard_page:
                def _on_resume_draft(da_record):
                    wizard_page.load_from_record(da_record)
                    # Switch to wizard page (index 0)
                    self._nav_to(0)

                history_page.resume_draft_requested.connect(_on_resume_draft)
        except Exception:
            pass  # Module not loaded or not DA Generator

    def _build(self):
        dark = _is_dark()
        c = DARK_COLORS if dark else COLORS

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Sidebar --
        sidebar = QFrame()
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background: {c.get('primary_dark', c['primary'])};
                border: none;
            }}
        """)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(10, 12, 10, 12)
        sb_lay.setSpacing(4)

        # Cerasus brand in sidebar
        sidebar_brand = QLabel("CERASUS")
        sidebar_brand.setStyleSheet(f"""
            color: {COLORS['accent']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; font-weight: 600;
            letter-spacing: 3px; background: transparent;
            padding: 4px 0 2px 14px;
        """)
        sb_lay.addWidget(sidebar_brand)

        # Back to Hub button
        back_btn = QPushButton("Back to Hub")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedHeight(36)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {c['sidebar_text']};
                text-align: left;
                padding-left: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                font-weight: 500;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {c['sidebar_hover']};
                color: white;
            }}
        """)
        back_btn.clicked.connect(self._on_back_clicked)
        sb_lay.addWidget(back_btn)

        # Module name
        mod_label = QLabel(f"  {self.module.name.upper()}")
        mod_label.setStyleSheet(f"""
            color: white;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 2px;
            background: transparent;
            padding: 8px 0 4px 6px;
        """)
        sb_lay.addWidget(mod_label)

        sb_lay.addSpacing(8)

        # Nav buttons from module sidebar_sections
        self.nav_buttons = []
        page_classes = self.module.page_classes
        is_admin = self.app_state.get("user", {}).get("role") == ROLE_ADMIN
        btn_idx = 0
        visible_idx = 0  # tracks position in nav_buttons list

        for section_name, items in self.module.sidebar_sections:
            section_label = SidebarSectionLabel(section_name)
            sb_lay.addWidget(section_label)

            for page_name, icon_char in items:
                if btn_idx < len(page_classes):
                    _, requires_admin = page_classes[btn_idx]
                    if requires_admin and not is_admin:
                        btn_idx += 1
                        continue

                btn = SidebarButton(page_name, icon_char)
                nav_idx = visible_idx  # capture position in nav_buttons list
                btn.clicked.connect(lambda checked=False, i=nav_idx: self._nav_to(i))
                sb_lay.addWidget(btn)
                self.nav_buttons.append((btn, btn_idx, page_name))
                btn_idx += 1
                visible_idx += 1

        sb_lay.addStretch()

        # Dark mode toggle in sidebar footer
        self.dark_btn = QPushButton("DARK" if not self.app_state.get("dark_mode") else "LIGHT")
        self.dark_btn.setFixedHeight(28)
        self.dark_btn.setCursor(Qt.PointingHandCursor)
        self.dark_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px; font-weight: 500;
                letter-spacing: 1px;
                color: {c['sidebar_text']};
                border: none; padding: 0 12px;
                text-align: left;
            }}
            QPushButton:hover {{ color: white; }}
        """)
        self.dark_btn.clicked.connect(self._toggle_dark)
        sb_lay.addWidget(self.dark_btn)

        # ── Notifications bell button with badge ──
        bell_row = QHBoxLayout()
        bell_row.setContentsMargins(0, 0, 0, 0)
        bell_row.setSpacing(0)

        self._bell_btn = QPushButton()
        self._bell_btn.setFixedSize(40, 32)
        self._bell_btn.setCursor(Qt.PointingHandCursor)
        self._bell_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 18px;
                color: {c['sidebar_text']};
                border: none;
                padding: 0;
                text-align: center;
            }}
            QPushButton:hover {{ color: white; }}
        """)
        self._bell_btn.setText("\U0001F514")  # bell emoji
        self._bell_btn.clicked.connect(self._show_notifications_popup)
        bell_row.addWidget(self._bell_btn)

        # Badge label (red circle with count)
        self._bell_badge = QLabel("0")
        self._bell_badge.setFixedSize(20, 20)
        self._bell_badge.setAlignment(Qt.AlignCenter)
        self._bell_badge.setStyleSheet(f"""
            background: {COLORS['accent']};
            color: white;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10px; font-weight: 700;
            border-radius: 10px;
        """)
        self._bell_badge.hide()
        bell_row.addWidget(self._bell_badge)

        self._bell_label = QLabel("ALERTS")
        self._bell_label.setStyleSheet(f"""
            color: {c['sidebar_text']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; font-weight: 500;
            letter-spacing: 1px;
            background: transparent;
            padding-left: 2px;
        """)
        bell_row.addWidget(self._bell_label)
        bell_row.addStretch()
        sb_lay.addLayout(bell_row)

        # Cache for current notifications
        self._cached_notifications: list[dict] = []

        # Initial notification load (deferred so UI builds first)
        QTimer.singleShot(500, self._refresh_notifications)

        # User info footer
        user = self.app_state.get("user", {})
        user_frame = QFrame()
        user_frame.setStyleSheet(f"background: {c.get('primary_dark', c['primary'])}; border: none;")
        uf_lay = QVBoxLayout(user_frame)
        uf_lay.setContentsMargins(12, 8, 12, 8)
        u_name = QLabel(user.get("display_name", ""))
        u_name.setStyleSheet(f"""
            color: white;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; font-weight: 600; background: transparent;
        """)
        uf_lay.addWidget(u_name)
        u_role = QLabel(user.get("role", "").upper())
        u_role.setStyleSheet(f"""
            color: {c['sidebar_text']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; background: transparent;
        """)
        uf_lay.addWidget(u_role)
        sb_lay.addWidget(user_frame)

        # Online users indicator
        online_row = QHBoxLayout()
        online_row.setContentsMargins(14, 4, 0, 4)
        online_row.setSpacing(6)
        self._sb_online_dot = _make_dot(COLORS['success'], 8)
        online_row.addWidget(self._sb_online_dot)
        self.online_indicator = QLabel("1 online")
        self.online_indicator.setStyleSheet(f"""
            color: {c['sidebar_text']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; background: transparent;
        """)
        online_row.addWidget(self.online_indicator)
        online_row.addStretch()
        sb_lay.addLayout(online_row)

        # Sidebar online refresh timer
        self._sb_online_timer = QTimer(self)
        self._sb_online_timer.timeout.connect(self._refresh_sidebar_online)
        self._sb_online_timer.start(30000)
        self._refresh_sidebar_online()

        layout.addWidget(sidebar)

        # -- Right column: breadcrumb + page stack --
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)

        # Breadcrumb bar
        self.breadcrumb = BreadcrumbBar()
        self.breadcrumb.setStyleSheet(f"""
            background: {tc('card')};
            border-bottom: 1px solid {tc('border')};
        """)
        right_col.addWidget(self.breadcrumb)

        # Page Stack (animated crossfade)
        self.page_stack = AnimatedStackedWidget()
        self.page_stack.setStyleSheet(f"background: {tc('bg')};")

        self.pages = []
        for page_cls, requires_admin in page_classes:
            if requires_admin and not is_admin:
                continue
            try:
                page = page_cls(self.app_state)
                self.pages.append(page)
                self.page_stack.addWidget(page)
            except Exception as e:
                # Placeholder for pages not yet implemented
                placeholder = QWidget()
                p_lay = QVBoxLayout(placeholder)
                p_lay.addStretch()
                lbl = QLabel(f"Page: {page_cls.__name__}\n\n(Coming soon)")
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 18px;")
                p_lay.addWidget(lbl)
                p_lay.addStretch()
                self.pages.append(placeholder)
                self.page_stack.addWidget(placeholder)

        right_col.addWidget(self.page_stack)
        layout.addLayout(right_col)

        # Select first page
        if self.nav_buttons:
            self._nav_to(0)

    def _nav_to(self, index):
        """Switch to page at the given index and update sidebar active state."""
        # Map button index to stack index
        stack_idx = 0
        page_name = ""
        for i, (btn, btn_page_idx, btn_page_name) in enumerate(self.nav_buttons):
            if i == index:
                stack_idx = i
                page_name = btn_page_name
                btn.set_active(True)
            else:
                btn.set_active(False)

        if stack_idx < len(self.pages):
            self.page_stack.slide_to(stack_idx)
            page = self.pages[stack_idx]
            if hasattr(page, 'refresh'):
                try:
                    page.refresh()
                except Exception:
                    pass
            # Refresh notification badge on page switch
            try:
                self._refresh_notifications()
            except Exception:
                pass

        # Update breadcrumb
        mod_name = self.module.name
        self.breadcrumb.set_path([
            ("Hub", self.on_back_to_hub),
            (mod_name, lambda: self._nav_to(0)),
            (page_name, None),
        ])

    def _refresh_sidebar_online(self):
        """Update the online indicator in the sidebar."""
        try:
            users = session_manager.get_online_users()
            count = len(users)
            current = self.app_state.get("user", {}).get("username", "")
            others = [u for u in users if u["username"] != current]
            dark = _is_dark()
            c = DARK_COLORS if dark else COLORS

            if others:
                active_here = [u for u in others if u.get("active_module") == self.module.module_id]
                if active_here:
                    names = ", ".join(u["username"] for u in active_here[:3])
                    self.online_indicator.setText(f"{len(active_here)} also here: {names}")
                    self.online_indicator.setStyleSheet(f"""
                        color: {COLORS['success']};
                        font-family: 'Segoe UI', Arial, sans-serif;
                        font-size: 11px; background: transparent;
                    """)
                else:
                    self.online_indicator.setText(f"{count} online")
                    self.online_indicator.setStyleSheet(f"""
                        color: {c['sidebar_text']};
                        font-family: 'Segoe UI', Arial, sans-serif;
                        font-size: 11px; background: transparent;
                    """)
            else:
                self.online_indicator.setText("Only you")
                self.online_indicator.setStyleSheet(f"""
                    color: {c['sidebar_text']};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 11px; background: transparent;
                """)
        except Exception:
            pass

    def _refresh_notifications(self):
        from src.notification_ui import refresh_notifications
        refresh_notifications(self)

    def _show_notifications_popup(self):
        from src.notification_ui import show_notifications_popup
        show_notifications_popup(self)

    def _on_back_clicked(self):
        """Stop auto-refresh timer and navigate back to hub."""
        self._stop_auto_refresh()
        self.on_back_to_hub()

    def _auto_refresh(self):
        """Called by the read-only timer — refresh the currently visible page."""
        try:
            page = self.pages[self.page_stack.currentIndex()]
            if hasattr(page, 'refresh'):
                page.refresh()
        except Exception:
            pass

    def _stop_auto_refresh(self):
        """Stop the auto-refresh timer (call when leaving the module)."""
        if self._auto_refresh_timer is not None:
            self._auto_refresh_timer.stop()
            self._auto_refresh_timer = None

    def _toggle_dark(self):
        hub_window = self.window()
        if hasattr(hub_window, 'toggle_dark_mode'):
            hub_window.toggle_dark_mode()


# --------------------------------------------------------------------------
# Hub Main Window
# --------------------------------------------------------------------------

class HubMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self.app_state = {
            "user": None,
            "dark_mode": False,
        }

        self.modules = discover_modules()
        self.session_id = None
        self._companion_thread = None

        # Heartbeat timer
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._heartbeat)
        self._heartbeat_timer.setInterval(60_000)  # 60 seconds

        # Central stack: login -> picker -> module shell
        self.central_stack = QStackedWidget()
        self.setCentralWidget(self.central_stack)

        # Login screen
        self.login_screen = LoginScreen(self._on_login_success)
        self.central_stack.addWidget(self.login_screen)

        # Keyboard shortcuts
        self._setup_shortcuts()

        # Apply initial style
        self._apply_theme()

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _setup_shortcuts(self):
        """Register all global keyboard shortcuts on the main window."""
        # Ctrl+1 through Ctrl+5 -- switch to module by index
        for i in range(1, 6):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            idx = i - 1
            shortcut.activated.connect(lambda n=idx: self._shortcut_module(n))

        # Escape -- go back to hub
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._shortcut_back)

        # Ctrl+H -- go back to Hub / Module Picker
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self._shortcut_back_to_hub)

        # Ctrl+N -- context-aware "New" action
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._shortcut_new)

        # Ctrl+D -- toggle dark mode
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self.toggle_dark_mode)

        # Ctrl+L -- logout
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._shortcut_logout)

        # Ctrl+F -- focus hub search bar
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._shortcut_focus_search)

        # Ctrl+B -- manual database backup
        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(self._shortcut_backup)

        # F5 -- refresh current page
        QShortcut(QKeySequence("F5"), self).activated.connect(self._shortcut_refresh)

        # Ctrl+P -- print current page
        QShortcut(QKeySequence("Ctrl+P"), self).activated.connect(self._shortcut_print)

        # F1 -- show keyboard shortcuts help
        QShortcut(QKeySequence("F1"), self).activated.connect(self._show_shortcuts_help)

        # Ctrl+? (Ctrl+Shift+/) -- also show shortcuts help
        QShortcut(QKeySequence("Ctrl+Shift+/"), self).activated.connect(self._show_shortcuts_help)

    def _shortcut_back_to_hub(self):
        """Ctrl+H: return to the module picker from anywhere (except login)."""
        current = self.central_stack.currentWidget()
        if current is not self.login_screen:
            self._back_to_hub()

    def _shortcut_new(self):
        """Ctrl+N: context-aware 'New' action depending on current module."""
        current = self.central_stack.currentWidget()
        if not isinstance(current, ModuleShellWidget):
            return

        mod_id = current.module.module_id

        if mod_id == "da_generator":
            # Navigate to the first page (New DA page) and trigger its new action
            if current.pages:
                first_page = current.pages[0]
                current.page_stack.setCurrentIndex(0)
                if hasattr(first_page, '_new_da'):
                    first_page._new_da()
                elif hasattr(first_page, 'refresh'):
                    first_page.refresh()

        elif mod_id == "attendance":
            # Find the Log Infraction page (typically the infractions page)
            for i, page in enumerate(current.pages):
                cls_name = type(page).__name__.lower()
                if 'infraction' in cls_name or 'log' in cls_name:
                    current._nav_to(i)
                    break

        elif mod_id == "operations":
            # Try to trigger a new-record dialog on the current page
            active_page = current.pages[current.page_stack.currentIndex()] if current.pages else None
            if active_page and hasattr(active_page, '_new_record'):
                active_page._new_record()
            elif active_page and hasattr(active_page, '_add_record'):
                active_page._add_record()

    def _shortcut_logout(self):
        """Ctrl+L: log the current user out and return to the login screen."""
        current = self.central_stack.currentWidget()
        if current is self.login_screen:
            return

        reply = QMessageBox.question(
            self, "Logout",
            "Are you sure you want to log out?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Clean up session
        if self.session_id:
            try:
                session_manager.remove_session(self.session_id)
            except Exception:
                pass
            self.session_id = None
        self._heartbeat_timer.stop()

        user = self.app_state.get("user", {})
        username = user.get("username", "")
        audit.log_event("hub", "logout", username, "Logout from hub")

        self.app_state["user"] = None

        # Remove everything except login screen
        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        self.central_stack.setCurrentIndex(0)
        # Clear login fields
        self.login_screen.txt_username.clear()
        self.login_screen.txt_password.clear()
        self.login_screen.lbl_error.clear()
        self.login_screen.txt_username.setFocus()

    def _shortcut_focus_search(self):
        """Ctrl+F: focus the search bar on the module picker screen."""
        current = self.central_stack.currentWidget()
        if isinstance(current, ModulePickerScreen) and hasattr(current, 'search_input'):
            current.search_input.setFocus()
            current.search_input.selectAll()

    def _shortcut_backup(self):
        """Ctrl+B: trigger a manual database backup if backup_manager exists."""
        try:
            from src.backup_manager import create_backup
            path = create_backup("manual")
            if not path:
                QMessageBox.warning(self, "Backup Failed", "Could not create backup.")
                return
            QMessageBox.information(self, "Backup", "Database backup completed successfully.")
        except ImportError:
            QMessageBox.information(self, "Backup", "Backup module is not available.")
        except Exception as e:
            QMessageBox.warning(self, "Backup Failed", f"Backup failed: {e}")

    def _shortcut_refresh(self):
        """F5: refresh the current page."""
        current = self.central_stack.currentWidget()

        if isinstance(current, ModulePickerScreen):
            # Refresh the module picker (KPIs, alerts, online, announcements)
            if hasattr(current, '_refresh_summary'):
                current._refresh_summary()
            if hasattr(current, '_refresh_alerts'):
                current._refresh_alerts()
            if hasattr(current, 'refresh_online'):
                current.refresh_online()
            if hasattr(current, '_refresh_announcements_badge'):
                current._refresh_announcements_badge()
            return

        if isinstance(current, ModuleShellWidget):
            idx = current.page_stack.currentIndex()
            if idx < len(current.pages):
                page = current.pages[idx]
                if hasattr(page, 'refresh'):
                    try:
                        page.refresh()
                    except Exception:
                        pass
            return

        # Generic: try calling refresh on the current widget
        if hasattr(current, 'refresh'):
            try:
                current.refresh()
            except Exception:
                pass

    def _shortcut_print(self):
        """Ctrl+P: print the currently visible page widget."""
        current = self.central_stack.currentWidget()
        if current is self.login_screen:
            return

        # Determine the printable widget and a sensible title
        title = APP_NAME
        target = current

        if isinstance(current, ModuleShellWidget):
            idx = current.page_stack.currentIndex()
            if idx < len(current.pages):
                target = current.pages[idx]
            title = f"{APP_NAME} — {current.module.name}"

        from src.pdf_export import print_widget
        print_widget(target, title=title)

    def _show_shortcuts_help(self):
        """Show a dialog listing all keyboard shortcuts."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.setMinimumSize(480, 420)
        if self.app_state.get("dark_mode"):
            dlg.setStyleSheet(build_dialog_stylesheet(True))

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        title = QLabel("KEYBOARD SHORTCUTS")
        title.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700;
            letter-spacing: 2px; background: transparent;
        """)
        lay.addWidget(title)

        shortcuts = [
            ("Ctrl+1 ... Ctrl+5", "Switch to module (by position)"),
            ("Ctrl+H", "Return to Hub / Module Picker"),
            ("Ctrl+N", "New action (context-aware)"),
            ("Ctrl+D", "Toggle dark mode"),
            ("Ctrl+L", "Logout"),
            ("Ctrl+F", "Focus hub search bar"),
            ("Ctrl+B", "Manual database backup"),
            ("Ctrl+P", "Print current page"),
            ("F5", "Refresh current page"),
            ("Escape", "Go back"),
            ("F1  /  Ctrl+?", "Show this help"),
        ]

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        for row, (key, desc) in enumerate(shortcuts):
            key_lbl = QLabel(key)
            key_lbl.setStyleSheet(f"""
                color: {tc('text')};
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px; font-weight: 700;
                background: {tc('border')}; border-radius: 4px;
                padding: 4px 10px;
            """)
            key_lbl.setFixedHeight(28)
            grid.addWidget(key_lbl, row, 0)

            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px; background: transparent;
            """)
            grid.addWidget(desc_lbl, row, 1)

        lay.addLayout(grid)
        lay.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(36)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px; font-weight: 500;
                border-radius: 6px; padding: 0 24px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignRight)

        dlg.exec()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self):
        dark = self.app_state.get("dark_mode", False)
        set_dark_mode(dark)
        self.setStyleSheet(build_global_style(dark))

    def toggle_dark_mode(self):
        """Toggle dark mode, reapply theme, and rebuild the current screen."""
        from src.hub_audit_viewer import HubAuditViewer
        self.app_state["dark_mode"] = not self.app_state.get("dark_mode", False)
        self._apply_theme()

        # Persist dark mode preference
        save_setting("dark_mode", self.app_state.get("dark_mode", False))

        # Rebuild the current screen so widgets pick up the new theme
        current_idx = self.central_stack.currentIndex()
        if current_idx > 0:
            current_widget = self.central_stack.currentWidget()
            if isinstance(current_widget, ModulePickerScreen):
                self._show_module_picker()
            elif isinstance(current_widget, HubPeoplePage):
                self._show_people()
            elif isinstance(current_widget, HubAnalyticsPage):
                self._show_analytics()
            elif isinstance(current_widget, HubAuditViewer):
                self._show_audit()
            elif isinstance(current_widget, ActivityFeedPage):
                self._show_activity()
            elif isinstance(current_widget, AnnouncementsPage):
                self._show_announcements()
            else:
                from src.hub_backups import HubBackupsPage
                if isinstance(current_widget, HubBackupsPage):
                    self._show_backups()
                elif isinstance(current_widget, ModuleShellWidget):
                    # Re-enter the same module to rebuild the shell
                    module = current_widget.module
                    self._enter_module(module)

    # ------------------------------------------------------------------
    # Welcome / Onboarding Dialog (Hub #20)
    # ------------------------------------------------------------------

    def _show_welcome_dialog(self, user):
        """Show a one-time welcome dialog for first-time users."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Welcome")
        dlg.setMinimumSize(520, 420)
        if self.app_state.get("dark_mode"):
            dlg.setStyleSheet(build_dialog_stylesheet(True))

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(16)

        # Header
        header = QLabel("Welcome to Cerasus Hub")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(f"""
            color: {COLORS['accent']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 22px; font-weight: 700;
            letter-spacing: 1px; background: transparent;
        """)
        lay.addWidget(header)

        sub = QLabel(f"Hello, {user.get('display_name', user.get('username', ''))}! "
                     "Here is what you can do:")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; background: transparent;
        """)
        lay.addWidget(sub)

        lay.addSpacing(8)

        # Module overview grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        for idx, mod in enumerate(self.modules):
            icon_text = mod.icon if mod.icon else ""
            desc_text = mod.description if mod.description else mod.name

            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {tc('card')};
                    border: 1px solid {tc('border')};
                    border-radius: 8px;
                    padding: 10px 14px;
                }}
            """)
            c_lay = QHBoxLayout(card)
            c_lay.setContentsMargins(8, 6, 8, 6)
            c_lay.setSpacing(10)

            if icon_text:
                icon_lbl = QLabel(icon_text)
                icon_lbl.setStyleSheet(f"""
                    font-size: 20px; background: transparent;
                    color: {tc('text')};
                """)
                icon_lbl.setFixedWidth(28)
                c_lay.addWidget(icon_lbl)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)

            name_lbl = QLabel(mod.name)
            name_lbl.setStyleSheet(f"""
                color: {tc('text')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px; font-weight: 700;
                background: transparent;
            """)
            text_col.addWidget(name_lbl)

            desc_lbl = QLabel(desc_text)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px; background: transparent;
            """)
            text_col.addWidget(desc_lbl)

            c_lay.addLayout(text_col, 1)

            row = idx // 2
            col = idx % 2
            grid.addWidget(card, row, col)

        lay.addLayout(grid)
        lay.addStretch()

        # Get Started button
        start_btn = QPushButton("Get Started")
        start_btn.setCursor(Qt.PointingHandCursor)
        start_btn.setFixedHeight(42)
        start_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 600;
                letter-spacing: 1px;
                border-radius: 21px; padding: 0 32px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        start_btn.clicked.connect(dlg.accept)
        lay.addWidget(start_btn, alignment=Qt.AlignCenter)

        dlg.exec()

    def _on_login_success(self, user):
        self.app_state["user"] = user
        self.app_state["role"] = user.get("role", "")
        self.app_state["assigned_sites"] = auth.get_user_sites(user.get("username", ""))

        # Register session
        self.session_id = session_manager.register_session(
            user["username"], user["role"]
        )
        self._heartbeat_timer.start()

        # Start web companion server
        if not self._companion_thread:
            try:
                self._companion_thread = start_companion_server()
            except Exception:
                pass

        # Load all persisted settings (dark mode, sidebar state, etc.)
        settings = load_all_settings()
        if settings.get("dark_mode"):
            self.app_state["dark_mode"] = True
            self._apply_theme()

        # Check if user must change default password
        if auth.must_change_password(user["username"]):
            self._prompt_password_change(user["username"])

        # Show welcome dialog for first-time users (only once per user)
        welcome_key = f"welcome_shown_{user['username']}"
        if not get_setting(welcome_key):
            self._show_welcome_dialog(user)
            save_setting(welcome_key, True)

        # Restore the last active module if one was persisted
        last_mod_id = get_setting("last_active_module")
        if last_mod_id:
            for mod in self.modules:
                if mod.module_id == last_mod_id:
                    self._enter_module(mod)
                    return

        # Otherwise, show module picker
        self._show_module_picker()

    def _prompt_password_change(self, username: str):
        """Show dialog prompting user to change the default password."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Change Default Password")
        dlg.setMinimumSize(420, 260)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        info = QLabel("Your account is using the default password.\nPlease set a new password.")
        info.setStyleSheet("font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px;")
        lay.addWidget(info)

        new_pw = QLineEdit()
        new_pw.setPlaceholderText("New password (min 6 characters)")
        new_pw.setEchoMode(QLineEdit.Password)
        new_pw.setFixedHeight(38)
        lay.addWidget(new_pw)

        confirm_pw = QLineEdit()
        confirm_pw.setPlaceholderText("Confirm new password")
        confirm_pw.setEchoMode(QLineEdit.Password)
        confirm_pw.setFixedHeight(38)
        lay.addWidget(confirm_pw)

        error_lbl = QLabel("")
        error_lbl.setStyleSheet(f"color: {COLORS['danger']}; font-size: 12px;")
        lay.addWidget(error_lbl)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(btn_box)

        def on_accept():
            pw = new_pw.text().strip()
            cpw = confirm_pw.text().strip()
            if len(pw) < 6:
                error_lbl.setText("Password must be at least 6 characters.")
                return
            if pw != cpw:
                error_lbl.setText("Passwords do not match.")
                return
            auth.update_user(username, new_password=pw)
            dlg.accept()
            QMessageBox.information(self, "Password Changed",
                                    "Your password has been updated successfully.")

        btn_box.accepted.connect(on_accept)
        btn_box.rejected.connect(dlg.reject)

        result = dlg.exec()
        if result == QDialog.Rejected:
            QMessageBox.warning(self, "Warning",
                                "You are continuing with the default password.\n"
                                "It is strongly recommended to change it.")

    def _show_module_picker(self):
        # Remove old picker/shell if exists
        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        picker = ModulePickerScreen(self.modules, self._enter_module, self.app_state)
        self.central_stack.addWidget(picker)
        self.central_stack.setCurrentIndex(1)

    def _enter_module(self, module):
        # Update session
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, module.module_id)

        # Persist the last active module so the app can restore it on next login
        save_setting("last_active_module", module.module_id)

        # Notify module
        module.on_activate(self.app_state)

        # Remove old picker/shell, add module shell
        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        shell = ModuleShellWidget(module, self.app_state, self._back_to_hub)
        self.central_stack.addWidget(shell)
        self.central_stack.setCurrentIndex(1)

    def _show_people(self):
        """Navigate to the hub-level People & Sites page."""
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, "people")

        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        people_page = HubPeoplePage(self.app_state, on_back=self._back_to_hub)
        self.central_stack.addWidget(people_page)
        self.central_stack.setCurrentIndex(1)

    def _show_analytics(self):
        """Navigate to the hub-level Analytics & Insights page."""
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, "analytics")

        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        analytics_page = HubAnalyticsPage(on_back=self._back_to_hub)
        self.central_stack.addWidget(analytics_page)
        self.central_stack.setCurrentIndex(1)

    def _show_site_comparison(self):
        """Navigate to the hub-level Site Comparison page."""
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, "site_comparison")

        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        from src.pages_site_comparison import SiteComparisonPage

        wrapper = QWidget()
        w_lay = QVBoxLayout(wrapper)
        w_lay.setContentsMargins(0, 0, 0, 0)
        w_lay.setSpacing(0)

        back_bar = QFrame()
        back_bar.setFixedHeight(48)
        back_bar.setStyleSheet(
            f"QFrame {{ background: {tc('card')}; border-bottom: 1px solid {tc('border')}; }}"
        )
        bar_lay = QHBoxLayout(back_bar)
        bar_lay.setContentsMargins(16, 0, 16, 0)
        back_btn = QPushButton("< Back to Hub")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {COLORS['accent']};
                font-weight: 600; font-size: 14px; border: none; padding: 4px 8px; }}
            QPushButton:hover {{ text-decoration: underline; }}
        """)
        back_btn.clicked.connect(self._back_to_hub)
        bar_lay.addWidget(back_btn)
        bar_lay.addStretch()
        w_lay.addWidget(back_bar)

        page = SiteComparisonPage(self.app_state)
        w_lay.addWidget(page)

        self.central_stack.addWidget(wrapper)
        self.central_stack.setCurrentIndex(1)

    def _show_audit(self):
        """Navigate to the hub-level Audit Trail page."""
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, "audit")

        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        from src.hub_audit_viewer import HubAuditViewer
        audit_page = HubAuditViewer(on_back=self._back_to_hub)
        self.central_stack.addWidget(audit_page)
        self.central_stack.setCurrentIndex(1)

    def _show_activity(self):
        """Navigate to the hub-level Recent Activity feed."""
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, "activity")

        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        activity_page = ActivityFeedPage(self.app_state, on_back=self._back_to_hub)
        self.central_stack.addWidget(activity_page)
        self.central_stack.setCurrentIndex(1)

    def _show_backups(self):
        """Navigate to the hub-level Database Backups page."""
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, "backups")

        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        from src.hub_backups import HubBackupsPage
        backups_page = HubBackupsPage(on_back=self._back_to_hub)
        self.central_stack.addWidget(backups_page)
        self.central_stack.setCurrentIndex(1)

    def _show_task_queue(self):
        """Navigate to the hub-level Supervisor Task Queue page."""
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, "task_queue")

        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        task_page = TaskQueuePage(self.app_state, on_back=self._back_to_hub)
        self.central_stack.addWidget(task_page)
        self.central_stack.setCurrentIndex(1)

    def _show_announcements(self):
        """Navigate to the hub-level Announcements page."""
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, "announcements")

        while self.central_stack.count() > 1:
            w = self.central_stack.widget(1)
            self.central_stack.removeWidget(w)
            w.deleteLater()

        announcements_page = AnnouncementsPage(self.app_state, on_back=self._back_to_hub)
        self.central_stack.addWidget(announcements_page)
        self.central_stack.setCurrentIndex(1)

    def _shortcut_module(self, index):
        """Ctrl+1-5: switch to the module at that index in REGISTERED_MODULES."""
        current = self.central_stack.currentWidget()
        # Only work after login (not on login screen)
        if current is self.login_screen:
            return
        if index < len(self.modules):
            self._enter_module(self.modules[index])

    def _shortcut_back(self):
        from src.hub_audit_viewer import HubAuditViewer
        current = self.central_stack.currentWidget()
        if isinstance(current, (ModuleShellWidget, HubPeoplePage, HubAnalyticsPage, HubAuditViewer, ActivityFeedPage, AnnouncementsPage, TaskQueuePage)):
            self._back_to_hub()

    def _back_to_hub(self):
        if self.session_id:
            session_manager.heartbeat_session(self.session_id, "")
        self._show_module_picker()

    def _heartbeat(self):
        if self.session_id:
            session_manager.heartbeat_session(self.session_id)

    def closeEvent(self, event):
        """Clean up session and companion server on close."""
        if self.session_id:
            try:
                session_manager.remove_session(self.session_id)
            except Exception:
                pass
        self._heartbeat_timer.stop()
        # Stop backup scheduler if running
        if hasattr(self, '_backup_scheduler') and self._backup_scheduler:
            self._backup_scheduler.stop()
        stop_companion_server()
        event.accept()
