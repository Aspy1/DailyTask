"""Exam panel — card-style list with countdown highlights."""

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox,
    QMessageBox, QMenu, QScrollArea, QSizePolicy,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE


class _ExamCard(QWidget):
    """Card widget for one exam."""

    def __init__(self, exam: dict, days_left: int, parent=None):
        super().__init__(parent)
        self._exam = exam
        c = get_colors()

        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Card styling based on urgency
        if days_left < 0:
            bg = c["bg_surface"]
            accent_color = c["fg_disabled"]
        elif days_left == 0:
            bg = c["red"] + "12"
            accent_color = c["red"]
        elif days_left <= 3:
            bg = c["red"] + "08"
            accent_color = c["red"]
        elif days_left <= 7:
            bg = c["orange"] + "08"
            accent_color = c["orange"]
        else:
            bg = c["card_bg"]
            accent_color = c["accent"]

        self.setStyleSheet(f"""
            _ExamCard {{ background-color: {bg}; border-radius: 10px; }}
            _ExamCard:hover {{ background-color: {c['accent_bg']}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Left: countdown badge
        badge = QLabel()
        badge.setFixedSize(52, 52)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if days_left < 0:
            badge.setText("已过")
            badge.setStyleSheet(f"color: {c['fg_disabled']}; font-size: 11px; font-weight: 600; background: {c['bg_input']}; border-radius: 26px;")
        elif days_left == 0:
            badge.setText("今天")
            badge.setStyleSheet(f"color: #fff; font-size: 13px; font-weight: 700; background: {c['red']}; border-radius: 26px;")
        elif days_left <= 3:
            badge.setText(f"{days_left}天")
            badge.setStyleSheet(f"color: #fff; font-size: 13px; font-weight: 700; background: {c['red']}; border-radius: 26px;")
        elif days_left <= 7:
            badge.setText(f"{days_left}天")
            badge.setStyleSheet(f"color: #fff; font-size: 13px; font-weight: 700; background: {c['orange']}; border-radius: 26px;")
        else:
            badge.setText(f"{days_left}天")
            badge.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 13px; font-weight: 600; background: {c['bg_input']}; border-radius: 26px;")
        layout.addWidget(badge)

        # Center: info
        info = QVBoxLayout()
        info.setSpacing(4)

        name_lbl = QLabel(exam.get("course_name", ""))
        name_lbl.setStyleSheet(f"color: {c['fg_primary'] if days_left >= 0 else c['fg_disabled']}; font-size: 15px; font-weight: 600; border: none; background: transparent;")
        info.addWidget(name_lbl)

        date_lbl = QLabel(f"📅 {exam.get('exam_date', '')}")
        date_lbl.setStyleSheet(f"color: {accent_color}; font-size: 13px; border: none; background: transparent;")
        info.addWidget(date_lbl)

        extras = []
        if exam.get("scope"):
            extras.append(f"范围: {exam['scope']}")
        if exam.get("location"):
            extras.append(exam["location"])
        if exam.get("notes"):
            extras.append(exam["notes"])
        if extras:
            detail = QLabel(" · ".join(extras))
            detail.setWordWrap(True)
            detail.setStyleSheet(f"color: {c['fg_hint']}; font-size: 12px; border: none; background: transparent;")
            info.addWidget(detail)

        layout.addLayout(info, stretch=1)
        layout.addStretch()

    def contextMenuEvent(self, ev):
        # Handled by parent panel
        pass


class ExamPanel(QWidget):
    def __init__(self, dm: DataManager, parent=None):
        super().__init__(parent)
        self._dm = dm
        c = get_colors()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bar.setObjectName("taskBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(8)

        title = QLabel("考试")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bl.addWidget(title)
        bl.addStretch()

        add_btn = QPushButton("添加")
        add_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: #fff; border: none;
                border-radius: 8px; padding: 4px 14px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        add_btn.clicked.connect(lambda: self._add_exam())
        bl.addWidget(add_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border-radius: 8px; padding: 4px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
        refresh_btn.clicked.connect(self._refresh)
        bl.addWidget(refresh_btn)

        layout.addWidget(bar)

        # Scrollable card area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(16, 8, 16, 16)
        self._card_layout.setSpacing(8)
        self._card_layout.addStretch()
        scroll.setWidget(self._card_container)
        layout.addWidget(scroll, stretch=1)

        self._refresh()

    def _refresh(self) -> None:
        # Clear old cards (keep stretch)
        while self._card_layout.count() > 1:
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        exams = sorted(self._dm.exams.exams, key=lambda e: e.get("exam_date", ""))
        today = date.today()

        for e in exams:
            exam_date = e.get("exam_date", "")
            days_left = 999
            try:
                days_left = (date.fromisoformat(exam_date) - today).days
            except (ValueError, TypeError):
                pass

            card = _ExamCard(e, days_left)
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(
                lambda pos, ex=e: self._context_menu(pos, ex))
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _add_exam(self, exam: dict | None = None) -> None:
        dlg = ExamDialog(exam, self)
        if dlg.exec():
            data = dlg.result_data
            if exam:
                self._dm.exams.update_exam(exam["id"], data)
            else:
                self._dm.exams.add_exam(data)
            self._dm.exams.save()
            self._dm.data_changed.emit("exam")
            self._refresh()

    def _context_menu(self, pos, exam: dict) -> None:
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        """)
        menu.addAction("编辑").triggered.connect(lambda: self._add_exam(exam))
        menu.addAction("删除").triggered.connect(lambda: self._delete_exam(exam["id"]))
        menu.exec(self.mapToGlobal(pos))

    def _delete_exam(self, eid: str) -> None:
        name = eid
        for e in self._dm.exams.exams:
            if e["id"] == eid:
                name = e.get("course_name", eid)
                break
        if QMessageBox.question(self, "确认", f"删除考试「{name}」？") == QMessageBox.StandardButton.Yes:
            self._dm.exams.delete_exam(eid)
            self._dm.exams.save()
            self._dm.data_changed.emit("exam")
            self._refresh()

    def refresh_theme(self) -> None:
        self._refresh()


