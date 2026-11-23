"""P1：账单**半提交**与附件**差集**（审计 2026-11-21）。

账单复现：模拟 `expenses.save()` 失败 → 库存进度（`paid_count` / `last_charged_on`）
已经写入、通知已发、支出没有落盘。重启后同月也不会补记（`due_today` 看的是进度），
用户那笔钱永远没有账。反向顺序（先记支出、后推进度）则会重复记支出。

验收（审计原文）：分别让支出持久化 / 进度持久化失败，重启并重复执行后，
**正确账期恰有一条支出**，界面和通知有可解释状态。

附件复现：详情里移除一个附件，再添加**同名同内容**文件并保存 —— 最终索引保留一条，
但实体已删除（待删队列没有按最终引用重算）。
"""

import hashlib
import json
from pathlib import Path

from src.models import semester_paths
from src.services import reminder_service as rs
from src.services.data_manager import DataManager


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── 账单：业务键 + 待处理事件 ───────────────────────────────


class _FakeNotify:
    def __init__(self, dm: DataManager) -> None:
        self._dm = dm
        self.sent: list[dict] = []

    def _notify(self, title: str, body: str, **kw: object) -> None:
        self.sent.append({"title": title, "body": body, **kw})


def _billing_item(iid: str, **extra: object) -> dict:
    from src.models.course import schedule_date

    today = schedule_date()
    return {"id": iid, "name": "网盘会员", "category": "订阅",
            "billing_type": "monthly", "amount": 15.0, "due_day": today.day,
            "installments": 0, "paid_count": 0, "billing_active": True, **extra}


def _records(dm: DataManager) -> list[dict]:
    return [r for r in dm.expenses.records if r.get("category") == "subscription"]


def test_expense_failure_still_leaves_exactly_one_record_on_restart(tmp_path, qapp, monkeypatch) -> None:
    """支出落盘失败 → 进度**不能**先提交；重启后补记，恰好一条。"""
    dm = DataManager(tmp_path)
    dm.inventory.add_item(_billing_item("i_001"))
    dm.inventory.save()
    fake = _FakeNotify(dm)
    monkeypatch.setattr(dm.expenses, "save", lambda: False)

    rs._billing_charges_notify(fake)

    disk = json.loads(semester_paths.resolve(tmp_path, "expenses.json").read_text(encoding="utf-8")
                      if semester_paths.resolve(tmp_path, "expenses.json").exists()
                      else (tmp_path / "expenses.json").read_text(encoding="utf-8"))
    assert _records(dm) == [] or disk["records"] == [], "支出没落盘就不能报成功"
    assert "i_001" in {it["id"] for it in dm.inventory.items}

    # "重启"：重新读盘 + 再跑一次
    monkeypatch.undo()
    again = DataManager(tmp_path)
    rs._billing_charges_notify(_FakeNotify(again))

    records = _records(again)
    assert len(records) == 1, f"正确账期应恰有一条支出，实际 {records!r}"
    assert again.inventory.items[0]["paid_count"] == 1


def test_progress_failure_after_expense_does_not_double_charge(tmp_path, qapp, monkeypatch) -> None:
    """支出已落盘、进度持久化失败 → 重启后不得**重复**记支出（反向顺序陷阱）。"""
    dm = DataManager(tmp_path)
    dm.inventory.add_item(_billing_item("i_001"))
    dm.inventory.save()
    real_save = dm.inventory.save
    monkeypatch.setattr(dm.inventory, "save", lambda: False)

    rs._billing_charges_notify(_FakeNotify(dm))

    monkeypatch.setattr(dm.inventory, "save", real_save)
    again = DataManager(tmp_path)
    rs._billing_charges_notify(_FakeNotify(again))
    rs._billing_charges_notify(_FakeNotify(again))

    records = _records(again)
    assert len(records) == 1, f"同一账期只能记一次，实际 {len(records)} 条"
    assert again.inventory.items[0]["paid_count"] == 1
    reopened = DataManager(tmp_path)
    assert reopened.inventory.items[0]["paid_count"] == 1
    assert len(_records(reopened)) == 1


