"""**执行门**：策略 → 审批 → 快照 → 执行 → 审计 → 验收（H1–H5 的唯一接线处，2026-11-02）。

原来 `AIWorker._run_commands` 是"观察到执行"直连：`observe → execute → verify`，
中间没有任何强制点。现在每一条命令都必须依次过：

    1. `ai_policy.decide`      分级；BLOCKED（含未知操作 / `restore` / 非标准命令形态）→ 不执行
    2. `ai_approval`           HIGH_WRITE → 阻塞等人工审批；拒绝/超时/无界面 → **不写入**
    3. `ai_undo.capture`       写操作执行前留快照（撤销用，模型不可见）
    4. 执行（`InstructionParser.execute`）
    5. `ai_undo.finalize`      记写后指纹（撤销的 stale 判据）
    6. `ai_verify.check_ex`    回读验收 + **字段覆盖**（checked/total）
    7. `ai_audit`              动作 / 审批 / 验收 各一行 JSONL（脱敏）

为什么要单独成模块：`ai_service.py` 已在 800 行上限附近（Q-A1），而这一族逻辑与
"多轮循环 / 预算 / 收尾"无关，可以脱离 Qt 直接测（`tests/test_ai_guard.py`）。

⚠ 本模块**不 emit 信号、不碰 Model**（Q-B2）：它只读数据目录、写审计/快照文件，
并把结果交回 worker 线程；数据重载仍由主线程负责。
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.services import ai_approval, ai_audit, ai_policy, ai_undo, ai_verify
from src.services.ai_ledger import BLOCKED
from src.services.ai_verify import FAILED, UNVERIFIED
from src.services.ai_verify_coverage import Verdict, check_ex, summarize_verdicts

logger = logging.getLogger(__name__)

# 审批框里"这条命令会改什么"的**预测**（按操作给一句人话；没有登记的显示参数原文）
_INTENT: dict[str, str] = {
    "delete_item": "从库存里删除这条物品（不可从界面撤销）",
    "delete_course": "从课表里删除这门课",
    "delete_expense": "删除这条支出记录",
    "delete_plan": "删除这一天的某条日程",
    "replace_plans": "整体替换当天的日程计划",
    "set_locations": "整体替换位置清单",
    "finance_set": "改财务初始值（余额 / 月收入 / 固定支出）",
    "study_set_target": "改考研目标日期 / 每日目标",
}


@dataclass
class CommandRun:
    """一条命令的执行结果（**证据链**：结论 + 是否真的执行 + 原因）。"""

    command: str
    result: str = ""
    verdict: Verdict = field(default_factory=lambda: Verdict(FAILED, ""))
    executed: bool = False
    blocked_reason: str = ""
    approval: ai_approval.ApprovalOutcome | None = None
    label: str = ""
    snapshot_id: str = ""


@dataclass
class BatchResult:
    """一批命令的结果（worker 只用它拼文本 / 记账本）。"""

    runs: list[CommandRun] = field(default_factory=list)

    @property
    def results(self) -> list[str]:
        return [run.result for run in self.runs]

    @property
    def verdicts(self) -> list[Verdict]:
        return [run.verdict for run in self.runs]

    @property
    def labels(self) -> list[str]:
        return [run.label for run in self.runs]

    @property
    def blocked(self) -> list[CommandRun]:
        """没执行的（被策略拒绝 / 审批拒绝 / 超时 / 无界面）。"""
        return [run for run in self.runs if not run.executed]

    def feedback(self) -> str:
        """回喂给模型的文本：逐条回执 + `[验收]`（带覆盖）+ 未执行的原因。"""
        if not self.runs:
            return ""
        lines = [run.result for run in self.runs]
        no_write = [run for run in self.blocked]
        if no_write:
            lines.append("[未写入] 下面这些命令**没有执行**（没有任何数据被修改）：")
            lines += [f"  {run.command[:100]} —— {run.blocked_reason}" for run in no_write[:5]]
        return "\n".join(lines) + summarize_verdicts(self.verdicts)


def describe(command: str, data_dir) -> tuple[str, dict, dict, str, str]:
    """→ `(对象名, 改前, 改后, 将写的文件, 操作名)` —— 审批框要展示的全部事实。"""
    decision = ai_policy.decide(command)
    label = ai_verify.label_of(command, data_dir)
    before = ai_verify.observe(command, data_dir) if data_dir else {}
    _op, args = ai_verify.parse_command(command)
    after = _intent_after(decision.operation, args, before)
    target = ai_undo.target_path(decision.operation, data_dir) if data_dir else None
    return (label, before, after, target.name if target else "", decision.operation)


def _pick(args: dict, keys: tuple[str, ...]) -> dict:
    """只挑命令里**真的传了**的字段（没传的字段不会被改，别在预览里显示）。"""
    return {key: args[key] for key in keys if key in args}


# "改后"预览：操作 → 纯函数（**只用于展示**，不读盘、不作为验收证据）。
_AFTER_PREVIEW = {
    "replace_plans": lambda args: {"plans": f"整体替换（{args.get('plans', '')[:60]}…）"},
    "set_locations": lambda args: {"values": args.get("values", "")},
    "finance_set": lambda args: _pick(args, ("balance", "monthly_income", "fixed_expenses")),
    "study_set_target": lambda args: _pick(args, ("date", "daily_goal")),
}


def _intent_after(operation: str, args: dict, before: dict) -> dict:
    """预测"改后"的状态（只用于**展示**，不作为验收证据 —— 证据来自回读）。"""
    if operation.startswith("delete_") and "exists" in before:
        return {"exists": False}
    preview = _AFTER_PREVIEW.get(operation)
    return preview(args) if preview else {}


def _approve(command: str, decision: ai_policy.Decision, data_dir, broker,
             audit: ai_audit.AuditLog | None, request_id: str) -> ai_approval.ApprovalOutcome:
    """HIGH_WRITE 的审批：没有 broker / 没有界面 → 拒绝（默认不写）。"""
    label, before, after, target, operation = describe(command, data_dir)
    if broker is None:
        outcome = ai_approval.auto_deny(command, operation, decision.level)
        if audit is not None:
            # 没有界面也是一次**审批结论**（= 拒绝）；事后必须能从日志看出原因。
            audit.approval(request_id, command, granted=False, reason=outcome.reason,
                           object=label, write_target=target, before=before, after=after)
        return outcome
    request = broker.new_request(
        command, operation, decision.level,
        object_label=label, write_target=target, before=before, after=after)
    outcome = broker.request(request)
    if audit is not None:
        audit.approval(request_id, command, granted=outcome.granted,
                       reason=outcome.reason, gesture_id=outcome.gesture_id,
                       object=label, write_target=target, before=before, after=after)
    return outcome


def _blocked_run(command: str, reason: str, label: str = "") -> CommandRun:
    return CommandRun(command=command,
                      result=f"ERROR 未执行：{reason}（没有任何数据被修改）",
                      verdict=Verdict(BLOCKED, reason), executed=False,
                      blocked_reason=reason, label=label)


def run_batch(commands: list[str], *, data_dir, broker=None,
              audit: ai_audit.AuditLog | None = None,
              undo: ai_undo.SnapshotStore | None = None,
              request_id: str = "", executor=None) -> BatchResult:
    """逐条过执行门（顺序执行，与原来一致）。`executor(cmd) -> str` 可注入（测试用）。"""
    if executor is None:
        from src.services.ai_instructions import InstructionParser

        executor = InstructionParser.execute_one
    batch = BatchResult()
    for command in commands:
        batch.runs.append(_run_one(command, data_dir=data_dir, broker=broker, audit=audit,
                                   undo=undo, request_id=request_id, executor=executor))
    return batch


def _run_one(command: str, *, data_dir, broker, audit, undo, request_id,
             executor) -> CommandRun:
    decision = ai_policy.decide(command)
    # ⚠ 没有数据目录（脚本 / 单测 / 刚启动）时**也要**取对象名：`label_of` 会退回到
    #   `--name` 这类**命令里本来就有的**参数（不读盘）。否则事实行会变成"记入：未核对" ——
    #   用户看不出是哪件东西（H4：账本必须有对象身份）。
    label = ai_verify.label_of(command, data_dir)
    if not decision.allowed:
        if audit is not None:
            audit.action(request_id, command, operation=decision.operation,
                         level=decision.level, status="blocked", reason=decision.reason)
        return _blocked_run(command, decision.reason, label)

    if decision.requires_approval:
        outcome = _approve(command, decision, data_dir, broker, audit, request_id)
        if not outcome.granted:
            reason = f"未获批准（{_approval_reason(outcome.reason)}）"
            if audit is not None:
                # 审批拒绝也要有**动作级**记录：只写 approval 行会让人误以为"命令没出现过"。
                audit.action(request_id, command, operation=decision.operation,
                             level=decision.level, status="blocked", reason=reason,
                             object=label, write_target=write_target_of(
                                 decision.operation, data_dir))
            return _blocked_run(command, reason + "；需要用户确认后才能执行", label)

    return _execute(command, decision, data_dir=data_dir, audit=audit, undo=undo,
                    request_id=request_id, executor=executor, label=label)


def _record_execution(audit, *, request_id: str, command: str, decision,
                      result: str, before: dict, after: dict, snapshot,
                      verdict: Verdict, duration_ms: float) -> None:
    """动作 + 验收两行审计（before/after/duration/snapshot 一次写全）。"""
    if audit is None:
        return
    audit.action(request_id, command, operation=decision.operation, level=decision.level,
                 status=str(result)[:60], snapshot_id=snapshot.snapshot_id if snapshot else "",
                 before=before, after=after, duration_ms=duration_ms)
    audit.verify(request_id, command, state=verdict.state, detail=verdict.detail,
                 checked=verdict.checked, total=verdict.total)


def _execute(command: str, decision: ai_policy.Decision, *, data_dir, audit, undo,
             request_id, executor, label) -> CommandRun:
    started = time.monotonic()
    before = ai_verify.observe(command, data_dir) if data_dir else {}
    snapshot = None
    if undo is not None and decision.writes:
        snapshot = undo.capture(command, operation=decision.operation,
                                request_id=request_id, label=label)
    result = executor(command)
    if snapshot is not None:
        undo.finalize(snapshot)
    after = ai_verify.observe(command, data_dir) if data_dir and decision.writes else {}
    verdict = check_ex(command, before, result, data_dir) if data_dir else \
        Verdict(FAILED if not str(result).startswith("OK") else UNVERIFIED, str(result)[:80])
    _record_execution(
        audit, request_id=request_id, command=command, decision=decision,
        result=str(result), before=before, after=after, snapshot=snapshot, verdict=verdict,
        duration_ms=round((time.monotonic() - started) * 1000, 1))
    return CommandRun(command=command, result=str(result), verdict=verdict, executed=True,
                      label=label, snapshot_id=snapshot.snapshot_id if snapshot else "")


def _approval_reason(reason: str) -> str:
    """审批结局 → 给用户/模型看的中文（写进回执与审计）。"""
    return {
        ai_approval.DENIED: "用户拒绝",
        ai_approval.TIMEOUT: "审批超时",
        ai_approval.NO_UI: "没有可用的审批界面",
        ai_approval.INVALID_GESTURE: "审批信号无效",
        ai_approval.APPROVED: "已批准",
    }.get(str(reason), str(reason))


def write_target_of(operation: str, data_dir) -> str:
    """这条操作会写的文件（相对名）；跟 `ai_undo.TARGET_FILES` 同一口径。"""
    path = ai_undo.target_path(operation, data_dir) if data_dir else None
    return Path(path).name if path else ""
