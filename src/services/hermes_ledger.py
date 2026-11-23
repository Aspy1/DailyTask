"""Hermes 定时提醒的**投递账本**（三态：待投递 / 已接受 / 结果不确定）。

审计 2026-11-21 P2 的原状：脚本**先写去重账本，再由 Hermes 投递**。
两者之间失败（网关离线 / 微信故障）时，账本已经记成"发过了" →
当天那条提醒永远不再来，而且没有任何地方能看出漏发了。

现在的口径：

- 产出消息 = 记一行 `pending`（**还没送出去**）；
- 投递端确认成功 → `delivered`（按 Hermes 执行 ID 核对）；
- 一直没确认、且行已过期 = `uncertain`（**不自动重试** —— 我们的消息没有
  幂等键，重发等于重复提醒；改为记警告，提示人工核对）。

老账本没有 `state` 列：一律按 `delivered` 读，升级后不重放历史提醒。

⚠ 本模块的 SQL 只有一张写死的表名（`TABLE` 常量），所有值都走参数绑定 ——
ruff S608 在这里是误报，逐处标注理由而不是整目录豁免。
"""

# ruff: noqa: S608

import logging
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

PENDING = "pending"
DELIVERED = "delivered"
UNCERTAIN = "uncertain"

TABLE = "emitted"


def _connect(ledger: Path) -> sqlite3.Connection:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ledger)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                f"CREATE TABLE IF NOT EXISTS {TABLE} ("
                "namespace TEXT, key TEXT, expiry TEXT, state TEXT, produced_at TEXT, "
                "execution_id TEXT, PRIMARY KEY(namespace, key))")
            columns = {row[1] for row in db.execute(f"PRAGMA table_info({TABLE})")}
            for column in ("state", "produced_at", "execution_id"):
                if column not in columns:
                    db.execute(f"ALTER TABLE {TABLE} ADD COLUMN {column} TEXT")
    except sqlite3.Error:
        db.close()
        raise
    return db


def _expire(db: sqlite3.Connection, today: str) -> None:
    """过期行先定性：`pending` 过期 = 投递结果不确定（**不是**已发）。

    语义："说好在这个窗口内送出去，窗口过完了还没收到确认" → 不确定。
    """
    db.execute(
        f"UPDATE {TABLE} SET state = ? "
        "WHERE expiry <= ? AND state = ?",
        (UNCERTAIN, today, PENDING))
    db.execute(f"UPDATE {TABLE} SET state = ? WHERE state IS NULL", (DELIVERED,))


def warn_uncertain(db: sqlite3.Connection) -> None:
    """结果不确定的行要点名报出来 —— 否则漏发只能靠用户自己发现。"""
    rows = list(db.execute(
        f"SELECT namespace, key FROM {TABLE} WHERE state = ?", (UNCERTAIN,)))
    if rows:
        detail = "、".join(f"{ns}/{key}" for ns, key in rows[:10])
        logger.warning("有 %d 条提醒投递结果不确定（%s）—— 请人工核对；"
                       "本脚本没有幂等键，不会自动重试", len(rows), detail)


def begin(db: sqlite3.Connection, today: date, scheduler: tuple[Path, str] | None = None) -> str | None:
    """显式事务开始：先定性过期行（`pending` 过期 = 结果不确定）。"""
    db.execute("BEGIN IMMEDIATE")
    execution = _reconcile(db, *scheduler) if scheduler else None
    _expire(db, today.isoformat())
    return execution


def emit_keys(db: sqlite3.Connection, namespace: str, keys: set[str],
              now: datetime, days: int = 1, execution: str | None = None) -> None:
    """Record the pending keys and the scheduler execution that owns them."""
    expiry = (now.date() + timedelta(days=days)).isoformat()
    db.executemany(
        f"INSERT OR IGNORE INTO {TABLE} (namespace, key, expiry, state, produced_at, execution_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ((namespace, key, expiry, PENDING, now.isoformat(timespec="seconds"), execution) for key in keys))


def open_ledger(ledger: Path) -> sqlite3.Connection:
    return _connect(ledger)


def _reconcile(db: sqlite3.Connection, path: Path, job_id: str) -> str | None:
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as source:
            executions = _read_executions(db, source, job_id)
            running = source.execute(
                "SELECT id FROM executions WHERE job_id = ? AND status = 'running' LIMIT 2",
                (job_id,)).fetchall()
    except sqlite3.Error:
        logger.warning("Unable to read Hermes delivery results", exc_info=True)
        return None
    for execution, state in executions:
        db.execute(f"UPDATE {TABLE} SET state = ? WHERE execution_id = ? AND state IN (?, ?)",
                   (state, execution, PENDING, UNCERTAIN))
    return running[0][0] if len(running) == 1 else None


def _read_executions(db: sqlite3.Connection, source: sqlite3.Connection, job_id: str) -> list:
    results = []
    outstanding = db.execute(f"SELECT DISTINCT execution_id FROM {TABLE} WHERE state IN (?, ?) "
                             "AND execution_id IS NOT NULL", (PENDING, UNCERTAIN))
    for execution, in outstanding:
        result = source.execute("SELECT status, delivery_outcome FROM executions "
                                "WHERE id = ? AND job_id = ?", (execution, job_id)).fetchone()
        if not result:
            continue
        status, outcome = result
        if status == "completed" and outcome == "delivered":
            results.append((execution, DELIVERED))
        elif status in ("failed", "cancelled") or outcome in ("failed", "not_configured", "suppressed"):
            results.append((execution, UNCERTAIN))
    return results


def done_keys(db: sqlite3.Connection, namespace: str) -> set[str]:
    """该命名空间里**已经登记过**的键 —— 判重口径。

    包含 `pending`：同一窗口内**不重发**（这一轮已经产出过了）。
    投递失败由 `pending → uncertain` 暴露，而不是靠重发掩盖。
    """
    return {key for key, in db.execute(
        f"SELECT key FROM {TABLE} WHERE namespace = ?", (namespace,))}


def ledger_states(ledger: Path) -> dict[str, int]:
    """账本现状 → `{pending, delivered, uncertain}`（排查/测试用）。"""
    counts = {PENDING: 0, DELIVERED: 0, UNCERTAIN: 0}
    with closing(_connect(ledger)) as db:
        for state, count in db.execute(
                f"SELECT state, COUNT(*) FROM {TABLE} GROUP BY state"):
            key = DELIVERED if state is None else str(state)
            counts[key] = counts.get(key, 0) + int(count)
    return counts


def delivery_diagnostics(ledger: Path, gateway_home: Path | None = None) -> dict:
    """两个**独立**诊断口径（审计原文）：本机进程存活 ≠ 微信投递可用。

    进程由本机状态探针判断。历史确认记录只表示曾有成功投递。
    """
    from src.services.hermes_gateway import gateway_online

    states = ledger_states(ledger)
    return {
        "process_alive": gateway_online(gateway_home),
        "delivery_available": None,
        "states": states,
    }
