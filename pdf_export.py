"""
Cerasus Hub — PDF Export Utility
Uses PySide6's QPrinter/QPainter for zero-dependency PDF generation.
"""

from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import Qt, QMarginsF, QRectF
from PySide6.QtGui import QPainter, QFont, QColor, QPen
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtGui import QPageLayout

import os
from datetime import datetime

from src.config import REPORTS_DIR, ensure_directories


class PDFDocument:
    """Simple PDF document builder using QPrinter."""

    def __init__(self, filename="report.pdf", title="Cerasus Hub Report", orientation="portrait"):
        ensure_directories()
        self.filepath = os.path.join(REPORTS_DIR, filename)
        self.title = title
        self.printer = QPrinter(QPrinter.HighResolution)
        self.printer.setOutputFormat(QPrinter.PdfFormat)
        self.printer.setOutputFileName(self.filepath)
        if orientation == "landscape":
            self.printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        self.printer.setPageMargins(QMarginsF(50, 50, 50, 50))

        self.painter = None
        self.y = 0
        self.page_height = 0
        self.page_width = 0
        self.page_num = 1

    def begin(self):
        self.painter = QPainter()
        self.painter.begin(self.printer)
        rect = self.printer.pageRect(QPrinter.Point)
        self.page_width = rect.width()
        self.page_height = rect.height()
        self.y = 0
        self._draw_header()

    def _draw_header(self):
        """Draw page header with title and date."""
        self.painter.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.painter.setPen(QPen(QColor("#0F1A2E")))
        self.painter.drawText(0, self.y + 20, self.title)
        self.y += 30

        self.painter.setFont(QFont("Segoe UI", 9))
        self.painter.setPen(QPen(QColor("#6B7280")))
        self.painter.drawText(
            0, self.y + 12,
            f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}  |  Page {self.page_num}",
        )
        self.y += 20

        # Divider line
        self.painter.setPen(QPen(QColor("#B91C1C"), 2))
        self.painter.drawLine(0, int(self.y), int(self.page_width), int(self.y))
        self.y += 15

    def _check_page_break(self, needed_height=40):
        if self.y + needed_height > self.page_height - 30:
            self.printer.newPage()
            self.page_num += 1
            self.y = 0
            self._draw_header()

    def add_section_title(self, text):
        self._check_page_break(30)
        self.painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.painter.setPen(QPen(QColor("#0F1A2E")))
        self.painter.drawText(0, int(self.y + 16), text)
        self.y += 24

    def add_text(self, text, bold=False, size=10, color="#111827"):
        self._check_page_break(20)
        weight = QFont.Bold if bold else QFont.Normal
        self.painter.setFont(QFont("Segoe UI", size, weight))
        self.painter.setPen(QPen(QColor(color)))
        self.painter.drawText(0, int(self.y + 14), text)
        self.y += 18

    def add_table(self, headers, rows, col_widths=None):
        """Draw a table with headers and data rows."""
        if not col_widths:
            col_widths = [self.page_width / len(headers)] * len(headers)

        row_height = 22

        # Header row
        self._check_page_break(row_height * 2)
        x = 0
        self.painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.painter.setPen(Qt.NoPen)
        self.painter.setBrush(QColor("#0F1A2E"))
        self.painter.drawRect(0, int(self.y), int(self.page_width), row_height)

        self.painter.setPen(QPen(QColor("white")))
        for i, header in enumerate(headers):
            self.painter.drawText(int(x + 4), int(self.y + 15), str(header))
            x += col_widths[i]
        self.y += row_height

        # Data rows
        self.painter.setFont(QFont("Segoe UI", 8))
        for row_idx, row in enumerate(rows):
            self._check_page_break(row_height)
            x = 0

            # Alternating row background
            if row_idx % 2 == 0:
                self.painter.setPen(Qt.NoPen)
                self.painter.setBrush(QColor("#F9FAFB"))
                self.painter.drawRect(0, int(self.y), int(self.page_width), row_height)

            self.painter.setPen(QPen(QColor("#111827")))
            for i, cell in enumerate(row):
                text = str(cell) if cell is not None else ""
                # Truncate if too long
                if len(text) > 30:
                    text = text[:27] + "..."
                self.painter.drawText(int(x + 4), int(self.y + 15), text)
                x += col_widths[i]
            self.y += row_height

        self.y += 10

    def add_kpi_row(self, kpis):
        """Draw KPI cards. kpis: [(label, value, color), ...]"""
        self._check_page_break(50)
        card_width = self.page_width / len(kpis)
        x = 0
        for label, value, color in kpis:
            # Card background
            self.painter.setPen(QPen(QColor("#D1D5DB")))
            self.painter.setBrush(QColor("white"))
            self.painter.drawRoundedRect(
                int(x + 2), int(self.y), int(card_width - 4), 45, 4, 4,
            )

            # Label
            self.painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            self.painter.setPen(QPen(QColor("#6B7280")))
            self.painter.drawText(int(x + 8), int(self.y + 14), label.upper())

            # Value
            self.painter.setFont(QFont("Segoe UI", 14, QFont.Bold))
            self.painter.setPen(QPen(QColor(color)))
            self.painter.drawText(int(x + 8), int(self.y + 36), str(value))

            x += card_width
        self.y += 55

    def add_spacing(self, px=10):
        self.y += px

    def finish(self):
        if self.painter:
            self.painter.end()
        return self.filepath


def print_widget(widget, title=""):
    """Print any QWidget via the system print dialog.

    Opens a QPrintDialog so the user can choose a printer, then renders
    the widget onto the printed page.  Works for any page visible in the Hub.
    """
    from PySide6.QtPrintSupport import QPrintDialog

    printer = QPrinter(QPrinter.HighResolution)
    if title:
        printer.setDocName(title)

    dialog = QPrintDialog(printer, widget)
    dialog.setWindowTitle(f"Print — {title}" if title else "Print")
    if dialog.exec() != QPrintDialog.Accepted:
        return  # user cancelled

    painter = QPainter()
    if not painter.begin(printer):
        return

    # Scale the widget contents to fit the printable page area
    page_rect = printer.pageRect(QPrinter.DevicePixel)
    widget_size = widget.size()
    x_scale = page_rect.width() / widget_size.width()
    y_scale = page_rect.height() / widget_size.height()
    scale = min(x_scale, y_scale)
    painter.scale(scale, scale)

    widget.render(painter)
    painter.end()


def save_pdf_dialog(parent, default_name="report.pdf"):
    """Open save dialog and return chosen path, or None."""
    ensure_directories()
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export PDF",
        os.path.join(REPORTS_DIR, default_name),
        "PDF Files (*.pdf)",
    )
    return path
