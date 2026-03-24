"""
Cerasus Hub -- Site Comparison Matrix
Compare 2-3 sites side by side: headcount, infractions, DAs, avg points, etc.
"""

from datetime import date, timedelta
from collections import Counter

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QScrollArea, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, tc, _is_dark, btn_style
from src.database import get_conn
from src.shared_data import get_all_sites
from src.modules.attendance.policy_engine import (
    calculate_active_points, determine_discipline_level,
    DISCIPLINE_LABELS, INFRACTION_TYPES, POINT_WINDOW_DAYS,
)


# ════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════

def _site_metrics(site_name: str) -> dict:
    """Compute all comparison metrics for a single site."""
    conn = get_conn()

    officers = [
        dict(r) for r in conn.execute(
            "SELECT * FROM officers WHERE site = ? AND status = 'Active' ORDER BY name",
            (site_name,),
        ).fetchall()
    ]
    officer_ids = [o.get("officer_id", "") or o.get("employee_id", "") for o in officers]
    headcount = len(officers)

    cutoff = (date.today() - timedelta(days=POINT_WINDOW_DAYS)).isoformat()

    # Active infractions in window
    all_infractions = []
    all_inf_map = {}
    for oid in officer_ids:
        rows = conn.execute(
            "SELECT * FROM ats_infractions WHERE employee_id = ? AND infraction_date >= ?",
            (oid, cutoff),
        ).fetchall()
        inf_list = [dict(r) for r in rows]
        all_infractions.extend(inf_list)

        # All infractions for point calculation
        all_rows = conn.execute(
            "SELECT * FROM ats_infractions WHERE employee_id = ?",
            (oid,),
        ).fetchall()
        all_inf_map[oid] = [dict(r) for r in all_rows]

    # Open DAs
    da_total_open = 0
    for oid in officer_ids:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM da_records WHERE employee_officer_id = ? AND status != 'completed'",
            (oid,),
        ).fetchone()
        da_total_open += row["cnt"] if row else 0

    conn.close()

    # Points and discipline levels
    points_list = []
    vw_plus_count = 0
    for off in officers:
        oid = off.get("officer_id", "") or off.get("employee_id", "")
        inf_all = all_inf_map.get(oid, [])
        active_pts = calculate_active_points(inf_all)
        points_list.append(active_pts)
        level = determine_discipline_level(active_pts)
        if level not in ("", "none"):
            vw_plus_count += 1

    avg_points = round(sum(points_list) / len(points_list), 2) if points_list else 0.0
    active_infraction_count = len(all_infractions)
    infraction_rate = round(active_infraction_count / headcount, 2) if headcount else 0.0

    # Top infraction type
    type_counts = Counter()
    for inf in all_infractions:
        inf_type = inf.get("infraction_type", "Unknown")
        type_def = INFRACTION_TYPES.get(inf_type)
        label = type_def["category"] if type_def else inf_type.replace("_", " ").title()
        type_counts[label] += 1

    top_type = type_counts.most_common(1)[0][0] if type_counts else "N/A"

    return {
        "headcount": headcount,
        "active_infractions": active_infraction_count,
        "avg_points": avg_points,
        "vw_plus": vw_plus_count,
        "open_das": da_total_open,
        "infraction_rate": infraction_rate,
        "top_type": top_type,
        "type_counts": dict(type_counts),
    }


# ════════════════════════════════════════════════════════════════════════
# Site Comparison Page
# ════════════════════════════════════════════════════════════════════════

