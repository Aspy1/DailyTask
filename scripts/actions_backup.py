"""写入前的自动备份与轮转（从 `actions_core.py` 拆出，那里逼近 800 行上限）。

目录选 `data/backup/`：它在 `.gitignore` 里（不会被 GitSync 推到 GitHub），
而 `data/*.json` 本身有 git 历史兜底 —— 两者互补。

**归属清单（审计 2026-11-21 P0）**：备份文件名里只有 `<文件名>.<时间戳>`，
按学期的三个文件（courses/tasks/exams）在 A、B 两个学期下**同名** ——
于是切到 B 之后 `restore --name tasks.json` 会命中 A 的快照，命令回 OK，
B 的作业被替换成 A 的。清单为每份备份记下归属与内容指纹，恢复时据此校验。

⚠ `DATA` **必须每次现算**（延迟 import `actions_core` 取它的当前值）：测试的
`sandbox` fixture 会替换 `actions_core.DATA`，固化过一次的代价是备份写进用户真实
`data/`（2026-10-16 实测发生过）。
"""

import configparser
import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from src.models import semester_paths

logger = logging.getLogger(__name__)

DEFAULT_MAX_BACKUPS = 10
INDEX_NAME = "index.json"


def _backup_dir() -> Path:
    """备份目录（每次现算，见模块说明）。"""
    import scripts.actions_core as core

    return core.DATA / "backup" / "actions"


def _max_backups() -> int:
    """保留份数：读设置里的 `Backup.max_backups`（该键此前存在但无人使用）。

    用 configparser **只读**打开 settings.ini：绝不能为了读一个数字而让
    SettingsManager 去补默认值 / 回写这个含密钥的文件。
    """
    import scripts.actions_core as core

    try:
        parser = configparser.ConfigParser()
        parser.read(core.DATA / "settings.ini", encoding="utf-8")
        return max(1, min(int(parser.get("Backup", "max_backups", fallback="10")), 100))
    except (OSError, ValueError, configparser.Error):
        return DEFAULT_MAX_BACKUPS


# ── 归属清单 ────────────────────────────────────────────────


def _index_file() -> Path:
    return _backup_dir() / INDEX_NAME


def read_index() -> list[dict]:
    """读清单；缺失 / 损坏 → 空列表（旧版本留下的裸备份 = **来源未知**）。"""
    try:
        raw = json.loads(_index_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = raw.get("entries") if isinstance(raw, dict) else raw
    return [e for e in items or [] if isinstance(e, dict) and e.get("file")]


def _write_index(entries: list[dict]) -> None:
    folder = _backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"_version": 1, "entries": entries}
    tmp = _index_file().with_name(f"{INDEX_NAME}.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8", newline="")
        os.replace(tmp, _index_file())
    finally:
        tmp.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semester_for_path(path: Path) -> str:
    """Derive ownership from the resolved target, independent of the active pointer."""
    if not semester_paths.is_per_semester(path.name):
        return ""
    import scripts.actions_core as core

    root = (core.DATA / semester_paths.SEMESTER_DIR).resolve()
    parts = path.resolve().relative_to(root).parts
    if len(parts) != 2:
        raise ValueError("Invalid backup target")
    return parts[0]


def _next_seq(entries: list[dict]) -> int:
    """单调序号 —— **不能靠文件名排序**：同秒的 `-10` 会排在 `-2` 前面。"""
    return max((int(e.get("seq") or 0) for e in entries), default=0) + 1


def _target_of(path: Path, data_dir: Path) -> str:
    """相对数据目录的 posix 路径（可读、可审计、不存盘符）。"""
    try:
        return path.relative_to(data_dir).as_posix()
    except ValueError:
        return path.name


def _entry_for(dest: Path, source: Path, sequence: int) -> dict:
    """一份备份的**归属 + 内容**记录（恢复时据此校验，不靠文件名猜）。"""
    import scripts.actions_core as core

    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        payload = None
    version = payload.get("_version") if isinstance(payload, dict) else None
    return {
        "backup_id": f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{sequence}",
        "file": dest.name,
        "name": source.name,
        "target": _target_of(source, core.DATA),
        "semester_id": semester_for_path(source),
        # 备份**自己声明的**版本；与 `core._schema_version` 比，不一致就是迁移不匹配
        "schema_version": version if type(version) is int else 0,
        "supported_version": int(core._schema_version(source.name)),
        "sha256": _sha256(dest),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "seq": sequence,
    }


def _prune(entry: dict, entries: list[dict]) -> tuple[list[dict], set[str]]:
    """按**序号**轮转同名备份：只留最近 `max_backups` 份（清单项与文件一起删）。"""
    same = sorted((e for e in entries if (e.get("name"), e.get("semester_id")) ==
                   (entry["name"], entry["semester_id"])),
                  key=lambda e: int(e.get("seq") or 0))
    dropped = {str(e.get("file")) for e in same[:-_max_backups()]}
    return [e for e in entries if str(e.get("file")) not in dropped], dropped


