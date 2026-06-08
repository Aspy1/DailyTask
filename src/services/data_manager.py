"""Central data orchestration with signal-based change notification."""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.models.course import CourseModel
from src.models.task import TaskModel
from src.models.habit import HabitModel
from src.models.expense import ExpenseModel
from src.models.daily_log import DailyLogModel
from src.models.exam import ExamModel


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
        self.exams = ExamModel(data_dir / "exams.json")

        # Auto-reload: check file mtimes every 3s, reload if changed externally
        from PySide6.QtCore import QTimer
        self._file_mtimes: dict[str, float] = {}
        self._capture_mtimes()
        self._reload_timer = QTimer(self)
        self._reload_timer.timeout.connect(self._auto_reload)
        self._reload_timer.start(3000)  # 3 seconds

    def reload_all(self) -> None:
        """Re-read all data files from disk."""
        self.courses.reload()
        self.tasks.reload()
        self.habits.reload()
        self.expenses.reload()
        self.daily_logs.reload()
        self.exams.reload()
        self._capture_mtimes()

    def _capture_mtimes(self) -> None:
        """Record current file modification times."""
        for model, name in [
            (self.courses, "courses"), (self.tasks, "tasks"),
            (self.habits, "habits"), (self.expenses, "expenses"),
            (self.daily_logs, "daily_logs"),
            (self.exams, "exams"),
        ]:
            try:
                self._file_mtimes[name] = model.file_path.stat().st_mtime
            except OSError:
                pass

    def _auto_reload(self) -> None:
        """Check if any data file was modified externally and reload."""
        changed = False
        for model, name in [
            (self.courses, "courses"), (self.tasks, "tasks"),
            (self.habits, "habits"), (self.expenses, "expenses"),
            (self.daily_logs, "daily_logs"),
            (self.exams, "exams"),
        ]:
            try:
                mtime = model.file_path.stat().st_mtime
                if abs(mtime - self._file_mtimes.get(name, 0)) > 0.1:
                    model.reload()
                    self._file_mtimes[name] = mtime
                    changed = True
            except OSError:
                pass
        if changed:
            self.data_changed.emit("external")

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
