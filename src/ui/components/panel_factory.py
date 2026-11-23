"""面板工厂：首屏延迟构建（方案 A-1，`MD-files/PERFORMANCE_WORKFLOW.md` §3.1-1）。

**为什么需要**：`MainWorkspace.__init__` 原来一次构造 8 个面板 + 占位页 + 设置页，
而启动后用户只看得到「日程」。其余 7 个面板的构建成本全落在**首帧之前**，
正是手册 §2.2 表里"初始化多个面板"那一行。

**做法**：`PanelSlot` 是个"代理槽"—— 装进 `QStackedWidget` 的是一个**空容器**
（保证索引与 `_panel_map` 永远稳定），真正的面板在**首次需要时**才构造并塞进容器。
三条约束：

1. **对外入口不变**：`workspace._task_panel` 等属性首次访问即构造
   （`MainWorkspace.__getattr__` 落到这里）；
2. **事件不能丢**：面板建好之前到达的 `data_changed` 记进 `pending_events`，
   建好后立刻补刷一次（否则切过去看到的是"建面板那一刻"的旧数据）；
3. **可回退**：`LAZY_PANELS=0` 走原来的"全构造"路径（对照实验与线上回退都靠它）。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from PySide6.QtWidgets import QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

# 回退开关：`0` / `false` / `off` → 启动即全构造（与改造前完全一致）
LAZY_PANELS = os.environ.get("LIFE_ASSISTANT_LAZY_PANELS", "1").strip().lower() \
    not in ("0", "false", "off", "no")


class PanelSlot(QWidget):
    """一个面板的**代理槽**：容器先进栈，真面板首次使用时才构造。

    `key` 是导航键（`tasks` / `exams` …），`build()` 返回真正的面板。
    """

    def __init__(self, key: str, build: Callable[[], QWidget],
                 refresh: Callable[[QWidget, str], None], parent=None) -> None:
        super().__init__(parent)
        self._key = key
        self._build = build
        self._refresh = refresh
        # 建面板之前到达的事件（可能在 `__init__` 期间就来了）
        self._pending: list[str] = []
        self._panel: QWidget | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._layout = layout

    @property
    def key(self) -> str:
        return self._key

    @property
    def built(self) -> bool:
        return self._panel is not None

    def panel(self) -> QWidget:
        """取真面板（**首次调用即构造**，并把攒下的事件补刷掉）。"""
        if self._panel is None:
            self._panel = self._build()
            self._layout.addWidget(self._panel)
            for event in self._pending:
                self._refresh(self._panel, event)
            self._pending.clear()
        return self._panel

    def notify(self, event: str, *, decided: bool | None = None) -> None:
        """转发一个数据事件：已构造就刷，没构造就先攒着。

        `decided` 是**调用方已经算好的判断**（合并路径用它避免重复分派）：
        `True` = 该刷，`False` = 不该刷，`None` = 交给 `refresh` 回调自己判断。
        """
        if self._panel is None:
            self._pending.append(event)
            return
        if decided is False:
            return
        if decided is True:
            self._refresh_direct(self._panel)
            return
        self._refresh(self._panel, event)

    def _refresh_direct(self, panel: QWidget) -> None:
        """直接刷新（调用方已判定该刷）。"""
        hook = getattr(panel, "_refresh", None)
        if callable(hook):
            hook()

    def refresh_theme(self) -> None:
        """换主题只对**已构造**的面板生效（没构造的建出来就是新主题）。"""
        if self._panel is None:
            return
        hook = getattr(self._panel, "refresh_theme", None)
        if callable(hook):
            hook()


def mount(panel: QWidget, key: str, build: Callable[[], QWidget],
          refresh: Callable[[QWidget, str], None]) -> QWidget:
    """按 `LAZY_PANELS` 决定进栈的是"面板本身"还是"代理槽"。"""
    if not LAZY_PANELS or panel is not None:
        return panel if panel is not None else build()
    return PanelSlot(key, build, refresh)
