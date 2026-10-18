"""日程快照文本（供**人和 AI** 读）—— 从 `schedule_view.py` 搬出来。

搬的原因：`schedule_view.py` 923 行、`ScheduleView` 887 行，都超上限（`Q-A1`）；
这一族是**纯文本构建**（不碰任何控件、不 emit 信号），搬出来风险最低。

产出被 `ScheduleView._build_snapshot()` 交给「快速安排」的 AI 提示词
（`_quick_arrange`），也用于把"这几天有什么"讲清楚。
"""

from datetime import date, timedelta

from src.models.course import PERIOD_TIMES

DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def build_snapshot(dm, target: date, days: int = 1) -> str:
    """构建供人与 AI 阅读的 N 天日程快照。"""
    today = date.today()
    lines = [
        f"========== 日程快照: {days}天 (从{target.isoformat()}起) ==========",
        "当前日期: " + today.isoformat(),
        "",
    ]
    lines += ddl_lines(dm)
    lines += exam_lines(dm, today)

    period_count = dm.courses.get_period_count()
    for d in range(days):
        day = target + timedelta(days=d)
        lines += day_lines(dm, day, DAY_NAMES[day.weekday()], today, period_count)

    lines += instructions(days)
    return "\n".join(lines)


def ddl_lines(dm) -> list[str]:
    """全局 DDL（各天共用）。"""
    pending = dm.tasks.pending
    out = [f"--- DDL/截止日期 (共{len(pending)}项, 不可移动的红线) ---"]
    for t in pending:
        due = t.get("due_date", "")[:16].replace("T", " ") if t.get("due_date") else "无截止"
        course = t.get("course_name", "") or ""
        c_str = f" [{course}]" if course else ""
        out.append(f"  ● {t.get('title', '')}{c_str}  截止: {due}")
    out.append("")
    return out


def exam_lines(dm, today) -> list[str]:
    """未来考试列表（无则空）。"""
    exams = getattr(dm, "exams", None)
    if exams is None:
        return []
    upcoming = [e for e in exams.exams if e.get("exam_date", "") >= today.isoformat()]
    if not upcoming:
        return []
    out = [f"--- 考试安排 (共{len(upcoming)}场) ---"]
    for e in sorted(upcoming, key=lambda x: x.get("exam_date", "")):
        scope = e.get("scope", "") or ""
        scope_str = f"  范围: {scope}" if scope else ""
        out.append(f"  📝 {e.get('course_name', '')}  {e.get('exam_date', '')}{scope_str}")
    out.append("")
    return out


def day_lines(dm, day, day_name: str, today, period_count: int) -> list[str]:
    """单天：课程 / 习惯 / 已有安排 / 空闲时段。"""
    day_str = day.isoformat()
    marker = " ★今天" if day == today else ""
    lines = [f"========== {day_str} {day_name}{marker} =========="]

    courses = dm.courses.get_courses_for_date(day)
    lines += course_lines(courses)

    active = [h for h in dm.habits.habits if habit_active_on(h, day)]
    lines += habit_lines(active)
    lines += plan_lines(dm.daily_logs.get_plans(day_str))

    lines.append(f"  空闲: {free_slots_text(courses, period_count)}")
    lines.append("")
    return lines


def course_lines(courses: list[dict]) -> list[str]:
    """单天课程块。"""
    lines = [f"  课程({len(courses)}门):"]
    for c in courses:
        slot_strs = [f"第{s.get('start', '?')}-{s.get('end', '?')}节"
                     for s in c.get("time_slots", [])]
        loc = c.get("location", "") or ""
        loc_str = f" @{loc}" if loc else ""
        lines.append(f"    [{','.join(slot_strs)}] {c.get('name', '')}{loc_str}")
    return lines


def habit_lines(active: list[dict]) -> list[str]:
    """单天习惯块（无则空）。"""
    if not active:
        return []
    lines = [f"  习惯({len(active)}项):"]
    for h in active:
        rt = h.get("reminder_time", "") or ""
        rt_str = f" @{rt}" if rt else ""
        lines.append(f"    {h.get('name', '')}{rt_str} ({h.get('duration_minutes', 30)}分钟)")
    return lines


def plan_lines(plans: list[dict]) -> list[str]:
    """单天已有安排块（无则提示(无)）。"""
    if not plans:
        return ["  已有安排: (无)"]
    lines = [f"  已有安排({len(plans)}项):"]
    for p in plans:
        lines.append(f"    第{p.get('time_slot', '?')}节: {p.get('title', '')}")
    return lines


def habit_active_on(habit: dict, day) -> bool:
    sched = habit.get("schedule", {})
    st = sched.get("type", "daily")
    if st in ("daily", "interval"):
        return True
    if st == "weekly":
        return (day.weekday() + 1) in sched.get("days", [])
    return False


def free_slots_text(courses: list[dict], period_count: int) -> str:
    occupied: set[int] = set()
    for c in courses:
        for s in c.get("time_slots", []):
            occupied.update(range(s["start"], s["end"] + 1))
    times = []
    for p in range(1, period_count + 1):
        if p in occupied:
            continue
        if p <= len(PERIOD_TIMES):
            st_t, en_t = PERIOD_TIMES[p - 1]
            times.append(f"第{p}节({st_t}-{en_t})")
        else:
            times.append(f"第{p}节")
    return ", ".join(times) if times else "(无)"


def instructions(days: int) -> list[str]:
    return [
        "========== 安排指令 ==========",
        f"请为以上{days}天安排日程。规则：",
        "1. 课程时段不可占用，DDL截止时间不可移动",
        "2. 将习惯安排到对应日期的空闲时段",
        "3. 根据DDL紧迫度，将任务分配到各天空闲时段（越临近截止越优先）",
        "4. 如有考试，优先安排考前复习时间",
        "5. 允许在上课时段安排自习任务",
        "6. 用 ```sh 代码块输出 actions.py 命令（replace_plans / add_plan），不要用 JSON",
    ]
