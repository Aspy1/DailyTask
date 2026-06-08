"""Exam panel — list, add, edit upcoming exams."""

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialog, QLineEdit, QFormLayout,
    QDialogButtonBox, QMessageBox, QMenu,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE


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
        add_btn.clicked.connect(self._add_exam)
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

        # Exam list
        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none; }}
            QListWidget::item {{ padding: 12px 16px; border-bottom: 1px solid {c['border']}; }}
            QListWidget::item:selected {{ background-color: {c['accent_bg']}; }}
        """)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self._list, stretch=1)

        self._refresh()

    def _refresh(self) -> None:
        c = get_colors()
        self._list.clear()
        exams = sorted(self._dm.exams.exams, key=lambda e: e.get("exam_date", ""))
        today = date.today().isoformat()

        for e in exams:
            exam_date = e.get("exam_date", "")
            course = e.get("course_name", "")
            scope = e.get("scope", "") or ""
            notes = e.get("notes", "") or ""
            location = e.get("location", "") or ""

            # Days until exam
            days_left = ""
            delta = 999  # default: far future
            if exam_date:
                try:
                    delta = (date.fromisoformat(exam_date) - date.today()).days
                    if delta < 0:
                        days_left = " (已过)"
                    elif delta == 0:
                        days_left = " ★今天!"
                    elif delta <= 3:
                        days_left = f" ({delta}天后)"
                    elif delta <= 7:
                        days_left = f" ({delta}天后)"
                    else:
                        days_left = f" ({delta}天后)"
                except ValueError:
                    pass

            text = f"{course}  —  {exam_date}{days_left}"
            if scope:
                text += f"\n  范围: {scope}"
            if notes:
                text += f"\n  {notes}"
            if location:
                text += f"\n  地点: {location}"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, e["id"])
            if delta < 0:
                item.setForeground(Qt.GlobalColor.gray)
            self._list.addItem(item)

    def _add_exam(self, exam: dict | None = None) -> None:
        dlg = ExamDialog(self._dm, exam, self)
        if dlg.exec():
            data = dlg.result_data
            if exam:
                self._dm.exams.update_exam(exam["id"], data)
            else:
                self._dm.exams.add_exam(data)
            self._dm.exams.save()
            self._dm.data_changed.emit("exam")
            self._refresh()

    def _context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        eid = item.data(Qt.ItemDataRole.UserRole)
        exam = None
        for e in self._dm.exams.exams:
            if e["id"] == eid:
                exam = e
                break
        if not exam:
            return

        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        """)
        menu.addAction("编辑").triggered.connect(lambda: self._add_exam(exam))
        menu.addAction("删除").triggered.connect(lambda: self._delete_exam(eid))
        menu.exec(self._list.mapToGlobal(pos))

    def _delete_exam(self, eid: str) -> None:
        exam = None
        for e in self._dm.exams.exams:
            if e["id"] == eid:
                exam = e
                break
        name = exam.get("course_name", eid) if exam else eid
        if QMessageBox.question(self, "确认", f"删除考试「{name}」？") == QMessageBox.StandardButton.Yes:
            self._dm.exams.delete_exam(eid)
            self._dm.exams.save()
            self._dm.data_changed.emit("exam")
            self._refresh()

    def refresh_theme(self) -> None:
        self._refresh()


class ExamDialog(QDialog):
    def __init__(self, dm: DataManager, exam: dict | None = None, parent=None):
        super().__init__(parent)
        self._dm = dm
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
        self._date.setPlaceholderText("YYYY-MM-DD 如 2026-06-20")
        form.addRow("考试日期:", self._date)

        self._scope = QLineEdit(exam.get("scope", "") if exam else "")
        self._scope.setPlaceholderText("考试范围，如：第1-8章")
        form.addRow("范围:", self._scope)

        self._location = QLineEdit(exam.get("location", "") if exam else "")
        self._location.setPlaceholderText("如：教学楼A201")
        form.addRow("地点:", self._location)

        self._notes = QLineEdit(exam.get("notes", "") if exam else "")
        self._notes.setPlaceholderText("其他备注...")
        form.addRow("备注:", self._notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
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
