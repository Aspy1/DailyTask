"""作业附件存储：**文件落在磁盘、JSON 只存元数据**。

设计要点（与 `ARCHITECTURE.md` §8 的 schema 约定一致）：

- 目录布局 `<data_dir>/attachments/<task_id>/<stored_name>` —— **不存绝对路径**。
  JSON 里的 `task["attachments"]` 只是一组 dict：
  `{name, stored_name, size, sha256, added_at}`。
  存绝对路径的话，数据目录一搬家（换机器 / 换盘符 / 沙箱测试）全部失效。
- 文件系统本身**不是**事务性的，而 `tasks.json` 是。所以顺序固定为
  **先提交索引、再删文件**（`remove(..., commit=...)`）：索引没提交成功就**不删**，
  宁可留一个孤儿文件，也不让"JSON 里还指着一个已被删掉的文件"。
- `DataManager` 持有 `self.attachments`；根目录来自 `dm.data_dir`（**不是**模块级的
  `get_data_dir()` —— 测试与沙箱靠注入目录工作）。

安全（用户给的可能是任意路径）：

- 只取 basename，非法字符 / Windows 保留名 / 结尾点号一律清洗（`sanitize_filename`）；
- 真正落盘前再校验一次"解析后的路径仍在 root 内"，越界抛 `AttachmentPathInvalid`；
- 目录与符号链接**拒绝**（复制一个 .lnk/.symlink 只会让下游打不开或指向任意位置）。
"""

import hashlib
import logging
import os
import re
import shutil
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 单个附件上限 25 MB、每个作业最多 20 个 —— 超过就明确报错，不静默截断
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES_PER_TASK = 20
# 文件名长度上限（Windows 单段 255，留出 `<hash16>-` 前缀与 `.part` 临时后缀）
MAX_NAME_LEN = 120
HASH_PREFIX_LEN = 16
STORE_DIR_NAME = "attachments"

# `<>:"/\|?*` 与全部控制字符：Windows 上非法；POSIX 上也会让路径解析歧义
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
# Windows 设备名（不分大小写、带不带扩展名都算）
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
    + [f"COM{i}" for i in ("¹", "²", "³")]
    + [f"LPT{i}" for i in ("¹", "²", "³")]
)
_SAFE_TASK_KEY = re.compile(r"[^A-Za-z0-9_-]")


class AttachmentError(Exception):
    """附件操作失败（**可预期**的失败：超限 / 源不合法 / 越界）。

    `code` 是稳定标识，UI 据此映射 i18n 文案 —— 服务层不写中文、不弹窗。
    子类只覆盖 `code`，抛错时仍可带上诊断用的英文说明给日志。
    """

    code = "failed"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code)


class AttachmentTooLarge(AttachmentError):
    code = "too_large"


class AttachmentLimitReached(AttachmentError):
    code = "too_many"


class AttachmentSourceRejected(AttachmentError):
    """源不是普通文件：目录 / 符号链接 / 不存在 / 不可读。"""

    code = "rejected"


class AttachmentPathInvalid(AttachmentError):
    """解析后的路径跑到 root 外面（路径穿越）。"""

    code = "unsafe_path"


def _basename_only(raw: str) -> str:
    """只留最后一段（两种分隔符都处理：路径可能来自 Windows 也可能来自 POSIX 输入）。"""
    return raw.replace("\\", "/").rsplit("/", 1)[-1]


def _strip_illegal(raw: str) -> str:
    """去掉非法字符 / 控制字符 / 结尾点号与空格。"""
    cleaned = _ILLEGAL_CHARS.sub("_", raw)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    return cleaned.rstrip(". ")


def _split_ext(name: str) -> tuple[str, str]:
    """拆主名与扩展名（没有扩展名时 ext 为空串）。"""
    stem, dot, ext = name.rpartition(".")
    return (stem, ext) if dot else (name, "")


def _escape_reserved(stem: str, ext: str) -> str:
    """Windows 保留名（`CON` / `com1.txt` …）前加 `_`。"""
    if stem.upper() in _RESERVED_NAMES or (not stem and ext.upper() in _RESERVED_NAMES):
        return f"_{stem}" if stem else "_"
    return stem


def _truncate_stem(stem: str, ext: str) -> str:
    """超长时截断主名（保留扩展名）。"""
    limit = MAX_NAME_LEN - (len(ext) + 1 if ext else 0)
    return stem[:max(1, limit)]


def sanitize_filename(name: str, fallback: str = "file") -> str:
    """把任意字符串清洗成**可安全落盘**的单个文件名片段。

    - 只保留 basename（`..\\..\\x.txt` → `x.txt`，`/etc/passwd` → `passwd`）
    - 去掉 `<>:"/\\|?*` 与控制字符；连续空白压成一个空格
    - 去掉结尾的 `.` 与空格（Windows 上 `a.` 与 `a` 是同一个文件，会互相覆盖）
    - Windows 保留名（`CON` / `com1.txt` …）前面加 `_`
    - 超长则截断（保留扩展名）
    """
    raw = _strip_illegal(_basename_only(str(name or "")))
    if raw in ("", ".", ".."):
        return fallback
    stem, ext = _split_ext(raw)
    stem = _truncate_stem(_escape_reserved(stem, ext), ext)
    built = f"{stem}.{ext}" if ext else stem
    return built.rstrip(". ") or fallback


