import contextlib
import copy
import hashlib
import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

try:                       # Windows：OS 级文件锁（进程崩了由系统释放，不会留死锁）
    import msvcrt as _msvcrt
except ImportError:        # 其它平台：退回进程内锁（本项目只在 Windows 上跑）
    _msvcrt = None

logger = logging.getLogger(__name__)

# 进程内**唯一的写入锁**（审查 2026-10-17 #1）。
#
# `save()` 的"读磁盘指纹 → 比较 → 写"三步必须互斥：否则两个写入者会各自通过检查，
# 后写者**静默**覆盖前写者，且双方都返回成功（审查方隔离复现过）。加锁不保证"都写成功"，
# 但保证**至少有一个被拒绝并告知** —— 这正是要的性质。
#
# ⚠ `scripts/actions_core.py`（AI 那条写数据路径）在**同一进程**里也必须用它，
# 否则 AI 工作线程与 UI 线程照样交错。
WRITE_LOCK = threading.RLock()


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """**跨进程**的文件锁：同一个文件的写入者互斥。

    进程内的 `WRITE_LOCK` 只挡得住同进程的线程 —— 应用关掉之后，两个 CLI 各写各的，
    仍会同时通过指纹检查、后写者覆盖前写者（审查 2026-10-17 第三轮 #2）。
    这里加一层 OS 级文件锁：Windows 用 `msvcrt.locking`（进程退出即释放，不留死锁），
    其它平台退回进程内锁。

    ⚠ 覆盖范围：**指纹检查 + 写入**整段 —— 调用方把这两件事都放在 `with` 里。
    """
    with WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 这个 handle 必须活过 with 体（由 finally 收尾）→ 不能用 with 管
        handle = open(path.with_name(path.name + ".lock"), "a+b")  # noqa: SIM115
        acquired = False
        try:
            if _msvcrt is not None:
                handle.seek(0)
                _msvcrt.locking(handle.fileno(), _msvcrt.LK_LOCK, 1)
                acquired = True
            yield
        finally:
            # 收尾**绝不能再抛异常**（那会掩盖调用方真正的错，审查 2026-10-17 第四轮 #2）：
            # 只在**确实拿到过锁**时解锁，且各自吞掉自己的异常
            if acquired:
                with contextlib.suppress(OSError):     # 进程退出时解锁失败属正常
                    handle.seek(0)
                    _msvcrt.locking(handle.fileno(), _msvcrt.LK_UNLCK, 1)
            with contextlib.suppress(OSError):
                handle.close()


class DataCorrupted(RuntimeError):
    """文件存在但解析不出来 —— 已**留档**（改名保留现场），绝不当作空数据。"""


class MigrationUnavailable(RuntimeError):
    """缺少某一步迁移实现 —— **拒绝**升级（审查 2026-10-17 #5）。"""


class MigrationFailed(RuntimeError):
    """某一步迁移抛错 —— 版本不更新、文件不写。"""


