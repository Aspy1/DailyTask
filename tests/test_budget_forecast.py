"""本月预算预估（C 类第 6 项，用户用例表第 16 条）。

**纯计算、不存状态** ✓；算不出来的东西**列出来而不是硬编一个数字** ✓：

| 用户提的 | 数据里有没有 | 处理 |
|---|---|---|
| 日常支出 | ✓ 支出记录 | 按**近 90 天**日均推本月剩余天数 |
| 自动续费 | 只有到期日、**没有金额** ✗ | **列出"即将扣费"**，不折钱 |
| 要补货的 | 库存**没有价格** ✗ | **列出件数**，不折钱 |
| 分期付款 | 模型里**没有**这个字段 ✗ | 不假装算得出来 |
"""

import datetime

from src.services.budget import forecast, renewals_soon
from src.services.hints import budget_hints

DAY = datetime.date(2026, 10, 15)


def _records() -> list:
    """近 3 个月每天 ¥10（→ 日均 10），加上本月已花的 ¥100。"""
    out = [{"date": f"2026-0{m}-01", "amount": 300, "category": "餐饮"} for m in (8, 9)]
    out.append({"date": "2026-10-01", "amount": 100, "category": "餐饮"})
    return out


def test_projection_uses_history_not_just_this_month() -> None:
    """本月头几天样本太少 —— 用近 90 天日均推，不看本月单日。"""
    r = forecast(_records(), budget=1000, today=DAY)
    assert r["spent"] == 100, "本月已花只算本月的"
    assert r["daily"] > 0
    assert r["projected"] > r["spent"], "还要加上剩余天数的预估"
    assert r["over"] is False, "预算 1000 够用"


def test_over_budget_flag_and_amount() -> None:
    r = forecast(_records(), budget=100, today=DAY)
    assert r["over"] is True
    assert r["projected"] > r["budget"]


def test_no_budget_means_no_over_flag() -> None:
    r = forecast(_records(), budget=0, today=DAY)
    assert r["over"] is False, "没设预算就不说超支（0 不是'预算 0 元'）"


def test_renewals_list_names_only() -> None:
    """续费**只有名字**（金额我们不知道 ✗），且只在窗口内才列。"""
    items = [{"name": "QQ音乐", "membership": {"auto_renew": True, "expires_on": "2026-10-20"}},
             {"name": "网盘", "membership": {"auto_renew": True, "expires_on": "2030-01-01"}},
             {"name": "手动续的", "membership": {"auto_renew": False, "expires_on": "2026-10-16"}}]
    soon = renewals_soon(items, DAY)
    assert len(soon) == 1 and "QQ音乐" in soon[0]
    assert "2030" not in "".join(soon), "远期的不列"


def test_budget_hint_only_when_over(tmp_path) -> None:
    import json

    (tmp_path / "expenses.json").write_text(json.dumps(
        {"records": _records(), "budget": {"monthly": 50}}), encoding="utf-8")
    hints = budget_hints(tmp_path, [])
    assert len(hints) == 1 and "超支" in hints[0].text
    assert hints[0].key == "budget.over"

    (tmp_path / "expenses.json").write_text(json.dumps(
        {"records": _records(), "budget": {"monthly": 100000}}), encoding="utf-8")
    assert budget_hints(tmp_path, []) == [], "没超支就不提示"