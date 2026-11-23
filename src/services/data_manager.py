"""Central data orchestration with signal-based change notification.

**数据布局**（按学期分文件，见 `models/semester_paths.py`）：

- 按学期：`semesters/<当前学期>/{courses,tasks,exams}.json`
- 跨学期共享：`habits.json` / `routines.json`（近期安排）/ `expenses.json` / `daily_logs.json` / `inventory.json`
- 学期注册表：`semesters.json`（列表 + 当前学期）

`switch_semester()` 会把按学期的三个模型**重定向**到新学期的文件并重新加载 ——
这是"切换学期就该换一份数据"的落点（此前切学期只改周次映射，课表永远不变）。
"""

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import QObject, QTimer, Signal

from src.models import semester_paths
from src.models.base import DataCorrupted, Unreadable
from src.models.course import CourseModel
from src.models.daily_log import DailyLogModel
from src.models.exam import ExamModel
from src.models.expense import ExpenseModel
from src.models.habit import HabitModel
from src.models.inventory import InventoryModel
from src.models.membership_contacts import MembershipContactsModel
from src.models.routine import RoutineModel
from src.models.semester import (
    DEFAULT_EXAM_WEEKS,
    DEFAULT_PERIOD_COUNT,
    DEFAULT_TOTAL_WEEKS,
)
from src.models.semester_registry import SemesterRegistry
from src.models.study import StudyModel
from src.models.task import TaskModel
from src.services.attachments import STORE_DIR_NAME, AttachmentStore

