"""学期数据的合法性检测与状态判定（`src/models/semester.py` + `CourseModel`）。

背景：周次计算此前散在 5 处、口径各不相同 —— 状态栏不钳上界（学期过期后显示
"第 32 / 16 周"）、AI 忽略 `current_semester`、邮件摘要又是第三套算法。
这里把"检测"与"状态"钉住。
"""

from datetime import date, timedelta

import pytest

from src.models import semester as sem
from src.models.course import CourseModel


def _sem(**overrides: object) -> dict:
    base = {"id": "s1", "name": "2026 春", "start_date": "2026-02-23",
            "total_weeks": 20, "period_count": 5}
    base.update(overrides)
    return base


# ── 合法性检测（纯函数）─────────────────────────────────────

def test_valid_semester_has_no_issues() -> None:
    assert sem.validate_semester(_sem()) == []


@pytest.mark.parametrize("overrides,expected", [
    ({"id": ""}, sem.ISSUE_ID_MISSING),
    ({"start_date": None}, sem.ISSUE_START_MISSING),
    ({"start_date": ""}, sem.ISSUE_START_MISSING),
    ({"start_date": "2026/02/23"}, sem.ISSUE_START_UNPARSABLE),
    ({"start_date": "1999-01-01"}, sem.ISSUE_START_OUT_OF_RANGE),
    ({"total_weeks": None}, sem.ISSUE_TOTAL_MISSING),
    ({"total_weeks": 0}, sem.ISSUE_TOTAL_OUT_OF_RANGE),
    ({"total_weeks": 99}, sem.ISSUE_TOTAL_OUT_OF_RANGE),
    ({"period_count": 0}, sem.ISSUE_PERIOD_OUT_OF_RANGE),
    ({"period_count": 20}, sem.ISSUE_PERIOD_OUT_OF_RANGE),
])
def test_validate_semester_reports_each_issue(overrides, expected) -> None:
    assert expected in sem.validate_semester(_sem(**overrides))


def test_parse_date_accepts_datetime_and_rejects_garbage() -> None:
    assert sem.parse_date("2026-02-23") == date(2026, 2, 23)
    assert sem.parse_date("2026-02-23T08:00") == date(2026, 2, 23)
    assert sem.parse_date("不是日期") is None
    assert sem.parse_date(None) is None


def test_validate_all_reports_model_and_course_level_issues() -> None:
    semesters = [_sem(id="a"), _sem(id="a", start_date="2026-08-31")]   # 重复 id + 不重叠
    report = sem.validate_all(semesters, "missing", [])
    assert sem.ISSUE_DUPLICATE_IDS in report["model"]
    assert sem.ISSUE_CURRENT_MISSING in report["model"]

    overlap = sem.validate_all([_sem(id="a"), _sem(id="b", start_date="2026-03-01")], "a", [])
    assert sem.ISSUE_OVERLAP in overlap["model"]

    no_semester = sem.validate_all([], "", [{"id": "c1"}])
    assert sem.ISSUE_NO_SEMESTER in no_semester["model"]


def test_single_period_slot_is_valid() -> None:
    """`end` 是**闭区间**：单节连堂写 `start == end`（真实数据就是这样）。

    回归：曾按 `start < end` 校验 → 用户 24 门单节课被**全部误报**为"节次无效"。
    """
    assert sem.validate_courses(
        [{"day_of_week": 1, "time_slots": [{"start": 1, "end": 1}]}], 16, 5) == []
    assert sem.validate_courses(
        [{"day_of_week": 1, "time_slots": [{"start": 1, "end": 2}]}], 16, 5) == []


