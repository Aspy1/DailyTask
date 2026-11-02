"""高风险写入的**人工审批门**（H1/H2/P0，2026-11-02）。

问题（审查 H1）：模型返回的 ```sh 代码块**在同一轮由 worker 直接执行**，用户看到回复时
写入已经发生；提示词还要求模型"不要请求确认"。于是"先看要改什么、再决定"这一步根本不存在。

这里把它做成**代码里的门**（不是提示词）：

    策略判定为 HIGH_WRITE（见 `ai_policy`）
        → worker 线程 `broker.request()` **阻塞**
        → 主线程弹审批框（命令 / 对象 / 改前改后 / 将写哪个文件）
        → 用户批准 → UI **生成 gesture id** → `resolve(granted=True)`
        → 用户拒绝 / 超时 / 窗口关闭 → `resolve(granted=False)` → **一个字节都不写**

三条硬约束：

1. **默认拒绝**：没有界面（脚本 / 评估 / 无 UI 的单测）时不审批也不执行（`NO_UI`）。
2. **gesture id 由 UI 生成**：`issue_gesture()` 只在 UI 侧调用；`resolve` 校验它确实由本
   进程的 UI 签发 —— 模型（或注入的文本）自己编一个 id 一律无效（论文 P5 的"同机 approval
   可被 agent 绕过"在这里被挡在 `_gestures` 集合外）。
3. **超时 = 拒绝**：`DEFAULT_TIMEOUT_S`（120s）内没有答复就算拒绝；窗口关闭同样按拒绝。

⚠ 残余风险（如实写在这里，不假装解决）：这仍是**单机软审批**，不防"能直接改文件/能调
CLI 的本机进程"；它只保证 **AI 这条路径**在没人点"允许"时不会写。
"""

import logging
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# 审批结果（写进审计日志，`reason` 是用户/系统可读的值）
APPROVED = "approved"
DENIED = "denied"
TIMEOUT = "timeout"
NO_UI = "no_ui"
INVALID_GESTURE = "invalid_gesture"

DEFAULT_TIMEOUT_S = 120.0


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class ApprovalRequest:
    """一条待审批的高风险动作（**只读**快照，UI 拿它画界面）。"""

    request_id: str
    command: str
    operation: str
    level: str
    object_label: str = ""
    write_target: str = ""
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    timeout_s: float = DEFAULT_TIMEOUT_S
    created_at: str = field(default_factory=_now)

    def diff_lines(self) -> list[str]:
        """`字段：改前 → 改后`（两边都没有的字段不显示）。"""
        keys = list(dict.fromkeys([*self.before, *self.after]))
        return [f"{key}: {self.before.get(key, '（无）')} → {self.after.get(key, '（无）')}"
                for key in keys]


@dataclass(frozen=True)
class ApprovalOutcome:
    """审批结论。`granted=False` 时调用方**不得**执行写入。"""

    granted: bool
    reason: str
    gesture_id: str = ""
    decided_at: str = field(default_factory=_now)

    @property
    def denied_by_user(self) -> bool:
        return self.reason == DENIED


class _Pending:
    """一次在途审批：worker 等 `event`，UI 填 `outcome`。"""

    __slots__ = ("event", "outcome")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.outcome: ApprovalOutcome | None = None