def test_attachment_save_retry_cannot_create_a_missing_reference(tmp_path, qapp, monkeypatch) -> None:
    from src.ui.panels import task_detail_dialog as tdd

    monkeypatch.setattr(tdd.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    dm = DataManager(tmp_path)
    task_id = dm.tasks.add({"title": "Report"})
    assert dm.tasks.save()
    dialog = tdd.TaskDetailDialog(dm, dm.tasks.active[0])
    assert dialog._add_path(_write(tmp_path / "new.txt", b"example"))
    with monkeypatch.context() as patch:
        patch.setattr(dm.tasks, "save", lambda: False)
        dialog._on_save()
    dialog._on_save()
    reopened = DataManager(tmp_path)
    for entry in reopened.tasks.active[0].get("attachments", []):
        assert reopened.attachments.resolve(task_id, entry["stored_name"]) is not None


def test_billing_business_key_is_item_plus_period() -> None:
    from src.models.billing import business_key

    item = {"id": "i_001", "billing_type": "monthly"}
    assert business_key(item, __import__("datetime").date(2026, 11, 21)) == "i_001@2026-11"
    assert business_key(item, __import__("datetime").date(2026, 12, 1)) == "i_001@2026-12"


def test_notification_only_after_commit(tmp_path, qapp, monkeypatch) -> None:
    """通知必须在提交之后发：两份都失败时不能告诉用户"已记支出"。"""
    dm = DataManager(tmp_path)
    dm.inventory.add_item(_billing_item("i_001"))
    fake = _FakeNotify(dm)
    monkeypatch.setattr(dm.expenses, "save", lambda: False)
    monkeypatch.setattr(dm.inventory, "save", lambda: False)

    rs._billing_charges_notify(fake)

    assert fake.sent == [], f"都没提交成功却发了通知：{fake.sent!r}"


def test_pending_charge_event_is_idempotent(tmp_path, qapp) -> None:
    """扣款的**业务键幂等**：同一账期重复登记只留一条支出。"""
    import datetime as dt

    from src.models.billing import business_key

    dm = DataManager(tmp_path)
    item = _billing_item("i_001")
    dm.inventory.add_item(item)
    key = business_key(item, dt.date(2026, 11, 21))

    assert dm.expenses.ensure_charge(key, amount=15.0, note="网盘会员（月付）") is True
    assert dm.expenses.ensure_charge(key, amount=15.0, note="网盘会员（月付）") is False

    assert len(dm.expenses.charge_records(key)) == 1


# ── 附件：初始索引 vs 最终选择的**差集** ────────────────────


def _write(path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_remove_then_readd_same_content_keeps_the_file(tmp_path, qapp, monkeypatch) -> None:
    """⭐ 移除 → 加回同名同内容 → 保存：索引保留一条，**实体也还在**。"""
    from src.ui.panels import task_detail_dialog as tdd
    from src.ui.panels.task_detail_dialog import TaskDetailDialog

    monkeypatch.setattr(tdd.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    dm = DataManager(tmp_path)
    task_id = dm.tasks.add({"title": "算法实验报告"})
    dm.tasks.save()
    task = next(t for t in dm.tasks.active if t["id"] == task_id)
    source = _write(tmp_path / "inbox" / "要求.pdf", b"%PDF spec")
    entry = dm.attachments.add(task_id, source)
    dm.tasks.update(task_id, {"attachments": [entry]})
    dm.tasks.save()
    path = tmp_path / "attachments" / task_id / entry["stored_name"]
    assert path.is_file()

    dialog = TaskDetailDialog(dm, task)
    dialog._on_remove(entry)
    assert path.is_file(), "移除只是进待删队列，文件要等保存成功"
    assert dialog._add_path(source) is True
    dialog._on_save()

    stored = next(t for t in DataManager(tmp_path).tasks.active if t["id"] == task_id)
    assert len(stored["attachments"]) == 1
    assert path.is_file(), "最终索引仍引用这条实体，不能删"


def test_remove_then_readd_and_cancel_keeps_file_and_index(tmp_path, qapp, monkeypatch) -> None:
    """移除 → 加回 → **取消**：索引没提交，实体也不能删。"""
    from src.ui.panels import task_detail_dialog as tdd
    from src.ui.panels.task_detail_dialog import TaskDetailDialog

    monkeypatch.setattr(tdd.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    dm = DataManager(tmp_path)
    task_id = dm.tasks.add({"title": "期末项目"})
    dm.tasks.save()
    task = next(t for t in dm.tasks.active if t["id"] == task_id)
    source = _write(tmp_path / "inbox" / "plan.md", b"# plan")
    entry = dm.attachments.add(task_id, source)
    dm.tasks.update(task_id, {"attachments": [entry]})
    dm.tasks.save()
    path = tmp_path / "attachments" / task_id / entry["stored_name"]

    dialog = TaskDetailDialog(dm, task)
    dialog._on_remove(entry)
    dialog._add_path(source)
    dialog.reject()

    assert path.is_file(), "取消时实体必须保留"
    stored = next(t for t in DataManager(tmp_path).tasks.active if t["id"] == task_id)
    assert len(stored["attachments"]) == 1, "取消不提交索引"


def test_index_write_failure_cleans_up_only_new_entities(tmp_path, qapp, monkeypatch) -> None:
    """写索引失败：本次新增的暂存实体要清掉，**既有**实体一个都不动。"""
    from src.ui.panels import task_detail_dialog as tdd
    from src.ui.panels.task_detail_dialog import TaskDetailDialog

    monkeypatch.setattr(tdd.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    dm = DataManager(tmp_path)
    task_id = dm.tasks.add({"title": "英语作文"})
    dm.tasks.save()
    task = next(t for t in dm.tasks.active if t["id"] == task_id)
    kept = dm.attachments.add(task_id, _write(tmp_path / "inbox" / "old.txt", b"old"))
    dm.tasks.update(task_id, {"attachments": [kept]})
    dm.tasks.save()
    kept_path = tmp_path / "attachments" / task_id / kept["stored_name"]

    dialog = TaskDetailDialog(dm, task)
    assert dialog._add_path(_write(tmp_path / "inbox" / "new.txt", b"new")) is True
    new_paths = list((tmp_path / "attachments" / task_id).glob("*new*"))
    monkeypatch.setattr(dm.tasks, "save", lambda: False)

    dialog._on_save()

    assert kept_path.is_file(), "既有实体不得被清理"
    assert not any(p.is_file() for p in new_paths), "本次新增的暂存实体要清掉"


def test_cleanup_only_runs_for_confirmed_unreferenced(tmp_path, qapp, monkeypatch) -> None:
    """删后**不**加回 → 保存后实体才删（清理只针对最终无引用的）。"""
    from src.ui.panels import task_detail_dialog as tdd
    from src.ui.panels.task_detail_dialog import TaskDetailDialog

    monkeypatch.setattr(tdd.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    dm = DataManager(tmp_path)
    task_id = dm.tasks.add({"title": "物理习题"})
    dm.tasks.save()
    task = next(t for t in dm.tasks.active if t["id"] == task_id)
    entry = dm.attachments.add(task_id, _write(tmp_path / "inbox" / "a.txt", b"a"))
    dm.tasks.update(task_id, {"attachments": [entry]})
    dm.tasks.save()
    path = tmp_path / "attachments" / task_id / entry["stored_name"]

    dialog = TaskDetailDialog(dm, task)
    dialog._on_remove(entry)
    dialog._on_save()

    assert not path.exists()
    stored = next(t for t in DataManager(tmp_path).tasks.active if t["id"] == task_id)
    assert stored["attachments"] == []
