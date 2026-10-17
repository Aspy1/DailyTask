"""Central data orchestration with signal-based change notification.

**数据布局**（按学期分文件，见 `models/semester_paths.py`）：

- 按学期：`semesters/<当前学期>/{courses,tasks,exams}.json`
- 跨学期共享：`habits.json` / `expenses.json` / `daily_logs.json` / `inventory.json`
- 学期注册表：`semesters.json`（列表 + 当前学期）

`switch_semester()` 会把按学期的三个模型**重定向**到新学期的文件并重新加载 ——
这是"切换学期就该换一份数据"的落点（此前切学期只改周次映射，课表永远不变）。
"""

import json
import logging
import os
from datetime import date, datetime
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


def _read_doc(path: Path) -> dict | None:
    """读磁盘上的 JSON；缺失 / 损坏返回 None（调用方据此判断"有没有东西要保护"）。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_conflict_copy(doc: dict, name: str, folder: Path) -> Path:
    """把我方版本写成冲突副本（原子写：`.tmp` → `os.replace`，**不碰原文件**）。"""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


class DataManager(QObject):
    data_changed = Signal(str)
    # 落盘时发现"这个文件被别人改过" → (模型名, 冲突副本路径)。
    # 退出路径（`flush_on_exit`）与阶段 2 的 `_rev` 冲突都用它 —— 不静默选一边。
    save_conflict = Signal(str, str)

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
        self._attach_conflict_hook()

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
        # ⚠ 重建的模型要重新装回调（否则新学期那三个模型丢了回调 → 冲突又变静默覆盖）。
        # 这里**只装这三个**：本方法在 `__init__` 早期就会跑一次，那时共享模型还没建，
        # 走 `_models()` 会 AttributeError。
        for model in (self.courses, self.tasks, self.exams):
            model.on_conflict = self._on_model_conflict

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

    def _attach_conflict_hook(self) -> None:
        """给每个模型装上保存冲突回调（模型不是 QObject，所以用回调而不是信号）。

        ⚠ 切学期会**重建** courses/tasks/exams → `_bind_semester_models()` 里也要重装
        （那里单独处理，因为它跑得比共享模型更早）。
        """
        for model, _name in self._models():
            model.on_conflict = self._on_model_conflict

    def _on_model_conflict(self, model) -> None:
        """某模型保存时发现磁盘被外部改过 → 留副本 + 通知（不覆盖、不静默）。"""
        name = next((n for m, n in self._models() if m is model), "unknown")
        path = _write_conflict_copy(model.data, name,
                                    self.data_dir / "backup" / "save_conflict")
        logger.warning("%s 保存被拒：磁盘内容已被外部改动（我方版本存 %s）", name, path)
        self.save_conflict.emit(name, str(path))

    def save_all(self) -> None:
        """**无条件**落盘全部模型（勿漏 exams/inventory —— ERRORS #026）。

        ⚠ 退出 / 重启**不要**用这个（会覆盖外部改动）→ 用 `flush_on_exit()`。
        保留它是给"明确知道没有外部写入"的场合：测试与 `acceptance_check.py`。
        """
        for model, _name in self._models():
            model.save()

    def flush_on_exit(self) -> None:
        """退出 / 重启前落盘，但**不覆盖**别人改过的文件。

        退出时整份写回是最现实的静默覆盖路径（审查 2026-10-17 #1）：应用跑着的
        时候若 skill / CLI / 手工改过文件，`save_all()` 会把那些改动整份盖掉。
        这里逐模型比对**磁盘内容**而不是 mtime —— 应用自己保存也会动 mtime，
        只比 mtime 会把"刚保存完就退出"误判成冲突：

        - 文件缺失 → 正常落盘（没东西可保护）
        - 磁盘内容 == 内存态 → **不碰文件**（各面板本来就显式保存，这里是兜底）
        - 读不出来（损坏）或内容不同 → **不覆盖**：我方版本落到
          `data/backup/save_conflict/`（`data/backup/` 已在 `.gitignore`），
          原文件保持原样（损坏现场也留着），并发 `save_conflict` 告知
        """
        folder = self.data_dir / "backup" / "save_conflict"
        for model, name in self._models():
            if not model.file_path.exists():
                model.save()
                continue
            on_disk = _read_doc(model.file_path)
            if on_disk is not None and on_disk == model.data:
                continue
            path = _write_conflict_copy(model.data, name, folder)
            logger.warning("退出时 %s 与磁盘不一致，已跳过覆盖（我方版本存 %s）",
                           name, path)
            self.save_conflict.emit(name, str(path))
        self._capture_mtimes()

    def get_today_summary(self) -> dict:
        return {
            "pending_tasks": len(self.tasks.pending),
            "pending_habits": len(self.habits.get_pending_today()),
            "today_expense": self.expenses.today_total(),
            "budget_remaining": self.expenses.budget.get("monthly", 0) - self.expenses.month_total(),
            "today_courses": self.courses.get_today_courses(),
        }
