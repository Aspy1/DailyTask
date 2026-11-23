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
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager
from src.ui.animations import fade_in
from src.ui.components import panel_factory
from src.ui.components.panel_factory import PanelSlot
from src.ui.components.refresh_coalescer import RefreshCoalescer
from src.ui.panels.course_panel import CoursePanel
from src.ui.panels.exam_panel import ExamPanel
from src.ui.panels.expense_panel import ExpensePanel
from src.ui.panels.habit_panel import HabitPanel
from src.ui.panels.inventory_panel import InventoryPanel
from src.ui.panels.routine_panel import RoutinePanel
from src.ui.panels.settings_panel import SettingsPanel
from src.ui.panels.study_panel import StudyPanel
from src.ui.panels.task_panel import TaskPanel
from src.ui.styles.theme import (
    MOTION,
    SIZE_BODY_S,
    SIZE_CAPTION,
    SIZE_SUBTITLE,
    get_colors,
    surface_color,
)
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
    # AI 动作级撤销（H3，2026-11-02）：撤销会把**上一次写入涉及的任意文件**还原
    # （库存 / 日程 / 记账 / 课表…），所以同样按全刷处理 —— 只刷一个面板会留下
    # "数据已经回去了、界面还是旧值"的错觉。
    "ai_undo": ALL_PANELS,
    "external": ALL_PANELS,
    "internal": ALL_PANELS,
}


# **导航键 → 事件域名**：两者不是同一个词（`tasks` ↔ `task`、`daily` ↔ `habit`、
# `routines` ↔ `routine`）。`EVENT_PANELS` 用的是**域名**，所以比对前必须先翻译 ——
# 直接拿导航键去比会静默失效（只有 `inventory` 这种恰好相同的才会刷）。
KEY_TO_DOMAIN: dict[str, str] = {
    "tasks": "task",
    "exams": "exam",
    "daily": "habit",
    "routines": "routine",
    "study": "study",
    "expenses": "expense",
    "inventory": "inventory",
}

# 这些事件**走延迟合并**（一操作多广播的批量场景）：
# `ai_action` 是 AI 一次批量写入、`ai_undo` 是跨文件还原 —— 两者都会连发多个事件。
# 其余事件（单域变更 / external / semester）一律**同步刷**：
# 用户点完就该看到结果，"晚一拍"是可见回归（`tests/test_data_flow.py` 钉住这条语义）。
COALESCED_EVENTS = frozenset({"ai_action", "ai_undo"})


# **属性名 ↔ 导航键**（不是同一个词：`tasks` ↔ `_task_panel`）。
# 延迟构建靠它把"既有入口 `workspace._task_panel`"落到正确的代理槽上；
# `tests/test_lazy_panels.py` 会核对"每个延迟键都有对应属性"。
ATTR_TO_KEY: dict[str, str] = {
    "_task_panel": "tasks",
    "_exam_panel": "exams",
    "_habit_panel": "daily",
    "_routine_panel": "routines",
    "_study_panel": "study",
    "_expense_panel": "expenses",
    "_inventory_panel": "inventory",
}


