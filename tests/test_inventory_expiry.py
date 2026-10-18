"""药品保质期 / 常备药（C 类第 5 项，`PLAN.md` P20）。

**复用"到期日驱动状态"**（会员 `expires_on`、`runs_out_on` 都是这个形状）——
所以这一项只是**多接一个字段**，不是新机制。

⚠ **偏离 P20 原计划**：P20 写的是"到保质期的 **3/4** 时提醒"，但**我们只有到期日、
没有生产日期**，这个比例**算不出来** ✗。所以老实做成"**到期前 N 天**"
（`remind_before_days`，默认 7）—— 比假装精确更诚实。

⚠ 与 `runs_out_on` 的语义差别：那是"**用完要补货**"，这是"**临期要换新**"。
"""

import json

from src.models.inventory import InventoryModel
from tests.helpers import run


def _item(sandbox, idx: int = 0) -> dict:
    return json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))["items"][idx]


def test_expired_medicine_needs_replacing(sandbox) -> None:
    run('add_item --name "蒙脱石散" --quantity 1 --expires 2020-01-01')
    assert _item(sandbox)["status"] == "需购", "过期 → 需购（要换新）"


def test_remind_before_widens_the_window(sandbox) -> None:
    """`--remind-before 30`：到期前 30 天就标不足（默认只提前 7 天）。"""
    import datetime

    soon = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()
    run(f'add_item --name "蒲地蓝" --quantity 1 --expires {soon} --remind-before 30')
    assert _item(sandbox)["status"] == "不足"

    run(f'add_item --name "罗红霉素" --quantity 1 --expires {soon}')
    assert _item(sandbox, 1)["status"] == "充足", "默认 7 天窗，20 天后到期还算充足"


def test_far_expiry_is_fine(sandbox) -> None:
    run('add_item --name "西替利嗪" --quantity 1 --expires 2030-01-01')
    assert _item(sandbox)["status"] == "充足"


def test_expiry_beats_quantity_when_present(sandbox) -> None:
    """有保质期就按日期算（和会员同一口径），数量不再是依据。"""
    run('add_item --name "氨酚烷胺" --quantity 999 --expires 2020-01-01')
    assert _item(sandbox)["status"] == "需购"


def test_expiry_and_runs_out_are_separate_fields(sandbox) -> None:
    """两个字段语义不同，各自独立（互不覆盖）。"""
    run('add_item --name "鱼油" --quantity 1 --runs-out 2030-01-01 --expires 2020-01-01')
    item = _item(sandbox)
    assert item["runs_out_on"] == "2030-01-01"
    assert item["expires_on"] == "2020-01-01"
    assert InventoryModel.derive_status(item) == "需购", "保质期已过 → 需购"


def test_update_item_can_set_expiry(sandbox) -> None:
    run('add_item --name "金银花颗粒" --quantity 1')
    iid = _item(sandbox)["id"]
    assert run(f'update_item --id {iid} --expires 2020-01-01 --remind-before 10').startswith("OK")
    item = _item(sandbox)
    assert item["expires_on"] == "2020-01-01"
    assert item["remind_before_days"] == 10
