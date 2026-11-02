"""**执行门**的端到端回归（H1–H5）：策略 → 审批 → 快照 → 执行 → 审计 → 验收。

对应 issue 的四个沙箱探针：
- P-A：`delete_item` 没有审批界面 → 不执行，文件 SHA 不变；
- P-B：`restore --yes` → 策略直接拒绝，文件 SHA 不变；
- P-C：12 条命令 → 只执行 8 条，且截断可见；
- P-D：注入口令不能造成未审批写入（协议层见 `test_ai_injection.py`）。
"""

import hashlib
import json
from collections.abc import Callable

from src.services import ai_approval, ai_audit, ai_guard, ai_undo, ai_verify
from src.services.ai_instructions import InstructionParser


def _seed_inventory(sandbox) -> None:
    (sandbox / "inventory.json").write_text(
        json.dumps({"_version": 1,
                    "items": [{"id": "i_001", "name": "纸巾", "quantity": 1}],
                    "locations": []}, ensure_ascii=False),
        encoding="utf-8")


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _audit(sandbox) -> ai_audit.AuditLog:
    return ai_audit.AuditLog(sandbox / "ai_actions.jsonl")


def _spy(executed: list[str], result: str = "OK stub") -> Callable[[str], str]:
    def executor(command: str) -> str:
        executed.append(command)
        return result
    return executor


DEFINITE_NO_WRITE = 'python scripts/actions.py delete_item --id i_001'
RESTORE = 'python scripts/actions.py restore --name "inventory.json" --yes'


# ── P-A / P-B：没有批准就不能写 ─────────────────────────────

def test_high_write_without_ui_is_blocked_and_sha_unchanged(sandbox) -> None:
    """⭐ P-A：没有审批界面 → `delete_item` 不执行，文件一个字节都不变。"""
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    before = _sha(target)
    executed: list[str] = []
    log = _audit(sandbox)

    batch = ai_guard.run_batch([DEFINITE_NO_WRITE], data_dir=sandbox,
                               audit=log, request_id="p-a", executor=_spy(executed))

    assert executed == []
    assert batch.runs[0].executed is False
    assert "没有可用的审批界面" in batch.runs[0].blocked_reason
    assert _sha(target) == before
    records = log.read()
    assert any(r["kind"] == "action" and r["status"] == "blocked" for r in records)


def test_restore_is_blocked_and_sha_unchanged(sandbox) -> None:
    """⭐ P-B：`restore --yes` 不在 AI 工具集里 → 不执行，文件不变。"""
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    before = _sha(target)
    executed: list[str] = []
    log = _audit(sandbox)

    batch = ai_guard.run_batch([RESTORE], data_dir=sandbox,
                               audit=log, request_id="p-b", executor=_spy(executed))

    assert executed == []
    assert batch.runs[0].executed is False
    assert "仅限用户手动" in batch.runs[0].blocked_reason
    assert _sha(target) == before


def test_denied_approval_blocks_execution_and_is_audited(sandbox) -> None:
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    before = _sha(target)
    executed: list[str] = []
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()
    broker.approval_requested.connect(
        lambda request: broker.resolve(request.request_id, False))
    log = _audit(sandbox)

    batch = ai_guard.run_batch([DEFINITE_NO_WRITE], data_dir=sandbox, broker=broker,
                               audit=log, request_id="deny", executor=_spy(executed))

    assert executed == [] and batch.runs[0].executed is False
    assert "用户拒绝" in batch.runs[0].blocked_reason
    assert _sha(target) == before
    approval = next(r for r in log.read() if r["kind"] == "approval")
    assert approval["granted"] is False and approval["reason"] == ai_approval.DENIED


def test_approval_timeout_blocks_execution(sandbox) -> None:
    """⭐ 超时 = 拒绝（不会卡住 worker，也不会默认放行）。"""
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    before = _sha(target)
    executed: list[str] = []
    broker = ai_approval.ApprovalBroker(timeout_s=0.05)
    broker.attach()
    log = _audit(sandbox)

    batch = ai_guard.run_batch([DEFINITE_NO_WRITE], data_dir=sandbox, broker=broker,
                               audit=log, request_id="timeout", executor=_spy(executed))

    assert executed == [] and batch.runs[0].executed is False
    assert "审批超时" in batch.runs[0].blocked_reason
    assert _sha(target) == before
    approval = next(r for r in log.read() if r["kind"] == "approval")
    assert approval["reason"] == ai_approval.TIMEOUT


