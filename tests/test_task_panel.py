"""TaskPanel 回归测试。

覆盖一个真实崩溃：`_refresh` 里 `c = get_colors()` 原先只在「DDL 临期」分支内赋值，
却在「已完成」标题分支被读 → 切到"已完成/全部"且有已完成任务时抛
`UnboundLocalError: cannot access local variable 'c'`。

2026-11-02 追加：第 5 列「详情」（按钮 + 备注/附件指示点、双击入口），
并守住"筛选 / 分页 / DDL 高亮"这些既有行为不被新列破坏。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.panels.task_cells import COLUMN_COUNT, DETAIL_COL, detail_badge, detail_button
from src.ui.panels.task_panel import PAGE_SIZE, TaskPanel


def _panel(tmp_path, qapp) -> TaskPanel:
    dm = DataManager(tmp_path)
    dm.tasks.add({"title": "已完成A", "due_date": "2026-01-01T23:00:00"})
    dm.tasks.add({"title": "待办B", "due_date": "2026-01-02T23:00:00"})
    dm.tasks.complete("t_001")
    return TaskPanel(dm)


def _fake_dialog(panel: TaskPanel) -> list[dict]:
    """把详情弹窗替换成只记录参数的假实现（不 `exec()`，测试不会阻塞）。"""
    seen: list[dict] = []

    class _Fake:
        def __init__(self, dm, task, parent=None) -> None:
            seen.append(task)

        def exec(self) -> int:
            return 0

    panel._detail_factory = _Fake
    return seen


# ── 既有回归（三态筛选 / DDL 高亮）─────────────────────────

def test_pending_filter_renders(tmp_path, qapp) -> None:
    panel = _panel(tmp_path, qapp)
    panel._status_filter = "pending"
    panel._refresh()
    assert panel._table.rowCount() == 1


def test_completed_filter_does_not_crash(tmp_path, qapp) -> None:
    """回归：此路径此前必定 UnboundLocalError。"""
    panel = _panel(tmp_path, qapp)
    panel._status_filter = "completed"
    panel._refresh()
    assert panel._table.rowCount() == 1


def test_all_filter_with_completed_task_does_not_crash(tmp_path, qapp) -> None:
    panel = _panel(tmp_path, qapp)
    panel._status_filter = "all"
    panel._refresh()
    assert panel._table.rowCount() == 2


def test_ddl_highlight_path_renders(tmp_path, qapp) -> None:
    """DDL 临期高亮分支（c 在此用于 setCellWidget）仍工作。"""
    panel = _panel(tmp_path, qapp)
    panel._highlight_ddl = True
    panel._refresh()
    assert panel._table.rowCount() >= 1


def test_due_date_none_is_still_rendered_as_dash(tmp_path, qapp) -> None:
    """`due_date` 为 "None" / 空 → 显示破折号（不能被新列改坏）。"""
    dm = DataManager(tmp_path)
    dm.tasks.add({"title": "无截止", "due_date": "None"})
    panel = TaskPanel(dm)
    assert panel._table.item(0, 1).text() == "—"


# ── 新增：详情列 ───────────────────────────────────────────

def test_table_has_detail_column(tmp_path, qapp) -> None:
    panel = _panel(tmp_path, qapp)
    assert panel._table.columnCount() == COLUMN_COUNT == 5
    assert panel._table.horizontalHeaderItem(DETAIL_COL).text() == \
        tr("panel.task.col_detail")


def test_detail_button_opens_dialog_for_its_row(tmp_path, qapp) -> None:
    panel = _panel(tmp_path, qapp)
    panel._status_filter = "all"
    panel._refresh()
    seen = _fake_dialog(panel)

    cell = panel._table.cellWidget(0, DETAIL_COL)
    button = detail_button(cell)
    assert button is not None
    button.click()

    assert [t["title"] for t in seen] == ["已完成A"]


def test_double_click_opens_dialog(tmp_path, qapp) -> None:
    panel = _panel(tmp_path, qapp)
    panel._status_filter = "all"
    panel._refresh()
    seen = _fake_dialog(panel)

    panel._on_cell_double_clicked(1, 2)

    assert [t["title"] for t in seen] == ["待办B"]


def test_detail_for_unknown_task_is_noop(tmp_path, qapp) -> None:
    panel = _panel(tmp_path, qapp)
    seen = _fake_dialog(panel)
    panel._open_detail("t_999")
    assert seen == []


def test_badge_only_when_notes_or_attachments(tmp_path, qapp) -> None:
    dm = DataManager(tmp_path)
    dm.tasks.add({"title": "什么都没有"})
    dm.tasks.add({"title": "有备注", "notes": "第三章"})
    dm.tasks.add({"title": "有附件", "attachments": [
        {"name": "a.pdf", "stored_name": "abc-a.pdf", "size": 2048,
         "sha256": "abc", "added_at": "2026-11-02T10:00:00"}]})
    panel = TaskPanel(dm)
    panel._status_filter = "all"
    panel._refresh()

    assert detail_badge(panel._table.cellWidget(0, DETAIL_COL)) is None
    assert detail_badge(panel._table.cellWidget(1, DETAIL_COL)) is not None
    badge = detail_badge(panel._table.cellWidget(2, DETAIL_COL))
    assert badge is not None and "2.0 KB" in badge.toolTip()


def test_detail_open_keeps_filters_and_page(tmp_path, qapp) -> None:
    """打开详情再刷新，不能把用户的筛选 / 页码重置回第一页。"""
    dm = DataManager(tmp_path)
    for i in range(PAGE_SIZE + 2):
        dm.tasks.add({"title": f"任务{i}", "due_date": "2026-12-01"})
    panel = TaskPanel(dm)
    panel._status_filter = "all"
    panel._next_page()
    panel._refresh()
    assert panel._page == 1

    _fake_dialog(panel)
    panel._open_detail("t_001")

    assert panel._page == 1
    assert panel._status_filter == "all"
    assert panel._table.rowCount() == len(dm.tasks.active) - PAGE_SIZE


def test_detail_cell_survives_theme_refresh(tmp_path, qapp) -> None:
    """换主题会把所有 QPushButton 重设样式 —— 详情按钮不能因此丢失。"""
    panel = _panel(tmp_path, qapp)
    panel._status_filter = "all"
    panel.refresh_theme()
    assert detail_button(panel._table.cellWidget(0, DETAIL_COL)) is not None
