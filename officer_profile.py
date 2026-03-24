"""
Cerasus Hub -- Officer 360 Profile Dialog
Cross-module view showing an officer's complete picture across all modules.
"""

from datetime import datetime, date

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QGridLayout,
    QScrollArea, QSizePolicy, QSpacerItem,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import tc, COLORS, btn_style, build_dialog_stylesheet, _is_dark
from src.database import get_conn
from src.shared_data import get_officer


# ── Helpers ───────────────────────────────────────────────────────────

def _safe_str(val, default=""):
    """Return string value or default if None/empty."""
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _make_table(headers, stretch_last=True):
    """Create a styled QTableWidget with the given headers."""
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(stretch_last)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    if stretch_last:
        table.horizontalHeader().setSectionResizeMode(
            len(headers) - 1, QHeaderView.Stretch
        )
    table.setStyleSheet(f"""
        QTableWidget {{
            border: 1px solid {tc('border')};
            border-radius: 4px;
            background: {tc('card')};
            gridline-color: {tc('border')};
            font-size: 13px;
        }}
        QTableWidget::item {{
            padding: 6px 8px;
            color: {tc('text')};
        }}
        QTableWidget::item:selected {{
            background: {tc('info_light')};
            color: {tc('info')};
        }}
        QHeaderView::section {{
            background: {tc('primary') if not _is_dark() else tc('primary_light')};
            color: white;
            padding: 8px 6px;
            border: none;
            font-weight: 600;
            font-size: 13px;
        }}
    """)
    return table


def _set_table_empty(table, message="No data available"):
    """Show a placeholder message when table has no rows."""
    table.setRowCount(1)
    item = QTableWidgetItem(message)
    item.setFlags(Qt.NoItemFlags)
    item.setTextAlignment(Qt.AlignCenter)
    item.setForeground(QColor(tc('text_light')))
    item.setFont(QFont("Segoe UI", 12))
    table.setItem(0, 0, item)
    table.setSpan(0, 0, 1, table.columnCount())


def _mini_kpi_card(title, value, color):
    """Create a small KPI card for the header row."""
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background: {tc('card')};
            border: 1px solid {tc('border')};
            border-top: 3px solid {color};
            border-radius: 6px;
        }}
    """)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(2)

    lbl_title = QLabel(title)
    lbl_title.setStyleSheet(f"""
        color: {tc('text_light')}; font-size: 11px; font-weight: 600;
        background: transparent; border: none;
    """)
    lbl_title.setAlignment(Qt.AlignCenter)
    lay.addWidget(lbl_title)

    lbl_value = QLabel(str(value))
    lbl_value.setStyleSheet(f"""
        color: {color}; font-size: 20px; font-weight: 800;
        background: transparent; border: none;
    """)
    lbl_value.setAlignment(Qt.AlignCenter)
    lay.addWidget(lbl_value)

    return card


def _section_label(text):
    """Create a section header label inside a tab."""
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        color: {tc('text')}; font-size: 15px; font-weight: 700;
        background: transparent; border: none;
        padding: 4px 0;
    """)
    return lbl


