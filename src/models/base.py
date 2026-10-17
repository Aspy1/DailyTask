import copy
import hashlib
import json
import logging
import os
import shutil
import time
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DataCorrupted(RuntimeError):
    """文件存在但解析不出来 —— 已**留档**（改名保留现场），绝不当作空数据。"""


class MigrationUnavailable(RuntimeError):
    """缺少某一步迁移实现 —— **拒绝**升级（审查 2026-10-17 #5）。"""


class MigrationFailed(RuntimeError):
    """某一步迁移抛错 —— 版本不更新、文件不写。"""


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
            raise DataCorrupted(
                f"{self.file_path.name} 无法解析（现场已留档 {self.recovered_from.name}）：{e}"
            ) from e
        # 自愈：旧文件可能早于版本键存在（Q-E4）；缺失即按 v1 处理
        self._data.setdefault("_version", 1)
        if self.version > self.supported_version:
            # 比本程序认识的版本还新（可能是更新版应用写的）→ 只警告，不改动数据
            note = (f"{self.file_path.name} 的 _version={self.version} "
                    f"比本程序支持的 v{self.supported_version} 新")
            logger.warning("%s —— 不做任何迁移，也不当作可覆盖的目标", note)
        # 记下"我们看到的磁盘内容"：保存前拿它判断有没有别人改过（见 `save()`）
        self._disk_fingerprint = self._fingerprint(self._data)
        return self._data

    def _quarantine(self) -> Path:
        """把当前文件改名留档（**保留现场**），返回留档路径。"""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        keep = self.file_path.with_name(
            f"{self.file_path.stem}.corrupt-{stamp}{self.file_path.suffix}")
        try:
            os.replace(self.file_path, keep)
        except OSError:
            keep = self.file_path          # 没搬成 → 返回原路径（调用方据此知道）
            logger.error("留档失败：%s", self.file_path, exc_info=True)
        return keep

    def reload(self) -> None:
        """Re-read data from disk, discarding in-memory changes."""
        self.load()

    def save(self) -> bool:
        """落盘。返回 `False` 表示**没写**（磁盘被别人改过，已交 `on_conflict`）。

        冲突检测用**磁盘内容指纹**，不用 mtime（应用自己保存也会动 mtime），也不用
        `_rev` 号 —— 那要求每个写入方都配合维护，而 `scripts/actions_core.py`、skill、
        手工编辑都会漏，于是冲突**静默**通过（那正是要修的问题）。指纹与键序无关，
        所以"只是被重新格式化过"不算改动。

        ⚠ 冲突时**不抛异常**：`save()` 有二十来个调用点（各面板改完就存），抛出去会把
        UI 打崩。留副本 + 通知由 `on_conflict`（`DataManager` 装上）负责。
        """
        if self._disk_fingerprint is not None:
            current = self._read_disk_fingerprint()
            if current is not None and current != self._disk_fingerprint:
                if self.on_conflict is not None:
                    self.on_conflict(self)
                return False
        self.atomic_write()
        self._disk_fingerprint = self._fingerprint(self._data)
        return True

    @staticmethod
    def _fingerprint(doc: dict) -> str:
        """内容指纹（`sort_keys` → 与键序无关）。"""
        blob = json.dumps(doc, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _read_disk_fingerprint(self) -> str | None:
        """磁盘上那份内容的指纹；文件缺失 / 损坏返回 None（当作"没有可冲突的对象"）。"""
        try:
            with open(self.file_path, encoding="utf-8") as f:
                return self._fingerprint(json.load(f))
        except (OSError, json.JSONDecodeError):
            return None

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
        for from_v, to_v, method in steps:
            try:
                method()
            except Exception as e:
                raise MigrationFailed(f"迁移 v{from_v}→v{to_v} 失败：{e}") from e
            self._data["_version"] = to_v
        self.save()

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
