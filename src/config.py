"""
Cerasus Hub — Configuration
Paths, constants, theme colors, and style helpers shared across all modules.
"""

import os
import sys


def get_app_root():
    """Application root: folder containing .exe (frozen) or project root (source)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_NAME = "Cerasus Hub"
APP_VERSION = "1.0"

# ── Paths ──────────────────────────────────────────────────────────────
ROOT_DIR = get_app_root()
DATA_DIR = os.path.join(ROOT_DIR, "data")
LOGS_DIR = os.path.join(ROOT_DIR, "logs")
REPORTS_DIR = os.path.join(ROOT_DIR, "reports")
LABELS_DIR = os.path.join(ROOT_DIR, "labels")

BACKUP_DIR = os.path.join(DATA_DIR, "backups")
DOCS_DIR = os.path.join(ROOT_DIR, "documents")

DB_FILE = os.path.join(DATA_DIR, "cerasus_hub.db")
LOCK_FILE = os.path.join(DATA_DIR, "edit.lock")

# ── Lock settings ──────────────────────────────────────────────────────
STALE_LOCK_THRESHOLD_MINUTES = 30

# ── Auto-refresh interval (ms) for read-only users ────────────────────
READ_ONLY_REFRESH_MS = 5000

# ── Roles ──────────────────────────────────────────────────────────────
ROLE_ADMIN = "admin"
ROLE_DIRECTOR = "director"
ROLE_STANDARD = "standard"
ROLE_VIEWER = "viewer"

# ── UI Theme colors (Cerasus brand — matched to cerasus.us) ───────────
COLORS = {
    "primary": "#1A1A2E",
    "primary_light": "#252540",
    "primary_mid": "#2E2E4A",
    "accent": "#C8102E",
    "accent_hover": "#A80D25",
    "accent_light": "#FDE8EB",
    "rose": "#C37474",
    "bg": "#F3F4F6",
    "card": "#FFFFFF",
    "text": "#1F2937",
    "text_light": "#6B7280",
    "success": "#059669",
    "success_light": "#D1FAE5",
    "warning": "#D97706",
    "warning_light": "#FEF3C7",
    "danger": "#C8102E",
    "danger_light": "#FDE8EB",
    "info": "#374151",
    "info_light": "#E5E7EB",
    "border": "#E5E7EB",
    "sidebar_text": "#9CA3AF",
    "sidebar_hover": "rgba(255, 255, 255, 0.08)",
    "sidebar_active": "#C8102E",
    "hover": "#F0F1F4",
    "table_selected": "#D6E4FF",
}

DARK_COLORS = {
    "primary": "#C37474",
    "primary_dark": "#1A1A2E",
    "primary_light": "#252540",
    "primary_mid": "#2E2E4A",
    "accent": "#E8384F",
    "accent_hover": "#C8102E",
    "accent_light": "#3D1C22",
    "rose": "#C37474",
    "bg": "#16162A",
    "card": "#1E1E36",
    "text": "#E5E7EB",
    "text_light": "#9CA3AF",
    "success": "#40C790",
    "success_light": "#1A3D2E",
    "warning": "#F0A030",
    "warning_light": "#3D3020",
    "danger": "#E8384F",
    "danger_light": "#3D1C22",
    "info": "#9CA3AF",
    "info_light": "#252540",
    "border": "#2E2E4A",
    "sidebar_text": "#9CA3AF",
    "sidebar_hover": "rgba(255, 255, 255, 0.08)",
    "sidebar_active": "#E8384F",
    "hover": "#2A2A42",
    "table_selected": "#1E3A5F",
}

# ── Design Tokens ─────────────────────────────────────────────────────
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
FONT_SIZES = {"xs": 11, "sm": 12, "md": 14, "lg": 16, "xl": 20, "xxl": 24, "hero": 32}
RADIUS = {"sm": 4, "md": 6, "lg": 8, "xl": 12, "pill": 9999}

# ── Settings cache (in-memory, backed by SQLite settings table) ───────
_settings_cache = {}


def get_theme_colors(dark=False):
    return DARK_COLORS if dark else COLORS


def _is_dark():
    return _settings_cache.get("dark_mode", False)


def tc(key):
    return get_theme_colors(_is_dark())[key]


def set_dark_mode(enabled: bool):
    _settings_cache["dark_mode"] = enabled


# ── Settings persistence helpers (backed by SQLite settings table) ────

def load_all_settings() -> dict:
    """Read every row from the SQLite ``settings`` table into *_settings_cache*
    and return a copy of the cache dict.

    Safe to call before any DB exists -- returns the current cache on error.
    """
    try:
        from src.database import get_conn
        conn = get_conn()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        for r in rows:
            key = r["key"] if isinstance(r, dict) else r[0]
            val = r["value"] if isinstance(r, dict) else r[1]
            # Coerce common boolean-ish strings
            if val in ("1", "true", "True"):
                _settings_cache[key] = True
            elif val in ("0", "false", "False"):
                _settings_cache[key] = False
            else:
                _settings_cache[key] = val
    except Exception:
        pass
    return dict(_settings_cache)


def save_setting(key: str, value) -> None:
    """Persist a single setting to the SQLite ``settings`` table and update
    the in-memory cache.

    *value* is stored as a string.  Booleans are saved as ``"1"``/``"0"``.
    """
    from datetime import datetime as _dt, timezone as _tz

    # Update in-memory cache immediately
    _settings_cache[key] = value

    str_val = str(value)
    if isinstance(value, bool):
        str_val = "1" if value else "0"

    try:
        from src.database import get_conn
        conn = get_conn()
        now = _dt.now(_tz.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, str_val, now),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_setting(key: str, default=None):
    """Return a cached setting value, or *default* if not found."""
    return _settings_cache.get(key, default)


def load_setting(key: str, default=""):
    """Convenience wrapper: ensure settings are loaded from SQLite, then return
    the value for *key* (or *default* if missing).

    Unlike :func:`get_setting` this will call :func:`load_all_settings` first
    when the cache is empty, so it is safe to call early in startup before the
    full cache has been populated.
    """
    if not _settings_cache:
        load_all_settings()
    return _settings_cache.get(key, default)


def btn_style(bg, fg="white", hover_bg=None, pill=False):
    if hover_bg is None:
        hover_bg = bg
    _disabled_bg = DARK_COLORS['border'] if _is_dark() else COLORS['border']
    _disabled_fg = DARK_COLORS['text_light'] if _is_dark() else COLORS['text_light']
    _radius = "9999px" if pill else "6px"
    return f"""
        QPushButton {{
            background: {bg}; color: {fg};
            border-radius: {_radius};
        }}
        QPushButton:hover {{
            background: {hover_bg};
        }}
        QPushButton:disabled {{
            background: {_disabled_bg}; color: {_disabled_fg};
        }}
    """


def card_style(padding=16):
    """Return a QFrame stylesheet matching the Control Tower card look."""
    c = get_theme_colors(_is_dark())
    return f"""
        QFrame {{
            background: {c['card']};
            border: 1px solid {c['border']};
            border-radius: 8px;
            padding: {padding}px;
        }}
    """


def badge_style(variant="info"):
    """Return a QLabel stylesheet for a colored badge (success/warning/danger/info)."""
    c = get_theme_colors(_is_dark())
    combos = {
        "success": (c["success_light"], c["success"]),
        "warning": (c["warning_light"], c["warning"]),
        "danger": (c["danger_light"], c["danger"]),
        "info": (c["info_light"], c["info"]),
    }
    bg, fg = combos.get(variant, combos["info"])
    return f"""
        QLabel {{
            background: {bg}; color: {fg};
            border-radius: 4px; padding: 3px 10px;
            font-size: 12px; font-weight: 600;
        }}
    """


def build_global_style(dark=False):
    c = get_theme_colors(dark)
    _text = c["text"]
    _bg = c["bg"]
    _card = c["card"]
    _card_alt = "#353545" if dark else "#F8F9FB"
    _border = c["border"]
    _input_bg = "#313244" if dark else "white"
    _info = c["info"]
    _info_light = c["info_light"]
    _primary = c["primary"] if not dark else c.get("primary_dark", c["primary_light"])
    _group_title = c["info"] if dark else COLORS["primary"]
    _accent = c["accent"]
    _hover = c["hover"]
    _selected = c["table_selected"]
    _r = RADIUS
    _sp = SPACING
    _fs = FONT_SIZES

    return f"""
