"""TaskPanel 回归测试。

覆盖一个真实崩溃：`_refresh` 里 `c = get_colors()` 原先只在「DDL 临期」分支内赋值，
却在「已完成」标题分支被读 → 切到"已完成/全部"且有已完成任务时抛
`UnboundLocalError: cannot access local variable 'c'`。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.services.data_manager import DataManager
from src.ui.panels.task_panel import TaskPanel


def _panel(tmp_path, qapp):
    dm = DataManager(tmp_path)
    dm.tasks.add({"title": "已完成A", "due_date": "2026-01-01T23:00:00"})
    dm.tasks.add({"title": "待办B", "due_date": "2026-01-02T23:00:00"})
    dm.tasks.complete("t_001")
    return TaskPanel(dm)


def test_pending_filter_renders(tmp_path, qapp):
    panel = _panel(tmp_path, qapp)
    panel._status_filter = "pending"
    panel._refresh()
    assert panel._table.rowCount() == 1


def test_completed_filter_does_not_crash(tmp_path, qapp):
    """回归：此路径此前必定 UnboundLocalError。"""
    panel = _panel(tmp_path, qapp)
    panel._status_filter = "completed"
    panel._refresh()
    assert panel._table.rowCount() == 1


def test_all_filter_with_completed_task_does_not_crash(tmp_path, qapp):
    panel = _panel(tmp_path, qapp)
    panel._status_filter = "all"
    panel._refresh()
    assert panel._table.rowCount() == 2


def test_ddl_highlight_path_renders(tmp_path, qapp):
    """DDL 临期高亮分支（c 在此用于 setCellWidget）仍工作。"""
    panel = _panel(tmp_path, qapp)
    panel._highlight_ddl = True
    panel._refresh()
    assert panel._table.rowCount() >= 1