def task_key(task_id: str) -> str:
    """任务 id → 目录名片段（只允许字母数字下划线短横线）。"""
    key = _SAFE_TASK_KEY.sub("_", str(task_id or "").strip())[:64]
    return key or "unknown"


def human_size(size: int) -> str:
    """字节数 → 人类可读（**纯函数**，无中文，语言无关）。"""
    try:
        value = max(0, int(size))
    except (TypeError, ValueError):
        return "0 B"
    if value < 1024:
        return f"{value} B"
    if value < 1024 ** 2:
        return f"{value / 1024:.1f} KB"
    return f"{value / 1024 ** 2:.1f} MB"


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AttachmentStore:
    """`<root>/<task_key>/<stored_name>` 的读写门面。

    `root` 由调用方给定（`DataManager` 传 `Path(dm.data_dir) / "attachments"`）。
    本类**不碰** tasks.json，也不决定"什么时候保存索引" —— 那是调用方的事。
    """

    def __init__(self, root: Path, max_bytes: int = MAX_FILE_BYTES,
                 max_files: int = MAX_FILES_PER_TASK) -> None:
        self.root = Path(root)
        self.max_bytes = int(max_bytes)
        self.max_files = int(max_files)

    # ── 路径 ────────────────────────────────────────────────

    def _root_resolved(self) -> Path:
        return self.root.resolve()

    def _inside_root(self, path: Path) -> bool:
        """解析后是否仍在 root 内（**符号链接也要解析**，防链接指向外面）。"""
        try:
            return path.resolve().is_relative_to(self._root_resolved())
        except OSError:
            logger.debug("附件路径解析失败：%s", path, exc_info=True)
            return False

    def task_dir(self, task_id: str) -> Path:
        return self.root / task_key(task_id)

    def resolve(self, task_id: str, stored_name: str) -> Path | None:
        """**不抛异常**地取一个附件路径；不存在或越界返回 None（= 缺失状态）。"""
        safe = sanitize_filename(stored_name, fallback="")
        if not safe or safe != stored_name:
            # stored_name 是我们自己生成的：不该带路径分隔符/非法字符
            logger.warning("附件名不合法，按缺失处理：%r", stored_name)
            return None
        path = self.task_dir(task_id) / safe
        if not self._inside_root(path):
            logger.warning("附件路径越界，按缺失处理：%s", path)
            return None
        return path if path.is_file() else None

    def _target(self, task_id: str, stored_name: str) -> Path:
        safe = sanitize_filename(stored_name, fallback="")
        if not safe or safe != stored_name:
            raise AttachmentPathInvalid(f"非法的存储名：{stored_name!r}")
        path = self.task_dir(task_id) / safe
        if not self._inside_root(path):
            raise AttachmentPathInvalid(f"附件路径越界：{path}")
        return path

    # ── 新增 ────────────────────────────────────────────────

    def add(self, task_id: str, source: str | Path,
            existing: Iterable[dict] = ()) -> dict:
        """复制一个文件进本任务，返回要写进 `task["attachments"]` 的元数据。

        - `existing` = 该任务**当前**的附件列表（用来判断"够不够 20 个"与去重）
        - 同内容（sha256 相同）→ 返回已有条目，**不重复落盘**（文件丢了会补回）
        - 目录 / 符号链接 / 不存在 / 超过 25 MB / 超过 20 个 → 抛 `AttachmentError` 子类
        """
        src, size = self._checked_source(source)
        entries = [e for e in existing if isinstance(e, dict)]
        digest = _sha256_of(src)
        dup = self._reuse_duplicate(task_id, src, digest, entries)
        if dup is not None:
            return dup
        # 数量以**磁盘上已有的文件数**为准（调用方漏传 existing 也拦得住），
        # 元数据条数只作下界（文件被手工删过时仍按索引计）
        used = max(len(entries), self._file_count(task_id))
        if used >= self.max_files:
            raise AttachmentLimitReached(f"{used} >= {self.max_files}")
        return self._store_new(task_id, src, size, digest)

    def _checked_source(self, source: str | Path) -> tuple[Path, int]:
        """校验源文件：必须是普通文件、可读、不超过大小上限。"""
        src = Path(source)
        if src.is_symlink() or not src.is_file():
            raise AttachmentSourceRejected(f"不是普通文件：{src}")
        try:
            size = src.stat().st_size
        except OSError as e:
            raise AttachmentSourceRejected(f"读不到源文件：{src}") from e
        if size > self.max_bytes:
            raise AttachmentTooLarge(f"{size} > {self.max_bytes}")
        return src, size

    def _reuse_duplicate(self, task_id: str, src: Path, digest: str,
                         entries: list[dict]) -> dict | None:
        """同内容已在列表里 → 复用那条元数据（文件被手工删过就补回来）。"""
        for entry in entries:
            if entry.get("sha256") != digest:
                continue
            stored = str(entry.get("stored_name") or "")
            if stored:
                self._copy_atomic(src, self._target(task_id, stored), replace_missing=True)
            logger.debug("附件重复（sha256 命中），复用条目：%s", stored)
            return dict(entry)
        return None

    def _store_new(self, task_id: str, src: Path, size: int, digest: str) -> dict:
        """真正复制一份新文件，返回它的元数据。"""
        name = sanitize_filename(src.name)
        stored_name = f"{digest[:HASH_PREFIX_LEN]}-{name}"
        self._copy_atomic(src, self._target(task_id, stored_name))
        return {
            "name": name,
            "stored_name": stored_name,
            "size": size,
            "sha256": digest,
            "added_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _file_count(self, task_id: str) -> int:
        """任务目录下已有的附件文件数（不含 `.part` 临时文件）。"""
        folder = self.task_dir(task_id)
        if not self._inside_root(folder) or not folder.is_dir():
            return 0
        return sum(1 for p in folder.iterdir()
                   if p.is_file() and not p.name.endswith(".part"))

    def _copy_atomic(self, src: Path, target: Path, *, replace_missing: bool = False) -> None:
        """先写 `.part` 再 `os.replace` —— 中途失败不会留下半个文件。"""
        if replace_missing and target.is_file():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, target)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise AttachmentSourceRejected(f"复制失败：{src} → {target}") from e

    # ── 删除 ────────────────────────────────────────────────

    def remove(self, task_id: str, stored_name: str, *,
               commit: Callable[[], bool] | None = None) -> bool:
        """**先提交索引、再删文件**（`commit` 返回 False 时一个字节都不删）。

        `commit` 由调用方传入（通常 = `model.update(...)` + `model.save()` 的结果）。
        索引没写成 → 文件留着（孤儿文件可以清理，反向则无解）。
        """
        if commit is None:
            raise TypeError("remove() 必须传 commit（索引先写、文件后删）")
        if not commit():
            logger.warning("索引未提交，保留附件文件：%s/%s", task_id, stored_name)
            return False
        return self.discard(task_id, stored_name)

    def discard(self, task_id: str, stored_name: str) -> bool:
        """直接删一个文件（**不做**索引提交）；用于回滚本次新增与提交后的清理。"""
        path = self.resolve(task_id, stored_name)
        if path is None:
            return False
        try:
            path.unlink()
        except OSError:
            logger.error("删除附件失败：%s", path, exc_info=True)
            return False
        return True

    def remove_task(self, task_id: str) -> int:
        """删掉整条任务的附件目录，返回删掉的文件数（不在 root 内 → 0）。"""
        folder = self.task_dir(task_id)
        if not self._inside_root(folder) or not folder.is_dir():
            return 0
        count = sum(1 for p in folder.iterdir() if p.is_file())
        try:
            shutil.rmtree(folder)
        except OSError:
            logger.error("删除任务附件目录失败：%s", folder, exc_info=True)
            return 0
        return count

    # ── 诊断 ────────────────────────────────────────────────

    def orphan_report(self, tasks: Iterable[dict]) -> dict[str, list[str]]:
        """列出磁盘上**没人引用**的目录 / 文件（相对 root 的 posix 路径）。

        只报告、不删除 —— 删文件是不可逆动作，应该由用户看着报告决定。
        """
        referenced = _referenced_files(tasks)
        report: dict[str, list[str]] = {"task_dirs": [], "files": []}
        if not self.root.is_dir():
            return report
        for folder in sorted(p for p in self.root.iterdir() if p.is_dir()):
            if folder.name not in referenced:
                report["task_dirs"].append(folder.name)
                continue
            report["files"] += _stray_files(folder, referenced[folder.name])
        return report


def _referenced_files(tasks: Iterable[dict]) -> dict[str, set[str]]:
    """任务列表 → `{task_key: {stored_name, …}}`（索引里**声明**存在的文件）。"""
    referenced: dict[str, set[str]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        names = referenced.setdefault(task_key(str(task.get("id") or "")), set())
        for entry in task.get("attachments") or []:
            if isinstance(entry, dict) and entry.get("stored_name"):
                names.add(str(entry["stored_name"]))
    return referenced


def _stray_files(folder: Path, referenced: set[str]) -> list[str]:
    """已知任务目录里"索引没提过"的文件（相对 root 的 posix 路径）。"""
    return [f"{folder.name}/{item.name}"
            for item in sorted(p for p in folder.iterdir() if p.is_file())
            if item.name not in referenced]
