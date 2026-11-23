"""P0-2：撤销必须绑定**实际提交版本**（审计 2026-11-21）。

复现的故障：目标从 0 经 AI 写成 1，另一写者再写成 2；`finalize` **事后再读盘**，
读到 2 并把它当成"AI 这一笔的写后指纹"。随后的撤销把 2 恢复成 0 ——
用户/AI 之后的合法写入被静默抹掉。

修复口径（审计原文）：写入层在**目标文件锁内**产生结构化回执（操作 ID、目标、
提交前后版本、变更字段）；撤销持同一目标锁，版本一致才恢复；调用方的延迟读盘
只用来显示验证结果。若写入成功而索引登记失败，返回「已提交，撤销记录待修复」。
"""

import json
import threading

import scripts.actions_core as core
from src.services import ai_undo


def _seed(path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _store(sandbox) -> ai_undo.SnapshotStore:
    store = ai_undo.SnapshotStore.for_data_dir(sandbox)
    assert store is not None
    return store


def _payload(name: str) -> dict:
    return {"_version": 1, "items": [{"id": "i_001", "name": name}]}


def test_receipt_records_the_bytes_that_were_actually_committed(sandbox) -> None:
    """写入层回执：目标、提交前后指纹、版本、操作 ID 都在锁内产生。"""
    target = sandbox / "inventory.json"
    _seed(target, _payload("零"))
    core.forget_loaded("inventory.json")

    core.save("inventory.json", _payload("一"))

    receipt = core.last_commit("inventory.json")
    assert receipt is not None
    assert receipt["target"] == str(target.resolve()) or receipt["target"].endswith("inventory.json")
    assert receipt["after_sha"] == ai_undo.file_hash(target)
    assert receipt["after_sha"] != receipt["before_sha"]
    assert int(receipt["version"]) >= 1 and receipt["operation_id"]


def test_hermes_cli_receipt_does_not_adopt_a_later_write(sandbox, monkeypatch) -> None:
    import uuid

    from scripts import hermes_actions as bridge

    monkeypatch.setenv("LIFE_ASSISTANT_SINGLE_INSTANCE_KEY", f"UndoAudit-{uuid.uuid4().hex}")
    target = sandbox / "inventory.json"
    _seed(target, _payload("before"))
    execute = bridge._execute_cli

    def interleave(argv, data_dir, outcome) -> str:
        result = execute(argv, data_dir, outcome)
        assert result.startswith("OK ")
        _seed(target, _payload("later writer"))
        return result

    monkeypatch.setattr(bridge, "_execute_cli", interleave)
    result = bridge.dispatch_request(
        {"action": "add_item", "parameters": {"name": "assistant write"}}, data_dir=sandbox)
    assert result["snapshot_id"]
    assert _store(sandbox).undo(result["snapshot_id"])[0] is False
    assert json.loads(target.read_text(encoding="utf-8"))["items"][0]["name"] == "later writer"


def test_missing_receipt_leaves_the_snapshot_unusable(sandbox) -> None:
    target = sandbox / "inventory.json"
    _seed(target, _payload("before"))
    store = _store(sandbox)
    snapshot = store.capture("add_item", operation="add_item")
    _seed(target, _payload("later writer"))
    store.finalize(snapshot)
    assert store.undo(snapshot.snapshot_id)[0] is False


def test_undo_refuses_when_a_later_writer_took_the_target(sandbox) -> None:
    """⭐ AI 写 1 → 另一写者写 2 → 撤销**不能**把 2 恢复成 0。"""
    target = sandbox / "inventory.json"
    _seed(target, _payload("零"))
    core.forget_loaded("inventory.json")
    store = _store(sandbox)

    snapshot = store.capture('python scripts/actions.py update_item --id i_001',
                             operation="update_item")
    core.save("inventory.json", _payload("一"))                 # AI 这一笔
    receipt = core.last_commit("inventory.json")
    assert receipt is not None

    # 另一写者（用户 / 另一个 CLI / 另一个学期作业）在 finalize 之前写入
    core.forget_loaded("inventory.json")
    core.save("inventory.json", _payload("二"))

    store.finalize(snapshot, receipt=receipt)
    ok, detail = store.undo()

    assert ok is False and "改过" in detail, detail
    names = [it["name"] for it in json.loads(target.read_text(encoding="utf-8"))["items"]]
    assert names == ["二"], "后发生的合法写入不能被撤销抹掉"


def test_receipt_makes_the_happy_path_still_undoable(sandbox) -> None:
    """反向回归：没有第三方写入时，撤销仍能回到 AI 写入之前。"""
    target = sandbox / "inventory.json"
    _seed(target, _payload("零"))
    core.forget_loaded("inventory.json")
    store = _store(sandbox)

    snapshot = store.capture('python scripts/actions.py update_item --id i_001',
                             operation="update_item")
    core.save("inventory.json", _payload("一"))
    store.finalize(snapshot, receipt=core.last_commit("inventory.json"))

    ok, detail = store.undo()
    assert ok, detail
    names = [it["name"] for it in json.loads(target.read_text(encoding="utf-8"))["items"]]
    assert names == ["零"]


def test_barrier_interleaving_of_two_writers_never_restores_stale_bytes(sandbox) -> None:
    """⭐ 用 Barrier 确定性安排交错（不依赖 sleep）。"""
    target = sandbox / "inventory.json"
    _seed(target, _payload("零"))
    core.forget_loaded("inventory.json")
    store = _store(sandbox)
    barrier = threading.Barrier(2, timeout=10)
    errors: list[BaseException] = []
    receipts: dict[str, dict] = {}

    def ai_writer() -> None:
        try:
            snapshot = store.capture('python scripts/actions.py update_item --id i_001',
                                     operation="update_item")
            core.save("inventory.json", _payload("一"))
            receipts["ai"] = core.last_commit("inventory.json")
            receipts["snapshot"] = snapshot.snapshot_id
            barrier.wait()
            store.finalize(snapshot, receipt=receipts["ai"])
        except BaseException as error:  # noqa: BLE001 — 线程异常带回主线程断言
            errors.append(error)

    def other_writer() -> None:
        try:
            barrier.wait()
            core.forget_loaded("inventory.json")
            core.save("inventory.json", _payload("二"))
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=ai_writer), threading.Thread(target=other_writer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    ok, _detail = store.undo()
    names = [it["name"] for it in json.loads(target.read_text(encoding="utf-8"))["items"]]
    assert "二" in names, f"后写者的内容必须还在，实际 {names!r}"
    assert ok is False or names == ["零"], "要么拒绝，要么只回到 AI 写入前的状态"


def test_index_write_failure_reports_pending_repair(sandbox, monkeypatch) -> None:
    """写入已提交、回执登记失败 → 明确报「已提交，撤销记录待修复」，不谎报可撤销。"""
    target = sandbox / "inventory.json"
    _seed(target, _payload("零"))
    core.forget_loaded("inventory.json")
    store = _store(sandbox)
    snapshot = store.capture('python scripts/actions.py update_item --id i_001',
                             operation="update_item")
    core.save("inventory.json", _payload("一"))

    def broken(_items) -> None:
        raise OSError("磁盘满")

    monkeypatch.setattr(store, "_write_index", broken)
    result = store.finalize(snapshot, receipt=core.last_commit("inventory.json"))

    assert result is not None and result.pending_repair is True
    assert result.after_hash, "回执里的写后指纹仍然要留下（数据确实已提交）"
    monkeypatch.undo()
    assert store.undo()[0] is False, "登记不完整的动作不能撤销"
    assert "待修复" in store.undo()[1]


def test_receipt_is_thread_local_per_writer(sandbox) -> None:
    """两个线程各写一次：各自的回执必须是**自己**那一笔。"""
    target = sandbox / "inventory.json"
    _seed(target, _payload("零"))
    core.forget_loaded("inventory.json")
    seen: dict[str, dict | None] = {}
    barrier = threading.Barrier(2, timeout=10)

    def writer(name: str) -> None:
        barrier.wait()
        core.save("inventory.json", _payload(name))
        seen[name] = core.last_commit("inventory.json")

    threads = [threading.Thread(target=writer, args=(n,)) for n in ("甲", "乙")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert seen["甲"] and seen["乙"]
    assert seen["甲"]["after_sha"] != seen["乙"]["after_sha"]
    assert seen["甲"]["after_sha"] != seen["乙"]["before_sha"], "两人不能读到同一份回执"


def test_receipt_records_which_command_shape_it_came_from(sandbox) -> None:
    """回执带操作 ID 与变更字段 —— 审计要能据此还原"改了哪几项"。"""
    _seed(sandbox / "inventory.json", _payload("零"))
    core.forget_loaded("inventory.json")

    core.save("inventory.json", {**_payload("一"), "locations": ["架子"]})

    receipt = core.last_commit("inventory.json")
    assert receipt is not None
    assert set(receipt["changed_fields"]) == {"items", "locations"}
    assert receipt["operation_id"] and receipt["created_at"]
