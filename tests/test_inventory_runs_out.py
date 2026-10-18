"""「预估用完日」驱动状态（C 类第 1 项，用户用例表第 7/8 条）。

用户口径："估算大约还能用半年 / 预估还能用一个月" —— 现在只能落在 `notes` 里 ✗，
补上 `runs_out_on` 后**形状与会员到期日完全一致**（复用同一套"到期日驱动状态"）：

- 日期由**命令面**算（`--runs-out-months N`），不让模型做日期算术
- 已过 → 需购 · 7 天内 → 不足 · 否则充足
- `need_restock()` 自动带上它 → 托盘 + 邮件提醒照旧
"""

from src.models.inventory import InventoryModel, runs_out_date
from tests.helpers import run


def _item(sandbox) -> dict:
    import json

    return json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))["items"][0]


def test_runs_out_date_is_computed_by_code() -> None:
    """日期算术交给代码（30 天/月近似），不让模型算。"""
    assert runs_out_date(6, __import__("datetime").date(2026, 1, 1)) == "2026-06-30"
    assert runs_out_date(1, __import__("datetime").date(2026, 1, 1)) == "2026-01-31"


def test_add_item_with_runs_out_months_sets_date_and_status(sandbox) -> None:
    assert run('add_item --name "垃圾袋" --quantity 130 --runs-out-months 6').startswith("OK")
    item = _item(sandbox)
    assert item["runs_out_on"] == runs_out_date(6), "要存成算好的日期"
    assert item["status"] == "充足", "还有半年 → 充足"


def test_runs_out_in_the_past_means_need_to_buy(sandbox) -> None:
    run('add_item --name "鱼油" --quantity 1 --runs-out 2020-01-01')
    assert _item(sandbox)["status"] == "需购", "已过预估用完日 → 需购"


def test_runs_out_soon_means_low_stock(sandbox) -> None:
    """`runs_out_date(0)` = 今天 → 在 7 天警示窗内 → 不足。"""
    run('add_item --name "抽纸" --quantity 5 --runs-out-months 0')
    assert _item(sandbox)["status"] == "不足"


def test_runs_out_beats_quantity_when_present(sandbox) -> None:
    """有预估用完日时**按日期算**（与会员到期日同一口径），数量不再是依据。"""
    run('add_item --name "茶包" --quantity 999 --runs-out 2020-01-01')
    item = _item(sandbox)
    assert item["quantity"] == 999
    assert item["status"] == "需购"


def test_update_item_can_set_runs_out(sandbox) -> None:
    run('add_item --name "洗衣粉" --quantity 2')
    iid = _item(sandbox)["id"]
    assert run(f'update_item --id {iid} --runs-out-months 1').startswith("OK")
    assert _item(sandbox)["runs_out_on"] == runs_out_date(1)


def test_runs_out_item_shows_up_in_restock(sandbox) -> None:
    """到点的东西要进 `need_restock`（→ 托盘 + 邮件提醒）。"""
    run('add_item --name "过期鱼油" --quantity 1 --runs-out 2020-01-01')
    assert "过期鱼油" in run("need_restock")
    assert InventoryModel  # 模型可用（导入自检）