def _backup_file(p: Path) -> Path | None:
    """把 `p` 的**当前内容**存一份到备份目录，并按份数上限轮转。"""
    from src.models.base import file_lock

    with file_lock(_index_file()):
        return _backup_under_lock(p)


def _backup_under_lock(p: Path) -> Path | None:
    if not p.exists():
        return None
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{p.name}.{stamp}.json"
    n = 2
    while dest.exists():                      # 同一秒内多次写入也不互相覆盖
        dest = backup_dir / f"{p.name}.{stamp}-{n}.json"
        n += 1
    shutil.copy2(p, dest)
    entries = read_index()
    entry = _entry_for(dest, p, _next_seq(entries))
    entries.append(entry)
    retained, dropped = _prune(entry, entries)
    _write_index(retained)
    for name in dropped:
        try:
            (backup_dir / Path(name).name).unlink(missing_ok=True)
        except OSError:
            logger.warning("Unable to remove an expired backup", exc_info=True)
    return dest


# ── 恢复候选与归属 ──────────────────────────────────────────


def candidates(name: str, stamp: str = "") -> list[tuple[dict | None, Path]]:
    """`name` 的备份候选，**按序号从新到旧**（清单里没有的也列出，归属为 None）。

    ⚠ 不按文件名排序：同一秒内 `-2` / `-10` 的字典序会把 `-10` 排到 `-2` 前面，
    于是"最近一份"永远选错 —— 审计里"同秒备份排序"验收项。
    """
    folder = _backup_dir()
    files = sorted(folder.glob(f"{name}.*.json"))
    if stamp:
        files = [f for f in files if stamp in f.name]
    entries = {str(e.get("file")): e for e in read_index() if e.get("name") == name}
    ordered = sorted(files, key=lambda f: (_seq_of(entries.get(f.name)), f.name), reverse=True)
    return [(entries.get(f.name), f) for f in ordered]


def _seq_of(entry: dict | None) -> int:
    if entry is None:
        return -1
    return int(entry.get("seq") or 0)


def newest(name: str, stamp: str = "", semester: str = "") -> tuple[dict | None, Path] | None:
    items = candidates(name, stamp)
    if semester:
        matching = next((pair for pair in items if (pair[0] or {}).get("semester_id") == semester), None)
        if matching is not None:
            return matching
    return items[0] if items else None


def entry_for_file(path: Path) -> dict | None:
    return next((e for e in read_index() if e.get("file") == path.name), None)


def verify(name: str, entry: dict | None, source: Path, declared: str,
           current_semester: str) -> str:
    """恢复前校验一份备份 → **空串表示通过**，否则是给用户看的原因。

    审计 P0 的验收项都在这里：归属（学期）、迁移版本、内容指纹。
    归属**未知**（旧快照没有清单条目）时要求显式声明（`--semester`），不猜。
    """
    semester_scope = semester_paths.is_per_semester(name)
    if entry is None:
        if semester_scope and not declared:
            return (f"{source.name} 没有归属记录（旧快照），"
                    f"请用 --semester <学期id> 明确它是哪个学期的备份")
        entry = {"semester_id": declared, "sha256": ""}
    return (_owner_problem(name, entry, source, declared, current_semester)
            or _version_problem(source, entry)
            or _content_problem(source, entry))


def _owner_problem(name: str, entry: dict, source: Path, declared: str,
                   current_semester: str) -> str:
    """归属校验：按学期的文件**只能**恢复到同一个学期（共享文件不受限）。"""
    if not semester_paths.is_per_semester(name):
        return ""
    owner = str(entry.get("semester_id") or declared)
    if not owner:
        return f"{source.name} 的归属为空，请用 --semester 指定"
    if owner != current_semester:
        return (f"{source.name} 属于学期 {owner}，当前学期是 {current_semester} —— "
                f"跨学期恢复会覆盖另一学期的数据，已拒绝")
    if declared and declared != owner:
        return f"声明的学期 {declared} 与备份归属 {owner} 不一致，已拒绝"
    return ""


def _version_problem(source: Path, entry: dict) -> str:
    """迁移版本：备份比本程序支持的**新** → 拒绝（写回去等于静默降级）。"""
    supported = int(entry.get("supported_version") or 0)
    version = int(entry.get("schema_version") or 0)
    if supported and version > supported:
        return (f"{source.name} 的版本 v{version} 比本程序支持的 v{supported} 新"
                f"（迁移不匹配），拒绝用它覆盖")
    return ""


def _content_problem(source: Path, entry: dict) -> str:
    """内容指纹：清单里记的 sha256 与当前备份文件不一致 → 备份被改过 / 损坏。"""
    recorded = str(entry.get("sha256") or "")
    if recorded and _sha256(source) != recorded:
        return f"{source.name} 的内容与备份清单不一致（已被改动 / 损坏），已拒绝"
    return ""
