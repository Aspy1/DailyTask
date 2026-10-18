"""「有什么」命令面的新能力（P18 第 1 步）：份数 / 同类不同特征 / 位置 / 补货。

起因：审查 + 核实发现现有 11 条真实数据用到了 `unit` / `min_quantity` / `instances`，
而 **AI 只能写 `min_quantity`** —— 直接让 AI 重建会得到比现有更差的数据。
所以先把命令面补齐：`--unit` / `--doses-per-unit` / `--instances` / `consume`。
"""

import json

from tests.helpers import run


def _items(sandbox) -> list[dict]:
    path = sandbox / "inventory.json"
    return json.loads(path.read_text(encoding="utf-8"))["items"] if path.exists() else []


def test_add_item_records_unit_and_doses(sandbox) -> None:
    """份数：`--unit` 说明单位、`--doses-per-unit` 说明一份里有多少小单位。"""
    assert run('add_item --name "布洛芬" --category "日常消耗品" --quantity 1 '
               '--unit "盒" --doses-per-unit 24 --min_qty 1 --location "药箱"').startswith("OK")

    item = _items(sandbox)[0]
    assert item["unit"] == "盒"
    assert item["doses_per_unit"] == 24
    assert item["location"] == "药箱"


def test_add_item_derives_status_from_min_qty(sandbox) -> None:
    """补货：数量低于下限就该是"不足"（原来只判 `qty<=0`，1 件/下限 5 也记成充足 ✗）。"""
    run('add_item --name "纸巾" --quantity 1 --min_qty 5')
    assert _items(sandbox)[0]["status"] == "不足"

    run('add_item --name "抽纸" --quantity 5 --min_qty 5')
    assert _items(sandbox)[1]["status"] == "充足"

    run('add_item --name "洗手液" --quantity 0 --min_qty 1')
    assert _items(sandbox)[2]["status"] == "需购"


def test_add_item_keeps_instances_for_same_type(sandbox) -> None:
    """同类不同特征：一条物品 + 多个 instances（而不是拆成两条无关物品）。"""
    spec = ('[{"tags": ["Type-C"], "notes": "1米"}, '
            '{"tags": ["Lightning"], "notes": "0.5米"}]')
    run(f'add_item --name "充电线" --quantity 2 --instances \'{spec}\'')

    item = _items(sandbox)[0]
    assert len(item["instances"]) == 2
    assert item["instances"][0]["tags"] == ["Type-C"]
    assert item["instances"][1]["notes"] == "0.5米"


def test_instances_bad_json_is_rejected_without_writing(sandbox) -> None:
    """非法 JSON 只回 ERROR，**不写任何文件**（R-002 的入口校验）。"""
    out = run('add_item --name "充电线" --instances \'不是 JSON\'')
    assert out.startswith("ERROR")
    assert _items(sandbox) == []


def test_consume_decrements_and_updates_status(sandbox) -> None:
    """消耗：按每份含量扣减 + 重算状态，不用先查再手算。"""
    run('add_item --name "洗手液" --quantity 2 --unit "瓶" --min_qty 1')
    iid = _items(sandbox)[0]["id"]

    out = run(f"consume --id {iid} --amount 1")
    assert out.startswith("OK")

    item = _items(sandbox)[0]
    assert item["quantity"] == 1
    assert item["status"] == "充足"

    run(f"consume --id {iid} --amount 1")
    assert _items(sandbox)[0]["status"] == "需购", "用完了要标成需购"


def test_consume_unknown_id_is_rejected(sandbox) -> None:
    assert run("consume --id i_999").startswith("ERROR")


def test_update_item_replaces_instances_and_unit(sandbox) -> None:
    run('add_item --name "充电线" --quantity 1 --unit "条"')
    iid = _items(sandbox)[0]["id"]

    run(f'update_item --id {iid} --unit "根" --instances \'[{{"tags": ["USB-C"]}}]\'')

    item = _items(sandbox)[0]
    assert item["unit"] == "根"
    assert item["instances"] == [{"tags": ["USB-C"]}]


