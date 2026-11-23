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
    """文件存在但**内容**不能用 —— 已**留档**（改名保留现场），绝不当作空数据。

    含义固定为"这份现场已经不可恢复"：JSON 解析失败、根不是对象、`_version`
    类型不对、编码非法、schema 不符都归到这里。**不包括**"暂时读不出来"（见 `Unreadable`）。
    """


class Unreadable(RuntimeError):
    """文件**暂时**读不出来（被别的进程占用 / 权限 / 磁盘忙）—— 可恢复，重试即可。

    与 `DataCorrupted` 分开的理由：损坏要留档，暂时不可读**不能**留档
    （那会把一份好文件永久改名为 `.corrupt-*`，审计 2026-11-21 P1）。
    """


class MigrationUnavailable(RuntimeError):
    """缺少某一步迁移实现 —— **拒绝**升级（审查 2026-10-17 #5）。"""


class MigrationFailed(RuntimeError):
    """某一步迁移抛错 —— 版本不更新、文件不写。"""


# "暂时不可读"的重试节奏：Windows 上 Defender / 索引服务会短暂独占文件。
READ_ATTEMPTS = 5
READ_RETRY_SECONDS = 0.05


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
            except Unreadable as e:
                # **暂时**读不出来：现场是好的，绝不能留档，也不能覆盖它。
                # 用默认值让应用起来，写入一律拒绝（等下一次轮询重试）。
                self._data = copy.deepcopy(self._default_data)
                self._disk_fingerprint = None
                self._write_blocked = True
                logger.warning("%s %s —— 暂用默认值，本次不写入", self.file_path.name, e)

    def load(self) -> dict[str, Any]:
        """读盘 → 分类处理（审计 2026-11-21 P1：五种状态必须分开）。

        | 状态 | 判据 | 处理 |
        |---|---|---|
        | 缺失 | 文件不存在 | 建默认值（`_ensure_file`） |
        | **暂时不可读** | `OSError` 重试后仍失败 | 抛 `Unreadable`：**不留档**，上层用默认值继续并禁止写入 |
        | 编码错误 | 非法 UTF-8 | 留档，`DataCorrupted` |
        | 解析失败 | 非法 JSON | 留档，`DataCorrupted` |
        | schema 不符 | 根不是对象 / `_version` 类型不对 / 顶层键类型不对 | 留档，`DataCorrupted` |
        | 未来版本 | `_version` 比本程序新 | **不是损坏**：只警告，只读 |
        """
        raw = self._read_text()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise self._corrupt(f"无法解析：{e}") from e
        problem = self._schema_problem(parsed)
        if problem:
            raise self._corrupt(problem)
        self._data = parsed
        # ⚠ 指纹必须是**磁盘原文**的指纹：下面 `setdefault("_version", 1)` 会改内存态，
        # 而由 `actions.py`/TG 写入的文件可能没有 `_version` → 用改过的内存指纹去比磁盘
        # 永远不相等，第一次保存就被误判成"外部改动"（2026-10-31 全量走查实测）。
        self._disk_fingerprint = self._fingerprint(self._data)
        # 自愈：旧文件可能早于版本键存在（Q-E4）；缺失即按 v1 处理
        self._data.setdefault("_version", 1)
        self._loaded_future = self.version > self.supported_version
        if self._loaded_future:
            # 比本程序认识的版本还新（可能是更新版应用写的）→ 只警告，不改动数据
            note = (f"{self.file_path.name} 的 _version={self.version} "
                    f"比本程序支持的 v{self.supported_version} 新")
            logger.warning("%s —— 不做任何迁移，也不当作可覆盖的目标", note)
        return self._data

    def _read_text(self) -> str:
        """读原文；**暂时不可读**要重试（占用/权限），一直读不出来 → `Unreadable`。

        `UnicodeDecodeError` 在这里就归为损坏（不是"暂时"）：编码不会自己变好。
        """
        last: OSError | None = None
        for attempt in range(READ_ATTEMPTS):
            try:
                # `utf-8-strict`：非法字节必须当成损坏，不能 `errors="replace"`（那会改数据）
                return self.file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as e:
                raise self._corrupt(f"不是合法 UTF-8：{e}") from e
            except OSError as exc:
                last = exc
                if attempt < READ_ATTEMPTS - 1:
                    time.sleep(READ_RETRY_SECONDS)
        raise Unreadable(f"{self.file_path.name} 暂时读不出来：{last}") from last

    def _corrupt(self, detail: str) -> DataCorrupted:
        """留档 + 返回要抛的异常（**保留现场**，绝不静默当空数据）。"""
        self.recovered_from = self._quarantine()
        kept = (self.recovered_from.name if self.recovered_from
                else "留档失败，现场仍在原处")
        return DataCorrupted(f"{self.file_path.name} 损坏（{kept}）：{detail}")

    def _schema_problem(self, parsed: Any) -> str:
        """结构检查 → 空串表示通过。

        这些形状原来会从**别处**炸开（`AttributeError` / `TypeError`），
        既没有留档也没有默认值兜底：根是数组、`_version` 是字符串、顶层键类型不对。
        """
        if not isinstance(parsed, dict):
            return f"顶层必须是 JSON 对象，收到 {type(parsed).__name__}"
        version = parsed.get("_version", 1)
        if isinstance(version, bool) or not isinstance(version, int):
            return f"_version 必须是整数，收到 {type(version).__name__}"
        if version < 1:
            return f"_version 必须 ≥ 1，收到 {version}"
        for key, expected in self._default_data.items():
            if key == "_version" or key not in parsed:
                continue
            if not isinstance(parsed[key], type(expected)):
                return (f"{key} 必须是 {type(expected).__name__}，"
                        f"收到 {type(parsed[key]).__name__}")
        return ""

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
        """Re-read data from disk, discarding in-memory changes.

        ⚠ 成功重载后**解除写入封锁**：`Unreadable` 是暂时的，文件恢复可读后
        那些"本次不写入"的模型要能继续工作（否则一次占用就永久失写）。
        """
        self.load()
        if not self._write_blocked:
            return
        self._write_blocked = False
        self._loaded_future = self.version > self.supported_version
        logger.info("%s 已恢复可读，解除写入封锁", self.file_path.name)

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
        """`.tmp` → 备份 `.bak` → `os.replace`（原子替换）。

        **编码只做一次、只写一次**（2026-11-23 性能改造，cProfile 证据见
        `scripts/perf_profile.py`）：原来 `json.dump(..., indent=2)` 走纯 Python
        编码器并**每几个字符 `write()` 一次** —— 10k 条 × 一次保存 ≈ 54 万次写调用，
        占整次保存的 86%。改成先 `json.dumps` 再一次性写，输出字节完全相同
        （`tests/test_save_encoding.py` 逐字节钉住，含 CRLF 与中文）。

        ⚠ 换行保持平台默认（Windows 文本模式 = CRLF）：这批文件进 git，
        换行风格变了会让整份文件在 diff 里重写。
        """
        tmp_path = self.file_path.with_suffix(".tmp")
        bak_path = self.file_path.with_suffix(".bak")
        try:
            payload = json.dumps(self._data, ensure_ascii=False, indent=2)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(payload)                 # 一次写：不再逐 token 调用

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
            # 失败要**清理临时文件**：原来留一堆 `*.tmp` 在数据目录里（实测复现）
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
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
