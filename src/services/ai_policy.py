"""AI 动作的**权限分级**（H1/H2/P0 的代码强制点，2026-11-02）。

为什么需要：项目原来把「读数据」和「删数据」放在**同一条执行路径**上，模型输出什么就执行什么；
`restore --yes` 的"确认信号"可以由**同机的任何进程**（包括模型自己）拼出来，等于没有确认。
论文侧的口径（`docs/ai-harness-audit/findings.csv` H1/H2）只说了一件事：**权限判定必须在
模型之外**，而且默认应当是"拒绝"。

本模块只做**判定**（纯函数，无 Qt、无 IO）：

    READ        只读，直接执行
    LOW_WRITE   可撤销的低风险写入，直接执行（执行前留快照，见 `ai_undo`）
    HIGH_WRITE  高风险写入，**必须**经人工审批（见 `ai_approval`），拒绝/超时 = 不写
    BLOCKED     不允许由 AI 执行（含**未知操作** —— 未知一律失败关闭）

⚠ 判定用**严格命令形态**（`python scripts/actions.py <动作>`）：模型偶尔会写
`cd x && python …` / `sudo …` / `cat > file`，那些不是本项目的写入入口，一律 `BLOCKED`。
命令形态的**唯一**解析处在本模块（`parse_shape`），解析器与执行门共用它。

⚠ 新增写命令时**必须**在这里登记级别；漏登记 = `BLOCKED`（安全的方向），
`tests/test_ai_policy.py::test_every_handler_is_classified` 会红着提醒你补。
"""

import re
from dataclasses import dataclass

READ = "read"
LOW_WRITE = "low_write"
HIGH_WRITE = "high_write"
BLOCKED = "blocked"

LEVELS = (READ, LOW_WRITE, HIGH_WRITE, BLOCKED)

# 只读：不改任何文件
_READ_OPS = frozenset({
    "status", "lookup_item", "need_restock",
    "expense_summary", "finance_summary",
    "list_backups", "list_mistakes", "study_summary",
})

# 高风险：删除 / 整段覆盖 / 金额与目标设定 —— 见 `ai_approval`
_HIGH_OPS = frozenset({
    "delete_item", "delete_course", "delete_expense", "delete_plan",
    "replace_plans", "set_locations",
    "finance_set", "study_set_target",
})

# 明确禁止 AI 调用的操作（**保留给用户手动**的恢复入口）
_FORBIDDEN_OPS = frozenset({"restore"})

# 可撤销的低风险写入
_LOW_OPS = frozenset({
    "add_task", "complete_task", "add_exam", "add_habit", "log_habit",
    "add_plan", "complete_plan", "add_course", "update_course",
    "add_item", "update_item", "consume", "add_location",
    "add_expense", "add_saving",
    "log_study", "add_mistake", "review_mistake", "master_mistake", "add_mock",
})

OP_LEVEL: dict[str, str] = {
    **dict.fromkeys(_READ_OPS, READ),
    **dict.fromkeys(_LOW_OPS, LOW_WRITE),
    **dict.fromkeys(_HIGH_OPS, HIGH_WRITE),
    **dict.fromkeys(_FORBIDDEN_OPS, BLOCKED),
}

# 严格命令形态：`python[3] scripts/actions.py <动作> [--k v]…`
_SHAPE_RE = re.compile(r"^python3?\s+scripts/actions\.py\s+([a-z][a-z0-9_]*)(?=\s|$)")
# 只在这些字符**不在引号内**时算 shell 语法（值里出现 `>` 不该被误杀）
_META_CHARS = frozenset("|;&<>`")
_FORBIDDEN_LEADS = ("sudo", "bash", "sh", "cmd", "powershell", "rm", "cat", "echo",
                    "curl", "wget", "python3 -c", "python -c")


@dataclass(frozen=True)
class CommandShape:
    """一条命令文本的**形态判定**结果（`reason` 为空 = 形态合法）。"""

    operation: str
    reason: str = ""

    @property
    def ok(self) -> bool:
        return not self.reason


@dataclass(frozen=True)
class Decision:
    """一条命令的权限判定（给执行门用）。"""

    command: str
    operation: str
    level: str
    reason: str = ""

    @property
    def requires_approval(self) -> bool:
        return self.level == HIGH_WRITE

    @property
    def allowed(self) -> bool:
        return self.level in (READ, LOW_WRITE, HIGH_WRITE)

    @property
    def writes(self) -> bool:
        return self.level in (LOW_WRITE, HIGH_WRITE)


def _has_shell_meta(line: str) -> bool:
    """引号外的 shell 元字符（`|` `;` `&` `<` `>` 反引号）—— 模型不该写这些。"""
    quote = ""
    for ch in line:
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in "'\"":
            quote = ch
        elif ch in _META_CHARS:
            return True
    return False


def parse_shape(line: str) -> CommandShape:
    """严格解析一行命令 → `(操作名, 不合法原因)`。

    `reason` 非空则**不可执行**；解析器用 `ok` 过滤，策略层用 `operation` 分级。
    """
    text = str(line or "").strip()
    if not text:
        return CommandShape("", "空命令")
    match = _SHAPE_RE.match(text)
    if match is None:
        lowered = text.lower()
        if any(lowered.startswith(lead) for lead in _FORBIDDEN_LEADS):
            return CommandShape("", "只接受 `python scripts/actions.py <动作>` 形式")
        return CommandShape("", "不是 `python scripts/actions.py <动作>` 形式")
    if _has_shell_meta(text):
        return CommandShape(match.group(1), "命令里不允许 shell 语法（| ; & < > `）")
    return CommandShape(match.group(1))


def operation_of(command: str) -> str:
    """提取动作名（形态不合法时返回空串）—— 不做策略判定。"""
    return parse_shape(command).operation


def classify(command: str) -> str:
    """一条命令的权限级别。形态错误 / 未知操作 / 禁止操作 → `BLOCKED`。"""
    return decide(command).level


def decide(command: str) -> Decision:
    """完整判定：级别 + 原因（原因会进审计日志与模型回执）。"""
    shape = parse_shape(command)
    if not shape.ok:
        return Decision(str(command or ""), "", BLOCKED, shape.reason)
    level = OP_LEVEL.get(shape.operation)
    if level is None:
        return Decision(str(command or ""), shape.operation, BLOCKED,
                        f"未知操作 {shape.operation}（默认拒绝）")
    if level == BLOCKED:
        return Decision(str(command or ""), shape.operation, BLOCKED,
                        f"{shape.operation} 不由 AI 执行（仅限用户手动）")
    return Decision(str(command or ""), shape.operation, level)


def requires_approval(command: str) -> bool:
    """这条命令是否必须先经人工审批。"""
    return decide(command).requires_approval


def is_ai_callable(operation: str) -> bool:
    """AI 是否允许调用该操作（`restore` 与未知操作 → False）。"""
    return OP_LEVEL.get(str(operation or ""), BLOCKED) != BLOCKED


def policy_table() -> dict[str, tuple[str, ...]]:
    """级别 → 操作名（文档 / 测试用）。"""
    out: dict[str, list[str]] = {level: [] for level in LEVELS}
    for op, level in sorted(OP_LEVEL.items()):
        out[level].append(op)
    return {level: tuple(ops) for level, ops in out.items()}
