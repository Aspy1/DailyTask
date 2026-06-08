"""Main content area — flat panel switching via sidebar navigation."""

from PySide6.QtWidgets import (
    QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.i18n.loader import tr
from src.services.settings_manager import SettingsManager
from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.ui.panels.settings_panel import SettingsPanel
from src.ui.panels.course_panel import CoursePanel
from src.ui.panels.task_panel import TaskPanel
from src.ui.panels.expense_panel import ExpensePanel
from src.ui.panels.habit_panel import HabitPanel
from src.ui.panels.exam_panel import ExamPanel
from src.ui.widgets.schedule_view import ScheduleView
from src.ui.widgets.course_detail_dialog import CourseDetailDialog
from src.ui.styles.theme import get_colors


class MainWorkspace(QWidget):
    """Content area that switches between panels based on sidebar selection."""

    def __init__(self, settings: SettingsManager, ai_service: AIService,
                 dm: DataManager, plugin_manager=None, parent=None):
        super().__init__(parent)
        self._dm = dm
        self._settings = settings
        self._ai_service = ai_service
        self._plugin_manager = plugin_manager

        c = get_colors()
        self.setObjectName("workspace")
        self.setStyleSheet(
            f"#workspace {{ background-color: {c['bg_root']}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # ── Create all panels ──────────────────────────────────
        self._schedule_view = ScheduleView(dm)
        self._course_panel = CoursePanel(dm)
        self._task_panel = TaskPanel(dm)
        self._habit_panel = HabitPanel(dm)
        self._exam_panel = ExamPanel(dm)
        self._expense_panel = ExpensePanel(dm)

        # Placeholder panels (will be replaced with real ones later)
        self._inventory_panel = self._placeholder("有什么", "物品统计与分类管理")
        self._meal_panel = self._placeholder("吃什么", "菜品记录与智能推荐")

        self._settings_panel = SettingsPanel(settings, ai_service, plugin_manager, dm)

        # ── Flat stack: index = nav key ────────────────────────
        self._panel_map: dict[str, int] = {
            "schedule": 0, "courses": 1, "tasks": 2,
            "exams": 3, "daily": 4, "expenses": 5,
            "inventory": 6, "meals": 7,
            "settings": 8,
        }
        panels = [
            self._schedule_view,   # 0: schedule
            self._course_panel,    # 1: courses
            self._task_panel,      # 2: tasks
            self._exam_panel,      # 3: exams
            self._habit_panel,     # 4: daily (habits)
            self._expense_panel,   # 5: expenses
            self._inventory_panel, # 6: inventory
            self._meal_panel,      # 7: meals
            self._settings_panel,  # 8: settings
        ]
        for p in panels:
            self._stack.addWidget(p)

        # ── Cross-panel signals ────────────────────────────────
        self._course_panel.on_view_tasks(self._on_view_course_tasks)
        self._schedule_view.course_table_requested.connect(
            lambda: self.switch_to("courses"))
        self._schedule_view.task_focus_requested.connect(self._on_task_focus)
        self._schedule_view.quick_adjust_requested.connect(self._on_quick_adjust)

        dm.data_changed.connect(self._on_data_changed)

    def _placeholder(self, title: str, desc: str) -> QWidget:
        c = get_colors()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {c['fg_primary']}; font-size: 20px; font-weight: 600;")
        desc_lbl = QLabel(desc)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px;")
        hint = QLabel("即将上线")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"color: {c['accent']}; font-size: 12px; margin-top: 8px;"
            f"padding: 4px 16px; background: {c['accent_bg']}; border-radius: 12px;")
        layout.addWidget(title_lbl)
        layout.addWidget(desc_lbl)
        layout.addWidget(hint)
        return page

    def switch_to(self, key: str) -> None:
        idx = self._panel_map.get(key)
        if idx is not None:
            self._stack.setCurrentIndex(idx)
            # Refresh the target panel
            w = self._stack.widget(idx)
            if hasattr(w, "_refresh") and callable(w._refresh):
                w._refresh()

    def _on_view_course_tasks(self, course_name: str) -> None:
        dlg = CourseDetailDialog(self._dm, course_name, self)
        dlg.exec()

    def _on_quick_adjust(self, prompt: str) -> None:
        """Forward quick-adjust prompt to AI panel."""
        # Trigger AI panel via the main window
        mw = self.window()
        if mw and hasattr(mw, 'ai_panel'):
            mw.ai_panel.fill_input(prompt)

    def _on_task_focus(self, course_name: str) -> None:
        self.switch_to("tasks")
        if course_name:
            self._task_panel.filter_by_course(course_name)

    def show_ddl_tasks(self) -> None:
        self.switch_to("tasks")
        self._task_panel.show_ddl_highlight()

    def _on_data_changed(self, action: str) -> None:
        self._course_panel._refresh()
        self._schedule_view._refresh()
        if "task" in action:
            self._task_panel._refresh()
        if "expense" in action:
            self._expense_panel._refresh()
        if "habit" in action:
            self._habit_panel._refresh()

    def refresh_theme(self) -> None:
        for attr in (
            "_course_panel", "_task_panel", "_schedule_view",
            "_habit_panel", "_expense_panel", "_inventory_panel",
            "_meal_panel", "_settings_panel",
        ):
            w = getattr(self, attr, None)
            if w is None:
                continue
            if hasattr(w, "refresh_theme") and callable(getattr(w, "refresh_theme")):
                try:
                    w.refresh_theme()
                except Exception:
                    pass

    @property
    def course_panel(self):
        return self._course_panel