def test_validate_courses_flags_bad_rows() -> None:
    assert sem.validate_courses([{"weeks": {"start": 1, "end": 99}}], 20, 5) \
        == [sem.ISSUE_COURSE_WEEKS]
    assert sem.validate_courses([{"day_of_week": 9}], 20, 5) == [sem.ISSUE_COURSE_DAY]
    assert sem.validate_courses([{"day_of_week": 1, "time_slots": []}], 20, 5) \
        == [sem.ISSUE_COURSE_SLOTS]
    assert sem.validate_courses([{"day_of_week": 1, "time_slots": [{"start": 3, "end": 2}]}],
                                20, 5) == [sem.ISSUE_COURSE_SLOTS]
    assert sem.validate_courses([{"day_of_week": 1, "time_slots": [{"start": 1, "end": 9}]}],
                                20, 5) == [sem.ISSUE_COURSE_SLOTS]
    assert sem.validate_courses([{"day_of_week": 1, "time_slots": [{"start": 1, "end": 2}]}],
                                20, 5) == []


# ── 状态判定（纯函数）───────────────────────────────────────

def test_status_none_without_semester() -> None:
    status = sem.semester_status(None, date(2026, 3, 1))
    assert status["state"] == sem.STATE_NONE
    assert status["week"] is None


def test_status_invalid_when_start_date_unparsable() -> None:
    status = sem.semester_status(_sem(start_date="坏数据"), date(2026, 3, 1))
    assert status["state"] == sem.STATE_INVALID
    assert status["week"] is None
    assert sem.ISSUE_START_UNPARSABLE in status["issues"]


def test_status_not_started_before_term() -> None:
    status = sem.semester_status(_sem(start_date="2026-03-02"), date(2026, 2, 20))
    assert status["state"] == sem.STATE_NOT_STARTED
    assert status["week"] is None


def test_status_active_computes_week_and_days_left() -> None:
    start = date(2026, 2, 23)
    status = sem.semester_status(_sem(start_date=start.isoformat()), start + timedelta(days=10))
    assert status["state"] == sem.STATE_ACTIVE
    assert status["week"] == 2
    assert status["total_weeks"] == 20
    assert status["exam_weeks"] == sem.DEFAULT_EXAM_WEEKS
    assert status["teaching_end_date"] == start + timedelta(days=20 * 7 - 1)
    assert status["end_date"] == start + timedelta(days=21 * 7 - 1)     # 含期末周
    assert status["days_left"] == 21 * 7 - 1 - 10


def test_status_exam_week_after_teaching_weeks() -> None:
    """教学周上完后是**期末周**（状态 `exam`），此时不上课。"""
    start = date(2026, 9, 21)
    semester = _sem(start_date=start.isoformat(), total_weeks=16, exam_weeks=1)
    during_exam = start + timedelta(days=16 * 7 + 1)
    status = sem.semester_status(semester, during_exam)
    assert status["state"] == sem.STATE_EXAM
    assert status["week"] == 16                     # 仍显示最后一周的课表
    assert sem.week_number_for(semester, during_exam) is None


def test_status_expired_only_after_exam_weeks() -> None:
    start = date(2026, 9, 21)
    semester = _sem(start_date=start.isoformat(), total_weeks=16, exam_weeks=1)
    assert sem.semester_status(semester, start + timedelta(days=17 * 7 - 1))["state"] \
        == sem.STATE_EXAM
    assert sem.semester_status(semester, start + timedelta(days=17 * 7))["state"] \
        == sem.STATE_EXPIRED


def test_autumn_semester_matches_user_example() -> None:
    """用户口径：秋季 9/21 起、16 教学周 → 第 16 周周五 = 次年 1/8，之后进入期末周。"""
    start = date(2026, 9, 21)
    assert start.isoweekday() == 1
    last_class = start + timedelta(days=16 * 7 - 3)          # 第 16 周周五
    assert last_class == date(2027, 1, 8)
    semester = _sem(start_date=start.isoformat(), total_weeks=16, exam_weeks=1)
    assert sem.semester_status(semester, last_class)["state"] == sem.STATE_ACTIVE
    assert sem.semester_status(semester, last_class + timedelta(days=3))["state"] \
        == sem.STATE_EXAM


