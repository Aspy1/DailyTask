"""收入 / 固定支出 / 预计支出 —— **代码算，AI 只解释**（A4，用户 2026-10-31 口径）。

- 用户只给**初始值**：总余额、月收入、固定支出（房租 / 话费这类每月不变的）；
- **"预计本月支出"由代码算**：过去 `BASIS_MONTHS` 个**整月**的**中位数**
  （中位数比均值抗"某个月买了台电脑"这种离群值）；
- 本月已花超过中位数时，取**已花**（不能报一个比实际还低的数）；
- 数据不够几个月就如实说"用了 N 个月"，不假装满额；
- 界面必须注明依据；**AI 不许自己算** ✗ —— 问它就调 `finance_summary` 读这里的结果。

本模块**纯函数**：给定记录 + 用户设的值 → 一张汇总表。
"""

from datetime import date

BASIS_MONTHS = 3


def monthly_totals(records: list) -> dict[str, float]:
    """按 `YYYY-MM` 汇总支出（金额解析不了的记录跳过，不把整页算崩）。"""
    out: dict[str, float] = {}
    for record in records or []:
        month = str(record.get("date") or "")[:7]
        if len(month) != 7:
            continue
        try:
            amount = float(record.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        out[month] = out.get(month, 0.0) + amount
    return {month: round(total, 2) for month, total in out.items()}


def median(values: list) -> float:
    """中位数（偶数个取中间两个的平均）；空 → 0。"""
    data = sorted(float(v) for v in values)
    if not data:
        return 0.0
    mid = len(data) // 2
    if len(data) % 2:
        return round(data[mid], 2)
    return round((data[mid - 1] + data[mid]) / 2, 2)


def basis_months(today: date, months: int = BASIS_MONTHS) -> list[str]:
    """"之前的 N 个整月"（**不含本月**）→ `["2026-09", "2026-08", "2026-07"]`。"""
    keys: list[str] = []
    year, month = today.year, today.month
    for _ in range(months):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        keys.append(f"{year}-{month:02d}")
    return keys


def summary(records: list, finance: dict | None = None,
            today: date | None = None, months: int = BASIS_MONTHS) -> dict:
    """一张汇总表：已花 / 预计本月支出 / 收入 / 固定支出 / 本月结余 / 余额 + 依据。"""
    today = today or date.today()
    finance = finance or {}
    totals = monthly_totals(records)
    keys = basis_months(today, months)
    used = [totals[key] for key in keys if key in totals]
    spent = totals.get(today.strftime("%Y-%m"), 0.0)
    projected = max(median(used), spent) if used else spent
    income = _number(finance.get("monthly_income"))
    fixed = _number(finance.get("fixed_expenses"))
    return {
        "spent": round(spent, 2),
        "projected": round(projected, 2),
        "basis_months": len(used),
        "basis_total": months,
        "income": round(income, 2),
        "fixed": round(fixed, 2),
        "left": round(income - projected, 2),
        "balance": round(_number(finance.get("balance")), 2),
    }


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
