"""Course schedule panel — refined toolbar and table."""

from datetime import date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors
from src.ui.widgets.course_table import CourseTable


class CoursePanel(QWidget):
    def __init__(self, dm: DataManager, parent=None):
        super().__init__(parent)
        self._dm = dm

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        c = get_colors()

        # Toolbar
        bar = QWidget()
        bar.setObjectName("courseBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)

        self._week_label = QLabel()
        self._week_label.setFont(QFont(self.font().family(), 13))
        self._week_label.setStyleSheet("font-weight: 600; border: none;")
        bar_layout.addWidget(self._week_label)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: 1px solid {c['border']}; border-radius: 6px; padding: 4px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        """)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh)
        bar_layout.addWidget(refresh_btn)

        bar_layout.addStretch()

        for text, slot in [("< 上一周", self._prev_week), ("本周", self._go_today), ("下一周 >", self._next_week)]:
            btn = QPushButton(text)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                    border: 1px solid {c['border']}; border-radius: 6px; padding: 4px 12px; font-size: 13px; }}
                QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(slot)
            bar_layout.addWidget(btn)

        layout.addWidget(bar)

        # Table — row count driven by semester data, default 5
        self._table = CourseTable(self._dm.courses.get_period_count())
        self._table.course_rename_requested.connect(self._rename_course)
        self._table.course_delete_requested.connect(self._delete_course)
        layout.addWidget(self._table, stretch=1)

        # Footer
        footer = QWidget()
        footer.setObjectName("courseFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 4, 16, 4)
        self._count_label = QLabel()
        self._count_label.setObjectName("courseCount")
        fl.addWidget(self._count_label)
        layout.addWidget(footer)

        self._current_week_offset = 0
        self._refresh()

    @property
    def _week_number(self) -> int:
        semester = self._dm.courses.get_semester(self._dm.courses.current_semester)
        if not semester:
            return max(1, 1 + self._current_week_offset)
        total = semester.get("total_weeks", 20)
        try:
            today = date.today()
            start = date.fromisoformat(semester["start_date"])
            delta = (today - start).days
            base = max(1, delta // 7 + 1) if delta >= 0 else 1
        except (KeyError, ValueError):
            base = 1
        return max(1, min(base + self._current_week_offset, total))

    def _refresh(self) -> None:
        week = self._week_number
        semester = self._dm.courses.get_semester(self._dm.courses.current_semester)
        if semester:
            total = semester.get("total_weeks", 20)
        else:
            total = "?"
        self._week_label.setText(f"第 {week} / {total} 周")

        courses = []
        for day in range(1, 8):
            courses.extend(self._dm.courses.get_courses_for_day(day, week))

        self._table.set_courses(courses, week)
        self._count_label.setText(f"{len(courses)} 门课程")

    def _prev_week(self) -> None:
        self._current_week_offset -= 1
        self._refresh()

    def _next_week(self) -> None:
        self._current_week_offset += 1
        self._refresh()

    def _go_today(self) -> None:
        self._current_week_offset = 0
        self._refresh()

    def _rename_course(self, course_id: str) -> None:
        course = None
        for c in self._dm.courses.courses:
            if c["id"] == course_id:
                course = c
                break
        if course is None:
            return
        old_name = course.get("name", "")
        new_name, ok = QInputDialog.getText(
            self, "修改课程名称", "新名称:", text=old_name
        )
        if ok and new_name.strip():
            self._dm.courses.update_course(course_id, {"name": new_name.strip()})
            self._dm.courses.save()
            self._dm.data_changed.emit("update_course")
            self._refresh()

    def _delete_course(self, course_id: str) -> None:
        course = None
        for c in self._dm.courses.courses:
            if c["id"] == course_id:
                course = c
                break
        if course is None:
            return
        name = course.get("name", "未知课程")
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除「{name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._dm.courses.delete_course(course_id)
            self._dm.courses.save()
            self._dm.data_changed.emit("delete_course")
            self._refresh()

    def on_view_tasks(self, callback) -> None:
        self._table.view_course_tasks.connect(callback)

    @property
    def table(self) -> CourseTable:
        return self._table

    def refresh_theme(self) -> None:
        """Reapply dynamic styles on theme change."""
        c = get_colors()
        # generic button style for this panel
        btn_qss = f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: 1px solid {c['border']}; border-radius: 6px; padding: 4px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        """
        for btn in self.findChildren(QPushButton):
            try:
                btn.setStyleSheet(btn_qss)
            except Exception:
                pass

        # labels
        try:
            self._week_label.setStyleSheet("font-weight: 600; border: none; color: %s;" % c['fg_primary'])
        except Exception:
            pass

        # propagate to course table if it supports refresh
        if hasattr(self._table, 'refresh_theme') and callable(getattr(self._table, 'refresh_theme')):
            try:
                self._table.refresh_theme()
            except Exception:
                pass
