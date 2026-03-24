"""
Cerasus Hub — Shared Widgets
SidebarButton, BarChartWidget, and common UI helpers used across all modules.
"""

from PySide6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox, QFileDialog, QStackedWidget,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QRect, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush

from src.config import COLORS, DARK_COLORS, tc, _is_dark, btn_style, SPACING, FONT_SIZES, RADIUS


# ── Breadcrumb Bar ────────────────────────────────────────────────────

class BreadcrumbBar(QWidget):
    """Clickable breadcrumb navigation: Hub > Module > Page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 6, 16, 6)
        self._layout.setSpacing(0)
        self._labels: list[QLabel] = []
        self.setFixedHeight(28)

    def set_path(self, segments: list[tuple[str, callable]]):
        """Set breadcrumb segments. Each segment is (display_text, on_click_callback).
        The last segment is shown as non-clickable (current location).
        """
        # Clear existing
        for lbl in self._labels:
            self._layout.removeWidget(lbl)
            lbl.deleteLater()
        self._labels.clear()

        for i, (text, callback) in enumerate(segments):
            is_last = (i == len(segments) - 1)

            if i > 0:
                sep = QLabel("  >  ")
                sep.setStyleSheet(f"""
                    color: {tc('text_light')};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 12px;
                    background: transparent;
                    border: none;
                """)
                self._layout.addWidget(sep)
                self._labels.append(sep)

            lbl = QLabel(text)
            if is_last:
                lbl.setStyleSheet(f"""
                    color: {tc('text')};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 12px;
                    font-weight: 600;
                    background: transparent;
                    border: none;
                """)
            else:
                lbl.setCursor(Qt.PointingHandCursor)
                lbl.setStyleSheet(f"""
                    QLabel {{
                        color: {tc('text_light')};
                        font-family: 'Segoe UI', Arial, sans-serif;
                        font-size: 12px;
                        font-weight: 500;
                        background: transparent;
                        border: none;
                    }}
                    QLabel:hover {{
                        color: {tc('text')};
                        text-decoration: underline;
                    }}
                """)
                # Bind click via mousePressEvent
                cb = callback  # capture
                lbl.mousePressEvent = lambda ev, fn=cb: fn()
            self._layout.addWidget(lbl)
            self._labels.append(lbl)

        self._layout.addStretch()


# ── Sidebar Button ─────────────────────────────────────────────────────

class SidebarButton(QPushButton):
    """Navigation button for the module sidebar."""
    def __init__(self, text, icon_char="", parent=None):
        super().__init__(parent)
        display = f"  {text}"
        self.setText(display)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(42)
        self.setStyleSheet(self._style(active=False))

    def set_active(self, active: bool):
        self.setStyleSheet(self._style(active=active))

    def _style(self, active=False):
        dark = _is_dark()
        c = DARK_COLORS if dark else COLORS
        if active:
            return f"""
                QPushButton {{
                    background: rgba(255, 255, 255, 0.12);
                    color: white;
                    text-align: left;
                    padding-left: 13px;
                    font-size: 14px;
                    font-weight: 700;
                    border: none;
                    border-left: 3px solid {c['sidebar_active']};
                    border-radius: 0px;
                    border-top-right-radius: 6px;
                    border-bottom-right-radius: 6px;
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background: transparent;
                    color: {c['sidebar_text']};
                    text-align: left;
                    padding-left: 16px;
                    font-size: 14px;
                    font-weight: 500;
                    border: none;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background: rgba(255, 255, 255, 0.10);
                    color: white;
                }}
            """


# ── Section Label ──────────────────────────────────────────────────────

class SidebarSectionLabel(QLabel):
    """Section header label in the sidebar."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        c = DARK_COLORS if _is_dark() else COLORS
        self.setStyleSheet(f"""
            color: {c['sidebar_text']};
            font-size: 11px;
            font-weight: 700;
            padding-left: 18px;
            padding-top: 14px;
            padding-bottom: 4px;
            background: transparent;
            letter-spacing: 1px;
        """)


# ── Bar Chart Widget ───────────────────────────────────────────────────

