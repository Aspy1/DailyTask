"""审批门（H1/P0）：允许 / 拒绝 / 超时 / 伪造手势，以及**离屏弹窗**。

三条必须成立的性质（论文 P5「同机 approval 可被 agent 绕过」的对策）：
1. 没有界面 = **不执行**（不是"默认通过"）；
2. 拒绝 / 超时 / 关窗口 = **不执行**；
3. 审批手势 id 只能由 UI 侧签发，模型自编的 id 一律无效。
"""

import time
from typing import TYPE_CHECKING

from src.services import ai_approval

if TYPE_CHECKING:
    from src.ui.widgets.ai_approval_dialog import ApprovalDialog


def _request(broker: ai_approval.ApprovalBroker) -> ai_approval.ApprovalRequest:
    return broker.new_request(
        'python scripts/actions.py delete_item --id i_001', "delete_item", "high_write",
        object_label="布洛芬", write_target="inventory.json",
        before={"exists": True}, after={"exists": False})


# ── broker：四种结局 ───────────────────────────────────────

def test_no_ui_denies_immediately() -> None:
    """⭐ 没有界面（脚本 / 评估 / 无 UI 单测）→ 立刻拒绝，**不会**卡 120s。"""
    broker = ai_approval.ApprovalBroker(timeout_s=30)
    started = time.monotonic()
    outcome = broker.request(_request(broker))
    assert outcome.granted is False
    assert outcome.reason == ai_approval.NO_UI
    assert time.monotonic() - started < 1.0


def test_approve_returns_the_ui_gesture() -> None:
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()
    seen: list[ai_approval.ApprovalRequest] = []

    def approve(request: ai_approval.ApprovalRequest) -> None:
        seen.append(request)
        broker.resolve(request.request_id, True, broker.issue_gesture())

    broker.approval_requested.connect(approve)
    outcome = broker.request(_request(broker))
    assert outcome.granted is True and outcome.reason == ai_approval.APPROVED
    assert len(outcome.gesture_id) == 16
    assert seen and seen[0].object_label == "布洛芬"
    assert broker.pending == 0


def test_deny_returns_no_gesture() -> None:
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()
    broker.approval_requested.connect(
        lambda request: broker.resolve(request.request_id, False))
    outcome = broker.request(_request(broker))
    assert outcome.granted is False and outcome.reason == ai_approval.DENIED
    assert outcome.gesture_id == ""


def test_deny_is_still_a_denial_when_a_gesture_is_handed_in() -> None:
    """⭐ 「拒绝」就是拒绝 —— 手里有没有 gesture 都不改变结论，而且它会作废。

    审计日志靠 `reason` 区分"用户拒绝"与"已批准"；以前拒绝被标成 `approved`，
    事后核查时分不清这两件事（`denied_by_user` 也永远为假）。
    """
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()

    def deny(request: ai_approval.ApprovalRequest) -> None:
        broker.resolve(request.request_id, False, broker.issue_gesture())

    broker.approval_requested.connect(deny)
    outcome = broker.request(_request(broker))
    assert outcome.granted is False
    assert outcome.reason == ai_approval.DENIED and outcome.denied_by_user
    assert outcome.gesture_id == ""
    assert broker._gestures == set(), "拒绝时交来的 gesture 必须作废（一次性）"


def test_denied_high_risk_action_writes_nothing_and_is_audited(tmp_path) -> None:
    """⭐ 端到端（执行门 + 审计）：审批被拒绝 → **一条命令都不执行**，审计记 `denied`。

    这是 H1/P0 真正要保的性质：不是"弹了框"，而是**没人点允许就没有写入**；
    而且事后能从审计日志看出"是用户拒绝的"，不是"已批准"。
    """
    import json

    from src.services import ai_audit, ai_guard

    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"items": [{"id": "i_001", "name": "布洛芬"}],
                                     "locations": []}), encoding="utf-8")
    log = ai_audit.AuditLog(tmp_path / "ai_actions.jsonl")
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()
    broker.approval_requested.connect(
        lambda request: broker.resolve(request.request_id, False))
    executed: list[str] = []

    def executor(command: str) -> str:      # 真执行器换成探针：被拒绝时它不该被调用
        executed.append(command)
        return "OK delete_item i_001"

    batch = ai_guard.run_batch(
        ['python scripts/actions.py delete_item --id i_001'],
        data_dir=tmp_path, broker=broker, audit=log, request_id="r1", executor=executor)

    assert executed == [], "被拒绝的命令绝不能被执行"
    assert batch.runs[0].executed is False
    assert "i_001" in inventory.read_text(encoding="utf-8"), "清单必须原样不动"
    approvals = [r for r in log.read() if r["kind"] == "approval"]
    assert approvals, "审批结论必须进审计日志"
    assert approvals[0]["granted"] is False
    assert approvals[0]["reason"] == ai_approval.DENIED


