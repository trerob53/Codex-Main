"""
Cerasus Hub -- Custom Fields Engine
Allows admins to define arbitrary custom fields for officers and store per-officer values.
"""

import secrets
from datetime import datetime, timezone

from src.database import get_conn
from src.config import COLORS, tc, _is_dark, btn_style, build_dialog_stylesheet


def _gen_id() -> str:
    return secrets.token_hex(12)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Schema ────────────────────────────────────────────────────────────

def ensure_custom_fields_tables():
    """Create the custom_field_definitions and custom_field_values tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS custom_field_definitions (
            field_id TEXT PRIMARY KEY,
            field_name TEXT NOT NULL UNIQUE,
            field_type TEXT NOT NULL DEFAULT 'text',
            field_options TEXT DEFAULT '',
            required INTEGER DEFAULT 0,
            display_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS custom_field_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            officer_id TEXT NOT NULL,
            field_id TEXT NOT NULL,
            value TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(officer_id, field_id)
        );
    """)
    conn.commit()
    conn.close()


# ── Field Definition CRUD ─────────────────────────────────────────────

def create_field(name: str, field_type: str = "text", options: str = "", required: bool = False) -> str:
    """Create a new custom field definition. Returns field_id."""
    field_id = _gen_id()
    now = _now()
    conn = get_conn()
    # Determine next display_order
    row = conn.execute("SELECT MAX(display_order) as mx FROM custom_field_definitions").fetchone()
    next_order = (row["mx"] or 0) + 1 if row and row["mx"] is not None else 1
    conn.execute(
        """INSERT INTO custom_field_definitions
           (field_id, field_name, field_type, field_options, required, display_order, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (field_id, name, field_type, options, 1 if required else 0, next_order, now),
    )
    conn.commit()
    conn.close()
    return field_id


def get_all_fields() -> list[dict]:
    """Return all custom field definitions ordered by display_order."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM custom_field_definitions ORDER BY display_order, field_name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_field(field_id: str):
    """Delete a custom field definition and all associated values."""
    conn = get_conn()
    conn.execute("DELETE FROM custom_field_values WHERE field_id = ?", (field_id,))
    conn.execute("DELETE FROM custom_field_definitions WHERE field_id = ?", (field_id,))
    conn.commit()
    conn.close()


def update_field_order(field_id: str, new_order: int):
    """Update the display_order for a field."""
    conn = get_conn()
    conn.execute(
        "UPDATE custom_field_definitions SET display_order = ? WHERE field_id = ?",
        (new_order, field_id),
    )
    conn.commit()
    conn.close()


# ── Per-Officer Values ────────────────────────────────────────────────

def get_values_for_officer(officer_id: str) -> dict:
    """Return a dict of field_name -> value for an officer's custom fields."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT d.field_name, v.value
           FROM custom_field_values v
           JOIN custom_field_definitions d ON d.field_id = v.field_id
           WHERE v.officer_id = ?
           ORDER BY d.display_order""",
        (officer_id,),
    ).fetchall()
    conn.close()
    return {r["field_name"]: r["value"] for r in rows}


