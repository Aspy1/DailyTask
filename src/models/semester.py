"""学期数据的**合法性检测**与**状态判定**（纯函数：无 Qt、无 IO、无副作用）。

**为什么单独成模块**：周次计算此前散在 5 处，口径各不相同 ——

| 位置 | 旧行为 |
|---|---|
| `MainWindow._update_date`（状态栏） | 只钳下界 → 学期过期后显示 **"第 32 / 16 周"** |
| `CoursePanel._week_number` | 钳上界（与状态栏不一致） |
| `AIService._get_current_week` | **忽略 `current_semester`**，取列表里第一个学期 |
| `CourseModel.active_courses` | 不钳上界 |
| `send_digest._week_number_for` | 超范围返回 None（又一种口径） |

现在统一到这里：模型与脚本都调用它（`CODE_STANDARDS Q-G4` 单一真值）。

**问题码**（`ISSUE_*`）是机器可读的，UI 负责翻译成文案
（`semester.issue.<code>`）—— 模型层不产生用户可见文案（`Q-N5`）。
"""

from datetime import date, timedelta

from src.models.coerce import as_int, parse_date

DEFAULT_TOTAL_WEEKS = 16          # 教学周（用户：每个学期 16 周）
DEFAULT_EXAM_WEEKS = 1            # 期末周（教学周之后）
DEFAULT_PERIOD_COUNT = 5
MIN_TOTAL_WEEKS = 1
MAX_TOTAL_WEEKS = 30
MAX_EXAM_WEEKS = 6
MIN_PERIOD_COUNT = 1
MAX_PERIOD_COUNT = 12
EARLIEST_START = date(2000, 1, 1)
LATEST_START = date(2100, 12, 31)

# 按季节给新学期预设开始日（用户口径：秋季 9/21 起、春季 3/2 起）
AUTUMN_START = (9, 21)
SPRING_START = (3, 2)

# ── 状态 ────────────────────────────────────────────────────
STATE_NONE = "none"                # 没有学期
STATE_INVALID = "invalid"          # 有学期但数据不合法（算不出周次）
STATE_NOT_STARTED = "not_started"  # 尚未开学
STATE_ACTIVE = "active"            # 学期进行中（教学周内）
STATE_EXAM = "exam"                # 期末周（教学周之后、学期结束之前）
STATE_EXPIRED = "expired"          # 学期已结束（含期末周也过了）

# ── 问题码：学期自身 ────────────────────────────────────────
ISSUE_ID_MISSING = "id_missing"
ISSUE_START_MISSING = "start_date_missing"
ISSUE_START_UNPARSABLE = "start_date_unparsable"
ISSUE_START_OUT_OF_RANGE = "start_date_out_of_range"
ISSUE_TOTAL_MISSING = "total_weeks_missing"
ISSUE_TOTAL_OUT_OF_RANGE = "total_weeks_out_of_range"
ISSUE_EXAM_OUT_OF_RANGE = "exam_weeks_out_of_range"
ISSUE_PERIOD_OUT_OF_RANGE = "period_count_out_of_range"

# ── 问题码：模型级 ──────────────────────────────────────────
ISSUE_CURRENT_MISSING = "current_missing"   # current_semester 指向不存在的学期
ISSUE_NO_SEMESTER = "no_semester"           # 有课程却没有任何学期
ISSUE_DUPLICATE_IDS = "duplicate_ids"
ISSUE_OVERLAP = "overlap"

# ── 问题码：课程级 ──────────────────────────────────────────
ISSUE_COURSE_WEEKS = "course_weeks_out_of_range"
ISSUE_COURSE_DAY = "course_day_out_of_range"
ISSUE_COURSE_SLOTS = "course_slots_invalid"

# 这些是"算不出周次"的阻断性问题（其余只是警告）
BLOCKING_ISSUES = frozenset({
    ISSUE_START_MISSING, ISSUE_START_UNPARSABLE, ISSUE_START_OUT_OF_RANGE,
    ISSUE_TOTAL_MISSING, ISSUE_TOTAL_OUT_OF_RANGE,
})


def _start_issues(semester: dict) -> list[str]:
    raw = semester.get("start_date")
    if raw in (None, ""):
        return [ISSUE_START_MISSING]
    start = parse_date(raw)
    if start is None:
        return [ISSUE_START_UNPARSABLE]
    return [] if EARLIEST_START <= start <= LATEST_START else [ISSUE_START_OUT_OF_RANGE]


def _range_issues(value: object, missing: str, out_of_range: str,
                  low: int, high: int) -> list[str]:
    """必填的整数范围检查（缺失 / 越界各给一个码）。"""
    number = as_int(value)
    if number is None:
        return [missing]
    return [] if low <= number <= high else [out_of_range]