def fingerprint(doc: dict) -> str:
    """内容指纹（`sort_keys` → 与键序无关）。

    `BaseJsonModel` 与 `scripts/actions_core.py`（AI 那条写入路径）共用它 ——
    两条路都要能判断"磁盘上这份内容还是不是我读到的那份"（审查 2026-10-17 #1）。
    """
    blob = json.dumps(doc, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def next_id(prefix: str, existing_ids: Iterable[str], width: int = 3) -> str:
    """按现有 ID 的**最大数字后缀 + 1** 生成新 ID。

    R-008 禁止 `len()+1` 生成 ID：删过条目后列表长度不再等于最大序号，
    新 ID 会与既有 ID 撞车（删掉 `c_002` 后再新增，len 仍为 2 → 又生成 `c_002`）。
    保持 `<prefix>_<零填充数字>` 格式，`actions.py` 的序号解析仍可用。
    """
    max_n = 0
    for raw in existing_ids:
        suffix = str(raw or "").rsplit("_", 1)[-1]
        if suffix.isdigit():
            max_n = max(max_n, int(suffix))
    return f"{prefix}_{max_n + 1:0{width}d}"


class BaseJsonModel:
    file_path: Path
    _data: dict[str, Any]
    # 载入 / 上次写入时**磁盘内容**的指纹（见 `save()`）；None = 还没有比较基准
    _disk_fingerprint: str | None = None
    # 保存冲突时的回调：由 `DataManager` 装上（留副本 + 通知界面）。模型不是 QObject，
    # 所以用回调而不是信号。
    on_conflict: Callable[["BaseJsonModel"], None] | None = None
    # 载入时发现文件损坏 → 留档路径（`DataManager` 汇总进日志/通知）；None = 正常
    recovered_from: Path | None = None
    # 载入时损坏且**留档失败** → 拒绝一切写入（不许毁现场，审查 2026-10-17 #3）
    _write_blocked: bool = False
    # 载入时磁盘版本**比程序支持的新** → 拒绝普通 save，避免静默降级。
    # 单独一个标志而不是每次比较 `self.version`：`migrate()` 会把内存版本抬到
    # 目标版本，那时 `version > supported` 是正常的（测试也覆盖了这一点）。
    _loaded_future: bool = False

    def __init__(self, file_path: Path, default_data: dict[str, Any] | None = None) -> None:
        self.file_path = file_path
        self._default_data = default_data or {"_version": 1}
        self._data = {}
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            # 必须**深拷贝**：DEFAULT_* 是模块级常量，浅拷贝会让所有实例共享同一个
            # 嵌套 list/dict，一个实例 append 后，之后新建的实例（哪怕指向另一个数据
            # 目录）会凭空多出这些条目（ERRORS #024）。
            self._data = copy.deepcopy(self._default_data)
            self.save()
        else:
            try:
                self.load()
            except DataCorrupted:
                # 已留档（`load()` 干的）→ 用默认值继续，别让应用起不来。
                # 现场路径记在 `recovered_from`，`DataManager` 会汇总进日志
                self._data = copy.deepcopy(self._default_data)
                self._disk_fingerprint = None
                if self.recovered_from is None:
                    # 留档**失败** → 损坏现场还在原地 → **不许**建替代文件
                    # （否则一写就把现场毁了，审查 2026-10-17 #3）
                    self._write_blocked = True
                    logger.error("%s 损坏且留档失败，已禁止写入以免毁掉现场",
                                 self.file_path.name)
                else:
                    self.save()

    def load(self) -> dict[str, Any]:
        with open(self.file_path, encoding="utf-8") as f:
            raw = f.read()
        try:
            self._data = json.loads(raw)
        except json.JSONDecodeError as e:
            # 损坏 ≠ 缺失：**保留现场**（改名留档）后抛，由 `__init__` 退回默认值。
            # 绝不静默当空数据（审查 2026-10-17 #5）
            self.recovered_from = self._quarantine()
            kept = (self.recovered_from.name if self.recovered_from
                    else "留档失败，现场仍在原处")
            raise DataCorrupted(
                f"{self.file_path.name} 无法解析（{kept}）：{e}") from e
        # 自愈：旧文件可能早于版本键存在（Q-E4）；缺失即按 v1 处理
        self._data.setdefault("_version", 1)
        self._loaded_future = self.version > self.supported_version
        if self._loaded_future:
            # 比本程序认识的版本还新（可能是更新版应用写的）→ 只警告，不改动数据
            note = (f"{self.file_path.name} 的 _version={self.version} "
                    f"比本程序支持的 v{self.supported_version} 新")
            logger.warning("%s —— 不做任何迁移，也不当作可覆盖的目标", note)
        # 记下"我们看到的磁盘内容"：保存前拿它判断有没有别人改过（见 `save()`）
        self._disk_fingerprint = self._fingerprint(self._data)
        return self._data

    def _quarantine(self) -> Path | None:
        """把当前文件改名留档（**保留现场**）；**失败返回 None**。

        返回 None 时调用方必须拒绝写入 —— 现场还在原地，写替代文件等于毁掉它
        （审查 2026-10-17 #3）。
        """
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        keep = self.file_path.with_name(
            f"{self.file_path.stem}.corrupt-{stamp}{self.file_path.suffix}")
        try:
            os.replace(self.file_path, keep)
        except OSError:
            logger.error("留档失败：%s", self.file_path, exc_info=True)
            return None
        return keep

    def reload(self) -> None:
        """Re-read data from disk, discarding in-memory changes."""
        self.load()

    def save(self) -> bool:
        """落盘。返回 `False` 表示**没写**（磁盘被别人改过或读不出来，已交 `on_conflict`）。

        冲突检测用**磁盘内容指纹**，不用 mtime（应用自己保存也会动 mtime），也不用
        `_rev` 号 —— 那要求每个写入方都配合维护，而 `scripts/actions_core.py`、skill、
        手工编辑都会漏，于是冲突**静默**通过（那正是要修的问题）。指纹与键序无关，
        所以"只是被重新格式化过"不算改动。

        **"读指纹 → 比较 → 写"整段持 `WRITE_LOCK`**（审查 2026-10-17 #1）：否则两个写入者
        各自通过检查、后写者静默覆盖。加锁后至少有一个会被拒绝。

        ⚠ 冲突时**不抛异常**：`save()` 有二十来个调用点（各面板改完就存），抛出去会把
        UI 打崩。留副本 + 通知由 `on_conflict`（`DataManager` 装上）负责。
        """
        with file_lock(self.file_path):
            if self._write_blocked:
                # 载入时损坏且留档失败 → 一律不写（审查 2026-10-17 #3）
                self._report_conflict()
                return False
            if self._loaded_future:
                # 文件是**更新版应用**写的：本程序不认识新字段，写回去等于静默降级
                # （文档一直这么承诺，但旧实现只警告、`save()` 照样覆盖 ✗）
                logger.error("%s 的 _version=%d 比本程序支持的新，拒绝写入以免丢字段",
                             self.file_path.name, self.version)
                self._report_conflict()
                return False
            if self._disk_fingerprint is not None:
                state, current = self._read_disk_state()
                if state == "unreadable":
                    # 文件在但读不出来 → **拒绝覆盖**（写下去现场就没了，审查 #3）
                    self._report_conflict()
                    return False
                if state == "ok" and current != self._disk_fingerprint:
                    self._report_conflict()
                    return False
            self.atomic_write()
            self._disk_fingerprint = self._fingerprint(self._data)
            return True

    def _report_conflict(self) -> None:
        """把"这次没写"交给上层（留副本 + 通知），模型自己不弹窗也不抛异常。"""
        logger.warning("%s 保存被拒：磁盘内容与内存不一致或无法读取", self.file_path.name)
        if self.on_conflict is not None:
            self.on_conflict(self)

    @staticmethod
    def _fingerprint(doc: dict) -> str:
        """内容指纹（与 `base.fingerprint()` 同一实现，两处不各写一份）。"""
        return fingerprint(doc)

    def _read_disk_state(self) -> tuple[str, str | None]:
        """磁盘状态：(状态, 指纹)。状态 ∈ `missing` / `ok` / `unreadable`。

        `unreadable` = 文件在、但读不出来（损坏 / 权限）—— 调用方**必须拒绝覆盖**：
        覆盖会把现场毁掉（审查 2026-10-17 #3）。
        """
        if not self.file_path.exists():
            return "missing", None
        try:
            with open(self.file_path, encoding="utf-8") as f:
                return "ok", self._fingerprint(json.load(f))
        except (OSError, json.JSONDecodeError):
            return "unreadable", None

    def atomic_write(self) -> None:
        tmp_path = self.file_path.with_suffix(".tmp")
        bak_path = self.file_path.with_suffix(".bak")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)

            if self.file_path.exists():
                shutil.copy2(self.file_path, bak_path)

            # Retry on PermissionError (Windows Defender / file indexer lock)
            for attempt in range(5):
                try:
                    os.replace(tmp_path, self.file_path)
                    break
                except PermissionError:
                    if attempt < 4:
                        time.sleep(0.05)
                    else:
                        raise

            if bak_path.exists():
                bak_path.unlink()
        except Exception:
            if bak_path.exists() and not self.file_path.exists():
                shutil.copy2(bak_path, self.file_path)
            raise

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @data.setter
    def data(self, value: dict[str, Any]) -> None:
        self._data = value

    @property
    def version(self) -> int:
        return self._data.get("_version", 1)

    @property
    def supported_version(self) -> int:
        """本程序认识的版本（= 默认数据的版本）。比它新 = 更新版应用写的。"""
        return int(self._default_data.get("_version", 1))

    def migrate(self, target_version: int) -> None:
        """把数据迁到 `target_version`：**逐步**执行，缺一步就拒绝（审查 2026-10-17 #5）。

        - 逐步：v1→v2→v3 依次调 `_migrate_v1_to_v2` / `_migrate_v2_to_v3`
        - **缺哪一步就抛 `MigrationUnavailable`，一个字节都不写** ——
          旧实现找不到方法也照样把 `_version` 抬上去，数据"看起来迁过了"其实没有
        - 任一步抛错 → `MigrationFailed`，版本与文件都保持原样
        """
        current = self.version
        if current >= target_version:
            return
        steps = self._migration_steps(current, target_version)
        # 在**深拷贝**上迁移：任一步失败都不动内存（否则会出现"磁盘 v1、内存 v2 半成品"，
        # 之后一次普通保存就把失败迁移的中间态写进文件，审查 2026-10-17 #5）
        original = self._data
        self._data = copy.deepcopy(original)
        try:
            for from_v, to_v, method in steps:
                try:
                    method()
                except Exception as e:
                    raise MigrationFailed(f"迁移 v{from_v}→v{to_v} 失败：{e}") from e
                self._data["_version"] = to_v
        except Exception:
            self._data = original          # 回滚内存，与磁盘保持一致
            raise
        # 最终写盘也在事务边界内：被拒（磁盘被外部改过）或抛错 → 内存一并回滚，
        # 并明确报"迁移没完成"（审查 2026-10-17 第三轮 #3）
        was_future = self._loaded_future
        self._loaded_future = False       # 迁移是显式动作，目标版本可以高于默认版本
        try:
            saved = self.save()
        except Exception as e:
            self._data = original
            self._loaded_future = was_future
            raise MigrationFailed(f"迁移结果写盘失败：{e}") from e
        if not saved:
            self._data = original
            self._loaded_future = was_future
            raise MigrationFailed(
                "迁移结果没能写盘（磁盘内容已被外部改动）—— 内存与磁盘都保持原样")

    def _migration_steps(self, current: int, target: int) -> list[tuple]:
        """把迁移拆成逐步，并**先整条检查一遍**：缺哪一步就在这里抛。"""
        steps = []
        for from_v in range(current, target):
            method = getattr(self, f"_migrate_v{from_v}_to_v{from_v + 1}", None)
            if method is None:
                raise MigrationUnavailable(
                    f"{type(self).__name__} 缺少 v{from_v}→v{from_v + 1} 的迁移实现，"
                    f"拒绝把版本抬到 v{target}（数据未改动）")
            steps.append((from_v, from_v + 1, method))
        return steps
