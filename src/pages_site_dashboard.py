"""
Cerasus Hub -- Site Dashboard Page
Per-site metrics across all modules: headcount, infractions, DAs, attendance points.
"""

from datetime import date, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, tc, _is_dark, btn_style
from src.shared_widgets import make_stat_card
from src.database import get_conn
from src.shared_data import get_all_sites, get_all_officers
from src.modules.attendance.policy_engine import (
    calculate_active_points, determine_discipline_level,
    DISCIPLINE_LABELS, INFRACTION_TYPES, POINT_WINDOW_DAYS,
)


# ════════════════════════════════════════════════════════════════════════
# Site Dashboard Page
# ════════════════════════════════════════════════════════════════════════

class SiteDashboardPage(QWidget):
    PAGE_TITLE = "Site Dashboard"

    def __init__(self, app_state: dict, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self._build_ui()
        self.refresh()

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

        # -- Header row --
        header_row = QHBoxLayout()
        title = QLabel("Site Dashboard")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        header_row.addWidget(title)
        header_row.addStretch()

        # Site selector
        site_lbl = QLabel("Site:")
        site_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 14px; font-weight: 600; background: transparent;")
        header_row.addWidget(site_lbl)

        self.site_combo = QComboBox()
        self.site_combo.setMinimumWidth(260)
        self.site_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 14px;
                font-size: 14px;
                border: 2px solid {tc('border')};
                border-radius: 6px;
                background: {tc('card')};
                color: {tc('text')};
            }}
        """)
        self.site_combo.currentIndexChanged.connect(self._on_site_changed)
        header_row.addWidget(self.site_combo)

        self.layout_main.addLayout(header_row)

        # -- Stats cards row --
        self.cards_row = QHBoxLayout()
        self.cards_row.setSpacing(16)
        self.layout_main.addLayout(self.cards_row)

        # Placeholder cards (replaced on refresh)
        self._card_headcount = None
        self._card_infractions = None
        self._card_das = None
        self._card_avg_points = None

        # -- Officers table --
        officers_label = QLabel("Officers at Site")
        officers_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        officers_label.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        self.layout_main.addWidget(officers_label)

        self.officers_table = QTableWidget()
        self.officers_table.setColumnCount(7)
        self.officers_table.setHorizontalHeaderLabels([
            "Name", "Employee ID", "Position", "Active Points",
            "Discipline Level", "Last Infraction", "DAs",
        ])
        self.officers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.officers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.officers_table.verticalHeader().setVisible(False)
        self.officers_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.officers_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.officers_table.setAlternatingRowColors(True)
        self.officers_table.setSortingEnabled(True)
        self.officers_table.setMinimumHeight(300)
        self.layout_main.addWidget(self.officers_table)

        # -- Infraction breakdown table --
        breakdown_label = QLabel("Site Infraction Breakdown (Last 365 Days)")
        breakdown_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        breakdown_label.setStyleSheet(f"color: {tc('text')}; background: transparent;")
        self.layout_main.addWidget(breakdown_label)

        self.breakdown_table = QTableWidget()
        self.breakdown_table.setColumnCount(2)
        self.breakdown_table.setHorizontalHeaderLabels(["Infraction Type", "Count"])
        self.breakdown_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.breakdown_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.breakdown_table.verticalHeader().setVisible(False)
        self.breakdown_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.breakdown_table.setAlternatingRowColors(True)
        self.breakdown_table.setMaximumHeight(320)
        self.layout_main.addWidget(self.breakdown_table)

        self.layout_main.addStretch()

    # ── Refresh / Data ───────────────────────────────────────────────

    def refresh(self):
        """Reload site list and metrics."""
        self._populate_sites()
        self._refresh_metrics()

    def _populate_sites(self):
        """Fill the site combo with active sites."""
        self.site_combo.blockSignals(True)
        current_text = self.site_combo.currentText()
        self.site_combo.clear()

        sites = get_all_sites(status_filter="Active")
        for s in sites:
            self.site_combo.addItem(s["name"], s["site_id"])

        # Restore previous selection if still valid
        if current_text:
            idx = self.site_combo.findText(current_text)
            if idx >= 0:
                self.site_combo.setCurrentIndex(idx)

        self.site_combo.blockSignals(False)

    def _on_site_changed(self, _index):
        self._refresh_metrics()

    def _refresh_metrics(self):
        """Query all data for the selected site and update the UI."""
        site_name = self.site_combo.currentText()
        if not site_name:
            self._clear_ui()
            return

        conn = get_conn()

        # -- Get officers at this site --
        officers = [
            dict(r) for r in conn.execute(
                "SELECT * FROM officers WHERE site = ? AND status = 'Active' ORDER BY name",
                (site_name,),
            ).fetchall()
        ]
        officer_ids = [o.get("officer_id", "") or o.get("employee_id", "") for o in officers]

        # -- Infractions in last 365 days --
        cutoff = (date.today() - timedelta(days=POINT_WINDOW_DAYS)).isoformat()
        infraction_map = {}  # officer_id -> [infractions]
        all_infractions = []
        for oid in officer_ids:
            rows = conn.execute(
                "SELECT * FROM ats_infractions WHERE employee_id = ? AND infraction_date >= ?",
                (oid, cutoff),
            ).fetchall()
            inf_list = [dict(r) for r in rows]
            infraction_map[oid] = inf_list
            all_infractions.extend(inf_list)

        # -- All infractions (for active point calculation) --
        all_inf_map = {}
        for oid in officer_ids:
            rows = conn.execute(
                "SELECT * FROM ats_infractions WHERE employee_id = ?",
                (oid,),
            ).fetchall()
            all_inf_map[oid] = [dict(r) for r in rows]

        # -- DA records --
        da_counts = {}  # officer_id -> open DA count
        da_total_open = 0
        for oid in officer_ids:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM da_records WHERE employee_officer_id = ? AND status != 'completed'",
                (oid,),
            ).fetchone()
            cnt = row["cnt"] if row else 0
            da_counts[oid] = cnt
            da_total_open += cnt

        conn.close()

        # -- Compute stats --
        headcount = len(officers)
        active_infraction_count = len(all_infractions)

        points_list = []
        officer_rows = []
        for off in officers:
            oid = off.get("officer_id", "") or off.get("employee_id", "")
            inf_all = all_inf_map.get(oid, [])
            active_pts = calculate_active_points(inf_all)
            points_list.append(active_pts)

            level = determine_discipline_level(active_pts)
            level_label = DISCIPLINE_LABELS.get(level, level)

            last_inf = off.get("last_infraction_date", "")
            das = da_counts.get(oid, 0)

            officer_rows.append({
                "name": off.get("name", ""),
                "employee_id": off.get("employee_id", ""),
                "position": off.get("job_title", "") or off.get("role", ""),
                "active_points": active_pts,
                "discipline_level": level_label,
                "last_infraction": last_inf[:10] if last_inf else "",
                "das": das,
            })

        avg_points = round(sum(points_list) / len(points_list), 2) if points_list else 0.0

        # -- Infraction breakdown by category --
        type_counts = {}
        for inf in all_infractions:
            inf_type = inf.get("infraction_type", "Unknown")
            type_def = INFRACTION_TYPES.get(inf_type)
            label = type_def["category"] if type_def else inf_type.replace("_", " ").title()
            type_counts[label] = type_counts.get(label, 0) + 1

        # -- Update UI --
        self._update_cards(headcount, active_infraction_count, da_total_open, avg_points)
        self._update_officers_table(officer_rows)
        self._update_breakdown_table(type_counts)

    def _clear_ui(self):
        self._update_cards(0, 0, 0, 0.0)
        self.officers_table.setRowCount(0)
        self.breakdown_table.setRowCount(0)

    # ── Cards ────────────────────────────────────────────────────────

    def _update_cards(self, headcount, infractions, open_das, avg_points):
        # Remove old cards
        for card in (self._card_headcount, self._card_infractions,
                     self._card_das, self._card_avg_points):
            if card:
                self.cards_row.removeWidget(card)
                card.deleteLater()

        self._card_headcount = make_stat_card("Headcount", str(headcount), tc('info'))
        self._card_infractions = make_stat_card(
            "Active Infractions", str(infractions), tc('warning'))
        self._card_das = make_stat_card("Open DAs", str(open_das), tc('accent'))
        self._card_avg_points = make_stat_card(
            "Avg Points", str(avg_points), self._points_color(avg_points))

        for card in (self._card_headcount, self._card_infractions,
                     self._card_das, self._card_avg_points):
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.cards_row.addWidget(card)

    # ── Officers Table ───────────────────────────────────────────────

    def _update_officers_table(self, rows):
        self.officers_table.setSortingEnabled(False)
        self.officers_table.setRowCount(len(rows))

        for r, data in enumerate(rows):
            self.officers_table.setItem(r, 0, QTableWidgetItem(data["name"]))
            self.officers_table.setItem(r, 1, QTableWidgetItem(data["employee_id"]))
            self.officers_table.setItem(r, 2, QTableWidgetItem(data["position"]))

            # Points cell with color coding
            pts = data["active_points"]
            pts_item = QTableWidgetItem()
            pts_item.setData(Qt.DisplayRole, pts)
            pts_item.setForeground(QColor(self._points_color(pts)))
            pts_font = QFont("Segoe UI", 13, QFont.Bold)
            pts_item.setFont(pts_font)
            self.officers_table.setItem(r, 3, pts_item)

            self.officers_table.setItem(r, 4, QTableWidgetItem(data["discipline_level"]))
            self.officers_table.setItem(r, 5, QTableWidgetItem(data["last_infraction"]))

            das_item = QTableWidgetItem()
            das_item.setData(Qt.DisplayRole, data["das"])
            self.officers_table.setItem(r, 6, das_item)

        self.officers_table.setSortingEnabled(True)

    # ── Breakdown Table ──────────────────────────────────────────────

    def _update_breakdown_table(self, type_counts: dict):
        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        self.breakdown_table.setRowCount(len(sorted_types))

        for r, (label, count) in enumerate(sorted_types):
            self.breakdown_table.setItem(r, 0, QTableWidgetItem(label))
            cnt_item = QTableWidgetItem()
            cnt_item.setData(Qt.DisplayRole, count)
            cnt_item.setTextAlignment(Qt.AlignCenter)
            self.breakdown_table.setItem(r, 1, cnt_item)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _points_color(pts: float) -> str:
        if pts < 2:
            return "#059669"   # green
        elif pts <= 5:
            return "#D97706"   # yellow/amber
        elif pts <= 7:
            return "#EA580C"   # orange
        else:
            return "#DC2626"   # red
