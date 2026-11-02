"""命令上限的**代码强制**（H6/P1）：提示词里的"最多 8 条"不能只是文案。

论文 P1（Q02）的口径：提示词是 model-visible context，不是强制规则。这里验证
解析器自己会截断，并且把"少了多少条"写进可读报告（静默丢命令 = 用户以为写了、实际没写）。
"""

from src.services.ai_instructions import (
    MAX_COMMANDS_PER_REQUEST,
    MAX_COMMANDS_PER_TURN,
    InstructionParser,
    ParseResult,
)


def _cmd(index: int) -> str:
    return f'python scripts/actions.py add_item --name "物品{index}"'


def _block(commands: list[str], lang: str = "sh") -> str:
    return f"```{lang}\n" + "\n".join(commands) + "\n```"


def _parse(text: str, already: int = 0) -> ParseResult:
    return InstructionParser.parse_result(text, already=already)


def test_twelve_commands_are_cut_to_eight() -> None:
    """⭐ 探针 C 的回归：模型给 12 条，只执行前 8 条，并报告丢了 4 条。"""
    parsed = _parse(_block([_cmd(i) for i in range(1, 13)]))
    assert len(parsed.commands) == MAX_COMMANDS_PER_TURN == 8
    assert parsed.dropped_over_turn == 4
    assert parsed.truncated
    report = parsed.report()
    assert "最多 8 条" in report and "丢弃 4 条" in report
    assert "没有写入" in report


def test_only_the_first_code_block_is_used() -> None:
    """每轮只认 1 个块；后面的块整块丢弃（不是把命令合并执行）。"""
    text = "\n".join([
        _block([_cmd(1)]),
        _block([_cmd(2)]),
        _block([_cmd(3)]),
    ])
    parsed = _parse(text)
    assert parsed.commands == [_cmd(1)]
    assert parsed.blocks == 3 and parsed.dropped_blocks == 2
    assert "只执行第 1 个代码块" in parsed.report()


def test_request_wide_cap_counts_commands_already_executed() -> None:
    """整次请求 ≤ 24 条：跨轮累计（`already`）也必须算进去。"""
    parsed = _parse(_block([_cmd(i) for i in range(1, 13)]), already=20)
    assert len(parsed.commands) == 4
    assert parsed.dropped_over_request == 8
    assert f"整次请求最多 {MAX_COMMANDS_PER_REQUEST} 条" in parsed.report()


def test_no_room_left_means_no_commands() -> None:
    parsed = _parse(_block([_cmd(1), _cmd(2)]), already=MAX_COMMANDS_PER_REQUEST)
    assert parsed.commands == []
    assert parsed.dropped_over_request == 2


def test_non_standard_lines_are_rejected_not_executed() -> None:
    """`cd &&` / `sudo` / 管道 都不是本项目的写入入口 → 不进命令列表。"""
    block = _block([
        "cd scripts && python scripts/actions.py status",
        "sudo python scripts/actions.py restore --name x --yes",
        "python scripts/actions.py status | head -3",
        _cmd(1),
    ])
    parsed = _parse(block)
    assert parsed.commands == [_cmd(1)]
    assert len(parsed.dropped_invalid) == 3
    assert "[命令被拒]" in parsed.invalid_report()


def test_comment_lines_do_not_trigger_a_false_truncation_report() -> None:
    block = _block(["# 先看看库存", _cmd(1)])
    parsed = _parse(block)
    assert parsed.commands == [_cmd(1)]
    assert parsed.dropped_invalid == [] and not parsed.truncated


def test_old_parse_api_also_obeys_the_cap() -> None:
    """保留 `parse()` 旧签名，但上限必须一样（不能绕过）。"""
    assert len(InstructionParser.parse(_block([_cmd(i) for i in range(1, 13)]))) == 8
