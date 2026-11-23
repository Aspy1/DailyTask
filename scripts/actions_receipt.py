"""写入层的**提交回执**（从 `actions_core.py` 拆出：那里已超过 800 行上限，Q-A1）。

审计 2026-11-21 P0：撤销原来是在命令执行完之后**再读盘**取写后指纹 ——
中间若有另一个写者（用户 / 另一个 CLI / 另一个学期作业），读到的是**别人**的版本，
撤销于是把后来的合法写入抹掉。回执必须在**目标文件锁内**产生，撤销以它为准。

回执按**线程**分开存：AI 工作线程与主线程/委派执行各自写各自的文件，
共用一个槽位会让一方拿到另一方的回执（撤销恢复到错误的目标上）。
"""

import hashlib
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from src.models.base import fingerprint

_RECEIPTS = threading.local()
RECEIPT_FLAG = "--commit-receipt"


class CommandOutput(str):
    receipt: dict | None

    def __new__(cls, text: str, receipt: dict | None = None) -> "CommandOutput":
        result = super().__new__(cls, text)
        result.receipt = receipt
        return result


def pack(output: str) -> str:
    receipts = list(_receipt_map().values())
    return json.dumps({
        "output": output,
        "receipt": receipts[0] if len(receipts) == 1 and output.startswith("OK ") else None,
    }, ensure_ascii=False)


def unpack(response: str) -> CommandOutput:
    if response.startswith("{"):
        payload = json.loads(response)
        if isinstance(payload, dict) and isinstance(payload.get("output"), str):
            receipt = payload.get("receipt")
            return CommandOutput(payload["output"], receipt if isinstance(receipt, dict) else None)
        raise ValueError("Invalid commit receipt")
    return CommandOutput(response)


def reset() -> None:
    _receipt_map().clear()


def _receipt_map() -> dict[tuple[str, str], dict]:
    """当前线程的回执表（`threading.local` 里懒建）。"""
    if not hasattr(_RECEIPTS, "items"):
        _RECEIPTS.items = {}
    return _RECEIPTS.items


def file_hash(path: Path) -> str:
    """磁盘原文的 sha256；缺失/读不出来 → 空串。"""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def new_operation_id() -> str:
    return uuid.uuid4().hex[:12]


def record(data_dir: str | Path, name, path: Path, payload: dict, before_doc: dict,
           before_sha: str, operation_id: str, operation: str = "") -> None:
    """落一份**提交回执**（操作 ID / 目标 / 前后指纹 / 版本 / 变更字段）。

    调用方必须在 `file_lock` **内**调它：写后指纹一旦出锁就可能属于另一个写者。
    """
    _receipt_map()[(str(data_dir), name)] = {
        "operation_id": operation_id,
        "operation": operation or str(name),
        "target": str(path),
        "name": str(name),
        "before_sha": before_sha,
        "after_sha": file_hash(path),
        "version": int(payload.get("_version") or 0),
        "changed_fields": sorted(_changed_fields(before_doc, payload)),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def last(data_dir: str | Path, name: str) -> dict | None:
    """本线程最近一次写这个文件留下的回执（没有则 None）。"""
    return _receipt_map().get((str(data_dir), name))


def clear(data_dir: str | Path, name: str) -> None:
    """丢掉回执：内容已被**整份替换**（如 `restore`），留着会误导撤销。"""
    _receipt_map().pop((str(data_dir), name), None)


def _changed_fields(before_doc: dict, after_doc: dict) -> set[str]:
    """顶层字段的增删改（不递归 —— 回执要的是"改了哪几块"，不是逐字段 diff）。"""
    keys = (set(before_doc) | set(after_doc)) - {"_version"}
    return {key for key in keys
            if fingerprint({"v": before_doc.get(key)}) != fingerprint({"v": after_doc.get(key)})}