def test_forged_gesture_cannot_approve(sandbox) -> None:
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    before = _sha(target)
    executed: list[str] = []
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()

    def forge(request: ai_approval.ApprovalRequest) -> None:
        broker.resolve(request.request_id, True, "deadbeefdeadbeef")

    broker.approval_requested.connect(forge)
    batch = ai_guard.run_batch([DEFINITE_NO_WRITE], data_dir=sandbox, broker=broker,
                               request_id="forge", executor=_spy(executed))

    assert executed == [] and batch.runs[0].executed is False
    assert "审批信号无效" in batch.runs[0].blocked_reason
    assert _sha(target) == before


# ── 允许路径：审批通过才真的写 ─────────────────────────────

def test_approved_high_write_executes_and_is_audited(sandbox) -> None:
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    before = _sha(target)
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()

    def approve(request: ai_approval.ApprovalRequest) -> None:
        broker.resolve(request.request_id, True, broker.issue_gesture())

    broker.approval_requested.connect(approve)
    log = _audit(sandbox)

    def executor(command: str) -> str:
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["items"] = [it for it in payload["items"] if it.get("id") != "i_001"]
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return "OK delete_item i_001"

    batch = ai_guard.run_batch([DEFINITE_NO_WRITE], data_dir=sandbox, broker=broker,
                               audit=log, request_id="allow", executor=executor)

    assert batch.runs[0].executed is True
    assert _sha(target) != before
    assert "i_001" not in target.read_text(encoding="utf-8")
    approval = next(r for r in log.read() if r["kind"] == "approval")
    assert approval["granted"] is True and len(approval["gesture_id"]) == 16
    assert batch.runs[0].verdict.state == ai_verify.VERIFIED


# ── P-C：命令上限 ────────────────────────────────────────────

def test_only_eight_of_twelve_commands_run(sandbox) -> None:
    """⭐ P-C：模型给 12 条 → 解析器留 8 条，执行器也只被调用 8 次。"""
    commands = [f'python scripts/actions.py add_item --name "物品{i}"' for i in range(1, 13)]
    parsed = InstructionParser.parse_result(
        "```sh\n" + "\n".join(commands) + "\n```")
    executed: list[str] = []
    batch = ai_guard.run_batch(parsed.commands, data_dir=None,
                               executor=_spy(executed, "OK add_item"))

    assert len(parsed.commands) == 8 and parsed.dropped_over_turn == 4
    assert len(executed) == 8 == len(batch.runs)
    assert "丢弃 4 条" in parsed.report()


# ── 审计字段：before/after/duration/claim，且备注不进日志 ─────

def test_guard_audits_before_after_duration_and_redacts_notes(sandbox) -> None:
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    log = _audit(sandbox)
    command = ('python scripts/actions.py add_item --name "牙膏" '
               '--notes "我家地址：某路 1 号"')

    def executor(_command: str) -> str:
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["items"].append({"id": "i_002", "name": "牙膏"})
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return "OK add_item i_002"

    ai_guard.run_batch([command], data_dir=sandbox, audit=log,
                       request_id="audit-fields", executor=executor)

    action = next(record for record in log.read() if record["kind"] == "action")
    assert action["before"] != action["after"]
    assert action["duration_ms"] >= 0
    assert "我家地址" not in log.path.read_text(encoding="utf-8")
    assert "--notes ***" in action["command"]


# ── 撤销接线：执行门真的留下了快照 ──────────────────────────

def test_guard_captures_a_snapshot_that_can_be_undone(sandbox) -> None:
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    before = _sha(target)
    store = ai_undo.SnapshotStore.for_data_dir(sandbox)
    assert store is not None

    def executor(command: str) -> str:
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["items"].append({"id": "i_002", "name": "牙膏"})
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return "OK add_item i_002"

    batch = ai_guard.run_batch(
        ['python scripts/actions.py add_item --name "牙膏"'], data_dir=sandbox,
        undo=store, executor=executor)

    assert batch.runs[0].snapshot_id
    assert store.latest() is not None
    ok, detail = store.undo()
    assert ok, detail
    assert _sha(target) == before