class ExamDialog(QDialog):
    def __init__(self, exam: dict | None = None, parent=None):
        super().__init__(parent)
        c = get_colors()
        editing = exam is not None
        self.setWindowTitle("编辑考试" if editing else "添加考试")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_card']}; color: {c['fg_primary']}; }}
            QLabel {{ color: {c['fg_primary']}; background: transparent; border: none; }}
            QLineEdit {{
                background-color: {c['bg_input']}; color: {c['fg_primary']};
                border: 1px solid {c['border']}; padding: 6px 10px; font-size: 13px;
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 16)
        form = QFormLayout()
        form.setSpacing(10)

        self._course = QLineEdit(exam.get("course_name", "") if exam else "")
        self._course.setPlaceholderText("如：高等数学")
        form.addRow("课程:", self._course)

        self._date = QLineEdit(exam.get("exam_date", "") if exam else "")
        self._date.setPlaceholderText("YYYY-MM-DD")
        form.addRow("考试日期:", self._date)

        self._scope = QLineEdit(exam.get("scope", "") if exam else "")
        self._scope.setPlaceholderText("如：第1-8章")
        form.addRow("范围:", self._scope)

        self._location = QLineEdit(exam.get("location", "") if exam else "")
        self._location.setPlaceholderText("如：教学楼A201")
        form.addRow("地点:", self._location)

        self._notes = QLineEdit(exam.get("notes", "") if exam else "")
        self._notes.setPlaceholderText("其他备注...")
        form.addRow("备注:", self._notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _ok(self) -> None:
        if not self._course.text().strip():
            QMessageBox.warning(self, "错误", "请输入课程名称。")
            return
        if not self._date.text().strip():
            QMessageBox.warning(self, "错误", "请输入考试日期。")
            return
        self.result_data = {
            "course_name": self._course.text().strip(),
            "exam_date": self._date.text().strip(),
            "scope": self._scope.text().strip(),
            "location": self._location.text().strip(),
            "notes": self._notes.text().strip(),
        }
        self.accept()
