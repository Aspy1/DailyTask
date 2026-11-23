"""审计 P1：本地入口与 CI **同一组**命令、同样的参数。

复现（静态审查）：CI 的 push 分支过滤为 master（开发在 dev），
规范声称的覆盖率阈值也没出现在实际 pytest 命令里 —— "本地全绿"证明不了 CI 全绿。
"""

import re
from pathlib import Path

import pytest

import scripts.ci_local as local

CI_YML = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> str:
    return CI_YML.read_text(encoding="utf-8")


def test_ci_covers_the_delivery_branches(workflow: str) -> None:
    """⭐ push 过滤必须覆盖实际交付分支（审计原文："覆盖实际交付分支"）。"""
    match = re.search(r"on:\s*\n\s*push:\s*\n\s*branches:\s*\[([^\]]+)\]", workflow)
    assert match, "找不到 push.branches 过滤"
    branches = {item.strip() for item in match.group(1).split(",")}
    assert {"master", "dev"} <= branches, branches


def test_ci_enforces_the_coverage_floor(workflow: str) -> None:
    """覆盖率下限必须出现在**实际** pytest 命令里（文档写了不算）。"""
    assert "run: ./.venv/Scripts/python.exe scripts/ci_local.py --keep-going" in workflow
    pytest_command = next(cmd for name, cmd in local._steps(with_audit=False) if name == "pytest")
    assert "--cov-fail-under=50" in pytest_command


def test_local_entry_uses_the_same_gates() -> None:
    """本地入口跑的是同一组门禁（含工程规范与合成验收）。"""
    names = [name for name, _cmd in local._steps(with_audit=False)]
    for required in ("工程规范门禁", "合成数据验收", "pytest"):
        assert required in names, names


def test_local_entry_enforces_the_same_coverage_floor(workflow: str) -> None:
    """⭐ 两套入口的 pytest 参数必须一致 —— 否则一边过、一边红。"""
    assert "python -m venv .venv" in workflow
    steps = dict(local._steps(with_audit=False))
    assert {"main.py", "plugins"} <= set(steps["ruff"])
    assert {"main.py", "plugins"} <= set(steps["编译检查"])
