"""AI 回复里的**命令解析与执行**（从 `ai_service.py` 抽出，2026-10-19）。

为什么单独成模块：`ai_service.py` 顶到单文件 800 行上限 ✗，而这块职责独立
（"从回复文本里抽出命令" + "在内存里执行"），与 worker 的循环/预算/收尾无关 ✓。

⚠ `execute()` 运行在 **AI worker 线程**：**不得触碰 Model、不得 emit 信号** ——
数据重载与通知由主线程的 `AIService._on_response_with_instructions` 负责
（CODE_STANDARDS Q-B2 / Q-B4）。

## 上限是**代码强制**的（H6/P1，2026-11-02）

提示词里"每轮最多一个代码块、最多 8 条命令"以前只是**文案**：模型完全可以给 12 条，
解析器照单全收。现在改成硬上限：

    单轮   ≤ 1 个 ```sh 块 / ≤ 8 条命令
    单请求 ≤ 24 条命令（跨轮累计，由调用方传入 `already`）

超出部分**丢弃**并给出可读的截断报告（`ParseResult.report()`）—— 静默丢弃会让
"AI 说记了 10 条、实际只记 8 条"变成不可解释的差异 ✗。

命令形态用 `ai_policy.parse_shape` **严格匹配**：`cd x && python …`、`sudo …`、
`echo … > file` 都不再被当成可执行命令。
"""

import re
from dataclasses import dataclass, field

from src.services.ai_policy import parse_shape

# 单轮上限（与 `ai_prompts` 里对模型的说法**同一口径**）
MAX_BLOCKS_PER_TURN = 1
MAX_COMMANDS_PER_TURN = 8
# 整个请求的上限（多轮累加）
MAX_COMMANDS_PER_REQUEST = 24

_FENCE_RE = re.compile(r'```(?:sh|bash|shell|console|zsh)\s*\n?(.*?)(?:```|\Z)', re.DOTALL)


@dataclass
class ParseResult:
    """一次解析的**完整结论**（命令 + 为什么少了）。"""

    commands: list[str] = field(default_factory=list)
    blocks: int = 0
    dropped_blocks: int = 0            # 超出"每轮 1 块"而丢弃的块数
    dropped_invalid: list[str] = field(default_factory=list)
    dropped_over_turn: int = 0
    dropped_over_request: int = 0

    @property
    def truncated(self) -> bool:
        """有没有"命令被丢弃"（模型/用户需要知道）。"""
        return bool(self.dropped_blocks or self.dropped_over_turn
                    or self.dropped_over_request)

    def report(self) -> str:
        """截断报告（没有截断 → 空串，不啰嗦）。"""
        bits: list[str] = []
        if self.dropped_blocks:
            bits.append(f"只执行第 1 个代码块（另有 {self.dropped_blocks} 块被忽略）")
        if self.dropped_over_turn:
            bits.append(f"本轮最多 {MAX_COMMANDS_PER_TURN} 条，丢弃 {self.dropped_over_turn} 条")
        if self.dropped_over_request:
            bits.append(f"整次请求最多 {MAX_COMMANDS_PER_REQUEST} 条，"
                        f"丢弃 {self.dropped_over_request} 条")
        if self.dropped_invalid:
            bits.append(f"{len(self.dropped_invalid)} 行不是可执行的 actions.py 命令")
        if not bits:
            return ""
        return "[截断] " + "；".join(bits) + "。没执行的那部分**没有写入**，需要的话分批继续。"

    def invalid_report(self) -> str:
        """被拒的非法行（给模型看，最多 3 条，避免回喂太长的垃圾文本）。"""
        if not self.dropped_invalid:
            return ""
        shown = "\n".join(f"  {line[:120]}" for line in self.dropped_invalid[:3])
        return "[命令被拒] 下面这些不是合法的 `python scripts/actions.py …` 命令，没有执行：\n" + shown


class InstructionParser:
    """Extract and execute shell commands from AI responses."""

    @staticmethod
    def parse(text: str) -> list[str]:
        """只返回**要执行的命令**（上限已生效）。保留旧签名，调用方不必改。"""
        return InstructionParser.parse_result(text).commands

    @staticmethod
    def parse_result(text: str, already: int = 0,
                     per_turn: int = MAX_COMMANDS_PER_TURN,
                     per_request: int = MAX_COMMANDS_PER_REQUEST) -> ParseResult:
        """解析 → `ParseResult`（命令 + 截断/非法明细）。

        - 只认前 `MAX_BLOCKS_PER_TURN` 个代码块（其余整块丢弃并计数）
        - 块内只留形态合法的行（`ai_policy.parse_shape`），非法行单独记账
        - 单轮 ≤ `per_turn`、整请求 ≤ `per_request`（`already` = 本次请求此前已执行条数）
        """
        result = ParseResult()
        blocks = _FENCE_RE.findall(str(text or ""))
        result.blocks = len(blocks)
        used_blocks = blocks[:MAX_BLOCKS_PER_TURN]
        result.dropped_blocks = max(0, len(blocks) - len(used_blocks))

        candidates: list[str] = []
        for block in used_blocks:
            candidates += _lines_of(block, result)

        room_turn = max(0, per_turn)
        room_request = max(0, per_request - max(0, int(already)))
        limit = min(room_turn, room_request)
        result.commands = candidates[:limit]
        if len(candidates) > limit:
            over = len(candidates) - limit
            if room_request <= room_turn:
                result.dropped_over_request = over
            else:
                result.dropped_over_turn = over
        return result

    @staticmethod
    def execute(commands: list[str]) -> list[str]:
        """在**内存中**执行 actions.py 命令，返回每条命令的输出（逐条隔离异常）。"""
        return [InstructionParser.execute_one(cmd) for cmd in commands]

    @staticmethod
    def execute_one(command: str) -> str:
        """执行**一条**命令并返回输出（执行门 `ai_guard` 逐条用它，便于插入审批/快照）。"""
        try:
            from scripts.actions import run_in_process
        except ImportError as e:  # 仅项目结构异常时可能发生
            return f"ERROR 无法加载 scripts/actions.py: {e}"
        try:
            return run_in_process(command)
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            return f"ERROR {e}"


def _lines_of(block: str, result: ParseResult) -> list[str]:
    """一个代码块 → 合法命令行列表（非法行记进 `result.dropped_invalid`）。"""
    out: list[str] = []
    for raw in block.strip().split('\n'):
        line = raw.strip()
        if not line:
            continue
        if "scripts/actions.py" not in line:
            # 块里的非命令行（注释 / 说明）不计数，避免把"没有命令"误报成截断
            if line.startswith("#"):
                continue
            result.dropped_invalid.append(line)
            continue
        if parse_shape(line).ok:
            out.append(line)
        else:
            result.dropped_invalid.append(line)
    return out
