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


def test_real_course_today_triggers_outing_hints(tmp_path) -> None:
    """⭐ 用**真实模型**建一门今天的课（只有课、没有计划）→ 出门提示必须出现。

    回归 R7：`_has_class_on()` 原来按 `time_slots[].day` 判断，而**生产里没有这个字段**
    （星期在 `course.day_of_week`）—— 于是真实有课也永远不触发，旧测试还专门造了
    带 `day` 的假 slot 来配合实现 ✗。
    """
    from datetime import date as _date

    from src.services.data_manager import DataManager

    dm = DataManager(tmp_path)
    dm.courses.add_course({"name": "高等数学", "day_of_week": _date.today().isoweekday(),
                           "weeks": {"start": 1, "end": 16},
                           "time_slots": [{"start": 1, "end": 2, "location": "教三 201"}]})
    dm.courses.save()

    hints = today_hints(tmp_path)
    assert "outing.keys" in [h.key for h in hints], "今天有课 → 该提醒出门"
    assert "有课" in next(h.text for h in hints if h.key == "outing.keys")


def test_real_course_on_another_weekday_does_not_trigger(tmp_path) -> None:
    """⭐ 反例：课不在今天 → 不该提醒出门（同样是**真实模型**建的课）。"""
    from datetime import date as _date

    from src.services.data_manager import DataManager

    other_day = _date.today().isoweekday() % 7 + 1      # 明天那个星期几
    dm = DataManager(tmp_path)
    dm.courses.add_course({"name": "大学英语", "day_of_week": other_day,
                           "weeks": {"start": 1, "end": 16},
                           "time_slots": [{"start": 3, "end": 4, "location": "教三 202"}]})
    dm.courses.save()

    assert "outing.keys" not in [h.key for h in today_hints(tmp_path)]


def test_courses_outside_the_semester_weeks_do_not_trigger(tmp_path) -> None:
    """⭐ 教学周之外的课不算"今天有课" —— 这条规则由 `get_courses_for_date` 统一给 ✓。"""
    from datetime import date as _date

    from src.services.data_manager import DataManager

    dm = DataManager(tmp_path)
    dm.courses.add_course({"name": "体育", "day_of_week": _date.today().isoweekday(),
                           "weeks": {"start": 15, "end": 16},        # 只在前 16 周的后两周
                           "time_slots": [{"start": 5, "end": 5, "location": "东操场"}]})
    dm.courses.save()
    dm.semesters._data["semesters"][0]["start_date"] = "2020-02-24"   # 早就过了 16 周
    dm.semesters._data["semesters"][0]["total_weeks"] = 16
    dm.semesters.save()

    assert "outing.keys" not in [h.key for h in today_hints(tmp_path)]


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
