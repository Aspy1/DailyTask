"""一致性测试：SYSTEM_PROMPT_BASE 宣传的命令必须真的可执行。

防止 "prompt ↔ actions.py 漂移"：prompt 里让 AI 调用的每条命令，
都必须在 actions.py 有对应的内存执行 handler；有 handler 的命令
也必须在 CLI（main 的 subparser）里能调用。

已知缺口用 xfail 标注（非 strict），修复后会自动变为 XPASS。
"""

import re
import sys

import pytest

import scripts.actions as actions
from src.services.ai_service import SYSTEM_PROMPT_BASE

ADVERTISED = sorted(set(re.findall(r"scripts/actions\.py\s+([a-z_]+)", SYSTEM_PROMPT_BASE)))

# 16 条已实现的命令（README v0.9.0）。
IMPLEMENTED = [
    "add_task", "complete_task", "add_exam", "add_habit", "log_habit",
    "add_plan", "replace_plans", "delete_plan", "add_course", "delete_course",
    "add_item", "update_item", "delete_item", "need_restock", "lookup_item",
    "status",
]

# 缺口 1：prompt 宣传，但 run_in_process 无 handler（AI 调用会静默返回 ERROR）。
KNOWN_MISSING_HANDLERS = {"query_weather", "query_balance", "weather_stats"}

# 缺口 2：有 handler，但 main() 未注册 subparser（`python scripts/actions.py delete_item` 会 argparse 报错）。
KNOWN_MISSING_SUBPARSER = {"delete_item"}


def test_prompt_still_advertises_core_commands():
    assert {"add_task", "add_item", "lookup_item"} <= set(ADVERTISED)


@pytest.mark.parametrize("cmd", ADVERTISED)
def test_advertised_command_is_executable(sandbox, cmd):
    if cmd in KNOWN_MISSING_HANDLERS:
        pytest.xfail(f"'{cmd}' 在 SYSTEM_PROMPT_BASE 中宣传，但 actions.run_in_process 无 handler")
    out = actions.run_in_process(f"python scripts/actions.py {cmd}")
    assert "unknown action" not in out.lower(), out


@pytest.mark.parametrize("cmd", IMPLEMENTED)
def test_cli_subparser_exists(capsys, monkeypatch, sandbox, cmd):
    if cmd in KNOWN_MISSING_SUBPARSER:
        pytest.xfail(f"'{cmd}' 有 handler 但 main() 未注册 subparser")
    monkeypatch.setattr(sys, "argv", ["actions.py", cmd])
    try:
        actions.main()
    except SystemExit:
        # 缺必填参数会 exit(2) 并打印 "required"，这是正常的；
        # 只有 "invalid choice" 才说明 subparser 缺失。
        err = capsys.readouterr().err
        assert "invalid choice" not in err, err
