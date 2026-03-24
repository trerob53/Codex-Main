"""
Cerasus Hub -- Attendance Module: Log Infraction Page
Form for logging infractions with real-time point preview, emergency exemption section,
and auto-discipline calculation.
"""

from datetime import date, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QFrame, QCheckBox,
    QDateEdit, QGroupBox, QFormLayout, QScrollArea, QMessageBox,
    QCompleter, QDialog, QDialogButtonBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
)
from PySide6.QtCore import Qt, QDate, QRectF
from PySide6.QtGui import QFont, QColor, QTextDocument, QPainter, QPen, QBrush, QPainterPath
from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter

from src.config import COLORS, tc, _is_dark, btn_style, build_dialog_stylesheet
from src.shared_widgets import confirm_action
from src.shared_data import get_officer, get_officer_timeline
from src.modules.attendance import data_manager
from src.modules.attendance.policy_engine import (
    INFRACTION_TYPES, DISCIPLINE_LABELS, THRESHOLDS, calculate_active_points,
    determine_discipline_level, get_point_expiry_date, count_emergency_exemptions,
    EMERGENCY_MAX,
)
from src import audit
from src.document_vault import (
    DOC_TYPES, upload_document, get_documents_for_officer,
    delete_document, open_document,
)


class DisciplineProgressBar(QWidget):
    """Custom QPainter-based widget showing point total vs discipline thresholds.

    Thresholds: 1.5 -> Verbal, 6 -> Written, 8 -> Review, 10 -> Termination.
    Colored segments: green (0-1.5), yellow (1.5-6), orange (6-8), red (8-10), purple (10+).
    A marker indicates the officer's current point level.
    """

    SEGMENT_COLORS = [
        (1.5, "#22C55E"),   # green: 0 -> 1.5
        (6.0, "#F59E0B"),   # yellow: 1.5 -> 6
        (8.0, "#F97316"),   # orange: 6 -> 8
        (10.0, "#EF4444"),  # red: 8 -> 10
        (12.0, "#9333EA"),  # purple: 10 -> 12 (overflow zone)
    ]

    THRESHOLD_LABELS = [
        (1.5, "Verbal\n1.5"),
        (6.0, "Written\n6"),
        (8.0, "Review\n8"),
        (10.0, "Term.\n10"),
    ]

    def __init__(self, active_points: float = 0.0, parent=None):
        super().__init__(parent)
        self._points = min(active_points, 12.0)
        self.setFixedHeight(72)
        self.setMinimumWidth(300)

    def set_points(self, pts: float):
        self._points = min(pts, 12.0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        max_val = 12.0
        bar_y = 12
        bar_h = 22
        bar_left = 10
        bar_right = w - 10
        bar_w = bar_right - bar_left

        # Draw colored segments
        prev = 0.0
        for threshold, color in self.SEGMENT_COLORS:
            x0 = bar_left + (prev / max_val) * bar_w
            x1 = bar_left + (threshold / max_val) * bar_w
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            # Round corners on first and last segment
            if prev == 0:
                path = QPainterPath()
                path.addRoundedRect(QRectF(x0, bar_y, x1 - x0, bar_h), 4, 4)
                painter.drawPath(path)
            elif threshold == 12.0:
                path = QPainterPath()
                path.addRoundedRect(QRectF(x0, bar_y, x1 - x0, bar_h), 4, 4)
                painter.drawPath(path)
            else:
                painter.drawRect(QRectF(x0, bar_y, x1 - x0, bar_h))
            prev = threshold

        # Draw threshold tick lines and labels
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        for threshold, _ in self.THRESHOLD_LABELS:
            tx = bar_left + (threshold / max_val) * bar_w
            painter.drawLine(int(tx), bar_y, int(tx), bar_y + bar_h)

        # Draw threshold labels below bar
        label_font = QFont("Segoe UI", 8)
        painter.setFont(label_font)
        painter.setPen(QColor(tc('text_light')))
        for threshold, label in self.THRESHOLD_LABELS:
            tx = bar_left + (threshold / max_val) * bar_w
            lines = label.split("\n")
            for li, line in enumerate(lines):
                painter.drawText(
                    QRectF(tx - 24, bar_y + bar_h + 2 + li * 12, 48, 14),
                    Qt.AlignCenter, line
                )

        # Draw current point marker (triangle + value)
        marker_x = bar_left + (self._points / max_val) * bar_w
        marker_x = max(bar_left, min(marker_x, bar_right))

        # Triangle marker above bar
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tc('text')))
        path = QPainterPath()
        path.moveTo(marker_x, bar_y - 1)
        path.lineTo(marker_x - 5, bar_y - 8)
        path.lineTo(marker_x + 5, bar_y - 8)
        path.closeSubpath()
        painter.drawPath(path)

        # Point value label above marker
        painter.setPen(QColor(tc('text')))
        val_font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(val_font)

        painter.end()


