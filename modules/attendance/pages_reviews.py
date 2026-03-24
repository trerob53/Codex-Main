"""
Cerasus Hub -- Attendance Module: Employment Reviews Page
Table of employment reviews with edit/lock functionality.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QAbstractItemView, QGroupBox, QMessageBox,
    QDialog, QFormLayout, QDialogButtonBox, QDateEdit,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from src.config import COLORS, tc, _is_dark, btn_style, build_dialog_stylesheet
from src.shared_widgets import confirm_action
from src.modules.attendance import data_manager
from src.modules.attendance.policy_engine import calculate_active_points
from src import audit
from src.shared_data import get_officer


# ════════════════════════════════════════════════════════════════════════
# Review Edit Dialog
# ════════════════════════════════════════════════════════════════════════

class ReviewEditDialog(QDialog):
    """Dialog for editing an employment review."""

    def __init__(self, parent, review):
        super().__init__(parent)
        self.review = review
        self.setWindowTitle(f"Edit Review #{review.get('id', '')}")
        self.setMinimumWidth(500)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Info (read-only) -- resolve name from officer_id
        emp_id = self.review.get("employee_id", "")
        officer = get_officer(emp_id)
        emp_display = officer.get("name", emp_id) if officer else emp_id
        emp_label = QLabel(emp_display)
        emp_label.setStyleSheet(f"color: {tc('text')}; font-weight: bold;")
        layout.addRow("Employee:", emp_label)

        pts_label = QLabel(str(self.review.get("points_at_trigger", 0)))
        layout.addRow("Points at Trigger:", pts_label)

        triggered_label = QLabel(self.review.get("triggered_date", ""))
        layout.addRow("Triggered Date:", triggered_label)

        # Editable fields
        self.reviewed_by = QLineEdit(self.review.get("reviewed_by", ""))
        layout.addRow("Reviewed By:", self.reviewed_by)

        self.review_date = QDateEdit()
        self.review_date.setCalendarPopup(True)
        self.review_date.setDisplayFormat("yyyy-MM-dd")
        existing_date = self.review.get("review_date", "")
        if existing_date:
            try:
                self.review_date.setDate(QDate.fromString(existing_date, "yyyy-MM-dd"))
            except Exception:
                self.review_date.setDate(QDate.currentDate())
        else:
            self.review_date.setDate(QDate.currentDate())
        layout.addRow("Review Date:", self.review_date)

        self.outcome_combo = QComboBox()
        self.outcome_combo.addItems(["", "Retraining", "Final Warning", "Termination"])
        existing_outcome = self.review.get("outcome", "")
        idx = self.outcome_combo.findText(existing_outcome)
        if idx >= 0:
            self.outcome_combo.setCurrentIndex(idx)
        layout.addRow("Outcome:", self.outcome_combo)

        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        self.notes_edit.setPlainText(self.review.get("reviewer_notes", ""))
        layout.addRow("Reviewer Notes:", self.notes_edit)

        self.supervisor_edit = QTextEdit()
        self.supervisor_edit.setMaximumHeight(80)
        self.supervisor_edit.setPlainText(self.review.get("supervisor_comments", ""))
        layout.addRow("Supervisor Comments:", self.supervisor_edit)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_fields(self):
        return {
            "reviewed_by": self.reviewed_by.text().strip(),
            "review_date": self.review_date.date().toString("yyyy-MM-dd"),
            "outcome": self.outcome_combo.currentText(),
            "reviewer_notes": self.notes_edit.toPlainText().strip(),
            "supervisor_comments": self.supervisor_edit.toPlainText().strip(),
            "review_status": "Completed" if self.outcome_combo.currentText() else "Pending",
        }


# ════════════════════════════════════════════════════════════════════════
# Reviews Page
# ════════════════════════════════════════════════════════════════════════

class ReviewsPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._reviews = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(12)

        # Header
        hdr_row = QHBoxLayout()
        title = QLabel("Employment Reviews")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()

        # Officer name search
        hdr_row.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Officer name...")
        self.search_edit.setFixedWidth(180)
        self.search_edit.textChanged.connect(self._on_filter_changed)
        hdr_row.addWidget(self.search_edit)

        # Status filter
        hdr_row.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Pending", "Completed"])
        self.status_filter.setFixedWidth(150)
        self.status_filter.currentIndexChanged.connect(self._on_filter_changed)
        hdr_row.addWidget(self.status_filter)

        layout.addLayout(hdr_row)

        # Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Officer", "Triggered Date", "Points", "Status", "Outcome", "Locked"
        ])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']}; color: white;
                font-weight: 600; font-size: 14px; padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._on_row_double_click)
        layout.addWidget(self.table)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_profile = QPushButton("View Profile")
        self.btn_profile.setStyleSheet(btn_style(COLORS['primary']))
        self.btn_profile.clicked.connect(self._view_officer_profile)
        btn_row.addWidget(self.btn_profile)

        self.btn_edit = QPushButton("Edit Review")
        self.btn_edit.setStyleSheet(btn_style(COLORS['info']))
        self.btn_edit.clicked.connect(self._edit_review)
        btn_row.addWidget(self.btn_edit)

        self.btn_complete = QPushButton("Complete Review")
        self.btn_complete.setStyleSheet(btn_style(COLORS['success']))
        self.btn_complete.clicked.connect(self._complete_review)
        btn_row.addWidget(self.btn_complete)

        self.btn_lock = QPushButton("Lock Review")
        self.btn_lock.setStyleSheet(btn_style(COLORS['accent'], hover_bg=COLORS['accent_hover']))
        self.btn_lock.clicked.connect(self._lock_review)
        btn_row.addWidget(self.btn_lock)

        self.btn_schedule = QPushButton("Schedule Review (8+ pts)")
        self.btn_schedule.setStyleSheet(btn_style(COLORS['warning']))
        self.btn_schedule.clicked.connect(self._schedule_reviews)
        btn_row.addWidget(self.btn_schedule)

        layout.addLayout(btn_row)

    def refresh(self):
        self._load_reviews()

    def _on_filter_changed(self):
        self._load_reviews()

    def _load_reviews(self):
        status_filter = self.status_filter.currentText()
        name_search = self.search_edit.text().strip().lower()
        reviews = data_manager.get_all_reviews()

        if status_filter and status_filter != "All":
            reviews = [r for r in reviews if r.get("review_status", "") == status_filter]

        # Apply officer name search filter
        if name_search:
            filtered = []
            for r in reviews:
                officer_name = self._get_officer_name(r.get("employee_id", "")).lower()
                if name_search in officer_name:
                    filtered.append(r)
            reviews = filtered

        # Apply site-based access control
        role = self.app_state.get("role", "")
        assigned_sites = self.app_state.get("assigned_sites", [])
        if assigned_sites and role != "admin":
            filtered = []
            for r in reviews:
                emp_id = r.get("employee_id", "")
                if emp_id:
                    off = data_manager.get_officer(emp_id)
                    if off and off.get("site", "") in assigned_sites:
                        filtered.append(r)
            reviews = filtered

        self._reviews = reviews
        self.table.setRowCount(len(reviews))

        for i, rev in enumerate(reviews):
            # Officer name
            officer_name = self._get_officer_name(rev.get("employee_id", ""))
            name_item = QTableWidgetItem(officer_name)
            name_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(i, 0, name_item)

            # Triggered date
            self.table.setItem(i, 1, QTableWidgetItem(rev.get("triggered_date", "")))

            # Points
            pts_item = QTableWidgetItem(str(rev.get("points_at_trigger", 0)))
            pts_item.setTextAlignment(Qt.AlignCenter)
            pts = float(rev.get("points_at_trigger", 0))
            if pts >= 10:
                pts_item.setForeground(QColor(COLORS["danger"]))
            elif pts >= 8:
                pts_item.setForeground(QColor("#9333EA"))
            pts_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(i, 2, pts_item)

            # Status
            status = rev.get("review_status", "Pending")
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "Pending":
                status_item.setForeground(QColor(COLORS["warning"]))
            elif status == "Completed":
                status_item.setForeground(QColor(COLORS["success"]))
            self.table.setItem(i, 3, status_item)

            # Outcome
            outcome = rev.get("outcome", "")
            outcome_item = QTableWidgetItem(outcome or "--")
            outcome_item.setTextAlignment(Qt.AlignCenter)
            if outcome == "Termination":
                outcome_item.setForeground(QColor(COLORS["danger"]))
                outcome_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(i, 4, outcome_item)

            # Locked
            locked = rev.get("locked", 0)
            lock_item = QTableWidgetItem("Locked" if locked else "Open")
            lock_item.setTextAlignment(Qt.AlignCenter)
            if locked:
                lock_item.setForeground(QColor(tc("text_light")))
            self.table.setItem(i, 5, lock_item)

            self.table.setRowHeight(i, 44)

    def _get_officer_name(self, employee_id: str) -> str:
        if not employee_id:
            return ""
        off = get_officer(employee_id)
        return off.get("name", employee_id) if off else employee_id

    def _get_selected_review(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if 0 <= row < len(self._reviews):
            return self._reviews[row]
        return None

    def _on_row_double_click(self, index):
        self._view_officer_profile()

    def _view_officer_profile(self):
        review = self._get_selected_review()
        if not review:
            return
        officer_id = review.get("employee_id", "")
        if officer_id:
            try:
                from src.officer_360 import show_officer_profile
                show_officer_profile(self, officer_id, self.app_state)
            except Exception:
                pass

    def _edit_review(self):
        review = self._get_selected_review()
        if not review:
            QMessageBox.information(self, "Select Review", "Please select a review to edit.")
            return

        if review.get("locked"):
            QMessageBox.warning(self, "Locked", "This review is locked and cannot be edited.")
            return

        dlg = ReviewEditDialog(self, review)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            data_manager.update_review(review["id"], fields)

            username = self.app_state.get("username", "")
            audit.log_event(
                "attendance", "review_updated", username,
                details=f"Updated review #{review['id']}",
                table_name="ats_employment_reviews", record_id=str(review["id"]),
                action="update", employee_id=review.get("employee_id", ""),
            )
            self._load_reviews()

    def _schedule_reviews(self):
        """Create new pending reviews for all officers at 8+ active points
        who don't already have a pending review."""
        from datetime import datetime, timezone

        officers = data_manager.get_active_officers()
        existing_reviews = data_manager.get_all_reviews()
        # Set of employee_ids that already have a pending review
        pending_ids = {
            r.get("employee_id", "")
            for r in existing_reviews
            if r.get("review_status", "") == "Pending"
        }

        scheduled = 0
        for off in officers:
            oid = off.get("officer_id", "") or off.get("employee_id", "")
            if not oid or oid in pending_ids:
                continue

            infractions = data_manager.get_infractions_for_employee(oid)
            active_pts = calculate_active_points(infractions)
            if active_pts >= 8:
                data_manager.create_review({
                    "employee_id": oid,
                    "triggered_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "points_at_trigger": active_pts,
                    "review_status": "Pending",
                })
                scheduled += 1

        username = self.app_state.get("username", "")
        audit.log_event(
            "attendance", "reviews_scheduled", username,
            details=f"Scheduled {scheduled} new review(s) for officers at 8+ points.",
        )

        if scheduled > 0:
            QMessageBox.information(
                self, "Reviews Scheduled",
                f"Created {scheduled} new pending review(s) for officers at 8+ points.",
            )
        else:
            QMessageBox.information(
                self, "No New Reviews",
                "All officers at 8+ points already have pending reviews.",
            )
        self._load_reviews()

    def _complete_review(self):
        """Mark the selected review as completed with outcome notes."""
        review = self._get_selected_review()
        if not review:
            QMessageBox.information(self, "Select Review", "Please select a review to complete.")
            return

        if review.get("locked"):
            QMessageBox.warning(self, "Locked", "This review is locked and cannot be modified.")
            return

        if review.get("review_status") == "Completed":
            QMessageBox.information(self, "Already Completed", "This review is already completed.")
            return

        dlg = ReviewEditDialog(self, review)
        if dlg.exec() == QDialog.Accepted:
            fields = dlg.get_fields()
            # Force status to Completed
            fields["review_status"] = "Completed"
            if not fields.get("outcome"):
                QMessageBox.warning(self, "Outcome Required",
                                    "Please select an outcome before completing the review.")
                return

            data_manager.update_review(review["id"], fields)

            username = self.app_state.get("username", "")
            audit.log_event(
                "attendance", "review_completed", username,
                details=f"Completed review #{review['id']} with outcome: {fields['outcome']}",
                table_name="ats_employment_reviews", record_id=str(review["id"]),
                action="complete", employee_id=review.get("employee_id", ""),
            )
            self._load_reviews()

    def _lock_review(self):
        review = self._get_selected_review()
        if not review:
            QMessageBox.information(self, "Select Review", "Please select a review to lock.")
            return

        if review.get("locked"):
            QMessageBox.warning(self, "Already Locked", "This review is already locked.")
            return

        if not review.get("outcome"):
            QMessageBox.warning(self, "No Outcome", "Please set an outcome before locking the review.")
            return

        if not confirm_action(self, "Lock Review",
                              "Lock this review? It cannot be edited after locking."):
            return

        data_manager.lock_review(review["id"])

        username = self.app_state.get("username", "")
        audit.log_event(
            "attendance", "review_locked", username,
            details=f"Locked review #{review['id']}",
            table_name="ats_employment_reviews", record_id=str(review["id"]),
            action="lock", employee_id=review.get("employee_id", ""),
        )
        self._load_reviews()
