"""
Cerasus Hub -- Notification UI Components
Bell button with badge, notification popup dialog for ModuleShellWidget.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog,
)
from PySide6.QtCore import Qt, QTimer

from src.config import (
    COLORS, DARK_COLORS, tc, _is_dark, btn_style, build_dialog_stylesheet,
)


def build_bell_row(parent_widget, sidebar_colors):
    """Build the bell button row with badge for the sidebar.

    Returns (bell_row_layout, bell_btn, bell_badge, bell_label).
    """
    c = sidebar_colors

    bell_row = QHBoxLayout()
    bell_row.setContentsMargins(0, 0, 0, 0)
    bell_row.setSpacing(0)

    bell_btn = QPushButton()
    bell_btn.setFixedSize(40, 32)
    bell_btn.setCursor(Qt.PointingHandCursor)
    bell_btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 18px;
            color: {c['sidebar_text']};
            border: none;
            padding: 0;
            text-align: center;
        }}
        QPushButton:hover {{ color: white; }}
    """)
    bell_btn.setText("\U0001F514")  # bell emoji
    bell_row.addWidget(bell_btn)

    # Badge label (red circle with count)
    bell_badge = QLabel("0")
    bell_badge.setFixedSize(20, 20)
    bell_badge.setAlignment(Qt.AlignCenter)
    bell_badge.setStyleSheet(f"""
        background: {COLORS['accent']};
        color: white;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 10px; font-weight: 700;
        border-radius: 10px;
    """)
    bell_badge.hide()
    bell_row.addWidget(bell_badge)

    bell_label = QLabel("ALERTS")
    bell_label.setStyleSheet(f"""
        color: {c['sidebar_text']};
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 11px; font-weight: 500;
        letter-spacing: 1px;
        background: transparent;
        padding-left: 2px;
    """)
    bell_row.addWidget(bell_label)
    bell_row.addStretch()

    return bell_row, bell_btn, bell_badge, bell_label


def refresh_notifications(widget):
    """Fetch notifications from all modules and update the bell badge on widget.

    Widget must have _bell_btn, _bell_badge, _bell_label, _cached_notifications attrs.
    """
    try:
        from src.notifications import get_all_notifications
        widget._cached_notifications = get_all_notifications()
    except Exception:
        widget._cached_notifications = []

    count = len(widget._cached_notifications)
    has_critical = any(
        n.get("severity") == "critical" for n in widget._cached_notifications
    )

    if count > 0:
        widget._bell_badge.setText(str(count) if count < 100 else "99+")
        widget._bell_badge.show()
        widget._bell_label.setText(f"ALERTS ({count})")
        if has_critical:
            widget._bell_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    font-size: 18px;
                    color: {COLORS['accent']};
                    border: none; padding: 0;
                    text-align: center;
                }}
                QPushButton:hover {{ color: {COLORS['accent_hover']}; }}
            """)
        else:
            dark = _is_dark()
            c = DARK_COLORS if dark else COLORS
            widget._bell_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    font-size: 18px;
                    color: {c['sidebar_text']};
                    border: none; padding: 0;
                    text-align: center;
                }}
                QPushButton:hover {{ color: white; }}
            """)
    else:
        widget._bell_badge.hide()
        widget._bell_label.setText("ALERTS")


