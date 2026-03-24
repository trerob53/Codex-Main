"""
Cerasus Hub -- Training Module: Admin Pages
ManageCoursesPage (course CRUD, module/chapter editor, test builder) and ReportsPage.
"""

import csv
import io
import json
import os
import re

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QMessageBox, QFileDialog, QFormLayout,
    QGroupBox, QAbstractItemView, QDialog, QDialogButtonBox,
    QScrollArea, QSpinBox, QDoubleSpinBox, QCheckBox, QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from src.config import (
    COLORS, ROLE_ADMIN, tc, _is_dark, btn_style,
    build_dialog_stylesheet, REPORTS_DIR, ensure_directories,
)
from src.shared_widgets import make_stat_card, BarChartWidget, confirm_action
from src.modules.training import data_manager
from src import audit


# ════════════════════════════════════════════════════════════════════════
# Course Dialog
# ════════════════════════════════════════════════════════════════════════

class CourseDialog(QDialog):
    """Dialog for adding or editing a course."""

    def __init__(self, parent=None, course=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Course" if course else "New Course")
        self.setMinimumWidth(520)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.course = course
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Course title")
        layout.addRow("Title:", self.title_input)

        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("Course description")
        self.desc_input.setMaximumHeight(100)
        layout.addRow("Description:", self.desc_input)

        self.category_input = QComboBox()
        self.category_input.addItems(data_manager.get_course_categories())
        layout.addRow("Category:", self.category_input)

        self.status_input = QComboBox()
        self.status_input.addItems(["Published", "Draft", "Archived"])
        layout.addRow("Status:", self.status_input)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        if self.course:
            self.title_input.setText(self.course.get("title", ""))
            self.desc_input.setPlainText(self.course.get("description", ""))
            idx = self.category_input.findText(self.course.get("category", ""))
            if idx >= 0:
                self.category_input.setCurrentIndex(idx)
            sidx = self.status_input.findText(self.course.get("status", ""))
            if sidx >= 0:
                self.status_input.setCurrentIndex(sidx)

    def get_data(self) -> dict:
        return {
            "title": self.title_input.text().strip(),
            "description": self.desc_input.toPlainText().strip(),
            "category": self.category_input.currentText(),
            "status": self.status_input.currentText(),
        }


# ════════════════════════════════════════════════════════════════════════
# Module Dialog
# ════════════════════════════════════════════════════════════════════════

class ModuleDialog(QDialog):
    def __init__(self, parent=None, module=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Module" if module else "New Module")
        self.setMinimumWidth(400)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.module = module
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Module title")
        layout.addRow("Title:", self.title_input)

        self.order_input = QSpinBox()
        self.order_input.setRange(0, 999)
        layout.addRow("Sort Order:", self.order_input)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        if self.module:
            self.title_input.setText(self.module.get("title", ""))
            self.order_input.setValue(self.module.get("sort_order", 0))

    def get_data(self) -> dict:
        return {
            "title": self.title_input.text().strip(),
            "sort_order": self.order_input.value(),
        }


# ════════════════════════════════════════════════════════════════════════
# Chapter Dialog
# ════════════════════════════════════════════════════════════════════════

class ChapterDialog(QDialog):
    def __init__(self, parent=None, chapter=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Chapter" if chapter else "New Chapter")
        self.setMinimumWidth(560)
        self.setMinimumHeight(400)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.chapter = chapter
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Chapter title")
        layout.addRow("Title:", self.title_input)

        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText(
            "Enter concise chapter content. Avoid web copy-paste \u2014 "
            "write clear, direct training material."
        )
        self.content_input.setMinimumHeight(180)
        layout.addRow("Content:", self.content_input)

        self.btn_cleanup = QPushButton("Clean Up Content")
        self.btn_cleanup.setCursor(Qt.PointingHandCursor)
        self.btn_cleanup.setToolTip(
            "Strip web artifacts, condense verbose phrasing, and reformat for readability"
        )
        self.btn_cleanup.clicked.connect(self._clean_up_content)
        layout.addRow("", self.btn_cleanup)

        self.order_input = QSpinBox()
        self.order_input.setRange(0, 999)
        layout.addRow("Sort Order:", self.order_input)

        self.has_test_check = QCheckBox("This chapter has a test")
        layout.addRow("Test:", self.has_test_check)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        if self.chapter:
            self.title_input.setText(self.chapter.get("title", ""))
            self.content_input.setPlainText(self.chapter.get("content", ""))
            self.order_input.setValue(self.chapter.get("sort_order", 0))
            self.has_test_check.setChecked(bool(self.chapter.get("has_test", 0)))

    # ── Content clean-up (same logic as display-side formatter) ────
    @staticmethod
    def _condense_text(text: str) -> str:
        """Strip web artifacts and condense verbose phrasing (plain-text in, plain-text out)."""
        # Web artifact removal
        web_patterns = [
            r'(?i)\b(click here to|subscribe to|share this|read more|learn more at|'
            r'visit our website|copyright\s*©.*|all rights reserved).*',
            r'(?m)^[\w\s]+(?:\s*[>»/]\s*[\w\s]+){2,}\s*$',
            r'https?://[^\s<>"\']+',
        ]
        for pat in web_patterns:
            text = re.sub(pat, '', text)

        # Filler phrase removal
        filler_phrases = [
            r'\bit is important to note that\b',
            r'\bas previously mentioned\b',
            r'\bit should be noted that\b',
            r'\bas a matter of fact\b',
            r'\bthe fact of the matter is\b',
            r'\bin light of the fact that\b',
            r'\bit goes without saying\b',
        ]
        for fp in filler_phrases:
            text = re.sub(fp, '', text, flags=re.IGNORECASE)

        # Wordy construction replacements
        replacements = [
            (r'\bin order to\b',           'to'),
            (r'\bdue to the fact that\b',  'because'),
            (r'\bin the event that\b',     'if'),
            (r'\bat this point in time\b', 'now'),
            (r'\bfor the purpose of\b',    'to'),
            (r'\bwith regard to\b',        'regarding'),
            (r'\bprior to\b',             'before'),
            (r'\bsubsequent to\b',        'after'),
            (r'\bin accordance with\b',   'per'),
            (r'\bin conjunction with\b',  'with'),
        ]
        for pat, repl in replacements:
            text = re.sub(pat, repl, text, flags=re.IGNORECASE)

        # Collapse extra whitespace
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _clean_up_content(self):
        raw = self.content_input.toPlainText()
        if not raw.strip():
            return
        cleaned = self._condense_text(raw)
        self.content_input.setPlainText(cleaned)

    def get_data(self) -> dict:
        return {
            "title": self.title_input.text().strip(),
            "content": self.content_input.toPlainText().strip(),
            "sort_order": self.order_input.value(),
            "has_test": 1 if self.has_test_check.isChecked() else 0,
        }


# ════════════════════════════════════════════════════════════════════════
# Test Builder Dialog
# ════════════════════════════════════════════════════════════════════════

class TestBuilderDialog(QDialog):
    """Dialog for building/editing a test with multiple-choice questions."""

    def __init__(self, parent=None, test=None, chapter_id="", course_id=""):
        super().__init__(parent)
        self.setWindowTitle("Edit Test" if test else "Build Test")
        self.setMinimumWidth(640)
        self.setMinimumHeight(500)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self.test = test
        self.chapter_id = chapter_id
        self.course_id = course_id
        self.questions = []
        if test:
            self.questions = list(test.get("questions", []))
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title and passing score
        form = QFormLayout()
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Test title")
        form.addRow("Title:", self.title_input)

        self.passing_input = QDoubleSpinBox()
        self.passing_input.setRange(0, 100)
        self.passing_input.setValue(70.0)
        self.passing_input.setSuffix("%")
        form.addRow("Passing Score:", self.passing_input)
        layout.addLayout(form)

        # Questions area
        q_label = QLabel("Questions:")
        q_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        q_label.setStyleSheet(f"color: {tc('text')};")
        layout.addWidget(q_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("border: none;")
        self.q_container = QWidget()
        self.q_layout = QVBoxLayout(self.q_container)
        self.q_layout.setSpacing(12)
        scroll.setWidget(self.q_container)
        layout.addWidget(scroll)

        # Add question button
        btn_add = QPushButton("+ Add Question")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.setStyleSheet(btn_style(tc("info"), "white"))
        btn_add.setFixedHeight(36)
        btn_add.clicked.connect(self._add_question)
        layout.addWidget(btn_add)

        # Dialog buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # Populate
        if self.test:
            self.title_input.setText(self.test.get("title", ""))
            self.passing_input.setValue(self.test.get("passing_score", 70.0))

        self.question_widgets = []
        for q in self.questions:
            self._add_question_widget(q)

        if not self.questions:
            self._add_question()

    def _add_question(self):
        self._add_question_widget({"question": "", "options": ["", "", "", ""], "correct": 0})

    def _add_question_widget(self, q_data: dict):
        idx = len(self.question_widgets)
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {tc('card')}; border: 1px solid {tc('border')};
                border-radius: 6px; padding: 10px;
            }}
        """)
        f_lay = QVBoxLayout(frame)
        f_lay.setSpacing(8)

        header_row = QHBoxLayout()
        q_num = QLabel(f"Question {idx + 1}")
        q_num.setFont(QFont("Segoe UI", 12, QFont.Bold))
        q_num.setStyleSheet(f"color: {tc('text')}; border: none;")
        header_row.addWidget(q_num)
        header_row.addStretch()

        btn_remove = QPushButton("Remove")
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.setStyleSheet(f"""
            QPushButton {{
                background: {tc('danger')}; color: white; border: none;
                border-radius: 4px; padding: 4px 12px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {tc('accent_hover')}; }}
        """)
        btn_remove.clicked.connect(lambda checked, fr=frame, i=idx: self._remove_question(fr, i))
        header_row.addWidget(btn_remove)
        f_lay.addLayout(header_row)

        q_input = QLineEdit()
        q_input.setPlaceholderText("Enter question text")
        q_input.setText(q_data.get("question", ""))
        q_input.setStyleSheet(f"border: 1px solid {tc('border')}; border-radius: 4px; padding: 6px;")
        f_lay.addWidget(q_input)

        options = q_data.get("options", ["", "", "", ""])
        correct = q_data.get("correct", 0)
        opt_inputs = []
        correct_combo = QComboBox()

        for oi, opt_text in enumerate(options):
            opt_row = QHBoxLayout()
            opt_label = QLabel(f"Option {chr(65 + oi)}:")
            opt_label.setStyleSheet(f"color: {tc('text')}; font-size: 12px; border: none;")
            opt_label.setFixedWidth(75)
            opt_row.addWidget(opt_label)
            opt_input = QLineEdit()
            opt_input.setText(opt_text)
            opt_input.setPlaceholderText(f"Option {chr(65 + oi)}")
            opt_input.setStyleSheet(f"border: 1px solid {tc('border')}; border-radius: 4px; padding: 5px;")
            opt_row.addWidget(opt_input)
            opt_inputs.append(opt_input)
            f_lay.addLayout(opt_row)
            correct_combo.addItem(f"Option {chr(65 + oi)}")

        correct_row = QHBoxLayout()
        correct_label = QLabel("Correct Answer:")
        correct_label.setStyleSheet(f"color: {tc('success')}; font-weight: 600; font-size: 12px; border: none;")
        correct_row.addWidget(correct_label)
        correct_combo.setCurrentIndex(correct)
        correct_row.addWidget(correct_combo)
        correct_row.addStretch()
        f_lay.addLayout(correct_row)

        self.q_layout.addWidget(frame)
        self.question_widgets.append({
            "frame": frame,
            "q_input": q_input,
            "opt_inputs": opt_inputs,
            "correct_combo": correct_combo,
        })

    def _remove_question(self, frame: QFrame, idx: int):
        # Find by frame reference, not index (index can be stale after earlier removals)
        to_remove = None
        for i, qw in enumerate(self.question_widgets):
            if qw["frame"] is frame:
                to_remove = i
                break
        if to_remove is not None:
            self.question_widgets.pop(to_remove)
        frame.deleteLater()
        # Re-number remaining questions
        for i, qw in enumerate(self.question_widgets):
            labels = qw["frame"].findChildren(QLabel)
            if labels:
                labels[0].setText(f"Question {i + 1}")

    def _on_accept(self):
        self.questions = []
        for qw in self.question_widgets:
            if not qw["frame"].parent():
                continue
            q_text = qw["q_input"].text().strip()
            if not q_text:
                continue
            options = [inp.text().strip() for inp in qw["opt_inputs"]]
            correct = qw["correct_combo"].currentIndex()
            self.questions.append({
                "question": q_text,
                "options": options,
                "correct": correct,
            })
        self.accept()

    def get_data(self) -> dict:
        return {
            "title": self.title_input.text().strip(),
            "passing_score": self.passing_input.value(),
            "questions": self.questions,
            "chapter_id": self.chapter_id,
            "course_id": self.course_id,
        }


# ════════════════════════════════════════════════════════════════════════
# Enroll Officers Dialog
# ════════════════════════════════════════════════════════════════════════

class EnrollOfficersDialog(QDialog):
    """Dialog for enrolling multiple officers in a course."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enroll Officers in Course")
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)
        self.setStyleSheet(build_dialog_stylesheet(_is_dark()))
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Course selector
        course_row = QHBoxLayout()
        course_lbl = QLabel("Course:")
        course_lbl.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 14px;")
        course_lbl.setFixedWidth(80)
        course_row.addWidget(course_lbl)
        self.course_combo = QComboBox()
        self.course_combo.setFixedHeight(34)
        courses = data_manager.get_all_courses()
        self._courses = [c for c in courses if c.get("status") == "Published"]
        for c in self._courses:
            self.course_combo.addItem(c.get("title", ""), c.get("course_id", ""))
        course_row.addWidget(self.course_combo)
        layout.addLayout(course_row)

        # Officer multi-select list
        officer_lbl = QLabel("Select Officers:")
        officer_lbl.setStyleSheet(f"color: {tc('text')}; font-weight: 600; font-size: 14px;")
        layout.addWidget(officer_lbl)

        # Search filter
        self.officer_search = QLineEdit()
        self.officer_search.setPlaceholderText("Search officers...")
        self.officer_search.setFixedHeight(32)
        self.officer_search.textChanged.connect(self._filter_officers)
        layout.addWidget(self.officer_search)

        self.officer_list = QListWidget()
        self.officer_list.setSelectionMode(QListWidget.MultiSelection)
        self.officer_list.setStyleSheet(f"""
            QListWidget {{
                background: {tc('bg')}; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 4px;
                font-size: 13px;
            }}
            QListWidget::item {{ padding: 6px 8px; }}
            QListWidget::item:selected {{
                background: {tc('info')}; color: white;
            }}
        """)
        self._officers = data_manager.get_active_officers()
        for o in self._officers:
            item = QListWidgetItem(f"{o.get('name', '')}  ({o.get('site', '')})")
            item.setData(Qt.UserRole, o.get("officer_id", ""))
            self.officer_list.addItem(item)
        layout.addWidget(self.officer_list)

        # Select all / none
        sel_row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.setFixedHeight(30)
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.setStyleSheet(btn_style(tc("info"), "white"))
        btn_all.clicked.connect(self.officer_list.selectAll)
        sel_row.addWidget(btn_all)
        btn_none = QPushButton("Clear Selection")
        btn_none.setFixedHeight(30)
        btn_none.setCursor(Qt.PointingHandCursor)
        btn_none.setStyleSheet(btn_style(tc("border"), tc("text")))
        btn_none.clicked.connect(self.officer_list.clearSelection)
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Enroll")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _filter_officers(self, text: str):
        text = text.strip().lower()
        for i in range(self.officer_list.count()):
            item = self.officer_list.item(i)
            item.setHidden(text not in item.text().lower())

    def get_data(self) -> dict:
        course_id = self.course_combo.currentData()
        officer_ids = []
        for item in self.officer_list.selectedItems():
            oid = item.data(Qt.UserRole)
            if oid:
                officer_ids.append(oid)
        return {"course_id": course_id, "officer_ids": officer_ids}


