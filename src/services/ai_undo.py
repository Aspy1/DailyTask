"""AI 写入的**动作级快照与撤销**（H3/P0，2026-11-02）。

为什么需要：原来"撤销 AI 的写入"只有一条路 —— 整文件 `restore`（用最近一份备份盖回去）。
那是**文件级**回滚：会把同一文件里**别的**改动一起抹掉，而且 `restore --yes` 本来就是
模型可以自己拼出来的命令（见 `ai_policy`：现在已禁止 AI 调用）。快速安排有 undo + stale
检查，AI 写入却什么都没有 ✗。

这里补的是**动作级**：每条写命令执行**之前**给目标文件留一份快照，并记下
`before_hash`（写前）与 `after_hash`（写后）。撤销时：

1. 当前文件指纹 **必须** 等于 `after_hash` —— 否则说明用户在写之后又改过（或别的进程/CLI
   写过），撤销会覆盖那些改动 → **拒绝**（stale），提示改用 `restore`/手动处理；
2. 通过检查 → 用快照原子恢复（`tmp` + `os.replace`），并把快照标成已撤销（不能撤两次）。

⚠ 撤销**不暴露给模型**：没有对应 `actions.py` 命令、提示词里没有它，只有 UI 上的按钮
（`tests/test_ai_policy.py::test_audit_and_undo_are_not_ai_commands` 守着）。

⚠ 快照存在 `<data>/ai_undo/`（子目录）：它是**审计产物**，不是用户数据模型，
不进 `DataManager` 的模型清单，也不经 `actions.py`（R-002 管的是 `data/*.json` 用户数据）。
"""

# 本模块的 `SnapshotStore.list` 会遮蔽内建 `list`；在会**立即求值注解**的 Python 上，
# 后续 `list[Snapshot]` 会变成 `function[...]`，导入即 TypeError。延迟注解以兼容
# （该类里 `list` 方法也刻意排在所有 `list[...]` 注解之后，见类末尾的说明）。
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.models import semester_paths
from src.models.base import file_lock

logger = logging.getLogger(__name__)

DIR_NAME = "ai_undo"
INDEX_NAME = "index.json"
# 登记失败的旁标（索引写不进去时的唯一凭据；`index.json` 本身可能已损坏）
PENDING_NAME = "pending.json"
BLOB_DIR = "blobs"
DEFAULT_KEEP = 50

# 操作 → 它会写的那个数据文件（**唯一映射**；新增写命令要在这里登记）
TARGET_FILES: dict[str, str] = {
    # 物品 / 库存
    "add_item": "inventory.json", "update_item": "inventory.json",
    "delete_item": "inventory.json", "consume": "inventory.json",
    "add_location": "inventory.json", "set_locations": "inventory.json",
    # 作业 / 课程 / 考试（按学期分文件）
    "add_task": "tasks.json", "complete_task": "tasks.json",
    "add_course": "courses.json", "update_course": "courses.json",
    "delete_course": "courses.json",
    "add_exam": "exams.json",
    # 日程 / 存钱
    "add_plan": "daily_logs.json", "replace_plans": "daily_logs.json",
    "delete_plan": "daily_logs.json", "complete_plan": "daily_logs.json",
    "add_saving": "daily_logs.json",
    # 习惯
    "add_habit": "habits.json", "log_habit": "habits.json",
    # 记账
    "add_expense": "expenses.json", "delete_expense": "expenses.json",
    "finance_set": "expenses.json",
    # 考研备考
    "log_study": "study.json", "add_mistake": "study.json",
    "review_mistake": "study.json", "master_mistake": "study.json",
    "add_mock": "study.json", "study_set_target": "study.json",
}


def file_hash(path: Path) -> str:
    """文件内容的 sha256；文件不存在 → 空串。"""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _replace_index(source: Path, target: Path) -> None:
    for delay in (0.01, 0.03, 0.07):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            time.sleep(delay)
    os.replace(source, target)


def current_semester_id(data_dir: Path) -> str:
    """当前学期 id（**只读**解析，不创建默认学期 —— 快照不该有副作用）。"""
    registry = semester_paths.read_registry(Path(data_dir))
    semesters = registry.get("semesters") or []
    current = str(registry.get("current_semester") or "")
    if current and any(s.get("id") == current for s in semesters):
        return current
    if semesters:
        return str(semesters[-1].get("id") or "")
    from src.models.semester import default_semester

    return str(default_semester().get("id") or "")