def _optional_range_issue(value: object, code: str, low: int, high: int) -> list[str]:
    """选填的整数范围检查（缺失不算错）。"""
    number = as_int(value)
    return [] if number is None or low <= number <= high else [code]


def validate_semester(semester: dict) -> list[str]:
    """学期自身的问题码（空列表 = 合法）。"""
    issues: list[str] = []
    if not str(semester.get("id") or "").strip():
        issues.append(ISSUE_ID_MISSING)
    issues += _start_issues(semester)
    issues += _range_issues(semester.get("total_weeks"), ISSUE_TOTAL_MISSING,
                            ISSUE_TOTAL_OUT_OF_RANGE, MIN_TOTAL_WEEKS, MAX_TOTAL_WEEKS)
    issues += _optional_range_issue(semester.get("period_count"), ISSUE_PERIOD_OUT_OF_RANGE,
                                    MIN_PERIOD_COUNT, MAX_PERIOD_COUNT)
    issues += _optional_range_issue(semester.get("exam_weeks"), ISSUE_EXAM_OUT_OF_RANGE,
                                    0, MAX_EXAM_WEEKS)
    return issues


def end_date_of(start: date, total_weeks: int) -> date:
    """第 `total_weeks` 周的最后一天。"""
    return start + timedelta(days=total_weeks * 7 - 1)


def season_start_for(today: date) -> date:
    """按季节给"新建学期"预设开始日（用户口径：秋 9/21、春 3/2）。

    7–12 月 → 当年 9/21（秋季学期，通常正在进行）；1–6 月 → 当年 3/2（春季学期）。
    **故意不往后推一年**：10 月建学期时默认给"当年 9/21"才是用户所处的那个学期。
    """
    month, day = AUTUMN_START if today.month >= 7 else SPRING_START
    return date(today.year, month, day)


DEFAULT_SEMESTER_ID = "sem_default"
DEFAULT_SEMESTER_NAME = "默认学期"


def default_semester(today: date | None = None) -> dict:
    """全新数据目录用的默认学期（开始日按季节预设）。"""
    return {
        "id": DEFAULT_SEMESTER_ID,
        "name": DEFAULT_SEMESTER_NAME,
        "start_date": season_start_for(today or date.today()).isoformat(),
        "total_weeks": DEFAULT_TOTAL_WEEKS,
        "exam_weeks": DEFAULT_EXAM_WEEKS,
        "period_count": DEFAULT_PERIOD_COUNT,
    }


def semester_status(semester: dict | None, today: date) -> dict:
    """**唯一口径**的学期状态。

    返回：`{state, week, total_weeks, exam_weeks, period_count, start_date,
    teaching_end_date, end_date, days_left, issues}`
    - `state`：`none` / `invalid` / `not_started` / `active` / **`exam`（期末周）** / `expired`
    - `week`：当前教学周（`exam`/`expired` 时是总周数；`not_started`/`invalid`/`none` 时为 `None`）
    - `teaching_end_date`：教学周最后一天；`end_date`：**含期末周**的学期最后一天
    - `days_left`：距学期（含期末周）结束的天数
    """
    status = {
        "state": STATE_NONE, "week": None, "total_weeks": None, "exam_weeks": None,
        "period_count": None, "start_date": None, "teaching_end_date": None,
        "end_date": None, "days_left": None, "issues": [],
    }
    if not semester:
        return status

    issues = validate_semester(semester)
    status["issues"] = issues
    start = parse_date(semester.get("start_date"))
    total = as_int(semester.get("total_weeks"))
    if not _usable(start, total, issues):
        status["state"] = STATE_INVALID
        return status

    period = as_int(semester.get("period_count"))
    exam = as_int(semester.get("exam_weeks"))
    if exam is None or not (0 <= exam <= MAX_EXAM_WEEKS):
        exam = DEFAULT_EXAM_WEEKS
    teaching_end = end_date_of(start, total)
    semester_end = end_date_of(start, total + exam)
    status.update({
        "total_weeks": total,
        "exam_weeks": exam,
        "period_count": period if period and period > 0 else DEFAULT_PERIOD_COUNT,
        "start_date": start,
        "teaching_end_date": teaching_end,
        "end_date": semester_end,
        "days_left": (semester_end - today).days,
    })
    week = (today - start).days // 7 + 1
    if today < start:
        status["state"] = STATE_NOT_STARTED
    elif week <= total:
        status["state"] = STATE_ACTIVE
        status["week"] = max(1, week)
    elif today <= semester_end:
        # 期末周：教学周已上完，仍显示最后一周的课表（不是空白页）
        status["state"] = STATE_EXAM
        status["week"] = total
    else:
        status["state"] = STATE_EXPIRED
        status["week"] = total
    return status