class SiteComparisonPage(QWidget):
    PAGE_TITLE = "Site Comparison"

    def __init__(self, app_state: dict, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._build_ui()
        self._populate_combos()

    # ── Build UI ─────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        self.layout_main = QVBoxLayout(container)
        self.layout_main.setContentsMargins(32, 24, 32, 24)
        self.layout_main.setSpacing(20)
        scroll.setWidget(container)

        # -- Title --
        title = QLabel("Site Comparison Matrix")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        self.layout_main.addWidget(title)

        subtitle = QLabel("Select 2 or 3 sites to compare metrics side by side")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px; background: transparent;")
        self.layout_main.addWidget(subtitle)

        # -- Selectors row --
        sel_row = QHBoxLayout()
        sel_row.setSpacing(16)

        combo_style = f"""
            QComboBox {{
                padding: 8px 14px;
                font-size: 14px;
                border: 2px solid {tc('border')};
                border-radius: 6px;
                background: {tc('card')};
                color: {tc('text')};
                min-width: 200px;
            }}
        """
        label_style = f"color: {tc('text_light')}; font-size: 13px; font-weight: 600; background: transparent;"

        self.combos = []
        for label_text in ("Site A", "Site B", "Site C (optional)"):
            v_lay = QVBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet(label_style)
            v_lay.addWidget(lbl)
            combo = QComboBox()
            combo.setStyleSheet(combo_style)
            v_lay.addWidget(combo)
            sel_row.addLayout(v_lay)
            self.combos.append(combo)

        sel_row.addSpacing(16)

        compare_btn = QPushButton("Compare")
        compare_btn.setCursor(Qt.PointingHandCursor)
        compare_btn.setFixedHeight(40)
        compare_btn.setStyleSheet(btn_style(COLORS['accent'], "white", COLORS['accent_hover']))
        compare_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: white;
                border: none; border-radius: 6px;
                padding: 10px 28px; font-size: 14px; font-weight: 700;
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        compare_btn.clicked.connect(self._on_compare)
        sel_row.addWidget(compare_btn, alignment=Qt.AlignBottom)

        sel_row.addStretch()
        self.layout_main.addLayout(sel_row)

        # -- Comparison table --
        comp_label = QLabel("Metric Comparison")
        comp_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        comp_label.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        self.layout_main.addWidget(comp_label)

        self.comp_table = QTableWidget()
        self.comp_table.setColumnCount(4)  # Metric + 3 sites max
        self.comp_table.setHorizontalHeaderLabels(["Metric", "Site A", "Site B", "Site C"])
        self.comp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.comp_table.verticalHeader().setVisible(False)
        self.comp_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.comp_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.comp_table.setAlternatingRowColors(True)
        self.comp_table.setMinimumHeight(320)
        self.layout_main.addWidget(self.comp_table)

        # -- Infraction breakdown table --
        bd_label = QLabel("Infraction Breakdown by Type")
        bd_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        bd_label.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        self.layout_main.addWidget(bd_label)

        self.breakdown_table = QTableWidget()
        self.breakdown_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.breakdown_table.verticalHeader().setVisible(False)
        self.breakdown_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.breakdown_table.setAlternatingRowColors(True)
        self.breakdown_table.setMinimumHeight(280)
        self.layout_main.addWidget(self.breakdown_table)

        self.layout_main.addStretch()

    # ── Populate combos ──────────────────────────────────────────────

    def _populate_combos(self):
        sites = get_all_sites(status_filter="Active")
        for combo in self.combos:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("-- Select --", None)
            for s in sites:
                combo.addItem(s["name"], s["site_id"])
            combo.blockSignals(False)

    # ── Refresh (called when page is shown) ──────────────────────────

    def refresh(self):
        self._populate_combos()

    # ── Compare logic ────────────────────────────────────────────────

    def _on_compare(self):
        selected = []
        for combo in self.combos:
            name = combo.currentText()
            if name and name != "-- Select --":
                selected.append(name)

        if len(selected) < 2:
            self.comp_table.setRowCount(0)
            self.breakdown_table.setRowCount(0)
            return

        # De-duplicate
        selected = list(dict.fromkeys(selected))
        if len(selected) < 2:
            return

        # Gather metrics
        site_data = {}
        for name in selected:
            site_data[name] = _site_metrics(name)

        self._fill_comparison_table(selected, site_data)
        self._fill_breakdown_table(selected, site_data)

    # ── Comparison table ─────────────────────────────────────────────

    METRICS = [
        ("Headcount",           "headcount",           "high_good"),
        ("Active Infractions",  "active_infractions",  "low_good"),
        ("Avg Points / Officer","avg_points",          "low_good"),
        ("Officers at VW+",    "vw_plus",             "low_good"),
        ("Open DAs",           "open_das",            "low_good"),
        ("Infraction Rate",    "infraction_rate",     "low_good"),
        ("Top Infraction Type","top_type",            "none"),
    ]

    def _fill_comparison_table(self, sites: list, data: dict):
        col_count = 1 + len(sites)
        self.comp_table.setColumnCount(col_count)
        headers = ["Metric"] + sites
        self.comp_table.setHorizontalHeaderLabels(headers)
        self.comp_table.setRowCount(len(self.METRICS))

        for r, (label, key, rank_mode) in enumerate(self.METRICS):
            self.comp_table.setItem(r, 0, self._metric_item(label))

            values = [data[s].get(key, 0) for s in sites]

            for c, site_name in enumerate(sites):
                val = data[site_name].get(key, 0)
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                item.setFont(QFont("Segoe UI", 13, QFont.Bold))

                # Color-code: best = green, worst = red (for numeric rows)
                if rank_mode != "none" and len(values) >= 2:
                    numeric_vals = [v for v in values if isinstance(v, (int, float))]
                    if numeric_vals and isinstance(val, (int, float)):
                        best = max(numeric_vals) if rank_mode == "high_good" else min(numeric_vals)
                        worst = min(numeric_vals) if rank_mode == "high_good" else max(numeric_vals)
                        if val == best and best != worst:
                            item.setForeground(QColor(tc('success')))
                            item.setBackground(QColor(self._alpha_color(tc('success'), 18)))
                        elif val == worst and best != worst:
                            item.setForeground(QColor(tc('danger')))
                            item.setBackground(QColor(self._alpha_color(tc('danger'), 18)))

                self.comp_table.setItem(r, c + 1, item)

    # ── Infraction breakdown table ───────────────────────────────────

    def _fill_breakdown_table(self, sites: list, data: dict):
        # Gather all infraction types across sites
        all_types = set()
        for s in sites:
            all_types.update(data[s].get("type_counts", {}).keys())
        all_types = sorted(all_types)

        col_count = 1 + len(sites)
        self.breakdown_table.setColumnCount(col_count)
        self.breakdown_table.setHorizontalHeaderLabels(["Infraction Type"] + sites)
        self.breakdown_table.setRowCount(len(all_types))

        for r, inf_type in enumerate(all_types):
            self.breakdown_table.setItem(r, 0, self._metric_item(inf_type))

            counts = [data[s].get("type_counts", {}).get(inf_type, 0) for s in sites]
            max_count = max(counts) if counts else 0
            min_count = min(counts) if counts else 0

            for c, site_name in enumerate(sites):
                cnt = data[site_name].get("type_counts", {}).get(inf_type, 0)
                item = QTableWidgetItem(str(cnt))
                item.setTextAlignment(Qt.AlignCenter)
                item.setFont(QFont("Segoe UI", 13, QFont.Bold))

                # Color: lowest count is best (green), highest is worst (red)
                if max_count != min_count and max_count > 0:
                    if cnt == min_count:
                        item.setForeground(QColor(tc('success')))
                        item.setBackground(QColor(self._alpha_color(tc('success'), 18)))
                    elif cnt == max_count:
                        item.setForeground(QColor(tc('danger')))
                        item.setBackground(QColor(self._alpha_color(tc('danger'), 18)))

                self.breakdown_table.setItem(r, c + 1, item)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _metric_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
        return item

    @staticmethod
    def _alpha_color(hex_color: str, alpha_percent: int) -> str:
        """Convert hex color to a lighter tint by mixing with white at alpha_percent."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            factor = alpha_percent / 100
            r2 = int(r * factor + 255 * (1 - factor))
            g2 = int(g * factor + 255 * (1 - factor))
            b2 = int(b * factor + 255 * (1 - factor))
            return f"#{r2:02X}{g2:02X}{b2:02X}"
        return hex_color
