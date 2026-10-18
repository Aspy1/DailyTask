"""常备量（`PLAN.md` P20 的另一条路："剩常备量的 1/4 时提醒"）。

P20 说两条路：新增 `stock_target`，或约定 `min_quantity = 常备量 / 4`。

**选了新增 `stock_target`** —— 因为"**低于多少提醒**"和"**应该常备多少**"本来就是
两件事 ✗：用户说"常备 6 盒"时，他心里的是"我该有 6 盒"，而不是"低于 1.5 盒提醒我"。
混用会让阈值含义变模糊，而且用户改常备量时还得自己算 1/4 ✗。
"""

import json

from tests.helpers import run


def _item(sandbox) -> dict:
    return json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))["items"][0]


def test_stock_target_reminds_at_a_quarter(sandbox) -> None:
    """常备 6 盒 → 剩 ≤1.5 盒算不足（用户口径："剩常备量的 1/4"）。"""
    run('add_item --name "蒲地蓝" --quantity 6 --unit "盒" --stock-target 6')
    assert _item(sandbox)["status"] == "充足", "满常备量 → 充足"

    run('update_item --id "i_001" --quantity 2')
    assert _item(sandbox)["status"] == "充足", "2 盒 > 1.5 → 还够"

    run('update_item --id "i_001" --quantity 1')
    assert _item(sandbox)["status"] == "不足", "1 盒 ≤ 1.5 → 该补了"


def test_empty_is_still_need_to_buy(sandbox) -> None:
    run('add_item --name "蒙脱石散" --quantity 0 --stock-target 4')
    assert _item(sandbox)["status"] == "需购", "没了就是需购（不是不足）"


def test_stock_target_takes_precedence_over_min_quantity(sandbox) -> None:
    """设了常备量就按它算 —— 别让两个阈值互相打架 ✗。"""
    run('add_item --name "金银花" --quantity 3 --min-qty 1 --stock-target 20')
    assert _item(sandbox)["status"] == "不足", "3 ≤ 20/4=5 → 不足（按常备量算）"


def test_without_target_the_old_rules_still_apply(sandbox) -> None:
    run('add_item --name "创可贴" --quantity 2 --min-qty 5')
    assert _item(sandbox)["status"] == "不足", "没常备量 → 退回 min_quantity"
    run('add_item --name "棉签" --quantity 5 --min-qty 5')
    assert json.loads((sandbox / "inventory.json").read_text(
        encoding="utf-8"))["items"][1]["status"] == "充足"
