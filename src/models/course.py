"""Course and semester data model."""

from datetime import date, datetime, timedelta
from pathlib import Path

from src.models.base import BaseJsonModel, next_id
from src.models.semester import (
    DEFAULT_PERIOD_COUNT,
    DEFAULT_TOTAL_WEEKS,
    as_int,
    parse_date,
    validate_all,
    week_number_for,
)
from src.models.semester import semester_status as _semester_status


def schedule_date() -> date:
    """Effective date: 0:00–1:00 AM still counts as the previous day."""
    now = datetime.now()
    if now.hour < 1:
        return (now - timedelta(days=1)).date()
    return now.date()


# Period time definitions: (start_time_str, end_time_str)
PERIOD_TIMES = [
    ("08:30", "10:05"),
    ("10:25", "12:00"),
    ("13:30", "15:05"),
    ("15:25", "17:00"),
    ("18:30", "20:05"),
    ("20:10", "21:45"),
]


DEFAULT_COURSES = {
    "_version": 3,
    "semesters": [],
    "current_semester": "",
    "courses": [],
    "holidays": {"excluded": [], "makeup": {}},
}


class CourseModel(BaseJsonModel):
    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_COURSES)
        self._repair_semesters()

    def _repair_semesters(self) -> None:
        """幂等自愈：只补**能安全推断**的字段，不猜 `start_date`。

        猜不出的一律不动（由 `validate()` 报出来让用户改），避免"自愈"把数据改坏。
        """
        changed = False
        for i, semester in enumerate(self._data.get("semesters", [])):
            changed |= self._repair_semester_fields(semester, i)

        # current_semester 指向不存在的学期 → 选一个最合理的（今天所在的 > 开始日最新的）
        if self.semesters and not self.get_semester(self.current_semester):
            picked = self._pick_semester()
            if picked:
                self._data["current_semester"] = picked.get("id", "")
                changed = True
        if changed:
            self.save()

    @staticmethod
    def _repair_semester_fields(semester: dict, index: int) -> bool:
        """补 id / 总周数 / 每天节次的缺省值；返回是否改动。"""
        changed = False
        if not str(semester.get("id") or "").strip():
            semester["id"] = semester.get("name") or f"sem_{index + 1}"
            changed = True
        if as_int(semester.get("total_weeks")) is None:
            semester["total_weeks"] = DEFAULT_TOTAL_WEEKS
            changed = True
        if as_int(semester.get("period_count")) is None:
            semester["period_count"] = DEFAULT_PERIOD_COUNT
            changed = True
        return changed

    def _pick_semester(self) -> dict | None:
        """挑一个最合理的学期：今天落在其区间内的优先，否则取开始日最新的。"""
        today = schedule_date()
        spans = []
        for s in self.semesters:
            start = parse_date(s.get("start_date"))
            total = as_int(s.get("total_weeks")) or DEFAULT_TOTAL_WEEKS
            if start is None:
                continue
            spans.append((start, start + timedelta(days=total * 7 - 1), s))
        for start, end, semester in spans:
            if start <= today <= end:
                return semester
        return max(spans, key=lambda item: item[0])[2] if spans else None

    @property
    def semesters(self) -> list[dict]:
        return self._data.get("semesters", [])

    @property
    def current_semester(self) -> str:
        return self._data.get("current_semester", "")

    @current_semester.setter
    def current_semester(self, value: str) -> None:
        self._data["current_semester"] = value

    @property
    def courses(self) -> list[dict]:
        return self._data.get("courses", [])

    def get_semester(self, semester_id: str) -> dict | None:
        if not semester_id:
            return None
        for s in self.semesters:
            if s.get("id") == semester_id:
                return s
        return None

    def get_period_count(self) -> int:
        semester = self.get_semester(self.current_semester)
        if semester:
            return as_int(semester.get("period_count")) or DEFAULT_PERIOD_COUNT
        return DEFAULT_PERIOD_COUNT

    # ── 学期状态与体检（唯一口径，见 models/semester.py）─────────

    def semester_status(self, semester_id: str | None = None,
                        today: date | None = None) -> dict:
        """当前（或指定）学期状态：`{state, week, total_weeks, ...}`。"""
        sid = self.current_semester if semester_id is None else semester_id
        return _semester_status(self.get_semester(sid), today or schedule_date())

    def validate(self) -> dict:
        """学期/课程数据体检：返回问题码（UI 负责翻译成文案）。"""
        return validate_all(self.semesters, self.current_semester, self.courses)

    def current_week(self) -> int | None:
        """当前教学周；未开学/已结束/数据不合法时为 None（**不猜**）。"""
        return self.semester_status()["week"]

    def create_semester(self, name: str, start: date, total_weeks: int = DEFAULT_TOTAL_WEEKS,
                        period_count: int = DEFAULT_PERIOD_COUNT,
                        make_current: bool = True) -> str:
        """新建学期并（默认）设为当前。"""
        semesters = self._data.setdefault("semesters", [])
        sid = next_id("sem", (str(s.get("id") or "") for s in semesters))
        semesters.append({
            "id": sid,
            "name": name or sid,
            "start_date": start.isoformat(),
            "total_weeks": max(1, min(int(total_weeks), 30)),
            "period_count": max(1, min(int(period_count), 12)),
        })
        if make_current:
            self._data["current_semester"] = sid
        return sid

    def set_current_semester(self, semester_id: str) -> bool:
        """切换当前学期；目标不存在返回 False。"""
        if self.get_semester(semester_id) is None:
            return False
        self._data["current_semester"] = semester_id
        return True

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
                ws = ts.get("weeks", {})
                w_start = ws.get("start", 1)
                w_end = ws.get("end", 20)
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
        weeks = course.get("weeks", {})
        if weeks:
            w_start = weeks.get("start", 1)
            w_end = weeks.get("end", 20)
            if week_number < w_start or week_number > w_end:
                return False

        excluded = course.get("excluded_weeks", [])
        if week_number in excluded:
            return False

        parity = course.get("week_parity", "all")
        if parity == "odd" and week_number % 2 == 0:
            return False
        return not (parity == "even" and week_number % 2 == 1)

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

    def get_today_courses(self, semester_id: str | None = None) -> list[dict]:
        return self.get_courses_for_date(schedule_date(), semester_id)

    def get_courses_for_date(self, target: date, semester_id: str | None = None) -> list[dict]:
        sid = self.current_semester if semester_id is None else semester_id
        # 统一口径 + 坏数据不抛异常：学期缺失/不合法/未开学/超出总周数 → 无课
        week_number = week_number_for(self.get_semester(sid), target)
        if week_number is None:
            return []

        holidays = self._data.get("holidays", {})
        target_str = target.isoformat()

        # Excluded date → no courses
        if target_str in holidays.get("excluded", []):
            return []

        # Makeup date → use the mapped day_of_week
        makeup = holidays.get("makeup", {})
        day_of_week = makeup.get(target_str, target.isoweekday())

        return self.get_courses_for_day(day_of_week, week_number)

    # ── Holidays ───────────────────────────────────────────

    def add_holiday(self, excluded: list[str], makeup: dict[str, int]) -> None:
        """Record holidays. excluded: [\"2026-06-05\", ...], makeup: {\"2026-06-13\": 5} (date→day_of_week)."""
        h = self._data.setdefault("holidays", {"excluded": [], "makeup": {}})
        for d in excluded:
            if d not in h["excluded"]:
                h["excluded"].append(d)
        h["makeup"].update(makeup)

    def clear_holidays(self) -> None:
        """Clear all holiday/makeup records."""
        self._data["holidays"] = {"excluded": [], "makeup": {}}

    @property
    def holidays(self) -> dict:
        return self._data.get("holidays", {"excluded": [], "makeup": {}})
