"""方案 C 的**决策判据**（`MD-files/PERFORMANCE_WORKFLOW.md` §3.4）。

手册要求"试验前先为主要指标定预算，例如要求重负载下作业操作 P95 至少改善 20%，
同时为首屏和稳定内存约定可接受的额外开销"。这里把那条规则**变成可执行判定**，
而不是留一句"待用户裁决"：

    指标                                    预算          判据
    ─────────────────────────────────────────────────────────────
    单条完成 P95（10k 档）                  改善 ≥20%     ✅ 实测 +100%
    分页 P95（10k 档）                      不许变慢      ✅ 实测 +98.8%
    全量列表 P95（10k 档）                  不慢于 20%    ❌ 实测 −150%
    批量导入 P95（10k 档）                  不慢于 20%    ❌ 实测 −29%
    首屏与稳态内存                          额外 ≤10%     ✅ 未接生产，0 增量

**结论**：只有"单条写入"这一条满足预算，"整体切换"不满足。所以决策是
**不做整体切换**；若将来要做，只把写入路径切到 SQLite，列表/筛选继续走内存态。
"""

from __future__ import annotations

# 每一项： (指标名, 基线键, **最低可接受改善百分比**, 说明)
#
# 语义**统一**为"改善百分比的下限"（改善是正数、变慢是负数）：
#   +20 → 必须至少改善 20%        （手册示例：重负载下作业操作）
#     0 → 必须持平或更快           （高频只读操作不许变慢）
#   -20 → 最多允许慢 20%           （可接受的额外开销）
# 判定一律是 `improvement_pct >= 下限` —— 只有一种方向，不给符号留解释空间。
BUDGETS: tuple[tuple[str, str, float, str], ...] = (
    ("单条完成 P95", "单条完成", 20.0, "重负载下作业操作至少改善 20%（手册示例）"),
    ("分页 100 条 P95", "分页 100 条", 0.0, "不许变慢（分页是高频只读操作）"),
    ("全量列表 P95", "按学期列表", -20.0, "最多允许慢 20%"),
    ("批量导入 P95", "批量导入", -20.0, "最多允许慢 20%"),
)


def judge(improvement_pct: float, min_improvement_pct: float) -> bool:
    """某指标的实测改善是否达到**最低要求**（唯一方向：越大越好）。"""
    return improvement_pct >= min_improvement_pct


def decide(rows: list[dict]) -> dict:
    """拿 `perf_sqlite_bench.py` 的结果套预算 → 逐项判定 + 总决策。"""
    measured = {row["label"].split("·")[0]: row for row in rows}
    results = []
    for label, key, allowed, note in BUDGETS:
        row = measured.get(key)
        if row is None:
            results.append({"indicator": label, "measured": None, "pass": False,
                            "note": f"没有测到「{key}」"})
            continue
        p95 = row["p95_improvement_pct"]
        results.append({"indicator": label, "improvement_pct": p95,
                        "budget_pct": allowed, "pass": judge(p95, allowed),
                        "note": note})
    passed = sum(1 for r in results if r["pass"])
    return {
        "results": results,
        "passed": passed,
        "total": len(results),
        # 整体切换要求**全部**指标达标；只切写入则只看写入那一项
        "full_switch_approved": passed == len(results),
        "write_only_approved": next(
            (r["pass"] for r in results if r["indicator"] == "单条完成 P95"), False),
    }


def main() -> int:
    import json
    import sys
    from pathlib import Path

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print("用法：perf_sqlite_decision.py <perf_sqlite_bench 的 JSON>")
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    # 兼容两种输入：`perf_sqlite_bench --json` 的裸结果，与 `archive()` 包了一层
    # `{"environment":…, "results":…, "raw_samples":…}` 的归档产物
    payload = payload.get("results", payload)
    rows = payload["tiers"]["10000"]
    verdict = decide(rows)

    print("— 方案 C 决策判据（10k 档 P95）—")
    for item in verdict["results"]:
        mark = "✅" if item["pass"] else "❌"
        value = item.get("improvement_pct")
        shown = f"{value:+.1f}%" if value is not None else "未测"
        print(f"  {mark} {item['indicator']:<16} 实测 {shown:>8}  "
              f"预算 {item['budget_pct']:+.0f}%   {item['note']}")
    print(f"\n  整体切换：{'批准' if verdict['full_switch_approved'] else '不批准'}"
          f"（{verdict['passed']}/{verdict['total']} 达标）")
    print(f"  仅切写入：{'批准' if verdict['write_only_approved'] else '不批准'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
