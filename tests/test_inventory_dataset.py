"""「有什么」的数据集（本地 / 家）：换季把衣物寄回家、来年再寄回。

用户口径（2026-10-18）：

1. 寄回家的东西放**家**那一边（平行数据集）；
2. 家那一边**不区分位置** —— 一律只表示"在家"；
3. **补货只看本地** —— 家里的东西在这儿买不了，提醒了也没用；
4. "寄回家 / 寄回来"是**改归属字段**，不是删了再建。

数据形状是**纯新增**（物品加 `dataset`、顶层加 `current_dataset`），老文件靠自愈补齐，
所以**没有升 `_version`** —— 与这份文件既往加字段的做法一致（`Q-E4` 也说
`_migrate_vN_to_vM` 仍是骨架，尚无历史版本迁移需求）。
"""

import json

from src.models.inventory import InventoryModel


def _model(tmp_path) -> InventoryModel:
    return InventoryModel(tmp_path / "inventory.json")


def test_old_file_without_dataset_keys_is_treated_as_local(tmp_path) -> None:
    """老数据没有 `dataset` / `current_dataset` → 一律按**本地**处理（自愈，不动文件）。"""
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"_version": 1, "items": [
        {"id": "i_001", "name": "T恤", "quantity": 3, "status": "充足"}]},
        ensure_ascii=False), encoding="utf-8")

    m = InventoryModel(path)
    assert m.current_dataset == "local"
    assert [it["id"] for it in m.visible_items] == ["i_001"]
    assert m.dataset_of(m.items[0]) == "local"


def test_unknown_dataset_value_falls_back_to_local(tmp_path) -> None:
    """读侧防御：文件里写了不认识的数据集名 → 归本地（写侧由命令层 SPECS 拦）。"""
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"_version": 1, "current_dataset": "火星",
                                "items": [{"id": "i_001", "name": "x",
                                           "dataset": "车库"}]}, ensure_ascii=False),
                    encoding="utf-8")
    m = InventoryModel(path)
    assert m.current_dataset == "local"
    assert m.dataset_of(m.items[0]) == "local"


def test_set_dataset_switches_and_rejects_unknown(tmp_path) -> None:
    m = _model(tmp_path)
    assert m.set_dataset("home") is True
    assert m.current_dataset == "home"
    assert m.set_dataset("车库") is False
    assert m.current_dataset == "home", "非法名字不该改数据"


def test_home_has_no_locations_but_local_does(tmp_path) -> None:
    """家不区分位置（用户口径）→ 家那一边的允许位置为空。"""
    m = _model(tmp_path)
    m.data["locations"] = ["衣柜左1", "书架1"]
    assert m.allowed_locations == ["衣柜左1", "书架1"]
    m.set_dataset("home")
    assert m.allowed_locations == []


def test_visible_items_and_tags_follow_the_dataset(tmp_path) -> None:
    m = _model(tmp_path)
    m.data["items"] = [
        {"id": "i_001", "name": "T恤", "dataset": "local", "tags": ["夏装"], "status": "充足"},
        {"id": "i_002", "name": "羽绒服", "dataset": "home", "tags": ["冬装"], "status": "充足"},
    ]
    assert [it["name"] for it in m.visible_items] == ["T恤"]
    assert m.all_tags == ["夏装"]

    m.set_dataset("home")
    assert [it["name"] for it in m.visible_items] == ["羽绒服"]
    assert m.all_tags == ["冬装"]


def test_need_restock_only_counts_local(tmp_path) -> None:
    """补货只看本地 —— 与"当前在看哪一边"无关。"""
    m = _model(tmp_path)
    m.data["items"] = [
        {"id": "i_001", "name": "本地纸巾", "dataset": "local", "quantity": 0, "status": "需购"},
        {"id": "i_002", "name": "家里纸巾", "dataset": "home", "quantity": 0, "status": "需购"},
    ]
    assert [it["name"] for it in m.need_restock] == ["本地纸巾"]

    m.set_dataset("home")
    assert [it["name"] for it in m.need_restock] == ["本地纸巾"], "看家那边时也只看本地"


def test_move_item_changes_ownership_without_touching_ids(tmp_path) -> None:
    """寄回家 / 寄回来 = 改归属字段：id 不变、条数不变（不是删了再建）。"""
    m = _model(tmp_path)
    m.data["items"] = [{"id": "i_001", "name": "羽绒服", "dataset": "local",
                        "quantity": 2, "status": "充足"}]

    assert m.move_item("i_001", "home") is True
    assert m.dataset_of(m.items[0]) == "home"
    assert [it["id"] for it in m.items] == ["i_001"], "id 必须原样保留"

    assert m.move_item("i_001", "local") is True
    assert m.dataset_of(m.items[0]) == "local"

    assert m.move_item("i_999", "home") is False, "找不到的 id 不该假装成功"
    assert m.move_item("i_001", "车库") is False, "非法数据集名不该改数据"
    assert len(m.items) == 1
