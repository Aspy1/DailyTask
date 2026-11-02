"""监督质量评估（H8/P2）：`scripts/ai_oversight_eval.py` 必须可重复、全绿。

它补的是 `scripts/ai_eval.py` 的盲区：只测任务结果不够，还要测
"该拒绝时拒绝、拒绝后没写、撤销挡 stale、注入被挡、伪成功被发现、覆盖如实"。
"""

import pytest

from scripts import ai_oversight_eval


def test_all_oversight_scenarios_pass() -> None:
    results = ai_oversight_eval.evaluate()
    failed = [r for r in results if not r.ok]
    assert not failed, [(r.name, r.detail) for r in failed]
    assert len(results) == len(ai_oversight_eval.SCENARIOS)


def test_every_h8_dimension_has_a_scenario() -> None:
    names = {result.name for result in ai_oversight_eval.evaluate()}
    assert {
        "unauthorized_write",      # 未授权写入
        "approval_bypass",         # 审批绕过 / 伪造 gesture
        "approval_deny",           # 用户拒绝
        "approval_timeout",        # 超时
        "undo_success",            # 撤销成功
        "undo_stale",              # stale 拒绝
        "injection_blocked",       # 注入拦截
        "command_cap",             # 命令上限
        "false_success",           # 伪成功识别
        "field_coverage",          # 字段覆盖
        "audit_redaction",         # 审计可解析 + 脱敏
    } <= names


def test_results_carry_evidence_text() -> None:
    for result in ai_oversight_eval.evaluate():
        assert result.detail, result.name


def test_cli_exits_zero_when_all_pass(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        ai_oversight_eval.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "passed" in out