def target_path(operation: str, data_dir: Path) -> Path | None:
    """这条操作会写的文件路径；没登记 / 不是写操作 → None。"""
    name = TARGET_FILES.get(str(operation or ""))
    if not name or not data_dir:
        return None
    if semester_paths.is_per_semester(name):
        sid = current_semester_id(data_dir)
        if not sid:
            return None
        return semester_paths.semester_dir(Path(data_dir), sid) / name
    return Path(data_dir) / name


@dataclass
class Snapshot:
    """一条写命令的**写前快照**（元数据 + blob 路径）。"""

    snapshot_id: str
    request_id: str = ""
    command: str = ""
    operation: str = ""
    label: str = ""
    target: str = ""                 # 相对 data_dir 的 posix 路径（可读、可审计）
    before_hash: str = ""
    after_hash: str = ""
    blob: str = ""                   # 相对 store 根目录
    created_at: str = field(default_factory=_now)
    undone_at: str = ""
    # 提交回执（审计 2026-11-21 P0）：写入层在目标锁内产生的**实际提交版本**。
    # 旧实现 `finalize` 在命令执行完之后再读盘 —— 中间若有另一个写者，
    # 读到的是**别人**的版本，撤销于是把后来的合法写入抹掉。
    operation_id: str = ""
    committed_version: int = 0
    changed_fields: list[str] = field(default_factory=list)
    # 写入已提交、但索引登记失败 → 数据是真的，撤销记录待修复（不许谎报可撤销）
    pending_repair: bool = False

    @property
    def undoable(self) -> bool:
        # 没有写后指纹（执行中断）或写前=写后（no-op）都不算可撤销：
        # 否则界面会亮起"撤销 AI 写入"，点下去只是把同样的字节再写一遍。
        return bool(self.operation_id) and self.written and not self.undone_at and not self.pending_repair

    @property
    def written(self) -> bool:
        """写后指纹与写前不同 = 这次动作**真的改了文件**。"""
        return bool(self.after_hash) and self.after_hash != self.before_hash

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> Snapshot:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


