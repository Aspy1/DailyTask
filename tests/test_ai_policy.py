"""AI 动作**权限分级**的回归（H1/H2/P0，2026-11-02）。

判据来自论文映射（`docs/ai-harness-audit/findings.csv` H1/H2）：
- 权限判定必须在**模型之外**，且默认拒绝；
- `restore` 这种"把整份文件盖回去"的动作不能留在 AI 的工具集里；
- 未知操作 = 拒绝（不是"试试看"）。
"""

import pytest

import scripts.actions as actions
from src.services import ai_policy


def _cmd(action: str) -> str:
    return f"python scripts/actions.py {action}"


def test_read_commands_do_not_need_approval() -> None:
    for action in ("status", "lookup_item", "need_restock", "expense_summary"):
        decision = ai_policy.decide(_cmd(action))
        assert decision.level == ai_policy.READ, action
        assert decision.allowed and not decision.requires_approval


def test_low_write_runs_without_approval_but_is_a_write() -> None:
    decision = ai_policy.decide(_cmd("add_item") + ' --name "抽纸" --quantity 2')
    assert decision.level == ai_policy.LOW_WRITE
    assert decision.allowed and decision.writes and not decision.requires_approval


@pytest.mark.parametrize("action", [
    "delete_item --id i_001",
    "delete_course --id c_001",
    "delete_expense --id e_001",
    "delete_plan --date 2026-11-02 --index 0",
    'replace_plans --date 2026-11-02 --plans \'[{"title":"x"}]\'',
    'set_locations --values "书架1"',
    "finance_set --balance 5000",
    "study_set_target --date 2027-12-25",
])
def test_high_risk_actions_need_human_approval(action: str) -> None:
    decision = ai_policy.decide(_cmd(action))
    assert decision.level == ai_policy.HIGH_WRITE, action
    assert decision.requires_approval and decision.allowed


@pytest.mark.parametrize("command", [
    'python scripts/actions.py restore --name "inventory.json" --yes',
    "python scripts/actions.py definitely_not_a_command --x 1",
    'python scripts/actions.py rm -rf data',
])
def test_restore_and_unknown_are_blocked(command: str) -> None:
    """⭐ `restore` 与**未知操作**都不许 AI 执行（未知 = 默认拒绝）。"""
    decision = ai_policy.decide(command)
    assert decision.level == ai_policy.BLOCKED
    assert not decision.allowed and not decision.requires_approval


def test_restore_is_not_ai_callable() -> None:
    assert ai_policy.is_ai_callable("restore") is False
    assert ai_policy.is_ai_callable("add_item") is True
    assert ai_policy.is_ai_callable("no_such_action") is False


@pytest.mark.parametrize("command", [
    "cd scripts && python scripts/actions.py status",
    "sudo python scripts/actions.py status",
    'echo "python scripts/actions.py status" > x.txt',
    "python scripts/other.py status",
    "./scripts/actions.py status",
    "python scripts/actions.py status | head -3",
    "python scripts/actions.py status; rm -rf data",
])
def test_non_standard_command_shapes_are_blocked(command: str) -> None:
    """⭐ 只认 `python scripts/actions.py <动作>`；别的形态不是本项目的写入入口。"""
    assert ai_policy.classify(command) == ai_policy.BLOCKED


def test_quoted_gt_is_not_shell_syntax() -> None:
    """引号里的 `>` 是**数据**（`--note "5 > 3"`），不能因此判成 shell 语法。"""
    decision = ai_policy.decide('python scripts/actions.py add_expense --amount 5 --note "5 > 3"')
    assert decision.level == ai_policy.LOW_WRITE


def test_every_handler_is_classified() -> None:
    """⭐ 新增写命令必须登记级别；漏登记 = BLOCKED（安全方向），但这里要求**显式**。"""
    unclassified = sorted(set(actions.HANDLERS) - set(ai_policy.OP_LEVEL))
    assert not unclassified, f"这些命令没有权限级别：{unclassified}"


def test_policy_table_has_all_levels() -> None:
    table = ai_policy.policy_table()
    assert table[ai_policy.READ] and table[ai_policy.LOW_WRITE]
    assert table[ai_policy.HIGH_WRITE] and table[ai_policy.BLOCKED] == ("restore",)


def test_audit_and_undo_are_not_ai_commands() -> None:
    """审计与撤销是**监督设施** —— 不能被模型当成工具调用（H3/H4 的边界）。"""
    from src.services import ai_prompts

    for name in ("undo", "audit", "ai_undo", "ai_audit"):
        assert name not in actions.HANDLERS, name
    assert "scripts/actions.py restore" not in ai_prompts.SYSTEM_PROMPT_BASE
    assert "scripts/actions.py undo" not in ai_prompts.SYSTEM_PROMPT_BASE