def test_guard_snapshot_is_stale_safe(sandbox) -> None:
    """AI 写完后用户又改过 → 撤销拒绝，用户改动保留。"""
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    store = ai_undo.SnapshotStore.for_data_dir(sandbox)
    assert store is not None

    def executor(command: str) -> str:
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["items"].append({"id": "i_002", "name": "牙膏"})
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return "OK add_item i_002"

    ai_guard.run_batch(['python scripts/actions.py add_item --name "牙膏"'],
                       data_dir=sandbox, undo=store, executor=executor)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["items"].append({"id": "i_003", "name": "用户手改"})
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    ok, detail = store.undo()
    assert ok is False and "改过" in detail
    assert "用户手改" in target.read_text(encoding="utf-8")


# ── 真 worker + stub provider（不联网、不用 key）────────────

class _StubProvider:
    """按顺序回放文本；不联网、不需要 API key。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    def chat(self, **_kwargs: object) -> str:
        text = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return text


def _run_worker(sandbox, replies: list[str], **kwargs: object) -> list[str]:
    from src.services.ai_service import AIWorker
    from src.services.data_manager import DataManager

    dm = DataManager(sandbox)
    worker = AIWorker(_StubProvider(replies), "stub", "",
                      [{"role": "user", "content": "x"}], dm, None, **kwargs)
    out: list[str] = []
    worker.finished_with_instructions.connect(lambda text, _instr: out.append(text))
    worker.finished.connect(out.append)
    worker.error.connect(out.append)
    worker.run()
    return out


def test_worker_blocks_delete_when_user_denies(qapp, sandbox) -> None:
    """⭐ stub provider 走完整 worker 路径：用户拒绝 → 数据不变、文本明说未写入。"""
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    before = _sha(target)
    broker = ai_approval.ApprovalBroker(timeout_s=5)
    broker.attach()
    broker.approval_requested.connect(
        lambda request: broker.resolve(request.request_id, False))
    log = _audit(sandbox)

    out = _run_worker(
        sandbox,
        [f"```sh\n{DEFINITE_NO_WRITE}\n```", "没有写入，需要你确认。"],
        approval=broker, audit=log, request_id="worker-deny")

    assert _sha(target) == before
    joined = "\n".join(out)
    assert "用户拒绝" in joined or "未写入" in joined
    assert any(r["kind"] == "approval" and r["granted"] is False for r in log.read())


def test_worker_blocks_restore_command(qapp, sandbox) -> None:
    _seed_inventory(sandbox)
    target = sandbox / "inventory.json"
    before = _sha(target)

    out = _run_worker(
        sandbox,
        [f"```sh\n{RESTORE}\n```", "没有写入。"],
        audit=_audit(sandbox), request_id="worker-restore")

    assert _sha(target) == before
    joined = "\n".join(out)
    assert "仅限用户手动" in joined or "未写入" in joined


def test_worker_audits_claim_without_raw_text(qapp, sandbox) -> None:
    """H9：模型自述只留 claim 指纹 + 代码账本摘要，不把原文写进 JSONL。"""
    log = _audit(sandbox)
    _run_worker(
        sandbox,
        ['```sh\npython scripts/actions.py add_item --name "牙膏" --quantity 2\n```',
         "已记录：我家地址是某路 1 号"],
        audit=log, request_id="claim-audit")

    claim = next(record for record in log.read() if record["kind"] == "claim")
    assert claim["claim_len"] and claim["claim_sha256"]
    assert claim["evidence"]
    assert "我家地址" not in log.path.read_text(encoding="utf-8")


def test_worker_reports_truncation_for_twelve_commands(qapp, sandbox) -> None:
    """⭐ stub provider 真发 12 条命令：只写 8 条，且用户能看到截断说明。"""
    commands = [f'python scripts/actions.py add_item --name "物品{i}"'
                for i in range(1, 13)]
    out = _run_worker(
        sandbox,
        ["```sh\n" + "\n".join(commands) + "\n```", "处理完了。"],
        audit=_audit(sandbox), request_id="worker-cap")

    items = json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))["items"]
    assert len(items) == 8, items
    joined = "\n".join(out)
    assert "[截断]" in joined and "丢弃 4 条" in joined