class OfficerQuickViewDialog(QDialog):
    """Modal dialog showing an officer's full profile, attendance points, infractions,
    DA records, and a cross-module chronological timeline."""

    # Module colour palette for timeline dots
    MODULE_COLORS = {
        "attendance": "#3B82F6",   # blue
        "da_generator": "#EF4444", # red
        "uniforms": "#9333EA",     # purple
        "training": "#22C55E",     # green
        "system": "#6B7280",       # grey
    }

    def __init__(self, officer_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Officer Quick View")
        self.setMinimumSize(660, 740)
        self.resize(660, 740)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._officer_id = officer_id
        officer = get_officer(officer_id)
        if not officer:
            outer.addWidget(QLabel("Officer not found."))
            return
        self._officer_name = officer.get("name", "")

        # ── Header (above tabs) ──
        header_frame = QFrame()
        header_frame.setStyleSheet(f"background: {tc('card')}; border-bottom: 1px solid {tc('border')};")
        header_lay = QVBoxLayout(header_frame)
        header_lay.setContentsMargins(24, 16, 24, 12)
        header_lay.setSpacing(4)

        name_lbl = QLabel(officer.get("name", "Unknown"))
        name_lbl.setFont(QFont("Segoe UI", 18, QFont.Bold))
        name_lbl.setStyleSheet(f"color: {tc('text')}; background: transparent; border: none;")
        header_lay.addWidget(name_lbl)

        status = officer.get("status", "Unknown")
        status_color = COLORS.get("success") if status == "Active" else COLORS.get("danger")
        status_lbl = QLabel(status.upper())
        status_lbl.setStyleSheet(
            f"background: {status_color}; color: white; padding: 2px 10px; "
            f"border-radius: 10px; font-size: 11px; font-weight: 700;"
        )
        status_lbl.setFixedWidth(105)
        header_lay.addWidget(status_lbl)
        outer.addWidget(header_frame)

        # ── Tab widget ──
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab {{
                background: {tc('card')};
                color: {tc('text_light')};
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid {tc('border')};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {tc('bg')};
                color: {COLORS['accent']};
                border-bottom: 2px solid {COLORS['accent']};
            }}
            QTabBar::tab:hover {{
                color: {COLORS['accent']};
            }}
        """)

        # ── Profile tab (existing content) ──
        profile_tab = self._build_profile_tab(officer, officer_id)
        tabs.addTab(profile_tab, "Profile")

        # ── Timeline tab ──
        timeline_tab = self._build_timeline_tab(officer_id)
        tabs.addTab(timeline_tab, "Timeline")

        # ── Documents tab ──
        docs_tab = self._build_documents_tab(officer_id, officer.get("name", ""))
        tabs.addTab(docs_tab, "Documents")

        outer.addWidget(tabs)

        # ── Close button ──
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        btn_box.setStyleSheet(
            f"QPushButton {{ background: {tc('card')}; color: {tc('text')}; "
            f"border: 1px solid {tc('border')}; border-radius: 6px; "
            f"padding: 8px 24px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {COLORS['accent']}; color: white; }}"
        )
        outer.addWidget(btn_box)

    # ── Profile tab builder ──────────────────────────────────────────

    def _build_profile_tab(self, officer: dict, officer_id: str) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # ── Profile card ──
        profile_card = QFrame()
        profile_card.setStyleSheet(
            f"QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; border-radius: 8px; }}"
        )
        profile_lay = QFormLayout(profile_card)
        profile_lay.setContentsMargins(16, 14, 16, 14)
        profile_lay.setSpacing(8)

        def _info_label(text):
            lbl = QLabel(str(text) if text else "--")
            lbl.setStyleSheet(f"color: {tc('text')}; font-size: 13px;")
            lbl.setWordWrap(True)
            return lbl

        def _field_label(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; font-weight: 600;")
            return lbl

        profile_lay.addRow(_field_label("Employee ID:"), _info_label(officer.get("employee_id")))
        profile_lay.addRow(_field_label("Position:"), _info_label(officer.get("job_title") or officer.get("role_title") or officer.get("role")))
        profile_lay.addRow(_field_label("Site:"), _info_label(officer.get("site")))
        profile_lay.addRow(_field_label("Hire Date:"), _info_label(officer.get("hire_date")))
        profile_lay.addRow(_field_label("Email:"), _info_label(officer.get("email")))
        profile_lay.addRow(_field_label("Phone:"), _info_label(officer.get("phone")))
        layout.addWidget(profile_card)

        # ── Attendance points & discipline ──
        infractions = data_manager.get_infractions_for_employee(officer_id)
        active_pts = calculate_active_points(infractions)
        current_level = determine_discipline_level(active_pts)
        level_label = DISCIPLINE_LABELS.get(current_level, "None")
        exemptions_used = count_emergency_exemptions(infractions)

        pts_card = QFrame()
        pts_card.setStyleSheet(
            f"QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; border-radius: 8px; }}"
        )
        pts_lay = QVBoxLayout(pts_card)
        pts_lay.setContentsMargins(16, 14, 16, 14)
        pts_lay.setSpacing(6)

        pts_title = QLabel("Attendance Summary")
        pts_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        pts_title.setStyleSheet(f"color: {tc('text')};")
        pts_lay.addWidget(pts_title)

        if active_pts >= 10:
            pts_color = COLORS['danger']
        elif active_pts >= 6:
            pts_color = COLORS['warning']
        else:
            pts_color = COLORS.get('success', '#22C55E')

        pts_value = QLabel(f"{active_pts:.1f} active points")
        pts_value.setFont(QFont("Segoe UI", 16, QFont.Bold))
        pts_value.setStyleSheet(f"color: {pts_color};")
        pts_lay.addWidget(pts_value)

        level_lbl = QLabel(f"Discipline Level: {level_label}")
        level_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        pts_lay.addWidget(level_lbl)

        exempt_lbl = QLabel(f"Emergency Exemptions Used: {exemptions_used}/{EMERGENCY_MAX} (last 90 days)")
        exempt_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
        pts_lay.addWidget(exempt_lbl)

        # Discipline progression bar
        progress_label = QLabel("Discipline Progression")
        progress_label.setStyleSheet(f"color: {tc('text')}; font-size: 12px; font-weight: 600; margin-top: 6px;")
        pts_lay.addWidget(progress_label)

        progress_bar = DisciplineProgressBar(active_pts)
        pts_lay.addWidget(progress_bar)

        layout.addWidget(pts_card)

        # ── Discipline History Timeline (#26) ──
        timeline_card = QFrame()
        timeline_card.setStyleSheet(
            f"QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; border-radius: 8px; }}"
        )
        tl_lay = QVBoxLayout(timeline_card)
        tl_lay.setContentsMargins(16, 14, 16, 14)
        tl_lay.setSpacing(6)

        tl_title = QLabel("Discipline Progression Timeline")
        tl_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        tl_title.setStyleSheet(f"color: {tc('text')};")
        tl_lay.addWidget(tl_title)

        # Build timeline from infractions: find the first date each discipline level was reached
        _LEVEL_ORDER = [
            ("verbal_warning", "Verbal Warning", "#3B82F6"),
            ("written_warning", "Written Warning", "#F59E0B"),
            ("employment_review", "Employment Review", "#F97316"),
            ("termination_eligible", "Termination Eligible", "#EF4444"),
        ]
        sorted_inf_tl = sorted(infractions, key=lambda x: x.get("infraction_date", ""))
        level_dates = {}  # level_key -> first date reached
        running_pts = 0.0
        _cutoff_tl = (date.today() - timedelta(days=365)).isoformat()
        for inf in sorted_inf_tl:
            inf_date_str = inf.get("infraction_date", "")
            if not inf_date_str or inf_date_str < _cutoff_tl:
                continue
            if not inf.get("points_active", 1):
                continue
            running_pts += float(inf.get("points_assigned", 0))
            for lvl_key, _, _ in _LEVEL_ORDER:
                if lvl_key not in level_dates:
                    threshold_val = {"verbal_warning": 1.5, "written_warning": 6.0,
                                     "employment_review": 8.0, "termination_eligible": 10.0}.get(lvl_key, 999)
                    if running_pts >= threshold_val:
                        level_dates[lvl_key] = inf_date_str[:10]

        if not level_dates:
            no_prog = QLabel("No discipline thresholds reached in the current point window.")
            no_prog.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; font-style: italic;")
            tl_lay.addWidget(no_prog)
        else:
            for lvl_key, lvl_label, lvl_color in _LEVEL_ORDER:
                step_row = QHBoxLayout()
                step_row.setSpacing(8)

                # Colored dot
                dot = QLabel("\u25CF")
                dot.setFixedWidth(18)
                dot.setAlignment(Qt.AlignCenter)

                if lvl_key in level_dates:
                    dot.setStyleSheet(f"color: {lvl_color}; font-size: 16px; background: transparent;")
                    lbl = QLabel(f"{lvl_label}")
                    lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
                    lbl.setStyleSheet(f"color: {lvl_color};")
                    date_lbl = QLabel(level_dates[lvl_key])
                    date_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px;")
                else:
                    dot.setStyleSheet(f"color: {tc('border')}; font-size: 16px; background: transparent;")
                    lbl = QLabel(f"{lvl_label}")
                    lbl.setFont(QFont("Segoe UI", 12))
                    lbl.setStyleSheet(f"color: {tc('text_light')};")
                    date_lbl = QLabel("--")
                    date_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px;")

                step_row.addWidget(dot)
                step_row.addWidget(lbl)
                step_row.addStretch()
                step_row.addWidget(date_lbl)
                tl_lay.addLayout(step_row)

                # Connector line (except last)
                if lvl_key != "termination_eligible":
                    conn_line = QFrame()
                    conn_line.setFixedWidth(2)
                    conn_line.setFixedHeight(12)
                    reached = lvl_key in level_dates
                    conn_line.setStyleSheet(f"background: {lvl_color if reached else tc('border')};")
                    line_row = QHBoxLayout()
                    line_row.addSpacing(8)
                    line_row.addWidget(conn_line)
                    line_row.addStretch()
                    tl_lay.addLayout(line_row)

        layout.addWidget(timeline_card)

        # ── Last 10 Infractions ──
        inf_card = QFrame()
        inf_card.setStyleSheet(
            f"QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; border-radius: 8px; }}"
        )
        inf_lay = QVBoxLayout(inf_card)
        inf_lay.setContentsMargins(16, 14, 16, 14)
        inf_lay.setSpacing(4)

        inf_title = QLabel(f"Recent Infractions ({len(infractions)} total)")
        inf_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        inf_title.setStyleSheet(f"color: {tc('text')};")
        inf_lay.addWidget(inf_title)

        sorted_inf = sorted(infractions, key=lambda x: x.get("infraction_date", ""), reverse=True)
        if sorted_inf:
            for inf in sorted_inf[:10]:
                inf_type_key = inf.get("infraction_type", "")
                inf_info = INFRACTION_TYPES.get(inf_type_key, {})
                inf_label = inf_info.get("label", inf_type_key)
                inf_pts = inf_info.get("points", 0)
                inf_date = inf.get("infraction_date", "")[:10]

                row_lbl = QLabel(f"  \u2022  {inf_date}  \u2014  {inf_label}  ({inf_pts} pts)")
                row_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
                inf_lay.addWidget(row_lbl)

            if len(sorted_inf) > 10:
                more = QLabel(f"  ... and {len(sorted_inf) - 10} more")
                more.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px; font-style: italic;")
                inf_lay.addWidget(more)
        else:
            none_lbl = QLabel("  No infractions on record.")
            none_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; font-style: italic;")
            inf_lay.addWidget(none_lbl)

        layout.addWidget(inf_card)

        # ── Last 5 DA Records ──
        try:
            from src.modules.da_generator.data_manager import get_das_for_officer_id
            da_records = get_das_for_officer_id(officer_id)
        except Exception:
            da_records = []

        da_card = QFrame()
        da_card.setStyleSheet(
            f"QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; border-radius: 8px; }}"
        )
        da_lay = QVBoxLayout(da_card)
        da_lay.setContentsMargins(16, 14, 16, 14)
        da_lay.setSpacing(4)

        da_title = QLabel(f"Disciplinary Actions ({len(da_records)} total)")
        da_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        da_title.setStyleSheet(f"color: {tc('text')};")
        da_lay.addWidget(da_title)

        level_colors = {
            "Verbal Warning": "#3B82F6",
            "Written Warning": "#F59E0B",
            "Final Warning": "#EF4444",
            "Suspension": "#9333EA",
            "Termination": "#DC2626",
        }

        if da_records:
            for da in da_records[:5]:
                level = da.get("discipline_level", "Unknown")
                created = da.get("created_at", "")[:10]
                status = da.get("status", "draft")
                chip_color = level_colors.get(level, tc('text_light'))

                da_row = QHBoxLayout()
                da_date_lbl = QLabel(created)
                da_date_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; min-width: 80px;")
                da_row.addWidget(da_date_lbl)

                da_level_lbl = QLabel(level or "Unknown")
                da_level_lbl.setStyleSheet(f"color: {chip_color}; font-size: 12px; font-weight: 700;")
                da_row.addWidget(da_level_lbl)

                da_status_lbl = QLabel(status.upper())
                da_status_lbl.setStyleSheet(
                    f"background: {tc('border')}; color: {tc('text_light')}; "
                    f"padding: 1px 6px; border-radius: 3px; font-size: 10px;"
                )
                da_row.addWidget(da_status_lbl)
                da_row.addStretch()
                da_lay.addLayout(da_row)

            if len(da_records) > 5:
                more = QLabel(f"  ... and {len(da_records) - 5} more DA records")
                more.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px; font-style: italic;")
                da_lay.addWidget(more)
        else:
            none_lbl = QLabel("  No disciplinary actions on record.")
            none_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; font-style: italic;")
            da_lay.addWidget(none_lbl)

        layout.addWidget(da_card)

        # ── Custom Fields ──
        try:
            from src.custom_fields import get_all_fields, get_values_for_officer, ensure_custom_fields_tables
            ensure_custom_fields_tables()
            custom_fields = get_all_fields()
            if custom_fields:
                cf_values = get_values_for_officer(officer_id)
                cf_card = QFrame()
                cf_card.setStyleSheet(
                    f"QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; border-radius: 8px; }}"
                )
                cf_lay = QVBoxLayout(cf_card)
                cf_lay.setContentsMargins(16, 14, 16, 14)
                cf_lay.setSpacing(6)

                cf_title = QLabel("Custom Fields")
                cf_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
                cf_title.setStyleSheet(f"color: {tc('text')};")
                cf_lay.addWidget(cf_title)

                cf_form = QFormLayout()
                cf_form.setSpacing(6)
                for field in custom_fields:
                    fname = field.get("field_name", "")
                    value = cf_values.get(fname, "")
                    f_lbl = QLabel(f"{fname}:")
                    f_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; font-weight: 600;")
                    v_lbl = QLabel(str(value) if value else "--")
                    v_lbl.setStyleSheet(f"color: {tc('text')}; font-size: 13px;")
                    v_lbl.setWordWrap(True)
                    cf_form.addRow(f_lbl, v_lbl)
                cf_lay.addLayout(cf_form)
                layout.addWidget(cf_card)
        except Exception:
            pass  # Custom fields module not available or DB not initialized

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Timeline tab builder ─────────────────────────────────────────

    def _build_timeline_tab(self, officer_id: str) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)

        events = get_officer_timeline(officer_id)

        if not events:
            empty_lbl = QLabel("No timeline events found for this officer.")
            empty_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; font-style: italic; padding: 20px;")
            empty_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(empty_lbl)
            layout.addStretch()
            scroll.setWidget(container)
            return scroll

        # ── Legend ──
        legend_row = QHBoxLayout()
        legend_row.setSpacing(16)
        for mod, color in self.MODULE_COLORS.items():
            dot = QLabel("\u25CF")
            dot.setStyleSheet(f"color: {color}; font-size: 14px; background: transparent;")
            dot.setFixedWidth(16)
            label = QLabel(mod.replace("_", " ").title())
            label.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px; background: transparent;")
            pair = QHBoxLayout()
            pair.setSpacing(3)
            pair.addWidget(dot)
            pair.addWidget(label)
            legend_row.addLayout(pair)
        legend_row.addStretch()

        legend_frame = QFrame()
        legend_frame.setStyleSheet(
            f"QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; "
            f"border-radius: 6px; }}"
        )
        legend_inner = QVBoxLayout(legend_frame)
        legend_inner.setContentsMargins(12, 8, 12, 8)
        legend_inner.addLayout(legend_row)
        layout.addWidget(legend_frame)
        layout.addSpacing(12)

        # ── Group events by month ──
        current_month = ""
        line_color = tc('border')

        for event in events:
            ev_date = event.get("date", "")
            if len(ev_date) >= 7:
                month_key = ev_date[:7]  # "YYYY-MM"
            else:
                month_key = "Unknown"

            if month_key != current_month:
                current_month = month_key
                # Month header
                try:
                    from datetime import datetime as _dt
                    month_display = _dt.strptime(month_key, "%Y-%m").strftime("%B %Y")
                except Exception:
                    month_display = month_key

                if layout.count() > 2:  # add spacing between month groups
                    layout.addSpacing(8)

                month_lbl = QLabel(month_display)
                month_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
                month_lbl.setStyleSheet(
                    f"color: {tc('text')}; padding: 6px 0 4px 0; background: transparent;"
                )
                layout.addWidget(month_lbl)

            # ── Single timeline event row ──
            module = event.get("module", "system")
            dot_color = self.MODULE_COLORS.get(module, self.MODULE_COLORS.get("system", "#6B7280"))
            severity = event.get("severity", "neutral")

            event_frame = QFrame()
            event_frame.setStyleSheet(
                f"QFrame {{ background: transparent; border: none; }}"
            )
            event_row = QHBoxLayout(event_frame)
            event_row.setContentsMargins(0, 2, 0, 2)
            event_row.setSpacing(0)

            # Date column (fixed width, right-aligned)
            date_lbl = QLabel(ev_date)
            date_lbl.setFixedWidth(82)
            date_lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
            date_lbl.setStyleSheet(
                f"color: {tc('text_light')}; font-size: 11px; "
                f"padding-top: 4px; padding-right: 8px; background: transparent;"
            )
            event_row.addWidget(date_lbl)

            # Timeline spine: dot + vertical line
            spine = QFrame()
            spine.setFixedWidth(24)
            spine.setMinimumHeight(36)
            spine.setStyleSheet("background: transparent;")
            spine_lay = QVBoxLayout(spine)
            spine_lay.setContentsMargins(8, 4, 8, 0)
            spine_lay.setSpacing(0)

            dot_lbl = QLabel("\u25CF")
            dot_lbl.setStyleSheet(f"color: {dot_color}; font-size: 16px; background: transparent;")
            dot_lbl.setAlignment(Qt.AlignCenter)
            dot_lbl.setFixedHeight(18)
            spine_lay.addWidget(dot_lbl)

            line = QFrame()
            line.setFixedWidth(2)
            line.setStyleSheet(f"background: {line_color};")
            line.setSizePolicy(line.sizePolicy().horizontalPolicy(), line.sizePolicy().Expanding)
            spine_lay.addWidget(line, 1, Qt.AlignHCenter)

            event_row.addWidget(spine)

            # Event content card
            content_card = QFrame()
            # Determine left-border color based on severity
            sev_colors = {
                "danger": COLORS.get("danger", "#EF4444"),
                "warning": COLORS.get("warning", "#F59E0B"),
                "success": COLORS.get("success", "#22C55E"),
                "info": "#3B82F6",
                "neutral": tc('border'),
            }
            left_border = sev_colors.get(severity, tc('border'))
            content_card.setStyleSheet(
                f"QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; "
                f"border-left: 3px solid {left_border}; border-radius: 6px; }}"
            )
            content_lay = QVBoxLayout(content_card)
            content_lay.setContentsMargins(10, 6, 10, 6)
            content_lay.setSpacing(2)

            # Module + type badge line
            badge_row = QHBoxLayout()
            badge_row.setSpacing(6)

            mod_label = QLabel(module.replace("_", " ").title())
            mod_label.setStyleSheet(
                f"background: {dot_color}; color: white; padding: 1px 8px; "
                f"border-radius: 3px; font-size: 10px; font-weight: 700;"
            )
            badge_row.addWidget(mod_label)

            type_label = QLabel(event.get("type", "").replace("_", " ").title())
            type_label.setStyleSheet(
                f"color: {tc('text_light')}; font-size: 10px; font-weight: 600;"
            )
            badge_row.addWidget(type_label)
            badge_row.addStretch()
            content_lay.addLayout(badge_row)

            # Summary text
            summary_lbl = QLabel(event.get("summary", ""))
            summary_lbl.setWordWrap(True)
            summary_lbl.setStyleSheet(f"color: {tc('text')}; font-size: 12px;")
            content_lay.addWidget(summary_lbl)

            event_row.addWidget(content_card, 1)

            layout.addWidget(event_frame)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Documents tab builder ────────────────────────────────────────

    def _build_documents_tab(self, officer_id: str, officer_name: str) -> QWidget:
        from datetime import datetime as _dt

        wrapper = QWidget()
        main_lay = QVBoxLayout(wrapper)
        main_lay.setContentsMargins(16, 12, 16, 12)
        main_lay.setSpacing(10)

        # ── Upload button row ──
        top_row = QHBoxLayout()
        upload_btn = QPushButton("+ Upload Document")
        upload_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['accent']}; color: white; "
            f"border-radius: 6px; padding: 9px 22px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {COLORS['accent_hover']}; }}"
        )
        top_row.addWidget(upload_btn)
        top_row.addStretch()
        main_lay.addLayout(top_row)

        # ── Documents table ──
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["Type", "Filename", "Size", "Uploaded", "Expiry", "By", "Actions"])
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        main_lay.addWidget(table, 1)

        # Store references for refresh
        self._docs_table = table
        self._docs_officer_id = officer_id
        self._docs_officer_name = officer_name

        def _refresh_docs_table():
            docs = get_documents_for_officer(officer_id)
            table.setRowCount(len(docs))
            today = _dt.now().date()
            for row_idx, doc in enumerate(docs):
                # Type
                table.setItem(row_idx, 0, QTableWidgetItem(doc.get("doc_type", "")))

                # Filename
                table.setItem(row_idx, 1, QTableWidgetItem(doc.get("original_filename", "")))

                # Size
                size_bytes = doc.get("file_size", 0) or 0
                if size_bytes >= 1_048_576:
                    size_str = f"{size_bytes / 1_048_576:.1f} MB"
                elif size_bytes >= 1024:
                    size_str = f"{size_bytes / 1024:.0f} KB"
                else:
                    size_str = f"{size_bytes} B"
                table.setItem(row_idx, 2, QTableWidgetItem(size_str))

                # Uploaded date
                created = doc.get("created_at", "")[:10]
                table.setItem(row_idx, 3, QTableWidgetItem(created))

                # Expiry date (highlight amber/red)
                expiry = doc.get("expiry_date", "")
                expiry_item = QTableWidgetItem(expiry if expiry else "--")
                if expiry:
                    try:
                        exp_date = _dt.strptime(expiry, "%Y-%m-%d").date()
                        days_left = (exp_date - today).days
                        if days_left < 0:
                            expiry_item.setForeground(QColor(COLORS["danger"]))
                            expiry_item.setToolTip(f"EXPIRED ({abs(days_left)} days ago)")
                        elif days_left <= 30:
                            expiry_item.setForeground(QColor(COLORS["warning"]))
                            expiry_item.setToolTip(f"Expires in {days_left} day(s)")
                    except ValueError:
                        pass
                table.setItem(row_idx, 4, expiry_item)

                # Uploaded by
                table.setItem(row_idx, 5, QTableWidgetItem(doc.get("uploaded_by", "")))

                # Actions: Open + Delete buttons
                action_widget = QWidget()
                action_lay = QHBoxLayout(action_widget)
                action_lay.setContentsMargins(4, 2, 4, 2)
                action_lay.setSpacing(4)

                open_btn = QPushButton("Open")
                open_btn.setFixedHeight(26)
                open_btn.setStyleSheet(
                    f"QPushButton {{ background: {tc('primary_light')}; color: white; "
                    f"border-radius: 4px; padding: 2px 10px; font-size: 11px; font-weight: 600; }}"
                    f"QPushButton:hover {{ background: {tc('primary_mid')}; }}"
                )
                doc_id = doc["doc_id"]
                open_btn.clicked.connect(lambda _, did=doc_id: open_document(did))
                action_lay.addWidget(open_btn)

                del_btn = QPushButton("Delete")
                del_btn.setFixedHeight(26)
                del_btn.setStyleSheet(
                    f"QPushButton {{ background: {COLORS['danger']}; color: white; "
                    f"border-radius: 4px; padding: 2px 10px; font-size: 11px; font-weight: 600; }}"
                    f"QPushButton:hover {{ background: {COLORS['accent_hover']}; }}"
                )
                del_btn.clicked.connect(lambda _, did=doc_id: _delete_doc(did))
                action_lay.addWidget(del_btn)

                table.setCellWidget(row_idx, 6, action_widget)

        def _delete_doc(doc_id):
            if not confirm_action(self, "Delete this document? This cannot be undone."):
                return
            delete_document(doc_id)
            _refresh_docs_table()

        def _show_upload_dialog():
            dlg = QDialog(self)
            dlg.setWindowTitle("Upload Document")
            dlg.setMinimumWidth(420)
            dlg.setStyleSheet(build_dialog_stylesheet(_is_dark()))

            form_lay = QVBoxLayout(dlg)
            form_lay.setContentsMargins(20, 16, 20, 16)
            form_lay.setSpacing(10)

            # Doc type
            type_lbl = QLabel("Document Type")
            type_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; font-weight: 600;")
            form_lay.addWidget(type_lbl)
            type_combo = QComboBox()
            type_combo.addItems(DOC_TYPES)
            form_lay.addWidget(type_combo)

            # Description
            desc_lbl = QLabel("Description (optional)")
            desc_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; font-weight: 600;")
            form_lay.addWidget(desc_lbl)
            desc_edit = QLineEdit()
            desc_edit.setPlaceholderText("e.g. Guard Card renewal 2026")
            form_lay.addWidget(desc_edit)

            # Expiry date
            exp_lbl = QLabel("Expiry Date (optional)")
            exp_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px; font-weight: 600;")
            form_lay.addWidget(exp_lbl)
            exp_date = QDateEdit()
            exp_date.setCalendarPopup(True)
            exp_date.setDisplayFormat("yyyy-MM-dd")
            exp_date.setDate(QDate.currentDate().addYears(1))
            exp_check = QCheckBox("Set expiry date")
            form_lay.addWidget(exp_check)
            form_lay.addWidget(exp_date)
            exp_date.setVisible(False)
            exp_check.toggled.connect(exp_date.setVisible)

            # File picker
            file_row = QHBoxLayout()
            file_edit = QLineEdit()
            file_edit.setPlaceholderText("No file selected")
            file_edit.setReadOnly(True)
            file_row.addWidget(file_edit, 1)
            browse_btn = QPushButton("Browse...")
            browse_btn.setStyleSheet(
                f"QPushButton {{ background: {tc('primary_light')}; color: white; "
                f"border-radius: 4px; padding: 8px 16px; font-size: 12px; font-weight: 600; }}"
                f"QPushButton:hover {{ background: {tc('primary_mid')}; }}"
            )

            def _pick_file():
                path, _ = QFileDialog.getOpenFileName(
                    dlg, "Select Document", "",
                    "All Files (*);;PDF (*.pdf);;Images (*.png *.jpg *.jpeg);;Documents (*.doc *.docx)",
                )
                if path:
                    file_edit.setText(path)

            browse_btn.clicked.connect(_pick_file)
            file_row.addWidget(browse_btn)
            form_lay.addLayout(file_row)

            # Buttons
            btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btn_box.accepted.connect(dlg.accept)
            btn_box.rejected.connect(dlg.reject)
            form_lay.addWidget(btn_box)

            if dlg.exec() != QDialog.Accepted:
                return
            if not file_edit.text():
                QMessageBox.warning(self, "No File", "Please select a file to upload.")
                return

            expiry_str = ""
            if exp_check.isChecked():
                expiry_str = exp_date.date().toString("yyyy-MM-dd")

            upload_document(
                officer_id=officer_id,
                officer_name=officer_name,
                doc_type=type_combo.currentText(),
                source_path=file_edit.text(),
                description=desc_edit.text().strip(),
                expiry_date=expiry_str,
                uploaded_by="",  # Could be populated from app_state if available
            )
            _refresh_docs_table()

        upload_btn.clicked.connect(_show_upload_dialog)

        # Initial load
        _refresh_docs_table()

        return wrapper


# ════════════════════════════════════════════════════════════════════════
# Bulk Infraction Entry Dialog (#27)
# ════════════════════════════════════════════════════════════════════════

class BulkInfractionDialog(QDialog):
    """Dialog for logging the same infraction type for multiple officers at once."""

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.setWindowTitle("Bulk Infraction Entry")
        self.setMinimumSize(620, 600)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._officer_checks = []  # list of (QCheckBox, officer_id)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Bulk Infraction Entry")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        desc = QLabel("Log the same infraction for multiple officers at once.")
        desc.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
        layout.addWidget(desc)

        # Infraction details form
        form = QFormLayout()
        form.setSpacing(8)

        self.type_combo = QComboBox()
        for key, info in INFRACTION_TYPES.items():
            pts_text = f"{info['points']} pts" if info['points'] > 0 else "0 pts"
            self.type_combo.addItem(f"{info['label']} ({pts_text})", key)
        form.addRow("Infraction Type:", self.type_combo)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Infraction Date:", self.date_edit)

        self.site_combo = QComboBox()
        self.site_combo.setEditable(True)
        self.site_combo.setInsertPolicy(QComboBox.NoInsert)
        from src.shared_data import get_sites_for_user
        sites = get_sites_for_user(self.app_state)
        for s in sites:
            self.site_combo.addItem(s.get("name", ""))
        form.addRow("Site:", self.site_combo)

        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(60)
        self.notes_edit.setPlaceholderText("Notes (applied to all)...")
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        # Officer selection
        officer_grp = QGroupBox("Select Officers")
        officer_grp.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 13px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 6px;
                margin-top: 8px; padding-top: 18px; background: {tc('card')};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
        """)
        officer_outer = QVBoxLayout(officer_grp)

        # Select all / none
        sel_row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.setStyleSheet(btn_style(COLORS['info']))
        btn_all.clicked.connect(lambda: self._toggle_all(True))
        sel_row.addWidget(btn_all)
        btn_none = QPushButton("Select None")
        btn_none.setStyleSheet(btn_style(tc('text_light')))
        btn_none.clicked.connect(lambda: self._toggle_all(False))
        sel_row.addWidget(btn_none)
        self.lbl_selected_count = QLabel("0 selected")
        self.lbl_selected_count.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
        sel_row.addWidget(self.lbl_selected_count)
        sel_row.addStretch()
        officer_outer.addLayout(sel_row)

        # Scrollable checkbox list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(250)
        scroll_widget = QWidget()
        self._check_layout = QVBoxLayout(scroll_widget)
        self._check_layout.setSpacing(4)
        self._check_layout.setContentsMargins(8, 8, 8, 8)

        from src.shared_data import filter_by_user_sites
        officers = data_manager.get_active_officers()
        officers = filter_by_user_sites(self.app_state, officers)
        officers.sort(key=lambda o: o.get("name", ""))

        for off in officers:
            name = off.get("name", "")
            eid = off.get("employee_id", "")
            oid = off.get("officer_id", "")
            site = off.get("site", "")
            chk = QCheckBox(f"{name} ({eid}) - {site}")
            chk.setStyleSheet(f"color: {tc('text')}; font-size: 12px;")
            chk.toggled.connect(self._update_count)
            self._officer_checks.append((chk, oid))
            self._check_layout.addWidget(chk)

        self._check_layout.addStretch()
        scroll.setWidget(scroll_widget)
        officer_outer.addWidget(scroll)
        layout.addWidget(officer_grp)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(btn_style(tc('text_light')))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Log Infractions")
        btn_save.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS.get('accent_hover', COLORS['accent'])))
        btn_save.clicked.connect(self._save_all)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _toggle_all(self, checked):
        for chk, _ in self._officer_checks:
            chk.setChecked(checked)

    def _update_count(self):
        count = sum(1 for chk, _ in self._officer_checks if chk.isChecked())
        self.lbl_selected_count.setText(f"{count} selected")

    def _save_all(self):
        selected = [(chk, oid) for chk, oid in self._officer_checks if chk.isChecked()]
        if not selected:
            QMessageBox.warning(self, "No Officers", "Please select at least one officer.")
            return

        inf_type = self.type_combo.currentData()
        if not inf_type:
            QMessageBox.warning(self, "Validation", "Please select an infraction type.")
            return

        type_info = INFRACTION_TYPES.get(inf_type, {})
        inf_date = self.date_edit.date().toString("yyyy-MM-dd")
        site = self.site_combo.currentText()
        notes = self.notes_edit.toPlainText().strip()
        username = self.app_state.get("username", "")

        count = len(selected)
        if not confirm_action(
            self, "Confirm Bulk Entry",
            f"Log {type_info.get('label', inf_type)} for {count} officer(s) on {inf_date}?"
        ):
            return

        logged = 0
        for chk, oid in selected:
            fields = {
                "employee_id": oid,
                "infraction_type": inf_type,
                "infraction_date": inf_date,
                "description": notes,
                "site": site,
            }
            data_manager.create_infraction(fields, entered_by=username)
            logged += 1

        audit.log_event(
            "attendance", "bulk_infraction_created", username,
            details=f"Bulk logged {type_info.get('label', inf_type)} for {logged} officers on {inf_date}",
        )

        QMessageBox.information(
            self, "Bulk Entry Complete",
            f"Successfully logged {logged} infraction(s)."
        )
        self.accept()


class InfractionsPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._officer_map = {}  # display_text -> officer_id
        self._build()

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # Header
        title = QLabel("Log Infraction")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        # ── Form card
        form_card = QFrame()
        form_card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 8px;
            }}
        """)
        form_layout = QFormLayout(form_card)
        form_layout.setContentsMargins(24, 20, 24, 20)
        form_layout.setSpacing(14)

        # Officer selection (autocomplete) + Quick View button
        self.officer_combo = QComboBox()
        self.officer_combo.setEditable(True)
        self.officer_combo.setInsertPolicy(QComboBox.NoInsert)
        self.officer_combo.setMinimumWidth(350)
        self.officer_combo.currentIndexChanged.connect(self._on_officer_changed)

        self.btn_officer_quick_view = QPushButton("\U0001f441 Quick View")
        self.btn_officer_quick_view.setCursor(Qt.PointingHandCursor)
        self.btn_officer_quick_view.setFixedHeight(34)
        self.btn_officer_quick_view.setStyleSheet(
            f"QPushButton {{ background: {tc('card')}; color: {tc('text')}; "
            f"border: 1px solid {tc('border')}; border-radius: 6px; "
            f"padding: 4px 12px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {COLORS['accent']}; color: white; "
            f"border-color: {COLORS['accent']}; }}"
        )
        self.btn_officer_quick_view.clicked.connect(self._open_officer_quick_view)

        self.btn_print_summary = QPushButton("\U0001f5b6 Print Summary")
        self.btn_print_summary.setCursor(Qt.PointingHandCursor)
        self.btn_print_summary.setFixedHeight(34)
        self.btn_print_summary.setStyleSheet(
            f"QPushButton {{ background: {tc('card')}; color: {tc('text')}; "
            f"border: 1px solid {tc('border')}; border-radius: 6px; "
            f"padding: 4px 12px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {COLORS['accent']}; color: white; "
            f"border-color: {COLORS['accent']}; }}"
        )
        self.btn_print_summary.clicked.connect(self._print_summary)

        officer_row = QHBoxLayout()
        officer_row.setSpacing(8)
        officer_row.addWidget(self.officer_combo, 1)
        officer_row.addWidget(self.btn_officer_quick_view)
        officer_row.addWidget(self.btn_print_summary)
        form_layout.addRow("Officer:", officer_row)

        # Infraction type dropdown
        self.type_combo = QComboBox()
        self.type_combo.setMinimumWidth(350)
        for key, info in INFRACTION_TYPES.items():
            pts_text = f"{info['points']} pts" if info['points'] > 0 else "0 pts"
            self.type_combo.addItem(f"{info['label']} ({pts_text})", key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form_layout.addRow("Infraction Type:", self.type_combo)

        # Date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form_layout.addRow("Infraction Date:", self.date_edit)

        # Site
        self.site_combo = QComboBox()
        self.site_combo.setEditable(True)
        self.site_combo.setInsertPolicy(QComboBox.NoInsert)
        form_layout.addRow("Site:", self.site_combo)

        # Description/notes
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        self.notes_edit.setPlaceholderText("Description or notes...")
        form_layout.addRow("Notes:", self.notes_edit)

        layout.addWidget(form_card)

        # ── Prior Discipline History (DA records + infraction history)
        self.history_card = QFrame()
        self.history_card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 8px;
            }}
        """)
        history_lay = QVBoxLayout(self.history_card)
        history_lay.setContentsMargins(24, 16, 24, 16)

        history_header = QHBoxLayout()
        history_title = QLabel("Prior Discipline History")
        history_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        history_title.setStyleSheet(f"color: {tc('text')};")
        history_header.addWidget(history_title)
        self.lbl_history_badge = QLabel("")
        self.lbl_history_badge.setStyleSheet(
            f"background: {tc('border')}; color: {tc('text_light')}; "
            f"padding: 2px 10px; border-radius: 10px; font-size: 12px;"
        )
        history_header.addWidget(self.lbl_history_badge)
        history_header.addStretch()
        history_lay.addLayout(history_header)

        self.history_container = QVBoxLayout()
        self.history_container.setSpacing(8)
        history_lay.addLayout(self.history_container)

        self.lbl_no_history = QLabel("Select an officer to view discipline history.")
        self.lbl_no_history.setStyleSheet(f"color: {tc('text_light')}; font-style: italic; padding: 8px 0;")
        self.history_container.addWidget(self.lbl_no_history)

        layout.addWidget(self.history_card)

        # ── Emergency Exemption section
        self.exemption_group = QGroupBox("Emergency Exemption")
        self.exemption_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 14px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 20px; background: {tc('card')};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 6px; }}
        """)
        exemption_lay = QVBoxLayout(self.exemption_group)
        self.chk_documentation = QCheckBox("Documentation Provided")
        self.chk_approved = QCheckBox("Exemption Approved")
        self.exemption_warning = QLabel("")
        self.exemption_warning.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
        exemption_lay.addWidget(self.chk_documentation)
        exemption_lay.addWidget(self.chk_approved)
        exemption_lay.addWidget(self.exemption_warning)
        self.exemption_group.setVisible(False)
        layout.addWidget(self.exemption_group)

        # ── Real-time point preview
        preview_card = QFrame()
        preview_card.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 8px;
            }}
        """)
        preview_lay = QVBoxLayout(preview_card)
        preview_lay.setContentsMargins(24, 16, 24, 16)

        preview_title = QLabel("Point Preview")
        preview_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        preview_title.setStyleSheet(f"color: {tc('text')};")
        preview_lay.addWidget(preview_title)

        pts_row = QHBoxLayout()
        self.lbl_current_pts = QLabel("Current: 0")
        self.lbl_current_pts.setFont(QFont("Segoe UI", 14))
        self.lbl_current_pts.setStyleSheet(f"color: {tc('text_light')};")
        pts_row.addWidget(self.lbl_current_pts)

        plus_lbl = QLabel("+")
        plus_lbl.setFont(QFont("Segoe UI", 16, QFont.Bold))
        plus_lbl.setStyleSheet(f"color: {tc('text_light')};")
        pts_row.addWidget(plus_lbl)

        self.lbl_new_pts = QLabel("New: 0")
        self.lbl_new_pts.setFont(QFont("Segoe UI", 14))
        self.lbl_new_pts.setStyleSheet(f"color: {COLORS['warning']};")
        pts_row.addWidget(self.lbl_new_pts)

        eq_lbl = QLabel("=")
        eq_lbl.setFont(QFont("Segoe UI", 16, QFont.Bold))
        eq_lbl.setStyleSheet(f"color: {tc('text_light')};")
        pts_row.addWidget(eq_lbl)

        self.lbl_total_pts = QLabel("Total: 0")
        self.lbl_total_pts.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.lbl_total_pts.setStyleSheet(f"color: {tc('text')};")
        pts_row.addWidget(self.lbl_total_pts)

        pts_row.addStretch()
        preview_lay.addLayout(pts_row)

        self.lbl_discipline_preview = QLabel("Discipline Level: None")
        self.lbl_discipline_preview.setFont(QFont("Segoe UI", 13))
        self.lbl_discipline_preview.setStyleSheet(f"color: {tc('text_light')};")
        preview_lay.addWidget(self.lbl_discipline_preview)

        self.lbl_expiry_preview = QLabel("Points expire: --")
        self.lbl_expiry_preview.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
        preview_lay.addWidget(self.lbl_expiry_preview)

        layout.addWidget(preview_card)

        # ── Save & Export buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_bulk_entry = QPushButton("Bulk Entry")
        self.btn_bulk_entry.setStyleSheet(btn_style(COLORS['warning']))
        self.btn_bulk_entry.setFixedWidth(160)
        self.btn_bulk_entry.setFixedHeight(44)
        self.btn_bulk_entry.clicked.connect(self._open_bulk_entry)
        btn_row.addWidget(self.btn_bulk_entry)

        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_csv.setStyleSheet(btn_style(COLORS['info']))
        self.btn_export_csv.setFixedWidth(160)
        self.btn_export_csv.setFixedHeight(44)
        self.btn_export_csv.clicked.connect(self._export_csv)
        btn_row.addWidget(self.btn_export_csv)

        self.btn_save = QPushButton("Save Infraction")
        self.btn_save.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        self.btn_save.setFixedWidth(200)
        self.btn_save.setFixedHeight(44)
        self.btn_save.clicked.connect(self._save_infraction)
        btn_row.addWidget(self.btn_save)
        layout.addLayout(btn_row)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self):
        from src.shared_data import filter_by_user_sites, get_sites_for_user

        # Populate officer combo (filtered by user's assigned sites)
        self.officer_combo.blockSignals(True)
        current_text = self.officer_combo.currentText()
        self.officer_combo.clear()
        self._officer_map.clear()

        officers = data_manager.get_active_officers()
        officers = filter_by_user_sites(self.app_state, officers)
        for off in officers:
            name = off.get("name", "")
            eid = off.get("employee_id", "")
            oid = off.get("officer_id", "")
            display = f"{name} ({eid})" if eid else name
            self._officer_map[display] = oid
            self.officer_combo.addItem(display, oid)

        # Set up completer
        completer = QCompleter(list(self._officer_map.keys()))
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.officer_combo.setCompleter(completer)

        if current_text:
            idx = self.officer_combo.findText(current_text)
            if idx >= 0:
                self.officer_combo.setCurrentIndex(idx)
        self.officer_combo.blockSignals(False)

        # Populate site combo (filtered by user's assigned sites)
        self.site_combo.blockSignals(True)
        current_site = self.site_combo.currentText()
        self.site_combo.clear()
        sites = get_sites_for_user(self.app_state)
        for s in sites:
            self.site_combo.addItem(s.get("name", ""))
        if current_site:
            idx = self.site_combo.findText(current_site)
            if idx >= 0:
                self.site_combo.setCurrentIndex(idx)
        self.site_combo.blockSignals(False)

        self._update_preview()
        self._update_discipline_history()

    def _on_officer_changed(self, idx):
        self._update_preview()
        self._update_discipline_history()

    def _on_type_changed(self, idx):
        inf_type = self.type_combo.currentData()
        # Show/hide emergency exemption section
        is_emergency = inf_type in ("emergency_exemption_approved", "emergency_exemption_denied")
        self.exemption_group.setVisible(is_emergency)

        if is_emergency:
            # Check exemption count
            officer_id = self.officer_combo.currentData()
            if officer_id:
                infractions = data_manager.get_infractions_for_employee(officer_id)
                used = count_emergency_exemptions(infractions)
                if used >= EMERGENCY_MAX:
                    self.exemption_warning.setText(
                        f"Warning: Officer has already used {used}/{EMERGENCY_MAX} emergency exemptions in 90 days."
                    )
                else:
                    self.exemption_warning.setText(
                        f"Exemptions used: {used}/{EMERGENCY_MAX} in last 90 days."
                    )

        self._update_preview()

    def _update_preview(self):
        officer_id = self.officer_combo.currentData()
        inf_type = self.type_combo.currentData()
        type_info = INFRACTION_TYPES.get(inf_type, {})
        new_pts = type_info.get("points", 0)

        current_pts = 0.0
        if officer_id:
            infractions = data_manager.get_infractions_for_employee(officer_id)
            current_pts = calculate_active_points(infractions)

        total_pts = current_pts + new_pts
        level = determine_discipline_level(total_pts)

        self.lbl_current_pts.setText(f"Current: {current_pts:.1f}")
        self.lbl_new_pts.setText(f"New: +{new_pts}")
        self.lbl_total_pts.setText(f"Total: {total_pts:.1f}")

        level_label = DISCIPLINE_LABELS.get(level, level)
        self.lbl_discipline_preview.setText(f"Discipline Level: {level_label}")

        # Color the total based on severity
        if total_pts >= 10:
            self.lbl_total_pts.setStyleSheet(f"color: {COLORS['danger']}; font-size: 16px; font-weight: bold;")
        elif total_pts >= 8:
            self.lbl_total_pts.setStyleSheet(f"color: #9333EA; font-size: 16px; font-weight: bold;")
        elif total_pts >= 6:
            self.lbl_total_pts.setStyleSheet(f"color: {COLORS['warning']}; font-size: 16px; font-weight: bold;")
        else:
            self.lbl_total_pts.setStyleSheet(f"color: {tc('text')}; font-size: 16px; font-weight: bold;")

        # Auto-discipline from type
        auto_disc = type_info.get("auto_discipline", "")
        if auto_disc:
            disc_label = DISCIPLINE_LABELS.get(auto_disc, auto_disc)
            self.lbl_discipline_preview.setText(
                f"Discipline Level: {level_label}  |  Auto: {disc_label}"
            )

        # Expiry date preview
        inf_date = self.date_edit.date().toString("yyyy-MM-dd")
        expiry = get_point_expiry_date(inf_date)
        self.lbl_expiry_preview.setText(f"Points expire: {expiry}")

    def _update_discipline_history(self):
        """Show recent DA records and infraction summary for the selected officer."""
        # Clear existing history items (keep the layout itself)
        while self.history_container.count():
            item = self.history_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        officer_id = self.officer_combo.currentData()
        if not officer_id:
            lbl = QLabel("Select an officer to view discipline history.")
            lbl.setStyleSheet(f"color: {tc('text_light')}; font-style: italic; padding: 8px 0;")
            self.history_container.addWidget(lbl)
            self.lbl_history_badge.setText("")
            return

        # ── Fetch DA records for this officer ──
        try:
            from src.modules.da_generator.data_manager import get_das_for_officer_id
            da_records = get_das_for_officer_id(officer_id)
        except Exception:
            da_records = []

        # ── Fetch recent infractions ──
        infractions = data_manager.get_infractions_for_employee(officer_id)
        active_pts = calculate_active_points(infractions)
        current_level = determine_discipline_level(active_pts)
        level_label = DISCIPLINE_LABELS.get(current_level, "None")

        # Summary line
        summary = QLabel(
            f"Active Points: {active_pts:.1f}  |  Current Level: {level_label}  |  "
            f"Total Infractions: {len(infractions)}  |  DA Records: {len(da_records)}"
        )
        summary.setFont(QFont("Segoe UI", 12))
        summary.setStyleSheet(
            f"color: {tc('text')}; background: {tc('bg')}; "
            f"padding: 8px 12px; border-radius: 6px;"
        )
        summary.setWordWrap(True)
        self.history_container.addWidget(summary)

        total_items = len(da_records) + len(infractions)
        if total_items == 0:
            self.lbl_history_badge.setText("Clean Record")
            self.lbl_history_badge.setStyleSheet(
                f"background: {COLORS['success']}; color: white; "
                f"padding: 2px 10px; border-radius: 10px; font-size: 12px;"
            )
        else:
            self.lbl_history_badge.setText(f"{len(da_records)} DA{'s' if len(da_records) != 1 else ''}")
            badge_color = COLORS['danger'] if len(da_records) >= 2 else (
                COLORS['warning'] if len(da_records) == 1 else COLORS['success']
            )
            self.lbl_history_badge.setStyleSheet(
                f"background: {badge_color}; color: white; "
                f"padding: 2px 10px; border-radius: 10px; font-size: 12px;"
            )

        # ── Show DA records (most recent first, limit 5) ──
        if da_records:
            da_header = QLabel("Disciplinary Actions:")
            da_header.setFont(QFont("Segoe UI", 12, QFont.Bold))
            da_header.setStyleSheet(f"color: {tc('text')}; padding-top: 4px;")
            self.history_container.addWidget(da_header)

            for da in da_records[:5]:
                level = da.get("discipline_level", "Unknown")
                created = da.get("created_at", "")[:10]
                violation = da.get("violation_type", "")
                status = da.get("status", "draft")
                narrative_preview = (da.get("incident_narrative", "") or "")[:80]
                if len(da.get("incident_narrative", "") or "") > 80:
                    narrative_preview += "..."

                # Color-coded severity chip
                level_colors = {
                    "Verbal Warning": "#3B82F6",
                    "Written Warning": "#F59E0B",
                    "Final Warning": "#EF4444",
                    "Suspension": "#9333EA",
                    "Termination": "#DC2626",
                }
                chip_color = level_colors.get(level, tc('text_light'))

                da_row = QFrame()
                da_row.setStyleSheet(
                    f"background: {tc('bg')}; border: 1px solid {tc('border')}; "
                    f"border-left: 4px solid {chip_color}; border-radius: 4px;"
                )
                da_row_lay = QVBoxLayout(da_row)
                da_row_lay.setContentsMargins(12, 8, 12, 8)
                da_row_lay.setSpacing(2)

                top_line = QHBoxLayout()
                lbl_level = QLabel(level or "Unknown")
                lbl_level.setFont(QFont("Segoe UI", 11, QFont.Bold))
                lbl_level.setStyleSheet(f"color: {chip_color};")
                top_line.addWidget(lbl_level)

                lbl_date = QLabel(created)
                lbl_date.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px;")
                top_line.addWidget(lbl_date)

                if violation:
                    lbl_viol = QLabel(f"({violation})")
                    lbl_viol.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px;")
                    top_line.addWidget(lbl_viol)

                lbl_status = QLabel(status.upper())
                lbl_status.setStyleSheet(
                    f"background: {tc('border')}; color: {tc('text_light')}; "
                    f"padding: 1px 6px; border-radius: 3px; font-size: 10px;"
                )
                top_line.addWidget(lbl_status)
                top_line.addStretch()
                da_row_lay.addLayout(top_line)

                if narrative_preview:
                    lbl_narr = QLabel(narrative_preview)
                    lbl_narr.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px;")
                    lbl_narr.setWordWrap(True)
                    da_row_lay.addWidget(lbl_narr)

                self.history_container.addWidget(da_row)

            if len(da_records) > 5:
                more_lbl = QLabel(f"... and {len(da_records) - 5} more DA records")
                more_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px; font-style: italic;")
                self.history_container.addWidget(more_lbl)

        # ── Show recent infractions (last 5) ──
        if infractions:
            inf_header = QLabel("Recent Infractions:")
            inf_header.setFont(QFont("Segoe UI", 12, QFont.Bold))
            inf_header.setStyleSheet(f"color: {tc('text')}; padding-top: 4px;")
            self.history_container.addWidget(inf_header)

            sorted_inf = sorted(infractions, key=lambda x: x.get("infraction_date", ""), reverse=True)
            for inf in sorted_inf[:5]:
                inf_type_key = inf.get("infraction_type", "")
                inf_info = INFRACTION_TYPES.get(inf_type_key, {})
                inf_label = inf_info.get("label", inf_type_key)
                inf_pts = inf_info.get("points", 0)
                inf_date = inf.get("infraction_date", "")[:10]

                inf_row = QLabel(f"  •  {inf_date}  —  {inf_label}  ({inf_pts} pts)")
                inf_row.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px;")
                self.history_container.addWidget(inf_row)

            if len(infractions) > 5:
                more_lbl = QLabel(f"  ... and {len(infractions) - 5} more infractions")
                more_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 11px; font-style: italic;")
                self.history_container.addWidget(more_lbl)

    def _open_officer_quick_view(self):
        """Open the Officer Quick View dialog for the currently selected officer."""
        officer_id = self.officer_combo.currentData()
        if not officer_id:
            QMessageBox.warning(self, "No Officer Selected", "Please select an officer first.")
            return
        dlg = OfficerQuickViewDialog(officer_id, parent=self)
        dlg.exec()

    def _print_summary(self):
        """Generate and print an infraction summary report for the selected officer."""
        officer_id = self.officer_combo.currentData()
        if not officer_id:
            QMessageBox.warning(self, "No Officer", "Select an officer first.")
            return

        html = self._build_summary_html(officer_id)

        doc = QTextDocument()
        doc.setHtml(html)

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageOrientation(printer.pageLayout().orientation())
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Infraction Summary Report")
        preview.paintRequested.connect(lambda p: doc.print_(p))
        preview.exec()

    def _build_summary_html(self, officer_id: str) -> str:
        """Build a print-ready HTML infraction summary report."""
        from datetime import date as dt_date

        officer = get_officer(officer_id)
        if not officer:
            return "<h1>Officer not found.</h1>"

        infractions = data_manager.get_infractions_for_employee(officer_id)
        active_pts = calculate_active_points(infractions)
        current_level = determine_discipline_level(active_pts)
        level_label = DISCIPLINE_LABELS.get(current_level, "None")
        exemptions_used = count_emergency_exemptions(infractions)
        username = self.app_state.get("username", "Unknown")

        # Fetch DA records
        try:
            from src.modules.da_generator.data_manager import get_das_for_officer_id
            da_records = get_das_for_officer_id(officer_id)
        except Exception:
            da_records = []

        # ── Styles ──
        css = """
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; color: #111; margin: 0; padding: 20px; }
            h1 { font-size: 16pt; text-align: center; margin-bottom: 2px; letter-spacing: 1px; }
            h2 { font-size: 12pt; border-bottom: 2px solid #333; padding-bottom: 4px; margin-top: 18px; margin-bottom: 8px; }
            .subtitle { text-align: center; font-size: 10pt; color: #555; margin-bottom: 16px; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
            th, td { border: 1px solid #999; padding: 5px 8px; font-size: 9pt; text-align: left; }
            th { background-color: #e0e0e0; font-weight: bold; }
            tr:nth-child(even) td { background-color: #f7f7f7; }
            .info-table td { border: none; padding: 3px 10px; font-size: 10pt; }
            .info-table .label { font-weight: bold; width: 140px; color: #333; }
            .status-box { border: 2px solid #333; padding: 10px 14px; margin-bottom: 12px; }
            .status-box .value { font-size: 14pt; font-weight: bold; }
            .footer { margin-top: 20px; border-top: 1px solid #999; padding-top: 6px; font-size: 8pt; color: #666; text-align: center; }
            .no-data { font-style: italic; color: #888; padding: 6px 0; }
        </style>
        """

        # ── Header ──
        header = """
        <h1>CERASUS SECURITY &mdash; INFRACTION SUMMARY REPORT</h1>
        <div class="subtitle">Confidential &mdash; For Internal Use Only</div>
        """

        # ── Officer Info ──
        officer_name = officer.get("name", "Unknown")
        emp_id = officer.get("employee_id", "--")
        position = officer.get("job_title") or officer.get("role_title") or officer.get("role", "--")
        site = officer.get("site", "--")
        hire_date = officer.get("hire_date", "--")

        officer_info = f"""
        <h2>Officer Information</h2>
        <table class="info-table">
            <tr><td class="label">Name:</td><td>{officer_name}</td>
                <td class="label">Employee ID:</td><td>{emp_id}</td></tr>
            <tr><td class="label">Position:</td><td>{position}</td>
                <td class="label">Site:</td><td>{site}</td></tr>
            <tr><td class="label">Hire Date:</td><td>{hire_date}</td>
                <td class="label">Status:</td><td>{officer.get("status", "--")}</td></tr>
        </table>
        """

        # ── Current Status ──
        status_section = f"""
        <h2>Current Status</h2>
        <div class="status-box">
            <table class="info-table">
                <tr><td class="label">Active Points:</td><td><span class="value">{active_pts:.1f}</span></td>
                    <td class="label">Discipline Level:</td><td><span class="value">{level_label}</span></td></tr>
                <tr><td class="label">Emergency Exemptions Used:</td><td>{exemptions_used}/{EMERGENCY_MAX} (last 90 days)</td>
                    <td class="label">Total Infractions:</td><td>{len(infractions)}</td></tr>
            </table>
        </div>
        """

        # ── Infraction History Table ──
        sorted_inf = sorted(infractions, key=lambda x: x.get("infraction_date", ""), reverse=True)
        if sorted_inf:
            inf_rows = ""
            for inf in sorted_inf:
                inf_type_key = inf.get("infraction_type", "")
                inf_info = INFRACTION_TYPES.get(inf_type_key, {})
                inf_label = inf_info.get("label", inf_type_key)
                inf_pts = inf.get("points_assigned", inf_info.get("points", 0))
                inf_date = inf.get("infraction_date", "")[:10]
                inf_site = inf.get("site", "")
                inf_desc = inf.get("description", "")
                inf_by = inf.get("entered_by", "")
                inf_rows += f"""
                <tr>
                    <td>{inf_date}</td>
                    <td>{inf_label}</td>
                    <td style="text-align:center;">{inf_pts}</td>
                    <td>{inf_site}</td>
                    <td>{inf_desc}</td>
                    <td>{inf_by}</td>
                </tr>"""
            infraction_table = f"""
            <h2>Infraction History</h2>
            <table>
                <tr>
                    <th style="width:80px;">Date</th>
                    <th>Type</th>
                    <th style="width:50px;">Points</th>
                    <th>Site</th>
                    <th>Description</th>
                    <th>Entered By</th>
                </tr>
                {inf_rows}
            </table>
            """
        else:
            infraction_table = """
            <h2>Infraction History</h2>
            <p class="no-data">No infractions on record.</p>
            """

        # ── Point Expiry Schedule ──
        today = dt_date.today()
        expiry_entries = []
        running_total = active_pts
        for inf in sorted_inf:
            inf_date_str = inf.get("infraction_date", "")
            if not inf_date_str or not inf.get("points_active", 1):
                continue
            pts = float(inf.get("points_assigned", 0))
            if pts <= 0:
                continue
            expiry_str = get_point_expiry_date(inf_date_str)
            if not expiry_str:
                continue
            try:
                exp_date = date.fromisoformat(expiry_str) if isinstance(expiry_str, str) else expiry_str
            except (ValueError, TypeError):
                continue
            if exp_date > today:
                expiry_entries.append((expiry_str, pts, inf_date_str[:10]))

        # Sort by expiry date ascending
        expiry_entries.sort(key=lambda x: x[0])

        if expiry_entries:
            expiry_rows = ""
            remaining = active_pts
            for exp_date, pts, orig_date in expiry_entries:
                remaining -= pts
                remaining = max(remaining, 0)
                expiry_rows += f"""
                <tr>
                    <td>{exp_date}</td>
                    <td style="text-align:center;">{pts}</td>
                    <td>From infraction on {orig_date}</td>
                    <td style="text-align:center;">{remaining:.1f}</td>
                </tr>"""
            expiry_section = f"""
            <h2>Point Expiry Schedule</h2>
            <table>
                <tr>
                    <th style="width:100px;">Expiry Date</th>
                    <th style="width:60px;">Points</th>
                    <th>Source</th>
                    <th style="width:80px;">New Total</th>
                </tr>
                {expiry_rows}
            </table>
            """
        else:
            expiry_section = """
            <h2>Point Expiry Schedule</h2>
            <p class="no-data">No upcoming point expirations.</p>
            """

        # ── DA History ──
        if da_records:
            da_rows = ""
            for da in da_records:
                da_level = da.get("discipline_level", "Unknown")
                da_created = da.get("created_at", "")[:10]
                da_status = da.get("status", "draft")
                da_violation = da.get("violation_type", "")
                da_narrative = (da.get("incident_narrative", "") or "")[:120]
                if len(da.get("incident_narrative", "") or "") > 120:
                    da_narrative += "..."
                da_rows += f"""
                <tr>
                    <td>{da_created}</td>
                    <td>{da_level}</td>
                    <td>{da_violation}</td>
                    <td>{da_status.upper()}</td>
                    <td>{da_narrative}</td>
                </tr>"""
            da_section = f"""
            <h2>Disciplinary Action History</h2>
            <table>
                <tr>
                    <th style="width:80px;">Date</th>
                    <th>Level</th>
                    <th>Violation</th>
                    <th style="width:70px;">Status</th>
                    <th>Summary</th>
                </tr>
                {da_rows}
            </table>
            """
        else:
            da_section = """
            <h2>Disciplinary Action History</h2>
            <p class="no-data">No disciplinary action records.</p>
            """

        # ── Footer ──
        gen_date = dt_date.today().isoformat()
        footer = f"""
        <div class="footer">
            Generated on {gen_date} by {username} &mdash; Cerasus Hub Attendance Module
        </div>
        """

        return f"<html><head>{css}</head><body>{header}{officer_info}{status_section}{infraction_table}{expiry_section}{da_section}{footer}</body></html>"

    def _export_csv(self):
        """Export infractions to CSV. If an officer is selected, export only their
        infractions; otherwise export all infractions."""
        import csv as csv_mod
        import io

        officer_id = self.officer_combo.currentData()
        if officer_id:
            infractions = data_manager.get_infractions_for_employee(officer_id)
            officer_name = self.officer_combo.currentText()
            default_name = f"infractions_{officer_id}.csv"
        else:
            infractions = data_manager.get_all_infractions()
            officer_name = "All Officers"
            default_name = "infractions_all.csv"

        if not infractions:
            QMessageBox.information(self, "No Data", "No infractions to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Infractions CSV", default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        fieldnames = [
            "id", "employee_id", "infraction_type", "infraction_date",
            "points_assigned", "description", "site", "discipline_triggered",
            "points_active", "point_expiry_date", "entered_by",
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv_mod.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(infractions)

            username = self.app_state.get("username", "")
            audit.log_event(
                "attendance", "infractions_exported", username,
                details=f"Exported {len(infractions)} infractions for {officer_name} to CSV.",
            )
            QMessageBox.information(
                self, "Export Complete",
                f"Exported {len(infractions)} infraction(s) to:\n{path}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Export Error", f"Failed to export CSV:\n{exc}")

    def _open_bulk_entry(self):
        """Open the Bulk Infraction Entry dialog."""
        dlg = BulkInfractionDialog(self.app_state, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._update_preview()
            self._update_discipline_history()

    def _save_infraction(self):
        officer_id = self.officer_combo.currentData()
        if not officer_id:
            QMessageBox.warning(self, "Validation", "Please select an officer.")
            return

        inf_type = self.type_combo.currentData()
        if not inf_type:
            QMessageBox.warning(self, "Validation", "Please select an infraction type.")
            return

        type_info = INFRACTION_TYPES.get(inf_type, {})
        inf_date = self.date_edit.date().toString("yyyy-MM-dd")
        site = self.site_combo.currentText()
        notes = self.notes_edit.toPlainText().strip()
        username = self.app_state.get("username", "")

        fields = {
            "employee_id": officer_id,
            "infraction_type": inf_type,
            "infraction_date": inf_date,
            "description": notes,
            "site": site,
        }

        # Emergency exemption fields
        if inf_type in ("emergency_exemption_approved", "emergency_exemption_denied"):
            fields["documentation_provided"] = self.chk_documentation.isChecked()
            fields["exemption_approved"] = self.chk_approved.isChecked()

        # Duplicate check: same type within last 7 days
        existing = data_manager.get_infractions_for_employee(officer_id)
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        for ex in existing:
            if ex.get("infraction_type") == inf_type and ex.get("infraction_date", "") >= cutoff:
                dup_date = ex.get("infraction_date", "unknown date")
                dup_reply = QMessageBox.warning(
                    self, "Possible Duplicate",
                    f"This officer already has a {type_info.get('label', inf_type)} "
                    f"logged on {dup_date}.\n\nDo you still want to proceed?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if dup_reply != QMessageBox.Yes:
                    return
                break  # Only warn once

        if not confirm_action(self, "Confirm Infraction",
                              f"Log {type_info.get('label', inf_type)} for this officer?"):
            return

        infraction_id = data_manager.create_infraction(fields, entered_by=username)

        # Audit log
        officer_name = self.officer_combo.currentText()
        audit.log_event(
            "attendance", "infraction_created", username,
            details=f"Logged {type_info.get('label', inf_type)} for {officer_name}",
            table_name="ats_infractions", record_id=str(infraction_id),
            action="create", employee_id=officer_id,
        )

        QMessageBox.information(self, "Success", "Infraction logged successfully.")

        # ── Check if a NEW discipline threshold was crossed ──
        self._check_discipline_threshold(officer_id, officer_name, inf_date, inf_type, type_info)

        # Reset form
        self.notes_edit.clear()
        self.date_edit.setDate(QDate.currentDate())
        self.chk_documentation.setChecked(False)
        self.chk_approved.setChecked(False)
        self._update_preview()

    def _check_discipline_threshold(self, officer_id, officer_name, inf_date, inf_type, type_info):
        """Check if the new infraction pushed the employee to a NEW discipline threshold."""
        # Get current infractions (including the one just saved)
        infractions = data_manager.get_infractions_for_employee(officer_id)
        new_points = calculate_active_points(infractions)
        new_level = determine_discipline_level(new_points)

        # Calculate what points were BEFORE this infraction by subtracting the new infraction's points
        infraction_pts = float(type_info.get("points", 0))
        old_points = new_points - infraction_pts
        old_level = determine_discipline_level(old_points)

        # Only prompt if we crossed into a NEW threshold level
        if new_level == old_level or new_level == "none":
            return

        level_label = DISCIPLINE_LABELS.get(new_level, new_level)

        reply = QMessageBox.question(
            self,
            "Discipline Threshold Reached",
            f"{officer_name} has reached {new_points:.1f} active points.\n\n"
            f"This triggers a {level_label} under the progressive discipline policy.\n\n"
            f"Would you like to generate a Disciplinary Action document now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if reply != QMessageBox.Yes:
            return

        # Navigate to DA Generator module
        self._navigate_to_da_generator(officer_id, officer_name, inf_date, inf_type, type_info, new_points)

    def _navigate_to_da_generator(self, officer_id, officer_name, inf_date, inf_type, type_info, active_points):
        """Switch to DA Generator module and pre-populate with attendance data."""

        officer_data = get_officer(officer_id)
        if not officer_data:
            return

        infraction_data = {
            "infraction_type": inf_type,
            "infraction_date": inf_date,
            "type_label": type_info.get("label", inf_type),
            "points": type_info.get("points", 0),
        }

        main_window = self.window()
        if hasattr(main_window, '_enter_module'):
            for mod in getattr(main_window, '_modules', []):
                if mod.module_id == 'da_generator':
                    main_window._enter_module(mod)
                    # Try to pre-populate via the shell
                    shell = getattr(main_window, '_current_shell', None)
                    if shell and shell.pages:
                        wizard = shell.pages[0]
                        if hasattr(wizard, 'pre_populate_from_attendance'):
                            wizard.pre_populate_from_attendance(officer_data, infraction_data, active_points)
                    break
