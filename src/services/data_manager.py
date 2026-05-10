"""Central data orchestration with signal-based change notification."""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.models.course import CourseModel
from src.models.task import TaskModel
from src.models.habit import HabitModel
from src.models.expense import ExpenseModel
from src.models.daily_log import DailyLogModel


class DataManager(QObject):
    data_changed = Signal(str)

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        self.courses = CourseModel(data_dir / "courses.json")
        self.tasks = TaskModel(data_dir / "tasks.json")
        self.habits = HabitModel(data_dir / "habits.json")
        self.expenses = ExpenseModel(data_dir / "expenses.json")
        self.daily_logs = DailyLogModel(data_dir / "daily_logs.json")

    def reload_all(self) -> None:
        """Re-read all data files from disk."""
        self.courses.reload()
        self.tasks.reload()
        self.habits.reload()
        self.expenses.reload()
        self.daily_logs.reload()

    def save_all(self) -> None:
        self.courses.save()
        self.tasks.save()
        self.habits.save()
        self.expenses.save()
        self.daily_logs.save()

    def get_today_summary(self) -> dict:
        return {
            "pending_tasks": len(self.tasks.pending),
            "pending_habits": len(self.habits.get_pending_today()),
            "today_expense": self.expenses.today_total(),
            "budget_remaining": self.expenses.budget.get("monthly", 0) - self.expenses.month_total(),
            "today_courses": self.courses.get_today_courses(),
        }
