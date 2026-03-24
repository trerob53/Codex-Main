"""Loading overlay widget for pages that take time to refresh."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
from src.config import tc


class LoadingOverlay(QWidget):
    """Semi-transparent overlay that shows 'Loading...' over a parent widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet(f"""
            background: rgba(243, 244, 246, 0.85);
        """)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)

        self.label = QLabel("Loading...")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(f"""
            color: {tc('text')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 16px;
            font-weight: 600;
            background: transparent;
        """)
        lay.addWidget(self.label)
        self.hide()

    def show_loading(self, message="Loading..."):
        """Show the overlay with a message."""
        self.label.setText(message)
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()

    def hide_loading(self):
        """Hide the overlay."""
        self.hide()

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)
