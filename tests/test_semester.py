"""学期数据的合法性检测与状态判定（`src/models/semester.py` + `CourseModel`）。

背景：周次计算此前散在 5 处、口径各不相同 —— 状态栏不钳上界（学期过期后显示
"第 32 / 16 周"）、AI 忽略 `current_semester`、邮件摘要又是第三套算法。
这里把"检测"与"状态"钉住。
"""

from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from src.models import semester as sem

if TYPE_CHECKING:
    from src.models.course import CourseModel
    from src.models.semester_registry import SemesterRegistry


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


def test_courses_out_of_week_range_names_the_courses() -> None:
    """周次超范围要**点名**：光有问题码，用户面对 20 多门课找不到是哪门。

    与 `validate_courses` 同源（共用 `_weeks_out_of_range`）——两者必须同时报/不报。
    """
    courses = [
        {"name": "高数", "weeks": {"start": 1, "end": 18}},
        {"name": "英语", "weeks": {"start": 1, "end": 16}},
        {"id": "c3", "weeks": {"start": 1, "end": 99}},
    ]
    assert sem.courses_out_of_week_range(courses, 16) == ["高数", "c3"]
    assert sem.courses_out_of_week_range(courses, None) == []       # 没学期就不判
    assert sem.validate_courses(courses, 16, 5).count(sem.ISSUE_COURSE_WEEKS) == 2


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


# ── 注册表 + 模型（学期元信息 vs 按学期的数据）────────────────

def _registry(tmp_path: Path) -> "SemesterRegistry":
    from src.models.semester_registry import SemesterRegistry

    return SemesterRegistry(tmp_path / "semesters.json")


def _model(tmp_path: Path, registry: "SemesterRegistry") -> "CourseModel":
    from src.models.course import CourseModel

    return CourseModel(tmp_path / "courses.json", registry)


def test_model_does_not_crash_on_broken_semester(tmp_path) -> None:
    """坏数据不能把界面搞崩（旧代码 `date.fromisoformat` 会直接抛）。"""
    registry = _registry(tmp_path)
    registry._data["semesters"] = [{"id": "bad", "start_date": "xx", "total_weeks": 20}]
    registry._data["current_semester"] = "bad"
    model = _model(tmp_path, registry)
    model.add_course({"name": "高数", "day_of_week": 1,
                      "time_slots": [{"start": 1, "end": 2}]})

    assert model.semester_status()["state"] == sem.STATE_INVALID
    assert model.current_week() is None
    assert model.get_courses_for_date(date.today()) == []
    assert model.get_courses_for_day(1, 1)  # 直接按周次取仍然可用


def test_registry_repairs_missing_fields_and_picks_current(tmp_path) -> None:
    registry = _registry(tmp_path)
    registry._data["semesters"] = [
        {"id": "old", "start_date": "2020-02-24"},
        {"id": "new", "start_date": date.today().isoformat()},
    ]
    registry._data["current_semester"] = "不存在的 id"
    registry.repair()

    assert registry.current_semester == "new"                  # 今天所在的学期优先
    for semester in registry.semesters:
        assert semester["total_weeks"] == sem.DEFAULT_TOTAL_WEEKS
        assert semester["period_count"] == sem.DEFAULT_PERIOD_COUNT
        assert semester["exam_weeks"] == sem.DEFAULT_EXAM_WEEKS


def test_registry_create_and_switch(tmp_path) -> None:
    registry = _registry(tmp_path)
    sid = registry.create_semester("2026 秋", date(2026, 8, 31),
                                   total_weeks=18, period_count=6)
    assert registry.current_semester == sid
    assert registry.period_count() == 6
    assert registry.status()["total_weeks"] == 18
    assert registry.set_current_semester("不存在") is False
    assert registry.set_current_semester(sid) is True


def test_model_validate_reports_issues(tmp_path) -> None:
    registry = _registry(tmp_path)
    registry._data["semesters"] = [{"id": "s", "start_date": "2026-02-23", "total_weeks": 20}]
    registry._data["current_semester"] = "s"
    model = _model(tmp_path, registry)
    model._data["courses"] = [{"id": "c_001", "name": "坏课", "day_of_week": 9}]
    report = model.validate()
    assert sem.ISSUE_COURSE_DAY in report["courses"]


