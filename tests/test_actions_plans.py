"""日程计划的命令：`complete_plan`（用户用例表第 10 条）。

"（assumption）我收拾完扑克牌了" → 标记日程完成；若同时涉及物品，AI 另外调 `update_item`。
"""

import json

from tests.helpers import run

DAY = "2026-10-18"


def _plans(sandbox) -> list[dict]:
    path = sandbox / "daily_logs.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("plans", {}).get(DAY, [])


def test_complete_plan_marks_the_item_done(sandbox) -> None:
    run(f'add_plan --date "{DAY}" --title "整理扑克牌" --slot 2')
    assert _plans(sandbox)[0].get("done") is None, "新建的计划默认未完成"

    out = run(f'complete_plan --date "{DAY}" --index 0')
    assert out.startswith("OK"), out

    plan = _plans(sandbox)[0]
    assert plan["done"] is True
    assert plan.get("completed_at"), "要留完成时间"


def test_complete_plan_is_idempotent(sandbox) -> None:
    """再点一次不报错（幂等）—— 用户可能重复说"我做完了"。"""
    run(f'add_plan --date "{DAY}" --title "整理扑克牌" --slot 2')
    assert run(f'complete_plan --date "{DAY}" --index 0').startswith("OK")
    assert run(f'complete_plan --date "{DAY}" --index 0').startswith("OK")


def test_complete_plan_rejects_out_of_range_index(sandbox) -> None:
    run(f'add_plan --date "{DAY}" --title "整理扑克牌" --slot 2')
    out = run(f'complete_plan --date "{DAY}" --index 9')
    assert out.startswith("ERROR"), out
    assert _plans(sandbox)[0].get("done") is None, "越界不该改动任何数据"
