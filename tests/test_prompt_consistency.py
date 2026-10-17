"""一致性测试：SYSTEM_PROMPT_BASE 宣传的命令必须真的可执行。

防止 "prompt ↔ actions.py 漂移"，**双向**把关：

1. prompt 里让 AI 调用的每条命令，都必须在 actions.py 有内存执行 handler，
   且 CLI（main 的 subparser）里也能调用；
2. 反过来，每个已实现的 handler 也必须出现在 prompt 里 —— 否则 AI 永远
   不会用这条命令（有实现等于没实现）。

历史缺口（现已修复，见 dev-logs/2026-10-16-功能可用性排查.md）：
prompt 曾宣传不存在的 query_weather / query_balance / weather_stats；
delete_item 有 handler 却漏注册 subparser；delete_course / delete_plan / status
有实现但没写进 prompt。
"""

import re
import sys

import pytest

import scripts.actions as actions
from src.services.ai_service import SYSTEM_PROMPT_BASE

ADVERTISED = sorted(set(re.findall(r"scripts/actions\.py\s+([a-z_]+)", SYSTEM_PROMPT_BASE)))

# 23 条已实现的命令（README v0.9.0 + 2026-10-16 记账/备份扩展 + update_course）。
IMPLEMENTED = [
    "add_task", "complete_task", "add_exam", "add_habit", "log_habit",
    "add_plan", "replace_plans", "delete_plan",
    "add_course", "update_course", "delete_course",
    "add_item", "update_item", "delete_item", "need_restock", "lookup_item",
    "status",
    "add_expense", "add_saving", "delete_expense", "expense_summary",
    "list_backups", "restore",
]


def test_prompt_still_advertises_core_commands() -> None:
    assert {"add_task", "add_item", "lookup_item"} <= set(ADVERTISED)


@pytest.mark.parametrize("cmd", ADVERTISED)
def test_advertised_command_is_executable(sandbox, cmd) -> None:
    out = actions.run_in_process(f"python scripts/actions.py {cmd}")
    assert "unknown action" not in out.lower(), out


@pytest.mark.parametrize("cmd", IMPLEMENTED)
def test_cli_subparser_exists(capsys, monkeypatch, sandbox, cmd) -> None:
    monkeypatch.setattr(sys, "argv", ["actions.py", cmd])
    try:
        actions.main()
    except SystemExit:
        # 缺必填参数会 exit(2) 并打印 "required"，这是正常的；
        # 只有 "invalid choice" 才说明 subparser 缺失。
        err = capsys.readouterr().err
        assert "invalid choice" not in err, err


@pytest.mark.parametrize("cmd", IMPLEMENTED)
def test_every_implemented_command_is_advertised(cmd) -> None:
    """有 handler 就必须写进 prompt，否则 AI 无从得知这条命令存在。"""
    assert cmd in ADVERTISED, f"{cmd} 已实现但 AI 提示词未宣传"


def test_implemented_list_matches_handlers() -> None:
    """IMPLEMENTED 常量自身不得漂移（rc：handlers 字典的键）。"""
    from pathlib import Path

    source = Path(actions.__file__).read_text(encoding="utf-8")
    handlers = set(re.findall(r'"([a-z_]+)": cmd_', source))
    assert handlers == set(IMPLEMENTED), handlers ^ set(IMPLEMENTED)


def test_cli_runs_as_subprocess() -> None:
    """提示词宣传的调用形式必须真的能跑：`python scripts/actions.py <命令>`。

    2026-10-16 拆分 actions.py 时踩过：模块内改成 `from scripts.actions_cli import ...`
    后，直接以脚本方式运行会 `ModuleNotFoundError: No module named 'scripts'`
    —— 而 AI 收到的命令正是这个形式（进程内执行器另有路径，测不到这个坑）。
    用只读的 `status`，不碰任何数据。
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(actions.__file__).resolve().parent.parent
    proc = subprocess.run(
        [sys.executable, "scripts/actions.py", "status"],
        cwd=str(root), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-400:]
    assert "tasks=" in proc.stdout, proc.stdout
    assert "ModuleNotFoundError" not in proc.stderr

