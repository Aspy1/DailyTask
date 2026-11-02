"""AI 高风险动作的**审批弹窗**（H1/P0，2026-11-02）。

用户在这里看到的是**将要发生什么**，而不是事后的一句"已完成"：

    命令原文 · 对象（哪个物品 / 哪门课 / 哪天的日程）· 改前 → 改后 · 会写哪个文件

三个出口都**不写数据**：点「拒绝」、超时（`DEFAULT_TIMEOUT_S`）、直接关窗口。

⚠ gesture id 由**本文件在用户点「允许执行」时**向 broker 申请（`issue_gesture()`），
模型/注入文本自己编一个 id 会被 broker 判为无效（见 `ai_approval`）。
⚠ 离屏可测：`tests/test_ai_approval.py` 直接构造弹窗并调用 `_on_approve` / `_on_deny` /
`_on_timeout`，不需要 `exec()` 事件循环。
"""

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QLabel

from src.i18n.loader import tr
from src.services.ai_approval import (
    DEFAULT_TIMEOUT_S,
    TIMEOUT,
    ApprovalBroker,
    ApprovalRequest,
)
from src.ui.styles.theme import LAYOUT, get_colors
from src.ui.widgets.dialog_shell import DialogShell, action_row, form_row

logger = logging.getLogger(__name__)

# 倒计时刷新间隔（秒级足够；审批要等用户读，不必更细）
_TICK_MS = 1000


def _value_label(text: str) -> QLabel:
    """值标签（可换行、可选中，长命令不会被截断成"看不出改了什么"）。"""
    label = QLabel(text or "—")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class ApprovalDialog(DialogShell):
    """一条高风险动作的确认框。`decided(True)` = 用户点了允许。"""

    decided = Signal(bool)

    def __init__(self, request: ApprovalRequest, broker: ApprovalBroker | None = None,
                 parent=None, timeout_s: float | None = None) -> None:
        super().__init__(parent, tr("dialog.ai_approval.title"),
                         min_width=LAYOUT["dialog_width_md"], buttons=False)
        self.request = request
        self.gesture_id = ""
        self.timed_out = False
        self._broker = broker
        self._remaining = float(timeout_s if timeout_s is not None else
                                (request.timeout_s or DEFAULT_TIMEOUT_S))
        self._build_body()
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._update_countdown()

    # ── 界面 ──────────────────────────────────────────────
    def _build_body(self) -> None:
        heading = QLabel(tr("dialog.ai_approval.heading"))
        heading.setStyleSheet(f"font-weight: 600; color: {get_colors()['fg_primary']};")
        self.body.addWidget(heading)
        self.body.addWidget(form_row(tr("dialog.ai_approval.label_command"),
                                     _value_label(self.request.command)))
        self.body.addWidget(form_row(tr("dialog.ai_approval.label_object"),
                                     _value_label(self.request.object_label)))
        self.body.addWidget(form_row(tr("dialog.ai_approval.label_file"),
                                     _value_label(self.request.write_target)))
        self.body.addWidget(QLabel(tr("dialog.ai_approval.label_effect")))
        self.body.addWidget(_value_label("\n".join(self.request.diff_lines())))
        self.body.addWidget(self._hint_label())
        self.add_action_row(action_row(
            tr("dialog.ai_approval.btn_approve"), self._on_approve,
            cancel_text=tr("dialog.ai_approval.btn_deny"), on_cancel=self._on_deny,
            danger=True))

    def _hint_label(self) -> QLabel:
        label = QLabel(tr("dialog.ai_approval.hint"))
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {get_colors()['fg_secondary']};")
        self._countdown = label
        return label

    def _update_countdown(self) -> None:
        seconds = max(0, round(self._remaining))
        self._countdown.setText(
            f"{tr('dialog.ai_approval.hint')}\n{tr('dialog.ai_approval.countdown', seconds=seconds)}")

    # ── 出口（三个都**不写数据**）────────────────────────────
    def _tick(self) -> None:
        self._remaining -= _TICK_MS / 1000.0
        if self._remaining <= 0:
            self._on_timeout()
            return
        self._update_countdown()

    def _on_approve(self) -> None:
        """允许：gesture id 由 **UI 侧**申请（模型拿不到，也无法伪造）。"""
        self._stop_timer()
        if self._broker is not None:
            self.gesture_id = self._broker.issue_gesture()
        self.decided.emit(True)
        self.accept()

    def _on_deny(self) -> None:
        self._stop_timer()
        self.decided.emit(False)
        self.reject()

    def _on_timeout(self) -> None:
        self.timed_out = True
        self._stop_timer()
        self.decided.emit(False)
        self.reject()

    def _stop_timer(self) -> None:
        if getattr(self, "_timer", None) is not None:
            self._timer.stop()

    def reject(self) -> None:
        """关窗口 / Esc = 拒绝（**默认不写**）。"""
        self._stop_timer()
        super().reject()


class ApprovalPrompt:
    """把 `ApprovalBroker.approval_requested` 接到弹窗上的**主线程适配器**。

    生命周期：`MainWindow` 构造时建一份（`broker.attach()` 之后才算有界面）。
    没有它 → broker 一律 `NO_UI` 拒绝（脚本/评估/无界面启动时**不会**误写）。
    """

    def __init__(self, broker: ApprovalBroker, parent=None,
                 timeout_s: float | None = None) -> None:
        self._broker = broker
        self._parent = parent
        self._timeout_s = timeout_s
        self._dialog: ApprovalDialog | None = None
        broker.approval_requested.connect(self._on_requested)
        broker.attach()

    def _on_requested(self, request: ApprovalRequest) -> None:
        dialog = ApprovalDialog(request, self._broker, self._parent, self._timeout_s)
        self._dialog = dialog
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._dialog = None
        reason = TIMEOUT if dialog.timed_out else ""
        self._broker.resolve(request.request_id, accepted, dialog.gesture_id, reason=reason)

    def shutdown(self) -> None:
        """退出时断开并标记"没有界面"（之后的高风险动作直接拒绝，不会卡住）。"""
        self._broker.detach()
        try:
            self._broker.approval_requested.disconnect(self._on_requested)
        except (RuntimeError, TypeError):
            # 已断开 / 对象已销毁：退出路径可忽略（CODE_STANDARDS Q-I1 显式边界）
            logger.debug("审批信号断开失败（退出路径可忽略）", exc_info=True)

    @property
    def dialog(self) -> ApprovalDialog | None:
        """当前打开的弹窗（off-screen 测试用）。"""
        return self._dialog


__all__ = ["ApprovalDialog", "ApprovalPrompt"]
