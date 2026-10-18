"""本月预算预估（C 类第 6 项，用户用例表第 16 条）。

用户原话（备注）："新功能：预算预估 涉及现有的分期付款 自动续费 要补货的东西
以及根据之前几个月预估的日常支出"。

**纯计算，不存状态** ✓（存下来会过期、还要同步 ✗）—— 每次现算。

诚实边界（数据里有什么就说什么）：
- **日常支出**：按**近 3 个月**的日均推本月剩余天数 ✓（本月头几天样本太少，单看本月会飘 ✗）
- **自动续费**：会员**只有到期日、没有金额** ✗ → **列出"即将扣费"**，不硬编一个数字
- **要补货的**：库存里没有价格 ✗ → **列出件数**，不折算成钱
- **分期付款**：数据模型里**没有**这个字段（用户现实中记账）✗ → 不假装算得出来
"""

from datetime import date, timedelta

from src.models.inventory import days_until

HISTORY_DAYS = 90          # 用最近 90 天估日均
RENEW_WINDOW = 30          # 30 天内到期的会员算"即将扣费"


def _spent_since(records: list, since: str) -> float:
    total = 0.0
    for r in records or []:
        if str(r.get("date", ""))[:10] >= since:
            total += float(r.get("amount") or 0)
    return total


def renewals_soon(items: list, today: date | None = None) -> list[str]:
    """`RENEW_WINDOW` 天内到期的会员（**只报名字** —— 金额我们不知道 ✗）。"""
    out = []
    for it in items or []:
        m = it.get("membership") or {}
        if not m.get("auto_renew"):
            continue
        days = days_until(str(m.get("expires_on") or ""), today)
        if days is not None and days <= RENEW_WINDOW:
            out.append(f"{it.get('name', '')}（{m.get('expires_on', '')}）")
    return out


def forecast(records: list, budget: float = 0, items: list | None = None,
             today: date | None = None) -> dict:
    """本月预算预估 → 一个 dict（**纯函数**，好测）。

    `projected` = 本月已花 + 近 90 天日均 × 本月剩余天数（含今天，保守一点）。
    """
    today = today or date.today()
    budget = float(budget or 0)

    month_start = today.replace(day=1).isoformat()
    spent = _spent_since(records, month_start)

    hist_start = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    history = _spent_since(records, hist_start)
    daily = history / HISTORY_DAYS

    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    days_left = (next_month - today).days
    projected = spent + daily * days_left

    return {
        "spent": round(spent, 2),
        "budget": round(budget, 2),
        "daily": round(daily, 2),
        "days_left": days_left,
        "projected": round(projected, 2),
        "over": budget > 0 and projected > budget,
        "renewals": renewals_soon(items, today),
    }
