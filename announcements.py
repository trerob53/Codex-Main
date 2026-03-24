"""
Cerasus Hub — Internal Announcements Board
Database functions and UI for company-wide and site-specific announcements.
"""

import json
import uuid
from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QDialog, QLineEdit, QTextEdit, QComboBox, QCheckBox,
    QDateEdit, QMessageBox, QSizePolicy, QGroupBox, QGridLayout,
)
from PySide6.QtCore import Qt, QDate

from src.config import COLORS, ROLE_ADMIN, tc, btn_style, build_dialog_stylesheet, _is_dark
from src.database import get_conn


# ── Constants ─────────────────────────────────────────────────────────

CATEGORIES = ["General", "Policy Change", "Schedule Update", "Holiday Notice", "Safety Alert", "Training"]
PRIORITIES = ["Normal", "Important", "Urgent"]

PRIORITY_COLORS = {
    "Urgent": COLORS["danger"],
    "Important": COLORS["warning"],
    "Normal": COLORS["info"],
}

CATEGORY_COLORS = {
    "General": "#6B7280",
    "Policy Change": "#7C3AED",
    "Schedule Update": "#2563EB",
    "Holiday Notice": "#059669",
    "Safety Alert": "#C8102E",
    "Training": "#D97706",
}


# ── Database Functions ────────────────────────────────────────────────

def ensure_announcements_tables():
    """Create announcements tables if they do not exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS announcements (
            announcement_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            target_sites TEXT DEFAULT '',
            priority TEXT DEFAULT 'Normal',
            pinned INTEGER DEFAULT 0,
            expires_at TEXT DEFAULT '',
            posted_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS announcement_reads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            announcement_id TEXT NOT NULL,
            username TEXT NOT NULL,
            read_at TEXT NOT NULL,
            UNIQUE(announcement_id, username)
        );
    """)
    conn.commit()
    conn.close()


