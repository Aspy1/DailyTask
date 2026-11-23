from datetime import date, datetime
from types import SimpleNamespace

import pytest

from src.ui.widgets.schedule_focus import ScheduleFocus


def _course(name: str, period: int, location: str) -> dict:
    return {"name": name, "time_slots": [
        {"start": period, "end": period, "location": location},
    ]}


def test_focus_shows_tied_next_courses_and_skips_started_course(qapp) -> None:
    courses = [_course("Later", 4, "B405"), _course("Started", 1, "A101"),
               _course("Algorithms", 2, "C201"), _course("Networks", 2, "D202")]
    widget = ScheduleFocus(SimpleNamespace(
        courses=SimpleNamespace(get_courses_for_date=lambda _: courses),
        habits=SimpleNamespace(get_pending_today=lambda: [{"name": "Read"}]),
    ))
    widget.refresh(datetime(2026, 11, 23, 9))

    body = widget.details.text()
    for expected in ("10:25", "Algorithms", "C201", "Networks", "D202"):
        assert expected in body
    assert all(other not in body for other in ("Later", "Started", "Read"))


def test_focus_replaces_finished_schedule_with_today_habits(qapp) -> None:
    pending = [{"name": "Read"}, {"name": "Stretch"}]
    widget = ScheduleFocus(SimpleNamespace(
        courses=SimpleNamespace(get_courses_for_date=lambda _: [_course("Done", 1, "A101")]),
        habits=SimpleNamespace(get_pending_today=lambda: pending),
    ))
    widget.refresh(datetime(2026, 11, 23, 18))
    assert widget.heading.text() == "今日习惯"
    assert "Read" in widget.details.text() and "Stretch" in widget.details.text()

    pending.clear()
    widget.refresh(datetime(2026, 11, 23, 18))
    assert widget.isHidden()


@pytest.mark.parametrize("hour, minute", [(0, 59), (1, 0)])
def test_focus_respects_schedule_date_cutover(qapp, hour, minute) -> None:
    requested_dates = []
    courses = [_course("Morning", 1, "A101")]

    def get_courses(day: date) -> list[dict]:
        requested_dates.append(day)
        return courses

    widget = ScheduleFocus(SimpleNamespace(
        courses=SimpleNamespace(get_courses_for_date=get_courses),
        habits=SimpleNamespace(get_pending_today=lambda: [{"name": "Read"}]),
    ))
    now = datetime(2026, 11, 23, hour, minute)
    widget.refresh(now)

    if hour == 0:
        assert requested_dates == []
        assert widget.details.text() == "Read"
    else:
        assert requested_dates == [now.date()]
        assert "Morning" in widget.details.text()


def test_focus_limits_habit_preview_without_losing_pending_count(qapp) -> None:
    habits = [{"name": name} for name in ("Read", "Stretch", "Walk", "Review")]
    widget = ScheduleFocus(SimpleNamespace(
        courses=SimpleNamespace(get_courses_for_date=lambda _: []),
        habits=SimpleNamespace(get_pending_today=lambda: habits),
    ))
    widget.refresh(datetime(2026, 11, 23, 18))

    assert widget.details.text() == "Read、Stretch、Walk等 4 项待完成"
