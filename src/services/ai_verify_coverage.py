"""验收的**覆盖度**（`checked/total` 字段）—— 从 `ai_verify.py` 分出（单文件 ≤800 行，Q-A1）。

为什么需要（H5/P1，2026-11-02）：`add_item` 只核对"清单里有没有这个名字"，
`replace_plans` 只比对标题 —— 但界面上统一显示"验收通过"，用户会理解成
"这条命令的效果**全部**核对过了"✗。覆盖度把结论拆成两半：

    checked = 验收器**真的比对过**的字段数
    total   = 这条命令**会改到**的字段数

于是界面能照实说「验收通过（1/2 字段）」或「未核对（0/1 字段）」，
而不是笼统的「验收通过」（审查 H5：covered ≠ verified）。

三张表：
- `_EFFECT_FIELDS`   命令会改到的字段（按参数名；只有命令里真传了才算分母）
- `_IMPLICIT_FIELDS` 没有参数名但一定会变的状态（完成 / 删除 / 打卡…）
- `_VERIFIED_FIELDS` 验收器真的比对过的字段（分子）—— 改验收器时必须同步改这里

没登记的操作 → 分母 0 → **不显示**覆盖（不假装核对过，也不假装有分母）。
"""

import json
from dataclasses import dataclass
from pathlib import Path

from src.services.ai_verify import (
    _CHECKS,
    FAILED,
    MISMATCH,
    NOOP,
    PLAN_FIELDS,
    UNVERIFIED,
    VERIFIED,
    check,
    parse_command,
)

_EFFECT_FIELDS: dict[str, tuple[str, ...]] = {
    "add_item": ("name", "category", "quantity", "unit", "location", "tags", "notes",
                 "min_qty", "doses_per_unit", "min_doses", "instances", "membership",
                 "billing_type", "amount", "due_day", "installments", "runs_out_months",
                 "stock_target", "expires", "remind_before"),
    "update_item": ("name", "group", "category", "quantity", "status", "unit",
                    "location", "tags", "notes", "min_qty", "min_doses",
                    "doses_per_unit", "instances", "membership", "billing_type",
                    "amount", "due_day", "installments", "runs_out",
                    "runs_out_months", "stock_target", "expires", "remind_before",
                    "worn_days", "needs_wash"),
    "consume": ("amount",),
    "add_task": ("title", "due", "course", "priority", "tags", "notes"),
    "add_course": ("name", "day", "weeks", "slots", "location", "teacher", "parity"),
    "update_course": ("name", "day", "weeks", "slots", "location", "teacher", "parity"),
    "add_exam": ("course", "date", "scope", "location", "notes", "tags"),
    "add_habit": ("name", "schedule", "duration", "reminder"),
    "add_plan": ("title", "slot", "type", "note", "course"),
    "replace_plans": PLAN_FIELDS,
    "add_expense": ("amount", "category", "note", "date"),
    "add_saving": ("amount", "note"),
    "finance_set": ("balance", "monthly_income", "fixed_expenses"),
    "add_location": ("name",),
    "set_locations": ("values",),
    # 考研备考
    "log_study": ("subject", "minutes", "date", "note"),
    "add_mistake": ("subject", "topic", "question", "answer"),
    "add_mock": ("subject", "score", "full_score", "duration", "date"),
    "study_set_target": ("date", "daily_goal"),
}

_IMPLICIT_FIELDS: dict[str, tuple[str, ...]] = {
    "complete_task": ("status",),
    "complete_plan": ("done",),
    "log_habit": ("completed",),
    "delete_item": ("exists",),
    "delete_course": ("exists",),
    "delete_expense": ("exists",),
    "delete_plan": ("titles",),
    "review_mistake": ("stage",),
    "master_mistake": ("mastered",),
}

_VERIFIED_FIELDS: dict[str, tuple[str, ...]] = {
    "add_item": ("name",),
    "update_item": ("name", "group", "category", "quantity", "status",
                      "unit", "location", "tags", "notes", "min_qty",
                      "min_doses", "doses_per_unit", "instances", "membership",
                      "billing_type", "amount", "due_day", "installments",
                      "runs_out", "runs_out_months", "stock_target", "expires",
                      "remind_before", "worn_days", "needs_wash"),
    "consume": ("amount",),
    "add_task": ("title",),
    "complete_task": ("status",),
    "add_course": ("name",),
    "update_course": ("name", "day", "weeks", "slots", "location", "teacher", "parity"),
    "delete_course": ("exists",),
    "add_exam": ("course", "date"),
    "add_habit": ("name",),
    "log_habit": ("completed",),
    "add_plan": ("title",),
    "replace_plans": PLAN_FIELDS,
    "complete_plan": ("done",),
    "delete_plan": ("titles",),
    "delete_item": ("exists",),
    "delete_expense": ("exists",),
    "add_expense": ("amount", "date"),
    "add_saving": ("amount",),
    "finance_set": ("balance", "monthly_income", "fixed_expenses"),
    "add_location": ("name",),
    "set_locations": ("values",),
    # 考研备考
    "log_study": ("subject", "minutes"),
    "add_mistake": ("subject", "topic"),
    "add_mock": ("subject", "score"),
    "review_mistake": ("stage",),
    "master_mistake": ("mastered",),
    "study_set_target": ("date", "daily_goal"),
}
_IGNORED_EMPTY_UPDATE_FIELDS = frozenset({
    "name", "category", "status", "unit", "location",
    "runs_out", "expires", "membership", "billing_type",
})