logger = logging.getLogger(__name__)


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
    # 按学期模型当前绑定的学期 id（`_auto_reload` 用它发现"外部切了学期"，审查 #6）
    _bound_semester: str = ""
    # 文件名 → 事件域名（**唯一映射**，审计 2026-11-21 P1）。
    # 轮询已经知道是哪个文件变了，就发对应域名让**一个**面板刷新；
    # 退化成 `external` 会让所有面板每 3 秒重建一次（"不知道改了什么"的语义）。
    DOMAIN_OF: ClassVar[dict[str, str]] = {
        "courses": "course", "tasks": "task", "habits": "habit",
        "routines": "routine", "expenses": "expense", "daily_logs": "plan",
        "exams": "exam", "inventory": "inventory", "study": "study",
        "semesters": "semester",
        # 私有手机号不进 UI 刷新链路（只在会员弹窗里读），故不登记域名
    }

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
        self.routines = RoutineModel(data_dir / "routines.json")
        self.expenses = ExpenseModel(data_dir / "expenses.json")
        self.daily_logs = DailyLogModel(data_dir / "daily_logs.json")
        self.inventory = InventoryModel(data_dir / "inventory.json")
        # 考研备考（跨学期共享）：学习时长 / 错题间隔复习 / 模考
        self.study = StudyModel(data_dir / "study.json")
        # 会员手机号：**私有**文件（不进仓库、不进 AI 提示词）——
        # 见 `git_sync.PRIVATE_FILES` 与 `models/membership_contacts.py`
        self.membership_contacts = MembershipContactsModel(
            data_dir / "private" / "memberships.json")
        # 作业附件：文件本身落在 `<data_dir>/attachments/<task_id>/`，`tasks.json`
        # 里只留元数据（`name/stored_name/size/sha256/added_at`）。
        # 根目录取**注入的** `data_dir`，不是模块级 `get_data_dir()` —— 沙箱测试靠它隔离。
        self.attachments = AttachmentStore(Path(data_dir) / STORE_DIR_NAME)
        self.habits._inventory = self.inventory
        self._attach_conflict_hook()
        self._log_recoveries()

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
        self._bound_semester = self.semesters.current_semester

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
            (self.habits, "habits"), (self.routines, "routines"),
            (self.expenses, "expenses"),
            (self.daily_logs, "daily_logs"), (self.exams, "exams"),
            (self.inventory, "inventory"), (self.study, "study"),
            (self.semesters, "semesters"),
            (self.membership_contacts, "membership_contacts"),
        ]

    def reload_all(self) -> None:
        """Re-read all data files from disk.

        ⚠ 单个文件损坏**不能**让整次重载抛异常：`BaseJsonModel.load()` 会先留档再抛
        `DataCorrupted`，这个异常若逃出 QTimer 槽 / AI 回调，会变成"界面不刷新"甚至崩溃。
        这里逐个隔离：坏文件已在模型层留档，其余文件照常重载。

        `Unreadable`（暂时读不出来）同样隔离：**留原样**，下次轮询会再试。
        """
        for model, name in self._models():
            try:
                model.reload()
            except DataCorrupted as e:
                logger.error("%s 重载失败（现场已留档）：%s", name, e)
            except Unreadable as e:
                logger.warning("%s 暂时读不出来，保留内存态：%s", name, e)
        self._capture_mtimes()

    def _capture_mtimes(self) -> None:
        """记录文件探针（**存在状态 + `st_mtime_ns`**，审计 2026-11-21 P1）。

        用 `st_mtime`（float 秒）会把亚秒级差异压掉，再加 0.1s 阈值 →
        同一秒内的内容更新有时**整个漏掉**。`st_mtime_ns` 是整数纳秒，不丢精度。
        """
        for model, name in self._models():
            try:
                self._file_mtimes[name] = model.file_path.stat().st_mtime_ns
            except OSError:
                # 缺失本身就是一种状态（0 = 不存在），别让异常吞掉变化检测
                self._file_mtimes[name] = 0

    def _auto_reload(self) -> None:
        """比对探针 → 重载变了的文件 → **按域**发通知（审计 2026-11-21 P1）。

        已知文件发对应域名（`tasks.json` → `task`），让**一个**面板刷新；
        只有"探针显示变了、但没有登记域名"时才退回 `external`（保守全刷）。
        """
        changed, fallback = self._reload_touched()
        if self.semesters.current_semester != self._bound_semester:
            # 外部（skill / CLI）改了注册表 → 必须走**同一条切换流程**：重定向按学期的
            # 三个模型，否则界面还在读旧学期的文件（审查 2026-10-17 #6）
            self._bind_semester_models()
            self.data_changed.emit("semester")
            return
        for domain in changed:
            self.data_changed.emit(domain)
        if fallback:
            # 不确定的状态仍然保守全刷："宁可多刷，不能漏刷"
            self.data_changed.emit("external")

    def _reload_touched(self) -> tuple[list[str], bool]:
        """重载探针显示变了的文件 → `(涉及的域名, 是否有未登记域名的文件)`。"""
        changed: list[str] = []
        fallback = False
        for model, name in self._models():
            mtime = self._probe(name, model)
            if mtime is None:
                continue                       # 没变 / 暂时读不出来（下轮重试）
            self._file_mtimes[name] = mtime
            domain = self.DOMAIN_OF.get(name)
            if domain is None:
                fallback = True
            elif domain not in changed:
                changed.append(domain)
        return changed, fallback

    def _probe(self, name: str, model) -> int | None:
        """单个文件的探针 → **变了才重载**并返回新探针；没变 / 读不出来 → None。"""
        try:
            mtime = model.file_path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        if mtime == self._file_mtimes.get(name, 0) and not model._write_blocked:
            return None
        try:
            model.reload()
        except DataCorrupted as e:
            logger.error("%s 外部写入后无法解析（现场已留档）：%s", name, e)
        except Unreadable as e:
            logger.warning("%s 暂时读不出来，下轮再试：%s", name, e)
            return None                        # 不更新探针 → 下一轮还会重试
        return mtime

    def _log_recoveries(self) -> None:
        """把"留档的损坏文件"与"禁止写入的文件"汇总进日志 —— 应用还能起，但必须留痕。"""
        recovered = {name: model.recovered_from for model, name in self._models()
                     if model.recovered_from is not None}
        if recovered:
            detail = "、".join(f"{n}→{p.name}" for n, p in recovered.items())
            logger.error("载入时有 %d 个文件损坏，现场已留档（当前用的是默认值）：%s",
                         len(recovered), detail)
        blocked = [name for model, name in self._models() if model._write_blocked]
        if blocked:
            names = "、".join(blocked)
            logger.error("以下文件损坏且留档失败，已禁止写入（请手工处理后再用）：%s", names)

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

        **冲突判定只有一份实现**：`BaseJsonModel.save()` 的磁盘指纹基线。
        不能用"磁盘内容 == 内存态"来判 —— 启动自愈（补订阅分类 / `item_seq` /
        默认目标日、按当前日期重算状态）只改内存、不改磁盘，这种差异**不是**外部
        改动；旧实现把它当冲突，于是每次打开→退出都刷副本并弹窗（`ERRORS #061`）。

        - 文件缺失 → 正常落盘（没东西可保护）
        - 磁盘内容 == 内存态 → **不碰文件**（各面板本来就显式保存，这里是兜底）
        - 其余 → 交给 `save()`：指纹与基线一致（只是自愈）→ 安全写入；
          不一致（真实外部改动）/ 损坏 → `_report_conflict()` → 留副本 + 发信号；
          没有基线（`_disk_fingerprint is None`）→ 同样 fail-closed，禁止覆盖
        """
        for model, _name in self._models():
            if not model.file_path.exists():
                model.save()
                continue
            state, current = model._read_disk_state()
            if state == "ok" and current == model._fingerprint(model.data):
                continue
            if model._disk_fingerprint is None:
                # 没有基线就无法区分"自愈"与"外部改动" → 按冲突处理，禁止覆盖
                model._report_conflict()
                continue
            model.save()
        self._capture_mtimes()

    def get_today_summary(self) -> dict:
        return {
            "pending_tasks": len(self.tasks.pending),
            "pending_habits": len(self.habits.get_pending_today()),
            "today_expense": self.expenses.today_total(),
            "budget_remaining": self.expenses.budget.get("monthly", 0) - self.expenses.month_total(),
            "today_courses": self.courses.get_today_courses(),
        }
