"""物品字段的**可写清单**（`ITEM_FIELDS`）守卫。

为什么单独一个文件：2026-10-19 实测到一个**静默丢数据**的 bug ——
`add_item` / `update_item` 各写一份字段白名单，后加的字段（`membership` /
`expires_on` / `runs_out_on` / `stock_target` / `worn_since` …）只加进了**命令路径**
（`scripts/actions_cmds_items.py` 直接改 dict，不经过模型），于是：

- **会员弹窗**填完到期日一保存就没了 ✗（`update_item` 还返回 `True` 谎报成功 ✗✗）；
- 任何"带会员信息建一条"的调用也丢字段。

⚠ 为什么原来的测试没拦住：命令路径的测试（`test_actions_*` / `test_inventory_expiry` …）
**全走 CLI** ✗ —— 它们根本不经过模型的这两个方法。
"""

import logging
from datetime import date, timedelta

from src.models.inventory import ITEM_FIELDS, InventoryModel

# C 类加的字段。**手写**（不从 `ITEM_FIELDS` 里复制 —— 复制就测不出"清单漏了" ✗）。
C_CLASS_FIELDS = {
    "membership": {"username": "my_qq", "expires_on": "2027-03-15", "auto_renew": True},
    "expires_on": "2027-03-15",
    "runs_out_on": "2027-03-15",
    "remind_before_days": 30,
    "stock_target": 2,
    "worn_since": (date.today() - timedelta(days=3)).isoformat(),
    "wash_after_days": 7,
    "needs_wash": True,
}


def _model(tmp_path) -> InventoryModel:
    return InventoryModel(tmp_path / "inventory.json")


def test_add_item_keeps_every_writable_field(tmp_path) -> None:
    m = _model(tmp_path)
    iid = m.add_item({"name": "会员卡", "quantity": 1, **C_CLASS_FIELDS})
    item = m.items[0]
    for key, value in C_CLASS_FIELDS.items():
        assert item.get(key) == value, f"add_item 丢了字段 {key}"
    assert iid == item["id"]


def test_update_item_persists_every_writable_field(tmp_path) -> None:
    """回归：会员弹窗的保存路径（`update_item(iid, {"membership": …})`）曾经**什么都不存**。"""
    m = _model(tmp_path)
    m.add_item({"name": "会员卡", "quantity": 1})
    for key, value in C_CLASS_FIELDS.items():
        assert m.update_item("i_001", {key: value}) is True
        assert m.items[0].get(key) == value, f"update_item 丢了字段 {key}"


def test_update_item_warns_on_unknown_field(tmp_path, caplog) -> None:
    """清单外的键要**告警**，不能默默吞 —— 默默吞就是那个 bug 的形态。"""
    m = _model(tmp_path)
    m.add_item({"name": "纸巾", "quantity": 1})
    with caplog.at_level(logging.WARNING):
        m.update_item("i_001", {"not_a_field": 1})
    assert "not_a_field" in caplog.text


def test_membership_survives_the_ui_save_path(tmp_path) -> None:
    """端到端：会员弹窗就是 `update_item` → `save`，然后界面重新读盘。"""
    m = _model(tmp_path)
    m.add_item({"name": "网盘会员", "category": "虚拟品类", "quantity": 1})
    m.update_item("i_001", {"membership": {"expires_on": "2027-03-15", "auto_renew": True}})
    m.save()
    again = _model(tmp_path)
    assert again.items[0]["membership"]["expires_on"] == "2027-03-15"


def test_item_fields_has_no_duplicates() -> None:
    assert len(ITEM_FIELDS) == len(set(ITEM_FIELDS))


# ── 覆盖**全部**可写字段（审查 R10：只挑几个 C 类字段不够）──────────

# 每个可写字段的样例值。**手写**（不是从 `ITEM_FIELDS` 推导）——
# 这样"清单加了字段但没人管它"会被下面那条一致性断言抓住 ✓。
SAMPLES = {
    "name": "样例物品", "category": "日常消耗品", "group": "分组", "quantity": 3,
    "unit": "瓶", "status": "不足", "min_quantity": 2, "min_doses": 4,
    "location": "桌面", "notes": "备注", "tags": ["常用"], "instances": [{"tags": ["A"]}],
    "ignore_low_stock": True, "doses_per_unit": 24,
    "membership": {"username": "me", "expires_on": "2027-01-01"},
    "expires_on": "2027-01-01", "runs_out_on": "2027-01-01", "remind_before_days": 10,
    "stock_target": 6, "worn_since": "2026-10-01", "wash_after_days": 7, "needs_wash": True,
    "status_locked": True,
    # 月付 / 分期（A1，2026-10-31）
    "billing_type": "monthly", "amount": 15.0, "due_day": 5, "installments": 0,
    "paid_count": 2, "billing_active": True, "last_charged_on": "2026-10-05",
}


def test_samples_cover_every_writable_field() -> None:
    """样例表必须与 `ITEM_FIELDS` **同步** —— 两边都要动，否则新字段会漏测。"""
    assert set(SAMPLES) == set(ITEM_FIELDS), \
        f"样例表与清单不同步：清单多 {set(ITEM_FIELDS) - set(SAMPLES)}，" \
        f"样例多 {set(SAMPLES) - set(ITEM_FIELDS)}"


def test_add_item_keeps_all_writable_fields(tmp_path) -> None:
    """⭐ `add_item` 要**原样**保留每一个可写字段。

    回归 R10：`unit` 曾被硬写成"件"，显式传的 `unit` 被丢掉；
    而 `status` / 余量是在**默认值之前**算的（`add_item({'name': 'x'})` 会得到"需购"）。
    """
    m = _model(tmp_path)
    m.add_item(dict(SAMPLES))
    item = m.items[0]
    for key, value in SAMPLES.items():
        assert item.get(key) == value, f"add_item 丢了或改了字段 {key}"


def test_add_item_with_only_a_name_is_not_marked_restock(tmp_path) -> None:
    """⭐ 只给名字建一条：数量默认 1、余量默认 1 → 状态**充足**（原来算成"需购"）。"""
    m = _model(tmp_path)
    m.add_item({"name": "只有名字"})
    item = m.items[0]
    assert item["quantity"] == 1 and item["remaining_doses"] == 1
    assert item["status"] == "充足", "默认值还没填就拿原始 data 推状态 → 误判需购"


def test_update_item_keeps_all_writable_fields(tmp_path) -> None:
    """`update_item` 同样覆盖全部字段（`status` 除外：它会被自动推导，见批次三那条遗留）。"""
    m = _model(tmp_path)
    m.add_item({"name": "占位", "quantity": 1})
    for key, value in SAMPLES.items():
        if key == "status":
            continue                      # 手动 status 会被自动推导覆盖（另一条已知遗留）
        assert m.update_item("i_001", {key: value}) is True
        assert m.items[0].get(key) == value, f"update_item 丢了字段 {key}"