def create_announcement(title, content, category="General", target_sites=None,
                        priority="Normal", pinned=False, expires_at="", posted_by="") -> str:
    """Create a new announcement and return its ID."""
    ensure_announcements_tables()
    aid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    sites_json = json.dumps(target_sites) if target_sites else ""
    conn = get_conn()
    conn.execute(
        """INSERT INTO announcements
           (announcement_id, title, content, category, target_sites, priority, pinned, expires_at, posted_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (aid, title, content, category, sites_json, priority, 1 if pinned else 0, expires_at, posted_by, now, now),
    )
    conn.commit()
    conn.close()
    return aid


def get_active_announcements(username, user_sites=None) -> list:
    """Return active (non-expired) announcements filtered by user sites, with read status."""
    ensure_announcements_tables()
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()

    rows = conn.execute(
        """SELECT a.*,
                  CASE WHEN ar.username IS NOT NULL THEN 1 ELSE 0 END as read
           FROM announcements a
           LEFT JOIN announcement_reads ar
               ON a.announcement_id = ar.announcement_id AND ar.username = ?
           WHERE (a.expires_at = '' OR a.expires_at IS NULL OR a.expires_at > ?)
           ORDER BY a.pinned DESC, a.created_at DESC""",
        (username, now),
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        row = dict(r)
        # Filter by target_sites
        target = row.get("target_sites", "")
        if target:
            try:
                sites_list = json.loads(target)
            except (json.JSONDecodeError, TypeError):
                sites_list = []
            if sites_list:
                # If user has assigned sites, check overlap; if user_sites is empty, they see everything
                if user_sites:
                    if not any(s in user_sites for s in sites_list):
                        continue
        row["read"] = bool(row["read"])
        results.append(row)

    return results


def mark_read(announcement_id, username):
    """Mark an announcement as read for a user."""
    ensure_announcements_tables()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO announcement_reads (announcement_id, username, read_at) VALUES (?, ?, ?)",
        (announcement_id, username, now),
    )
    conn.commit()
    conn.close()


def get_unread_count(username, user_sites=None) -> int:
    """Get count of unread, non-expired announcements for a user."""
    announcements = get_active_announcements(username, user_sites)
    return sum(1 for a in announcements if not a["read"])


def delete_announcement(announcement_id):
    """Delete an announcement and its read records."""
    ensure_announcements_tables()
    conn = get_conn()
    conn.execute("DELETE FROM announcement_reads WHERE announcement_id = ?", (announcement_id,))
    conn.execute("DELETE FROM announcements WHERE announcement_id = ?", (announcement_id,))
    conn.commit()
    conn.close()


# ── Post Announcement Dialog ─────────────────────────────────────────

class PostAnnouncementDialog(QDialog):
    """Dialog for admin users to create a new announcement."""

    def __init__(self, posted_by, parent=None):
        super().__init__(parent)
        self.posted_by = posted_by
        self.result_id = None
        self.setWindowTitle("Post Announcement")
        self.setMinimumSize(520, 560)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("POST ANNOUNCEMENT")
        title.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700;
            letter-spacing: 2px;
        """)
        layout.addWidget(title)

        # Title
        lbl = QLabel("Title")
        lbl.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 13px;")
        layout.addWidget(lbl)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Announcement title...")
        self.title_input.setFixedHeight(40)
        layout.addWidget(self.title_input)

        # Content
        lbl2 = QLabel("Content")
        lbl2.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 13px;")
        layout.addWidget(lbl2)
        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText("Write your announcement here...")
        self.content_input.setMinimumHeight(120)
        layout.addWidget(self.content_input)

        # Row: Category + Priority
        row = QHBoxLayout()
        row.setSpacing(16)

        col1 = QVBoxLayout()
        col1_lbl = QLabel("Category")
        col1_lbl.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 13px;")
        col1.addWidget(col1_lbl)
        self.category_combo = QComboBox()
        self.category_combo.addItems(CATEGORIES)
        self.category_combo.setFixedHeight(38)
        col1.addWidget(self.category_combo)
        row.addLayout(col1)

        col2 = QVBoxLayout()
        col2_lbl = QLabel("Priority")
        col2_lbl.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 13px;")
        col2.addWidget(col2_lbl)
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(PRIORITIES)
        self.priority_combo.setFixedHeight(38)
        col2.addWidget(self.priority_combo)
        row.addLayout(col2)

        layout.addLayout(row)

        # Target Sites
        sites_lbl = QLabel("Target Sites")
        sites_lbl.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 13px;")
        layout.addWidget(sites_lbl)

        self.all_sites_cb = QCheckBox("All Sites (company-wide)")
        self.all_sites_cb.setChecked(True)
        self.all_sites_cb.setStyleSheet(f"""
            QCheckBox {{ color: {tc('text')}; font-size: 13px; spacing: 8px; }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border: 2px solid {tc('border')}; border-radius: 4px;
                background: {tc('card')};
            }}
            QCheckBox::indicator:checked {{
                background: {COLORS['accent']}; border-color: {COLORS['accent']};
            }}
        """)
        self.all_sites_cb.toggled.connect(self._toggle_sites)
        layout.addWidget(self.all_sites_cb)

        # Sites checkboxes container
        self.sites_frame = QFrame()
        self.sites_frame.setStyleSheet(f"""
            QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; border-radius: 6px; padding: 8px; }}
        """)
        self.sites_layout = QGridLayout(self.sites_frame)
        self.sites_layout.setContentsMargins(8, 4, 8, 4)
        self.sites_layout.setSpacing(4)
        self.site_checkboxes = []

        # Load sites from DB
        try:
            conn = get_conn()
            sites = conn.execute("SELECT name FROM sites WHERE status = 'Active' ORDER BY name").fetchall()
            conn.close()
            for i, s in enumerate(sites):
                cb = QCheckBox(s["name"])
                cb.setStyleSheet(f"""
                    QCheckBox {{ color: {tc('text')}; font-size: 12px; spacing: 6px; }}
                    QCheckBox::indicator {{
                        width: 16px; height: 16px;
                        border: 2px solid {tc('border')}; border-radius: 3px;
                        background: {tc('card')};
                    }}
                    QCheckBox::indicator:checked {{
                        background: {COLORS['accent']}; border-color: {COLORS['accent']};
                    }}
                """)
                self.site_checkboxes.append(cb)
                self.sites_layout.addWidget(cb, i // 3, i % 3)
        except Exception:
            pass

        self.sites_frame.setVisible(False)
        layout.addWidget(self.sites_frame)

        # Row: Pin + Expiry
        row2 = QHBoxLayout()
        row2.setSpacing(16)

        self.pin_cb = QCheckBox("Pin this announcement")
        self.pin_cb.setStyleSheet(f"""
            QCheckBox {{ color: {tc('text')}; font-size: 13px; spacing: 8px; }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border: 2px solid {tc('border')}; border-radius: 4px;
                background: {tc('card')};
            }}
            QCheckBox::indicator:checked {{
                background: {COLORS['accent']}; border-color: {COLORS['accent']};
            }}
        """)
        row2.addWidget(self.pin_cb)

        row2.addSpacing(16)

        exp_lbl = QLabel("Expires:")
        exp_lbl.setStyleSheet(f"color: {tc('text')}; font-size: 13px; font-weight: 600;")
        row2.addWidget(exp_lbl)

        self.expiry_date = QDateEdit()
        self.expiry_date.setCalendarPopup(True)
        self.expiry_date.setDate(QDate.currentDate().addDays(30))
        self.expiry_date.setFixedHeight(38)
        row2.addWidget(self.expiry_date)

        self.no_expiry_cb = QCheckBox("No expiry")
        self.no_expiry_cb.setChecked(True)
        self.no_expiry_cb.setStyleSheet(f"""
            QCheckBox {{ color: {tc('text')}; font-size: 12px; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 2px solid {tc('border')}; border-radius: 3px;
                background: {tc('card')};
            }}
            QCheckBox::indicator:checked {{
                background: {COLORS['accent']}; border-color: {COLORS['accent']};
            }}
        """)
        self.no_expiry_cb.toggled.connect(lambda checked: self.expiry_date.setEnabled(not checked))
        self.expiry_date.setEnabled(False)
        row2.addWidget(self.no_expiry_cb)

        row2.addStretch()
        layout.addLayout(row2)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        post_btn = QPushButton("Post Announcement")
        post_btn.setCursor(Qt.PointingHandCursor)
        post_btn.setFixedHeight(42)
        post_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 600;
                border-radius: 6px; padding: 0 28px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        post_btn.clicked.connect(self._post)
        btn_row.addWidget(post_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(42)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {tc('border')}; color: {tc('text')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; font-weight: 600;
                border-radius: 6px; padding: 0 28px;
            }}
            QPushButton:hover {{ background: {tc('info_light')}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _toggle_sites(self, checked):
        self.sites_frame.setVisible(not checked)

    def _post(self):
        title = self.title_input.text().strip()
        content = self.content_input.toPlainText().strip()
        if not title:
            QMessageBox.warning(self, "Missing Title", "Please enter a title for the announcement.")
            return
        if not content:
            QMessageBox.warning(self, "Missing Content", "Please enter content for the announcement.")
            return

        category = self.category_combo.currentText()
        priority = self.priority_combo.currentText()
        pinned = self.pin_cb.isChecked()

        expires_at = ""
        if not self.no_expiry_cb.isChecked():
            qdate = self.expiry_date.date()
            expires_at = datetime(qdate.year(), qdate.month(), qdate.day(), 23, 59, 59, tzinfo=timezone.utc).isoformat()

        target_sites = None
        if not self.all_sites_cb.isChecked():
            target_sites = [cb.text() for cb in self.site_checkboxes if cb.isChecked()]
            if not target_sites:
                QMessageBox.warning(self, "No Sites Selected", "Please select at least one site or choose 'All Sites'.")
                return

        self.result_id = create_announcement(
            title=title, content=content, category=category,
            target_sites=target_sites, priority=priority,
            pinned=pinned, expires_at=expires_at, posted_by=self.posted_by,
        )
        self.accept()


# ── Announcements Page ────────────────────────────────────────────────

class AnnouncementsPage(QWidget):
    """Full-page announcements board, accessible from the ModulePickerScreen."""

    def __init__(self, app_state, on_back=None):
        super().__init__()
        self.app_state = app_state
        self.on_back = on_back
        self._build()
        self.refresh()

    def _build(self):
        self.setStyleSheet(f"background: {tc('bg')};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header bar
        header = QFrame()
        header.setFixedHeight(56)
        header.setStyleSheet(f"""
            QFrame {{ background: {tc('card')}; border-bottom: 1px solid {tc('border')}; }}
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(28, 0, 28, 0)

        back_btn = QPushButton("Back to Hub")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedHeight(36)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px; font-weight: 500;
                color: {tc('text_light')}; border: none; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {COLORS['accent']}; }}
        """)
        if self.on_back:
            back_btn.clicked.connect(self.on_back)
        h_lay.addWidget(back_btn)

        h_lay.addSpacing(16)

        page_title = QLabel("ANNOUNCEMENTS")
        page_title.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700;
            letter-spacing: 3px; background: transparent; border: none;
        """)
        h_lay.addWidget(page_title)

        h_lay.addStretch()

        # Post button (admin only)
        user = self.app_state.get("user", {})
        if user.get("role") == ROLE_ADMIN:
            post_btn = QPushButton("Post Announcement")
            post_btn.setCursor(Qt.PointingHandCursor)
            post_btn.setFixedHeight(36)
            post_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['accent']}; color: white;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 13px; font-weight: 600;
                    border-radius: 6px; padding: 0 20px;
                }}
                QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
            """)
            post_btn.clicked.connect(self._open_post_dialog)
            h_lay.addWidget(post_btn)

        outer.addWidget(header)

        # Scrollable feed
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {tc('bg')}; border: none; }}")

        self.feed_container = QWidget()
        self.feed_container.setStyleSheet(f"background: {tc('bg')};")
        self.feed_layout = QVBoxLayout(self.feed_container)
        self.feed_layout.setContentsMargins(40, 24, 40, 24)
        self.feed_layout.setSpacing(12)

        scroll.setWidget(self.feed_container)
        outer.addWidget(scroll)

    def refresh(self):
        """Reload announcements from the database and rebuild the feed."""
        # Clear existing cards
        while self.feed_layout.count():
            child = self.feed_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        user = self.app_state.get("user", {})
        username = user.get("username", "")
        user_sites = self.app_state.get("assigned_sites", [])
        is_admin = user.get("role") == ROLE_ADMIN

        try:
            announcements = get_active_announcements(username, user_sites)
        except Exception:
            announcements = []

        if not announcements:
            empty = QLabel("No announcements at this time.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 15px; padding: 40px;
                background: transparent;
            """)
            self.feed_layout.addWidget(empty)
            self.feed_layout.addStretch()
            return

        for ann in announcements:
            card = self._make_card(ann, is_admin, username)
            self.feed_layout.addWidget(card)

        self.feed_layout.addStretch()

    def _make_card(self, ann, is_admin, username):
        """Build a single announcement card widget."""
        is_read = ann.get("read", False)
        is_pinned = ann.get("pinned", 0)
        priority = ann.get("priority", "Normal")
        category = ann.get("category", "General")

        card = QFrame()
        border_left_color = "#3B82F6" if not is_read else tc("border")
        card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-left: 4px solid {border_left_color};
                border-radius: 8px;
                padding: 16px 20px;
            }}
        """)

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(4, 4, 4, 4)
        card_lay.setSpacing(8)

        # Top row: pin icon, title, badges
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        if is_pinned:
            pin_lbl = QLabel("PIN")
            pin_lbl.setFixedHeight(26)
            pin_lbl.setStyleSheet(f"""
                background: {tc('info_light')}; color: {tc('text')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10px; font-weight: 700;
                letter-spacing: 1px;
                border-radius: 4px; padding: 2px 8px;
            """)
            top_row.addWidget(pin_lbl)

        title_lbl = QLabel(ann.get("title", ""))
        title_lbl.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700;
            background: transparent;
        """)
        title_lbl.setWordWrap(True)
        top_row.addWidget(title_lbl, 1)

        # Category badge
        cat_color = CATEGORY_COLORS.get(category, "#6B7280")
        cat_lbl = QLabel(category.upper())
        cat_lbl.setFixedHeight(26)
        cat_lbl.setStyleSheet(f"""
            background: {cat_color}; color: white;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10px; font-weight: 700;
            letter-spacing: 1px;
            border-radius: 4px; padding: 2px 8px;
        """)
        top_row.addWidget(cat_lbl)

        # Priority badge
        if priority != "Normal":
            pri_color = PRIORITY_COLORS.get(priority, COLORS["info"])
            pri_lbl = QLabel(priority.upper())
            pri_lbl.setFixedHeight(26)
            pri_lbl.setStyleSheet(f"""
                background: {pri_color}; color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10px; font-weight: 700;
                letter-spacing: 1px;
                border-radius: 4px; padding: 2px 8px;
            """)
            top_row.addWidget(pri_lbl)

        card_lay.addLayout(top_row)

        # Content
        content_lbl = QLabel(ann.get("content", ""))
        content_lbl.setWordWrap(True)
        content_lbl.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px; line-height: 1.5;
            background: transparent;
        """)
        card_lay.addWidget(content_lbl)

        # Footer row: posted by, date, actions
        footer_row = QHBoxLayout()
        footer_row.setSpacing(12)

        # Parse date
        created = ann.get("created_at", "")
        try:
            dt = datetime.fromisoformat(created)
            date_str = dt.strftime("%b %d, %Y at %I:%M %p")
        except Exception:
            date_str = created

        meta_lbl = QLabel(f"Posted by {ann.get('posted_by', 'Unknown')} on {date_str}")
        meta_lbl.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 12px; background: transparent;
        """)
        footer_row.addWidget(meta_lbl)

        # Target sites info
        target = ann.get("target_sites", "")
        if target:
            try:
                sites_list = json.loads(target)
                if sites_list:
                    sites_str = ", ".join(sites_list[:3])
                    if len(sites_list) > 3:
                        sites_str += f" +{len(sites_list) - 3} more"
                    site_lbl = QLabel(f"Sites: {sites_str}")
                    site_lbl.setStyleSheet(f"""
                        color: {tc('text_light')};
                        font-family: 'Segoe UI', Arial, sans-serif;
                        font-size: 11px; background: transparent;
                    """)
                    footer_row.addWidget(site_lbl)
            except Exception:
                pass

        footer_row.addStretch()

        # Mark as Read button
        ann_id = ann.get("announcement_id", "")
        if not is_read:
            read_btn = QPushButton("Mark as Read")
            read_btn.setCursor(Qt.PointingHandCursor)
            read_btn.setFixedHeight(28)
            read_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {tc('border')}; color: {tc('text')};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 11px; font-weight: 600;
                    border-radius: 4px; padding: 0 12px;
                }}
                QPushButton:hover {{ background: {COLORS['accent']}; color: white; }}
            """)
            read_btn.clicked.connect(lambda checked=False, a=ann_id, u=username: self._mark_read(a, u))
            footer_row.addWidget(read_btn)
        else:
            read_indicator = QLabel("READ")
            read_indicator.setFixedHeight(26)
            read_indicator.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10px; font-weight: 600;
                letter-spacing: 1px; background: transparent;
            """)
            footer_row.addWidget(read_indicator)

        # Delete button (admin only)
        if is_admin:
            del_btn = QPushButton("Delete")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setFixedHeight(28)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {COLORS['danger']};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 11px; font-weight: 600;
                    border: 1px solid {COLORS['danger']};
                    border-radius: 4px; padding: 0 12px;
                }}
                QPushButton:hover {{ background: {COLORS['danger']}; color: white; }}
            """)
            del_btn.clicked.connect(lambda checked=False, a=ann_id: self._delete(a))
            footer_row.addWidget(del_btn)

        card_lay.addLayout(footer_row)
        return card

    def _mark_read(self, announcement_id, username):
        try:
            mark_read(announcement_id, username)
        except Exception:
            pass
        self.refresh()

    def _delete(self, announcement_id):
        reply = QMessageBox.question(
            self, "Delete Announcement",
            "Are you sure you want to delete this announcement?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                delete_announcement(announcement_id)
            except Exception:
                pass
            self.refresh()

    def _open_post_dialog(self):
        user = self.app_state.get("user", {})
        username = user.get("username", "")
        dlg = PostAnnouncementDialog(posted_by=username, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.refresh()