QMainWindow, QWidget {{
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: {_fs['md']}px;
    color: {_text};
}}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit {{
    border: 1px solid {_border};
    border-radius: {_r['md']}px;
    padding: 8px 12px;
    background: {_input_bg};
    font-size: {_fs['md']}px;
    min-height: 38px;
    color: {_text};
}}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus {{
    border: 2px solid {_accent};
}}
QComboBox:focus {{
    border: 2px solid {_accent};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {_card};
    color: {_text};
    border: 1px solid {_border};
    selection-background-color: {_selected};
    selection-color: {_text};
    padding: 2px;
}}
QComboBox QAbstractItemView::item {{
    color: {_text};
    padding: 4px 8px;
    min-height: 24px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: {_selected};
    color: {_text};
}}
QPushButton {{
    border: none;
    border-radius: {_r['md']}px;
    padding: 9px 20px;
    font-size: {_fs['md']}px;
    font-weight: 600;
    min-height: 36px;
}}
QPushButton:focus {{
    outline: none;
    border: 2px solid {_accent};
}}
QPushButton:pressed {{
    opacity: 0.85;
}}
QTableWidget {{
    border: 1px solid {_border};
    border-radius: {_r['sm']}px;
    background: {_card};
    gridline-color: transparent;
    font-size: {_fs['md']}px;
    alternate-background-color: {_card_alt};
}}
QTableWidget::item {{
    padding: 8px 12px;
    color: {_text};
    min-height: 36px;
}}
QTableWidget::item:selected {{
    background: {_selected};
    color: {_text};
}}
QTableWidget::item:hover:!selected {{
    background: {_hover};
}}
QHeaderView::section {{
    background: {_primary};
    color: white;
    padding: 10px 12px;
    border: none;
    font-weight: 600;
    font-size: {_fs['md']}px;
    min-height: 40px;
}}
QScrollBar:vertical {{
    width: 8px;
    background: transparent;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {_border};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_info};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    height: 8px;
    background: transparent;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {_border};
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {_info};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QGroupBox {{
    font-weight: 700;
    font-size: {_fs['md']}px;
    color: {_group_title};
    border: 1px solid {_border};
    border-radius: {_r['lg']}px;
    margin-top: {_sp['md']}px;
    padding: {_sp['xxl']}px {_sp['lg']}px {_sp['lg']}px {_sp['lg']}px;
    background: {_card};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {_sp['lg']}px;
    padding: 0 8px;
}}
QScrollArea {{
    background: {_bg};
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: {_bg};
}}
QLabel {{
    color: {_text};
}}
QMessageBox {{
    background: {_card};
}}
QMessageBox QLabel {{
    color: {_text};
}}
QDialog {{
    background: {_bg};
}}
QToolTip {{
    background: {_card};
    color: {_text};
    border: 1px solid {_border};
    border-radius: {_r['sm']}px;
    padding: 6px 10px;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: {_fs['sm']}px;
}}
"""


def build_dialog_stylesheet(dark=False):
    c = get_theme_colors(dark)
    _card = c["card"]
    _bg = c["bg"]
    _text = c["text"]
    _border = c["border"]
    _accent = c["accent"]
    _r = RADIUS
    _fs = FONT_SIZES
    return f"""
    QDialog {{ background: {_bg}; }}
    QLabel {{ color: {_text}; font-size: {_fs['md']}px; }}
    QLineEdit, QTextEdit {{
        background: {_card}; border: 2px solid {_border};
        border-radius: {_r['md']}px; padding: 10px 12px;
        font-size: {_fs['md']}px; color: {_text};
        min-height: 40px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border-color: {_accent}; }}
    QComboBox {{
        background: {_card}; border: 2px solid {_border};
        border-radius: {_r['md']}px; padding: 10px 12px;
        font-size: {_fs['md']}px; color: {_text}; min-height: 40px;
    }}
    QComboBox:focus {{ border-color: {_accent}; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right;
        width: 30px; border-left: 1px solid {_border};
        border-top-right-radius: {_r['md']}px; border-bottom-right-radius: {_r['md']}px;
        background: {c['primary_light']};
    }}
    QComboBox::down-arrow {{
        image: none; border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid white; margin-right: 5px;
    }}
    QComboBox QAbstractItemView {{
        background: {_card}; color: {_text};
        border: 2px solid {c['primary_light']};
        border-radius: {_r['sm']}px; selection-background-color: {c['primary_light']};
        selection-color: white; padding: 4px;
        outline: 0px;
    }}
    QComboBox QAbstractItemView::item {{
        color: {_text};
        padding: 6px 12px;
        min-height: 28px;
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {c['primary_light']};
        color: white;
    }}
    QDateEdit {{
        background: {_card}; border: 2px solid {_border};
        border-radius: {_r['md']}px; padding: 10px 12px;
        font-size: {_fs['md']}px; color: {_text};
        min-height: 40px;
    }}
    QDateEdit:focus {{ border-color: {_accent}; }}
    QDateEdit::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right;
        width: 30px; border-left: 1px solid {_border};
        border-top-right-radius: {_r['md']}px; border-bottom-right-radius: {_r['md']}px;
        background: {c['primary_light']};
    }}
    QDateEdit::down-arrow {{
        image: none; border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid white; margin-right: 5px;
    }}
    QDialogButtonBox QPushButton {{
        background: {_accent}; color: white; border: none;
        border-radius: {_r['md']}px; padding: 12px 28px;
        font-size: {_fs['md']}px; font-weight: 600;
        min-height: 40px;
    }}
    QDialogButtonBox QPushButton:hover {{ background: {c.get('accent_hover', _accent)}; }}
    QDialogButtonBox QPushButton[text="Cancel"] {{
        background: {_border}; color: {_text};
    }}
    QDialogButtonBox QPushButton[text="Cancel"]:hover {{
        background: {c.get('info_light', _border)};
    }}
"""


def ensure_directories():
    for d in [DATA_DIR, LOGS_DIR, REPORTS_DIR, LABELS_DIR, BACKUP_DIR, DOCS_DIR]:
        os.makedirs(d, exist_ok=True)
