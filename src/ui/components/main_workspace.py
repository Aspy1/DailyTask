"""Column 3 → Main content area with flat tab switching."""

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
from src.ui.widgets.schedule_view import ScheduleView
from src.ui.widgets.course_detail_dialog import CourseDetailDialog
from src.ui.styles.theme import get_colors


class MainWorkspace(QWidget):
    def __init__(self, settings: SettingsManager, ai_service: AIService, dm: DataManager, plugin_manager=None, parent=None):
        super().__init__(parent)
        self._dm = dm
        self._settings = settings
        self._ai_service = ai_service
        self._plugin_manager = plugin_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # ── Study tab: course + task sub-tabs ─────────────────
        study = QWidget()
        sl = QVBoxLayout(study)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        c = get_colors()
        sub_bar = QWidget()
        sub_bar.setObjectName("taskBar")
        sbl = QHBoxLayout(sub_bar)
        sbl.setContentsMargins(12, 8, 12, 8)
        sbl.setSpacing(4)
        self._study_sub_btns = []
        self._study_sub_map: dict[str, int] = {"schedule": 0, "courses": 1, "tasks": 2}
        for text, key in [("日程", "schedule"), ("作业", "tasks")]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: transparent; color: {c['fg_secondary']}; border: none;
                    border-radius: 8px; padding: 4px 14px; font-size: 13px; }}
                QPushButton:hover {{ background-color: {c['accent_bg']}; }}
                QPushButton:checked {{ background-color: {c['nav_selected_bg']}; color: {c['nav_selected_fg']}; font-weight: 600; }}
            """)
            btn.clicked.connect(lambda checked, k=key: self._switch_study_sub(k))
            sbl.addWidget(btn)
            self._study_sub_btns.append(btn)
        sbl.addStretch()
        sl.addWidget(sub_bar)

        self._course_panel = CoursePanel(dm)
        self._task_panel = TaskPanel(dm)
        self._schedule_view = ScheduleView(dm)

        # Connect course-table right-click "view tasks" → switch to task panel + filter
        self._course_panel.on_view_tasks(self._on_view_course_tasks)

        study_sub = QStackedWidget()
        study_sub.addWidget(self._schedule_view)
        study_sub.addWidget(self._course_panel)
        study_sub.addWidget(self._task_panel)
        sl.addWidget(study_sub, stretch=1)
        self._study_sub_stack = study_sub
        self._study_sub_btns[0].setChecked(True)
        self._study_sub_stack.setCurrentIndex(0)

        # Schedule → course_table button opens course table
        self._schedule_view.course_table_requested.connect(lambda: self._switch_study_sub("courses"))
        # Schedule → DDL marker click opens task panel with course filter
        self._schedule_view.task_focus_requested.connect(self._on_task_focus)

        self._stack.addWidget(study)  # index 0: study

        # ── Life tab: habit + expense sub-tabs ────────────────
        life = QWidget()
        ll = QVBoxLayout(life)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        lbar = QWidget()
        lbar.setObjectName("taskBar")
        lblayout = QHBoxLayout(lbar)
        lblayout.setContentsMargins(12, 8, 12, 8)
        lblayout.setSpacing(4)
        self._life_sub_btns = []
        self._life_sub_map: dict[str, int] = {}
        for i, (text, key) in enumerate([("生活习惯", "habits"), ("记账", "expenses")]):
            self._life_sub_map[key] = i
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: transparent; color: {c['fg_secondary']}; border: none;
                    border-radius: 8px; padding: 4px 14px; font-size: 13px; }}
                QPushButton:hover {{ background-color: {c['accent_bg']}; }}
                QPushButton:checked {{ background-color: {c['nav_selected_bg']}; color: {c['nav_selected_fg']}; font-weight: 600; }}
            """)
            btn.clicked.connect(lambda checked, k=key: self._switch_life_sub(k))
            lblayout.addWidget(btn)
            self._life_sub_btns.append(btn)
        lblayout.addStretch()
        ll.addWidget(lbar)

        self._habit_panel = HabitPanel(dm)
        self._expense_panel = ExpensePanel(dm)

        life_sub = QStackedWidget()
        life_sub.addWidget(self._habit_panel)
        life_sub.addWidget(self._expense_panel)
        ll.addWidget(life_sub, stretch=1)
        self._life_sub_stack = life_sub
        self._life_sub_btns[0].setChecked(True)

        self._stack.addWidget(life)  # index 1: life

        # ── Plugins tab ───────────────────────────────────────
        from src.ui.panels.plugins_panel import PluginsPanel
        self._plugins_panel = PluginsPanel(plugin_manager, settings, ai_service, dm)
        self._stack.addWidget(self._plugins_panel)  # index 2

        # ── Settings tab ──────────────────────────────────────
        self._stack.addWidget(SettingsPanel(settings, ai_service, plugin_manager, dm))  # index 3
        # ── More placeholder ──────────────────────────────────
        self._stack.addWidget(self._placeholder("more"))  # index 4

        dm.data_changed.connect(self._on_data_changed)

    def _placeholder(self, tab_id: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(tr(f"tab.{tab_id}") if tab_id != "more" else "更多")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 18px;")
        layout.addWidget(label)
        return page

    def switch_to(self, tab_id: str) -> None:
        mapping = {"study": 0, "life": 1, "widgets": 2, "settings": 3, "more": 4}
        idx = mapping.get(tab_id, 0)
        self._stack.setCurrentIndex(idx)

    def _on_view_course_tasks(self, course_name: str) -> None:
        dlg = CourseDetailDialog(self._dm, course_name, self)
        dlg.exec()

    def _switch_study_sub(self, key: str) -> None:
        idx = self._study_sub_map.get(key, 0)
        self._study_sub_stack.setCurrentIndex(idx)
        # Only uncheck all if showing a panel without a button (courses)
        btn_idx = {"schedule": 0, "tasks": 1}.get(key, -1)
        for i, btn in enumerate(self._study_sub_btns):
            btn.setChecked(i == btn_idx)
        if key == "tasks":
            self._task_panel._refresh()
        elif key == "schedule":
            self._schedule_view._refresh()

    def _switch_life_sub(self, key: str) -> None:
        idx = self._life_sub_map.get(key, 0)
        self._life_sub_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._life_sub_btns):
            btn.setChecked(i == idx)
        self._life_sub_stack.widget(idx)._refresh()

    def _on_task_focus(self, course_name: str) -> None:
        """Handle click on DDL marker in schedule view."""
        self._switch_study_sub("tasks")
        if course_name:
            self._task_panel.filter_by_course(course_name)

    def show_ddl_tasks(self) -> None:
        self._switch_study_sub("tasks")
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
        # Call refresh hooks on child panels if they provide them
        for attr in (
            "_course_panel", "_task_panel", "_schedule_view",
            "_habit_panel", "_expense_panel", "_plugins_panel",
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
