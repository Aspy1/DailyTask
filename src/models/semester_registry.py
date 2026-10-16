"""学期**注册表**（`data/semesters.json`）：学期列表 + 当前学期 + 状态/体检。

为什么单独成文件：课程表/作业/考试是**按学期**分文件的（`data/semesters/<id>/…`），
而"有哪些学期、当前是哪个"必须放在**共享**的地方，否则切学期时连"切到哪"都读不到。

本类承担原来 `CourseModel` 里的全部学期职责（状态、周次、体检、新建/切换）；
`CourseModel` 保留同名转发方法，调用方不必区分"课程"与"学期"两个模型。
"""

from datetime import date, timedelta
from pathlib import Path

from src.models.base import BaseJsonModel, next_id
from src.models.coerce import as_int, parse_date
from src.models.semester import (
    DEFAULT_EXAM_WEEKS,
    DEFAULT_PERIOD_COUNT,
    DEFAULT_SEMESTER_ID,
    DEFAULT_TOTAL_WEEKS,
    MAX_EXAM_WEEKS,
    MAX_PERIOD_COUNT,
    MAX_TOTAL_WEEKS,
    MIN_PERIOD_COUNT,
    MIN_TOTAL_WEEKS,
    default_semester,
    validate_all,
    week_number_for,
)
from src.models.semester import semester_status as _semester_status

DEFAULT_REGISTRY = {
    "_version": 1,
    "semesters": [],
    "current_semester": "",
}


class SemesterRegistry(BaseJsonModel):
    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_REGISTRY)
        self.repair()

    # ── 读写 ────────────────────────────────────────────────

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
    def current(self) -> dict | None:
        return self.get_semester(self.current_semester)

    def get_semester(self, semester_id: str) -> dict | None:
        if not semester_id:
            return None
        for semester in self.semesters:
            if semester.get("id") == semester_id:
                return semester
        return None

    # ── 自愈 ────────────────────────────────────────────────

    def repair(self) -> None:
        """幂等自愈：只补**能安全推断**的字段，不猜 `start_date`。"""
        changed = False
        for index, semester in enumerate(self.semesters):
            changed |= self._repair_fields(semester, index)
        if self.semesters and not self.get_semester(self.current_semester):
            picked = self.pick_semester()
            if picked:
                self.current_semester = picked.get("id", "")
                changed = True
        if changed:
            self.save()

    @staticmethod
    def _repair_fields(semester: dict, index: int) -> bool:
        changed = False
        if not str(semester.get("id") or "").strip():
            semester["id"] = semester.get("name") or f"sem_{index + 1}"
            changed = True
        for key, default in (("total_weeks", DEFAULT_TOTAL_WEEKS),
                             ("period_count", DEFAULT_PERIOD_COUNT),
                             ("exam_weeks", DEFAULT_EXAM_WEEKS)):
            if as_int(semester.get(key)) is None:
                semester[key] = default
                changed = True
        return changed

    def pick_semester(self) -> dict | None:
        """挑一个最合理的学期：今天落在其区间内的优先，否则取开始日最新的。"""
        today = date.today()
        spans = []
        for semester in self.semesters:
            start = parse_date(semester.get("start_date"))
            if start is None:
                continue
            total = as_int(semester.get("total_weeks")) or DEFAULT_TOTAL_WEEKS
            exam = as_int(semester.get("exam_weeks")) or 0
            spans.append((start, start + timedelta(days=(total + exam) * 7 - 1), semester))
        for start, end, semester in spans:
            if start <= today <= end:
                return semester
        return max(spans, key=lambda item: item[0])[2] if spans else None

    # ── 新建 / 切换 ─────────────────────────────────────────

    def create_semester(self, name: str, start: date, total_weeks: int = DEFAULT_TOTAL_WEEKS,
                        period_count: int = DEFAULT_PERIOD_COUNT,
                        exam_weeks: int = DEFAULT_EXAM_WEEKS,
                        make_current: bool = True) -> str:
        semesters = self._data.setdefault("semesters", [])
        sid = next_id("sem", (str(s.get("id") or "") for s in semesters))
        semesters.append({
            "id": sid,
            "name": name or sid,
            "start_date": start.isoformat(),
            "total_weeks": max(MIN_TOTAL_WEEKS, min(int(total_weeks), MAX_TOTAL_WEEKS)),
            "period_count": max(MIN_PERIOD_COUNT, min(int(period_count), MAX_PERIOD_COUNT)),
            "exam_weeks": max(0, min(int(exam_weeks), MAX_EXAM_WEEKS)),
        })
        if make_current:
            self.current_semester = sid
        return sid

    def set_current_semester(self, semester_id: str) -> bool:
        """只改注册表里的指针；**按学期的模型重定向由 `DataManager.switch_semester()` 负责**。"""
        if self.get_semester(semester_id) is None:
            return False
        self.current_semester = semester_id
        return True

    # ── 状态 / 周次 / 体检 ──────────────────────────────────

    def status(self, semester_id: str | None = None, today: date | None = None) -> dict:
        sid = self.current_semester if semester_id is None else semester_id
        return _semester_status(self.get_semester(sid), today or date.today())

    def current_week(self) -> int | None:
        return self.status()["week"]

    def period_count(self) -> int:
        semester = self.current
        return (as_int(semester.get("period_count")) if semester else None) or DEFAULT_PERIOD_COUNT

    def week_number_for(self, target: date) -> int | None:
        return week_number_for(self.current, target)

    def ensure_default(self) -> str:
        """保证存在当前学期（没有就建一个默认的）；返回其 id。幂等。"""
        if self.get_semester(self.current_semester):
            return self.current_semester
        if not self.semesters:
            self._data["semesters"] = [default_semester()]
        picked = self.pick_semester() or self.semesters[0]
        self.current_semester = picked.get("id") or DEFAULT_SEMESTER_ID
        return self.current_semester

    def validate(self, courses: list[dict] | None = None) -> dict:
        return validate_all(self.semesters, self.current_semester, courses or [])
