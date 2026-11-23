"""备份 / 恢复命令（从 `actions.py` 拆出：那里已逼近 800 行上限，Q-A1）。

**归属校验（审计 2026-11-21 P0）**：按学期的文件在 A/B 两个学期下同名，
扁平备份池里分不清来源 —— 切到 B 之后恢复会命中 A 的快照并把 B 覆盖掉。
现在先解析**显式目标**，在目标锁内比对归属 / 版本 / 内容指纹，全部通过才提交。
"""

import hashlib
import json
import os

from scripts.actions_backup import (
    _backup_dir,
    _backup_file,
    _max_backups,
)
from scripts.actions_core import (
    _path,
    _schema_version,
    _text,
    _validate_payload,
    emit,
    forget_loaded,
)


def cmd_list_backups(args) -> None:
    from scripts.actions_backup import candidates, entry_for_file

    name = _text(getattr(args, "name", None), "name")
    found = _collect(name, _text(getattr(args, "stamp", None), "stamp"),
                     _text(getattr(args, "semester", None), "semester"),
                     candidates, entry_for_file)
    if not found:
        emit("NO_BACKUP" + (f" for {name}" if name else ""))
        return
    for entry, f in found[-20:]:
        owner = (entry or {}).get("semester_id") or "—"
        stamp_of = (entry or {}).get("created_at") or ""
        emit(f"  {f.name}  ({f.stat().st_size} 字节)  学期={owner}  {stamp_of}".rstrip())
    emit(f"共 {len(found)} 份（每个文件保留上限 {_max_backups()} 份）")


def _collect(name: str, stamp: str, semester: str, candidates, entry_for_file) -> list:
    """候选列表 + 过滤（**按顺序**：名称 → 时间戳 → 归属学期）。"""
    found = candidates(name, stamp) if name else _every_backup()
    if not semester:
        return found
    labelled = [(entry or entry_for_file(f), f) for entry, f in found]
    return [pair for pair in labelled if (pair[0] or {}).get("semester_id") == semester]


def _every_backup() -> list:
    """备份池里的全部文件（清单本身不在其中）。"""
    folder = _backup_dir()
    if not folder.is_dir():
        return []
    return [(None, f) for f in sorted(folder.glob("*.json")) if f.name != "index.json"]


def cmd_restore(args) -> None:
    """用备份覆盖当前文件。

    ⚠ **这是给用户的手动恢复入口**：必须显式 `--yes`；AI 不得自行调用
    （提示词里已写明）。恢复前会把"当前版本"再备份一次，避免恢复错方向。
    """
    from scripts import actions_backup as backups
    from src.models.base import file_lock

    name = _text(args.name, "name", required=True)
    if not getattr(args, "yes", False):
        emit("ERROR restore 需要显式 --yes（手动恢复入口，避免误覆盖）")
        return

    dest = _path(name)
    current = backups.semester_for_path(dest)
    picked = backups.newest(name, _text(getattr(args, "stamp", None), "stamp"), current)
    if picked is None:
        emit(f"ERROR 没有 {name} 的备份（先用 list_backups 查看）")
        return
    entry, src = picked
    try:
        raw = src.read_bytes()
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        emit(f"ERROR 备份本身损坏：{src.name}（{e}）")
        return
    _validate_payload(name, data)
    version = data.get("_version", 1)
    if type(version) is not int or not 1 <= version <= _schema_version(name):
        emit(f"ERROR {src.name} 的版本无效或不受支持")
        return

    declared = _text(getattr(args, "semester", None), "semester")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 恢复也是写入口 → 同一把文件锁（审查 2026-10-17 第三轮 #2）。
    # 校验也放在锁内：读到一半目标被切学期/改写的话，"校验通过"就没意义了。
    with file_lock(dest):
        reason = backups.verify(name, entry, src, declared, current)
        if entry and entry.get("sha256") and hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            reason = "备份内容与读入版本不一致"
        if reason:
            emit(f"ERROR {reason}")
            return
        _backup_file(dest)
        tmp = dest.with_name(dest.name + ".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
    forget_loaded(name)                 # 内容整份换了 → 丢掉旧基准
    emit(f"OK restore {name} ← {src.name}")