def _usable(start: date | None, total: int | None, issues: list[str]) -> bool:
    """数据是否够用（能算出周次）。"""
    return (start is not None and total is not None
            and MIN_TOTAL_WEEKS <= total <= MAX_TOTAL_WEEKS
            and not any(code in BLOCKING_ISSUES for code in issues))


def week_number_for(semester: dict | None, target: date) -> int | None:
    """目标日期是学期第几周；缺失/不合法/未开学/超出总周数 → None（**不钳制**）。

    与 `semester_status()` 的分工：这里回答"这一天算不算学期内的教学日"（用于取课表），
    那里回答"现在整体处于什么状态"（用于显示，已结束会钳到总周数）。
    """
    status = semester_status(semester, target)
    if status["state"] == STATE_NOT_STARTED or status["week"] is None:
        return None
    start, total = status["start_date"], status["total_weeks"]
    week = (target - start).days // 7 + 1
    return week if 1 <= week <= total else None


def _slots_invalid(slots: list[dict], period_count: int | None) -> bool:
    """节次是否无效。

    ⚠ `end` 是**闭区间**：单节连堂写 `{"start": 1, "end": 1}`（真实数据就是这么存的），
    所以合法性要求是 `end >= start`，**不是** `end > start`。
    （2026-10-16 曾按 `start < end` 校验，把用户 24 门单节课全部误报。）
    """
    if not slots:
        return True
    for slot in slots:
        start, end = as_int(slot.get("start")), as_int(slot.get("end"))
        if start is None or end is None or start < 1 or end < start:
            return True
        if period_count and end > period_count:
            return True
    return False


def _weeks_out_of_range(course: dict, total_weeks: int | None) -> bool:
    weeks = course.get("weeks") or {}
    w_start, w_end = as_int(weeks.get("start")), as_int(weeks.get("end"))
    return bool(total_weeks and w_start is not None and w_end is not None
                and (w_start < 1 or w_end > total_weeks or w_start > w_end))


def _course_issues(course: dict, total_weeks: int | None,
                   period_count: int | None) -> list[str]:
    if _weeks_out_of_range(course, total_weeks):
        return [ISSUE_COURSE_WEEKS]
    day = as_int(course.get("day_of_week"))
    if day is None or not (1 <= day <= 7):
        return [ISSUE_COURSE_DAY]
    if _slots_invalid(course.get("time_slots") or [], period_count):
        return [ISSUE_COURSE_SLOTS]
    return []


def validate_courses(courses: list[dict], total_weeks: int | None,
                     period_count: int | None) -> list[str]:
    """课程级问题码（相对当前学期的周数/节次）。"""
    issues: list[str] = []
    for course in courses:
        issues += _course_issues(course, total_weeks, period_count)
    return issues


def _model_issues(semesters: list[dict], current_id: str, courses: list[dict]) -> list[str]:
    issues: list[str] = []
    ids = [str(s.get("id") or "") for s in semesters]
    if len(set(ids)) != len(ids):
        issues.append(ISSUE_DUPLICATE_IDS)
    if not semesters and courses:
        issues.append(ISSUE_NO_SEMESTER)
    if current_id and current_id not in ids:
        issues.append(ISSUE_CURRENT_MISSING)
    return issues


def _semester_spans(semesters: list[dict]) -> list[tuple[date, date]]:
    spans = []
    for s in semesters:
        start, total = parse_date(s.get("start_date")), as_int(s.get("total_weeks"))
        if start and total and MIN_TOTAL_WEEKS <= total <= MAX_TOTAL_WEEKS:
            spans.append((start, end_date_of(start, total)))
    return sorted(spans)


def _has_overlap(spans: list[tuple[date, date]]) -> bool:
    return any(spans[i][0] <= spans[i - 1][1] for i in range(1, len(spans)))


def validate_all(semesters: list[dict], current_id: str,
                 courses: list[dict]) -> dict:
    """整体体检：`{semesters: {id: [码]}, model: [码], courses: [码]}`。"""
    per_semester = {str(s.get("id") or f"#{i}"): validate_semester(s)
                    for i, s in enumerate(semesters)}
    model_issues = _model_issues(semesters, current_id, courses)
    if _has_overlap(_semester_spans(semesters)):
        model_issues.append(ISSUE_OVERLAP)

    current = next((s for s in semesters if s.get("id") == current_id), None)
    status = semester_status(current, date.today())
    return {
        "semesters": per_semester,
        "model": model_issues,
        "courses": validate_courses(courses, status["total_weeks"], status["period_count"]),
    }
