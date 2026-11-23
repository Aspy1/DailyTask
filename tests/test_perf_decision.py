"""方案 C 的**决策判据**必须可复核（`PERFORMANCE_WORKFLOW.md` §3.4）。

手册要求"试验前先为主要指标定预算……再决定是否实装"。这条规则如果只写在报告里，
下次换个数据就能得出相反结论；所以把判据本身钉成测试：

1. 预算表覆盖手册点名的四类操作；
2. `judge()` 的语义正确（改善阈值 vs 允许劣化阈值是两个方向）；
3. 用**本次实测**的 10k 数据得出一致结论：整体切换不批准、仅切写入批准；
4. 少一项指标时**不批准**（缺证据不能当通过）。
"""

import json
from pathlib import Path

import pytest

import scripts.perf_sqlite_decision as decision


def _rows(**overrides: float) -> list[dict]:
    """构造 `perf_sqlite_bench` 形状的行（可逐项覆盖 P95 改善值）。"""
    base = {
        "单条完成": 100.0, "分页 100 条": 98.8,
        "按学期列表": -158.2, "批量导入": -32.9,
    }
    base.update(overrides)
    return [{"label": f"{key}·JSON", "median_improvement_pct": value,
             "p95_improvement_pct": value}
            for key, value in base.items()]


def test_budgets_cover_the_four_documented_operations() -> None:
    keys = {key for _label, key, _allowed, _note in decision.BUDGETS}

    assert keys == {"单条完成", "分页 100 条", "按学期列表", "批量导入"}


def test_judge_direction_is_correct() -> None:
    """唯一方向：`improvement_pct >= 下限`（改善为正、变慢为负）。

    语义统一成"最低改善百分比"，所以：
      +20 要求至少改善 20%；0 要求持平或更快；-20 允许最多慢 20%。
    """
    assert decision.judge(100.0, 20.0) is True       # 改善 100% 满足"≥20%"
    assert decision.judge(10.0, 20.0) is False       # 只改善 10%，不满足"≥20%"
    assert decision.judge(0.0, 0.0) is True          # 持平满足"不许变慢"
    assert decision.judge(-1.0, 0.0) is False        # 变慢 1%，违反"不许变慢"
    assert decision.judge(-10.0, -20.0) is True      # 慢 10%，仍在"最多慢 20%"内
    assert decision.judge(-30.0, -20.0) is False     # 慢 30%，超出预算


def test_measured_data_rejects_a_full_switch() -> None:
    """⭐ 本次实测：2/4 达标 → 整体切换不批准，但仅切写入批准。"""
    verdict = decision.decide(_rows())

    assert verdict["full_switch_approved"] is False
    assert verdict["passed"] == 2 and verdict["total"] == 4
    assert verdict["write_only_approved"] is True


def test_a_clean_sweep_would_approve_the_full_switch() -> None:
    """反向用例：四项都达标时判据必须给出"批准"（判据不是永远说不）。"""
    verdict = decision.decide(_rows(**{"按学期列表": 25.0, "批量导入": 30.0}))

    assert verdict["full_switch_approved"] is True


def test_missing_indicator_counts_as_not_approved() -> None:
    """少一项指标 → 不批准（缺证据 ≠ 通过）。"""
    rows = [r for r in _rows() if not r["label"].startswith("批量导入")]
    verdict = decision.decide(rows)

    assert verdict["full_switch_approved"] is False
    missing = next(r for r in verdict["results"] if r["indicator"] == "批量导入 P95")
    assert missing["pass"] is False and "没有测到" in missing["note"]


def test_real_benchmark_output_matches_the_report() -> None:
    """用归档的原始输出复核一遍（报告与判据不许漂）。

    数据来自 `scripts/perf_sqlite_bench.py` 的归档（`perf-data/sqlite-comparison.json`）。
    """
    payload_path = (Path(__file__).resolve().parent.parent
                    / "dev-logs" / "perf-data" / "sqlite-comparison.json")
    if not payload_path.exists():
        pytest.skip("未附基准输出（可选产物）")

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    rows = payload["results"]["tiers"]["10000"]
    verdict = decision.decide(rows)

    assert verdict["full_switch_approved"] is False
    assert verdict["write_only_approved"] is True
    # 原始样本也必须归档（手册 §5：可复核中位/P95/尾部）
    assert payload.get("raw_samples"), "归档里没有逐次样本"
