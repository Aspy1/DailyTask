"""方案 C 原型的功能验收（`MD-files/PERFORMANCE_WORKFLOW.md` §3.3）。

原型只回答"值不值得实装"，所以这里守的是**正确性**而不是性能：

1. 按学期隔离（跨学期不串号）；
2. 未完成筛选；
3. **分页不重不漏**（稳定排序键）；
4. 单条完成幂等；
5. 批量导入幂等（重复导入不重复插入）；
6. 版本化 schema（更高版本拒绝打开）；
7. 在线备份可恢复；
8. 查询计划真的走索引。

性能对照见 `scripts/perf_sqlite_bench.py` 与报告。
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing

import pytest

from src.services import task_store_sqlite as store


def _tasks(n: int, *, semester_prefix: str = "") -> list[dict]:
    return [{"id": f"{semester_prefix}t_{i:04d}", "title": f"作业 {i}",
             "course_name": f"课程 {i % 5}", "due_date": f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}T23:59:00",
             "status": "completed" if i % 4 == 0 else "pending",
             "tags": ["标签"], "notes": "", "attachments": [],
             "created_at": "2026-01-01T00:00:00", "reminded": False}
            for i in range(n)]


@pytest.fixture
def db(tmp_path) -> Iterator[object]:
    connection = store.connect(tmp_path / "tasks.db")
    yield connection
    connection.close()


def test_import_and_list_round_trip(db) -> None:
    tasks = _tasks(50)
    assert store.import_tasks(db, "sem_001", tasks) == 50

    got = store.list_tasks(db, "sem_001")

    assert len(got) == 50
    assert {t["id"] for t in got} == {t["id"] for t in tasks}


def test_semesters_are_isolated(db) -> None:
    """⭐ 身份关联：`semester_id` + `task_id` 是主键，跨学期不串号。"""
    store.import_tasks(db, "sem_001", _tasks(10, semester_prefix="a"))
    store.import_tasks(db, "sem_002", _tasks(5, semester_prefix="b"))

    assert len(store.list_tasks(db, "sem_001")) == 10
    assert len(store.list_tasks(db, "sem_002")) == 5


def test_pending_filter(db) -> None:
    store.import_tasks(db, "sem_001", _tasks(40))

    pending = store.pending_tasks(db, "sem_001")

    assert pending and all(t["status"] == "pending" for t in pending)
    assert len(pending) == len([t for t in _tasks(40) if t["status"] == "pending"])


def test_pagination_is_complete_and_unique(db) -> None:
    """⭐ 分页不重不漏（稳定排序键是唯一 tie-breaker）。"""
    store.import_tasks(db, "sem_001", _tasks(100))

    seen: list[str] = []
    for offset in range(0, 100, 7):
        seen.extend(t["id"] for t in store.page_tasks(db, "sem_001",
                                                      offset=offset, limit=7))

    assert len(seen) == len(set(seen)), "跨页出现了重复项"
    assert set(seen) == {t["id"] for t in _tasks(100)}, "漏了条目"


def test_complete_is_idempotent(db) -> None:
    store.import_tasks(db, "sem_001", _tasks(5))

    assert store.complete_task(db, "sem_001", "t_0001", "2026-03-01T10:00:00") is True
    assert store.complete_task(db, "sem_001", "t_0001", "2026-03-02T10:00:00") is False

    task = next(t for t in store.list_tasks(db, "sem_001") if t["id"] == "t_0001")
    assert task["status"] == "completed"
    assert task["completed_at"] == "2026-03-01T10:00:00", "幂等：不再改第二次的时间"


def test_reimport_does_not_duplicate(db) -> None:
    """批量导入幂等（UPSERT）：重复导入同一批不产生重复行。"""
    tasks = _tasks(20)
    store.import_tasks(db, "sem_001", tasks)
    store.import_tasks(db, "sem_001", tasks)

    assert store.counts(db)["total"] == 20


def test_reimport_updates_in_place(db) -> None:
    store.import_tasks(db, "sem_001", _tasks(3))
    changed = _tasks(3)
    changed[0]["title"] = "改过的标题"
    store.import_tasks(db, "sem_001", changed)

    got = next(t for t in store.list_tasks(db, "sem_001") if t["id"] == "t_0000")

    assert got["title"] == "改过的标题"
    assert store.counts(db)["total"] == 3


def test_future_schema_is_refused(sandbox) -> None:
    """更高版本 → 拒绝打开（不猜结构，也不静默降级写入）。"""
    path = sandbox / "future.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(f"PRAGMA user_version={store.SCHEMA_VERSION + 5}")
    before = path.read_bytes()

    with pytest.raises(RuntimeError, match="拒绝打开"):
        store.connect(path)
    assert path.read_bytes() == before


def test_query_plan_uses_the_index(db) -> None:
    """常用查询必须走索引（手册 §3.3-2：检查查询计划）。"""
    plan = store.query_plan(
        db,
        "SELECT * FROM tasks WHERE semester_id = ? AND status = 'pending' "
        "ORDER BY due_date, task_id", ("sem_001",))

    text = " ".join(plan).lower()
    assert "idx_tasks_sem_status_due" in text or "using index" in text, plan


def test_online_backup_is_restorable(tmp_path, db) -> None:
    """⭐ 在线备份（Backup API）→ 副本可独立打开且内容一致。"""
    store.import_tasks(db, "sem_001", _tasks(30))
    target = tmp_path / "backup.db"

    store.backup_to(db, target)
    restored = store.connect(target)
    try:
        assert store.counts(restored)["total"] == 30
        assert len(store.list_tasks(restored, "sem_001")) == 30
    finally:
        restored.close()


def test_transaction_rolls_back_on_failure(db) -> None:
    """一个事务里中途失败 → 整体回滚（不留半截写入）。"""
    store.import_tasks(db, "sem_001", _tasks(3))

    with pytest.raises(ValueError), store.transaction(db) as tx:
        tx.execute("UPDATE tasks SET title = '脏写' WHERE task_id = 't_0000'")
        raise ValueError("模拟中途失败")

    got = next(t for t in store.list_tasks(db, "sem_001") if t["id"] == "t_0000")
    assert got["title"] == "作业 0"


def test_json_payload_is_preserved(db) -> None:
    """`tags` / `attachments` 是 JSON 列，读回来要还原成容器（不能变成字符串）。"""
    store.import_tasks(db, "sem_001", [
        {"id": "t_x", "title": "带附件", "tags": ["a", "b"],
         "attachments": [{"name": "x.pdf", "stored_name": "h-x.pdf"}],
         "due_date": "2026-05-01T00:00:00"}])

    task = store.list_tasks(db, "sem_001")[0]

    assert task["tags"] == ["a", "b"]
    assert task["attachments"][0]["stored_name"] == "h-x.pdf"
    assert json.dumps(task, ensure_ascii=False)   # 可序列化回 JSON