class BarChartWidget(QWidget):
    """Simple horizontal bar chart widget."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self.setMinimumHeight(160)
        self.setMaximumHeight(280)

    def set_data(self, data):
        """data: [(label, value, color_hex), ...]"""
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        max_val = max(v for _, v, _ in self._data) if self._data else 1
        if max_val == 0:
            max_val = 1

        bar_height = min(28, max(16, (h - 20) // max(len(self._data), 1) - 6))
        label_width = 120
        value_width = 60
        chart_width = w - label_width - value_width - 20

        y = 10
        for label, value, color in self._data:
            painter.setPen(QPen(QColor(tc('text'))))
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.drawText(QRect(4, y, label_width - 8, bar_height),
                             Qt.AlignRight | Qt.AlignVCenter, label[:16])

            bar_x = label_width
            bar_bg = "#45475a" if _is_dark() else "#f3f4f6"
            painter.setBrush(QBrush(QColor(bar_bg)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_x, y + 2, chart_width, bar_height - 4, 4, 4)

            fill_width = int((value / max_val) * chart_width) if max_val > 0 else 0
            fill_width = max(fill_width, 4)
            painter.setBrush(QBrush(QColor(color)))
            painter.drawRoundedRect(bar_x, y + 2, fill_width, bar_height - 4, 4, 4)

            painter.setPen(QPen(QColor(tc('text_light'))))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(QRect(bar_x + chart_width + 4, y, value_width, bar_height),
                             Qt.AlignLeft | Qt.AlignVCenter, str(value))

            y += bar_height + 6
        painter.end()


# ── Sparkline Widget ───────────────────────────────────────────────────

class SparklineWidget(QWidget):
    """Tiny inline line chart for showing trends."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self.setFixedHeight(24)
        self.setMinimumWidth(60)

    def set_data(self, data: list):
        """data: list of numeric values (most recent last)."""
        self._data = [float(d) for d in data if d is not None] if data else []
        self.update()

    def paintEvent(self, event):
        if len(self._data) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        padding = 2

        min_val = min(self._data)
        max_val = max(self._data)
        val_range = max_val - min_val if max_val != min_val else 1

        points = []
        for i, val in enumerate(self._data):
            x = padding + (i / (len(self._data) - 1)) * (w - 2 * padding)
            y = h - padding - ((val - min_val) / val_range) * (h - 2 * padding)
            points.append((x, y))

        # Determine color based on trend
        if self._data[-1] > self._data[0]:
            color = QColor(tc('success'))
        elif self._data[-1] < self._data[0]:
            color = QColor(tc('danger'))
        else:
            color = QColor(tc('text_light'))

        pen = QPen(color, 2)
        painter.setPen(pen)

        for i in range(len(points) - 1):
            painter.drawLine(int(points[i][0]), int(points[i][1]),
                           int(points[i+1][0]), int(points[i+1][1]))

        painter.end()


# ── Stat Card ──────────────────────────────────────────────────────────

def apply_card_shadow(widget):
    """Apply a subtle drop shadow to a widget."""
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(12)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, 30))
    widget.setGraphicsEffect(shadow)


def make_stat_card(title: str, value: str, color: str = "", trend_data: list = None) -> QFrame:
    """Create a dashboard stat card widget."""
    if not color:
        color = tc('info')

    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background: {tc('card')};
            border: 1px solid {tc('border')};
            border-top: 3px solid {color};
            border-radius: 8px;
            padding: 16px;
        }}
    """)
    apply_card_shadow(card)

    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 12, 16, 12)
    lay.setSpacing(4)

    lbl_title = QLabel(title)
    lbl_title.setStyleSheet(f"color: {tc('text_light')}; font-size: {FONT_SIZES['sm']}px; font-weight: 600; background: transparent; border: none;")
    lay.addWidget(lbl_title)

    lbl_value = QLabel(str(value))
    lbl_value.setStyleSheet(f"color: {color}; font-size: {FONT_SIZES['hero']}px; font-weight: 800; background: transparent; border: none;")
    lay.addWidget(lbl_value)

    if trend_data and len(trend_data) >= 2:
        sparkline = SparklineWidget()
        sparkline.setStyleSheet("background: transparent; border: none;")
        sparkline.set_data(trend_data)
        lay.addWidget(sparkline)

    return card


# ── Confirm Dialog ─────────────────────────────────────────────────────

def set_table_empty_state(table: QTableWidget, message: str = "No records found"):
    """Show a message when table has no rows."""
    if table.rowCount() == 0:
        table.setRowCount(1)
        table.setRowHeight(0, 56)
        item = QTableWidgetItem(message)
        item.setFlags(Qt.NoItemFlags)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QColor(tc('text_light')))
        item.setFont(QFont("Segoe UI", 15))
        table.setItem(0, 0, item)
        table.setSpan(0, 0, 1, table.columnCount())


def setup_table(table: QTableWidget):
    """Apply consistent polish to any QTableWidget."""
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setDefaultSectionSize(40)


def make_status_badge(text: str, variant: str = "info") -> QLabel:
    """Return a small colored pill label suitable for embedding in table cells."""
    c = DARK_COLORS if _is_dark() else COLORS
    combos = {
        "success": (c["success_light"], c["success"]),
        "warning": (c["warning_light"], c["warning"]),
        "danger": (c["danger_light"], c["danger"]),
        "info": (c["info_light"], c["info"]),
    }
    bg, fg = combos.get(variant, combos["info"])
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(f"""
        background: {bg}; color: {fg};
        border-radius: {RADIUS['pill']}px;
        padding: 3px 12px;
        font-size: {FONT_SIZES['xs']}px;
        font-weight: 700;
    """)
    return lbl


def confirm_action(parent, title: str, message: str) -> bool:
    """Show a Yes/No confirmation dialog."""
    result = QMessageBox.question(parent, title, message,
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return result == QMessageBox.Yes


def make_page_header(title: str, subtitle: str = "") -> QFrame:
    """Create a consistent page header with title and optional subtitle."""
    header = QFrame()
    header.setStyleSheet(f"""
        QFrame {{
            background: transparent;
            border: none;
            padding: 0;
        }}
    """)
    lay = QVBoxLayout(header)
    lay.setContentsMargins(0, 0, 0, 8)
    lay.setSpacing(4)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(f"""
        color: {tc('text')};
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 22px;
        font-weight: 700;
        background: transparent;
        border: none;
    """)
    lay.addWidget(title_lbl)

    if subtitle:
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px;
            background: transparent;
            border: none;
        """)
        lay.addWidget(sub_lbl)

    return header


