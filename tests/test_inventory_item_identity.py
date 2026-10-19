"""物品 id **只增不复用** + 删物品时清私有手机号 —— 2026-10-19 审查 R9 的回归。

病根：手机号存在**私有文件**里、按物品 id 关联，而老实现挑"最小的空缺号"：
删掉 `i_001` 再新建一条，新物品**又会拿到 `i_001`** → 旧手机号串到新物品上
（用户会看到别人的号码挂在自己新记的会员上）。

防串号的**关键**是 id 不复用；"删的时候顺手清一下"只是卫生 ——
备份/同步恢复、CLI 删除、异常中断都可能漏掉清理。
"""

import json

from src.models.inventory import InventoryModel, next_item_id
from src.models.membership_contacts import MembershipContactsModel
from src.services.data_manager import DataManager

# ── id 不复用（根因）────────────────────────────────────────

def test_ids_are_not_reused_after_delete(tmp_path) -> None:
    """⭐ 删掉 `i_001` 再新建 → 新物品**不会**拿到 `i_001`。"""
    m = InventoryModel(tmp_path / "inventory.json")
    assert m.add_item({"name": "旧会员", "quantity": 1}) == "i_001"
    assert m.delete_item("i_001") is True
    second = m.add_item({"name": "新会员", "quantity": 1})
    assert second != "i_001", "id 被复用了 —— 私有手机号会串到新物品上"


def test_ids_keep_growing_and_survive_a_reload(tmp_path) -> None:
    """序号**存盘**：重新读盘后继续往后接，不会回到已删的号。"""
    path = tmp_path / "inventory.json"
    m = InventoryModel(path)
    m.add_item({"name": "A", "quantity": 1})
    m.add_item({"name": "B", "quantity": 1})
    m.delete_item("i_002")
    m.save()

    again = InventoryModel(path)
    assert again.add_item({"name": "C", "quantity": 1}) == "i_003"


def test_old_files_without_seq_get_unique_ids(tmp_path) -> None:
    """老数据文件没有 `item_seq` → 按现有**最大号**往后接（不与已有 id 冲突）。"""
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"_version": 1, "items": [
        {"id": "i_007", "name": "老数据", "quantity": 1}], "locations": []}), encoding="utf-8")
    m = InventoryModel(path)
    assert m.add_item({"name": "新的", "quantity": 1}) == "i_008"


def test_next_item_id_is_a_pure_function() -> None:
    assert next_item_id({}, [{"id": "i_003"}]) == "i_004"
    assert next_item_id({"item_seq": 9}, []) == "i_010"


# ── 串号场景：删 → 重建 ─────────────────────────────────────

def test_a_new_item_never_inherits_the_old_phone(tmp_path) -> None:
    """⭐ 端到端复现审查给的那个场景：删掉带手机号的会员 → 新建会员 → 号码**不跟着走**。"""
    dm = DataManager(tmp_path)
    old = dm.inventory.add_item({"name": "网盘会员", "category": "虚拟品类", "quantity": 1})
    dm.membership_contacts.set_phone(old, "13800000000")
    dm.membership_contacts.save()

    dm.inventory.delete_item(old)
    dm.inventory.save()
    dm.membership_contacts.forget(old)
    dm.membership_contacts.save()

    fresh = dm.inventory.add_item({"name": "新会员", "category": "虚拟品类", "quantity": 1})
    assert fresh != old, "id 复用了，这个测试就没意义了"
    contacts = MembershipContactsModel(tmp_path / "private" / "memberships.json")
    assert contacts.phone_of(fresh) == "", "新物品继承了旧手机号（串号）"
    assert contacts.phone_of(old) == "", "删掉的物品还留着手机号"


def test_cli_delete_item_clears_the_private_phone(sandbox) -> None:
    """CLI 的 `delete_item` 也要清私有文件（那是 AI / TG 那条写入路径）。"""
    from helpers import read_json, run

    assert run('add_item --name "网盘会员" --category "虚拟品类" --quantity 1').startswith("OK")
    private = sandbox / "private" / "memberships.json"
    private.parent.mkdir(parents=True, exist_ok=True)
    private.write_text(json.dumps({"_version": 1, "contacts": {"i_001": {"phone": "13800000000"}}}),
                       encoding="utf-8")

    assert run("delete_item --id i_001").startswith("OK")
    assert "i_001" not in read_json(sandbox, "private/memberships.json").get("contacts", {})
