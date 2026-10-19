"""日期驱动的状态必须**跨天生效**（三种日期都算）—— 2026-10-19 审查 R3 的回归。

病根：`derive_status()` 早就支持三种日期（会员到期 / 保质期 `expires_on` / 预计用完
`runs_out_on`），但**入口**只认会员那一种：
`has_expiry()` 只看 `membership.expires_on`，于是 `load()` 与 `effective_status()`
对顶层日期一律走"用存下来的 `status`"——存盘时是"充足"，日期过了也还是"充足"。
界面、AI 摘要、补货、每日提醒**全都漏报**，重启也治不好。

所以这里测的是**跨天**：先存一个未来的日期，再把 `today` 推到日期之后。
"""

from datetime import date, timedelta

from src.models.inventory import InventoryModel
from src.services.ai_prompts import inventory_prompt

TODAY = date(2026, 10, 19)
SOON = (TODAY + timedelta(days=3)).isoformat()      # 3 天后 → 在 7 天提醒窗口内
PAST = (TODAY - timedelta(days=1)).isoformat()      # 昨天 → 已经过了


def _item(**extra: object) -> dict:
    return {"id": "i_001", "name": "布洛芬", "quantity": 5, "min_quantity": 1,
            "unit": "盒", "status": "充足", **extra}


# ── 判定：三种日期都算"日期驱动" ────────────────────────────

def test_has_time_status_covers_all_three_dates() -> None:
    assert InventoryModel.has_time_status(_item(membership={"expires_on": SOON}))
    assert InventoryModel.has_time_status(_item(expires_on=SOON))
    assert InventoryModel.has_time_status(_item(runs_out_on=SOON))
    assert not InventoryModel.has_time_status(_item()), "没有日期 → 不是日期驱动"


# ── 跨天：顶层日期必须生效 ──────────────────────────────────

def test_expires_on_takes_effect_after_the_date_passes() -> None:
    """⭐ 保质期过了 → `需购`，哪怕存盘状态是"充足"。"""
    item = _item(expires_on=PAST)
    assert InventoryModel.derive_status(item, TODAY) == "需购"
    assert InventoryModel.effective_status(item, TODAY) == "需购"


def test_runs_out_on_takes_effect_after_the_date_passes() -> None:
    """⭐ 预计用完日过了 → `需购`（顶层日期，原来完全不生效）。"""
    item = _item(runs_out_on=PAST)
    assert InventoryModel.effective_status(item, TODAY) == "需购"


def test_manual_status_is_still_respected_without_dates() -> None:
    """⚠ 没有日期的手动 `status` 不能被自动推导覆盖（那是 2026-10-18 抓到的回归）。"""
    item = _item(status="需购")           # 手动标成需购，但数量其实够
    assert InventoryModel.effective_status(item, TODAY) == "需购"


def test_ignore_low_stock_still_exempts() -> None:
    """显式豁免（`ignore_low_stock`）仍然跳过重算。"""
    item = _item(expires_on=PAST, ignore_low_stock=True)
    assert InventoryModel.effective_status(item, TODAY) == "充足"


# ── 真实出口：补货 / 重载 / 摘要 ─────────────────────────────

def test_restock_reload_and_prompt_see_the_expired_item(tmp_path) -> None:
    """⭐ 三个真实出口都要看到它：`need_restock` / 重新读盘 / AI 摘要。

    这里用**真实今天**（`need_restock` 是属性、按当天算）—— 日期取"昨天"，已经过期。
    """
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    path = tmp_path / "inventory.json"
    model = InventoryModel(path)
    model.add_item({"name": "蒲地蓝", "category": "日常消耗品", "quantity": 5,
                    "unit": "盒", "expires_on": yesterday})
    model.save()

    later = InventoryModel(path)                        # 重新读盘（跨天 / 重启）
    assert later.items[0]["status"] == "需购"            # ① 读盘时就重算了
    assert [it["id"] for it in later.need_restock] == ["i_001"]   # ② 补货列表
    assert "需购" in inventory_prompt(later)             # ③ AI 摘要
