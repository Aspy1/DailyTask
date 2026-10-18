"""日程的「学习 / 生活」区分（C 类第 2 项，用户用例表第 13 条）。

用户原话："日程表界面有些拥挤了，加功能区分学习和生活显示"。

设计：**规则给默认 + 用户可覆盖 + 顶部筛选**
（不按类别分组 —— 日程是按**节次**排的，分组会打乱时间轴 ✗）。
"""

from src.models.daily_log import LIFE, STUDY, DailyLogModel, plan_category
from src.ui.widgets.schedule_filter import visible


def test_plan_category_defaults_by_rule() -> None:
    """规则给默认：带 `course_name` / 课业类 `type` → 学习；其余 → 生活。"""
    assert plan_category({"title": "复习英语"}) == LIFE
    assert plan_category({"title": "复习英语", "course_name": "英语"}) == STUDY
    assert plan_category({"title": "x", "type": "course_note"}) == STUDY


def test_user_override_wins_over_the_rule() -> None:
    """用户改过的以**存下来的**为准（即使规则会判成另一个）。"""
    assert plan_category({"title": "x", "course_name": "英语", "category": LIFE}) == LIFE
    assert plan_category({"title": "x", "category": STUDY}) == STUDY
    assert plan_category({"title": "x", "category": "垃圾值"}) == LIFE, "非法值退回规则"


def test_filter_visibility_rules() -> None:
    """课程算学习、习惯算生活、计划按规则。"""
    assert visible("all", "course") and visible("all", "habit")
    assert visible("study", "course") is True
    assert visible("life", "course") is False
    assert visible("life", "habit") is True
    assert visible("study", "habit") is False
    assert visible("study", "plan", {"title": "x", "course_name": "英语"}) is True
    assert visible("life", "plan", {"title": "x", "course_name": "英语"}) is False


def test_set_plan_category_persists(sandbox) -> None:
    model = DailyLogModel(sandbox / "daily_logs.json")
    model.add_plan({"title": "复习英语"}, day="2026-10-18")

    assert model.set_plan_category("2026-10-18", 0, STUDY) is True
    assert model.get_plans("2026-10-18")[0]["category"] == STUDY
    assert model.set_plan_category("2026-10-18", 9, STUDY) is False, "越界返回 False"
