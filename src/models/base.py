import copy
import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


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
            self.load()

    def load(self) -> dict[str, Any]:
        with open(self.file_path, encoding="utf-8") as f:
            self._data = json.load(f)
        # 自愈：旧文件可能早于版本键存在（Q-E4）；缺失即按 v1 处理
        self._data.setdefault("_version", 1)
        # 记下"我们看到的磁盘内容"：保存前拿它判断有没有别人改过（见 `save()`）
        self._disk_fingerprint = self._fingerprint(self._data)
        return self._data

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

    def migrate(self, target_version: int) -> None:
        current = self.version
        if current >= target_version:
            return
        method_name = f"_migrate_v{current}_to_v{target_version}"
        if hasattr(self, method_name):
            getattr(self, method_name)()
        self._data["_version"] = target_version
        self.save()
