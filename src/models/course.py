"""Course and semester data model."""

from datetime import date, datetime, time, timedelta
from pathlib import Path

from src.models.base import BaseJsonModel

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
    def __init__(self, file_path: Path):
        super().__init__(file_path, DEFAULT_COURSES)
        self._repair_semesters()

    def _repair_semesters(self) -> None:
        changed = False
        for i, s in enumerate(self._data.get("semesters", [])):
            if "id" not in s:
                s["id"] = s.get("name", f"sem_{i + 1}")
                changed = True
        if changed:
            self.save()

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
            return semester.get("period_count", 5)
        return 5

    def add_course(self, course: dict) -> str:
        courses = self._data.setdefault("courses", [])
        course["id"] = course.get("id", f"c_{len(courses) + 1:03d}")
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
        if parity == "even" and week_number % 2 == 1:
            return False

        return True

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
        sid = semester_id or self.current_semester
        semester = self.get_semester(sid)
        if not semester:
            return []
        start = date.fromisoformat(semester["start_date"])
        delta = (target - start).days
        if delta < 0:
            return []
        week_number = delta // 7 + 1
        total = semester.get("total_weeks", 20)
        if week_number > total:
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

    @property
    def active_courses(self) -> list[dict]:
        """Courses whose week range includes the current week."""
        today = schedule_date()
        semester = self.get_semester(self.current_semester)
        if not semester:
            return self.courses
        start = date.fromisoformat(semester["start_date"])
        delta = (today - start).days
        current_week = max(1, delta // 7 + 1) if delta >= 0 else 1

        result = []
        for c in self.courses:
            if self._is_active_week(c, current_week):
                result.append(c)
        return result
