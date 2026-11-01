"""日程快照（AI 快速安排提示词）纯文本测试。"""

from datetime import date
from types import SimpleNamespace

from src.ui.widgets.schedule_snapshot import (
    build_snapshot,
    course_lines,
    day_lines,
    exam_lines,
    free_slots_text,
    habit_active_on,
    habit_lines,
    instructions,
    plan_lines,
)


def _dm() -> SimpleNamespace:
    courses = [{
        "name": "高等数学", "location": "A501",
        "time_slots": [{"start": 1, "end": 2}],
    }]
    return SimpleNamespace(
        tasks=SimpleNamespace(pending=[{
            "title": "第三章习题", "course_name": "高等数学",
            "due_date": "2026-11-02T22:00:00",
        }]),
        exams=SimpleNamespace(exams=[{
            "course_name": "高等数学", "exam_date": "2026-11-05",
            "scope": "第1-5章",
        }]),
        courses=SimpleNamespace(
            get_period_count=lambda: 4,
            get_courses_for_date=lambda _d: courses,
        ),
        habits=SimpleNamespace(habits=[{
            "name": "背单词", "reminder_time": "20:00",
            "duration_minutes": 20, "schedule": {"type": "daily"},
        }]),
        daily_logs=SimpleNamespace(
            get_plans=lambda _d: [{"time_slot": 3, "title": "课程汇报"}]),
    )


def test_helpers_cover_courses_habits_plans_and_free_slots() -> None:
    dm = _dm()
    assert "高等数学" in "\n".join(course_lines(dm.courses.get_courses_for_date(date.today())))
    assert "背单词" in "\n".join(habit_lines(dm.habits.habits))
    assert "课程汇报" in "\n".join(plan_lines([{"time_slot": 3, "title": "课程汇报"}]))
    assert plan_lines([]) == ["  已有安排: (无)"]
    assert "第1节" not in free_slots_text(
        dm.courses.get_courses_for_date(date.today()), 4)
    assert "第3节" in free_slots_text(
        dm.courses.get_courses_for_date(date.today()), 4)
    assert habit_active_on({"schedule": {"type": "weekly", "days": [1]}},
                           date(2026, 11, 2)) is True
    assert habit_active_on({"schedule": {"type": "weekly", "days": [2]}},
                           date(2026, 11, 2)) is False


def test_snapshot_and_exam_and_instructions() -> None:
    dm = _dm()
    snapshot = build_snapshot(dm, date(2026, 11, 2), days=2)
    assert "日程快照: 2天" in snapshot
    assert "第三章习题" in snapshot
    assert "背单词" in snapshot
    assert "课程汇报" in snapshot
    assert "安排指令" in snapshot
    exams = exam_lines(dm, date(2026, 11, 1))
    assert "考试安排" in "\n".join(exams) and "第1-5章" in "\n".join(exams)
    assert exam_lines(SimpleNamespace(), date(2026, 11, 1)) == []
    assert len(instructions(2)) >= 6


def test_day_lines_marks_today_and_free_slots() -> None:
    dm = _dm()
    lines = day_lines(dm, date(2026, 11, 2), "周一", date(2026, 11, 2), 4)
    text = "\n".join(lines)
    assert "★今天" in text
    assert "空闲:" in text