class MainWorkspace(QWidget):
    """Content area that switches between panels based on sidebar selection."""

    # 面板切换（包括状态栏「DDL / 考试」跳转）→ 侧边栏高亮同步。
    panel_changed = Signal(str)

    def __init__(self, settings: SettingsManager,
                 dm: DataManager, plugin_manager=None, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._settings = settings
        self._plugin_manager = plugin_manager

        self.setObjectName("workspace")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 切页时的容器底色 = `surfaces.transition`（必须与内容同色，否则换页会闪）
        self.setStyleSheet(
            f"#workspace {{ background-color: {surface_color('transition')}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # ── 面板：首屏立即构造，其余**首次进入时**再建（方案 A-1）──────────
        # 启动后用户只看得到「日程」，把 7 个面板的构建成本压在首帧之前是纯浪费
        # （`MD-files/PERFORMANCE_WORKFLOW.md` §2.2「初始化多个面板」）。
        # 对外入口 `self._task_panel` 等**保持不变**：首次访问即构造（见 `__getattr__`）。
        # 回退：环境变量 `LIFE_ASSISTANT_LAZY_PANELS=0` → 全构造（与改造前一致）。
        self._slots: dict[str, PanelSlot] = {}
        self._built: dict[str, object] = {}

        self._schedule_view = ScheduleView(dm)          # 首屏，必须立即构造
        self._meal_panel = self._placeholder(
            tr("workspace.meal.title"), tr("workspace.meal.desc"))
        self._settings_panel = SettingsPanel(settings, plugin_manager, dm)

        # ── Flat stack: index = nav key（顺序见 `_add_panels()`）──
        self._panel_map = self._add_panels()

        # ── Cross-panel signals ────────────────────────────────
        self._schedule_view.course_panel.on_view_tasks(self._on_view_course_tasks)
        self._schedule_view.task_focus_requested.connect(self._on_task_focus)

        self._coalescer = RefreshCoalescer(self._apply_refresh, self)
        dm.data_changed.connect(self._on_data_changed)

    # ── 延迟构造的面板 ────────────────────────────────────────

    def _lazy_panel(self, key: str) -> QWidget | None:
        """取一个延迟面板（**首次调用即构造**）；未知键 → None。"""
        slot = self._slots.get(key)
        return slot.panel() if slot is not None else None

    def __getattr__(self, name: str) -> object:
        """`workspace._task_panel` 这类**既有入口**在首次访问时按需构造。

        导航键（`tasks`）与属性名（`_task_panel`）**不是**同一个词（单复数/词形都不同），
        所以走显式表 `ATTR_TO_KEY`。只处理表里登记的属性；
        其它属性一律走正常失败（不能把拼写错误吞成 None）。
        """
        key = ATTR_TO_KEY.get(name)
        slots = self.__dict__.get("_slots") or {}
        if key is not None and key in slots:
            return slots[key].panel()
        # 回退模式（`LAZY_PANELS=0`）：面板是**直接构造**的，没有代理槽
        built = self.__dict__.get("_built") or {}
        if key is not None and key in built:
            return built[key]
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def _add_panels(self) -> dict[str, int]:
        """按**导航键顺序**把面板装进栈，返回 `key → index`（顺序即索引）。

        延迟模式下装进栈的是 `PanelSlot`（空容器 + 构造回调），索引与键集不变。
        """
        panels = [
            ("schedule", self._schedule_view),     # 含 日/周 两页（首屏，已构造）
            ("tasks", TaskPanel),                  # 以下均延迟构造
            ("exams", ExamPanel),
            ("daily", HabitPanel),                 # 习惯
            ("routines", RoutinePanel),            # 近期安排（每日固定任务）
            ("study", StudyPanel),                 # 考研备考（11408）
            ("expenses", ExpensePanel),
            ("inventory", InventoryPanel),
            ("meals", self._meal_panel),
            ("settings", self._settings_panel),
        ]
        mapping: dict[str, int] = {}
        for index, (key, factory) in enumerate(panels):
            widget = (factory if not isinstance(factory, type)
                      else self._slot_for(key, factory))
            self._stack.addWidget(widget)
            mapping[key] = index
        return mapping

    def _slot_for(self, key: str, factory: type) -> QWidget:
        """为一个延迟面板建代理槽（`LAZY_PANELS=0` 时直接构造）。"""
        def build() -> QWidget:
            panel = factory(self._dm)
            self._built[key] = panel
            return panel

        # ⚠ 读模块属性而不是 `from ... import LAZY_PANELS` 的值：
        #   按值复制会在 import 时定型，运行期改开关（测试 / 回退）就失效了 ——
        #   那会让"回退路径"从未被真正执行过。
        if not panel_factory.LAZY_PANELS:
            return build()
        # 回调签名是 `(panel, event)`（槽持有面板实例，这里只按域名判断要不要刷）
        slot = PanelSlot(key, build, lambda panel, event: self._refresh_by_panel(key, panel, event))
        self._slots[key] = slot
        return slot

    def _panel_of(self, key: str) -> QWidget | None:
        """延迟键 → 真面板（未构造时返回 None，不触发构造）。"""
        return self._built.get(key)

    def _refresh_by_panel(self, key: str, panel: QWidget, event: str) -> None:
        """按**域名映射**刷新一个延迟面板（与 `_on_data_changed` 同一份 EVENT_PANELS）。

        ⚠ 必须先把导航键翻译成域名：`EVENT_PANELS` 存的是 `task` / `exam`，
        拿 `tasks` / `exams` 直接比会**静默不刷**（只有 `inventory` 恰好同名）。
        """
        domain = KEY_TO_DOMAIN.get(key)
        if domain is not None and domain in EVENT_PANELS.get(event, ALL_PANELS):
            self._refresh_panel(panel)

    def _notify_panels(self, event: str) -> None:
        """把事件转给所有延迟面板：没构造的先攒着（建好后补刷，事件不丢）。"""
        for slot in self._slots.values():
            slot.notify(event)

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

    def switch_to(self, key: str, refresh: bool = True) -> None:
        """切到某个面板。

        顺序是 **刷新 → 定淡入起点 → 显示**，每一步都有理由：

        1. **先刷再显示**：原来先 `setCurrentIndex()` 再 `_refresh()`，于是"显示出来的
           第一帧"是上一轮的旧内容（首次进入就是空表格）→ 看着像闪一下空白。
        2. **只在换页时淡入**，且只淡**内容区**（`panel.fade_target()`）：整块面板淡入会把
           工具栏 / 页脚这些静态外框一起淡掉，切换看起来在"抖"。
        3. 淡入起点是 `motion.switch_fade_from`（0.9）而不是 0：起点 0 让第一帧整块透明，
           同样的空白帧换个地方出现而已。
        4. 同一页重复 `switch_to` 不淡入（点两次同一导航项不该闪）。

        `refresh=False` 给"切过去之后自己会刷"的调用方用（如 `show_ddl_tasks`）：
        否则同一份数据刷两遍（先 `_refresh`、再 `show_ddl_highlight` 里再 `_refresh`）。
        """
        idx = self._panel_map.get(key)
        if idx is None:
            return
        panel = self._stack.widget(idx)
        if isinstance(panel, PanelSlot):
            # 首次进入 → 此刻才构造，并把栈里那一格**换成真面板**。
            # 为什么必须替换而不是"装着槽"：`currentWidget()` 是既有契约
            # （`test_routine_panel` 等直接比较），槽留在栈里会让它返回容器而不是面板。
            real = panel.panel()
            self._stack.removeWidget(panel)
            self._stack.insertWidget(idx, real)
            del self._slots[key]
            panel.deleteLater()
            panel = real
        if refresh:
            self._refresh_panel(panel)
        if self._stack.currentIndex() != idx:
            fade_in(self._fade_target(panel),
                    duration=MOTION["duration_switch"],
                    start=MOTION["switch_fade_from"])
            self._stack.setCurrentIndex(idx)
        self.panel_changed.emit(key)      # 语义不变：无论是否换页都通知侧边栏

    @staticmethod
    def _refresh_panel(panel: QWidget) -> None:
        """刷新面板（`_refresh` 是全仓约定入口；没有该方法的占位页跳过）。"""
        refresh = getattr(panel, "_refresh", None)
        if callable(refresh):
            refresh()

    @staticmethod
    def _fade_target(panel: QWidget) -> QWidget:
        """淡入的目标控件：面板可指定 `fade_target()`（内容区），默认整个面板。"""
        target = getattr(panel, "fade_target", None)
        return target() if callable(target) else panel

    def _on_view_course_tasks(self, course_name: str) -> None:
        dlg = CourseDetailDialog(self._dm, course_name, self)
        dlg.exec()

    def _on_task_focus(self, course_name: str) -> None:
        # `refresh=False`：下面一定会刷一次（筛选或直接刷新），别白刷两遍
        self.switch_to("tasks", refresh=False)
        if course_name:
            self._task_panel.filter_by_course(course_name)
        else:
            self._refresh_panel(self._task_panel)

    def show_ddl_tasks(self) -> None:
        # 同上：`show_ddl_highlight()` 内部已经 `_refresh()` 过了
        self.switch_to("tasks", refresh=False)
        self._task_panel.show_ddl_highlight()

    def _on_data_changed(self, action: str) -> None:
        """数据事件 → 刷新。**默认同步**，只有批量事件走合并（方案 A-3）。

        为什么默认同步：用户点完勾选 / 外部写入到达，界面必须**当场**更新；
        把刷新推迟到下一轮事件循环是可见回归（`tests/test_data_flow.py` 钉住）。
        合并只对"一次操作连发多个事件"的批量场景有价值 —— 目前是 AI 批量写入
        与跨文件撤销（`ai_action` / `ai_undo`），它们逐个刷会把同一批数据重画多次。
        """
        if action not in COALESCED_EVENTS:
            self._apply_refresh([action])
            return
        self._coalescer.request(action)

    def _apply_refresh(self, events: list[str]) -> None:
        """合并后的真正刷新：**先把事件并成一份要刷的面板集合**，再各刷一次。

        逐事件分派会让同一面板被刷多次（`task` + `task_status` 都要刷作业面板）——
        合并的意义就在这里：同一批数据只重画一遍。
        """
        self._schedule_view._refresh()
        domains: set[str] = set()
        include_unknown = False
        for event in events:
            mapped = EVENT_PANELS.get(event)
            if mapped is None:
                include_unknown = True          # 未登记事件 → 保守全刷
                continue
            domains |= mapped
        if include_unknown:
            domains |= ALL_PANELS
        for key, slot in self._slots.items():
            domain = KEY_TO_DOMAIN.get(key)
            if domain is None:
                continue
            # 判断在这里做完，槽只负责"刷 or 攒着"（不再重复分派）
            slot.notify(events[-1] if events else "", decided=domain in domains)
        for key, panel in self._built.items():
            if key not in self._slots and KEY_TO_DOMAIN.get(key) in domains:
                self._refresh_panel(panel)

    def refresh_theme(self) -> None:
        # 自身底色也是构造时写死的，换主题必须重刷（否则内容区留着旧主题色）
        self.setStyleSheet(
            f"#workspace {{ background-color: {surface_color('transition')}; }}")
        # 已构造的延迟面板（没构造的建出来就是新主题，不必唤起来）
        for slot in self._slots.values():
            slot.refresh_theme()
        for key, panel in self._built.items():
            if key not in self._slots:
                hook = getattr(panel, "refresh_theme", None)
                if callable(hook):
                    hook()
        for attr in ("_schedule_view", "_meal_panel", "_settings_panel"):
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
