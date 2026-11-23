from datetime import datetime
from types import SimpleNamespace

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
