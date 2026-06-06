"""Popup showing schedules + tasks for a specific course."""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QTabWidget, QWidget,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors


class CourseDetailDialog(QDialog):
    def __init__(self, dm: DataManager, course_name: str, parent=None):
        super().__init__(parent)
        self._dm = dm
        self._course_name = course_name
        self._today = date.today().isoformat()

        c = get_colors()
        self.setWindowTitle(f"《{course_name}》的事项")
        self.setMinimumSize(420, 400)
        self.resize(480, 500)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_root']}; }}
            QListWidget {{ background-color: transparent; border: none; }}
            QListWidget::item {{ padding: 8px 12px; border-radius: 8px; font-size: 12px; color: {c['fg_primary']}; }}
            QListWidget::item:selected {{ background-color: {c['accent_bg']}; color: {c['fg_primary']}; }}
            QListWidget::item:hover {{ background-color: {c['bg_elevated']}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)

        title = QLabel(f"《{course_name}》")
        title.setFont(QFont(self.font().family(), 15))
        title.setStyleSheet(f"font-weight: 700; color: {c['fg_primary']};")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabBar::tab {{ padding: 6px 16px; font-size: 12px; color: {c['fg_secondary']}; border: none; }}
            QTabBar::tab:selected {{ color: {c['accent']}; font-weight: 600; border-bottom: 2px solid {c['accent']}; }}
        """)

        # 日程 tab
        sched = QWidget()
        sl = QVBoxLayout(sched); sl.setContentsMargins(0, 8, 0, 0)
        self._sched_list = QListWidget()
        sl.addWidget(self._sched_list)
        tabs.addTab(sched, "日程")

        # 作业 tab
        tasks_w = QWidget()
        tl = QVBoxLayout(tasks_w); tl.setContentsMargins(0, 8, 0, 0)
        self._task_list = QListWidget()
        tl.addWidget(self._task_list)
        tabs.addTab(tasks_w, "作业")

        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['fg_primary']};
                border: 1px solid {c['border']}; border-radius: 8px; padding: 6px 20px; font-size: 12px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self) -> None:
        cn = self._course_name

        # ── Plans ──────────────────────────────────────────
        self._sched_list.clear()
        all_plans = []
        for day, plans in self._dm.daily_logs._data.get("plans", {}).items():
            for p in plans:
                if p.get("course_name") == cn:
                    all_plans.append((day, p))
        all_plans.sort(key=lambda x: x[0])
        if all_plans:
            for day, p in all_plans:
                ts = p.get("time_slot", "?")
                title = p.get("title", "")
                is_past = day < self._today
                item = QListWidgetItem(f"📅 {day} 时段{ts} — {title}")
                if is_past:
                    item.setForeground(Qt.GlobalColor.gray)
                self._sched_list.addItem(item)
        else:
            item = QListWidgetItem("暂无日程计划")
            item.setForeground(Qt.GlobalColor.gray)
            self._sched_list.addItem(item)

        # ── Tasks ───────────────────────────────────────────
        self._task_list.clear()
        tasks = [t for t in self._dm.tasks.active if (t.get("course_name", "") or "") == cn]
        if tasks:
            for t in tasks:
                title = t.get("title", "")
                status = t.get("status", "pending")
                due = (t.get("due_date", "") or "")[:16].replace("T", " ")
                prefix = "✓" if status == "completed" else "○"
                label = f"{prefix} {title}"
                if due and due != "None":
                    label += f"\n  截止: {due}"
                item = QListWidgetItem(label)
                if status == "completed":
                    item.setForeground(Qt.GlobalColor.gray)
                self._task_list.addItem(item)
        else:
            item = QListWidgetItem("暂无作业")
            item.setForeground(Qt.GlobalColor.gray)
            self._task_list.addItem(item)

    def refresh_theme(self) -> None:
        c = get_colors()
        try:
            self.setStyleSheet(f"""
                QDialog {{ background-color: {c['bg_root']}; }}
                QListWidget {{ background-color: transparent; border: none; }}
                QListWidget::item {{ padding: 8px 12px; border-radius: 8px; font-size: 12px; color: {c['fg_primary']}; }}
                QListWidget::item:selected {{ background-color: {c['accent_bg']}; color: {c['fg_primary']}; }}
                QListWidget::item:hover {{ background-color: {c['bg_elevated']}; }}
            """)
        except Exception:
            pass
