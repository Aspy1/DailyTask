"""P1：UI 的成功判定必须以**提交结果**为准（审计 2026-11-21）。

复现：作业勾选先改内存、不看 `save()` 返回值就广播刷新 ——
落盘被拒（磁盘被外部改过）时界面显示"已完成"，磁盘还是未完成，
而且广播会让其它面板按内存态重画，看起来一切正常。

验收（审计原文）：服务层收口"变更 + 提交"，失败时回滚内存或重新加载；
提交完成后才发领域事件。
"""

import json

import pytest

from src.models import semester_paths
from src.services.data_manager import DataManager
from src.ui.panels import task_panel as tp
from src.ui.panels.task_panel import TaskPanel


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch) -> None:
    """弹窗是模态的：离屏跑测试会一直等关闭。项目里同类测试都这样打桩。"""
    monkeypatch.setattr(tp.QMessageBox, "warning", staticmethod(lambda *a, **k: None))


def _seed(dm: DataManager, title: str = "算法实验报告") -> str:
    task_id = dm.tasks.add({"title": title})
    dm.tasks.save()
    return task_id


def _disk_status(tmp_path, task_id: str) -> str:
    path = semester_paths.resolve(tmp_path, "tasks.json")
    tasks = json.loads(path.read_text(encoding="utf-8"))["tasks"]
    return next(t["status"] for t in tasks if t["id"] == task_id)


def _panel(dm: DataManager) -> TaskPanel:
    return TaskPanel(dm)


def test_checkbox_rolls_back_when_save_is_refused(qapp, tmp_path) -> None:
    """⭐ `save()` 返回 False → 内存回滚，界面不报完成，不发事件。"""
    dm = DataManager(tmp_path)
    task_id = _seed(dm)
    panel = _panel(dm)
    events: list[str] = []
    dm.data_changed.connect(events.append)

    dm.tasks.on_conflict = None
    dm.tasks._disk_fingerprint = "被人改过的指纹"      # 让 save() 判为冲突
    panel._on_check(task_id, True)

    task = next(t for t in dm.tasks.tasks if t["id"] == task_id)
    assert task["status"] == "pending", "保存失败必须回滚内存"
    assert "task" not in " ".join(events), f"没提交成功不该广播：{events!r}"
    assert _disk_status(tmp_path, task_id) == "pending"


def test_checkbox_succeeds_and_broadcasts_after_commit(qapp, tmp_path) -> None:
    dm = DataManager(tmp_path)
    task_id = _seed(dm)
    panel = _panel(dm)
    events: list[str] = []
    dm.data_changed.connect(events.append)

    panel._on_check(task_id, True)

    assert _disk_status(tmp_path, task_id) == "completed"
    assert any("task" in event for event in events), events


def test_checkbox_does_not_rebuild_rows_twice_when_event_refreshes(qapp, sandbox, monkeypatch) -> None:
    dm = DataManager(sandbox)
    task_id = _seed(dm)
    panel = _panel(dm)
    rebuild_rows = panel._rebuild_rows
    renders = []

    def count_rebuild() -> None:
        renders.append(True)
        rebuild_rows()

    monkeypatch.setattr(panel, "_rebuild_rows", count_rebuild)
    dm.data_changed.connect(lambda _: panel._refresh())
    panel._on_check(task_id, True)

    assert renders == [True]
    assert panel._table.rowCount() == 0
    assert _disk_status(sandbox, task_id) == "completed"


def test_uncomplete_rolls_back_too(qapp, tmp_path) -> None:
    dm = DataManager(tmp_path)
    task_id = _seed(dm)
    dm.tasks.complete(task_id)
    dm.tasks.save()
    panel = _panel(dm)

    dm.tasks._disk_fingerprint = "被人改过的指纹"
    panel._on_check(task_id, False)

    task = next(t for t in dm.tasks.tasks if t["id"] == task_id)
    assert task["status"] == "completed", "取消勾选保存失败也要回滚"