# ── DataManager：切换学期 = 换一份数据文件 ──────────────────

def test_switch_semester_switches_data_files(tmp_path, qapp) -> None:
    """**本次改动的核心**：切学期要换课程/作业/考试的数据，而不是只改周次映射。"""
    from src.services.data_manager import DataManager

    dm = DataManager(tmp_path)
    dm.courses.add_course({"name": "高数", "day_of_week": 1,
                           "time_slots": [{"start": 1, "end": 1}]})
    dm.courses.save()
    dm.tasks.add({"title": "作业A", "due_date": "2026-12-01"})
    dm.tasks.save()
    first = dm.semesters.current_semester
    assert len(dm.courses.courses) == 1

    second = dm.create_semester("新学期", date(2027, 3, 2))
    assert second != first
    assert dm.courses.courses == []          # 新学期从**空白**开始
    assert dm.tasks.tasks == []
    assert dm.courses.file_path.parent.name == second
    assert (tmp_path / "semesters" / first / "courses.json").exists()   # 旧学期文件仍在

    assert dm.switch_semester(first) is True
    assert len(dm.courses.courses) == 1      # 切回去，数据还在
    assert len(dm.tasks.tasks) == 1


def test_shared_data_survives_semester_switch(tmp_path, qapp) -> None:
    """有什么 / 记账 / 习惯 / 日程计划 跨学期**继承**。"""
    from src.services.data_manager import DataManager

    dm = DataManager(tmp_path)
    dm.inventory.add_item({"name": "洗发水", "category": "日常消耗品"})
    dm.inventory.save()
    dm.expenses.add({"amount": 12, "category": "food"})
    dm.expenses.save()
    dm.habits.add_habit({"name": "跑步"})
    dm.habits.save()
    dm.daily_logs.add_plan({"title": "复习", "time_slot": 3}, day="2027-03-02")
    dm.daily_logs.save()

    dm.create_semester("新学期", date(2027, 3, 2))

    assert dm.inventory.items                # 有什么：继承
    assert dm.expenses.records               # 记账：继承
    assert dm.habits.habits                  # 习惯：继承
    assert dm.daily_logs.get_plans("2027-03-02")   # 日程计划：继承


def test_migration_from_legacy_layout(tmp_path, qapp) -> None:
    """旧布局（courses.json 里同时放学期与课程）→ 按学期分文件（幂等）。"""
    import json

    from src.models import semester_paths
    from src.services.data_manager import DataManager

    legacy = {
        "_version": 3,
        "semesters": [{"id": "s1", "name": "旧学期", "start_date": "2026-03-09",
                       "total_weeks": 16, "period_count": 5}],
        "current_semester": "s1",
        "courses": [{"id": "c_001", "name": "高数", "day_of_week": 1,
                     "time_slots": [{"start": 1, "end": 1}]}],
        "holidays": {"excluded": ["2026-04-06"], "makeup": {}},
    }
    (tmp_path / "courses.json").write_text(json.dumps(legacy, ensure_ascii=False),
                                           encoding="utf-8")
    (tmp_path / "tasks.json").write_text(
        json.dumps({"_version": 2, "tasks": [{"id": "t_001", "title": "旧作业"}],
                    "archived": []}), encoding="utf-8")
    (tmp_path / "exams.json").write_text(
        json.dumps({"_version": 1, "exams": [{"id": "e_001", "course_name": "高数"}]}),
        encoding="utf-8")

    dm = DataManager(tmp_path)

    assert dm.semesters.current_semester == "s1"
    assert [c["name"] for c in dm.courses.courses] == ["高数"]
    assert [t["title"] for t in dm.tasks.tasks] == ["旧作业"]
    assert len(dm.exams.exams) == 1
    assert dm.courses.holidays["excluded"] == ["2026-04-06"]
    # 旧文件已清理，新布局就位
    assert not (tmp_path / "courses.json").exists()
    assert not (tmp_path / "tasks.json").exists()
    assert (tmp_path / "semesters" / "s1" / "courses.json").exists()
    # 幂等：再跑一次不会重复迁移
    assert semester_paths.migrate_legacy(tmp_path) is False
