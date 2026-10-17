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
