"""Main content area — flat panel switching via sidebar navigation."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager
from src.ui.animations import fade_in
from src.ui.panels.course_panel import CoursePanel
from src.ui.panels.exam_panel import ExamPanel
from src.ui.panels.expense_panel import ExpensePanel
from src.ui.panels.habit_panel import HabitPanel
from src.ui.panels.inventory_panel import InventoryPanel
from src.ui.panels.routine_panel import RoutinePanel
from src.ui.panels.settings_panel import SettingsPanel
from src.ui.panels.study_panel import StudyPanel
from src.ui.panels.task_panel import TaskPanel
from src.ui.styles.theme import SIZE_BODY_S, SIZE_CAPTION, SIZE_SUBTITLE, get_colors
from src.ui.widgets.course_detail_dialog import CourseDetailDialog
from src.ui.widgets.schedule_view import ScheduleView

logger = logging.getLogger(__name__)


# 数据事件 → 需要刷新的面板键（**唯一映射**，2026-10-17 审查 #6）。
#
# 起因：原来只把 external / internal / ai_action 当"全刷"，其余用**子串**匹配
# （`key in action`）→ `task_status` / `update_course` 靠巧合匹配上，而 `"semester"`
# 匹配不上任何面板 → **切学期后作业/考试面板不刷新**；`"saving"` 也匹配不上记账面板。
# 现在显式登记，`tests/test_data_events.py` 扫全仓 emit 守住它。
# 未登记的事件 → `_on_data_changed` 保守全刷（不会漏，但浪费一次重绘）。
ALL_PANELS = frozenset({"task", "expense", "habit", "routine", "exam",
                        "inventory", "study"})
EVENT_PANELS: dict[str, frozenset[str]] = {
    # 域名本身（面板直接用自己的域发事件）
    "task": frozenset({"task"}),
    "exam": frozenset({"exam"}),
    "habit": frozenset({"habit"}),
    "routine": frozenset({"routine"}),
    "expense": frozenset({"expense"}),
    "inventory": frozenset({"inventory"}),
    "study": frozenset({"study"}),
    # 历史事件名（同一个域的不同写法，别让它们掉进"保守全刷"）
    "task_status": frozenset({"task"}),
    "saving": frozenset({"expense"}),      # 存钱也显示在记账面板（原来漏刷）
    "course": frozenset(),
    "update_course": frozenset(),
    "delete_course": frozenset(),
    "plan": frozenset(),
    # 切学期：课程表 / 作业 / 考试都换了一份数据（审查 #6 报的漏刷）
    "semester": frozenset({"task", "exam"}),
    # 来源不明（AI 批量改动 / 外部写入 / 内部批量）→ 全刷
    "ai_action": ALL_PANELS,
    "external": ALL_PANELS,
    "internal": ALL_PANELS,
}


class MainWorkspace(QWidget):
    """Content area that switches between panels based on sidebar selection."""

    # 课程右键"布置了作业 / 考试通知" → MainWindow 展开 AI 面板并填入 prompt。
    # 课程表（周视图）与日程（日视图）都走这条信号，不再一个发信号、一个借用 data_changed。
    fill_ai_prompt = Signal(str)
    # 面板切换（包括状态栏「DDL / 考试」跳转）→ 侧边栏高亮同步。
    panel_changed = Signal(str)

    def __init__(self, settings: SettingsManager, ai_service: AIService,
                 dm: DataManager, plugin_manager=None, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._settings = settings
        self._ai_service = ai_service
        self._plugin_manager = plugin_manager

        c = get_colors()
        self.setObjectName("workspace")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#workspace {{ background-color: {c['bg_root']}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # ── Create all panels ──────────────────────────────────
        # 课程表已并入日程（日/周切换），不再是独立面板 —— 见 ScheduleView.course_panel
        self._schedule_view = ScheduleView(dm)
        self._task_panel = TaskPanel(dm)
        self._habit_panel = HabitPanel(dm)
        self._routine_panel = RoutinePanel(dm)
        self._exam_panel = ExamPanel(dm)
        self._expense_panel = ExpensePanel(dm)
        self._study_panel = StudyPanel(dm)

        # Placeholder panels (will be replaced with real ones later)
        self._inventory_panel = InventoryPanel(dm)
        self._meal_panel = self._placeholder(
            tr("workspace.meal.title"), tr("workspace.meal.desc"))

        self._settings_panel = SettingsPanel(settings, ai_service, plugin_manager, dm)

        # ── Flat stack: index = nav key（顺序见 `_add_panels()`）──
        self._panel_map = self._add_panels()

        # ── Cross-panel signals ────────────────────────────────
        self._schedule_view.course_panel.on_view_tasks(self._on_view_course_tasks)
        self._schedule_view.task_focus_requested.connect(self._on_task_focus)
        self._schedule_view.quick_adjust_requested.connect(self._on_quick_adjust)
        self._schedule_view.fill_ai_prompt.connect(self.fill_ai_prompt.emit)

        dm.data_changed.connect(self._on_data_changed)

    def _add_panels(self) -> dict[str, int]:
        """按**导航键顺序**把面板装进栈，返回 `key → index`（顺序即索引）。"""
        panels = [
            ("schedule", self._schedule_view),     # 含 日/周 两页
            ("tasks", self._task_panel),
            ("exams", self._exam_panel),
            ("daily", self._habit_panel),          # 习惯
            ("routines", self._routine_panel),     # 近期安排（每日固定任务）
            ("study", self._study_panel),          # 考研备考（11408）
            ("expenses", self._expense_panel),
            ("inventory", self._inventory_panel),
            ("meals", self._meal_panel),
            ("settings", self._settings_panel),
        ]
        for _key, panel in panels:
            self._stack.addWidget(panel)
        return {key: idx for idx, (key, _panel) in enumerate(panels)}

    def _placeholder(self, title: str, desc: str) -> QWidget:
        c = get_colors()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {c['fg_primary']}; font-size: {SIZE_SUBTITLE}px; font-weight: 600;")
        desc_lbl = QLabel(desc)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setStyleSheet(f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px;")
        hint = QLabel(tr("workspace.placeholder.coming_soon"))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"color: {c['accent_text']}; font-size: {SIZE_CAPTION}px; margin-top: 8px;"
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
            fade_in(w)          # 动效模板（Q-H16）：只淡入，不动几何
            self.panel_changed.emit(key)

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
        # 日程视图**总是**刷（课程块 / 事项行 / 计划都在它里面）
        self._schedule_view._refresh()
        # 显式映射（见 EVENT_PANELS）：没登记的事件保守**全刷** —— 不会漏，但浪费一次重绘，
        # 且 `tests/test_data_events.py` 会红着提醒去登记（审查 2026-10-17 #6）
        keys = EVENT_PANELS.get(action, ALL_PANELS)
        for panel, key in (
            (self._task_panel, "task"),
            (self._expense_panel, "expense"),
            (self._habit_panel, "habit"),
            (self._routine_panel, "routine"),
            (self._exam_panel, "exam"),
            (self._inventory_panel, "inventory"),
            (self._study_panel, "study"),
        ):
            if key in keys:
                panel._refresh()

    def refresh_theme(self) -> None:
        # 自身底色也是构造时写死的，换主题必须重刷（否则内容区留着旧主题色）
        c = get_colors()
        self.setStyleSheet(
            f"#workspace {{ background-color: {c['bg_root']}; }}")
        for attr in (
            "_task_panel", "_schedule_view",
            "_habit_panel", "_expense_panel", "_inventory_panel",
            "_routine_panel", "_study_panel", "_meal_panel", "_settings_panel",
        ):
            w = getattr(self, attr, None)
            if w is None:
                continue
            if hasattr(w, "refresh_theme") and callable(w.refresh_theme):
                try:
                    w.refresh_theme()
                except Exception:
                    logger.debug("MainWorkspace.refresh_theme 中忽略异常", exc_info=True)

    @property
    def course_panel(self) -> CoursePanel:
        """课程表（已并入日程的周视图；保留该入口给菜单/测试用）。"""
        return self._schedule_view.course_panel

    @property
    def schedule_view(self) -> ScheduleView:
        return self._schedule_view
