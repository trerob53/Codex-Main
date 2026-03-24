"""Form validation helpers for consistent input validation across all modules."""

from PySide6.QtWidgets import QLineEdit, QComboBox, QMessageBox

def validate_required(fields: list, parent=None) -> bool:
    """Validate that all required fields have values.
    fields: list of (widget, field_name) tuples.
    Returns True if all valid, False if any empty. Highlights invalid fields red.
    """
    all_valid = True
    for widget, name in fields:
        value = ""
        if isinstance(widget, QLineEdit):
            value = widget.text().strip()
        elif isinstance(widget, QComboBox):
            value = widget.currentText().strip()

        if not value:
            widget.setStyleSheet(widget.styleSheet() + " border: 2px solid #C8102E;")
            all_valid = False
        else:
            # Remove red border if it was set
            style = widget.styleSheet()
            if "border: 2px solid #C8102E" in style:
                widget.setStyleSheet(style.replace("border: 2px solid #C8102E;", ""))

    if not all_valid and parent:
        QMessageBox.warning(parent, "Required Fields", "Please fill in all required fields (highlighted in red).")

    return all_valid


def validate_numeric(widget: QLineEdit, field_name: str, min_val=None, max_val=None, parent=None) -> bool:
    """Validate numeric input."""
    text = widget.text().strip()
    if not text:
        return True  # empty is OK, use validate_required for mandatory
    try:
        val = float(text)
        if min_val is not None and val < min_val:
            QMessageBox.warning(parent, "Invalid Value", f"{field_name} must be at least {min_val}.")
            return False
        if max_val is not None and val > max_val:
            QMessageBox.warning(parent, "Invalid Value", f"{field_name} must be at most {max_val}.")
            return False
        return True
    except ValueError:
        QMessageBox.warning(parent, "Invalid Value", f"{field_name} must be a number.")
        return False