def test_min_doses_is_dose_level_threshold(sandbox) -> None:
    """片级下限：说"剩不到 5 片"要用 `--min-doses 5`，不是 `--min-qty 5`（= 5 盒 ✗）。

    2026-10-18 探针发现：模型把"5 片"写成了"5 盒"（差 24 倍），因为原来只有单位级下限。
    """
    run('add_item --name "布洛芬" --quantity 1 --unit "盒" --doses-per-unit 24 '
        '--min-doses 5 --location "药箱"')

    item = _items(sandbox)[0]
    assert item["min_doses"] == 5
    assert item["status"] == "充足", "1 盒 = 24 片，还在 5 片之上"


def test_min_doses_fires_below_threshold_while_unit_level_does_not(sandbox) -> None:
    """对照：片级下限会触发、单位级不会 —— 这正是当初单位错位的后果。"""
    run('add_item --name "布洛芬" --quantity 1 --unit "盒" --doses-per-unit 4 '
        '--min-doses 5')
    assert _items(sandbox)[0]["status"] == "不足", "1 盒 4 片 < 下限 5 片 → 不足"

    run('add_item --name "对照" --quantity 1 --unit "盒" --doses-per-unit 4 --min_qty 1')
    assert _items(sandbox)[1]["status"] == "充足", "只有单位级下限时看不出片数不够"


def test_set_locations_replaces_the_allowed_list(sandbox) -> None:
    """位置清单：整份替换 + 去空白去重（AI 重建时只从这份里选）。"""
    assert run('set_locations --values "衣柜左1, 衣柜左2 ,衣柜左1,书架1"').startswith("OK")

    data = json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))
    assert data["locations"] == ["衣柜左1", "衣柜左2", "书架1"], "去空白 + 去重"


def test_unknown_location_is_registered_automatically(sandbox) -> None:
    """位置是**受控属性**：物品用了清单外的位置 → 自动登记进清单（用户允许 AI 自行添加）。"""
    run('set_locations --values "衣柜左1"')
    out = run('add_item --name "洗发水" --quantity 2 --unit "瓶" --location "卫生间柜子"')

    assert "新增位置" in out, f"回执里应说明新增了位置：{out}"
    data = json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))
    assert "卫生间柜子" in data["locations"]
    assert data["items"][0]["location"] == "卫生间柜子"


def test_lookup_filters_by_location_category_and_restock(sandbox) -> None:
    """查找支持多属性组合：位置 / 分类 / 标签 / 只看需补货。"""
    run('add_item --name "T恤" --quantity 3 --unit "件" --category "衣物" '
        '--location "衣柜左1" --tags "夏装"')
    run('add_item --name "QQ音乐会员" --quantity 1 --unit "个" --category "虚拟品类"')
    run('add_item --name "纸巾" --quantity 0 --unit "包" --category "日常消耗品" '
        '--location "书架3"')

    assert "T恤" in run('lookup_item --location "衣柜左1"')
    assert "QQ音乐会员" in run('lookup_item --category "虚拟品类"')
    assert "T恤" in run('lookup_item --tag "夏装"')

    restock = run("lookup_item --restock yes")
    assert "纸巾" in restock and "T恤" not in restock, "只看需补货的"

    assert "FOUND 3" in run("lookup_item"), "不带条件 = 列出全部"


def test_consume_keeps_the_partial_box(sandbox) -> None:
    """⚠ P1 回归：1 盒 24 片用掉 1 片 → **23 片**，不是"0 盒"（审查 F1）。

    老算法 `(1*24 - 1) // 24 = 0` 把 23 片凭空丢了。
    """
    run('add_item --name "布洛芬" --quantity 1 --unit "盒" '
        '--doses-per-unit 24 --min-doses 5')
    iid = _items(sandbox)[0]["id"]

    out = run(f"consume --id {iid} --amount 1")
    item = _items(sandbox)[0]
    assert item["remaining_doses"] == 23, out
    assert item["quantity"] == 0, "不足一盒时盒数是 0（只做展示换算）"
    assert item["status"] == "充足", "23 片还在 5 片下限之上"


def test_consume_walks_down_and_reports_status(sandbox) -> None:
    """连续扣减 24 → 19 → 4 → 0，状态跟着下限走（审查要求的边界）。"""
    run('add_item --name "布洛芬" --quantity 1 --unit "盒" '
        '--doses-per-unit 24 --min-doses 5')
    iid = _items(sandbox)[0]["id"]

    for amount, left, status in [(5, 19, "充足"), (15, 4, "不足"), (4, 0, "需购")]:
        run(f"consume --id {iid} --amount {amount}")
        item = _items(sandbox)[0]
        assert item["remaining_doses"] == left, item
        assert item["status"] == status, item


