"""月付 / 分期（花呗）的**纯规则**：什么时候该扣、扣完没有。

用户 2026-10-31 的口径（`PLAN.md` P23 A1）：

- 两样都是「**订阅**」品类下的**库存条目**（和会员同一套），额外带账单字段；
- **只填「每月几号」**（`due_day`）—— 不做"每笔单独日期"；
- **月付**（`billing_type="monthly"`）：不限期数，每月 `due_day` 号扣一次；
- **分期**（`billing_type="installment"`）：`installments` 期、每期 `amount`；
  ★ **只填不算** ✗ —— 不算手续费 / 利息 / 剩余本金，用户填多少就是多少；
- 到期：**代码**记一笔支出（分类 `订阅/分期`）+ 发一封提醒邮件；
  **AI 只解释，不改数** ✗（和 A4 同一条原则）；
- 期数扣完 → **自动停用并保留** ✓（`billing_active=False`，还能回查）。

本模块**无 I/O、无 Qt**：给定条目 + 今天的日期 → 该不该扣 / 扣完怎么变。
"""

import calendar
from datetime import date

BILLING_MONTHLY = "monthly"
BILLING_INSTALLMENT = "installment"
BILLING_TYPES = (BILLING_MONTHLY, BILLING_INSTALLMENT)

# 自动记的那笔支出归到哪一类（记账分类 id / 名字，见 `models/expense.py`）
BILLING_CATEGORY_ID = "subscription"
BILLING_CATEGORY_NAME = "订阅/分期"


def is_billing(item: dict) -> bool:
    """这条物品是不是一条账单（月付 / 分期）。"""
    return (item.get("billing_type") or "") in BILLING_TYPES


def due_day_of(item: dict) -> int | None:
    """每月几号扣；没填 / 不合法 → `None`（**不猜**，也不会乱扣钱）。"""
    try:
        day = int(item.get("due_day") or 0)
    except (TypeError, ValueError):
        return None
    return day if 1 <= day <= 31 else None


def monthly_amount(item: dict) -> float:
    """每期金额（元）。解析不了按 0 处理 —— 0 元的账单不该真去记账。"""
    try:
        return float(item.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def is_active(item: dict) -> bool:
    """还能不能继续扣：显式停用 → 否；分期扣满期数 → 否（停用并保留）。"""
    if not is_billing(item):
        return False
    if item.get("billing_active") is False:
        return False
    total = installments_of(item)
    return total is None or paid_count(item) < total


def installments_of(item: dict) -> int | None:
    """总期数；`0` / 空 = **不限期数**（月付会员就是这种）→ `None`。"""
    try:
        n = int(item.get("installments") or 0)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def paid_count(item: dict) -> int:
    try:
        return max(0, int(item.get("paid_count") or 0))
    except (TypeError, ValueError):
        return 0


def remaining(item: dict) -> int | None:
    """还剩几期；不限期的返回 `None`。"""
    total = installments_of(item)
    return None if total is None else max(0, total - paid_count(item))


def charge_day_this_month(item: dict, today: date) -> int | None:
    """本月的扣款日 —— `due_day=31` 遇到小月要夹到月末（否则那些月永远不扣 ✗）。"""
    day = due_day_of(item)
    if day is None:
        return None
    return min(day, calendar.monthrange(today.year, today.month)[1])


def charged_this_month(item: dict, today: date) -> bool:
    """这个月已经扣过了吗（`last_charged_on` 的年月）。"""
    raw = str(item.get("last_charged_on") or "")[:10]
    if not raw:
        return False
    return raw[:7] == today.isoformat()[:7]


def due_today(item: dict, today: date) -> bool:
    """今天该扣吗：在扣、到了日子、这个月还没扣过。

    **补扣**：应用那天没开 → 过了扣款日再打开也会扣一次（同月只一次），
    这样不会因为"那天没开机"就漏记一笔钱 ✓。
    """
    if not is_active(item):
        return False
    day = charge_day_this_month(item, today)
    if day is None:
        return False
    return today.day >= day and not charged_this_month(item, today)


def apply_charge(item: dict, today: date) -> dict:
    """把"扣了这一期"写回条目（**原地改**），返回给支出记录的摘要。纯计算，不存盘。"""
    item["paid_count"] = paid_count(item) + 1
    item["last_charged_on"] = today.isoformat()
    total = installments_of(item)
    if total is not None and item["paid_count"] >= total:
        item["billing_active"] = False          # 扣完 → 停用并保留（用户口径）
    nth = item["paid_count"]
    return {"title": item.get("name", ""), "nth": nth, "total": total,
            "amount": monthly_amount(item)}


def charge_note(name: str, nth: int, total: int | None) -> str:
    """记账那条的备注（用户要知道"这是第几期"）。"""
    if total:
        return f"{name}（第 {nth}/{total} 期）"
    return f"{name}（月付）"
