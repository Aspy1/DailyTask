"""课程"本周是否上课"与"同一时段两门课"的纯规则（无 Qt / 无 IO）。

**为什么要它**：选修课多 / 有重修时，**同一时段会有两门课**。周视图原来是
`setCellWidget` 直接放块 —— 同一格的第二门课会**静默覆盖**第一门，
课表上看起来"只有一门课"，用户根本不知道撞课了。

冲突判定要同时服务两处，所以抽成纯函数（与 `models/semester.py` 同一套路）：
- 周视图：把冲突格渲染成一个列出**两门课**的块
- 日视图：该时段卡片上加一行"两门课，记得请假"的提示
"""

from src.models.coerce import as_int


def _in_week_range(course: dict, week: int) -> bool:
    weeks = course.get("weeks") or {}
    if not weeks:
        return True
    w_start = as_int(weeks.get("start")) or 1
    w_end = as_int(weeks.get("end")) or 20
    return w_start <= week <= w_end


def _parity_allows(course: dict, week: int) -> bool:
    parity = course.get("week_parity", "all")
    if parity == "odd":
        return week % 2 == 1
    if parity == "even":
        return week % 2 == 0
    return True


def is_active_week(course: dict, week: int) -> bool:
    """该课程在第 `week` 周是否上课（周次范围 / 排除周 / 单双周）。"""
    return (_in_week_range(course, week)
            and week not in (course.get("excluded_weeks") or [])
            and _parity_allows(course, week))


def slots_of(course: dict) -> list[int]:
    """课程占用的节次列表。

    ⚠ `end` 是**闭区间**：单节连堂写 `{"start": 1, "end": 1}`（真实数据就是这样），
    所以展开是 `range(start, end + 1)`。
    """
    slots: list[int] = []
    for slot in course.get("time_slots") or []:
        start, end = as_int(slot.get("start")), as_int(slot.get("end"))
        if start is None or end is None or start < 1 or end < start:
            continue
        slots.extend(range(start, end + 1))
    return slots


def courses_by_cell(courses: list[dict], week: int,
                    period_count: int | None = None) -> dict[tuple[int, int], list[dict]]:
    """`{(day_of_week, 节次): [课程, ...]}`（只含本周上课、且在节次范围内的课）。"""
    cells: dict[tuple[int, int], list[dict]] = {}
    for course in courses:
        if not is_active_week(course, week):
            continue
        day = as_int(course.get("day_of_week"))
        if day is None or not (1 <= day <= 7):
            continue
        for slot in slots_of(course):
            if period_count and slot > period_count:
                continue
            cells.setdefault((day, slot), []).append(course)
    return cells


def conflicts_by_cell(courses: list[dict], week: int,
                      period_count: int | None = None) -> dict[tuple[int, int], list[dict]]:
    """只保留**两门及以上**的格子：`{(day, 节次): [课程, ...]}`。"""
    return {key: value
            for key, value in courses_by_cell(courses, week, period_count).items()
            if len(value) > 1}


def find_conflicts(courses: list[dict], week: int,
                   period_count: int | None = None) -> list[dict]:
    """冲突列表（按天/节次排序）：`[{"day": 1, "slot": 3, "courses": [...]}]`。"""
    cells = conflicts_by_cell(courses, week, period_count)
    return [{"day": day, "slot": slot, "courses": value}
            for (day, slot), value in sorted(cells.items())]
