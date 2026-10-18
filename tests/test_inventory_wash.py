"""衣物状态：穿了几天 / 该洗了（C 类第 4 项，用户用例表第 13/22 条）。

用户用例：
- 第 13 条："毛巾两条 一条蓝色一条黄色 在晾衣架上" → 备注问"是否正确初始化提醒清洗的日程表"
- 第 22 条："我把衣柜3最里面的蓝色床单换来用了 记得提醒我洗之前的蓝色床单"

两个设计选择：
1. **不存"穿了几天"计数器** —— 计数器要有人记得每天 +1（漏一天就错，跨天/跨设备必错 ✗）；
   存"从哪天开始穿"的日期，天数**每次算** ✓（和 `runs_out_on` 同一思路）
2. **"该洗了"走「今日提示」**（`services/hints.py`），**不进物品状态** ——
   状态那套是"库存够不够"（充足/不足/需购），跟"该不该洗"是两回事 ✓
"""

import json

from src.models.inventory import needs_wash_now, worn_days, worn_since_date
from src.services.hints import wash_hints
from tests.helpers import run


def test_worn_since_date_is_computed_by_code() -> None:
    import datetime

    assert worn_since_date(3, datetime.date(2026, 10, 18)) == "2026-10-15"
    assert worn_since_date(0, datetime.date(2026, 10, 18)) == "2026-10-18"


def test_worn_days_is_derived_not_counted() -> None:
    """天数从起始日**算出来**（老数据没这个字段 → `None`，不是 0）。"""
    import datetime

    today = datetime.date(2026, 10, 18)
    assert worn_days({"worn_since": "2026-10-15"}, today) == 3
    assert worn_days({"worn_since": "2026-10-18"}, today) == 0
    assert worn_days({}, today) is None
    assert worn_days({"worn_since": "不是日期"}, today) is None


def test_needs_wash_now_explicit_or_by_days() -> None:
    import datetime

    today = datetime.date(2026, 10, 18)
    assert needs_wash_now({"needs_wash": True}, today) is True, "显式标了就该洗"
    assert needs_wash_now({"worn_since": "2026-10-15", "wash_after_days": 3}, today) is True
    assert needs_wash_now({"worn_since": "2026-10-17", "wash_after_days": 3}, today) is False
    assert needs_wash_now({}, today) is False, "什么都没记 → 不提示"


def test_wash_hints_only_for_items_needing_wash() -> None:
    hints = wash_hints([{"id": "i_1", "name": "毛巾", "needs_wash": True},
                        {"id": "i_2", "name": "牙膏", "needs_wash": False}])
    assert len(hints) == 1
    assert "毛巾" in hints[0].text and hints[0].key == "wash.i_1"
    assert wash_hints([]) == []


def _item(sandbox) -> dict:
    return json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))["items"][0]


def test_commands_set_and_clear_the_wash_state(sandbox) -> None:
    run('add_item --name "毛巾" --quantity 2 --location "晾衣架"')
    iid = _item(sandbox)["id"]

    assert run(f'update_item --id {iid} --worn-days 0 --needs-wash yes').startswith("OK")
    item = _item(sandbox)
    assert item["needs_wash"] is True
    assert item["worn_since"] == worn_since_date(0)
    assert needs_wash_now(item) is True

    assert run(f'update_item --id {iid} --needs-wash no').startswith("OK")
    assert needs_wash_now(_item(sandbox)) is False, "洗好了就不该再提示"
