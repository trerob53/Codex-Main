"""
Cerasus Hub -- Recent Activity Feed Page
Hub-level page showing the last 100 audit log events across all modules.
"""

import json
from datetime import datetime, timezone, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QComboBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer

from src.config import COLORS, tc, btn_style
from src.database import get_conn


# ---------------------------------------------------------------------------
# Module color mapping
# ---------------------------------------------------------------------------

MODULE_COLORS = {
    "operations": "#2563EB",   # blue
    "uniforms": "#7C3AED",     # purple
    "attendance": "#059669",   # green
    "training": "#D97706",     # amber
    "da_generator": "#C8102E", # red (accent)
    "hub": "#6B7280",          # gray
}

MODULE_DISPLAY_NAMES = {
    "operations": "Operations",
    "uniforms": "Uniforms",
    "attendance": "Attendance",
    "training": "Training",
    "da_generator": "DA Generator",
    "hub": "Hub",
}


# ---------------------------------------------------------------------------
# Human-readable event descriptions
# ---------------------------------------------------------------------------

def _parse_details(details_str: str) -> dict:
    """Try to parse a details string as JSON; return dict or empty."""
    if not details_str:
        return {}
    try:
        return json.loads(details_str)
    except (json.JSONDecodeError, TypeError):
        return {"raw": details_str}


def humanize_event(event_type: str, details_str: str, module: str) -> str:
    """Convert event_type + details into a human-readable sentence."""
    d = _parse_details(details_str)

    # Helper to pull a name-like field from details
    name = (
        d.get("employee_name")
        or d.get("officer_name")
        or d.get("name")
        or d.get("employee")
        or d.get("officer")
        or ""
    )

    mapping = {
        # Infractions / attendance
        "infraction_created": f"Logged a {d.get('type', 'infraction')} for {name}" if name else "Logged an infraction",
        "infraction_updated": f"Updated infraction for {name}" if name else "Updated an infraction",
        "infraction_deleted": f"Removed infraction for {name}" if name else "Removed an infraction",

        # DA Generator
        "da_created": f"Created a new DA for {name}" if name else "Created a new DA",
        "da_updated": f"Updated DA for {name}" if name else "Updated a DA",
        "da_deleted": f"Deleted DA for {name}" if name else "Deleted a DA",
        "da_exported": f"Exported DA for {name}" if name else "Exported a DA",

        # Officers / people
        "officer_created": f"Added new officer: {name}" if name else "Added a new officer",
        "officer_updated": f"Updated officer record: {name}" if name else "Updated an officer record",
        "officer_deleted": f"Removed officer: {name}" if name else "Removed an officer",

        # Sites
        "site_created": f"Added new site: {d.get('site_name', name)}" if (d.get('site_name') or name) else "Added a new site",
        "site_updated": f"Updated site: {d.get('site_name', name)}" if (d.get('site_name') or name) else "Updated a site",

        # Uniforms
        "uniform_issued": f"Issued uniform to {name}" if name else "Issued a uniform",
        "uniform_returned": f"Received uniform return from {name}" if name else "Received a uniform return",
        "inventory_updated": f"Updated uniform inventory" + (f": {d.get('item', '')}" if d.get('item') else ""),
        "order_created": "Created a new uniform order",
        "order_updated": "Updated a uniform order",

        # Training
        "training_created": f"Created training record for {name}" if name else "Created a training record",
        "training_completed": f"Marked training complete for {name}" if name else "Marked training complete",
        "training_updated": f"Updated training record for {name}" if name else "Updated a training record",
        "cert_created": f"Added certification for {name}" if name else "Added a certification",
        "cert_expired": f"Certification expired for {name}" if name else "A certification expired",

        # Config / settings
        "config_change": f"Updated {d.get('setting', d.get('key', 'a setting'))}",
        "settings_updated": f"Updated {d.get('setting', d.get('key', 'application settings'))}",

        # Auth / session
        "login": "Signed into Cerasus Hub",
        "logout": "Signed out of Cerasus Hub",
        "password_changed": "Changed their password",
        "user_created": f"Created user account: {d.get('username', name)}" if (d.get('username') or name) else "Created a new user account",
        "user_updated": f"Updated user account: {d.get('username', name)}" if (d.get('username') or name) else "Updated a user account",

        # Schedule / operations
        "schedule_created": "Created a new schedule",
        "schedule_updated": "Updated a schedule",
        "shift_assigned": f"Assigned shift to {name}" if name else "Assigned a shift",
        "shift_updated": f"Updated shift for {name}" if name else "Updated a shift",
    }

    result = mapping.get(event_type)
    if result:
        return result

    # Fallback: make event_type human-ish
    fallback = event_type.replace("_", " ").capitalize()
    if d.get("raw"):
        fallback += f" -- {d['raw'][:80]}"
    elif name:
        fallback += f" for {name}"
    return fallback


# ---------------------------------------------------------------------------
# Relative timestamp formatting
# ---------------------------------------------------------------------------

