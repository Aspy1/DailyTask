"""作业存储的 **SQLite 原型**（方案 C，`MD-files/PERFORMANCE_WORKFLOW.md` §3.3）。

⚠ ruff S608 在本文件整体豁免：SQL 的拼接部分**只有**模块级常量 `LIST_ORDER`
与本文件写死的表名，一切外部值都走 `?` 参数绑定（见 `tests/test_task_store_sqlite.py`）。

**这是原型，不是已切换的权威存储。** 目标是把"方案是否值得实装"变成可测的问题：

- 用**同一份合成数据**，对比 JSON 与 SQLite 的四类常见操作：
  按学期列表、未完成筛选、分页、单条完成 / 批量导入；
- 保留**稳定身份**：`semester_id` + `task_id` 是主键的一部分，跨学期不串号；
- 版本化 schema（`PRAGMA user_version`）+ 必要索引 + 稳定排序键
  （分页必须带唯一 tie-breaker，否则跨页会重复或漏项）。

**刻意不做**的事（手册 §3.3 的边界）：

- 不接进 `TaskModel`、不改任何 UI / CLI 入口（原型独立，随时可丢）；
- 不把数据库文件当跨机器同步协议（同步仍走 JSON + git）；
- 附件实体仍留在文件系统，库里只存元数据。
"""

# ruff: noqa: S608

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

# 分页/列表的**稳定排序键**：`due_date` 可能大量重复（同一门课多份作业同天截止），
# 只按它排序时 SQLite 不保证跨页一致 → 必须补唯一 tie-breaker（task_id）。
#
# ⚠ 本模块所有 SQL 的拼接部分**只有**这个常量与本文件写死的表名；一切外部值都走
# `?` 参数绑定 —— ruff S608 在这里是误报（逐处标注理由，不整目录豁免）。
LIST_ORDER = "ORDER BY due_date ASC, task_id ASC"

TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    semester_id  TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    title        TEXT NOT NULL,
    course_name  TEXT NOT NULL DEFAULT '',
    due_date     TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    priority     TEXT NOT NULL DEFAULT 'medium',
    tags         TEXT NOT NULL DEFAULT '[]',   -- JSON 数组（查询不倒查 tags）
    notes        TEXT NOT NULL DEFAULT '',
    attachments  TEXT NOT NULL DEFAULT '[]',   -- 仅元数据，实体在文件系统
    created_at   TEXT NOT NULL DEFAULT '',
    completed_at TEXT,
    reminded     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (semester_id, task_id)
);
CREATE INDEX IF NOT EXISTS idx_tasks_sem_status_due
    ON tasks(semester_id, status, due_date, task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_sem_due
    ON tasks(semester_id, due_date, task_id);
"""


def connect(path: Path, *, wal: bool = True) -> sqlite3.Connection:
    """打开（并初始化）数据库。

    `wal=True` 走 WAL：写不阻塞读、崩溃后能恢复；代价是同机多进程时会有
    `-wal` / `-shm` 附属文件（手册要求验证这件事）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5.0)
    try:
        _initialize(db, wal)
    except BaseException:
        db.close()
        raise
    return db


def _initialize(db: sqlite3.Connection, wal: bool) -> None:
    """Reject future schema versions before changing the database."""
    current = db.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"数据库 schema v{current} 比本程序支持的 v{SCHEMA_VERSION} 新，拒绝打开")
    db.row_factory = sqlite3.Row
    if wal:
        db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(TASKS_DDL)
    if current < SCHEMA_VERSION:
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        db.commit()