def set_value(officer_id: str, field_id: str, value: str):
    """Set or update a custom field value for an officer."""
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO custom_field_values (officer_id, field_id, value, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(officer_id, field_id) DO UPDATE SET value = ?, updated_at = ?""",
        (officer_id, field_id, value, now, value, now),
    )
    conn.commit()
    conn.close()


# ── Admin Dialog ──────────────────────────────────────────────────────

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QCheckBox,
    QFrame, QFormLayout, QDialogButtonBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class CustomFieldsAdminDialog(QDialog):
    """Admin dialog for managing custom field definitions."""

    FIELD_TYPES = ["Text", "Number", "Date", "Dropdown", "Checkbox"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Fields Manager")
        self.setMinimumSize(680, 520)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        ensure_custom_fields_tables()
        self._build()
        self._refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel("Custom Fields")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(title)

        subtitle = QLabel("Define additional fields that appear on every officer profile.")
        subtitle.setStyleSheet(f"color: {tc('text_light')}; font-size: 13px;")
        layout.addWidget(subtitle)

        # Add-field form
        form_frame = QFrame()
        form_frame.setStyleSheet(
            f"QFrame {{ background: {tc('card')}; border: 1px solid {tc('border')}; "
            f"border-radius: 8px; padding: 12px; }}"
        )
        form_lay = QHBoxLayout(form_frame)
        form_lay.setSpacing(8)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Field name...")
        self.name_input.setFixedWidth(180)
        form_lay.addWidget(self.name_input)

        self.type_combo = QComboBox()
        self.type_combo.addItems(self.FIELD_TYPES)
        self.type_combo.setFixedWidth(120)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        form_lay.addWidget(self.type_combo)

        self.options_input = QLineEdit()
        self.options_input.setPlaceholderText("Options (comma-separated, for dropdown)")
        self.options_input.setFixedWidth(200)
        self.options_input.setEnabled(False)
        form_lay.addWidget(self.options_input)

        self.required_cb = QCheckBox("Required")
        self.required_cb.setStyleSheet(f"color: {tc('text')};")
        form_lay.addWidget(self.required_cb)

        btn_add = QPushButton("+ Add Field")
        btn_add.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS.get('accent_hover', COLORS['accent'])))
        btn_add.clicked.connect(self._add_field)
        form_lay.addWidget(btn_add)

        layout.addWidget(form_frame)

        # Fields table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Field Name", "Type", "Options", "Required", "Order"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 13px; padding: 6px; border: none;
            }}
        """)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_up = QPushButton("Move Up")
        btn_up.setStyleSheet(btn_style(COLORS['info']))
        btn_up.clicked.connect(self._move_up)
        btn_row.addWidget(btn_up)

        btn_down = QPushButton("Move Down")
        btn_down.setStyleSheet(btn_style(COLORS['info']))
        btn_down.clicked.connect(self._move_down)
        btn_row.addWidget(btn_down)

        btn_delete = QPushButton("Delete Field")
        btn_delete.setStyleSheet(btn_style(COLORS['danger']))
        btn_delete.clicked.connect(self._delete_field)
        btn_row.addWidget(btn_delete)

        layout.addLayout(btn_row)

        # Close
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

    def _on_type_changed(self, text):
        self.options_input.setEnabled(text.lower() == "dropdown")

    def _refresh(self):
        self._fields = get_all_fields()
        self.table.setRowCount(len(self._fields))
        for i, f in enumerate(self._fields):
            self.table.setItem(i, 0, QTableWidgetItem(f.get("field_name", "")))
            self.table.setItem(i, 1, QTableWidgetItem(f.get("field_type", "text").capitalize()))
            self.table.setItem(i, 2, QTableWidgetItem(f.get("field_options", "")))
            req_text = "Yes" if f.get("required") else "No"
            req_item = QTableWidgetItem(req_text)
            req_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, req_item)
            order_item = QTableWidgetItem(str(f.get("display_order", 0)))
            order_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, order_item)

    def _add_field(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Field name is required.")
            return
        field_type = self.type_combo.currentText().lower()
        options = self.options_input.text().strip() if field_type == "dropdown" else ""
        required = self.required_cb.isChecked()
        try:
            create_field(name, field_type, options, required)
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Could not create field:\n{exc}")
            return
        self.name_input.clear()
        self.options_input.clear()
        self.required_cb.setChecked(False)
        self._refresh()

    def _get_selected_idx(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "No Selection", "Please select a field first.")
            return -1
        return rows[0].row()

    def _delete_field(self):
        idx = self._get_selected_idx()
        if idx < 0:
            return
        field = self._fields[idx]
        result = QMessageBox.question(
            self, "Delete Custom Field",
            f"Delete field '{field['field_name']}'?\n\nThis will remove the field and all stored values for every officer.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        delete_field(field["field_id"])
        self._refresh()

    def _move_up(self):
        idx = self._get_selected_idx()
        if idx <= 0:
            return
        self._swap_order(idx, idx - 1)

    def _move_down(self):
        idx = self._get_selected_idx()
        if idx < 0 or idx >= len(self._fields) - 1:
            return
        self._swap_order(idx, idx + 1)

    def _swap_order(self, idx_a, idx_b):
        fa = self._fields[idx_a]
        fb = self._fields[idx_b]
        order_a = fa.get("display_order", 0)
        order_b = fb.get("display_order", 0)
        update_field_order(fa["field_id"], order_b)
        update_field_order(fb["field_id"], order_a)
        self._refresh()
        # Reselect the moved row
        new_idx = idx_b
        self.table.selectRow(new_idx)
