"""Read-only course or habit reminder shown on the schedule homepage."""

from datetime import datetime, time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.i18n.loader import tr
from src.models.course import PERIOD_TIMES, schedule_date
from src.ui.styles.cards import card
from src.ui.styles.theme import SPACING, font

_HABIT_PREVIEW_LIMIT = 3


def _upcoming_slots(courses: list[dict], now: datetime) -> list[tuple[time, str, str]]:
    slots = []
    for course in courses:
        for slot in course.get("time_slots", []):
            period = slot.get("start")
            if not isinstance(period, int) or not 1 <= period <= len(PERIOD_TIMES):
                continue
            start = time.fromisoformat(PERIOD_TIMES[period - 1][0])
            if start > now.time():
                slots.append((start, course.get("name", ""),
                              slot.get("location") or course.get("location") or ""))
    return slots


class ScheduleFocus(QWidget):
    def __init__(self, data_manager, parent=None) -> None:
        super().__init__(parent)
        self._dm = data_manager
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        surface = card("item")
        outer.addWidget(surface)
        content = QVBoxLayout(surface)
        content.setSpacing(SPACING["spacing_xs"])
        self.heading = QLabel()
        self.heading.setFont(font("sectionTitle"))
        self.details = QLabel()
        self.details.setFont(font("body"))
        for label in (self.heading, self.details):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            content.addWidget(label)

    def refresh(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        day = schedule_date(now)
        if day == now.date():
            courses = self._dm.courses.get_courses_for_date(day)
            upcoming = _upcoming_slots(courses, now)
            if upcoming:
                self._show_courses(upcoming)
                return
        self._show_habits()

    def _show_courses(self, upcoming: list[tuple[time, str, str]]) -> None:
        start = min(slot[0] for slot in upcoming)
        lines = [
            tr("widget.schedule.focus_course_detail", time=start.strftime("%H:%M"), name=name,
               location=location or tr("widget.schedule.focus_location_unknown"))
            for slot_time, name, location in upcoming if slot_time == start
        ]
        self.heading.setText(tr("widget.schedule.focus_next_course"))
        self.details.setText("\n".join(dict.fromkeys(lines)))
        self.show()

    def _show_habits(self) -> None:
        habits = self._dm.habits.get_pending_today()
        self.heading.setText(tr("widget.schedule.focus_today_habits"))
        names = tr("widget.schedule.focus_habit_separator").join(
            habit["name"] for habit in habits[:_HABIT_PREVIEW_LIMIT])
        if len(habits) > _HABIT_PREVIEW_LIMIT:
            names = tr("widget.schedule.focus_habit_overflow", names=names, total=len(habits))
        self.details.setText(names)
        self.setVisible(bool(habits))
