"""出门与设备提醒（C 类第 7 项，`PLAN.md` P20）。

用户 P20 原话要点：
- **关键物品归位**：出门前提醒归位到**默认位置**（口径：`右手架子上`）
- **倒垃圾**：每天**第一次出门**时提醒 —— 结合日程 / 习惯判断"今天是否会出门"（**上课也算出门**）
- **电子设备**：提醒充电 / 检查电量
- 在**日程界面**给一条**可以直接 x 掉**的提示（骨架见 C 类第 3 项）

"出门"的判断全在**代码**里 ✓ —— 不让模型猜。
"""

import datetime
import json

from src.services.hints import outing_hints, today_hints

# 2026-10-19 是周一（isoweekday == 1）
MONDAY = datetime.date(2026, 10, 19)


def test_no_class_no_plan_means_no_outing_hints() -> None:
    assert outing_hints([], [], MONDAY) == [], "不出门就别啰嗦"


def test_class_counts_as_going_out() -> None:
    """用户口径："上课也算出门"。"""
    courses = [{"name": "高等数学", "time_slots": [{"day": 1, "start": 1, "end": 2}]}]
    hints = outing_hints([], courses, MONDAY)
    assert hints, "周一有课 → 该提醒出门"
    assert "有课" in hints[0].text


def test_other_weekday_class_does_not_count() -> None:
    courses = [{"name": "高数", "time_slots": [{"day": 3, "start": 1, "end": 2}]}]
    assert outing_hints([], courses, MONDAY) == [], "周三的课不影响周一"


def test_a_plan_counts_as_going_out() -> None:
    hints = outing_hints([{"title": "去图书馆"}], [], MONDAY)
    assert hints and "有安排" in hints[0].text


def test_hints_cover_the_three_items() -> None:
    hints = outing_hints([{"title": "x"}], [], MONDAY)
    text = " ".join(h.text for h in hints)
    assert "右手架子" in text, "关键物品归位（用户口径的默认位置）"
    assert "垃圾" in text
    assert "电" in text, "设备充电"
    assert len({h.key for h in hints}) == len(hints), "key 要唯一（界面靠它去重）"


def test_today_hints_merges_outing_rules(tmp_path) -> None:
    """接进 `today_hints()`：今天有计划 → 出门提示出现（天气没有也不影响）。"""
    today = datetime.date.today().isoformat()
    (tmp_path / "daily_logs.json").write_text(
        json.dumps({"plans": {today: [{"title": "去实验室"}]}}), encoding="utf-8")
    keys = [h.key for h in today_hints(tmp_path)]
    assert "outing.keys" in keys and "outing.trash" in keys