class SnapshotStore:
    """动作级快照仓库（`<data>/ai_undo/`）。线程安全靠"整份 index 原子替换"。"""

    def __init__(self, root: Path, keep: int = DEFAULT_KEEP) -> None:
        self.root = Path(root)
        self.keep = max(1, int(keep))
        self.data_dir = self.root.parent
        # worker 线程 capture/finalize 与主线程 undo 会并发读改写 index；RLock 允许嵌套调用
        self._index_lock = threading.RLock()

    @classmethod
    def for_data_dir(cls, data_dir, keep: int = DEFAULT_KEEP) -> SnapshotStore | None:
        """按数据目录建快照仓库；`data_dir` 为空 → None（调用方跳过）。"""
        if not data_dir:
            return None
        return cls(Path(data_dir) / DIR_NAME, keep)

    # ── 元数据 ────────────────────────────────────────────
    def _index_file(self) -> Path:
        return self.root / INDEX_NAME

    def _write_index(self, items: list[Snapshot]) -> None:
        with self._index_lock:
            self.root.mkdir(parents=True, exist_ok=True)
            # 唯一临时名：即使未来去掉锁，也不会两个写者共用同一个 .tmp
            tmp = self._index_file().with_name(f"{INDEX_NAME}.{uuid.uuid4().hex}.tmp")
            try:
                tmp.write_text(
                    json.dumps([s.to_dict() for s in items], ensure_ascii=False, indent=2),
                    encoding="utf-8")
                _replace_index(tmp, self._index_file())
            finally:
                tmp.unlink(missing_ok=True)

    # ── 快照 ──────────────────────────────────────────────
    def capture(self, command: str, operation: str = "", request_id: str = "",
                label: str = "") -> Snapshot | None:
        """执行**前**调用：复制目标文件 + 记 `before_hash`。没有目标文件映射 → None。"""
        path = target_path(operation, self.data_dir)
        if path is None:
            return None
        if not path.exists():
            # 动作前文件不存在（本次会新建）→ 撤销等于"删文件"，风险高于收益，直接不留快照
            logger.info("目标文件还不存在，跳过快照：%s", path.name)
            return None
        try:
            payload = path.read_bytes()
        except OSError:
            logger.warning("Unable to read the pre-commit snapshot", exc_info=True)
            return None
        snapshot = Snapshot(
            snapshot_id=uuid.uuid4().hex[:12],
            request_id=request_id, command=str(command or ""),
            operation=operation, label=label,
            target=path.relative_to(self.data_dir).as_posix(),
            before_hash=hashlib.sha256(payload).hexdigest(),
            blob=f"{BLOB_DIR}/{uuid.uuid4().hex[:12]}.json",
        )
        blob_path = self.root / snapshot.blob
        try:
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(payload)
        except OSError:
            logger.error("快照写入失败（本次动作将无法撤销）：%s", path, exc_info=True)
            return None
        with file_lock(self._index_file()), self._index_lock:
            items = self.list()
            items.append(snapshot)
            self._prune(items)
            self._write_index(items)
        return snapshot

    def finalize(self, snapshot: Snapshot | None, receipt: dict | None = None) -> Snapshot | None:
        """执行**后**调用：记下**实际提交**的指纹（撤销的 stale 判据）。

        `receipt` = 写入层在目标文件锁内产生的回执（`scripts.actions_core.last_commit`）。
        缺失或者目标与写前版本对不上时，保留快照供排查，但不允许撤销。

        写入已提交、但索引登记失败 → 返回带 `pending_repair=True` 的快照：
        数据是真的，必须让调用方如实回报「已提交，撤销记录待修复」，不许谎报可撤销。
        """
        if snapshot is None:
            return None
        if receipt and self._matches_receipt(snapshot, receipt):
            snapshot.after_hash = str(receipt.get("after_sha") or "")
            snapshot.operation_id = str(receipt.get("operation_id") or "")
            snapshot.committed_version = int(receipt.get("version") or 0)
            snapshot.changed_fields = list(receipt.get("changed_fields") or [])
        else:
            logger.info("No matching commit receipt for undo: %s", snapshot.target)
            return snapshot
        return self._register(snapshot)

    def _matches_receipt(self, snapshot: Snapshot, receipt: dict) -> bool:
        return (bool(receipt.get("operation_id"))
                and bool(receipt.get("after_sha"))
                and receipt.get("before_sha") == snapshot.before_hash
                and Path(str(receipt.get("target") or "")).resolve() ==
                (self.data_dir / snapshot.target).resolve())

    def _register(self, snapshot: Snapshot) -> Snapshot:
        """把写后指纹登记进索引；失败 → 标记 `pending_repair`（不抛，数据已提交）。

        登记失败时索引里那一行仍是"写后指纹缺失"的老样子 —— 下次读取会被当成
        "执行中断"，所以额外落一个旁标文件，让后续的撤销能如实说出**是哪一种**缺。
        """
        try:
            with file_lock(self._index_file()), self._index_lock:
                items = self.list()
                for item in items:
                    if item.snapshot_id == snapshot.snapshot_id:
                        item.after_hash = snapshot.after_hash
                        item.operation_id = snapshot.operation_id
                        item.committed_version = snapshot.committed_version
                        item.changed_fields = list(snapshot.changed_fields)
                self._write_index(items)
        except OSError:
            snapshot.pending_repair = True
            logger.error("撤销记录登记失败（数据已提交）：%s", snapshot.target, exc_info=True)
            try:
                with file_lock(self._index_file()):
                    self._mark_pending(snapshot)
            except OSError:
                logger.error("Unable to persist the undo repair marker", exc_info=True)
        return snapshot

    def _pending_file(self) -> Path:
        return self.root / PENDING_NAME

    def _mark_pending(self, snapshot: Snapshot) -> None:
        """旁标：`{snapshot_id: 写后指纹}`（索引写不进去时的唯一凭据）。"""
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            raw = json.loads(self._pending_file().read_text(encoding="utf-8"))
            pending = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            pending = {}
        pending[snapshot.snapshot_id] = {"after_hash": snapshot.after_hash,
                                        "operation_id": snapshot.operation_id}
        tmp = self._pending_file().with_name(PENDING_NAME + ".tmp")
        try:
            tmp.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self._pending_file())
        finally:
            tmp.unlink(missing_ok=True)

    def _pending(self) -> dict[str, dict]:
        try:
            raw = json.loads(self._pending_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _prune(self, items: list[Snapshot]) -> None:
        """只保留最近 `keep` 条（更老的 blob 一起删掉，避免无限增长）。"""
        over = items[:-self.keep] if len(items) > self.keep else []
        for old in over:
            (self.root / old.blob).unlink(missing_ok=True)
        if over:
            del items[:len(over)]

    # ── 撤销 ──────────────────────────────────────────────
    def latest(self) -> Snapshot | None:
        """最近一条**可撤销**的快照。"""
        with self._index_lock:
            for snapshot in reversed(self.list()):
                if snapshot.undoable:
                    return snapshot
        return None

    def undo(self, snapshot_id: str = "") -> tuple[bool, str]:
        """撤销一条快照 → `(成功?, 说明)`。

        ⚠ stale 判据：当前文件指纹必须等于**提交回执**里的 `after_hash`。
        不一致 → **拒绝**（不覆盖用户改动）。
        """
        with file_lock(self._index_file()), self._index_lock:
            items = self.list()
            snapshot = self._pick(items, snapshot_id)
            if snapshot is None:
                # 没有可撤销的，但可能有"已提交、登记失败"的：如实说出来
                broken = next((s for s in reversed(items) if s.pending_repair), None)
                if broken is not None:
                    return False, ("这条动作已提交但撤销记录待修复（写入时的登记失败），"
                                   "无法安全撤销")
                return False, "没有可撤销的 AI 写入"
            return self._apply_undo(items, snapshot)

    def _pick(self, items: list[Snapshot], snapshot_id: str) -> Snapshot | None:
        if snapshot_id:
            return next((s for s in items if s.snapshot_id == snapshot_id), None)
        return next((s for s in reversed(items) if s.undoable), None)

    def _apply_undo(self, items: list[Snapshot], snapshot: Snapshot) -> tuple[bool, str]:
        if snapshot.undone_at:
            return False, "这条动作已经撤销过了"
        if snapshot.pending_repair:
            return False, "这条动作已提交但撤销记录待修复（写入时的登记失败），无法安全撤销"
        if not snapshot.after_hash:
            return False, "这条动作没有完成记录（写后指纹缺失），无法安全撤销"
        if not snapshot.written:
            return False, "这条动作没有改变文件，无需撤销"
        restored, detail = self._restore_committed_snapshot(snapshot)
        if not restored:
            return False, detail
        snapshot.undone_at = _now()
        self._write_index(items)
        return True, f"已撤销：{snapshot.label or snapshot.operation or snapshot.target}"

    def _restore_committed_snapshot(self, snapshot: Snapshot) -> tuple[bool, str]:
        if not snapshot.operation_id:
            return False, "此快照没有可核对的提交回执，无法安全撤销"
        path = self.data_dir / snapshot.target
        # **持同一把目标锁**（审计 2026-11-21 P0）：校验与写回必须互斥，
        # 否则"校验通过 → 别人写入 → 我把旧快照盖上去"照样会抹掉合法改动。
        with file_lock(path):
            current = file_hash(path)
            if current != snapshot.after_hash:
                logger.warning("撤销被拒（stale）：%s 当前 %s ≠ 记录 %s",
                               snapshot.target, current[:12], snapshot.after_hash[:12])
                return False, ("文件在 AI 写入之后又被改过（指纹不一致），为免覆盖你的改动，"
                               "本次撤销已取消")
            blob = self.root / snapshot.blob
            try:
                payload = blob.read_bytes()
            except OSError:
                return False, "快照内容读不到了，无法撤销"
            if hashlib.sha256(payload).hexdigest() != snapshot.before_hash:
                return False, "快照内容指纹不匹配，无法撤销"
            if not self._restore(path, payload):
                return False, "写回快照失败（磁盘错误）"
        return True, ""

    # ⚠ 位置故意靠后：`list` 在类体里遮蔽内建 `list`；没有延迟注解时（3.12/3.13），
    # 排在 `list[Snapshot]` 注解之前会让导入当场的 `function[...]` 抛 TypeError。
    def list(self) -> list[Snapshot]:
        with self._index_lock:
            try:
                raw = json.loads(self._index_file().read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return []
            if not isinstance(raw, list):
                return []
            items = [Snapshot.from_dict(item) for item in raw if isinstance(item, dict)]
        pending = self._pending()
        for item in items:
            mark = pending.get(item.snapshot_id)
            if mark is None:
                continue
            item.pending_repair = True
            item.after_hash = str(mark.get("after_hash") or item.after_hash)
            item.operation_id = str(mark.get("operation_id") or item.operation_id)
        return items

    @staticmethod
    def _restore(path: Path, payload: bytes) -> bool:
        """原子写回（`tmp` + `os.replace`）。"""
        tmp = path.with_name(path.name + ".undo.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(payload)
            os.replace(tmp, path)
            return True
        except OSError:
            logger.error("撤销写回失败：%s", path, exc_info=True)
            return False
        finally:
            tmp.unlink(missing_ok=True)