@dataclass(frozen=True)
class Verdict:
    """一条验收结论 **+ 覆盖**（`checked/total` = 核对到的字段 / 会改到的字段）。"""

    state: str
    detail: str
    checked: int = 0
    total: int = 0
    fields: tuple[str, ...] = ()

    @property
    def partial(self) -> bool:
        """核对得不全（有分母、分子更小）—— 界面**必须**照实说。"""
        return self.total > 0 and self.checked < self.total

    @property
    def resolves(self) -> bool:
        """目标状态是否成立（verified / 本来已满足）。"""
        return self.state in (VERIFIED, NOOP)

    def coverage_text(self) -> str:
        """`（1/2 字段）`；没有分母时返回空串（不添噪）。"""
        if self.total <= 0:
            return ""
        return f"（{self.checked}/{self.total} 字段）"

    def as_text(self) -> str:
        """给模型看的一句话：状态 + 说明 + 覆盖。"""
        return f"{self.state}: {self.detail}{self.coverage_text()}"

    def render(self) -> str:
        """**界面口径**：不再一律写「验收通过」（H5）。"""
        from src.services.ai_ledger import STATE_LABEL

        label = STATE_LABEL.get(self.state, self.state)
        if self.state == VERIFIED and self.partial:
            return f"{label}，但只核对了 {self.checked}/{self.total} 字段：{self.detail}"
        if self.state == VERIFIED:
            return f"{label}{self.coverage_text()}：{self.detail}"
        if self.state == UNVERIFIED:
            return f"未核对{self.coverage_text()}：{self.detail or '这条命令没有验收器'}"
        return f"{label}：{self.detail}"


def _plans_payload_fields(raw: str) -> set[str]:
    """`--plans` JSON 里**实际出现**的字段（title/time_slot/note…），去重。"""
    try:
        plans = json.loads(str(raw or "[]"))
    except (TypeError, ValueError):
        return set()
    if not isinstance(plans, list):
        return set()
    fields: set[str] = set()
    for plan in plans:
        if isinstance(plan, dict):
            fields |= set(plan) & set(PLAN_FIELDS)
    return fields


def coverage_of(operation: str, args: dict) -> tuple[int, int, tuple[str, ...]]:
    """`(已核对字段数, 会改到的字段数, 已核对字段名)` —— 纯查表，不读数据。"""
    if operation == "replace_plans":
        # `--plans` 是 JSON：分母是载荷里实际出现的子字段，不是一个笼统的 "plans"。
        fields = _plans_payload_fields((args or {}).get("plans", ""))
        if operation not in _CHECKS or not fields:
            return 0, len(fields), ()
        checked = tuple(sorted(fields & set(_VERIFIED_FIELDS.get(operation, ()))))
        return len(checked), len(fields), checked
    total = _effect_fields(operation, args)
    if operation not in _CHECKS or not total:
        return 0, len(total), ()
    checked = tuple(sorted(set(_VERIFIED_FIELDS.get(operation, ())) & total))
    return len(checked), len(total), checked


def _effect_fields(operation: str, args: dict) -> set[str]:
    supplied = args or {}
    fields = {field for field in _EFFECT_FIELDS.get(operation, ()) if field in supplied}
    if operation == "update_item":
        fields = {field for field in fields
                  if field not in _IGNORED_EMPTY_UPDATE_FIELDS or supplied[field]}
    return fields | set(_IMPLICIT_FIELDS.get(operation, ()))


def check_ex(command: str, before: dict, result: str, data_dir: Path) -> Verdict:
    """`ai_verify.check()` 的**带覆盖**版本（执行门 / 账本用；旧签名保持不变）。

    ⚠ `unverified` 的 checked **必须是 0**：没核对就别说"核对了 1 个字段"。
    """
    operation, args = parse_command(command)
    state, detail = check(command, before, result, data_dir)
    checked, total, fields = coverage_of(operation, args)
    if state == UNVERIFIED:
        return Verdict(state, detail, 0, total, ())
    return Verdict(state, detail, checked, total, fields)


def summarize_verdicts(verdicts: list[Verdict]) -> str:
    """一批结论拼成给模型看的一段（带 `checked/total`，格式与 `ai_verify.summarize` 一致）。"""
    if not verdicts:
        return ""
    return "\n[验收]\n" + "\n".join(f"  {v.as_text()}" for v in verdicts)


# 状态常量在这里也导出，方便调用方只 import 本模块
__all__ = ["FAILED", "MISMATCH", "NOOP", "UNVERIFIED", "VERIFIED",
           "Verdict", "check_ex", "coverage_of", "summarize_verdicts"]
