"""
Cerasus Hub — Hub Analytics Page
Cross-module analytics dashboard accessible from the module picker.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, tc, btn_style
from src.shared_widgets import make_stat_card, BarChartWidget, set_table_empty_state
from src.analytics_engine import get_hub_analytics, get_trend_data
# Lazy-imported in methods that use them to avoid crash if PDF dependencies are missing
# from src.report_generator import generate_executive_summary, generate_all_site_reports


class HubAnalyticsPage(QWidget):
    """Full-page analytics dashboard for Cerasus Hub."""

    def __init__(self, on_back=None, parent=None):
        super().__init__(parent)
        self._on_back = on_back
        self._period_days = 30
        self._build()
        self.refresh()

    # ── Build UI ──────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"""
            QFrame {{ background: {tc('card')}; border-bottom: 1px solid {tc('border')}; }}
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(24, 0, 24, 0)

        if self._on_back:
            back_btn = QPushButton("Back to Hub")
            back_btn.setCursor(Qt.PointingHandCursor)
            back_btn.setFixedHeight(36)
            back_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {tc('text_light')};
                    font-size: 13px; font-weight: 600; border: none; padding: 0 12px;
                }}
                QPushButton:hover {{ color: {COLORS['accent']}; }}
            """)
            back_btn.clicked.connect(self._on_back)
            h_lay.addWidget(back_btn)

        title = QLabel("Analytics & Insights")
        title.setStyleSheet(f"""
            color: {tc('text')}; font-size: 20px; font-weight: 300;
            letter-spacing: 2px; background: transparent; border: none;
        """)
        h_lay.addWidget(title)
        h_lay.addStretch()

        # Period selector
        period_label = QLabel("Period:")
        period_label.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; background: transparent; border: none;")
        h_lay.addWidget(period_label)

        self.period_combo = QComboBox()
        self.period_combo.addItems(["7 Days", "30 Days", "90 Days", "YTD"])
        self.period_combo.setCurrentIndex(1)
        self.period_combo.setFixedWidth(120)
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        h_lay.addWidget(self.period_combo)

        outer.addWidget(header)

        # ── Scrollable content ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background: {tc('bg')}; border: none;")

        content = QWidget()
        content.setStyleSheet(f"background: {tc('bg')};")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(28, 20, 28, 20)
        self._content_layout.setSpacing(16)

        # ── KPI summary row ───────────────────────────────────────────
        self._kpi_grid = QHBoxLayout()
        self._kpi_grid.setSpacing(12)

        self._kpi_cards = {}
        kpi_defs = [
            ("active_officers", "Active Officers", COLORS["info"]),
            ("infractions", "Infractions", COLORS["accent"]),
            ("hours_scheduled", "Hours Scheduled", COLORS["success"]),
            ("outstanding", "Items Outstanding", COLORS["warning"]),
            ("compliance", "Compliance %", COLORS["info"]),
            ("training", "Training %", COLORS["success"]),
        ]
        for key, label, color in kpi_defs:
            card = make_stat_card(label, "—", color)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._kpi_grid.addWidget(card)
            self._kpi_cards[key] = card

        self._content_layout.addLayout(self._kpi_grid)

        # ── Trend charts (2x2) ────────────────────────────────────────
        charts_label = QLabel("Trends")
        charts_label.setStyleSheet(f"""
            color: {tc('text')}; font-size: 16px; font-weight: 600;
            letter-spacing: 1px; background: transparent;
        """)
        self._content_layout.addWidget(charts_label)

        chart_grid = QGridLayout()
        chart_grid.setSpacing(12)

        self._chart_infractions = self._make_chart_card("Infractions per Week")
        self._chart_hours = self._make_chart_card("Hours Scheduled per Week")
        self._chart_issuances = self._make_chart_card("Issuances per Week")
        self._chart_site_points = self._make_chart_card("Attendance Points by Site")

        chart_grid.addWidget(self._chart_infractions["frame"], 0, 0)
        chart_grid.addWidget(self._chart_hours["frame"], 0, 1)
        chart_grid.addWidget(self._chart_issuances["frame"], 1, 0)
        chart_grid.addWidget(self._chart_site_points["frame"], 1, 1)

        self._content_layout.addLayout(chart_grid)

        # ── Tables section ────────────────────────────────────────────
        tables_label = QLabel("Details")
        tables_label.setStyleSheet(f"""
            color: {tc('text')}; font-size: 16px; font-weight: 600;
            letter-spacing: 1px; background: transparent;
        """)
        self._content_layout.addWidget(tables_label)

        # Site Performance table
        site_perf_label = QLabel("Site Performance")
        site_perf_label.setStyleSheet(f"color: {tc('text')}; font-size: 14px; font-weight: 600; background: transparent;")
        self._content_layout.addWidget(site_perf_label)

        self._site_table = QTableWidget()
        self._site_table.setColumnCount(6)
        self._site_table.setHorizontalHeaderLabels([
            "Site", "Officers", "Hours", "Infractions", "Compliance %", "Training %",
        ])
        self._site_table.horizontalHeader().setStretchLastSection(True)
        self._site_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._site_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._site_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._site_table.setAlternatingRowColors(True)
        self._site_table.setMinimumHeight(180)
        self._site_table.setMaximumHeight(300)
        self._content_layout.addWidget(self._site_table)

        # At-Risk Officers table
        risk_label = QLabel("At-Risk Officers")
        risk_label.setStyleSheet(f"color: {tc('text')}; font-size: 14px; font-weight: 600; background: transparent;")
        self._content_layout.addWidget(risk_label)

        self._risk_table = QTableWidget()
        self._risk_table.setColumnCount(5)
        self._risk_table.setHorizontalHeaderLabels([
            "Name", "Site", "Points", "Level", "Last Infraction",
        ])
        self._risk_table.horizontalHeader().setStretchLastSection(True)
        self._risk_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._risk_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._risk_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._risk_table.setAlternatingRowColors(True)
        self._risk_table.setMinimumHeight(140)
        self._risk_table.setMaximumHeight(260)
        self._content_layout.addWidget(self._risk_table)

        # ── Export buttons ────────────────────────────────────────────
        export_row = QHBoxLayout()
        export_row.setSpacing(12)
        export_row.addStretch()

        self.btn_export_pdf = QPushButton("Export PDF Summary")
        self.btn_export_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_export_pdf.setFixedHeight(40)
        self.btn_export_pdf.setStyleSheet(btn_style(COLORS["info"], "white", COLORS["primary_light"]))
        self.btn_export_pdf.clicked.connect(self._export_pdf_summary)
        export_row.addWidget(self.btn_export_pdf)

        self.btn_export_all = QPushButton("Generate All Site Reports")
        self.btn_export_all.setCursor(Qt.PointingHandCursor)
        self.btn_export_all.setFixedHeight(40)
        self.btn_export_all.setStyleSheet(btn_style(COLORS["accent"], "white", COLORS["accent_hover"]))
        self.btn_export_all.clicked.connect(self._export_all_site_reports)
        export_row.addWidget(self.btn_export_all)

        self._content_layout.addLayout(export_row)
        self._content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── Helpers ────────────────────────────────────────────────────────

    def _make_chart_card(self, title: str) -> dict:
        """Create a titled frame containing a BarChartWidget."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')};
                border: 1px solid {tc('border')};
                border-radius: 8px;
            }}
        """)
        frame.setMinimumHeight(220)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        lbl = QLabel(title)
        lbl.setStyleSheet(f"""
            color: {tc('text')}; font-size: 13px; font-weight: 600;
            background: transparent; border: none;
        """)
        lay.addWidget(lbl)

        chart = BarChartWidget()
        lay.addWidget(chart)
        return {"frame": frame, "chart": chart, "label": lbl}

    def _get_period_days(self) -> int:
        """Convert combo selection to days."""
        idx = self.period_combo.currentIndex()
        if idx == 0:
            return 7
        elif idx == 1:
            return 30
        elif idx == 2:
            return 90
        else:
            # YTD
            from datetime import datetime
            now = datetime.now()
            jan1 = datetime(now.year, 1, 1)
            return (now - jan1).days or 1

    # ── Data loading ──────────────────────────────────────────────────

    def refresh(self):
        """Reload all analytics data and update the UI."""
        days = self._get_period_days()
        data = get_hub_analytics(days)
        self._update_kpis(data)
        self._update_charts()
        self._update_site_table(data)
        self._update_risk_table()

    def _update_kpis(self, data: dict):
        """Update the KPI stat cards."""
        wf = data.get("workforce", {})
        att = data.get("attendance", {})
        ops = data.get("operations", {})
        uni = data.get("uniforms", {})
        trn = data.get("training", {})

        mapping = {
            "active_officers": str(wf.get("active", 0)),
            "infractions": str(att.get("total_infractions_period", 0)),
            "hours_scheduled": f"{ops.get('total_hours_scheduled', 0):.0f}",
            "outstanding": str(uni.get("total_outstanding", 0)),
            "compliance": f"{uni.get('compliance_rate', 0):.0f}%",
            "training": f"{trn.get('avg_completion_pct', 0):.0f}%",
        }

        for key, value in mapping.items():
            card = self._kpi_cards.get(key)
            if card:
                # Find the value label (second QLabel in the card's layout)
                layout = card.layout()
                if layout and layout.count() >= 2:
                    val_widget = layout.itemAt(1).widget()
                    if isinstance(val_widget, QLabel):
                        val_widget.setText(value)

    def _update_charts(self):
        """Load trend data and populate bar charts."""
        weeks = 12

        # Infractions per week
        inf_data = get_trend_data("infractions", weeks)
        self._chart_infractions["chart"].set_data([
            (d["week_start"][5:], d["value"], COLORS["accent"]) for d in inf_data
        ])

        # Hours per week
        hrs_data = get_trend_data("hours", weeks)
        self._chart_hours["chart"].set_data([
            (d["week_start"][5:], d["value"], COLORS["success"]) for d in hrs_data
        ])

        # Issuances per week
        iss_data = get_trend_data("issuances", weeks)
        self._chart_issuances["chart"].set_data([
            (d["week_start"][5:], d["value"], "#2563EB") for d in iss_data
        ])

        # Attendance points by site
        from src.database import get_conn
        conn = get_conn()
        site_points = []
        try:
            rows = conn.execute(
                "SELECT site, SUM(points_assigned) as pts FROM ats_infractions "
                "WHERE site != '' GROUP BY site ORDER BY pts DESC LIMIT 10"
            ).fetchall()
            site_points = [(r["site"], r["pts"] or 0, COLORS["warning"]) for r in rows]
        except Exception:
            pass
        conn.close()
        self._chart_site_points["chart"].set_data(site_points)

    def _update_site_table(self, data: dict):
        """Populate the site performance table."""
        from src.database import get_conn
        conn = get_conn()

        sites = []
        try:
            sites = conn.execute(
                "SELECT name FROM sites WHERE status = 'Active' ORDER BY name"
            ).fetchall()
        except Exception:
            pass

        ops_data = data.get("operations", {})
        hours_by_site = ops_data.get("hours_by_site", {})
        att_data = data.get("attendance", {})
        inf_by_site = att_data.get("infractions_by_site", {})
        start_date = data.get("period", {}).get("start", "")
        end_date = data.get("period", {}).get("end", "")

        self._site_table.setRowCount(0)
        self._site_table.setRowCount(len(sites))

        for row_idx, site in enumerate(sites):
            sn = site["name"]

            # Officers count for this site
            officers = 0
            try:
                r = conn.execute(
                    "SELECT COUNT(DISTINCT officer_name) as c FROM ops_assignments "
                    "WHERE site_name = ? AND date BETWEEN ? AND ?",
                    (sn, start_date, end_date),
                ).fetchone()
                officers = r["c"] if r else 0
            except Exception:
                pass

            hours = hours_by_site.get(sn, 0)
            infractions = inf_by_site.get(sn, 0)

            # Compliance % (simplified)
            compliance = "—"
            try:
                officer_names = [r["officer_name"] for r in conn.execute(
                    "SELECT DISTINCT officer_name FROM ops_assignments "
                    "WHERE site_name = ? AND date BETWEEN ? AND ?",
                    (sn, start_date, end_date),
                ).fetchall()]
                if officer_names:
                    ph = ",".join("?" * len(officer_names))
                    issued = conn.execute(
                        f"SELECT COUNT(*) as c FROM uni_issuances "
                        f"WHERE officer_name IN ({ph}) AND status = 'Outstanding'",
                        officer_names,
                    ).fetchone()["c"]
                    req = conn.execute("SELECT COUNT(*) as c FROM uni_requirements").fetchone()["c"]
                    expected = req * len(officer_names)
                    if expected > 0:
                        compliance = f"{issued / expected * 100:.0f}%"
            except Exception:
                pass

            # Training %
            training_pct = "—"
            try:
                officer_names_list = [r["officer_name"] for r in conn.execute(
                    "SELECT DISTINCT officer_name FROM ops_assignments "
                    "WHERE site_name = ? AND date BETWEEN ? AND ?",
                    (sn, start_date, end_date),
                ).fetchall()]
                if officer_names_list:
                    ph = ",".join("?" * len(officer_names_list))
                    oid_rows = conn.execute(
                        f"SELECT officer_id FROM officers WHERE name IN ({ph})",
                        officer_names_list,
                    ).fetchall()
                    oids = [r["officer_id"] for r in oid_rows]
                    total_courses = conn.execute(
                        "SELECT COUNT(*) as c FROM trn_courses WHERE status = 'Published'"
                    ).fetchone()["c"]
                    if oids and total_courses > 0:
                        id_ph = ",".join("?" * len(oids))
                        certs = conn.execute(
                            f"SELECT COUNT(*) as c FROM trn_certificates "
                            f"WHERE officer_id IN ({id_ph}) AND status = 'Active'",
                            oids,
                        ).fetchone()["c"]
                        training_pct = f"{certs / (total_courses * len(oids)) * 100:.0f}%"
            except Exception:
                pass

            items = [sn, str(officers), f"{hours:.0f}", str(infractions), compliance, training_pct]
            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter if col_idx > 0 else Qt.AlignLeft | Qt.AlignVCenter)
                self._site_table.setItem(row_idx, col_idx, item)

        conn.close()
        set_table_empty_state(self._site_table, "No active sites found")

    def _update_risk_table(self):
        """Populate the at-risk officers table."""
        from src.database import get_conn
        conn = get_conn()

        self._risk_table.setRowCount(0)
        try:
            rows = conn.execute(
                "SELECT name, site, active_points, discipline_level, last_infraction_date "
                "FROM officers WHERE active_points >= 5 AND status = 'Active' "
                "ORDER BY active_points DESC"
            ).fetchall()
            self._risk_table.setRowCount(len(rows))
            for row_idx, r in enumerate(rows):
                items = [
                    r["name"] or "",
                    r["site"] or "",
                    str(r["active_points"]),
                    r["discipline_level"] or "",
                    r["last_infraction_date"] or "",
                ]
                for col_idx, val in enumerate(items):
                    item = QTableWidgetItem(val)
                    if col_idx >= 2:
                        item.setTextAlignment(Qt.AlignCenter)
                    self._risk_table.setItem(row_idx, col_idx, item)
        except Exception:
            pass
        conn.close()
        set_table_empty_state(self._risk_table, "No at-risk officers")

    # ── Actions ───────────────────────────────────────────────────────

    def _on_period_changed(self, index):
        self.refresh()

    def _export_pdf_summary(self):
        """Generate and open the executive summary PDF."""
        try:
            from datetime import datetime, timedelta
            days = self._get_period_days()
            end = datetime.now().date()
            start = end - timedelta(days=days)
            from src.report_generator import generate_executive_summary
            fp = generate_executive_summary(start.isoformat(), end.isoformat())
            QMessageBox.information(self, "Report Generated", f"Executive summary saved to:\n{fp}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to generate report:\n{e}")

    def _export_all_site_reports(self):
        """Generate all site reports and show result."""
        try:
            from src.report_generator import generate_all_site_reports
            fps = generate_all_site_reports()
            QMessageBox.information(
                self, "Reports Generated",
                f"Generated {len(fps)} report(s).\nSaved to the reports folder.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to generate reports:\n{e}")