def relative_time(iso_str: str) -> str:
    """Convert ISO timestamp to a relative human-readable string."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return iso_str

    now = datetime.now(timezone.utc)
    diff = now - dt

    seconds = int(diff.total_seconds())
    if seconds < 0:
        return "Just now"
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days == 1:
        try:
            time_fmt = dt.astimezone().strftime("%#I:%M %p")  # Windows
        except ValueError:
            time_fmt = dt.astimezone().strftime("%-I:%M %p")  # Linux/Mac
        return f"Yesterday at {time_fmt}"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    return dt.astimezone().strftime("%b %d, %Y")


# ---------------------------------------------------------------------------
# Classify action type from event_type string
# ---------------------------------------------------------------------------

def _classify_action(event_type: str) -> str:
    """Classify an event_type into Create/Update/Delete/Other."""
    et = event_type.lower()
    if any(k in et for k in ("created", "create", "added", "issued", "login", "assigned")):
        return "Create"
    if any(k in et for k in ("updated", "update", "changed", "change", "completed")):
        return "Update"
    if any(k in et for k in ("deleted", "delete", "removed", "returned", "expired", "logout")):
        return "Delete"
    return "Other"


# ---------------------------------------------------------------------------
# Activity Feed Page
# ---------------------------------------------------------------------------

class ActivityFeedPage(QWidget):
    """Hub-level Recent Activity feed showing audit log events."""

    def __init__(self, app_state: dict, on_back=None, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.on_back = on_back
        self._all_events = []
        self._build()
        self._load_events()

    # -- Build UI ----------------------------------------------------------

    def _build(self):
        self.setStyleSheet(f"background: {tc('bg')};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Top bar ----
        top_bar = QFrame()
        top_bar.setFixedHeight(56)
        top_bar.setStyleSheet(f"""
            QFrame {{ background: {tc('card')}; border-bottom: 1px solid {tc('border')}; }}
        """)
        tb_lay = QHBoxLayout(top_bar)
        tb_lay.setContentsMargins(20, 0, 20, 0)

        back_btn = QPushButton("< Back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedHeight(36)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {COLORS['accent']};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ text-decoration: underline; }}
        """)
        back_btn.clicked.connect(self._go_back)
        tb_lay.addWidget(back_btn)

        title = QLabel("RECENT ACTIVITY")
        title.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 600;
            letter-spacing: 3px; background: transparent;
        """)
        tb_lay.addWidget(title)
        tb_lay.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setFixedHeight(32)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                border: none; border-radius: 4px;
                padding: 0 16px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 500;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        refresh_btn.clicked.connect(self._load_events)
        tb_lay.addWidget(refresh_btn)

        root.addWidget(top_bar)

        # ---- Filter bar ----
        filter_bar = QFrame()
        filter_bar.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border-bottom: 1px solid {tc('border')};
                padding: 8px 20px;
            }}
        """)
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(20, 8, 20, 8)
        fb_lay.setSpacing(16)

        combo_style = f"""
            QComboBox {{
                background: {tc('bg')};
                color: {tc('text')};
                border: 1px solid {tc('border')};
                border-radius: 6px;
                padding: 6px 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                min-width: 140px;
            }}
            QComboBox:hover {{
                border-color: {COLORS['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background: {tc('card')};
                color: {tc('text')};
                selection-background-color: {COLORS['accent']};
                selection-color: white;
                border: 1px solid {tc('border')};
            }}
        """

        # Module filter
        mod_label = QLabel("Module:")
        mod_label.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; background: transparent;")
        fb_lay.addWidget(mod_label)

        self.cmb_module = QComboBox()
        self.cmb_module.addItems([
            "All", "Operations", "Uniforms", "Attendance",
            "Training", "DA Generator", "Hub",
        ])
        self.cmb_module.setStyleSheet(combo_style)
        self.cmb_module.currentIndexChanged.connect(self._apply_filters)
        fb_lay.addWidget(self.cmb_module)

        # Action type filter
        act_label = QLabel("Action:")
        act_label.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; background: transparent;")
        fb_lay.addWidget(act_label)

        self.cmb_action = QComboBox()
        self.cmb_action.addItems(["All", "Create", "Update", "Delete"])
        self.cmb_action.setStyleSheet(combo_style)
        self.cmb_action.currentIndexChanged.connect(self._apply_filters)
        fb_lay.addWidget(self.cmb_action)

        # Date range filter
        date_label = QLabel("Period:")
        date_label.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; background: transparent;")
        fb_lay.addWidget(date_label)

        self.cmb_date = QComboBox()
        self.cmb_date.addItems(["All Time", "Today", "Last 7 Days", "Last 30 Days"])
        self.cmb_date.setStyleSheet(combo_style)
        self.cmb_date.currentIndexChanged.connect(self._apply_filters)
        fb_lay.addWidget(self.cmb_date)

        fb_lay.addStretch()

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 12px; background: transparent;
        """)
        fb_lay.addWidget(self.lbl_count)

        root.addWidget(filter_bar)

        # ---- Scrollable feed area ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {tc('bg')}; border: none; }}")

        self._feed_container = QWidget()
        self._feed_container.setStyleSheet(f"background: {tc('bg')};")
        self._feed_layout = QVBoxLayout(self._feed_container)
        self._feed_layout.setContentsMargins(20, 16, 20, 16)
        self._feed_layout.setSpacing(6)
        self._feed_layout.addStretch()

        scroll.setWidget(self._feed_container)
        root.addWidget(scroll)

    # -- Data loading ------------------------------------------------------

    def _load_events(self):
        """Fetch the latest 100 audit events from the database."""
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
            conn.close()
            self._all_events = [dict(r) for r in rows]
        except Exception:
            self._all_events = []
        self._apply_filters()

    # -- Filtering ---------------------------------------------------------

    def _apply_filters(self):
        """Filter cached events and rebuild the feed."""
        module_filter = self.cmb_module.currentText()
        action_filter = self.cmb_action.currentText()
        date_filter = self.cmb_date.currentText()

        filtered = list(self._all_events)

        # Module filter
        if module_filter != "All":
            # Map display name back to module_name key
            rev_map = {v: k for k, v in MODULE_DISPLAY_NAMES.items()}
            mod_key = rev_map.get(module_filter, module_filter.lower().replace(" ", "_"))
            filtered = [e for e in filtered if e.get("module_name", "").lower() == mod_key]

        # Action type filter
        if action_filter != "All":
            filtered = [e for e in filtered if _classify_action(e.get("event_type", "")) == action_filter]

        # Date range filter
        if date_filter != "All Time":
            now = datetime.now(timezone.utc)
            if date_filter == "Today":
                cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif date_filter == "Last 7 Days":
                cutoff = now - timedelta(days=7)
            elif date_filter == "Last 30 Days":
                cutoff = now - timedelta(days=30)
            else:
                cutoff = None

            if cutoff:
                def _after_cutoff(e):
                    ts = e.get("timestamp", "")
                    if not ts:
                        return False
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt >= cutoff
                    except (ValueError, TypeError):
                        return False
                filtered = [e for e in filtered if _after_cutoff(e)]

        self._rebuild_feed(filtered)

    # -- Feed rendering ----------------------------------------------------

    def _rebuild_feed(self, events: list):
        """Clear and rebuild the feed with the given event list."""
        # Clear existing cards
        while self._feed_layout.count():
            item = self._feed_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self.lbl_count.setText(f"{len(events)} event{'s' if len(events) != 1 else ''}")

        if not events:
            empty = QLabel("No activity found for the selected filters.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; padding: 40px;
                background: transparent;
            """)
            self._feed_layout.addWidget(empty)
            self._feed_layout.addStretch()
            return

        for ev in events:
            card = self._make_event_card(ev)
            self._feed_layout.addWidget(card)

        self._feed_layout.addStretch()

    def _make_event_card(self, ev: dict) -> QFrame:
        """Build a single event card widget."""
        module = ev.get("module_name", "hub").lower()
        color = MODULE_COLORS.get(module, "#6B7280")
        display_module = MODULE_DISPLAY_NAMES.get(module, module.replace("_", " ").title())

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-left: 4px solid {color};
                border-radius: 6px;
                padding: 12px 16px;
            }}
        """)

        h_lay = QHBoxLayout(card)
        h_lay.setContentsMargins(8, 6, 8, 6)
        h_lay.setSpacing(12)

        # Colored dot
        dot = QFrame()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"""
            background: {color};
            border-radius: 5px;
            border: none;
        """)
        h_lay.addWidget(dot, 0, Qt.AlignTop)

        # Text column
        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        # Description line
        description = humanize_event(
            ev.get("event_type", ""),
            ev.get("details", ""),
            module,
        )
        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px; font-weight: 500;
            background: transparent;
        """)
        text_col.addWidget(desc_lbl)

        # Meta line: username, relative time, module badge
        meta_lay = QHBoxLayout()
        meta_lay.setSpacing(8)

        username = ev.get("username", "System")
        user_lbl = QLabel(username)
        user_lbl.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px; font-weight: 600;
            background: transparent;
        """)
        meta_lay.addWidget(user_lbl)

        sep = QLabel("--")
        sep.setStyleSheet(f"color: {tc('border')}; font-size: 11px; background: transparent;")
        meta_lay.addWidget(sep)

        time_str = relative_time(ev.get("timestamp", ""))
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 11px;
            background: transparent;
        """)
        meta_lay.addWidget(time_lbl)

        meta_lay.addStretch()

        # Module tag badge
        tag = QLabel(f"  {display_module}  ")
        tag.setStyleSheet(f"""
            color: white;
            background: {color};
            border-radius: 3px;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10px; font-weight: 600;
            letter-spacing: 0.5px;
            padding: 2px 6px;
        """)
        meta_lay.addWidget(tag)

        text_col.addLayout(meta_lay)
        h_lay.addLayout(text_col, 1)

        return card

    # -- Navigation --------------------------------------------------------

    def _go_back(self):
        if self.on_back:
            self.on_back()