# ════════════════════════════════════════════════════════════════════════
# Manage Courses Page
# ════════════════════════════════════════════════════════════════════════

class ManageCoursesPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._selected_course_id = None
        self._build()

    def _get_username(self) -> str:
        return self.app_state.get("username", "admin")

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Manage Courses")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; border: none; background: transparent;")
        header_row.addWidget(title)
        header_row.addStretch()

        btn_categories = QPushButton("Manage Categories")
        btn_categories.setCursor(Qt.PointingHandCursor)
        btn_categories.setFixedHeight(38)
        btn_categories.setStyleSheet(btn_style(tc("info"), "white"))
        btn_categories.clicked.connect(self._manage_categories)
        header_row.addWidget(btn_categories)

        btn_enroll = QPushButton("Enroll Officers")
        btn_enroll.setCursor(Qt.PointingHandCursor)
        btn_enroll.setFixedHeight(38)
        btn_enroll.setStyleSheet(btn_style(tc("success"), "white"))
        btn_enroll.clicked.connect(self._enroll_officers)
        header_row.addWidget(btn_enroll)

        btn_add = QPushButton("+ New Course")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.setFixedHeight(38)
        btn_add.setStyleSheet(btn_style(tc("accent"), "white", tc("accent_hover")))
        btn_add.clicked.connect(self._add_course)
        header_row.addWidget(btn_add)
        layout.addLayout(header_row)

        # Courses table
        self.course_table = QTableWidget(0, 5)
        self.course_table.setHorizontalHeaderLabels([
            "Title", "Category", "Status", "Modules", "Actions"
        ])
        hdr = self.course_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            hdr.setSectionResizeMode(c, QHeaderView.Fixed)
        self.course_table.setColumnWidth(1, 130)
        self.course_table.setColumnWidth(2, 100)
        self.course_table.setColumnWidth(3, 80)
        self.course_table.setColumnWidth(4, 220)
        hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 8px 10px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.course_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.course_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.course_table.verticalHeader().setVisible(False)
        self.course_table.setAlternatingRowColors(True)
        self.course_table.setShowGrid(False)
        layout.addWidget(self.course_table)

        # ── Course content editor (modules/chapters) ──
        self.editor_group = QGroupBox("Course Content Editor")
        self.editor_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        self.editor_group.setVisible(False)
        editor_lay = QVBoxLayout(self.editor_group)
        editor_lay.setSpacing(12)

        # Module section
        mod_header = QHBoxLayout()
        mod_lbl = QLabel("Modules")
        mod_lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
        mod_lbl.setStyleSheet(f"color: {tc('text')}; border: none;")
        mod_header.addWidget(mod_lbl)
        mod_header.addStretch()
        btn_add_mod = QPushButton("+ Add Module")
        btn_add_mod.setCursor(Qt.PointingHandCursor)
        btn_add_mod.setFixedHeight(32)
        btn_add_mod.setStyleSheet(btn_style(tc("info"), "white"))
        btn_add_mod.clicked.connect(self._add_module)
        mod_header.addWidget(btn_add_mod)
        editor_lay.addLayout(mod_header)

        self.modules_table = QTableWidget(0, 4)
        self.modules_table.setHorizontalHeaderLabels(["Title", "Order", "Chapters", "Actions"])
        m_hdr = self.modules_table.horizontalHeader()
        m_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in [1, 2, 3]:
            m_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
        self.modules_table.setColumnWidth(1, 70)
        self.modules_table.setColumnWidth(2, 80)
        self.modules_table.setColumnWidth(3, 260)
        m_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {tc('info')};
                color: white; font-weight: 600; font-size: 13px;
                padding: 6px; border: none;
            }}
        """)
        self.modules_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.modules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.modules_table.verticalHeader().setVisible(False)
        self.modules_table.setShowGrid(False)
        self.modules_table.setMaximumHeight(200)
        editor_lay.addWidget(self.modules_table)

        # Chapter section
        ch_header = QHBoxLayout()
        ch_lbl = QLabel("Chapters")
        ch_lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
        ch_lbl.setStyleSheet(f"color: {tc('text')}; border: none;")
        ch_header.addWidget(ch_lbl)
        ch_header.addStretch()
        editor_lay.addLayout(ch_header)

        self.chapters_table = QTableWidget(0, 5)
        self.chapters_table.setHorizontalHeaderLabels(["Module", "Title", "Order", "Has Test", "Actions"])
        c_hdr = self.chapters_table.horizontalHeader()
        c_hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        c_hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in [2, 3, 4]:
            c_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
        self.chapters_table.setColumnWidth(2, 70)
        self.chapters_table.setColumnWidth(3, 80)
        self.chapters_table.setColumnWidth(4, 280)
        c_hdr.setStyleSheet(m_hdr.styleSheet())
        self.chapters_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.chapters_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.chapters_table.verticalHeader().setVisible(False)
        self.chapters_table.setShowGrid(False)
        self.chapters_table.setMaximumHeight(300)
        editor_lay.addWidget(self.chapters_table)

        layout.addWidget(self.editor_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Category Management ─────────────────────────────────────────

    def _manage_categories(self):
        """Open a dialog to add/edit/delete course categories."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Manage Course Categories")
        dlg.setMinimumWidth(420)
        dlg.setMinimumHeight(400)
        dlg.setStyleSheet(build_dialog_stylesheet(_is_dark()))

        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        info_lbl = QLabel("Add, edit, or remove course categories used when creating courses.")
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f"color: {tc('text_light')}; font-size: 12px;")
        lay.addWidget(info_lbl)

        # Category list
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        cat_list = QListWidget()
        cat_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {tc('border')}; border-radius: 6px;
                padding: 4px; background: {tc('bg')};
            }}
            QListWidget::item {{
                padding: 6px 8px; font-size: 13px; color: {tc('text')};
            }}
            QListWidget::item:selected {{
                background: {tc('info')}; color: white;
            }}
        """)
        categories = data_manager.get_course_categories()
        for cat in categories:
            cat_list.addItem(cat)
        lay.addWidget(cat_list)

        # Add row
        add_row = QHBoxLayout()
        add_input = QLineEdit()
        add_input.setPlaceholderText("New category name")
        add_input.setStyleSheet(f"border: 1px solid {tc('border')}; border-radius: 4px; padding: 6px;")
        add_row.addWidget(add_input)

        btn_add_cat = QPushButton("Add")
        btn_add_cat.setCursor(Qt.PointingHandCursor)
        btn_add_cat.setFixedSize(70, 32)
        btn_add_cat.setStyleSheet(btn_style(tc("success"), "white"))

        def _add_cat():
            name = add_input.text().strip()
            if name and name not in [cat_list.item(i).text() for i in range(cat_list.count())]:
                cat_list.addItem(name)
                add_input.clear()

        btn_add_cat.clicked.connect(_add_cat)
        add_row.addWidget(btn_add_cat)
        lay.addLayout(add_row)

        # Edit / Delete buttons
        btn_row = QHBoxLayout()

        btn_edit_cat = QPushButton("Rename Selected")
        btn_edit_cat.setCursor(Qt.PointingHandCursor)
        btn_edit_cat.setFixedHeight(32)
        btn_edit_cat.setStyleSheet(btn_style(tc("info"), "white"))

        def _rename_cat():
            item = cat_list.currentItem()
            if not item:
                return
            from PySide6.QtWidgets import QInputDialog
            new_name, ok = QInputDialog.getText(dlg, "Rename Category", "New name:", text=item.text())
            if ok and new_name.strip():
                item.setText(new_name.strip())

        btn_edit_cat.clicked.connect(_rename_cat)
        btn_row.addWidget(btn_edit_cat)

        btn_del_cat = QPushButton("Delete Selected")
        btn_del_cat.setCursor(Qt.PointingHandCursor)
        btn_del_cat.setFixedHeight(32)
        btn_del_cat.setStyleSheet(btn_style(tc("danger"), "white"))

        def _delete_cat():
            row = cat_list.currentRow()
            if row >= 0:
                cat_list.takeItem(row)

        btn_del_cat.clicked.connect(_delete_cat)
        btn_row.addWidget(btn_del_cat)
        lay.addLayout(btn_row)

        # Dialog buttons
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() == QDialog.Accepted:
            new_cats = [cat_list.item(i).text() for i in range(cat_list.count())]
            if new_cats:
                data_manager.save_course_categories(new_cats)
                QMessageBox.information(self, "Saved", "Course categories updated.")

    # ── Course CRUD ──────────────────────────────────────────────────

    def _enroll_officers(self):
        dlg = EnrollOfficersDialog(self)
        if dlg.exec() == QDialog.Accepted:
            result = dlg.get_data()
            course_id = result["course_id"]
            officer_ids = result["officer_ids"]
            if not course_id or not officer_ids:
                QMessageBox.warning(self, "Incomplete", "Select a course and at least one officer.")
                return
            enrolled = 0
            for oid in officer_ids:
                if data_manager.enroll_officer(oid, course_id):
                    enrolled += 1

            course = data_manager.get_course(course_id)
            course_title = course.get("title", "") if course else course_id
            audit.log_event("training", "officers_enrolled", self._get_username(),
                            f"Enrolled {enrolled} officer(s) in: {course_title}")
            QMessageBox.information(
                self, "Enrollment Complete",
                f"Successfully enrolled {enrolled} officer(s) in \"{course_title}\".\n"
                f"({len(officer_ids) - enrolled} were already enrolled.)"
            )
            self.refresh()

    def _add_course(self):
        dlg = CourseDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["title"]:
                QMessageBox.warning(self, "Missing Title", "Course title is required.")
                return
            data["created_by"] = self._get_username()
            cid = data_manager.create_course(data)
            audit.log_event("training", "course_created", self._get_username(),
                             f"Course: {data['title']}", record_id=cid)
            self.refresh()

    def _edit_course(self, course_id: str):
        course = data_manager.get_course(course_id)
        if not course:
            return
        dlg = CourseDialog(self, course)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            data_manager.update_course(course_id, data)
            audit.log_event("training", "course_updated", self._get_username(),
                             f"Course: {data['title']}", record_id=course_id)
            self.refresh()

    def _delete_course(self, course_id: str):
        course = data_manager.get_course(course_id)
        if not course:
            return
        if not confirm_action(self, "Delete Course",
                              f"Delete '{course.get('title', '')}' and all its content? This cannot be undone."):
            return
        data_manager.delete_course(course_id)
        audit.log_event("training", "course_deleted", self._get_username(),
                         f"Course: {course.get('title', '')}", record_id=course_id)
        if self._selected_course_id == course_id:
            self._selected_course_id = None
            self.editor_group.setVisible(False)
        self.refresh()

    def _manage_content(self, course_id: str):
        self._selected_course_id = course_id
        self.editor_group.setVisible(True)
        course = data_manager.get_course(course_id)
        if course:
            self.editor_group.setTitle(f"Course Content: {course.get('title', '')}")
        self._refresh_editor()

    # ── Module CRUD ──────────────────────────────────────────────────

    def _add_module(self):
        if not self._selected_course_id:
            return
        dlg = ModuleDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["title"]:
                return
            data["course_id"] = self._selected_course_id
            data_manager.create_module(data)
            audit.log_event("training", "module_created", self._get_username(),
                             f"Module: {data['title']}")
            self._refresh_editor()

    def _edit_module(self, module_id: str):
        modules = data_manager.get_modules_for_course(self._selected_course_id or "")
        mod = next((m for m in modules if m["module_id"] == module_id), None)
        if not mod:
            return
        dlg = ModuleDialog(self, mod)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            data_manager.update_module(module_id, data)
            self._refresh_editor()

    def _delete_module(self, module_id: str):
        if not confirm_action(self, "Delete Module",
                              "Delete this module and all its chapters?"):
            return
        data_manager.delete_module(module_id)
        audit.log_event("training", "module_deleted", self._get_username(), record_id=module_id)
        self._refresh_editor()

    def _add_chapter_to_module(self, module_id: str):
        if not self._selected_course_id:
            return
        dlg = ChapterDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["title"]:
                return
            data["module_id"] = module_id
            data["course_id"] = self._selected_course_id
            chid = data_manager.create_chapter(data)
            audit.log_event("training", "chapter_created", self._get_username(),
                             f"Chapter: {data['title']}")

            # If has_test, open test builder
            if data.get("has_test"):
                self._build_test(chid)

            self._refresh_editor()

    # ── Chapter CRUD ─────────────────────────────────────────────────

    def _edit_chapter(self, chapter_id: str):
        chapters = data_manager.get_chapters_for_course(self._selected_course_id or "")
        ch = next((c for c in chapters if c["chapter_id"] == chapter_id), None)
        if not ch:
            return
        dlg = ChapterDialog(self, ch)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            data_manager.update_chapter(chapter_id, data)
            self._refresh_editor()

    def _delete_chapter(self, chapter_id: str):
        if not confirm_action(self, "Delete Chapter", "Delete this chapter?"):
            return
        data_manager.delete_chapter(chapter_id)
        self._refresh_editor()

    # ── Test Builder ─────────────────────────────────────────────────

    def _build_test(self, chapter_id: str):
        if not self._selected_course_id:
            return
        existing = data_manager.get_test_for_chapter(chapter_id)
        dlg = TestBuilderDialog(
            self, test=existing,
            chapter_id=chapter_id,
            course_id=self._selected_course_id,
        )
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            if existing:
                data_manager.update_test(existing["test_id"], data)
                audit.log_event("training", "test_updated", self._get_username(),
                                 f"Test: {data.get('title', '')}")
            else:
                data_manager.create_test(data)
                audit.log_event("training", "test_created", self._get_username(),
                                 f"Test: {data.get('title', '')}")
            self._refresh_editor()

    # ── Refresh ──────────────────────────────────────────────────────

    def _refresh_editor(self):
        """Refresh the module/chapter editor tables."""
        if not self._selected_course_id:
            return

        course_id = self._selected_course_id
        modules = data_manager.get_modules_for_course(course_id)
        chapters = data_manager.get_chapters_for_course(course_id)

        # Module table
        self.modules_table.setRowCount(len(modules))
        for i, mod in enumerate(modules):
            mid = mod["module_id"]
            self.modules_table.setItem(i, 0, QTableWidgetItem(mod.get("title", "")))
            order_item = QTableWidgetItem(str(mod.get("sort_order", 0)))
            order_item.setTextAlignment(Qt.AlignCenter)
            self.modules_table.setItem(i, 1, order_item)

            ch_count = sum(1 for c in chapters if c.get("module_id") == mid)
            ch_item = QTableWidgetItem(str(ch_count))
            ch_item.setTextAlignment(Qt.AlignCenter)
            self.modules_table.setItem(i, 2, ch_item)

            # Action buttons
            actions = QWidget()
            a_lay = QHBoxLayout(actions)
            a_lay.setContentsMargins(4, 2, 4, 2)
            a_lay.setSpacing(6)

            btn_edit = QPushButton("Edit")
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.setFixedSize(60, 30)
            btn_edit.setStyleSheet(btn_style(tc("info"), "white"))
            btn_edit.clicked.connect(lambda checked, m=mid: self._edit_module(m))
            a_lay.addWidget(btn_edit)

            btn_add_ch = QPushButton("+ Chapter")
            btn_add_ch.setCursor(Qt.PointingHandCursor)
            btn_add_ch.setFixedSize(100, 30)
            btn_add_ch.setStyleSheet(btn_style(tc("success"), "white"))
            btn_add_ch.clicked.connect(lambda checked, m=mid: self._add_chapter_to_module(m))
            a_lay.addWidget(btn_add_ch)

            btn_del = QPushButton("Delete")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedSize(68, 30)
            btn_del.setStyleSheet(btn_style(tc("danger"), "white"))
            btn_del.clicked.connect(lambda checked, m=mid: self._delete_module(m))
            a_lay.addWidget(btn_del)

            self.modules_table.setCellWidget(i, 3, actions)
            self.modules_table.setRowHeight(i, 40)

        # Chapter table
        # Build module name map
        mod_map = {m["module_id"]: m.get("title", "") for m in modules}

        self.chapters_table.setRowCount(len(chapters))
        for i, ch in enumerate(chapters):
            chid = ch["chapter_id"]
            self.chapters_table.setItem(i, 0, QTableWidgetItem(mod_map.get(ch.get("module_id", ""), "")))
            self.chapters_table.setItem(i, 1, QTableWidgetItem(ch.get("title", "")))

            order_item = QTableWidgetItem(str(ch.get("sort_order", 0)))
            order_item.setTextAlignment(Qt.AlignCenter)
            self.chapters_table.setItem(i, 2, order_item)

            has_test = ch.get("has_test", 0)
            test_item = QTableWidgetItem("Yes" if has_test else "No")
            test_item.setTextAlignment(Qt.AlignCenter)
            if has_test:
                test_item.setForeground(QColor(tc("success")))
            self.chapters_table.setItem(i, 3, test_item)

            # Actions
            actions = QWidget()
            a_lay = QHBoxLayout(actions)
            a_lay.setContentsMargins(4, 2, 4, 2)
            a_lay.setSpacing(6)

            btn_edit = QPushButton("Edit")
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.setFixedSize(60, 30)
            btn_edit.setStyleSheet(btn_style(tc("info"), "white"))
            btn_edit.clicked.connect(lambda checked, c=chid: self._edit_chapter(c))
            a_lay.addWidget(btn_edit)

            if has_test:
                btn_test = QPushButton("Edit Test")
                btn_test.setCursor(Qt.PointingHandCursor)
                btn_test.setFixedSize(90, 30)
                btn_test.setStyleSheet(btn_style(tc("warning"), "white"))
                btn_test.clicked.connect(lambda checked, c=chid: self._build_test(c))
                a_lay.addWidget(btn_test)

            btn_del = QPushButton("Delete")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedSize(68, 30)
            btn_del.setStyleSheet(btn_style(tc("danger"), "white"))
            btn_del.clicked.connect(lambda checked, c=chid: self._delete_chapter(c))
            a_lay.addWidget(btn_del)

            self.chapters_table.setCellWidget(i, 4, actions)
            self.chapters_table.setRowHeight(i, 40)

    def refresh(self):
        courses = data_manager.get_all_courses()
        self.course_table.setRowCount(len(courses))
        for i, c in enumerate(courses):
            cid = c["course_id"]
            self.course_table.setItem(i, 0, QTableWidgetItem(c.get("title", "")))

            cat_item = QTableWidgetItem(c.get("category", ""))
            cat_item.setTextAlignment(Qt.AlignCenter)
            self.course_table.setItem(i, 1, cat_item)

            status = c.get("status", "")
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_colors = {"Published": tc("success"), "Draft": tc("warning"), "Archived": tc("text_light")}
            status_item.setForeground(QColor(status_colors.get(status, tc("text"))))
            status_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.course_table.setItem(i, 2, status_item)

            modules = data_manager.get_modules_for_course(cid)
            mod_item = QTableWidgetItem(str(len(modules)))
            mod_item.setTextAlignment(Qt.AlignCenter)
            self.course_table.setItem(i, 3, mod_item)

            # Actions
            actions = QWidget()
            a_lay = QHBoxLayout(actions)
            a_lay.setContentsMargins(4, 2, 4, 2)
            a_lay.setSpacing(6)

            btn_edit = QPushButton("Edit")
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.setFixedSize(52, 30)
            btn_edit.setStyleSheet(btn_style(tc("info"), "white"))
            btn_edit.clicked.connect(lambda checked, c=cid: self._edit_course(c))
            a_lay.addWidget(btn_edit)

            btn_content = QPushButton("Content")
            btn_content.setCursor(Qt.PointingHandCursor)
            btn_content.setFixedSize(90, 30)
            btn_content.setStyleSheet(btn_style(tc("success"), "white"))
            btn_content.clicked.connect(lambda checked, c=cid: self._manage_content(c))
            a_lay.addWidget(btn_content)

            btn_del = QPushButton("Delete")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedSize(56, 30)
            btn_del.setStyleSheet(btn_style(tc("danger"), "white"))
            btn_del.clicked.connect(lambda checked, c=cid: self._delete_course(c))
            a_lay.addWidget(btn_del)

            self.course_table.setCellWidget(i, 4, actions)
            self.course_table.setRowHeight(i, 44)

        # Refresh editor if a course is selected
        if self._selected_course_id:
            self._refresh_editor()


# ════════════════════════════════════════════════════════════════════════
# Reports Page
# ════════════════════════════════════════════════════════════════════════

class ReportsPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app_state = app_state
        self._build()

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(20)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Training Reports")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color: {tc('text')}; border: none; background: transparent;")
        header_row.addWidget(title)
        header_row.addStretch()

        btn_export = QPushButton("Export Progress CSV")
        btn_export.setCursor(Qt.PointingHandCursor)
        btn_export.setFixedHeight(38)
        btn_export.setStyleSheet(btn_style(tc("info"), "white"))
        btn_export.clicked.connect(self._export_progress)
        header_row.addWidget(btn_export)
        layout.addLayout(header_row)

        # Completion by site
        site_group = QGroupBox("Training Completion by Site")
        site_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600; font-size: 15px; color: {tc('text')};
                border: 1px solid {tc('border')}; border-radius: 8px;
                margin-top: 8px; padding-top: 24px; background: {tc('card')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 6px;
            }}
        """)
        site_lay = QVBoxLayout(site_group)
        self.site_chart = BarChartWidget()
        site_lay.addWidget(self.site_chart)

        self.site_table = QTableWidget(0, 3)
        self.site_table.setHorizontalHeaderLabels(["Site", "Officers", "Avg Completion %"])
        s_hdr = self.site_table.horizontalHeader()
        s_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in [1, 2]:
            s_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
        self.site_table.setColumnWidth(1, 100)
        self.site_table.setColumnWidth(2, 140)
        s_hdr.setStyleSheet(f"""
            QHeaderView::section {{
                background: {COLORS['primary']};
                color: white; font-weight: 600; font-size: 14px;
                padding: 6px; border: none;
                border-right: 1px solid {COLORS['primary_light']};
            }}
        """)
        self.site_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.site_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.site_table.verticalHeader().setVisible(False)
        self.site_table.setShowGrid(False)
        self.site_table.setAlternatingRowColors(True)
        self.site_table.setMaximumHeight(280)
        site_lay.addWidget(self.site_table)
        layout.addWidget(site_group)

        # Officer progress table
        progress_group = QGroupBox("Officer Progress")
        progress_group.setStyleSheet(site_group.styleSheet())
        progress_lay = QVBoxLayout(progress_group)

        self.progress_table = QTableWidget(0, 7)
        self.progress_table.setHorizontalHeaderLabels([
            "Officer", "Site", "Course", "Chapters Done", "Total", "Completion %", "Certified"
        ])
        p_hdr = self.progress_table.horizontalHeader()
        p_hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        p_hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in [1, 3, 4, 5, 6]:
            p_hdr.setSectionResizeMode(c, QHeaderView.Fixed)
        self.progress_table.setColumnWidth(1, 120)
        self.progress_table.setColumnWidth(3, 100)
        self.progress_table.setColumnWidth(4, 70)
        self.progress_table.setColumnWidth(5, 110)
        self.progress_table.setColumnWidth(6, 80)
        p_hdr.setStyleSheet(s_hdr.styleSheet())
        self.progress_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.progress_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.progress_table.verticalHeader().setVisible(False)
        self.progress_table.setShowGrid(False)
        self.progress_table.setAlternatingRowColors(True)
        progress_lay.addWidget(self.progress_table)
        layout.addWidget(progress_group)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _export_progress(self):
        ensure_directories()
        report = data_manager.get_officer_progress_report()
        if not report:
            QMessageBox.information(self, "No Data", "No progress data to export.")
            return

        path = os.path.join(REPORTS_DIR, "training_progress.csv")
        try:
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=report[0].keys())
                writer.writeheader()
                writer.writerows(report)
            QMessageBox.information(self, "Exported", f"Report saved to:\n{path}")
            audit.log_event("training", "report_exported",
                             self.app_state.get("username", ""), f"Path: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def refresh(self):
        # Site completion chart
        site_data = data_manager.get_completion_by_site()
        chart_data = [(s["site"][:14], s["avg_completion"], tc("info")) for s in site_data[:10]]
        self.site_chart.set_data(chart_data)

        self.site_table.setRowCount(len(site_data))
        for i, s in enumerate(site_data):
            self.site_table.setItem(i, 0, QTableWidgetItem(s["site"]))
            off_item = QTableWidgetItem(str(s["officers"]))
            off_item.setTextAlignment(Qt.AlignCenter)
            self.site_table.setItem(i, 1, off_item)

            pct_item = QTableWidgetItem(f"{s['avg_completion']:.1f}%")
            pct_item.setTextAlignment(Qt.AlignCenter)
            pct_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            if s["avg_completion"] >= 80:
                pct_item.setForeground(QColor(tc("success")))
            elif s["avg_completion"] >= 50:
                pct_item.setForeground(QColor(tc("warning")))
            else:
                pct_item.setForeground(QColor(tc("danger")))
            self.site_table.setItem(i, 2, pct_item)

        # Officer progress
        progress = data_manager.get_officer_progress_report()
        self.progress_table.setRowCount(len(progress))
        for i, p in enumerate(progress):
            self.progress_table.setItem(i, 0, QTableWidgetItem(p.get("officer_name", "")))
            self.progress_table.setItem(i, 1, QTableWidgetItem(p.get("site", "")))
            self.progress_table.setItem(i, 2, QTableWidgetItem(p.get("course", "")))

            done_item = QTableWidgetItem(str(p.get("chapters_done", 0)))
            done_item.setTextAlignment(Qt.AlignCenter)
            self.progress_table.setItem(i, 3, done_item)

            total_item = QTableWidgetItem(str(p.get("chapters_total", 0)))
            total_item.setTextAlignment(Qt.AlignCenter)
            self.progress_table.setItem(i, 4, total_item)

            pct_item = QTableWidgetItem(f"{p.get('completion_pct', 0):.1f}%")
            pct_item.setTextAlignment(Qt.AlignCenter)
            pct = p.get("completion_pct", 0)
            if pct >= 100:
                pct_item.setForeground(QColor(tc("success")))
            elif pct > 0:
                pct_item.setForeground(QColor(tc("warning")))
            pct_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.progress_table.setItem(i, 5, pct_item)

            cert_item = QTableWidgetItem(p.get("certified", "No"))
            cert_item.setTextAlignment(Qt.AlignCenter)
            if p.get("certified") == "Yes":
                cert_item.setForeground(QColor(tc("success")))
                cert_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.progress_table.setItem(i, 6, cert_item)
