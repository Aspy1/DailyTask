"""把课程 / 计划 / 习惯归入 1–6 时段（从 `schedule_view` 搬出来）。

搬出来的原因：`schedule_view.py` 的 `ScheduleView` 类贴着 400/800 行上限，
而这三段是**纯映射逻辑**（数据 → 时段桶），跟界面无关，最好读也最好测。

⚠ `add_habit_to_slots` 需要 `dm`（判断习惯今天是否活跃）—— 显式传进来。
"""

from src.models.course import PERIOD_TIMES


def add_course_to_slots(slot_data: dict[int, list[dict]], course: dict) -> None:
    """把单门课程写入其占用的每个时段。"""
    for slot in course.get("time_slots", []):
        for s in range(slot["start"], slot["end"] + 1):
            if 1 <= s <= 6:
                slot_data[s].append({
                    "type": "course",
                    "course": course,
                    "name": course.get("name", ""),
                    "location": course.get("location", ""),
                })

def add_plan_to_slots(slot_data: dict[int, list[dict]], plan: dict) -> None:
    """把单条计划写入其时段。"""
    ts = plan.get("time_slot", 0)
    if 1 <= ts <= 6:
        slot_data[ts].append({
            "type": "plan",
            "plan": plan,
            "plan_type": plan.get("type", "custom"),
            "title": plan.get("title", ""),
            "course_name": plan.get("course_name", ""),
            "note": plan.get("note", ""),
            "done": bool(plan.get("done")),
        })

def slot_for_minutes(minutes: int, period_count: int | None = None) -> int | None:
    """把「当天分钟数」映射到节次（1 起）；不在任何时段返回 None。"""
    periods = PERIOD_TIMES if period_count is None else PERIOD_TIMES[:period_count]
    for i, (start_s, end_s) in enumerate(periods):
        s = int(start_s[:2]) * 60 + int(start_s[3:])
        e = int(end_s[:2]) * 60 + int(end_s[3:])
        if s <= minutes <= e:
            return i + 1
    return None


def add_habit_to_slots(slot_data: dict[int, list[dict]], h: dict, dm) -> None:
    """把单个当日活跃习惯按提醒时间归入时段（`dm` 用来判断今天是否活跃）。"""
    if not dm.habits.is_active_today(h["id"]):
        return
    rt = h.get("reminder_time", "").strip()
    h_min = 0
    if rt:
        try:
            hh, mm = rt.split(":")
            h_min = int(hh) * 60 + int(mm)
        except ValueError:
            h_min = 0
    slot = slot_for_minutes(h_min) or 1
    if 1 <= slot <= 6:
        slot_data[slot].append({
            "type": "habit",
            "habit": h,
            "name": h.get("name", ""),
            "duration": h.get("duration_minutes", 30),
            "reminder_time": rt,
        })