def show_notifications_popup(parent_widget):
    """Open a popup dialog showing all notifications grouped by severity."""
    refresh_notifications(parent_widget)
    notifs = parent_widget._cached_notifications

    dlg = QDialog(parent_widget)
    dlg.setWindowTitle("Notifications")
    dlg.setMinimumSize(420, 360)
    dlg.resize(480, 520)
    dlg.setStyleSheet(build_dialog_stylesheet(_is_dark()))

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(12)

    title_lbl = QLabel(f"Notifications ({len(notifs)})")
    title_lbl.setStyleSheet(f"""
        color: {tc('text')};
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 18px; font-weight: 700;
        letter-spacing: 1px; background: transparent;
    """)
    lay.addWidget(title_lbl)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setStyleSheet(f"QScrollArea {{ background: {tc('bg')}; border: none; }}")

    cw = QWidget()
    cw.setStyleSheet(f"background: {tc('bg')};")
    clay = QVBoxLayout(cw)
    clay.setContentsMargins(0, 0, 0, 0)
    clay.setSpacing(6)

    sev_colors = {
        "critical": COLORS["accent"],
        "warning": COLORS["warning"],
        "info": COLORS["info"] if not _is_dark() else DARK_COLORS["info"],
    }
    sev_bg = {
        "critical": COLORS["danger_light"] if not _is_dark() else DARK_COLORS["danger_light"],
        "warning": COLORS["warning_light"] if not _is_dark() else DARK_COLORS["warning_light"],
        "info": COLORS["info_light"] if not _is_dark() else DARK_COLORS["info_light"],
    }
    sev_order = ["critical", "warning", "info"]
    sev_labels = {"critical": "CRITICAL", "warning": "WARNINGS", "info": "INFORMATION"}

    grouped = {}
    for n in notifs:
        grouped.setdefault(n.get("severity", "info"), []).append(n)

    if not notifs:
        el = QLabel("No active notifications")
        el.setAlignment(Qt.AlignCenter)
        el.setStyleSheet(f"""
            color: {tc('text_light')};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px; padding: 40px 0; background: transparent;
        """)
        clay.addWidget(el)
    else:
        for sev in sev_order:
            items = grouped.get(sev, [])
            if not items:
                continue
            bar_c = sev_colors.get(sev, COLORS["info"])
            bg_c = sev_bg.get(sev, tc("card"))

            sec = QLabel(f"  {sev_labels.get(sev, sev.upper())} ({len(items)})")
            sec.setStyleSheet(f"""
                color: {bar_c};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px; font-weight: 700;
                letter-spacing: 2px; padding: 8px 0 2px 0;
                background: transparent;
            """)
            clay.addWidget(sec)

            for n in items:
                card = QFrame()
                card.setCursor(Qt.PointingHandCursor)
                card.setStyleSheet(f"""
                    QFrame {{
                        background: {tc('card')};
                        border: 1px solid {tc('border')};
                        border-left: 4px solid {bar_c};
                        border-radius: 4px;
                        padding: 6px 10px;
                    }}
                    QFrame:hover {{ background: {bg_c}; }}
                """)
                cvl = QVBoxLayout(card)
                cvl.setContentsMargins(6, 4, 6, 4)
                cvl.setSpacing(2)

                mod_lbl = QLabel(n.get("module", "").upper())
                mod_lbl.setStyleSheet(f"""
                    color: {tc('text_light')};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 10px; font-weight: 600;
                    letter-spacing: 2px; background: transparent;
                """)
                cvl.addWidget(mod_lbl)

                msg_lbl = QLabel(n.get("message", ""))
                msg_lbl.setWordWrap(True)
                msg_lbl.setStyleSheet(f"""
                    color: {tc('text')};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 13px; font-weight: 600;
                    background: transparent;
                """)
                cvl.addWidget(msg_lbl)

                det = n.get("action_data", {}).get("detail", "")
                if det:
                    det_lbl = QLabel(det)
                    det_lbl.setWordWrap(True)
                    det_lbl.setStyleSheet(f"""
                        color: {tc('text_light')};
                        font-family: 'Segoe UI', Arial, sans-serif;
                        font-size: 11px; background: transparent;
                    """)
                    cvl.addWidget(det_lbl)

                clay.addWidget(card)

    clay.addStretch()
    scroll.setWidget(cw)
    lay.addWidget(scroll)

    cb = QPushButton("Close")
    cb.setCursor(Qt.PointingHandCursor)
    cb.setFixedHeight(36)
    cb.setStyleSheet(btn_style(tc('primary_light')))
    cb.clicked.connect(dlg.accept)
    lay.addWidget(cb)

    dlg.exec()
