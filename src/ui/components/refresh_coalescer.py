"""方案 A-3：合并同一操作造成的多次刷新（`MD-files/PERFORMANCE_WORKFLOW.md` §3.1-3）。

**问题**：一次用户操作往往广播多次 `data_changed`（勾选 → `task_status`；
AI 批量 → `ai_action`；外部/退出 → `external`），而 `MainWorkspace` 对每个事件
都**立刻**刷一遍面板。同一批数据被重画 N 次，用户只看到最后一次，前面全是白工。

**做法**：把同一事件循环轮次内到达的事件合并成**一次**刷新。
三条不变量（`tests/test_refresh_coalescer.py` 钉住）：

1. **同一轮合并**：3 个事件连发 → 只刷 1 次；
2. **事件不丢**：合并后仍按**最新事件**决定刷哪些面板（不能丢语义）；
3. **跨轮不合并**：两次用户操作的事件在不同轮次 → 各刷一次（中间态必须可见）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class RefreshCoalescer(QObject):
    """把短时间内到达的刷新请求合并成一次（**按事件循环轮次**，不是按时间猜）。

    用 `singleShot(0)` 而不是"等 X 毫秒"：`0` 表示"本轮事件处理完就执行"，
    与 Qt 的事件顺序一致，不会因为机器慢而把两次独立操作并成一次。

    **同步出口**：`flush_now()` 立即执行待处理刷新 —— 给"操作后必须马上看到结果"
    的路径用（外部写入、用户点完按钮）。只靠延迟合并会让界面晚一拍，
    那是**可见的回归**，不只是测试问题。
    """

    def __init__(self, apply: Callable[[list[str]], None], parent=None) -> None:
        super().__init__(parent)
        self._apply = apply
        self._pending: list[str] = []
        self._scheduled = False
        self._token = 0                 # 让过期的 singleShot 不重复执行
        self.apply_count = 0            # 供测试/诊断：真正刷了几次
        self.failed_count = 0           # 刷新本身失败的次数（不静默吞掉）

    @property
    def pending(self) -> list[str]:
        return list(self._pending)

    def request(self, event: str) -> None:
        """收到一个数据事件 → 记下来，本轮结束前只刷一次。"""
        if event not in self._pending:
            self._pending.append(event)
        if self._scheduled:
            return
        self._scheduled = True
        self._token += 1
        token = self._token
        QTimer.singleShot(0, lambda: self.flush_if(token))

    def flush_if(self, token: int) -> None:
        """定时器回调：只有**仍然有效**的那次才执行（先 `flush_now` 过就跳过）。"""
        if token != self._token:
            return
        self.flush()

    def flush_now(self) -> None:
        """**立即**执行（同步）：操作后必须马上看到结果的路径用它。"""
        self.flush()

    def flush(self) -> None:
        """执行合并后的刷新（事件按到达顺序交给 `apply`）。"""
        if not self._pending:
            self._scheduled = False
            return
        events = self._pending
        self._pending = []
        self._scheduled = False
        self._token += 1                # 让排队中的 singleShot 作废
        self.apply_count += 1
        try:
            self._apply(events)
        except Exception:      # 边界捕获：刷新失败不能让事件循环停摆
            logger.exception("合并刷新失败（事件：%s）", events)
            self.failed_count += 1
