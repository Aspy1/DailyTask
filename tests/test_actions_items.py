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


# ── 数据集（本地 / 家）───────────────────────────────────────

def _set_current_dataset(sandbox, name: str) -> None:
    """直接改文件里的"当前数据集"。

    没有切换命令 —— 切换是**界面**的事（`inventory_panel` 的按钮），命令行只跟随它。
    """
    path = sandbox / "inventory.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["current_dataset"] = name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_add_item_to_home_rejects_location(sandbox) -> None:
    """家数据集不使用位置：同时给 `--location` 就是参数矛盾 → **拒绝且不写**（R-002）。"""
    out = run('add_item --name "羽绒服" --dataset home --location "衣柜左1"')
    assert out.startswith("ERROR")
    assert _items(sandbox) == []


def test_add_item_follows_current_dataset(sandbox) -> None:
    """不写 `--dataset` 就落在**当前数据集** —— 与界面上看到的那一边一致。"""
    run('add_item --name "T恤" --quantity 3')
    _set_current_dataset(sandbox, "home")
    run('add_item --name "羽绒服" --quantity 2')

    assert [(it["name"], it["dataset"]) for it in _items(sandbox)] == [
        ("T恤", "local"), ("羽绒服", "home")]


def test_move_item_between_datasets_keeps_id_and_count(sandbox) -> None:
    """寄回家 / 寄回来 = `update_item --dataset`，**不是**删了再建。"""
    run('add_item --name "羽绒服" --quantity 2 --unit "件" --location "衣柜左1"')
    iid = _items(sandbox)[0]["id"]

    assert "归属：家" in run(f"update_item --id {iid} --dataset home")
    assert [(it["id"], it["dataset"]) for it in _items(sandbox)] == [(iid, "home")]

    assert "归属：本地" in run(f"update_item --id {iid} --dataset local")
    assert [(it["id"], it["dataset"]) for it in _items(sandbox)] == [(iid, "local")]


def test_update_without_dataset_does_not_move_anything(sandbox) -> None:
    """⚠ 回归：只改数量**不能**把物品搬走。

    早期实现里 `update_item` 的数据集回退成"当前数据集" —— 用户正看着"家"时改一条
    本地物品的数量，就会被**误搬**到家里。
    """
    run('add_item --name "T恤" --quantity 3')
    iid = _items(sandbox)[0]["id"]
    _set_current_dataset(sandbox, "home")

    run(f"update_item --id {iid} --quantity 5")

    assert _items(sandbox)[0]["dataset"] == "local", "没传 --dataset 就不该动归属"


def test_lookup_scopes_to_current_dataset_with_all_option(sandbox) -> None:
    """查找默认只看当前数据集；`--dataset home` / `all` 看另一边 / 两边。"""
    run('add_item --name "T恤" --quantity 3 --location "衣柜左1"')
    run('add_item --name "羽绒服" --quantity 2 --dataset home')

    current = run("lookup_item")
    assert "T恤" in current and "羽绒服" not in current

    home = run("lookup_item --dataset home")
    assert "羽绒服" in home and "T恤" not in home
    assert "[家]" in home, "家那一边要标出来（否则跨数据集查找时分不清）"
    assert "@" not in home, "家不显示位置（用户口径）"

    both = run("lookup_item --dataset all")
    assert "T恤" in both and "羽绒服" in both


def test_need_restock_ignores_home_items(sandbox) -> None:
    """补货只看本地：家里的东西在这儿买不了（用户口径）。"""
    run('add_item --name "本地纸巾" --quantity 0 --dataset local')
    run('add_item --name "家里纸巾" --quantity 0 --dataset home')

    out = run("need_restock")
    assert "本地纸巾" in out and "家里纸巾" not in out
    assert "家里纸巾" not in run("lookup_item --restock yes")


def test_dataset_all_is_rejected_on_update(sandbox) -> None:
    """`all` 只在查找里成立；写操作只接受一个确定的数据集。"""
    run('add_item --name "T恤" --quantity 1')
    iid = _items(sandbox)[0]["id"]
    assert run(f"update_item --id {iid} --dataset all").startswith("ERROR")


def test_home_item_does_not_register_location(sandbox) -> None:
    """家那一边不碰位置词表（`locations` 是**本地**数据集的）。"""
    run('set_locations --values "衣柜左1"')
    run('add_item --name "羽绒服" --quantity 2 --dataset home')

    data = json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))
    assert data["locations"] == ["衣柜左1"], "家不该往位置词表里加东西"
    assert data["items"][0]["location"] == ""
