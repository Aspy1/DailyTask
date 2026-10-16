"""某学期的课程表数据模型（含节假日）。

**文件**：`data/semesters/<学期id>/courses.json` —— 一个学期一份（切换学期就换文件）。

**与学期元信息的关系**：学期列表 / 当前学期 / 状态 / 周次 / 体检都在
`SemesterRegistry`（`data/semesters.json`）。本类保留**同名转发方法**，
这样调用方（界面 / AI / 脚本）不必区分"课程"与"学期"两个模型；
但**新建/切换学期**只能走 `DataManager`（它还要把模型重定向到新学期的文件）。
"""

from datetime import date
from pathlib import Path

from src.models.base import BaseJsonModel, next_id
from src.models.course_rules import conflicts_by_cell, find_conflicts, is_active_week
from src.models.semester_registry import SemesterRegistry

DEFAULT_COURSES = {
    "_version": 1,
    "courses": [],
    "holidays": {"excluded": [], "makeup": {}},
}

# Period time definitions: (start_time_str, end_time_str)
PERIOD_TIMES = [
    ("08:30", "10:05"),
    ("10:25", "12:00"),
    ("13:30", "15:05"),
    ("15:25", "17:00"),
    ("18:30", "20:05"),
    ("20:10", "21:45"),
]


class CourseModel(BaseJsonModel):
    def __init__(self, file_path: Path, registry: SemesterRegistry | None = None) -> None:
        super().__init__(file_path, DEFAULT_COURSES)
        self._registry = registry

    # ── 学期元信息（转发给注册表；`registry` 缺省时退化为"无学期"）──

    @property
    def semesters(self) -> list[dict]:
        return self._registry.semesters if self._registry else []

    @property
    def current_semester(self) -> str:
        return self._registry.current_semester if self._registry else ""

    def get_semester(self, semester_id: str) -> dict | None:
        return self._registry.get_semester(semester_id) if self._registry else None

    def semester_status(self, semester_id: str | None = None,
                        today: date | None = None) -> dict:
        if self._registry is None:
            from src.models.semester import STATE_NONE

            return {"state": STATE_NONE, "week": None, "total_weeks": None,
                    "exam_weeks": None, "period_count": None, "start_date": None,
                    "teaching_end_date": None, "end_date": None, "days_left": None,
                    "issues": []}
        return self._registry.status(semester_id, today)

    def current_week(self) -> int | None:
        return self._registry.current_week() if self._registry else None

    def get_period_count(self) -> int:
        if self._registry is None:
            from src.models.semester import DEFAULT_PERIOD_COUNT

            return DEFAULT_PERIOD_COUNT
        return self._registry.period_count()

    def validate(self) -> dict:
        if self._registry is None:
            return {"semesters": {}, "model": [], "courses": []}
        return self._registry.validate(self.courses)

    # ── 课程 ────────────────────────────────────────────────

    @property
    def courses(self) -> list[dict]:
        return self._data.get("courses", [])

    def add_course(self, course: dict) -> str:
        courses = self._data.setdefault("courses", [])
        course["id"] = course.get("id") or next_id("c", (c.get("id", "") for c in courses))
        course.setdefault("weeks", {"start": 1, "end": 20})
        course.setdefault("week_parity", "all")
        course.setdefault("day_of_week", 1)

        slots = course.get("time_slots", [])
        global_location = course.get("location", "")
        for slot in slots:
            slot.setdefault("location", global_location)

        courses.append(course)
        return course["id"]

    @staticmethod
    def get_teacher(course: dict, week: int | None = None) -> str:
        schedules = course.get("teacher_schedule")
        if schedules and week is not None:
            for ts in schedules:
                weeks = ts.get("weeks", {})
                w_start = weeks.get("start", 1)
                w_end = weeks.get("end", 20)
                if w_start <= week <= w_end:
                    return ts.get("name", "")
        return course.get("teacher", "")

    def update_course(self, course_id: str, changes: dict) -> bool:
        for course in self._data.get("courses", []):
            if course["id"] == course_id:
                course.update(changes)
                return True
        return False

    def delete_course(self, course_id: str) -> bool:
        courses = self._data.get("courses", [])
        for i, course in enumerate(courses):
            if course["id"] == course_id:
                courses.pop(i)
                return True
        return False

    def _is_active_week(self, course: dict, week_number: int) -> bool:
        """该课程第 `week_number` 周是否上课（规则见 `models/course_rules.py`）。"""
        return is_active_week(course, week_number)

    def get_courses_for_day(self, day_of_week: int, week_number: int) -> list[dict]:
        result = []
        for course in self._data.get("courses", []):
            if course.get("day_of_week") != day_of_week:
                continue
            if not self._is_active_week(course, week_number):
                continue
            result.append(course)
        result.sort(key=lambda c: c.get("time_slots", [{"start": 0}])[0]["start"])
        return result

    def get_today_courses(self) -> list[dict]:
        from src.models.course import schedule_date

        return self.get_courses_for_date(schedule_date())

    def get_courses_for_date(self, target: date) -> list[dict]:
        """某天的课；学期缺失/不合法/未开学/超出总周数/期末周 → 无课。"""
        week_number = self._registry.week_number_for(target) if self._registry else None
        if week_number is None:
            return []

        holidays = self._data.get("holidays", {})
        target_str = target.isoformat()
        if target_str in holidays.get("excluded", []):
            return []
        makeup = holidays.get("makeup", {})
        day_of_week = makeup.get(target_str, target.isoweekday())
        return self.get_courses_for_day(day_of_week, week_number)

    # ── 冲突（同一时段两门课）────────────────────────────────

    def find_conflicts(self, week: int | None = None) -> list[dict]:
        target = week if week is not None else self.current_week()
        if target is None:
            return []
        return find_conflicts(self.courses, target, self.get_period_count())

    def conflicts_by_cell(self, week: int) -> dict[tuple[int, int], list[dict]]:
        return conflicts_by_cell(self.courses, week, self.get_period_count())

    # ── Holidays ───────────────────────────────────────────

    def add_holiday(self, excluded: list[str], makeup: dict[str, int]) -> None:
        """Record holidays. excluded: [\"2026-06-05\", ...], makeup: {\"2026-06-13\": 5} (date→day_of_week)."""
        holidays = self._data.setdefault("holidays", {"excluded": [], "makeup": {}})
        for day in excluded:
            if day not in holidays["excluded"]:
                holidays["excluded"].append(day)
        holidays["makeup"].update(makeup)

    def clear_holidays(self) -> None:
        self._data["holidays"] = {"excluded": [], "makeup": {}}

    @property
    def holidays(self) -> dict:
        return self._data.get("holidays", {"excluded": [], "makeup": {}})


def schedule_date() -> date:
    """Effective date: 0:00–1:00 AM still counts as the previous day."""
    from datetime import datetime, timedelta

    now = datetime.now()
    if now.hour < 1:
        return (now - timedelta(days=1)).date()
    return now.date()
