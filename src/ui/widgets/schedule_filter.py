"""日程的「学习 / 生活」筛选（用户用例表第 13 条）。

用户原话："日程表界面有些拥挤了，加功能区分学习和生活显示"。

设计取舍：
- **规则给默认 + 用户可覆盖**（`daily_log.plan_category`）—— 不指望模型分类（它不可靠 ✗）
- **顶部三档筛选**，不做"按类别分组"：日程是按**节次**排的，分组会打乱时间轴 ✗
- 筛选是**视图状态**（和"看哪一边"一样），**不写进数据文件** ✓

搬进独立模块的原因：`schedule_view.py` 已经 789 行（上限 800），
塞不下筛选控件 + 过滤判断 + 菜单项。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from src.i18n.loader import tr
from src.models.daily_log import plan_category
from src.ui.styles.theme import SIZE_BODY_S, get_colors
from src.ui.widgets.rounded_button import RoundedButton

ALL, STUDY, LIFE = "all", "study", "life"


def visible(category: str, kind: str, plan: dict | None = None) -> bool:
    """当前筛选下这条该不该显示。`kind` ∈ `course` / `habit` / `plan`。

    课程算**学习**、习惯算**生活**、计划按 `plan_category()`（规则默认，用户可改）。
    """
    if category == ALL:
        return True
    if kind == "course":
        return category == STUDY
    if kind == "habit":
        return category == LIFE
    return plan_category(plan or {}) == category


def add_category_actions(menu, item: dict, on_pick) -> None:
    """给计划的右键菜单加「标记为学习 / 生活」（`on_pick(category)` 由调用方接）。"""
    from src.ui.widgets.menu import add_action

    for key, label in ((STUDY, tr("widget.schedule.menu_mark_study")),
                       (LIFE, tr("widget.schedule.menu_mark_life"))):
        add_action(menu, label, lambda checked=False, k=key: on_pick(k))


class CategoryFilter(QWidget):
    """三档分段控件：全部 / 学习 / 生活。`on_change(key)` 由调用方接。"""

    def __init__(self, on_change=None, parent=None) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._value = ALL
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self._buttons: dict[str, QPushButton] = {}
        for key, text in ((ALL, tr("widget.schedule.filter_all")),
                          (STUDY, tr("widget.schedule.filter_study")),
                          (LIFE, tr("widget.schedule.filter_life"))):
            btn = RoundedButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, k=key: self._pick(k))
            row.addWidget(btn)
            self._buttons[key] = btn
        self.refresh_theme()

    @property
    def value(self) -> str:
        return self._value

    def _pick(self, key: str) -> None:
        if key == self._value:
            return
        self._value = key
        self.refresh_theme()
        if self._on_change:
            self._on_change(key)

    def refresh_theme(self) -> None:
        """按当前主题重上色（选中档用强调色填充）。"""
        c = get_colors()
        for key, btn in self._buttons.items():
            on = key == self._value
            bg = c["accent"] if on else c["btn_secondary_bg"]
            fg = c["fg_on_fill"] if on else c["btn_secondary_fg"]
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {bg}; color: {fg}; border: none;"
                f" border-radius: 8px; padding: 4px 12px; font-size: {SIZE_BODY_S}px; }}")
