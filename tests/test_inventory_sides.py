"""「有什么」的归属：**位置就是归属**（学校 / 家）。

用户口径（2026-10-18，第二版 —— 第一版是"数据集字段 + 让模型判断'家里'指哪边"，被否）：

1. 位置是**唯一**的归属信号：说了位置就用它，没说就默认**学校**；
2. 归属**由位置推导**，不单独存 `dataset` 字段；
3. 「家」那一侧的位置就是"家"（换季寄回 / 存放），其余位置都算学校侧；
4. **补货只看学校那一侧**（家里的东西在这儿买不了）。

⚠ 为什么否掉第一版：flash 模型中文不稳，让它理解"家里"到底指哪边**必错**
（2026-10-18 探针实测：它把"家里抽纸"记成了寄回家的那批 ✗）。
换成"抄位置"这种机械规则后，模型只需要会复制字符串。
"""

from src.models.inventory import (
    DEFAULT_LOCATION,
    HOME_LOCATION,
    SIDE_HOME,
    SIDE_SCHOOL,
    InventoryModel,
)


def _model(tmp_path) -> InventoryModel:
    return InventoryModel(tmp_path / "inventory.json")


def test_side_is_derived_from_location(tmp_path) -> None:
    """归属由位置推导：位置是"家" → 家侧；宿舍格位 / "学校" / 空 → 学校侧。"""
    m = _model(tmp_path)
    assert m.side_of({"location": "书架3"}) == SIDE_SCHOOL
    assert m.side_of({"location": DEFAULT_LOCATION}) == SIDE_SCHOOL
    assert m.side_of({"location": ""}) == SIDE_SCHOOL
    assert m.side_of({"location": HOME_LOCATION}) == SIDE_HOME
    assert m.side_of({"location": "老家"}) == SIDE_HOME


def test_new_file_has_school_and_home_in_location_vocabulary(tmp_path) -> None:
    """新文件的位置词表里就有「学校」「家」两个粗格位（换季靠它们表达归属）。"""
    m = _model(tmp_path)
    assert DEFAULT_LOCATION in m.locations
    assert HOME_LOCATION in m.locations


def test_need_restock_only_counts_school_side(tmp_path) -> None:
    """补货只看学校那一侧 —— 家里的东西在这儿买不了（用户口径）。"""
    m = _model(tmp_path)
    m.data["items"] = [
        {"id": "i_001", "name": "学校纸巾", "location": "书架3",
         "quantity": 0, "status": "需购"},
        {"id": "i_002", "name": "家里纸巾", "location": HOME_LOCATION,
         "quantity": 0, "status": "需购"},
    ]
    assert [it["name"] for it in m.need_restock] == ["学校纸巾"]


def test_all_tags_cover_both_sides(tmp_path) -> None:
    """标签是全局的（分边只是视图的事，模型不掺和）。"""
    m = _model(tmp_path)
    m.data["items"] = [
        {"id": "i_001", "name": "T恤", "location": "衣柜左1", "tags": ["夏装"]},
        {"id": "i_002", "name": "羽绒服", "location": HOME_LOCATION, "tags": ["冬装"]},
    ]
    assert m.all_tags == ["冬装", "夏装"]
