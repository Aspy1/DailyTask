"""动作级快照与撤销（H3/P0）：能撤回，且**不会**覆盖用户后来的改动（stale 拒绝）。

场景（论文 P3「checkpoint ≠ verification」用在这里同理）：快照只说明"当时是什么样"，
撤销前必须**证明**文件还是 AI 写完时的那个状态 —— 否则就是把用户手改的内容一起抹掉。
"""

import json
import threading
from pathlib import Path

import pytest

from src.services import ai_undo


def _seed(path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _store(sandbox) -> ai_undo.SnapshotStore:
    store = ai_undo.SnapshotStore.for_data_dir(sandbox)
    assert store is not None
    return store


def test_annotations_are_deferred_for_eager_python() -> None:
    """⭐ 回归：`SnapshotStore.list` 会遮蔽内建 `list`。

    Python 3.12/3.13（以及部分 3.14 构建）在类体里**立即求值**后续注解，
    于是 `_write_index(self, items: list[Snapshot])` 里的 `list` 变成同名方法，
    导入 `ai_undo` 直接 `TypeError: 'function' object is not subscriptable`。
    `from __future__ import annotations` 让注解延迟求值，规避所有此类遮蔽。
    """
    source = Path(ai_undo.__file__).read_text(encoding="utf-8")
    head = "\n".join(source.splitlines()[:40])
    assert "from __future__ import annotations" in head


def test_capture_then_undo_restores_the_before_state(sandbox) -> None:
    """⭐ 写前快照 → 写 → 撤销 → 内容回到写前（动作级，不是整份备份）。"""
    target = sandbox / "inventory.json"
    _seed(target, {"_version": 1, "items": [{"id": "i_001", "name": "抽纸", "quantity": 2}]})
    store = _store(sandbox)

    snapshot = store.capture('python scripts/actions.py add_item --name "牙膏"',
                             operation="add_item", request_id="req1", label="牙膏")
    assert snapshot is not None and snapshot.before_hash == ai_undo.file_hash(target)

    # 模拟 actions.py 写入
    _seed(target, {"_version": 1, "items": [{"id": "i_001", "name": "抽纸", "quantity": 2},
                                           {"id": "i_002", "name": "牙膏", "quantity": 1}]})
    store.finalize(snapshot)
    assert snapshot.after_hash and snapshot.after_hash != snapshot.before_hash

    ok, detail = store.undo()
    assert ok, detail
    restored = json.loads(target.read_text(encoding="utf-8"))
    assert [item["name"] for item in restored["items"]] == ["抽纸"]


def test_undo_refuses_when_the_file_changed_after_the_write(sandbox) -> None:
    """⭐ stale：AI 写完之后文件又被改过 → 撤销必须**拒绝**（否则覆盖用户改动）。"""
    target = sandbox / "inventory.json"
    _seed(target, {"_version": 1, "items": []})
    store = _store(sandbox)

    snapshot = store.capture('python scripts/actions.py add_item --name "牙膏"',
                             operation="add_item")
    _seed(target, {"_version": 1, "items": [{"id": "i_001", "name": "牙膏"}]})
    store.finalize(snapshot)

    # 用户/CLI 之后又改了同一个文件
    _seed(target, {"_version": 1, "items": [{"id": "i_001", "name": "牙膏"},
                                           {"id": "i_002", "name": "我手动加的"}]})
    ok, detail = store.undo()
    assert ok is False and "改过" in detail
    assert "我手动加的" in target.read_text(encoding="utf-8"), "stale 时一个字节都不能动"


def test_undo_twice_is_refused(sandbox) -> None:
    target = sandbox / "inventory.json"
    _seed(target, {"_version": 1, "items": []})
    store = _store(sandbox)
    snapshot = store.capture('python scripts/actions.py add_item --name "牙膏"',
                             operation="add_item")
    _seed(target, {"_version": 1, "items": [{"id": "i_001"}]})
    store.finalize(snapshot)

    assert store.undo()[0] is True
    ok, detail = store.undo()
    assert ok is False and "没有可撤销" in detail


def test_no_snapshot_when_the_target_file_does_not_exist(sandbox) -> None:
    """动作前文件不存在（本次是新建）→ 不留快照：撤销等于"删文件"，风险高于收益。"""
    store = _store(sandbox)
    assert store.capture('python scripts/actions.py add_item --name "牙膏"',
                         operation="add_item") is None
    assert store.latest() is None


def test_unfinished_snapshot_is_not_undoable(sandbox) -> None:
    """写后指纹缺失（执行中途异常）→ 不许撤销，因为无法判断有没有被改过。"""
    target = sandbox / "inventory.json"
    _seed(target, {"_version": 1, "items": []})
    store = _store(sandbox)
    snapshot = store.capture('python scripts/actions.py add_item --name "x"',
                             operation="add_item")
    ok, detail = store.undo(snapshot.snapshot_id)
    assert ok is False and "没有完成记录" in detail


def test_noop_snapshot_is_not_undoable(sandbox) -> None:
    """⭐ 命令回 OK 但没改文件 → 不能亮"撤销"按钮，也不能报"已撤销"。"""
    target = sandbox / "inventory.json"
    _seed(target, {"_version": 1, "items": [{"id": "i_001"}]})
    store = _store(sandbox)
    snapshot = store.capture('python scripts/actions.py add_item --name "x"',
                             operation="add_item")
    store.finalize(snapshot)                       # 文件没变 → after_hash == before_hash
    assert snapshot is not None and snapshot.written is False
    assert store.latest() is None
    ok, detail = store.undo()
    assert ok is False and "没有可撤销" in detail
    ok, detail = store.undo(snapshot.snapshot_id)
    assert ok is False and "没有改变文件" in detail


def test_index_survives_concurrent_capture_and_finalize(sandbox) -> None:
    """⭐ worker 线程 capture/finalize 与主线程 undo 共用 index：并发写不能丢/坏。"""
    target = sandbox / "inventory.json"
    _seed(target, {"_version": 1, "items": []})
    store = _store(sandbox)
    barrier = threading.Barrier(6)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            for _ in range(5):
                snapshot = store.capture(
                    'python scripts/actions.py add_item --name "x"',
                    operation="add_item")
                store.finalize(snapshot)
        except BaseException as error:  # noqa: BLE001 — 线程里的异常要带回主线程断言
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    items = store.list()
    assert len(items) == 30
    assert all(item.snapshot_id for item in items)
    assert not list(store.root.glob("index.json.*.tmp")), "临时文件必须清理"


def test_keep_limit_prunes_old_snapshots(sandbox) -> None:
    target = sandbox / "inventory.json"
    _seed(target, {"_version": 1, "items": []})
    store = ai_undo.SnapshotStore(sandbox / ai_undo.DIR_NAME, keep=2)
    for index in range(4):
        snap = store.capture(f'python scripts/actions.py update_item --id i_{index}',
                             operation="update_item")
        _seed(target, {"_version": 1, "items": [{"n": index}]})
        store.finalize(snap)
    assert len(store.list()) == 2


@pytest.mark.parametrize("operation", [
    "add_item", "add_task", "add_expense", "add_habit", "add_plan",
    "complete_plan", "replace_plans", "log_study",
])
def test_every_write_operation_has_a_target_file(operation: str) -> None:
    """撤销要能找到"该还原哪个文件"；新增写命令必须登记（否则永远撤不了）。"""
    from src.services import ai_policy

    writes = [op for op, level in ai_policy.OP_LEVEL.items()
              if level in (ai_policy.LOW_WRITE, ai_policy.HIGH_WRITE)]
    missing = sorted(set(writes) - set(ai_undo.TARGET_FILES))
    assert not missing, f"这些写命令没有登记目标文件：{missing}"
    assert operation in ai_undo.TARGET_FILES


def test_semester_files_resolve_read_only(sandbox) -> None:
    """按学期分文件的命令（add_task → tasks.json）也要能定位，且**不创建**默认学期。"""
    from src.models import semester_paths

    path = ai_undo.target_path("add_task", sandbox)
    assert path is not None
    assert path.name == "tasks.json" and semester_paths.SEMESTER_DIR in path.parts
    assert not semester_paths.registry_path(sandbox).exists(), "只读解析不该写注册表"


def test_unknown_operation_has_no_target() -> None:
    assert ai_undo.target_path("restore", None) is None
    assert ai_undo.target_path("no_such", None) is None