@contextmanager
def transaction(db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """短事务：失败整体回滚（手册 §3.3-3「写事务尽量短」）。"""
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
    except Exception:
        db.rollback()
        raise
    else:
        db.commit()


def _row(task: dict, semester: str) -> tuple:
    """作业 → 一行（列顺序必须与 `INSERT_SQL` 一致）。"""
    return (
        semester, str(task.get("id") or ""), str(task.get("title") or ""),
        str(task.get("course_name") or ""), str(task.get("due_date") or ""),
        str(task.get("status") or "pending"), str(task.get("priority") or "medium"),
        _json(task, "tags"), str(task.get("notes") or ""),
        _json(task, "attachments"), str(task.get("created_at") or ""),
        task.get("completed_at"), 1 if task.get("reminded") else 0,
    )


def _json(task: dict, key: str) -> str:
    """把列表字段序列化成一列 JSON（附件只存元数据，实体在文件系统）。"""
    return json.dumps(task.get(key) or [], ensure_ascii=False)


INSERT_SQL = """
INSERT INTO tasks (semester_id, task_id, title, course_name, due_date, status,
                   priority, tags, notes, attachments, created_at, completed_at, reminded)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(semester_id, task_id) DO UPDATE SET
    title=excluded.title, course_name=excluded.course_name,
    due_date=excluded.due_date, status=excluded.status,
    priority=excluded.priority, tags=excluded.tags, notes=excluded.notes,
    attachments=excluded.attachments, completed_at=excluded.completed_at,
    reminded=excluded.reminded
"""


def import_tasks(db: sqlite3.Connection, semester: str, tasks: list[dict]) -> int:
    """批量导入（单事务 + 幂等 UPSERT：重复导入不会重复插入）。"""
    with transaction(db) as tx:
        tx.executemany(INSERT_SQL, (_row(t, semester) for t in tasks))
    return len(tasks)


def list_tasks(db: sqlite3.Connection, semester: str) -> list[dict]:
    """按学期取**全部**作业（排序稳定）。"""
    rows = db.execute(
        f"SELECT * FROM tasks WHERE semester_id = ? {LIST_ORDER}",
        (semester,))
    return [_to_task(row) for row in rows]


def pending_tasks(db: sqlite3.Connection, semester: str) -> list[dict]:
    """未完成筛选（走 `idx_tasks_sem_status_due`）。"""
    rows = db.execute(
        "SELECT * FROM tasks WHERE semester_id = ? AND status = 'pending' "
        f"{LIST_ORDER}", (semester,))
    return [_to_task(row) for row in rows]


def page_tasks(db: sqlite3.Connection, semester: str, *,
               offset: int, limit: int) -> list[dict]:
    """分页（带唯一 tie-breaker，跨页不重不漏）。"""
    rows = db.execute(
        f"SELECT * FROM tasks WHERE semester_id = ? {LIST_ORDER} LIMIT ? OFFSET ?",
        (semester, limit, offset))
    return [_to_task(row) for row in rows]


def complete_task(db: sqlite3.Connection, semester: str, task_id: str,
                  completed_at: str) -> bool:
    """单条完成（幂等：已完成再点一次不报错、也不改时间）。"""
    with transaction(db) as tx:
        cursor = tx.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ? "
            "WHERE semester_id = ? AND task_id = ? AND status = 'pending'",
            (completed_at, semester, task_id))
    return cursor.rowcount > 0


def counts(db: sqlite3.Connection) -> dict[str, int]:
    total = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    pending = db.execute(
        "SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]
    return {"total": int(total), "pending": int(pending)}


def query_plan(db: sqlite3.Connection, sql: str, params: tuple = ()) -> list[str]:
    """`EXPLAIN QUERY PLAN`（手册 §3.3-2：对常用 SQL 检查查询计划）。"""
    return [str(row[3]) for row in db.execute(f"EXPLAIN QUERY PLAN {sql}", params)]


def backup_to(db: sqlite3.Connection, target: Path) -> None:
    """**在线备份**（手册 §3.3-4：SQLite Backup API，运行中也能拿一致快照）。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as dest:
        db.backup(dest)


def _to_task(row: sqlite3.Row) -> dict:
    return {
        "id": row["task_id"], "title": row["title"], "course_name": row["course_name"],
        "due_date": row["due_date"], "status": row["status"],
        "priority": row["priority"], "tags": json.loads(row["tags"]),
        "notes": row["notes"], "attachments": json.loads(row["attachments"]),
        "created_at": row["created_at"], "completed_at": row["completed_at"],
        "reminded": bool(row["reminded"]),
    }
