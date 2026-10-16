"""工程规范门禁自身的守卫（`scripts/check_quality.py`）。

两层保证：
1. **探测器真的能探测** —— 用合成代码验证每个检查项，避免"门禁永远绿"的假象；
2. **当前仓库真的干净** —— `evaluate()` 无违规，且 baseline 不落后于现状。
"""

import ast
import json
from pathlib import Path

import pytest

import scripts.check_quality as cq

ROOT = Path(__file__).resolve().parent.parent


# ── 1. 探测器有效性 ─────────────────────────────────────────
def test_silent_swallow_detects_named_exception() -> None:
    """ruff S110 漏检具名异常，这里必须能抓到。"""
    handler = ast.parse("try:\n    pass\nexcept (ValueError, TypeError):\n    pass\n").body[0].handlers[0]
    assert cq._is_pass_only(handler.body) is True


def test_silent_swallow_ignores_real_handler() -> None:
    handler = ast.parse("try:\n    pass\nexcept ValueError:\n    print('x')\n").body[0].handlers[0]
    assert cq._is_pass_only(handler.body) is False


def test_id_regex_matches_len_plus_one() -> None:
    assert cq.ID_LEN1_RE.search('    x = f"c_{len(courses) + 1:03d}"')
    assert not cq.ID_LEN1_RE.search('    x = next_id("c", ids)')


def test_decl_violations_flags_oversized_class() -> None:
    src = "class Big:\n" + "    x = 1\n" * 500
    over = cq._decl_violations(ast.parse(src), "synthetic.py")
    assert any(k.startswith("class:Big@") for k in over)


def test_token_name_regex_flags_raw_color_names() -> None:
    assert cq.BAD_TOKEN_RE.match("red")
    assert cq.BAD_TOKEN_RE.match("yellow")
    assert not cq.BAD_TOKEN_RE.match("state_danger")


def test_log_helpers_detect_module_logger_calls() -> None:
    assert cq._is_logging_call(ast.parse("logger.info('x')").body[0].value) is True
    assert cq._is_logging_call(ast.parse("logging.warning('x')").body[0].value) is True
    assert cq._is_logging_call(ast.parse("print('x')").body[0].value) is False
    # 非模块级 logger（如 self.logger）不在契约内
    assert cq._is_logging_call(ast.parse("self.logger.info('x')").body[0].value) is False


def test_child_blocks_returns_if_branches() -> None:
    node = ast.parse("if x:\n    a()\nelse:\n    b()\n").body[0]
    assert len(cq._child_blocks(node)) == 2


def test_unwrapped_chinese_ignores_tr_arguments() -> None:
    """`tr("中文")` 的实参不算"未国际化"。"""
    tree = ast.parse('a = tr("面板标题")\nb = "裸中文"')
    assert cq._count_cn_in_file.__name__          # 存在性
    wrapped = cq._tr_arg_ids(tree)
    consts = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    unwrapped = [c.value for c in consts if id(c) not in wrapped]
    assert unwrapped == ["裸中文"]


# ── 2. 当前仓库状态 ─────────────────────────────────────────
def test_repository_passes_quality_gate() -> None:
    rep = cq.evaluate()
    assert rep.failures == [], "\n".join(rep.failures)


def test_absolute_rules_are_clean() -> None:
    assert cq.check_silent_swallow() == []
    assert cq.check_id_generation() == []
    assert cq.check_log_embedded() == []
    assert cq.check_top_level() == []
    assert cq.check_secret_not_tracked() == []


def test_no_new_secrets_beyond_baseline() -> None:
    """`SECRETS` 是**只读比对**（基线之外的发现必须为 0）。

    注意不能用 `detect-secrets scan --baseline X` —— 那个语义是"**更新**基线"
    （退出码恒 0，等于没检查），且会写脏工作区。
    """
    result = cq.check_new_secrets()
    if result is None:
        pytest.skip("detect-secrets 未安装")
    assert result == []


def test_baseline_is_not_behind_current_state() -> None:
    """baseline 只允许"比现状多"（已修好但没划掉），不允许"比现状少"（会漏防）。"""
    baseline = json.loads((ROOT / "scripts" / "quality_baseline.json").read_text(encoding="utf-8"))
    current_sizes = cq.check_sizes()
    missing = set(current_sizes) - set(baseline.get("sizes", {}))
    assert not missing, f"这些超限项不在 baseline 里，会漏防: {sorted(missing)}"
    assert set(cq.check_token_names()) <= set(baseline.get("token_names", []))
    assert cq.count_ui_chinese_literals() <= baseline.get("ui_chinese_literals", 0)
