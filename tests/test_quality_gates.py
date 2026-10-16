"""工程规范门禁自身的守卫（`scripts/check_quality.py`）。

两层保证：
1. **探测器真的能探测** —— 用合成代码验证每个检查项，避免"门禁永远绿"的假象；
2. **当前仓库真的干净** —— `evaluate()` 无违规，且 baseline 不落后于现状。
"""

import ast
import json
from pathlib import Path

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


# ── 2. 当前仓库状态 ─────────────────────────────────────────
def test_repository_passes_quality_gate() -> None:
    rep = cq.evaluate()
    assert rep.failures == [], "\n".join(rep.failures)


def test_absolute_rules_are_clean() -> None:
    assert cq.check_silent_swallow() == []
    assert cq.check_id_generation() == []
    assert cq.check_top_level() == []
    assert cq.check_secret_not_tracked() == []


def test_baseline_is_not_behind_current_state() -> None:
    """baseline 只允许"比现状多"（已修好但没划掉），不允许"比现状少"（会漏防）。"""
    baseline = json.loads((ROOT / "scripts" / "quality_baseline.json").read_text(encoding="utf-8"))
    current_sizes = cq.check_sizes()
    missing = set(current_sizes) - set(baseline.get("sizes", {}))
    assert not missing, f"这些超限项不在 baseline 里，会漏防: {sorted(missing)}"
    assert set(cq.check_token_names()) <= set(baseline.get("token_names", []))
    assert cq.count_ui_chinese_literals() <= baseline.get("ui_chinese_literals", 0)