def test_consume_more_than_left_floors_at_zero(sandbox) -> None:
    """超量扣减 → 停在 0，不会变负数。"""
    run('add_item --name "布洛芬" --quantity 1 --unit "盒" --doses-per-unit 24')
    iid = _items(sandbox)[0]["id"]

    run(f"consume --id {iid} --amount 100")
    item = _items(sandbox)[0]
    assert item["remaining_doses"] == 0 and item["quantity"] == 0
    assert item["status"] == "需购"


def test_partial_box_is_not_reported_as_need_buy(sandbox) -> None:
    """⚠ 连带回归：一盒用剩 23 片时 `quantity` 是 0，**不能**因此判成"需购"。"""
    run('add_item --name "布洛芬" --quantity 1 --unit "盒" '
        '--doses-per-unit 24 --min-doses 5')
    iid = _items(sandbox)[0]["id"]
    run(f"consume --id {iid} --amount 1")

    assert "布洛芬" not in run("need_restock"), "还有 23 片，不该进补货列表"


def test_model_and_cli_share_one_consume_algorithm(tmp_path) -> None:
    """CLI 与模型**共用**同一个扣减实现（审查 §6：不许各写一份消耗）。"""
    from src.models.inventory import InventoryModel, apply_consume

    item = {"id": "i_001", "quantity": 1, "doses_per_unit": 24, "min_doses": 5}
    assert apply_consume(item, 1) == 23
    assert item["quantity"] == 0

    m = InventoryModel(tmp_path / "inventory.json")
    m.data["items"] = [{"id": "i_001", "quantity": 1, "doses_per_unit": 24,
                        "min_doses": 5, "remaining_doses": 24}]
    assert m.consume_doses("i_001", 1) == 23
    assert m.items[0]["quantity"] == 0


# ── 归属：位置就是归属（学校 / 家）────────────────────────────

def test_add_item_defaults_location_to_school(sandbox) -> None:
    """没说位置 → 默认「学校」（用户口径 2026-10-18）。"""
    run('add_item --name "羽绒服" --quantity 2 --unit "件"')
    assert _items(sandbox)[0]["location"] == "学校"


def test_add_item_keeps_explicit_location(sandbox) -> None:
    """说了位置就照抄 —— 默认值不该覆盖用户说的格位。"""
    run('add_item --name "T恤" --quantity 3 --location "书架3"')
    assert _items(sandbox)[0]["location"] == "书架3"


def test_add_item_virtual_category_gets_no_default_location(sandbox) -> None:
    """虚拟品类（会员）不吃"学校"这个默认 —— 对它们没意义，留空更诚实。"""
    run('add_item --name "QQ音乐会员" --quantity 1 --category "虚拟品类"')
    assert _items(sandbox)[0]["location"] == ""


def test_send_home_and_back_is_just_a_location_change(sandbox) -> None:
    """"寄回家 / 寄回来"就是改位置：id 与条数都不变（不删不建）。"""
    run('add_item --name "羽绒服" --quantity 2 --unit "件" --location "衣柜左1"')
    iid = _items(sandbox)[0]["id"]

    run(f'update_item --id {iid} --location "家"')
    assert [(it["id"], it["location"]) for it in _items(sandbox)] == [(iid, "家")]

    run(f'update_item --id {iid} --location "学校"')
    assert [(it["id"], it["location"]) for it in _items(sandbox)] == [(iid, "学校")]


def test_need_restock_ignores_home_side(sandbox) -> None:
    """补货只看学校那一侧：位置是"家"的物品不参与。"""
    run('add_item --name "学校纸巾" --quantity 0 --location "书架3"')
    run('add_item --name "家里纸巾" --quantity 0 --location "家"')

    out = run("need_restock")
    assert "学校纸巾" in out and "家里纸巾" not in out
    assert "家里纸巾" not in run("lookup_item --restock yes")


def test_lookup_by_location_finds_home_items(sandbox) -> None:
    """按位置筛选是找"家里那批"的正规办法（比让模型判断"家里"可靠）。"""
    run('add_item --name "羽绒服" --quantity 2 --location "家"')
    run('add_item --name "T恤" --quantity 3 --location "书架3"')

    home = run('lookup_item --location "家"')
    assert "羽绒服" in home and "T恤" not in home
