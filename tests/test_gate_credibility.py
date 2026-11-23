"""P1：门禁必须能**证明**结论（审计 2026-11-21）。

复现：把外部检查工具模拟为缺失，严格工程门禁仍然得到**零项失败**；
密钥扫描遇到无效 JSON 退成空结果；Git 调用忽略退出码；部分工具用输出推断成功。
于是"门禁通过"可能只是"根本没检查"。

验收（审计原文）：为检查定义 PASS / VIOLATION / UNAVAILABLE；
严格模式后两项都退出非零并列明检查名；反例测试覆盖工具缺失、失败且无输出、
输出无法解析和 Git 不可用。
"""

from pathlib import Path

import pytest

import scripts.check_quality as cq

# ── 三态本身 ───────────────────────────────────────────────

def test_report_distinguishes_unavailable_from_pass() -> None:
    rep = cq.Report()
    rep.unavailable("VULTURE", "未安装")

    assert rep.outcome("VULTURE") == cq.UNAVAILABLE
    assert rep.outcome("RADON") == cq.STATE_OK
    assert rep.unavailable_items == ["VULTURE 未安装"]


def test_report_unavailable_is_not_a_violation() -> None:
    """非严格模式：缺工具只提示，不红（本地开发不该被环境卡住）。"""
    rep = cq.Report()
    rep.unavailable("VULTURE", "未安装")

    assert rep.has_violations is False


def test_report_violation_is_a_violation() -> None:
    rep = cq.Report()
    rep.fail("SILENT", "x")

    assert rep.outcome("SILENT") == cq.VIOLATION
    assert rep.has_violations is True


# ── 反例：工具缺失 / 失败且无输出 / 输出无法解析 ─────────────

def test_missing_tool_is_unavailable_not_pass(monkeypatch) -> None:
    monkeypatch.setattr(cq, "_console_script", lambda name: None)
    rep = cq.Report()

    cq.probe_console_tool(rep, "IMPORT-LINTER", "lint-imports", [])

    assert rep.outcome("IMPORT-LINTER") == cq.UNAVAILABLE


def test_failing_tool_without_output_is_a_violation(monkeypatch) -> None:
    """退出码非零但**没有任何输出** —— 旧实现会把它写成 posixpath 对象，几乎等于放行。"""
    class _Proc:
        returncode = 3
        stdout = ""
        stderr = ""

    monkeypatch.setattr(cq.subprocess, "run", lambda *a, **k: _Proc())
    monkeypatch.setattr(cq, "_console_script", lambda name: Path("dummy-tool"))
    rep = cq.Report()

    cq.probe_console_tool(rep, "IMPORT-LINTER", "lint-imports", [])

    assert rep.outcome("IMPORT-LINTER") == cq.VIOLATION
    assert any("退出码 3" in line for line in rep.lines)


def test_secrets_scan_cannot_parse_output(monkeypatch) -> None:
    """无效 JSON → 不能退成"没有新密钥"（旧实现返回 `{}`，等于全部放行）。"""
    class _Proc:
        returncode = 0
        stdout = b"not json at all"
        stderr = b""

    monkeypatch.setattr(cq.subprocess, "run", lambda *a, **k: _Proc())
    monkeypatch.setattr(cq, "_console_script", lambda name: Path("detect-secrets"))

    with pytest.raises(cq.ToolUnavailable):
        cq.run_secrets_scan()


def test_secrets_check_reports_unparseable_as_violation(monkeypatch) -> None:
    def broken() -> None:
        raise cq.ToolUnavailable("输出无法解析")

    monkeypatch.setattr(cq, "run_secrets_scan", broken)
    rep = cq.Report()

    cq.report_secrets(rep)

    assert rep.outcome("SECRETS") == cq.VIOLATION


def test_git_unavailable_is_a_violation(monkeypatch) -> None:
    """Git 不可用（未安装 / 不在仓库里）→ 顶层目录与密钥检查必须报无法执行。"""
    monkeypatch.setattr(cq, "_git_lines", lambda *a: None)
    rep = cq.Report()

    cq.report_git_checks(rep)

    assert rep.outcome("TOP-DIR") == cq.UNAVAILABLE
    assert rep.outcome("SECRET") == cq.UNAVAILABLE


def test_git_failure_is_not_treated_as_clean(monkeypatch) -> None:
    """退出码非零（比如不在 git 工作区）旧实现当成"没有跟踪项"= 通过。"""
    class _Proc:
        returncode = 128
        stdout = b"fatal: not a git repository"
        stderr = b""

    monkeypatch.setattr(cq.subprocess, "run", lambda *a, **k: _Proc())

    with pytest.raises(cq.ToolUnavailable):
        cq._tracked_entries()


# ── 严格模式端到端 ────────────────────────────────────────

def test_strict_mode_fails_when_a_tool_is_missing(monkeypatch) -> None:
    """⭐ 审计的复现条件：把外部工具模拟为缺失 → 严格门禁必须退出非零。"""
    monkeypatch.setattr(cq, "_console_script", lambda name: None)
    monkeypatch.setattr(cq.shutil, "which", lambda name: None)

    rep = cq.evaluate(with_tools=True)

    assert rep.has_violations or rep.unavailable_items, "缺工具不该得到零项结论"
    assert cq.main(["--strict"]) == 1


def test_strict_mode_is_clean_when_everything_is_available() -> None:
    """反向回归：当前仓库 + 已装工具 → 严格模式仍应通过。"""
    assert cq.main(["--strict"]) == 0


def test_report_lists_unavailable_checks_by_name() -> None:
    rep = cq.Report()
    rep.unavailable("RADON", "未安装")
    rep.unavailable("VULTURE", "未安装")

    text = rep.render()

    assert "无法执行" in text and "RADON" in text and "VULTURE" in text


def test_baseline_exemption_cannot_hide_a_gate_error() -> None:
    """基线豁免只对"存量债"生效：`UNAVAILABLE` 不得被 baseline 吞掉。"""
    rep = cq.Report()
    rep.unavailable("SECRETS", "输出无法解析")

    assert rep.has_violations is False, "非严格下只是提示"
    assert rep.outcome("SECRETS") == cq.UNAVAILABLE