# ── Table Export Utilities ────────────────────────────────────────────

def export_table_to_csv(table_widget: QTableWidget, parent=None, default_name="export.csv"):
    """Export a QTableWidget's visible data to CSV."""
    import csv
    path, _ = QFileDialog.getSaveFileName(parent, "Export to CSV", default_name, "CSV Files (*.csv)")
    if not path:
        return
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Header row
        headers = []
        for col in range(table_widget.columnCount()):
            item = table_widget.horizontalHeaderItem(col)
            headers.append(item.text() if item else f"Column {col}")
        writer.writerow(headers)
        # Data rows
        for row in range(table_widget.rowCount()):
            row_data = []
            for col in range(table_widget.columnCount()):
                item = table_widget.item(row, col)
                row_data.append(item.text() if item else "")
            writer.writerow(row_data)
    QMessageBox.information(parent, "Export Complete", f"Exported {table_widget.rowCount()} rows to:\n{path}")


def export_table_to_excel(table_widget: QTableWidget, parent=None, default_name="export.xlsx"):
    """Export to Excel using openpyxl if available, otherwise fall back to CSV."""
    try:
        import openpyxl
        path, _ = QFileDialog.getSaveFileName(parent, "Export to Excel", default_name, "Excel Files (*.xlsx)")
        if not path:
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        # Header row
        headers = []
        for col in range(table_widget.columnCount()):
            item = table_widget.horizontalHeaderItem(col)
            headers.append(item.text() if item else f"Column {col}")
        ws.append(headers)
        # Data rows
        for row in range(table_widget.rowCount()):
            row_data = []
            for col in range(table_widget.columnCount()):
                item = table_widget.item(row, col)
                row_data.append(item.text() if item else "")
            ws.append(row_data)
        wb.save(path)
        QMessageBox.information(parent, "Export Complete", f"Exported {table_widget.rowCount()} rows to:\n{path}")
    except ImportError:
        export_table_to_csv(table_widget, parent, default_name.replace('.xlsx', '.csv'))


# ── Animated Page Stack ───────────────────────────────────────────────

class AnimatedStackedWidget(QStackedWidget):
    """QStackedWidget with a 200ms crossfade transition between pages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._animation_duration = 200

    def slide_to(self, index):
        """Crossfade to the page at *index*."""
        if index == self.currentIndex() or index < 0 or index >= self.count():
            self.setCurrentIndex(index)
            return

        current_widget = self.currentWidget()
        next_widget = self.widget(index)

        if current_widget is None or next_widget is None:
            self.setCurrentIndex(index)
            return

        # Set up opacity effects
        current_effect = QGraphicsOpacityEffect(current_widget)
        current_widget.setGraphicsEffect(current_effect)

        next_effect = QGraphicsOpacityEffect(next_widget)
        next_widget.setGraphicsEffect(next_effect)
        next_effect.setOpacity(0.0)

        # Show next widget on top
        self.setCurrentIndex(index)

        # Animate fade in on the new page
        fade_in = QPropertyAnimation(next_effect, b"opacity")
        fade_in.setDuration(self._animation_duration)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InOutQuad)

        def _cleanup():
            # Remove effects to avoid rendering overhead
            try:
                current_widget.setGraphicsEffect(None)
                next_widget.setGraphicsEffect(None)
            except RuntimeError:
                pass  # widget may have been deleted

        fade_in.finished.connect(_cleanup)
        fade_in.start()
        # Keep a reference so it doesn't get garbage collected
        self._running_anim = fade_in