def test_timeout_is_a_denial() -> None:
    broker = ai_approval.ApprovalBroker(timeout_s=0.05)
    broker.attach()
    started = time.monotonic()
    outcome = broker.request(_request(broker))
    assert outcome.granted is False and outcome.reason == ai_approval.TIMEOUT
    assert time.monotonic() - started < 3.0


def test_forged_gesture_is_rejected() -> None:
    """⭐ 模型/注入文本自己编一个 gesture id → 无效（只有 UI 能签发）。"""
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()

    def forge(request: ai_approval.ApprovalRequest) -> None:
        broker.resolve(request.request_id, True, "deadbeefdeadbeef")

    broker.approval_requested.connect(forge)
    outcome = broker.request(_request(broker))
    assert outcome.granted is False
    assert outcome.reason == ai_approval.INVALID_GESTURE


def test_gesture_is_single_use() -> None:
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()
    gesture = broker.issue_gesture()

    def reuse(request: ai_approval.ApprovalRequest) -> None:
        broker.resolve(request.request_id, True, gesture)
        broker.resolve(request.request_id, True, gesture)     # 同一个 id 不能再用

    broker.approval_requested.connect(reuse)
    assert broker.request(_request(broker)).granted is True


# ── 离屏弹窗（QDialog 不出屏，直接调出口）──────────────────

def _dialog(qapp, broker=None,
            timeout_s: float = 120.0) -> tuple[ai_approval.ApprovalBroker, "ApprovalDialog"]:
    from src.ui.widgets.ai_approval_dialog import ApprovalDialog

    broker = broker or ai_approval.ApprovalBroker(timeout_s=timeout_s)
    request = _request(broker)
    return broker, ApprovalDialog(request, broker, None, timeout_s)


def test_dialog_shows_command_object_diff_and_target(qapp) -> None:
    """⭐ 用户点按钮之前必须能看到：命令 / 对象 / 改前改后 / 将写文件。"""
    from PySide6.QtWidgets import QLabel

    _broker, dialog = _dialog(qapp)
    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "python scripts/actions.py delete_item --id i_001" in texts
    assert "布洛芬" in texts
    assert "inventory.json" in texts
    assert "exists: True → False" in texts
    assert dialog.windowTitle()


def test_dialog_approve_issues_a_ui_gesture(qapp) -> None:
    broker, dialog = _dialog(qapp)
    seen: list[bool] = []
    dialog.decided.connect(seen.append)
    dialog._on_approve()
    assert seen == [True]
    assert len(dialog.gesture_id) == 16
    assert dialog.gesture_id in broker._gestures        # 由 UI 侧签发


def test_dialog_deny_has_no_gesture(qapp) -> None:
    _broker, dialog = _dialog(qapp)
    seen: list[bool] = []
    dialog.decided.connect(seen.append)
    dialog._on_deny()
    assert seen == [False]
    assert dialog.gesture_id == "" and dialog.timed_out is False


def test_dialog_timeout_counts_as_deny(qapp) -> None:
    _broker, dialog = _dialog(qapp, timeout_s=0.0)
    seen: list[bool] = []
    dialog.decided.connect(seen.append)
    dialog._tick()
    assert seen == [False]
    assert dialog.timed_out is True and dialog.gesture_id == ""


def test_dialog_countdown_text_is_visible(qapp) -> None:
    _broker, dialog = _dialog(qapp, timeout_s=9.0)
    assert "9" in dialog._countdown.text()


def test_prompt_timeout_is_recorded_as_timeout(qapp, monkeypatch) -> None:
    """⭐ 适配器层：弹窗超时不能被记成"用户拒绝"（审计要能区分两者）。"""
    from PySide6.QtWidgets import QDialog

    from src.ui.widgets import ai_approval_dialog

    class _TimeoutDialog:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.gesture_id = ""
            self.timed_out = True

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ai_approval_dialog, "ApprovalDialog", _TimeoutDialog)
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    prompt = ai_approval_dialog.ApprovalPrompt(broker, None)   # attach + connect
    try:
        outcome = broker.request(_request(broker))
    finally:
        prompt.shutdown()
    assert outcome.granted is False
    assert outcome.reason == ai_approval.TIMEOUT
