"""Print helper for generating print-friendly views of tables and data."""

from PySide6.QtWidgets import QTableWidget, QDialog, QVBoxLayout, QPushButton, QTextBrowser
from PySide6.QtCore import Qt
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from src.config import tc, COLORS


def print_table(parent, title: str, table: QTableWidget):
    """Open a print dialog for a table widget's contents."""
    # Build HTML from table
    html = f"""
    <html><head><style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 11px; }}
        h2 {{ color: #1A1A2E; margin-bottom: 8px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th {{ background: #1A1A2E; color: white; padding: 8px 6px; text-align: left; font-size: 10px; }}
        td {{ border-bottom: 1px solid #E5E7EB; padding: 6px; font-size: 10px; }}
        tr:nth-child(even) {{ background: #F9FAFB; }}
    </style></head><body>
    <h2>{title}</h2>
    <table>
    <tr>
    """

    # Headers
    for col in range(table.columnCount()):
        header = table.horizontalHeaderItem(col)
        if header and not table.isColumnHidden(col):
            html += f"<th>{header.text()}</th>"
    html += "</tr>"

    # Rows
    for row in range(table.rowCount()):
        html += "<tr>"
        for col in range(table.columnCount()):
            if table.isColumnHidden(col):
                continue
            item = table.item(row, col)
            text = item.text() if item else ""
            html += f"<td>{text}</td>"
        html += "</tr>"

    html += "</table></body></html>"

    # Show print preview dialog
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Print: {title}")
    dlg.setMinimumSize(700, 500)
    lay = QVBoxLayout(dlg)

    browser = QTextBrowser()
    browser.setHtml(html)
    lay.addWidget(browser)

    btn_print = QPushButton("Print")
    btn_print.setStyleSheet(f"""
        QPushButton {{
            background: {COLORS['accent']}; color: white;
            border: none; border-radius: 4px;
            padding: 10px 24px; font-size: 14px; font-weight: 600;
        }}
    """)

    def do_print():
        printer = QPrinter(QPrinter.HighResolution)
        print_dlg = QPrintDialog(printer, dlg)
        if print_dlg.exec() == QPrintDialog.Accepted:
            browser.print_(printer)

    btn_print.clicked.connect(do_print)
    lay.addWidget(btn_print, alignment=Qt.AlignCenter)

    dlg.exec()