class ApprovalBroker(QObject):
    """审批请求的**中继**：worker 线程阻塞等待，主线程弹框。

    ⚠ `request()` 会在**调用它的线程**里阻塞（AI worker 线程），绝不能在主线程调用 ——
    主线程要负责画弹窗，自己等自己会死锁。
    """

    approval_requested = Signal(object)   # ApprovalRequest

    def __init__(self, timeout_s: float = DEFAULT_TIMEOUT_S, parent=None) -> None:
        super().__init__(parent)
        self._timeout_s = max(0.0, float(timeout_s))
        self._pending: dict[str, _Pending] = {}
        self._gestures: set[str] = set()
        self._lock = threading.Lock()
        self._ui_attached = False

    # ── UI 侧 ─────────────────────────────────────────────
    def attach(self) -> None:
        """有界面接管审批（`ApprovalPrompt` 构造时调用）。"""
        self._ui_attached = True

    def detach(self) -> None:
        """界面没了 → 之后一律按"无界面"拒绝（不会卡住 120s）。"""
        self._ui_attached = False

    def issue_gesture(self) -> str:
        """**只给 UI 调**：签发一个一次性的审批手势 id（模型不可能拿到）。"""
        gesture = secrets.token_hex(8)
        with self._lock:
            self._gestures.add(gesture)
        return gesture

    def resolve(self, request_id: str, granted: bool, gesture_id: str = "",
                *, reason: str = "") -> bool:
        """UI 给结论。非法 gesture → 记为拒绝（**不是**错误，是安全行为）。

        ⚠ `reason` 必须区分四件事：用户点了允许（`APPROVED` + gesture）、
        用户点了拒绝（`DENIED`，**不带** gesture）、窗口超时（`TIMEOUT`，由 UI 显式传入）、
        以及"声称允许但手势是伪造的"（`INVALID_GESTURE`，同样**不执行**）。
        以前拒绝也被标成 `approved`，审计日志里"用户拒绝"与"已批准"分不开 —— 事后核查等于失效。
        """
        with self._lock:
            slot = self._pending.get(str(request_id))
            if slot is None:
                logger.warning("审批请求已失效（可能已超时）：%s", request_id)
                return False
            if slot.outcome is not None:
                logger.warning("审批请求已有结论，忽略重复答复：%s", request_id)
                return False
            granted = bool(granted)
            if not granted:
                outcome_reason = TIMEOUT if reason == TIMEOUT else DENIED
            elif gesture_id not in self._gestures:
                granted, outcome_reason = False, INVALID_GESTURE
                logger.error("审批手势无效（疑似伪造），按拒绝处理：%s", request_id)
            else:
                outcome_reason = APPROVED
            if gesture_id in self._gestures:
                self._gestures.discard(gesture_id)       # 一次性
            slot.outcome = ApprovalOutcome(granted, outcome_reason,
                                           gesture_id if granted else "")
        slot.event.set()
        return True

    # ── worker 侧 ─────────────────────────────────────────
    def request(self, request: ApprovalRequest) -> ApprovalOutcome:
        """阻塞等待审批结论（**非主线程**调用）。任何异常路径都返回拒绝。"""
        if not self._ui_attached:
            logger.warning("没有界面可用于审批，按拒绝处理：%s", request.operation)
            return ApprovalOutcome(False, NO_UI)
        slot = _Pending()
        with self._lock:
            self._pending[request.request_id] = slot
        try:
            self.approval_requested.emit(request)
            if not slot.event.wait(timeout=request.timeout_s or self._timeout_s):
                logger.warning("审批超时（%.0fs），按拒绝处理：%s",
                               request.timeout_s, request.operation)
                self._forget(request.request_id)
                return ApprovalOutcome(False, TIMEOUT)
            return slot.outcome or ApprovalOutcome(False, NO_UI)
        finally:
            self._forget(request.request_id)

    def _forget(self, request_id: str) -> None:
        with self._lock:
            self._pending.pop(str(request_id), None)

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    def new_request(self, command: str, operation: str, level: str,
                    **kwargs: object) -> ApprovalRequest:
        """造一条审批请求（`request_id` 由**代码**生成，模型无法预知或伪造）。"""
        return ApprovalRequest(
            request_id=uuid.uuid4().hex,
            command=command, operation=operation, level=level,
            timeout_s=self._timeout_s, **kwargs)


def auto_deny(command: str, operation: str, level: str, reason: str = NO_UI) -> ApprovalOutcome:
    """没有审批入口时用的结论（默认拒绝，**不执行**）。"""
    logger.info("审批不可用（%s），拒绝执行：%s", reason, operation or command[:60])
    return ApprovalOutcome(False, reason)
