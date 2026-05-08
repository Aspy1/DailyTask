"""Habit tracking data model with attached tasks."""

from datetime import date, datetime, timedelta
from pathlib import Path

from src.models.base import BaseJsonModel


DEFAULT_HABITS = {
    "_version": 2,
    "habits": [],
    "attached_task_templates": [],
    "logs": {},
}


class HabitModel(BaseJsonModel):
    def __init__(self, file_path: Path):
        super().__init__(file_path, DEFAULT_HABITS)

    @property
    def habits(self) -> list[dict]:
        return self._data.get("habits", [])

    @property
    def attached_task_templates(self) -> list[dict]:
        return self._data.get("attached_task_templates", [])

    @property
    def logs(self) -> dict:
        return self._data.setdefault("logs", {})

    def add_habit(self, habit: dict) -> str:
        habits = self._data.setdefault("habits", [])
        hid = habit.get("id", f"h_{len(habits) + 1:03d}")
        habit["id"] = hid
        habit.setdefault("streak", 0)
        habit.setdefault("longest_streak", 0)
        habit.setdefault("remind_enabled", True)
        habit.setdefault("reminder_time", "")
        habit.setdefault("duration_minutes", 30)
        habit.setdefault("attached_tasks", [])
        habit.setdefault("schedule", {"type": "interval", "value": 1, "unit": "day"})
        habit.setdefault("postpone_until", None)
        habit.setdefault("canceled_on", [])
        habit.setdefault("created_at", datetime.now().isoformat())
        habits.append(habit)
        return hid

    def update_habit(self, habit_id: str, changes: dict) -> bool:
        for h in self.habits:
            if h["id"] == habit_id:
                h.update(changes)
                return True
        return False

    def postpone(self, habit_id: str, until: str) -> bool:
        """Postpone a habit until a specific datetime or date string."""
        return self.update_habit(habit_id, {"postpone_until": until})

    def cancel_today(self, habit_id: str) -> bool:
        """Cancel today's instance of a habit."""
        today = date.today().isoformat()
        for h in self.habits:
            if h["id"] == habit_id:
                canceled = h.setdefault("canceled_on", [])
                if today not in canceled:
                    canceled.append(today)
                return True
        return False

    def is_active_today(self, habit_id: str) -> bool:
        habit = None
        for h in self.habits:
            if h["id"] == habit_id:
                habit = h
                break
        if not habit:
            return False

        today = date.today()
        today_str = today.isoformat()

        # Postponed → active on the postponed date
        pu = habit.get("postpone_until")
        if pu:
            pu_date = pu[:10]
            if pu_date == today_str:
                return True
            # If postponed to a future date, not active today
            if pu_date > today_str:
                return False
            # If postponed date has passed, fall through to normal check
            # Clear stale postponement
            habit["postpone_until"] = None

        # Canceled today
        if today_str in habit.get("canceled_on", []):
            return False

        schedule = habit.get("schedule", {"type": "interval", "value": 1, "unit": "day"})
        if schedule.get("type") == "weekly":
            days = schedule.get("days", [])
            return today.isoweekday() in days  # 1=Mon, 7=Sun
        else:
            # Interval: check if today is a multiple of value days from start
            if "start_date" in schedule and schedule["start_date"]:
                try:
                    start = date.fromisoformat(schedule["start_date"])
                    delta = (today - start).days
                    if delta < 0:
                        return False
                    return delta % schedule.get("value", 1) == 0
                except (ValueError, TypeError):
                    pass
            return True  # No start date → active every day

    def get_pending_today(self) -> list[dict]:
        return [h for h in self.habits
                if self.is_active_today(h["id"]) and not self.is_done_today(h["id"])]

    def add_template(self, template: dict) -> str:
        templates = self._data.setdefault("attached_task_templates", [])
        tid = template.get("id", f"at_{len(templates) + 1:03d}")
        template["id"] = tid
        template.setdefault("delay_hours", 24)
        template.setdefault("duration_minutes", 15)
        templates.append(template)
        return tid

    def log(self, habit_id: str, completed: bool, note: str = "") -> list[dict]:
        """Log a habit and return any auto-generated attached tasks."""
        today = date.today().isoformat()
        logs = self._data.setdefault("logs", {})
        day_log = logs.setdefault(today, {})
        day_log[habit_id] = {
            "completed": completed,
            "completed_at": datetime.now().isoformat() if completed else None,
            "note": note,
        }
        if completed:
            self._update_streak(habit_id)
        attached = []
        if completed:
            habit = None
            for h in self.habits:
                if h["id"] == habit_id:
                    habit = h
                    break
            if habit:
                for at in habit.get("attached_tasks", []):
                    due = datetime.now() + timedelta(hours=at.get("delay_hours", 24))
                    attached.append({
                        "title": at.get("name", ""),
                        "due_date": due.isoformat(),
                        "description": f"完成「{habit.get('name', '')}」后的附加事项",
                        "priority": "medium",
                        "tags": ["附加事项", habit.get("name", "")],
                    })
        return attached

    def _update_streak(self, habit_id: str) -> None:
        for habit in self._data.get("habits", []):
            if habit["id"] == habit_id:
                streak = habit.get("streak", 0) + 1
                habit["streak"] = streak
                if streak > habit.get("longest_streak", 0):
                    habit["longest_streak"] = streak
                return

    def is_done_today(self, habit_id: str) -> bool:
        today = date.today().isoformat()
        day_log = self.logs.get(today, {})
        entry = day_log.get(habit_id, {})
        return entry.get("completed", False)

    def get_pending_today(self) -> list[dict]:
        return [h for h in self.habits if not self.is_done_today(h["id"])]

    def delete_habit(self, habit_id: str) -> bool:
        habits = self._data.get("habits", [])
        for i, h in enumerate(habits):
            if h["id"] == habit_id:
                habits.pop(i)
                return True
        return False
