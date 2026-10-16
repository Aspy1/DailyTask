"""同一时段两门课（选修过多 / 重修）的检测与呈现。

**回归背景**：周视图原来用 `setCellWidget` 直接放课程块 —— 同一格的第二门课
**静默覆盖**第一门，课表看起来"只有一门课"，用户不知道撞课了、也就想不到请假。
"""

from datetime import date, timedelta

from PySide6.QtWidgets import QLabel

from src.models.course_rules import conflicts_by_cell, find_conflicts, slots_of
from src.services.data_manager import DataManager


def _course(name: str, day: int = 1, start: int = 1, end: int = 1,
            weeks: tuple[int, int] = (1, 16), parity: str = "all",
            excluded: tuple[int, ...] = ()) -> dict:
    return {"id": name, "name": name, "day_of_week": day,
            "time_slots": [{"start": start, "end": end, "location": f"{name}楼"}],
            "weeks": {"start": weeks[0], "end": weeks[1]},
            "week_parity": parity, "excluded_weeks": list(excluded)}


def _monday() -> date:
    today = date.today()
    return today - timedelta(days=today.isoweekday() - 1)


def _dm_with_semester(tmp_path) -> DataManager:
    dm = DataManager(tmp_path)
    dm.courses._data["semesters"] = [{
        "id": "s", "name": "本学期", "start_date": _monday().isoformat(),
        "total_weeks": 16, "period_count": 5, "exam_weeks": 1}]
    dm.courses._data["current_semester"] = "s"
    return dm


# ── 纯规则 ──────────────────────────────────────────────────

def test_slots_of_expands_closed_interval() -> None:
    """`end` 是闭区间：单节连堂 `start == end` 占 1 节；1-2 连堂占 2 节。"""
    assert slots_of(_course("A", start=1, end=1)) == [1]
    assert slots_of(_course("A", start=1, end=2)) == [1, 2]


def test_no_conflict_for_different_slots_or_days() -> None:
    courses = [_course("A", day=1, start=1, end=1), _course("B", day=1, start=2, end=2)]
    assert find_conflicts(courses, 1, 5) == []
    courses = [_course("A", day=1, start=1, end=1), _course("B", day=2, start=1, end=1)]
    assert find_conflicts(courses, 1, 5) == []


def test_conflict_when_two_courses_share_a_slot() -> None:
    conflicts = find_conflicts([_course("选修A"), _course("重修B")], 1, 5)
    assert len(conflicts) == 1
    assert (conflicts[0]["day"], conflicts[0]["slot"]) == (1, 1)
    assert {c["name"] for c in conflicts[0]["courses"]} == {"选修A", "重修B"}


def test_multi_period_overlap_is_detected_per_slot() -> None:
    """A 占 1-2 节、B 只占第 2 节 → 第 2 节冲突。"""
    cells = conflicts_by_cell([_course("A", start=1, end=2), _course("B", start=2, end=2)], 1, 5)
    assert set(cells) == {(1, 2)}


def test_week_range_and_parity_separate_courses() -> None:
    """周次范围不同 / 单双周不同 → 不算冲突。"""
    a = _course("A", weeks=(1, 8))
    b = _course("B", weeks=(9, 16))
    assert find_conflicts([a, b], 1, 5) == []
    assert find_conflicts([a, b], 9, 5) == []

    odd = _course("A", parity="odd")
    even = _course("B", parity="even")
    assert find_conflicts([odd, even], 3, 5) == []
    assert find_conflicts([odd, even], 4, 5) == []


def test_excluded_week_removes_conflict() -> None:
    """把某周加入 `excluded_weeks`（= 请假那周）后，该周不再算冲突。"""
    a = _course("A")
    b = _course("B", excluded=(3,))
    assert find_conflicts([a, b], 3, 5) == []
    assert find_conflicts([a, b], 4, 5) != []


