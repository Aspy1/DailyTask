"""Central data orchestration with signal-based change notification.

**数据布局**（按学期分文件，见 `models/semester_paths.py`）：

- 按学期：`semesters/<当前学期>/{courses,tasks,exams}.json`
- 跨学期共享：`habits.json` / `expenses.json` / `daily_logs.json` / `inventory.json`
- 学期注册表：`semesters.json`（列表 + 当前学期）

`switch_semester()` 会把按学期的三个模型**重定向**到新学期的文件并重新加载 ——
这是"切换学期就该换一份数据"的落点（此前切学期只改周次映射，课表永远不变）。
"""

import logging
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from src.models import semester_paths
from src.models.course import CourseModel
from src.models.daily_log import DailyLogModel
from src.models.exam import ExamModel
from src.models.expense import ExpenseModel
from src.models.habit import HabitModel
from src.models.inventory import InventoryModel
from src.models.semester import (
    DEFAULT_EXAM_WEEKS,
    DEFAULT_PERIOD_COUNT,
    DEFAULT_TOTAL_WEEKS,
)
from src.models.semester_registry import SemesterRegistry
from src.models.task import TaskModel

logger = logging.getLogger(__name__)


class DataManager(QObject):
    data_changed = Signal(str)

    def __init__(self, data_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        # 旧布局（courses.json 里同时放学期与课程）→ 按学期分文件（幂等）
        if semester_paths.migrate_legacy(data_dir):
            logger.info("数据目录已从旧布局迁移：%s", data_dir)

        self.semesters = SemesterRegistry(semester_paths.registry_path(data_dir))
        self.semesters.ensure_default()
        self.semesters.save()
        self._bind_semester_models()

        # ── 跨学期共享的模型 ──────────────────────────────────
        self.habits = HabitModel(data_dir / "habits.json")
        self.expenses = ExpenseModel(data_dir / "expenses.json")
        self.daily_logs = DailyLogModel(data_dir / "daily_logs.json")
        self.inventory = InventoryModel(data_dir / "inventory.json")
        self.habits._inventory = self.inventory

        # Auto-reload: check file mtimes every 3s, reload if changed externally
        self._file_mtimes: dict[str, float] = {}
        self._capture_mtimes()
        self._reload_timer = QTimer(self)
        self._reload_timer.timeout.connect(self._auto_reload)
        self._reload_timer.start(3000)  # 3 seconds

    # ── 按学期的模型 ────────────────────────────────────────

    def _bind_semester_models(self) -> None:
        """把 courses/tasks/exams 指向**当前学期**的文件（切换学期时重跑）。"""
        folder = semester_paths.semester_dir(self.data_dir, self.semesters.current_semester)
        folder.mkdir(parents=True, exist_ok=True)
        self.courses = CourseModel(folder / "courses.json", self.semesters)
        self.tasks = TaskModel(folder / "tasks.json")
        self.exams = ExamModel(folder / "exams.json")

    def switch_semester(self, semester_id: str) -> bool:
        """切换当前学期：改指针 → **重定向**按学期的模型 → 通知界面刷新。"""
        if not self.semesters.set_current_semester(semester_id):
            return False
        self.semesters.save()
        self._bind_semester_models()
        self._capture_mtimes()
        logger.info("已切换学期：%s", semester_id)
        self.data_changed.emit("semester")
        return True

    def create_semester(self, name: str, start: date,
                        total_weeks: int = DEFAULT_TOTAL_WEEKS,
                        period_count: int = DEFAULT_PERIOD_COUNT,
                        exam_weeks: int = DEFAULT_EXAM_WEEKS) -> str:
        """新建学期（从**空白**数据开始）并切过去。"""
        sid = self.semesters.create_semester(name, start, total_weeks,
                                             period_count, exam_weeks)
        self.semesters.save()
        self.switch_semester(sid)
        return sid

    # ── 共享的模型 ──────────────────────────────────────────

    def _models(self) -> list[tuple[object, str]]:
        return [
            (self.courses, "courses"), (self.tasks, "tasks"),
            (self.habits, "habits"), (self.expenses, "expenses"),
            (self.daily_logs, "daily_logs"), (self.exams, "exams"),
            (self.inventory, "inventory"), (self.semesters, "semesters"),
        ]

    def reload_all(self) -> None:
        """Re-read all data files from disk."""
        for model, _name in self._models():
            model.reload()
        self._capture_mtimes()

    def _capture_mtimes(self) -> None:
        """Record current file modification times."""
        for model, name in self._models():
            try:
                self._file_mtimes[name] = model.file_path.stat().st_mtime
            except OSError:
                logger.debug("DataManager._capture_mtimes 中忽略异常", exc_info=True)

    def _auto_reload(self) -> None:
        """Check if any data file was modified externally and reload."""
        changed = False
        for model, name in self._models():
            try:
                mtime = model.file_path.stat().st_mtime
                if abs(mtime - self._file_mtimes.get(name, 0)) > 0.1:
                    model.reload()
                    self._file_mtimes[name] = mtime
                    changed = True
            except OSError:
                logger.debug("DataManager._auto_reload 中忽略异常", exc_info=True)
        if changed:
            self.data_changed.emit("external")

    def save_all(self) -> None:
        """落盘全部模型（退出 / 重启前调用，勿漏 exams/inventory —— ERRORS #026）。"""
        for model, _name in self._models():
            model.save()

    def get_today_summary(self) -> dict:
        return {
            "pending_tasks": len(self.tasks.pending),
            "pending_habits": len(self.habits.get_pending_today()),
            "today_expense": self.expenses.today_total(),
            "budget_remaining": self.expenses.budget.get("monthly", 0) - self.expenses.month_total(),
            "today_courses": self.courses.get_today_courses(),
        }
