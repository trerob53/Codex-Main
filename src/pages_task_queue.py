"""
Cerasus Hub -- Supervisor Task Queue
Auto-populated to-do list that scans the database for actionable items
and also supports manually created tasks.
"""

import uuid
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QComboBox, QDialog, QLineEdit,
    QTextEdit, QDateEdit, QDialogButtonBox, QSizePolicy, QMessageBox,
)
from PySide6.QtCore import Qt, QDate

from src.config import COLORS, tc, btn_style, build_dialog_stylesheet, _is_dark
from src.database import get_conn


# ── Database bootstrap ────────────────────────────────────────────────

def ensure_task_queue_table():
    """Create the supervisor_tasks table if it doesn't exist."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_tasks (
            task_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'normal',
            due_date TEXT DEFAULT '',
            assigned_to TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            source TEXT DEFAULT 'manual',
            source_module TEXT DEFAULT '',
            source_record_id TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            completed_at TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Auto-task generation ──────────────────────────────────────────────

def generate_auto_tasks() -> list[dict]:
    """Scan the database and generate automatic task items."""
    tasks = []
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    conn = get_conn()

    # 1. DAs pending review
    try:
        rows = conn.execute(
            "SELECT da_id, employee_name, created_at FROM da_records "
            "WHERE status = 'pending_review'"
        ).fetchall()
        for r in rows:
            age_days = 0
            try:
                created = datetime.strptime(r["created_at"][:10], "%Y-%m-%d")
                age_days = (now - created).days
            except Exception:
                pass
            priority = "high" if age_days > 3 else "normal"
            tasks.append({
                "title": f"Review DA for {r['employee_name'] or 'Unknown'}",
                "description": f"DA {r['da_id'][:8]}... has been pending review for {age_days} day(s).",
                "priority": priority,
                "due_date": "",
                "source": "auto",
                "source_module": "da_generator",
                "source_record_id": r["da_id"],
            })
    except Exception:
        pass

    # 2. DAs pending delivery (completed but not delivered)
    try:
        rows = conn.execute(
            "SELECT da_id, employee_name FROM da_records "
            "WHERE status = 'completed' AND (delivered_at IS NULL OR delivered_at = '')"
        ).fetchall()
        for r in rows:
            tasks.append({
                "title": f"Deliver DA to {r['employee_name'] or 'Unknown'}",
                "description": f"DA {r['da_id'][:8]}... is completed but not yet delivered.",
                "priority": "normal",
                "due_date": "",
                "source": "auto",
                "source_module": "da_generator",
                "source_record_id": r["da_id"],
            })
    except Exception:
        pass

    # 3. DAs pending acknowledgment (delivered but not acknowledged)
    try:
        rows = conn.execute(
            "SELECT da_id, employee_name FROM da_records "
            "WHERE delivered_at IS NOT NULL AND delivered_at != '' "
            "AND (acknowledged IS NULL OR acknowledged = 0)"
        ).fetchall()
        for r in rows:
            tasks.append({
                "title": f"Get acknowledgment from {r['employee_name'] or 'Unknown'}",
                "description": f"DA {r['da_id'][:8]}... was delivered but not yet acknowledged.",
                "priority": "normal",
                "due_date": "",
                "source": "auto",
                "source_module": "da_generator",
                "source_record_id": r["da_id"],
            })
    except Exception:
        pass

    # 4. 30-day follow-ups for Written or Final Warnings (25-35 days ago)
    try:
        date_35 = (now - timedelta(days=35)).strftime("%Y-%m-%d")
        date_25 = (now - timedelta(days=25)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT da_id, employee_name, discipline_level, delivered_at FROM da_records "
            "WHERE discipline_level IN ('Written Warning', 'Final Warning') "
            "AND delivered_at >= ? AND delivered_at <= ?",
            (date_35, date_25),
        ).fetchall()
        for r in rows:
            tasks.append({
                "title": f"30-day follow-up review for {r['employee_name'] or 'Unknown'}",
                "description": f"{r['discipline_level']} delivered on {r['delivered_at'][:10]}. "
                               f"Follow-up window is now open.",
                "priority": "high",
                "due_date": "",
                "source": "auto",
                "source_module": "da_generator",
                "source_record_id": r["da_id"],
            })
    except Exception:
        pass

    # 5. Expiring points review (points expiring in next 7 days)
    try:
        expire_cutoff = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT i.id, i.employee_id, i.point_expiry_date, i.points_assigned, "
            "o.name AS officer_name "
            "FROM ats_infractions i "
            "LEFT JOIN officers o ON i.employee_id = o.officer_id "
            "WHERE i.points_active = 1 "
            "AND i.point_expiry_date != '' "
            "AND i.point_expiry_date <= ? "
            "AND i.point_expiry_date >= ?",
            (expire_cutoff, today_str),
        ).fetchall()
        for r in rows:
            name = r["officer_name"] or r["employee_id"] or "Unknown"
            tasks.append({
                "title": f"Review expiring points for {name}",
                "description": f"{r['points_assigned']} point(s) expiring on {r['point_expiry_date']}.",
                "priority": "normal",
                "due_date": r["point_expiry_date"],
                "source": "auto",
                "source_module": "attendance",
                "source_record_id": str(r["id"]),
            })
    except Exception:
        pass

    # 6. Officers near threshold (5.5+, 7.5+, 9.5+ active points)
    try:
        rows = conn.execute(
            "SELECT officer_id, name, active_points FROM officers "
            "WHERE active_points >= 5.5 AND status = 'Active' "
            "ORDER BY active_points DESC"
        ).fetchall()
        for r in rows:
            pts = r["active_points"] or 0
            if pts >= 9.5:
                level = "Termination"
                priority = "high"
            elif pts >= 7.5:
                level = "Final Warning"
                priority = "high"
            else:
                level = "Written Warning"
                priority = "normal"
            tasks.append({
                "title": f"Monitor {r['name'] or 'Unknown'} -- approaching {level}",
                "description": f"Currently at {pts} active points.",
                "priority": priority,
                "due_date": "",
                "source": "auto",
                "source_module": "attendance",
                "source_record_id": r["officer_id"],
            })
    except Exception:
        pass

    conn.close()
    return tasks


# ── Helpers ───────────────────────────────────────────────────────────

_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
_PRIORITY_COLORS = {
    "high": lambda: COLORS["danger"],
    "normal": lambda: COLORS["info"],
    "low": lambda: tc("text_light"),
}
_SOURCE_COLORS = {
    "da_generator": "#7C3AED",
    "attendance": "#374151",
    "manual": COLORS["accent"],
}


def _get_users() -> list[str]:
    """Return list of active usernames for the assign-to dropdown."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT username FROM users WHERE active = 1 ORDER BY username"
        ).fetchall()
        return [r["username"] for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ── Add Task Dialog ───────────────────────────────────────────────────

class AddTaskDialog(QDialog):
    """Dialog for creating a manual supervisor task."""

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.setWindowTitle("Add Task")
        self.setMinimumWidth(460)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title_label = QLabel("ADD TASK")
        title_label.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700; letter-spacing: 2px;
        """)
        lay.addWidget(title_label)

        # Title
        lay.addWidget(QLabel("Title"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Task title...")
        lay.addWidget(self.title_input)

        # Description
        lay.addWidget(QLabel("Description"))
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("Optional details...")
        self.desc_input.setMaximumHeight(80)
        lay.addWidget(self.desc_input)

        # Priority
        lay.addWidget(QLabel("Priority"))
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["Normal", "High", "Low"])
        lay.addWidget(self.priority_combo)

        # Due date
        lay.addWidget(QLabel("Due Date"))
        self.due_date_edit = QDateEdit()
        self.due_date_edit.setCalendarPopup(True)
        self.due_date_edit.setDate(QDate.currentDate().addDays(7))
        self.due_date_edit.setSpecialValueText("No due date")
        lay.addWidget(self.due_date_edit)

        # Assign to
        lay.addWidget(QLabel("Assign To"))
        self.assign_combo = QComboBox()
        self.assign_combo.addItem("")  # blank = unassigned
        for u in _get_users():
            self.assign_combo.addItem(u)
        lay.addWidget(self.assign_combo)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def get_task(self) -> dict | None:
        title = self.title_input.text().strip()
        if not title:
            return None
        user = self.app_state.get("user", {})
        return {
            "task_id": str(uuid.uuid4()),
            "title": title,
            "description": self.desc_input.toPlainText().strip(),
            "priority": self.priority_combo.currentText().lower(),
            "due_date": self.due_date_edit.date().toString("yyyy-MM-dd"),
            "assigned_to": self.assign_combo.currentText(),
            "status": "open",
            "source": "manual",
            "source_module": "",
            "source_record_id": "",
            "created_by": user.get("username", ""),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


# ── Task Queue Page ───────────────────────────────────────────────────

class TaskQueuePage(QWidget):
    """Supervisor Task Queue -- hub-level page."""

    def __init__(self, app_state, on_back=None, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._on_back = on_back
        self._filter_priority = "All"
        self._filter_status = "Open"
        self._filter_source = "All"
        ensure_task_queue_table()
        self._build()
        self.refresh()

    # ── Build UI ──────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top bar
        top_bar = QFrame()
        top_bar.setFixedHeight(52)
        top_bar.setStyleSheet(f"""
            QFrame {{ background: {tc('card')}; border-bottom: 1px solid {tc('border')}; }}
        """)
        tb_lay = QHBoxLayout(top_bar)
        tb_lay.setContentsMargins(20, 0, 20, 0)

        back_btn = QPushButton("< Back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px; font-weight: 600; border: none;
            }}
            QPushButton:hover {{ color: {COLORS['accent']}; }}
        """)
        back_btn.clicked.connect(self._go_back)
        tb_lay.addWidget(back_btn)

        page_title = QLabel("SUPERVISOR TASK QUEUE")
        page_title.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px; font-weight: 700; letter-spacing: 2px;
            background: transparent;
        """)
        tb_lay.addWidget(page_title)
        tb_lay.addStretch()

        add_btn = QPushButton("+ Add Task")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedHeight(34)
        add_btn.setStyleSheet(btn_style(COLORS['accent'], "white", COLORS['accent_hover']))
        add_btn.clicked.connect(self._add_task)
        tb_lay.addWidget(add_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setFixedHeight(34)
        refresh_btn.setStyleSheet(btn_style(tc('border'), tc('text')))
        refresh_btn.clicked.connect(self.refresh)
        tb_lay.addWidget(refresh_btn)

        outer.addWidget(top_bar)

        # Main content scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {tc('bg')}; border: none; }}")

        content = QWidget()
        content.setStyleSheet(f"background: {tc('bg')};")
        self._content_lay = QVBoxLayout(content)
        self._content_lay.setContentsMargins(28, 20, 28, 20)
        self._content_lay.setSpacing(16)

        # Summary bar
        self._summary_frame = QFrame()
        self._summary_frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
                padding: 14px 24px;
            }}
        """)
        summary_lay = QHBoxLayout(self._summary_frame)
        summary_lay.setSpacing(32)

        self._lbl_open = self._make_kpi("Open Tasks", "0", COLORS["info"])
        self._lbl_high = self._make_kpi("High Priority", "0", COLORS["danger"])
        self._lbl_overdue = self._make_kpi("Overdue", "0", COLORS["warning"])
        summary_lay.addWidget(self._lbl_open["widget"])
        summary_lay.addWidget(self._lbl_high["widget"])
        summary_lay.addWidget(self._lbl_overdue["widget"])
        summary_lay.addStretch()

        self._content_lay.addWidget(self._summary_frame)

        # Filters row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)

        filter_row.addWidget(QLabel("Priority:"))
        self._combo_priority = QComboBox()
        self._combo_priority.addItems(["All", "High", "Normal", "Low"])
        self._combo_priority.setFixedWidth(110)
        self._combo_priority.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._combo_priority)

        filter_row.addWidget(QLabel("Status:"))
        self._combo_status = QComboBox()
        self._combo_status.addItems(["Open", "Completed"])
        self._combo_status.setFixedWidth(120)
        self._combo_status.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._combo_status)

        filter_row.addWidget(QLabel("Source:"))
        self._combo_source = QComboBox()
        self._combo_source.addItems(["All", "Auto", "Manual"])
        self._combo_source.setFixedWidth(110)
        self._combo_source.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._combo_source)

        filter_row.addStretch()
        self._content_lay.addLayout(filter_row)

        # Task list container
        self._task_list_widget = QWidget()
        self._task_list_widget.setStyleSheet(f"background: {tc('bg')};")
        self._task_list_lay = QVBoxLayout(self._task_list_widget)
        self._task_list_lay.setContentsMargins(0, 0, 0, 0)
        self._task_list_lay.setSpacing(8)

        self._content_lay.addWidget(self._task_list_widget)
        self._content_lay.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── KPI helper ────────────────────────────────────────────────────

    def _make_kpi(self, label: str, value: str, color: str) -> dict:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(f"""
            color: {color};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 22px; font-weight: 700;
            background: transparent;
        """)
        lay.addWidget(val_lbl)

        desc_lbl = QLabel(label)
        desc_lbl.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 12px; font-weight: 600;
            letter-spacing: 1px; text-transform: uppercase;
            background: transparent;
        """)
        lay.addWidget(desc_lbl)

        return {"widget": w, "value_label": val_lbl}

    # ── Data loading ─────────────────────────────────────────────────

    def _load_manual_tasks(self) -> list[dict]:
        """Load manual tasks from the database."""
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM supervisor_tasks ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def _apply_filters(self, tasks: list[dict]) -> list[dict]:
        """Filter the combined task list based on current combo selections."""
        result = []
        for t in tasks:
            # Status filter
            status = t.get("status", "open")
            if self._filter_status == "Open" and status != "open":
                continue
            if self._filter_status == "Completed" and status != "completed":
                continue

            # Priority filter
            if self._filter_priority != "All":
                if t.get("priority", "normal").lower() != self._filter_priority.lower():
                    continue

            # Source filter
            src = t.get("source", "manual")
            if self._filter_source == "Auto" and src != "auto":
                continue
            if self._filter_source == "Manual" and src != "manual":
                continue

            result.append(t)
        return result

    def _on_filter_changed(self, _text=None):
        self._filter_priority = self._combo_priority.currentText()
        self._filter_status = self._combo_status.currentText()
        self._filter_source = self._combo_source.currentText()
        self.refresh()

    # ── Task card builder ─────────────────────────────────────────────

    def _make_task_card(self, task: dict) -> QFrame:
        card = QFrame()
        priority = task.get("priority", "normal")
        border_color = _PRIORITY_COLORS.get(priority, lambda: COLORS["info"])()
        card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-left: 4px solid {border_color};
                border-radius: 8px;
                padding: 14px 18px;
            }}
        """)

        card_lay = QHBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(14)

        # Left: priority badge
        badge = QLabel(priority.upper())
        badge_bg = border_color
        badge.setMinimumWidth(70)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"""
            background: {badge_bg}; color: white;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10px; font-weight: 700;
            letter-spacing: 1px;
            border-radius: 4px; padding: 4px 10px;
        """)
        card_lay.addWidget(badge)

        # Center: title + description + metadata
        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        title_lbl = QLabel(task.get("title", ""))
        title_lbl.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px; font-weight: 700;
            background: transparent;
        """)
        title_lbl.setWordWrap(True)
        info_col.addWidget(title_lbl)

        desc = task.get("description", "")
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
                background: transparent;
            """)
            desc_lbl.setWordWrap(True)
            info_col.addWidget(desc_lbl)

        # Metadata row: source module + due date
        meta_lay = QHBoxLayout()
        meta_lay.setSpacing(10)

        source_mod = task.get("source_module", "")
        if source_mod:
            src_color = _SOURCE_COLORS.get(source_mod, tc("text_light"))
            src_lbl = QLabel(source_mod.upper().replace("_", " "))
            src_lbl.setStyleSheet(f"""
                background: {src_color}; color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10px; font-weight: 600;
                letter-spacing: 1px;
                border-radius: 3px; padding: 2px 8px;
            """)
            meta_lay.addWidget(src_lbl)

        due = task.get("due_date", "")
        if due:
            today_str = datetime.now().strftime("%Y-%m-%d")
            overdue = due < today_str and task.get("status", "open") == "open"
            due_color = COLORS["danger"] if overdue else tc("text_light")
            due_lbl = QLabel(f"Due: {due}")
            due_lbl.setStyleSheet(f"""
                color: {due_color};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px; font-weight: 600;
                background: transparent;
            """)
            meta_lay.addWidget(due_lbl)

        source_tag = task.get("source", "manual")
        if source_tag == "auto":
            auto_lbl = QLabel("AUTO")
            auto_lbl.setStyleSheet(f"""
                background: {tc('border')}; color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 9px; font-weight: 700;
                letter-spacing: 1px;
                border-radius: 3px; padding: 2px 6px;
            """)
            meta_lay.addWidget(auto_lbl)

        meta_lay.addStretch()
        info_col.addLayout(meta_lay)

        card_lay.addLayout(info_col, 1)

        # Right: action buttons
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)

        if task.get("status", "open") == "open":
            complete_btn = QPushButton("Complete")
            complete_btn.setCursor(Qt.PointingHandCursor)
            complete_btn.setFixedSize(110, 32)
            complete_btn.setStyleSheet(btn_style(COLORS["success"], "white"))
            complete_btn.clicked.connect(
                lambda checked=False, t=task: self._complete_task(t)
            )
            btn_col.addWidget(complete_btn)

            if source_tag == "auto":
                dismiss_btn = QPushButton("Dismiss")
                dismiss_btn.setCursor(Qt.PointingHandCursor)
                dismiss_btn.setFixedSize(110, 32)
                dismiss_btn.setStyleSheet(btn_style(tc("border"), tc("text")))
                dismiss_btn.clicked.connect(
                    lambda checked=False, t=task: self._dismiss_task(t)
                )
                btn_col.addWidget(dismiss_btn)
        else:
            done_lbl = QLabel("DONE")
            done_lbl.setAlignment(Qt.AlignCenter)
            done_lbl.setStyleSheet(f"""
                color: {COLORS['success']};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px; font-weight: 700;
                letter-spacing: 1px;
                background: transparent;
            """)
            btn_col.addWidget(done_lbl)

        btn_col.addStretch()
        card_lay.addLayout(btn_col)

        return card

    # ── Actions ───────────────────────────────────────────────────────

    def _complete_task(self, task: dict):
        """Mark a task as completed."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        source = task.get("source", "manual")

        if source == "manual":
            # Update in database
            conn = get_conn()
            try:
                conn.execute(
                    "UPDATE supervisor_tasks SET status = 'completed', completed_at = ? "
                    "WHERE task_id = ?",
                    (now_str, task.get("task_id", "")),
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()
        else:
            # For auto tasks, store a dismissal/completion record so it doesn't reappear
            self._store_auto_task_action(task, "completed")

        self.refresh()

    def _dismiss_task(self, task: dict):
        """Dismiss an auto-generated task (don't show it again)."""
        self._store_auto_task_action(task, "dismissed")
        self.refresh()

    def _store_auto_task_action(self, task: dict, status: str):
        """Persist an action on an auto-generated task."""
        conn = get_conn()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            conn.execute(
                "INSERT OR REPLACE INTO supervisor_tasks "
                "(task_id, title, description, priority, due_date, assigned_to, "
                "status, source, source_module, source_record_id, created_by, "
                "completed_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"auto-{task.get('source_module', '')}-{task.get('source_record_id', '')}",
                    task.get("title", ""),
                    task.get("description", ""),
                    task.get("priority", "normal"),
                    task.get("due_date", ""),
                    "",
                    status,
                    "auto",
                    task.get("source_module", ""),
                    task.get("source_record_id", ""),
                    self.app_state.get("user", {}).get("username", ""),
                    now_str,
                    now_str,
                ),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _add_task(self):
        """Open the Add Task dialog and save to database."""
        dlg = AddTaskDialog(self.app_state, self)
        if dlg.exec() == QDialog.Accepted:
            task = dlg.get_task()
            if not task:
                QMessageBox.warning(self, "Missing Title", "Please enter a task title.")
                return
            conn = get_conn()
            try:
                conn.execute(
                    "INSERT INTO supervisor_tasks "
                    "(task_id, title, description, priority, due_date, assigned_to, "
                    "status, source, source_module, source_record_id, created_by, "
                    "completed_at, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        task["task_id"], task["title"], task["description"],
                        task["priority"], task["due_date"], task["assigned_to"],
                        task["status"], task["source"], task["source_module"],
                        task["source_record_id"], task["created_by"],
                        "", task["created_at"],
                    ),
                )
                conn.commit()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not save task: {e}")
            finally:
                conn.close()
            self.refresh()

    def _go_back(self):
        if self._on_back:
            self._on_back()

    # ── Refresh / data loading ──────────────────────────────────────

    def _get_dismissed_auto_keys(self) -> set:
        """Return set of source keys for dismissed/completed auto tasks."""
        conn = get_conn()
        keys = set()
        try:
            rows = conn.execute(
                "SELECT task_id FROM supervisor_tasks "
                "WHERE source = 'auto' AND status IN ('completed', 'dismissed')"
            ).fetchall()
            for r in rows:
                keys.add(r["task_id"])
        except Exception:
            pass
        finally:
            conn.close()
        return keys

    def refresh(self):
        """Reload auto-generated + manual tasks and rebuild the card list."""
        auto_tasks = generate_auto_tasks()
        manual_tasks = self._load_manual_tasks()

        # Filter out auto tasks that were dismissed/completed
        dismissed = self._get_dismissed_auto_keys()
        filtered_auto = []
        for t in auto_tasks:
            key = f"auto-{t.get('source_module', '')}-{t.get('source_record_id', '')}"
            if key not in dismissed:
                filtered_auto.append(t)

        all_tasks = filtered_auto + manual_tasks

        # Compute summaries before applying view filters
        today_str = datetime.now().strftime("%Y-%m-%d")
        open_tasks = [t for t in all_tasks if t.get("status", "open") == "open"]
        high_count = sum(1 for t in open_tasks if t.get("priority") == "high")
        overdue_count = sum(
            1 for t in open_tasks
            if t.get("due_date") and t["due_date"] < today_str
        )

        self._lbl_open["value_label"].setText(str(len(open_tasks)))
        self._lbl_high["value_label"].setText(str(high_count))
        self._lbl_overdue["value_label"].setText(str(overdue_count))

        # Apply view filters
        filtered = self._apply_filters(all_tasks)

        # Sort: high priority first, then by due date
        filtered.sort(key=lambda t: (
            _PRIORITY_ORDER.get(t.get("priority", "normal"), 1),
            t.get("due_date") or "9999-99-99",
        ))

        # Clear existing cards
        while self._task_list_lay.count():
            child = self._task_list_lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not filtered:
            empty = QLabel("No tasks match the current filters.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"""
                color: {tc('text_light')};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px; padding: 40px;
                background: transparent;
            """)
            self._task_list_lay.addWidget(empty)
            return

        for task in filtered:
            card = self._make_task_card(task)
            self._task_list_lay.addWidget(card)