def test_slots_beyond_period_count_are_ignored() -> None:
    assert find_conflicts([_course("A", start=6, end=6), _course("B", start=6, end=6)], 1, 5) == []


# ── 模型 ────────────────────────────────────────────────────

def test_model_find_conflicts_uses_current_week(tmp_path) -> None:
    dm = _dm_with_semester(tmp_path)
    dm.courses.add_course({"name": "选修A", "day_of_week": 1,
                           "time_slots": [{"start": 1, "end": 1}]})
    dm.courses.add_course({"name": "重修B", "day_of_week": 1,
                           "time_slots": [{"start": 1, "end": 1}]})
    conflicts = dm.courses.find_conflicts()
    assert len(conflicts) == 1
    assert len(conflicts[0]["courses"]) == 2


def test_model_conflicts_empty_without_semester(tmp_path) -> None:
    dm = DataManager(tmp_path)
    dm.courses.add_course({"name": "A", "day_of_week": 1, "time_slots": [{"start": 1, "end": 1}]})
    dm.courses.add_course({"name": "B", "day_of_week": 1, "time_slots": [{"start": 1, "end": 1}]})
    assert dm.courses.find_conflicts() == []          # 不知道是哪一周 → 不猜


# ── 周视图：两门课都要画出来 ────────────────────────────────

def test_week_table_renders_both_courses(qapp, tmp_path) -> None:
    """回归：第二门课曾被静默覆盖，现在必须两门都在。"""
    from src.ui.panels.course_panel import CoursePanel

    dm = _dm_with_semester(tmp_path)
    dm.courses.add_course({"name": "选修A", "day_of_week": 1,
                           "time_slots": [{"start": 1, "end": 1}]})
    dm.courses.add_course({"name": "重修B", "day_of_week": 1,
                           "time_slots": [{"start": 1, "end": 1}]})

    panel = CoursePanel(dm)
    panel._refresh()

    chip = panel.table.cellWidget(0, 0)              # 周一第 1 节
    assert chip is not None, "冲突格必须有块"
    assert {c["name"] for c in chip.courses} == {"选修A", "重修B"}
    texts = [label.text() for label in chip.findChildren(QLabel)]
    assert any("选修A" in t for t in texts)
    assert any("重修B" in t for t in texts)
    assert any("冲突" in t for t in texts)           # ⚠ 标题


def test_week_table_plain_course_without_conflict(qapp, tmp_path) -> None:
    from src.ui.panels.course_panel import CoursePanel

    dm = _dm_with_semester(tmp_path)
    dm.courses.add_course({"name": "独占", "day_of_week": 1,
                           "time_slots": [{"start": 1, "end": 1}]})
    panel = CoursePanel(dm)
    panel._refresh()
    chip = panel.table.cellWidget(0, 0)
    assert chip is not None and not hasattr(chip, "courses")   # 普通课程块


# ── 日视图：提示请假 ────────────────────────────────────────

def test_day_view_warns_about_conflict(qapp, tmp_path) -> None:
    from src.ui.widgets.schedule_view import ScheduleView

    dm = _dm_with_semester(tmp_path)
    today = date.today().isoweekday()
    for name in ("选修A", "重修B"):
        dm.courses.add_course({"name": name, "day_of_week": today,
                               "time_slots": [{"start": 1, "end": 1}]})

    view = ScheduleView(dm)
    view._refresh()
    texts = [label.text() for label in view.findChildren(QLabel)]
    assert any("记得请假" in t for t in texts), texts[:20]


def test_day_view_no_warning_without_conflict(qapp, tmp_path) -> None:
    from src.ui.widgets.schedule_view import ScheduleView

    dm = _dm_with_semester(tmp_path)
    dm.courses.add_course({"name": "独占", "day_of_week": date.today().isoweekday(),
                           "time_slots": [{"start": 1, "end": 1}]})
    view = ScheduleView(dm)
    view._refresh()
    texts = [label.text() for label in view.findChildren(QLabel)]
    assert not any("记得请假" in t for t in texts)
