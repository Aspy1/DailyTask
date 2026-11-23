"""`TaskDetailDialog` 行为测试（离屏 Qt，数据全在 `tmp_path`）。

重点守三条不变量：

1. **备注是纯文本且有上限**（`QPlainTextEdit` + `MAX_NOTES`），空白备注存为空串；
2. **附件先提交索引、再删文件**：`model.save()` 返回 False 时，文件一个都不许删；
3. **保存失败要回滚内存**：`notes` / `attachments` / `updated_at` 改回保存前的值
   （原来没有的键要删掉），否则内存领先磁盘，退出时 `flush_on_exit()` 会刷冲突副本。

另外覆盖：添加 / 去重 / 超限 / 缺失文件 / 取消回滚 / 老数据（没有 `attachments` 键）。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from src.services.data_manager import DataManager
from src.ui.panels import task_detail_dialog as tdd
from src.ui.panels.task_detail_dialog import MAX_NOTES, TaskDetailDialog


@pytest.fixture
def dm(tmp_path, qapp) -> DataManager:
    """`qapp` 必须显式依赖：`DataManager` 会 `QTimer(self)`，没有 QApplication 直接崩。"""
    return DataManager(tmp_path)


def _make_task(dm: DataManager, **extra: object) -> dict:
    payload = {"title": "算法实验报告", "course_name": "算法",
               "due_date": "2026-12-01T23:59:00"}
    payload.update(extra)
    task_id = dm.tasks.add(payload)
    dm.tasks.save()                       # `add()` 只改内存 —— 落盘才能"换一个 DataManager 再读"
    return next(t for t in dm.tasks.active if t["id"] == task_id)


def _dialog(dm, task, monkeypatch) -> tuple[TaskDetailDialog, list]:
    warnings: list = []
    monkeypatch.setattr(tdd.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warnings.append(a)))
    return TaskDetailDialog(dm, task), warnings


def _write(path: Path, data: bytes = b"hello") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _tasks_json(tmp_path: Path) -> dict:
    from src.models import semester_paths

    path = semester_paths.resolve(tmp_path, "tasks.json")
    return json.loads(path.read_text(encoding="utf-8"))


# ── 备注 ────────────────────────────────────────────────────

def test_notes_editor_is_plain_text_and_capped(dm, monkeypatch) -> None:
    task = _make_task(dm)
    dlg, _warnings = _dialog(dm, task, monkeypatch)

    dlg._notes.setPlainText("a" * (MAX_NOTES + 50))
    assert len(dlg.notes_text()) == MAX_NOTES
    assert dlg._notes.toPlainText() == "a" * MAX_NOTES


def test_blank_notes_are_preserved_verbatim(dm, monkeypatch) -> None:
    """空白备注不崩、也不被悄悄改写（原样落库；显示层自己决定怎么呈现）。"""
    task = _make_task(dm, notes="旧备注")
    dlg, warnings = _dialog(dm, task, monkeypatch)
    dlg._notes.setPlainText("   \n  ")
    dlg._on_save()

    assert warnings == []
    assert dm.tasks.data["tasks"][0]["notes"] == "   \n  "
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_notes_are_persisted_to_disk(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    dlg, _warnings = _dialog(dm, task, monkeypatch)
    dlg._notes.setPlainText("第三章习题\n用动态规划")
    dlg._on_save()

    reloaded = DataManager(tmp_path)
    stored = next(t for t in reloaded.tasks.active if t["id"] == task["id"])
    assert stored["notes"] == "第三章习题\n用动态规划"


# ── 附件：添加 / 去重 / 限额 ────────────────────────────────

def test_add_attachment_copies_file_and_saves_metadata(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    dlg, warnings = _dialog(dm, task, monkeypatch)
    src = _write(tmp_path / "inbox" / "报告.pdf", b"%PDF-1.4")

    assert dlg._add_path(src) is True
    dlg._on_save()

    assert warnings == []
    stored = next(t for t in DataManager(tmp_path).tasks.active if t["id"] == task["id"])
    entries = stored["attachments"]
    assert len(entries) == 1
    assert entries[0]["name"] == "报告.pdf"
    assert str(tmp_path) not in json.dumps(entries, ensure_ascii=False)
    copied = tmp_path / "attachments" / task["id"] / entries[0]["stored_name"]
    assert copied.read_bytes() == b"%PDF-1.4"


def test_adding_same_file_twice_keeps_one_entry(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    dlg, _warnings = _dialog(dm, task, monkeypatch)
    src = _write(tmp_path / "a.txt", b"same")

    assert dlg._add_path(src) is True
    assert dlg._add_path(src) is True
    assert len(dlg._entries) == 1
    assert dlg._status.text() == tdd.tr("dialog.task.duplicate", name="a.txt")


def test_add_rejects_oversized_file(dm, tmp_path, monkeypatch) -> None:
    dm.attachments.max_bytes = 3
    task = _make_task(dm)
    dlg, warnings = _dialog(dm, task, monkeypatch)

    assert dlg._add_path(_write(tmp_path / "big.bin", b"123456")) is False
    assert warnings, "超限必须给出提示"
    assert dlg._entries == []
    assert not (tmp_path / "attachments" / task["id"]).exists()


def test_add_rejects_directory(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    dlg, warnings = _dialog(dm, task, monkeypatch)
    (tmp_path / "folder").mkdir()

    assert dlg._add_path(tmp_path / "folder") is False
    assert warnings
    assert dlg._entries == []


def test_empty_attachment_list_shows_placeholder(dm, monkeypatch) -> None:
    task = _make_task(dm)
    dlg, _warnings = _dialog(dm, task, monkeypatch)
    placeholder = dlg.findChild(type(dlg._status), "taskAttachmentEmpty")
    assert placeholder is not None and placeholder.text()


# ── 附件：删除必须先提交索引 ───────────────────────────────

def test_remove_keeps_file_when_save_fails(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    src = _write(tmp_path / "a.txt", b"x")
    entry = dm.attachments.add(task["id"], src)
    dm.tasks.update(task["id"], {"attachments": [entry]})
    dm.tasks.save()
    path = tmp_path / "attachments" / task["id"] / entry["stored_name"]
    assert path.is_file()

    dlg, warnings = _dialog(dm, task, monkeypatch)
    dlg._on_remove(entry)
    monkeypatch.setattr(dm.tasks, "save", lambda: False)     # 模拟磁盘被外部改过
    dlg._on_save()

    assert warnings, "保存失败必须提示"
    assert path.is_file(), "索引没提交就不能删文件"
    stored = next(t for t in DataManager(tmp_path).tasks.active if t["id"] == task["id"])
    assert [e["stored_name"] for e in stored["attachments"]] == [entry["stored_name"]]


def test_save_failure_restores_in_memory_task(dm, tmp_path, monkeypatch) -> None:
    """保存失败 → 内存里的任务必须改回保存前（否则退出时会刷一份冲突副本）。"""
    task = _make_task(dm, notes="原始备注")
    entry = dm.attachments.add(task["id"], _write(tmp_path / "a.txt", b"x"))
    dm.tasks.update(task["id"], {"attachments": [entry]})
    dm.tasks.save()
    path = tmp_path / "attachments" / task["id"] / entry["stored_name"]
    before_notes = task["notes"]
    before_attachments = [dict(e) for e in task["attachments"]]
    before_updated_at = task["updated_at"]
    disk_before = _tasks_json(tmp_path)

    dlg, warnings = _dialog(dm, task, monkeypatch)
    dlg._notes.setPlainText("改过的备注")
    dlg._on_remove(entry)                                    # 索引里去掉附件
    monkeypatch.setattr(dm.tasks, "save", lambda: False)     # 模拟磁盘被外部改过
    dlg._on_save()

    assert warnings, "保存失败必须提示"
    assert path.is_file(), "索引没提交就不能删文件"
    assert _tasks_json(tmp_path) == disk_before, "没写盘就不许动磁盘"
    live = next(t for t in dm.tasks.active if t["id"] == task["id"])
    assert live is task, "回滚必须落在模型里那一份任务上"
    assert live["notes"] == before_notes
    assert live["attachments"] == before_attachments
    assert live["updated_at"] == before_updated_at, "失败的那次更新时间也不能留下"


def test_save_failure_keeps_attachments_key_absent(dm, tmp_path, monkeypatch) -> None:
    """老数据本来没有 `attachments` / `updated_at` 键 → 回滚后也**不许**留空壳。"""
    task = _make_task(dm, notes="原始备注")
    assert "attachments" not in task and "updated_at" not in task
    disk_before = _tasks_json(tmp_path)

    dlg, warnings = _dialog(dm, task, monkeypatch)
    assert dlg._add_path(_write(tmp_path / "b.txt", b"y")) is True
    monkeypatch.setattr(dm.tasks, "save", lambda: False)
    dlg._on_save()

    assert warnings
    assert "attachments" not in task, "内存不许把老数据悄悄升级成新 schema"
    assert "updated_at" not in task
    assert task["notes"] == "原始备注"
    assert _tasks_json(tmp_path) == disk_before


def test_remove_deletes_file_after_successful_save(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    entry = dm.attachments.add(task["id"], _write(tmp_path / "a.txt", b"x"))
    dm.tasks.update(task["id"], {"attachments": [entry]})
    dm.tasks.save()
    path = tmp_path / "attachments" / task["id"] / entry["stored_name"]

    dlg, warnings = _dialog(dm, task, monkeypatch)
    dlg._on_remove(entry)
    dlg._on_save()

    assert warnings == []
    assert not path.exists()
    stored = next(t for t in DataManager(tmp_path).tasks.active if t["id"] == task["id"])
    assert stored["attachments"] == []


def test_cancel_rolls_back_newly_added_files(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    dlg, _warnings = _dialog(dm, task, monkeypatch)
    assert dlg._add_path(_write(tmp_path / "a.txt", b"x")) is True
    folder = tmp_path / "attachments" / task["id"]
    assert list(folder.iterdir())

    dlg.reject()

    assert not folder.exists() or not list(folder.iterdir())
    stored = next(t for t in DataManager(tmp_path).tasks.active if t["id"] == task["id"])
    assert stored.get("attachments") in (None, [])


# ── 打开 / 缺失 ────────────────────────────────────────────

def test_open_uses_desktop_services_wrapper(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    entry = dm.attachments.add(task["id"], _write(tmp_path / "a.txt", b"x"))
    dlg, _warnings = _dialog(dm, task, monkeypatch)
    opened: list[Path] = []
    monkeypatch.setattr(tdd, "open_path", lambda p: opened.append(p) or True)

    dlg._on_open(entry)

    assert opened == [tmp_path / "attachments" / task["id"] / entry["stored_name"]]


def test_open_missing_file_warns_without_raising(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    entry = dm.attachments.add(task["id"], _write(tmp_path / "a.txt", b"x"))
    (tmp_path / "attachments" / task["id"] / entry["stored_name"]).unlink()
    dlg, warnings = _dialog(dm, task, monkeypatch)
    opened: list[Path] = []
    monkeypatch.setattr(tdd, "open_path", lambda p: opened.append(p) or True)

    dlg._on_open(entry)

    assert opened == []
    assert warnings, "文件缺失要提示用户"


def test_missing_file_is_marked_in_row_meta(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    entry = dm.attachments.add(task["id"], _write(tmp_path / "a.txt", b"x"))
    (tmp_path / "attachments" / task["id"] / entry["stored_name"]).unlink()
    dlg, _warnings = _dialog(dm, task, monkeypatch)

    assert tdd.tr("dialog.task.missing_file") in dlg._entry_meta(entry)


# ── 老数据 / 兼容 ──────────────────────────────────────────

def test_task_without_attachments_key_is_supported(dm, tmp_path, monkeypatch) -> None:
    task = _make_task(dm)
    task.pop("attachments", None)          # 老数据没有这个键
    dlg, warnings = _dialog(dm, task, monkeypatch)
    assert dlg._entries == []

    dlg._on_save()
    assert warnings == []
    stored = next(t for t in DataManager(tmp_path).tasks.active if t["id"] == task["id"])
    assert stored["attachments"] == []


def test_dirty_attachment_entries_do_not_crash(dm, monkeypatch) -> None:
    task = _make_task(dm, attachments=["not-a-dict", {"no_stored_name": True}])
    dlg, _warnings = _dialog(dm, task, monkeypatch)
    assert dlg._entries == []
