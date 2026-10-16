"""Popup showing schedules + tasks for a specific course."""

import logging
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.styles.theme import FONT_CN, SIZE_TITLE, get_colors
from src.ui.widgets.rounded_button import RoundedButton

logger = logging.getLogger(__name__)


class CourseDetailDialog(QDialog):
    def __init__(self, dm: DataManager, course_name: str, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._course_name = course_name
        self._today = date.today().isoformat()

        c = get_colors()
        self.setWindowTitle(tr("dialog.course.window_title", name=course_name))
        self.setMinimumSize(420, 400)
        self.resize(480, 500)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_root']}; }}
            QListWidget {{ background-color: transparent; border: none; }}
            QListWidget::item {{ padding: 8px 12px; border-radius: 8px; font-size: 13px; color: {c['fg_primary']}; }}
            QListWidget::item:selected {{ background-color: {c['accent_bg']}; color: {c['fg_primary']}; }}
            QListWidget::item:hover {{ background-color: {c['bg_elevated']}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)

        title = QLabel(tr("dialog.course.title", name=course_name))
        title.setFont(QFont(FONT_CN, SIZE_TITLE))
        title.setStyleSheet(f"font-weight: 700; color: {c['fg_primary']};")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabBar::tab {{ padding: 6px 16px; font-size: 13px; color: {c['fg_secondary']}; border: none; }}
            QTabBar::tab:selected {{ color: {c['accent_text']}; font-weight: 600; border-bottom: 2px solid {c['accent']}; }}
        """)

        # 日程 tab
        sched = QWidget()
        sl = QVBoxLayout(sched)
        sl.setContentsMargins(0, 8, 0, 0)
        self._sched_list = QListWidget()
        sl.addWidget(self._sched_list)
        tabs.addTab(sched, tr("dialog.course.tab_schedule"))

        # 作业 tab
        tasks_w = QWidget()
        tl = QVBoxLayout(tasks_w)
        tl.setContentsMargins(0, 8, 0, 0)
        self._task_list = QListWidget()
        tl.addWidget(self._task_list)
        tabs.addTab(tasks_w, tr("dialog.course.tab_tasks"))

        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = RoundedButton(tr("dialog.course.btn_close"))
        close_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 6px 20px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self) -> None:
        self._fill_plans()
        self._fill_tasks()

    def _fill_plans(self) -> None:
        """填充「日程」标签页。"""
        cn = self._course_name
        self._sched_list.clear()
        all_plans = []
        for day, plans in self._dm.daily_logs._data.get("plans", {}).items():
            for p in plans:
                if p.get("course_name") == cn:
                    all_plans.append((day, p))
        all_plans.sort(key=lambda x: x[0])
        if not all_plans:
            item = QListWidgetItem(tr("dialog.course.empty_plans"))
            item.setForeground(Qt.GlobalColor.gray)
            self._sched_list.addItem(item)
            return
        for day, p in all_plans:
            ts = p.get("time_slot", "?")
            title = p.get("title", "")
            item = QListWidgetItem(tr("dialog.course.plan_item", day=day, slot=ts, title=title))
            if day < self._today:
                item.setForeground(Qt.GlobalColor.gray)
            self._sched_list.addItem(item)

    def _fill_tasks(self) -> None:
        """填充「作业」标签页。"""
        cn = self._course_name
        self._task_list.clear()
        tasks = [t for t in self._dm.tasks.active
                 if (t.get("course_name", "") or "") == cn]
        if not tasks:
            item = QListWidgetItem(tr("dialog.course.empty_tasks"))
            item.setForeground(Qt.GlobalColor.gray)
            self._task_list.addItem(item)
            return
        for t in tasks:
            self._task_list.addItem(self._make_task_item(t))

    @staticmethod
    def _make_task_item(t: dict) -> QListWidgetItem:
        """把单条任务转成列表项（已完成置灰）。"""
        title = t.get("title", "")
        status = t.get("status", "pending")
        due = (t.get("due_date", "") or "")[:16].replace("T", " ")
        prefix = "✓" if status == "completed" else "○"
        label = f"{prefix} {title}"
        if due and due != "None":
            label += tr("dialog.course.task_due", due=due)
        item = QListWidgetItem(label)
        if status == "completed":
            item.setForeground(Qt.GlobalColor.gray)
        return item

    def refresh_theme(self) -> None:
        c = get_colors()
        try:
            self.setStyleSheet(f"""
                QDialog {{ background-color: {c['bg_root']}; }}
                QListWidget {{ background-color: transparent; border: none; }}
                QListWidget::item {{ padding: 8px 12px; border-radius: 8px; font-size: 13px; color: {c['fg_primary']}; }}
                QListWidget::item:selected {{ background-color: {c['accent_bg']}; color: {c['fg_primary']}; }}
                QListWidget::item:hover {{ background-color: {c['bg_elevated']}; }}
            """)
        except Exception:
            logger.debug("CourseDetailDialog.refresh_theme 中忽略异常", exc_info=True)
