"""
Cerasus Hub -- Officer 360 Profile Dialog
Cross-module officer profile accessible from any module via double-click.
"""

from datetime import datetime, date, timedelta

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QScrollArea,
    QSizePolicy, QGridLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.database import get_conn
from src.config import tc, COLORS, btn_style, build_dialog_stylesheet, _is_dark
from src.shared_widgets import make_stat_card


# ---------------------------------------------------------------------------
#  Module-level helper
# ---------------------------------------------------------------------------

def show_officer_profile(parent, officer_id: str, app_state: dict):
    """Open the Officer 360 profile dialog for the given officer."""
    dlg = Officer360Dialog(officer_id, app_state, parent)
    dlg.exec()


# ---------------------------------------------------------------------------
#  Helper utilities
# ---------------------------------------------------------------------------

def _safe_query(conn, sql, params=()):
    """Execute a query, returning an empty list if the table does not exist."""
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []


def _safe_query_one(conn, sql, params=()):
    """Execute a query returning a single row, or None on error."""
    try:
        return conn.execute(sql, params).fetchone()
    except Exception:
        return None


def _make_table(columns, stretch_last=True):
    """Create a styled QTableWidget with the given column headers."""
    table = QTableWidget()
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.setFont(QFont("Segoe UI", 13))

    header = table.horizontalHeader()
    if stretch_last:
        header.setStretchLastSection(True)
    for i in range(len(columns)):
        header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
    if stretch_last and len(columns) > 0:
        header.setSectionResizeMode(len(columns) - 1, QHeaderView.Stretch)

    return table


def _populate_table(table, rows, keys):
    """Fill a QTableWidget from a list of sqlite3.Row using the given keys."""
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, key in enumerate(keys):
            val = row[key] if key in row.keys() else ""
            item = QTableWidgetItem(str(val) if val else "")
            item.setFont(QFont("Segoe UI", 13))
            table.setItem(r, c, item)
    if not rows:
        _set_empty(table)


def _set_empty(table, msg="No records found"):
    """Show an empty-state message in the table."""
    table.setRowCount(1)
    item = QTableWidgetItem(msg)
    item.setFlags(Qt.NoItemFlags)
    item.setTextAlignment(Qt.AlignCenter)
    item.setForeground(QColor(tc("text_light")))
    item.setFont(QFont("Segoe UI", 13))
    table.setItem(0, 0, item)
    table.setSpan(0, 0, 1, table.columnCount())


# ---------------------------------------------------------------------------
#  Status badge
# ---------------------------------------------------------------------------

def _status_badge(status: str) -> QLabel:
    """Return a colored label acting as a status badge."""
    color_map = {
        "Active": tc("success"),
        "Inactive": tc("text_light"),
        "Terminated": tc("danger"),
    }
    bg_map = {
        "Active": tc("success_light"),
        "Inactive": tc("info_light"),
        "Terminated": tc("danger_light"),
    }
    fg = color_map.get(status, tc("text"))
    bg = bg_map.get(status, tc("info_light"))

    lbl = QLabel(status)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setFixedHeight(28)
    lbl.setStyleSheet(
        f"background: {bg}; color: {fg}; font-size: 13px; font-weight: 700; "
        f"border-radius: 6px; padding: 2px 14px; border: none;"
    )
    return lbl


# ---------------------------------------------------------------------------
#  Officer 360 Dialog
# ---------------------------------------------------------------------------

