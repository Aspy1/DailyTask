"""§14 反模式自查表里**可机械化**的那几条。

来源：`Agent Reliability Engineering Design Guide` §14（"反模式 → 修正"总表）。
那张表 22 条里，本项目**只适用一部分**（重试 / 幂等键 / 子 agent / 审批闸 / 检查点恢复
这些我们没有对应实现 ✗）—— 所以这里只钉住**能用代码检查**的，其余靠人工对照 ✓。

⚠ 这些测试是**源码扫描**（和 `test_ui_review_fixes` 同一手法）：防的是"有人把护栏删了"
✗ —— 不是证明护栏写对了（那是各功能自己的测试管的 ✓）。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_self_reported_success_does_not_close_the_task() -> None:
    """§2.3 / §14「自我汇报决定成败」→ 完成判定必须来自**命令自己的结果**。

    反例（修掉之前的写法）：只看模型有没有"说"已记录 ✗。
    """
    service = _src("src/services/ai_service.py")
    guards = _src("src/services/ai_loop_guards.py")
    assert "_split_results" in service, "要按命令的 OK/ERROR 分成功与失败"
    assert "startswith(\"OK\")" in service or "startswith('OK')" in service
    assert "def _has_write_cmd" in guards, "要能区分写命令与只读命令"


def test_partial_completion_is_reported() -> None:
    """§2.2 / §9.3 / §14「部分完成当完整呈现」→ 被切断要说清"执行了几条、成了几条"。"""
    service = _src("src/services/ai_service.py")
    assert "可能没记全" in service, "轮次/时限切断要上报"
    assert "条写命令没有生效" in service, "失败要**量化**（N/M），不是散文"


def test_prompt_is_not_the_only_enforcement_point() -> None:
    """§6.3 / §14「安全规则写在提示词里」→ 写数据的强制点必须在**代码边界**。"""
    items = _src("scripts/actions_cmds_items.py")
    assert "已有同名同位置且无区别的物品" in items, "重复写入要有硬护栏（拒绝）"


def test_both_budgets_are_explicit() -> None:
    """§3.3 / §14「拿框架默认当预算」→ **轮次 + 墙钟**都要显式设，别用默认。"""
    service = _src("src/services/ai_service.py")
    assert "for turn in range(" in service, "轮次预算"
    assert "_max_seconds" in service and "max_seconds" in service, "墙钟预算"


def test_a_counter_is_not_the_only_loop_detector() -> None:
    """§4 / §14「拿计数器当循环检测」→ 要有**重复检测**（告知 → 收束）。"""
    guards = _src("src/services/ai_loop_guards.py")
    assert "def repeat_nudge" in guards, "同一批命令重复要能被发现"
    assert "def cmds_key" in guards, "要有稳定的命令指纹"