def _info_label(text):
    """Create a light info label."""
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        color: {tc('text_light')}; font-size: 13px;
        background: transparent; border: none;
    """)
    return lbl


# ══════════════════════════════════════════════════════════════════════
# Officer Profile Dialog
# ══════════════════════════════════════════════════════════════════════

class OfficerProfileDialog(QDialog):
    """Cross-module 360 view of an officer."""

    def __init__(self, officer_id, app_state, parent=None):
        super().__init__(parent)
        self.officer_id = officer_id
        self.app_state = app_state
        self.officer = get_officer(officer_id) or {}

        name = _safe_str(self.officer.get("name"), "Unknown Officer")
        self.setWindowTitle(f"Officer Profile \u2014 {name}")
        self.setMinimumSize(850, 600)
        self.resize(900, 650)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))

        self._build()

    # ── Build ─────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── Header section ────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
            }}
        """)
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(20, 14, 20, 14)
        h_lay.setSpacing(8)

        # Name row
        name_row = QHBoxLayout()
        name = _safe_str(self.officer.get("name"), "Unknown Officer")
        lbl_name = QLabel(name)
        lbl_name.setStyleSheet(f"""
            color: {tc('text')}; font-size: 18px; font-weight: 800;
            background: transparent; border: none;
        """)
        name_row.addWidget(lbl_name)

        status = _safe_str(self.officer.get("status"), "Unknown")
        status_color = tc('success') if status == "Active" else tc('danger')
        lbl_status = QLabel(f"  {status}  ")
        lbl_status.setStyleSheet(f"""
            color: white; background: {status_color};
            font-size: 11px; font-weight: 700;
            border-radius: 4px; padding: 2px 8px;
        """)
        name_row.addWidget(lbl_status)
        name_row.addStretch()
        h_lay.addLayout(name_row)

        # Info row
        info_row = QHBoxLayout()
        info_parts = []
        emp_id = _safe_str(self.officer.get("employee_id"))
        if emp_id:
            info_parts.append(f"ID: {emp_id}")
        job_title = _safe_str(self.officer.get("job_title"))
        if job_title:
            info_parts.append(job_title)
        site = _safe_str(self.officer.get("site"))
        if site:
            info_parts.append(site)
        hire_date = _safe_str(self.officer.get("hire_date"))
        if hire_date:
            info_parts.append(f"Hired: {hire_date}")

        info_text = "  \u2022  ".join(info_parts) if info_parts else "No details available"
        lbl_info = QLabel(info_text)
        lbl_info.setStyleSheet(f"""
            color: {tc('text_light')}; font-size: 13px;
            background: transparent; border: none;
        """)
        info_row.addWidget(lbl_info)
        info_row.addStretch()
        h_lay.addLayout(info_row)

        # KPI cards row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        # Attendance Points
        att_points = self.officer.get("active_points", 0)
        try:
            att_points = float(att_points)
        except (ValueError, TypeError):
            att_points = 0
        if att_points >= 8:
            pts_color = tc('danger')
        elif att_points >= 5:
            pts_color = tc('warning')
        else:
            pts_color = tc('success')
        kpi_row.addWidget(_mini_kpi_card("Att. Points", f"{att_points:.1f}", pts_color))

        # Discipline Level
        disc_level = _safe_str(self.officer.get("discipline_level"), "None")
        if disc_level in ("Termination", "Final Written"):
            disc_color = tc('danger')
        elif disc_level in ("Written Warning", "Verbal Warning"):
            disc_color = tc('warning')
        else:
            disc_color = tc('success')
        kpi_row.addWidget(_mini_kpi_card("Discipline", disc_level, disc_color))

        # Uniform Compliance %
        uni_pct = self._calc_uniform_compliance()
        if uni_pct >= 90:
            uni_color = tc('success')
        elif uni_pct >= 70:
            uni_color = tc('warning')
        else:
            uni_color = tc('danger')
        kpi_row.addWidget(_mini_kpi_card("Uniform", f"{uni_pct}%", uni_color))

        # Training Completion %
        trn_pct = self._calc_training_completion()
        if trn_pct >= 90:
            trn_color = tc('success')
        elif trn_pct >= 50:
            trn_color = tc('warning')
        else:
            trn_color = tc('danger')
        kpi_row.addWidget(_mini_kpi_card("Training", f"{trn_pct}%", trn_color))

        h_lay.addLayout(kpi_row)
        root.addWidget(header)

        # ── Tabs ──────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {tc('border')};
                border-radius: 6px;
                background: {tc('card')};
            }}
            QTabBar::tab {{
                background: {tc('bg')};
                color: {tc('text_light')};
                padding: 8px 18px;
                border: 1px solid {tc('border')};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 13px;
                font-weight: 600;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {tc('card')};
                color: {tc('text')};
                border-bottom: 2px solid {COLORS['accent']};
            }}
            QTabBar::tab:hover {{
                color: {tc('text')};
            }}
        """)

        self.tabs.addTab(self._build_overview_tab(), "Overview")
        self.tabs.addTab(self._build_schedule_tab(), "Schedule")
        self.tabs.addTab(self._build_attendance_tab(), "Attendance")
        self.tabs.addTab(self._build_uniforms_tab(), "Uniforms")
        self.tabs.addTab(self._build_training_tab(), "Training")

        root.addWidget(self.tabs)

    # ── KPI Calculations ──────────────────────────────────────────────

    def _calc_uniform_compliance(self):
        """Calculate uniform compliance % based on requirements vs outstanding issuances."""
        try:
            conn = get_conn()
            job_title = _safe_str(self.officer.get("job_title"), "Security Officer")

            # Get required item count for this job title
            req_row = conn.execute(
                "SELECT COALESCE(SUM(qty_required), 0) as total FROM uni_requirements WHERE job_title = ?",
                (job_title,)
            ).fetchone()
            required = req_row["total"] if req_row else 0

            if required == 0:
                conn.close()
                return 100  # No requirements means fully compliant

            # Get outstanding issuance count
            iss_row = conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) as total FROM uni_issuances WHERE officer_id = ? AND status = 'Outstanding'",
                (self.officer_id,)
            ).fetchone()
            issued = iss_row["total"] if iss_row else 0

            conn.close()
            pct = min(100, int((issued / required) * 100))
            return pct
        except Exception:
            return 0

    def _calc_training_completion(self):
        """Calculate training completion % across all published courses."""
        try:
            conn = get_conn()

            # Total chapters across all published courses
            total_row = conn.execute(
                "SELECT COUNT(*) as c FROM trn_chapters WHERE course_id IN "
                "(SELECT course_id FROM trn_courses WHERE status = 'Published')"
            ).fetchone()
            total_chapters = total_row["c"] if total_row else 0

            if total_chapters == 0:
                conn.close()
                return 100  # No courses means nothing to complete

            # Completed chapters for this officer
            done_row = conn.execute(
                "SELECT COUNT(*) as c FROM trn_progress WHERE officer_id = ? AND completed = 1",
                (self.officer_id,)
            ).fetchone()
            done_chapters = done_row["c"] if done_row else 0

            conn.close()
            pct = min(100, int((done_chapters / total_chapters) * 100))
            return pct
        except Exception:
            return 0

    # ── Tab 1: Overview ───────────────────────────────────────────────

    def _build_overview_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")

        container = QWidget()
        container.setStyleSheet(f"background: {tc('card')};")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        lay.addWidget(_section_label("Officer Summary"))

        # Info grid
        grid = QGridLayout()
        grid.setSpacing(8)

        fields = [
            ("Full Name", _safe_str(self.officer.get("name"), "--")),
            ("Employee ID", _safe_str(self.officer.get("employee_id"), "--")),
            ("Job Title", _safe_str(self.officer.get("job_title"), "--")),
            ("Role", _safe_str(self.officer.get("role"), "--")),
            ("Site", _safe_str(self.officer.get("site"), "--")),
            ("Hire Date", _safe_str(self.officer.get("hire_date"), "--")),
            ("Weekly Hours", _safe_str(self.officer.get("weekly_hours"), "--")),
            ("Email", _safe_str(self.officer.get("email"), "--")),
            ("Phone", _safe_str(self.officer.get("phone"), "--")),
            ("Status", _safe_str(self.officer.get("status"), "--")),
        ]

        for i, (label, value) in enumerate(fields):
            row = i // 2
            col = (i % 2) * 2

            lbl_key = QLabel(label + ":")
            lbl_key.setStyleSheet(f"""
                color: {tc('text_light')}; font-size: 13px; font-weight: 600;
                background: transparent; border: none;
            """)
            grid.addWidget(lbl_key, row, col)

            lbl_val = QLabel(value)
            lbl_val.setStyleSheet(f"""
                color: {tc('text')}; font-size: 13px;
                background: transparent; border: none;
            """)
            grid.addWidget(lbl_val, row, col + 1)

        lay.addLayout(grid)

        # Module status indicators
        lay.addSpacing(8)
        lay.addWidget(_section_label("Module Status"))

        status_grid = QGridLayout()
        status_grid.setSpacing(10)

        modules_status = [
            ("Operations", self._get_ops_status()),
            ("Attendance", self._get_attendance_status()),
            ("Uniforms", self._get_uniforms_status()),
            ("Training", self._get_training_status()),
        ]

        for i, (mod_name, status_text) in enumerate(modules_status):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {tc('bg')};
                    border: 1px solid {tc('border')};
                    border-radius: 6px;
                    padding: 8px;
                }}
            """)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(12, 8, 12, 8)
            c_lay.setSpacing(4)

            lbl_mod = QLabel(mod_name)
            lbl_mod.setStyleSheet(f"""
                color: {tc('text')}; font-size: 13px; font-weight: 700;
                background: transparent; border: none;
            """)
            c_lay.addWidget(lbl_mod)

            lbl_st = QLabel(status_text)
            lbl_st.setWordWrap(True)
            lbl_st.setStyleSheet(f"""
                color: {tc('text_light')}; font-size: 12px;
                background: transparent; border: none;
            """)
            c_lay.addWidget(lbl_st)

            status_grid.addWidget(card, i // 2, i % 2)

        lay.addLayout(status_grid)

        # Notes
        notes = _safe_str(self.officer.get("notes"))
        if notes:
            lay.addSpacing(8)
            lay.addWidget(_section_label("Notes"))
            lbl_notes = QLabel(notes)
            lbl_notes.setWordWrap(True)
            lbl_notes.setStyleSheet(f"""
                color: {tc('text')}; font-size: 13px;
                background: {tc('bg')}; border: 1px solid {tc('border')};
                border-radius: 6px; padding: 10px;
            """)
            lay.addWidget(lbl_notes)

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _get_ops_status(self):
        try:
            conn = get_conn()
            today = date.today().isoformat()
            row = conn.execute(
                "SELECT COUNT(*) as c FROM ops_assignments WHERE officer_name = ? AND date >= ?",
                (_safe_str(self.officer.get("name")), today)
            ).fetchone()
            conn.close()
            count = row["c"] if row else 0
            return f"{count} upcoming assignment(s)"
        except Exception:
            return "No schedule data"

    def _get_attendance_status(self):
        pts = self.officer.get("active_points", 0)
        disc = _safe_str(self.officer.get("discipline_level"), "None")
        return f"{pts} active points, Discipline: {disc}"

    def _get_uniforms_status(self):
        try:
            conn = get_conn()
            row = conn.execute(
                "SELECT COUNT(*) as c FROM uni_issuances WHERE officer_id = ? AND status = 'Outstanding'",
                (self.officer_id,)
            ).fetchone()
            conn.close()
            count = row["c"] if row else 0
            return f"{count} outstanding item(s)"
        except Exception:
            return "No uniform data"

    def _get_training_status(self):
        try:
            conn = get_conn()
            cert_row = conn.execute(
                "SELECT COUNT(*) as c FROM trn_certificates WHERE officer_id = ? AND status = 'Active'",
                (self.officer_id,)
            ).fetchone()
            conn.close()
            certs = cert_row["c"] if cert_row else 0
            return f"{certs} active certificate(s)"
        except Exception:
            return "No training data"

    # ── Tab 2: Schedule (Operations) ──────────────────────────────────

    def _build_schedule_tab(self):
        container = QWidget()
        container.setStyleSheet(f"background: {tc('card')};")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        lay.addWidget(_section_label("Upcoming Schedule (Next 7 Days)"))

        self.schedule_table = _make_table([
            "Date", "Site", "Start", "End", "Hours", "Type", "Status"
        ])

        self._load_schedule()
        lay.addWidget(self.schedule_table)
        return container

    def _load_schedule(self):
        try:
            conn = get_conn()
            today = date.today().isoformat()
            officer_name = _safe_str(self.officer.get("name"), "")
            rows = conn.execute(
                "SELECT * FROM ops_assignments WHERE officer_name = ? AND date >= ? ORDER BY date LIMIT 20",
                (officer_name, today)
            ).fetchall()
            conn.close()

            if not rows:
                _set_table_empty(self.schedule_table, "No upcoming assignments")
                return

            self.schedule_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                r = dict(row)
                values = [
                    _safe_str(r.get("date")),
                    _safe_str(r.get("site_name")),
                    _safe_str(r.get("start_time")),
                    _safe_str(r.get("end_time")),
                    _safe_str(r.get("hours")),
                    _safe_str(r.get("assignment_type")),
                    _safe_str(r.get("status")),
                ]
                for j, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.schedule_table.setItem(i, j, item)

        except Exception:
            _set_table_empty(self.schedule_table, "No schedule data available")

    # ── Tab 3: Attendance ─────────────────────────────────────────────

    def _build_attendance_tab(self):
        container = QWidget()
        container.setStyleSheet(f"background: {tc('card')};")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        # Summary row
        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)

        att_points = self.officer.get("active_points", 0)
        try:
            att_points = float(att_points)
        except (ValueError, TypeError):
            att_points = 0

        disc_level = _safe_str(self.officer.get("discipline_level"), "None")
        last_infraction = _safe_str(self.officer.get("last_infraction_date"), "N/A")

        summary_row.addWidget(_info_label(f"Active Points: {att_points:.1f}"))
        summary_row.addWidget(_info_label(f"Discipline Level: {disc_level}"))
        summary_row.addWidget(_info_label(f"Last Infraction: {last_infraction}"))
        summary_row.addStretch()
        lay.addLayout(summary_row)

        lay.addSpacing(4)
        lay.addWidget(_section_label("Infraction History"))

        self.attendance_table = _make_table([
            "Date", "Type", "Points", "Discipline Triggered", "Notes"
        ])

        self._load_attendance()
        lay.addWidget(self.attendance_table)
        return container

    def _load_attendance(self):
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT * FROM ats_infractions WHERE employee_id = ? ORDER BY infraction_date DESC",
                (self.officer_id,)
            ).fetchall()
            conn.close()

            if not rows:
                _set_table_empty(self.attendance_table, "No infractions recorded")
                return

            self.attendance_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                r = dict(row)
                pts = r.get("points_assigned", 0)
                try:
                    pts_str = f"{float(pts):.1f}"
                except (ValueError, TypeError):
                    pts_str = str(pts)

                values = [
                    _safe_str(r.get("infraction_date")),
                    _safe_str(r.get("infraction_type")),
                    pts_str,
                    _safe_str(r.get("discipline_triggered")),
                    _safe_str(r.get("description")),
                ]
                for j, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.attendance_table.setItem(i, j, item)

        except Exception:
            _set_table_empty(self.attendance_table, "No attendance data available")

    # ── Tab 4: Uniforms ───────────────────────────────────────────────

    def _build_uniforms_tab(self):
        container = QWidget()
        container.setStyleSheet(f"background: {tc('card')};")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        # Summary row
        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)

        outstanding_count = 0
        try:
            conn = get_conn()
            row = conn.execute(
                "SELECT COUNT(*) as c FROM uni_issuances WHERE officer_id = ? AND status = 'Outstanding'",
                (self.officer_id,)
            ).fetchone()
            outstanding_count = row["c"] if row else 0
            conn.close()
        except Exception:
            pass

        uni_pct = self._calc_uniform_compliance()

        summary_row.addWidget(_info_label(f"Outstanding Items: {outstanding_count}"))
        summary_row.addWidget(_info_label(f"Compliance: {uni_pct}%"))
        summary_row.addStretch()
        lay.addLayout(summary_row)

        lay.addSpacing(4)
        lay.addWidget(_section_label("Outstanding Uniform Items"))

        self.uniforms_table = _make_table([
            "Item", "Size", "Qty", "Date Issued", "Condition"
        ])

        self._load_uniforms()
        lay.addWidget(self.uniforms_table)
        return container

    def _load_uniforms(self):
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT * FROM uni_issuances WHERE officer_id = ? AND status = 'Outstanding' ORDER BY date_issued DESC",
                (self.officer_id,)
            ).fetchall()
            conn.close()

            if not rows:
                _set_table_empty(self.uniforms_table, "No outstanding uniform items")
                return

            self.uniforms_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                r = dict(row)
                values = [
                    _safe_str(r.get("item_name")),
                    _safe_str(r.get("size")),
                    str(r.get("quantity", 1)),
                    _safe_str(r.get("date_issued")),
                    _safe_str(r.get("condition_issued")),
                ]
                for j, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.uniforms_table.setItem(i, j, item)

        except Exception:
            _set_table_empty(self.uniforms_table, "No uniform data available")

    # ── Tab 5: Training ───────────────────────────────────────────────

    def _build_training_tab(self):
        container = QWidget()
        container.setStyleSheet(f"background: {tc('card')};")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        # Summary row
        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)

        courses_done = 0
        courses_total = 0
        certs_count = 0
        try:
            conn = get_conn()

            # Total published courses
            t_row = conn.execute(
                "SELECT COUNT(*) as c FROM trn_courses WHERE status = 'Published'"
            ).fetchone()
            courses_total = t_row["c"] if t_row else 0

            # Courses where all chapters are completed by this officer
            if courses_total > 0:
                course_rows = conn.execute(
                    "SELECT course_id FROM trn_courses WHERE status = 'Published'"
                ).fetchall()
                for cr in course_rows:
                    cid = cr["course_id"]
                    chap_total = conn.execute(
                        "SELECT COUNT(*) as c FROM trn_chapters WHERE course_id = ?", (cid,)
                    ).fetchone()
                    chap_done = conn.execute(
                        "SELECT COUNT(*) as c FROM trn_progress WHERE officer_id = ? AND course_id = ? AND completed = 1",
                        (self.officer_id, cid)
                    ).fetchone()
                    total_c = chap_total["c"] if chap_total else 0
                    done_c = chap_done["c"] if chap_done else 0
                    if total_c > 0 and done_c >= total_c:
                        courses_done += 1

            cert_row = conn.execute(
                "SELECT COUNT(*) as c FROM trn_certificates WHERE officer_id = ?",
                (self.officer_id,)
            ).fetchone()
            certs_count = cert_row["c"] if cert_row else 0

            conn.close()
        except Exception:
            pass

        summary_row.addWidget(_info_label(f"Courses Completed: {courses_done} / {courses_total}"))
        summary_row.addWidget(_info_label(f"Certificates: {certs_count}"))
        summary_row.addStretch()
        lay.addLayout(summary_row)

        lay.addSpacing(4)
        lay.addWidget(_section_label("Course Progress"))

        self.training_table = _make_table([
            "Course", "Chapters Done", "Total", "Completion %", "Certified"
        ])

        self._load_training()
        lay.addWidget(self.training_table)
        return container

    def _load_training(self):
        try:
            conn = get_conn()
            courses = conn.execute(
                "SELECT * FROM trn_courses WHERE status = 'Published' ORDER BY title"
            ).fetchall()

            if not courses:
                conn.close()
                _set_table_empty(self.training_table, "No training courses available")
                return

            self.training_table.setRowCount(len(courses))
            for i, course in enumerate(courses):
                c = dict(course)
                cid = c["course_id"]

                # Chapter counts
                chap_total_row = conn.execute(
                    "SELECT COUNT(*) as c FROM trn_chapters WHERE course_id = ?", (cid,)
                ).fetchone()
                chap_total = chap_total_row["c"] if chap_total_row else 0

                chap_done_row = conn.execute(
                    "SELECT COUNT(*) as c FROM trn_progress WHERE officer_id = ? AND course_id = ? AND completed = 1",
                    (self.officer_id, cid)
                ).fetchone()
                chap_done = chap_done_row["c"] if chap_done_row else 0

                pct = int((chap_done / chap_total) * 100) if chap_total > 0 else 0

                # Certificate check
                cert_row = conn.execute(
                    "SELECT cert_id FROM trn_certificates WHERE officer_id = ? AND course_id = ? AND status = 'Active'",
                    (self.officer_id, cid)
                ).fetchone()
                certified = "Yes" if cert_row else "No"

                values = [
                    _safe_str(c.get("title")),
                    str(chap_done),
                    str(chap_total),
                    f"{pct}%",
                    certified,
                ]
                for j, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if j == 3:  # Completion % column - color code
                        if pct >= 100:
                            item.setForeground(QColor(tc('success')))
                        elif pct >= 50:
                            item.setForeground(QColor(tc('warning')))
                        else:
                            item.setForeground(QColor(tc('text_light')))
                    if j == 4 and certified == "Yes":
                        item.setForeground(QColor(tc('success')))
                    self.training_table.setItem(i, j, item)

            conn.close()

        except Exception:
            _set_table_empty(self.training_table, "No training data available")