def test_season_start_presets() -> None:
    assert sem.season_start_for(date(2026, 10, 16)) == date(2026, 9, 21)   # 秋季
    assert sem.season_start_for(date(2027, 3, 1)) == date(2027, 3, 2)      # 春季
    assert sem.season_start_for(date(2027, 7, 1)) == date(2027, 9, 21)     # 7 月起算秋季


def test_status_expired_clamps_week_to_total() -> None:
    """回归：学期过期后**不能**再显示"第 32 / 16 周"这种没意义的周次。"""
    start = date(2026, 2, 23)
    status = sem.semester_status(_sem(start_date=start.isoformat()),
                                 start + timedelta(days=32 * 7))
    assert status["state"] == sem.STATE_EXPIRED
    assert status["week"] == 20
    assert status["days_left"] < 0


def test_week_number_for_is_unclamped() -> None:
    """取课表用的周次：超出总周数要返回 None（不是钳到总周数）。"""
    start = date(2026, 2, 23)
    semester = _sem(start_date=start.isoformat())
    assert sem.week_number_for(semester, start) == 1
    assert sem.week_number_for(semester, start + timedelta(days=7)) == 2
    assert sem.week_number_for(semester, start - timedelta(days=1)) is None   # 未开学
    assert sem.week_number_for(semester, start + timedelta(days=21 * 7)) is None  # 超出
    assert sem.week_number_for(None, start) is None


# ── CourseModel 集成 ────────────────────────────────────────

def test_model_does_not_crash_on_broken_semester(tmp_path) -> None:
    """坏数据不能把界面搞崩（旧代码 `date.fromisoformat` 会直接抛）。"""
    model = CourseModel(tmp_path / "courses.json")
    model._data["semesters"] = [{"id": "bad", "start_date": "xx", "total_weeks": 20}]
    model._data["current_semester"] = "bad"
    model.add_course({"name": "高数", "day_of_week": 1,
                      "time_slots": [{"start": 1, "end": 2}]})

    assert model.semester_status()["state"] == sem.STATE_INVALID
    assert model.current_week() is None
    assert model.get_courses_for_date(date.today()) == []
    assert model.get_courses_for_day(1, 1)  # 直接按周次取仍然可用


def test_model_repairs_missing_fields_and_picks_current(tmp_path) -> None:
    model = CourseModel(tmp_path / "courses.json")
    model._data["semesters"] = [
        {"id": "old", "start_date": "2020-02-24"},
        {"id": "new", "start_date": date.today().isoformat()},
    ]
    model._data["current_semester"] = "不存在的 id"
    model._repair_semesters()

    assert model.current_semester == "new"                     # 今天所在的学期优先
    for s in model.semesters:
        assert s["total_weeks"] == sem.DEFAULT_TOTAL_WEEKS     # 缺省值已补
        assert s["period_count"] == sem.DEFAULT_PERIOD_COUNT


def test_model_create_and_switch_semester(tmp_path) -> None:
    model = CourseModel(tmp_path / "courses.json")
    sid = model.create_semester("2026 秋", date(2026, 8, 31), total_weeks=18, period_count=6)
    assert model.current_semester == sid
    assert model.get_period_count() == 6
    assert model.semester_status()["total_weeks"] == 18

    assert model.set_current_semester("不存在") is False
    assert model.set_current_semester(sid) is True


def test_model_validate_reports_issues(tmp_path) -> None:
    model = CourseModel(tmp_path / "courses.json")
    model._data["semesters"] = [{"id": "s", "start_date": "2026-02-23", "total_weeks": 20}]
    model._data["current_semester"] = "s"
    model._data["courses"] = [{"id": "c_001", "name": "坏课", "day_of_week": 9}]
    report = model.validate()
    assert sem.ISSUE_COURSE_DAY in report["courses"]