class Officer360Dialog(QDialog):
    """Full officer profile dialog with tabbed interface."""

    def __init__(self, officer_id: str, app_state: dict, parent=None):
        super().__init__(parent)
        self._officer_id = officer_id
        self._app_state = app_state
        self._loaded_tabs = set()

        # Load officer record
        conn = get_conn()
        self._officer = _safe_query_one(
            conn,
            "SELECT * FROM officers WHERE officer_id = ?",
            (officer_id,),
        )
        conn.close()

        name = self._officer["name"] if self._officer else officer_id
        self.setWindowTitle(f"Officer Profile: {name}")
        self.setMinimumSize(800, 600)
        self.resize(900, 650)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))

        self._build_ui()
        # Load overview immediately
        self._load_tab(0)
        self._tabs.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------
    #  UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setFont(QFont("Segoe UI", 13))
        self._tabs.setStyleSheet(self._tab_stylesheet())

        self._overview_widget = QWidget()
        self._schedule_widget = QWidget()
        self._attendance_widget = QWidget()
        self._uniforms_widget = QWidget()
        self._training_widget = QWidget()

        self._tabs.addTab(self._overview_widget, "Overview")
        self._tabs.addTab(self._schedule_widget, "Schedule")
        self._tabs.addTab(self._attendance_widget, "Attendance")
        self._tabs.addTab(self._uniforms_widget, "Uniforms")
        self._tabs.addTab(self._training_widget, "Training")

        root.addWidget(self._tabs)

    def _tab_stylesheet(self):
        c_bg = tc("bg")
        c_card = tc("card")
        c_text = tc("text")
        c_border = tc("border")
        c_accent = tc("accent")
        return f"""
            QTabWidget::pane {{
                border: none;
                background: {c_bg};
            }}
            QTabBar::tab {{
                background: {c_card};
                color: {c_text};
                border: 1px solid {c_border};
                border-bottom: none;
                padding: 10px 22px;
                font-size: 13px;
                font-weight: 600;
                font-family: 'Segoe UI';
            }}
            QTabBar::tab:selected {{
                background: {c_bg};
                border-bottom: 3px solid {c_accent};
                color: {c_accent};
            }}
            QTabBar::tab:hover {{
                background: {c_bg};
            }}
        """

    # ------------------------------------------------------------------
    #  Lazy tab loading
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index):
        self._load_tab(index)

    def _load_tab(self, index):
        if index in self._loaded_tabs:
            return
        self._loaded_tabs.add(index)

        loaders = {
            0: self._build_overview,
            1: self._build_schedule,
            2: self._build_attendance,
            3: self._build_uniforms,
            4: self._build_training,
        }
        loader = loaders.get(index)
        if loader:
            loader()

    # ------------------------------------------------------------------
    #  Tab 1: Overview
    # ------------------------------------------------------------------

    def _build_overview(self):
        layout = QVBoxLayout(self._overview_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        o = self._officer
        if not o:
            layout.addWidget(QLabel("Officer not found."))
            return

        # -- Info section --
        info_frame = QFrame()
        info_frame.setStyleSheet(
            f"background: {tc('card')}; border: 1px solid {tc('border')}; "
            f"border-radius: 8px; padding: 16px;"
        )
        info_layout = QGridLayout(info_frame)
        info_layout.setSpacing(10)

        fields = [
            ("Name", o["name"]),
            ("Employee ID", o["employee_id"]),
            ("Job Title", o["job_title"]),
            ("Site", o["site"]),
            ("Hire Date", o["hire_date"]),
            ("Email", o["email"]),
            ("Phone", o["phone"]),
        ]
        for i, (label, value) in enumerate(fields):
            row, col = divmod(i, 2)
            lbl = QLabel(f"{label}:")
            lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
            lbl.setStyleSheet(f"color: {tc('text_light')}; border: none; background: transparent;")
            val = QLabel(str(value) if value else "--")
            val.setFont(QFont("Segoe UI", 13))
            val.setStyleSheet(f"color: {tc('text')}; border: none; background: transparent;")
            info_layout.addWidget(lbl, row, col * 2)
            info_layout.addWidget(val, row, col * 2 + 1)

        # Status badge on top-right
        status_text = o["status"] if o["status"] else "Active"
        badge = _status_badge(status_text)
        info_layout.addWidget(badge, 0, 4, Qt.AlignRight | Qt.AlignTop)

        layout.addWidget(info_frame)

        # -- KPI cards --
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        # Active Points
        active_pts = o["active_points"] if o["active_points"] else 0
        pts_color = tc("danger") if active_pts >= 8 else (tc("warning") if active_pts >= 4 else tc("success"))
        kpi_row.addWidget(make_stat_card("Active Points", str(active_pts), pts_color))

        # Training progress
        training_pct = self._calc_training_progress()
        trn_color = tc("success") if training_pct >= 80 else (tc("warning") if training_pct >= 50 else tc("danger"))
        kpi_row.addWidget(make_stat_card("Training Progress", f"{training_pct}%", trn_color))

        # Uniform compliance
        uni_pct = self._calc_uniform_compliance()
        uni_color = tc("success") if uni_pct >= 80 else (tc("warning") if uni_pct >= 50 else tc("danger"))
        kpi_row.addWidget(make_stat_card("Uniform Compliance", f"{uni_pct}%", uni_color))

        # Days since last infraction
        days_since = self._calc_days_since_infraction()
        days_str = str(days_since) if days_since is not None else "N/A"
        days_color = tc("success") if (days_since is not None and days_since >= 30) else tc("warning")
        if days_since is None:
            days_color = tc("text_light")
        kpi_row.addWidget(make_stat_card("Days Since Infraction", days_str, days_color))

        layout.addLayout(kpi_row)
        layout.addStretch()

    def _calc_training_progress(self):
        """Compute training completion percentage from trn_progress."""
        conn = get_conn()
        try:
            total = _safe_query_one(
                conn,
                "SELECT COUNT(DISTINCT course_id) AS cnt FROM trn_courses WHERE status='Published'",
            )
            completed = _safe_query_one(
                conn,
                """SELECT COUNT(DISTINCT course_id) AS cnt FROM trn_certificates
                   WHERE officer_id = ? AND status = 'Active'""",
                (self._officer_id,),
            )
            conn.close()
            t = total["cnt"] if total and total["cnt"] else 0
            c = completed["cnt"] if completed and completed["cnt"] else 0
            return int((c / t) * 100) if t > 0 else 0
        except Exception:
            conn.close()
            return 0

    def _calc_uniform_compliance(self):
        """Compute uniform compliance: issued required items / total required items."""
        conn = get_conn()
        try:
            job_title = self._officer["job_title"] if self._officer else ""
            required = _safe_query(
                conn,
                "SELECT item_id, qty_required FROM uni_requirements WHERE job_title = ?",
                (job_title,),
            )
            if not required:
                conn.close()
                return 100  # No requirements = fully compliant

            met = 0
            for req in required:
                issued = _safe_query_one(
                    conn,
                    """SELECT COALESCE(SUM(quantity), 0) AS qty FROM uni_issuances
                       WHERE officer_id = ? AND item_id = ? AND status = 'Outstanding'""",
                    (self._officer_id, req["item_id"]),
                )
                if issued and issued["qty"] >= req["qty_required"]:
                    met += 1
            conn.close()
            return int((met / len(required)) * 100)
        except Exception:
            conn.close()
            return 0

    def _calc_days_since_infraction(self):
        """Return days since the last infraction, or None if none exist."""
        conn = get_conn()
        row = _safe_query_one(
            conn,
            """SELECT infraction_date FROM ats_infractions
               WHERE employee_id = ? ORDER BY infraction_date DESC LIMIT 1""",
            (self._officer_id,),
        )
        conn.close()
        if not row or not row["infraction_date"]:
            return None
        try:
            last = datetime.strptime(row["infraction_date"], "%Y-%m-%d").date()
            return (date.today() - last).days
        except Exception:
            return None

    # ------------------------------------------------------------------
    #  Tab 2: Schedule (Operations)
    # ------------------------------------------------------------------

    def _build_schedule(self):
        layout = QVBoxLayout(self._schedule_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        officer_name = self._officer["name"] if self._officer else ""

        # Assignments next 14 days
        lbl_assign = QLabel("Assignments (Next 14 Days)")
        lbl_assign.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_assign.setStyleSheet(f"color: {tc('text')}; border: none;")
        layout.addWidget(lbl_assign)

        cols = ["Date", "Site", "Start Time", "End Time", "Hours", "Type", "Status"]
        self._schedule_table = _make_table(cols)
        layout.addWidget(self._schedule_table)

        conn = get_conn()
        today = date.today().isoformat()
        end_14 = (date.today() + timedelta(days=14)).isoformat()
        rows = _safe_query(
            conn,
            """SELECT date, site_name, start_time, end_time, hours,
                      assignment_type, status
               FROM ops_assignments
               WHERE officer_name = ? AND date >= ? AND date <= ?
               ORDER BY date ASC""",
            (officer_name, today, end_14),
        )
        keys = ["date", "site_name", "start_time", "end_time", "hours",
                "assignment_type", "status"]
        _populate_table(self._schedule_table, rows, keys)

        # PTO next 30 days
        lbl_pto = QLabel("PTO / Unavailable (Next 30 Days)")
        lbl_pto.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_pto.setStyleSheet(f"color: {tc('text')}; border: none;")
        layout.addWidget(lbl_pto)

        pto_cols = ["Start Date", "End Date", "Type", "Status", "Notes"]
        self._pto_table = _make_table(pto_cols)
        layout.addWidget(self._pto_table)

        end_30 = (date.today() + timedelta(days=30)).isoformat()
        pto_rows = _safe_query(
            conn,
            """SELECT start_date, end_date, pto_type, status, notes
               FROM ops_pto_entries
               WHERE officer_name = ? AND end_date >= ? AND start_date <= ?
               ORDER BY start_date ASC""",
            (officer_name, today, end_30),
        )
        conn.close()
        pto_keys = ["start_date", "end_date", "pto_type", "status", "notes"]
        _populate_table(self._pto_table, pto_rows, pto_keys)

    # ------------------------------------------------------------------
    #  Tab 3: Attendance
    # ------------------------------------------------------------------

    def _build_attendance(self):
        layout = QVBoxLayout(self._attendance_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        o = self._officer

        # Summary cards
        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)

        pts = o["active_points"] if o and o["active_points"] else 0
        disc = o["discipline_level"] if o and o["discipline_level"] else "None"
        exempt = o["emergency_exemptions_used"] if o and o["emergency_exemptions_used"] else 0

        pts_color = tc("danger") if pts >= 8 else (tc("warning") if pts >= 4 else tc("success"))
        summary_row.addWidget(make_stat_card("Current Points", str(pts), pts_color))
        summary_row.addWidget(make_stat_card("Discipline Level", str(disc), tc("info")))
        summary_row.addWidget(make_stat_card("Emergency Exemptions Used", str(exempt), tc("warning")))

        layout.addLayout(summary_row)

        # Infraction history
        lbl = QLabel("Infraction History (Last 20)")
        lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl.setStyleSheet(f"color: {tc('text')}; border: none;")
        layout.addWidget(lbl)

        cols = ["Date", "Type", "Points", "Site", "Description"]
        self._infraction_table = _make_table(cols)
        layout.addWidget(self._infraction_table)

        conn = get_conn()
        rows = _safe_query(
            conn,
            """SELECT infraction_date, infraction_type, points_assigned, site, description
               FROM ats_infractions
               WHERE employee_id = ?
               ORDER BY infraction_date DESC LIMIT 20""",
            (self._officer_id,),
        )
        conn.close()
        keys = ["infraction_date", "infraction_type", "points_assigned", "site", "description"]
        _populate_table(self._infraction_table, rows, keys)

    # ------------------------------------------------------------------
    #  Tab 4: Uniforms
    # ------------------------------------------------------------------

    def _build_uniforms(self):
        layout = QVBoxLayout(self._uniforms_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Outstanding items
        lbl_out = QLabel("Outstanding Items")
        lbl_out.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_out.setStyleSheet(f"color: {tc('text')}; border: none;")
        layout.addWidget(lbl_out)

        cols = ["Item", "Size", "Qty", "Date Issued", "Condition"]
        self._uniform_table = _make_table(cols)
        layout.addWidget(self._uniform_table)

        conn = get_conn()
        rows = _safe_query(
            conn,
            """SELECT item_name, size, quantity, date_issued, condition_issued
               FROM uni_issuances
               WHERE officer_id = ? AND status = 'Outstanding'
               ORDER BY date_issued DESC""",
            (self._officer_id,),
        )
        keys = ["item_name", "size", "quantity", "date_issued", "condition_issued"]
        _populate_table(self._uniform_table, rows, keys)

        # Compliance check
        lbl_comp = QLabel("Compliance Check")
        lbl_comp.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_comp.setStyleSheet(f"color: {tc('text')}; border: none;")
        layout.addWidget(lbl_comp)

        comp_cols = ["Required Item", "Qty Required", "Qty Issued", "Status"]
        self._compliance_table = _make_table(comp_cols)
        layout.addWidget(self._compliance_table)

        job_title = self._officer["job_title"] if self._officer else ""
        required = _safe_query(
            conn,
            "SELECT item_id, item_name, qty_required FROM uni_requirements WHERE job_title = ?",
            (job_title,),
        )

        self._compliance_table.setRowCount(len(required))
        for r, req in enumerate(required):
            issued = _safe_query_one(
                conn,
                """SELECT COALESCE(SUM(quantity), 0) AS qty FROM uni_issuances
                   WHERE officer_id = ? AND item_id = ? AND status = 'Outstanding'""",
                (self._officer_id, req["item_id"]),
            )
            qty_issued = issued["qty"] if issued else 0
            met = qty_issued >= req["qty_required"]

            self._compliance_table.setItem(r, 0, QTableWidgetItem(str(req["item_name"])))
            self._compliance_table.setItem(r, 1, QTableWidgetItem(str(req["qty_required"])))
            self._compliance_table.setItem(r, 2, QTableWidgetItem(str(qty_issued)))

            status_item = QTableWidgetItem("Met" if met else "Missing")
            status_item.setForeground(QColor(tc("success") if met else tc("danger")))
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self._compliance_table.setItem(r, 3, status_item)

        if not required:
            _set_empty(self._compliance_table, "No uniform requirements defined for this job title")

        conn.close()

    # ------------------------------------------------------------------
    #  Tab 5: Training
    # ------------------------------------------------------------------

    def _build_training(self):
        layout = QVBoxLayout(self._training_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        conn = get_conn()

        # Course progress
        lbl_prog = QLabel("Course Progress")
        lbl_prog.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_prog.setStyleSheet(f"color: {tc('text')}; border: none;")
        layout.addWidget(lbl_prog)

        prog_cols = ["Course", "Chapters Completed", "Total Chapters", "Progress"]
        self._training_progress_table = _make_table(prog_cols)
        layout.addWidget(self._training_progress_table)

        courses = _safe_query(conn, "SELECT course_id, title FROM trn_courses WHERE status='Published'")
        self._training_progress_table.setRowCount(len(courses))
        for r, course in enumerate(courses):
            cid = course["course_id"]
            total_ch = _safe_query_one(
                conn,
                "SELECT COUNT(*) AS cnt FROM trn_chapters WHERE course_id = ?",
                (cid,),
            )
            done_ch = _safe_query_one(
                conn,
                """SELECT COUNT(*) AS cnt FROM trn_progress
                   WHERE officer_id = ? AND course_id = ? AND completed = 1 AND chapter_id != ''""",
                (self._officer_id, cid),
            )
            t = total_ch["cnt"] if total_ch else 0
            d = done_ch["cnt"] if done_ch else 0
            pct = f"{int((d / t) * 100)}%" if t > 0 else "0%"

            self._training_progress_table.setItem(r, 0, QTableWidgetItem(course["title"]))
            self._training_progress_table.setItem(r, 1, QTableWidgetItem(str(d)))
            self._training_progress_table.setItem(r, 2, QTableWidgetItem(str(t)))

            pct_item = QTableWidgetItem(pct)
            pct_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self._training_progress_table.setItem(r, 3, pct_item)

        if not courses:
            _set_empty(self._training_progress_table, "No published courses found")

        # Test attempts
        lbl_tests = QLabel("Test Attempts")
        lbl_tests.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_tests.setStyleSheet(f"color: {tc('text')}; border: none;")
        layout.addWidget(lbl_tests)

        test_cols = ["Course", "Test", "Score", "Passed", "Date"]
        self._test_table = _make_table(test_cols)
        layout.addWidget(self._test_table)

        attempts = _safe_query(
            conn,
            """SELECT ta.score, ta.passed, ta.completed_at,
                      t.title AS test_title, c.title AS course_title
               FROM trn_test_attempts ta
               LEFT JOIN trn_tests t ON ta.test_id = t.test_id
               LEFT JOIN trn_courses c ON ta.course_id = c.course_id
               WHERE ta.officer_id = ?
               ORDER BY ta.completed_at DESC""",
            (self._officer_id,),
        )
        self._test_table.setRowCount(len(attempts))
        for r, att in enumerate(attempts):
            self._test_table.setItem(r, 0, QTableWidgetItem(str(att["course_title"] or "")))
            self._test_table.setItem(r, 1, QTableWidgetItem(str(att["test_title"] or "")))
            self._test_table.setItem(r, 2, QTableWidgetItem(f"{att['score']:.0f}%"))

            passed_item = QTableWidgetItem("Yes" if att["passed"] else "No")
            passed_item.setForeground(QColor(tc("success") if att["passed"] else tc("danger")))
            passed_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self._test_table.setItem(r, 3, passed_item)

            self._test_table.setItem(r, 4, QTableWidgetItem(str(att["completed_at"] or "")))

        if not attempts:
            _set_empty(self._test_table, "No test attempts recorded")

        # Certificates
        lbl_certs = QLabel("Certificates")
        lbl_certs.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_certs.setStyleSheet(f"color: {tc('text')}; border: none;")
        layout.addWidget(lbl_certs)

        cert_cols = ["Course", "Issued Date", "Expiry Date", "Status"]
        self._cert_table = _make_table(cert_cols)
        layout.addWidget(self._cert_table)

        certs = _safe_query(
            conn,
            """SELECT cr.issued_date, cr.expiry_date, cr.status,
                      c.title AS course_title
               FROM trn_certificates cr
               LEFT JOIN trn_courses c ON cr.course_id = c.course_id
               WHERE cr.officer_id = ?
               ORDER BY cr.issued_date DESC""",
            (self._officer_id,),
        )
        self._cert_table.setRowCount(len(certs))
        for r, cert in enumerate(certs):
            self._cert_table.setItem(r, 0, QTableWidgetItem(str(cert["course_title"] or "")))
            self._cert_table.setItem(r, 1, QTableWidgetItem(str(cert["issued_date"] or "")))
            self._cert_table.setItem(r, 2, QTableWidgetItem(str(cert["expiry_date"] or "")))

            status_item = QTableWidgetItem(str(cert["status"] or ""))
            if cert["status"] == "Active":
                status_item.setForeground(QColor(tc("success")))
            else:
                status_item.setForeground(QColor(tc("danger")))
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self._cert_table.setItem(r, 3, status_item)

        if not certs:
            _set_empty(self._cert_table, "No certificates earned")

        conn.close()
