"""`TaskPanel` 的**单元格工厂**（从面板类里抽出来：Q-A1 类/函数行数限制）。

为什么单独一个模块：`TaskPanel` 已经接近 400 行上限，而"第 N 列长什么样"与面板的
筛选 / 分页 / 信号接线是两件事。抽出来之后：单元格逻辑可单独测（不需要造整个面板），
面板类只负责"取数据 → 交给工厂 → 放上表格"。

**约定**：这里的函数都可接收 `task: dict` + 回调，不持有 `DataManager`，
也不改数据 —— 点击回调交给面板处理（`on_open(task_id)` / `on_toggle(task_id, checked)`）。
"""

from collections.abc import Callable
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)

from src.i18n.loader import tr
from src.services.attachments import human_size
from src.ui.styles.theme import (
    CONTROLS,
    SIZE_BODY_S,
    SIZE_CAPTION,
    SPACING,
    btn_secondary_qss,
    get_colors,
)
from src.ui.widgets.rounded_button import RoundedButton

# 列下标（面板与测试共用同一份定义，避免"魔法数字 4"散落各处）
COURSE_COL = 0
DUE_COL = 1
TITLE_COL = 2
DONE_COL = 3
DETAIL_COL = 4


def warn_save_failed(parent: QWidget, what: str) -> None:
    """提交失败要**说出来**（审计 2026-11-21 P1）。

    旧实现勾选后不看 `save()` 返回值：落盘被拒时界面显示已完成、磁盘还是未完成。
    """
    QMessageBox.warning(parent, tr("panel.task.save_failed_title"),
                        tr("panel.task.save_failed_body", what=what))


def commit_status(dm, task_id: str, checked: bool, parent: QWidget) -> bool:
    """把勾选**提交到磁盘** → `True` = 可以刷新并广播。

    `save()` 返回 False（磁盘被外部改过 / 文件损坏）时回滚内存并弹提示：
    界面必须与磁盘一致，不能"显示已完成、实际没写进去"。
    """
    snapshot = dm.tasks.set_status(task_id, checked)
    if snapshot is None:
        return False
    if dm.tasks.save():
        dm.data_changed.emit("task_status")
        return True
    dm.tasks.restore_task(snapshot)
    warn_save_failed(parent, tr("panel.task.what_status"))
    return False


COLUMN_COUNT = 5


def attachments_of(task: dict) -> list[dict]:
    """任务里的附件元数据（脏数据过滤掉，永不让 UI 崩在 `AttributeError`）。"""
    raw = task.get("attachments") or []
    return [e for e in raw if isinstance(e, dict) and e.get("stored_name")]


def has_detail_content(task: dict) -> bool:
    """有备注或附件 → 详情入口要显示指示点。"""
    return bool(str(task.get("notes") or "").strip()) or bool(attachments_of(task))


def detail_tooltip(task: dict) -> str:
    """详情按钮的提示：把"有什么"说清楚（备注字数 + 附件数与总大小）。"""
    notes = str(task.get("notes") or "").strip()
    files = attachments_of(task)
    if not notes and not files:
        return tr("panel.task.detail_tooltip_empty")
    total = sum(int(e.get("size") or 0) for e in files)
    if notes and files:
        return tr("panel.task.detail_tooltip_both", chars=len(notes),
                  files=len(files), size=human_size(total))
    if files:
        return tr("panel.task.detail_tooltip_files", files=len(files),
                  size=human_size(total))
    return tr("panel.task.detail_tooltip_notes", chars=len(notes))


def is_near_ddl(due_date, highlight: bool) -> bool:
    """是否按 DDL 临期（3 天内）高亮截止列（`due_date` 已由面板解析成 date/None）。"""
    if not highlight or due_date is None:
        return False
    return due_date <= date.today() + timedelta(days=3)


def make_course_item(task: dict) -> QTableWidgetItem:
    item = QTableWidgetItem(task.get("course_name", "") or "—")
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


def make_due_item(due_display: str) -> QTableWidgetItem:
    item = QTableWidgetItem(due_display)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


def make_title_item(task: dict) -> QTableWidgetItem:
    item = QTableWidgetItem(task.get("title", ""))
    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    if task.get("status") == "completed":
        item.setForeground(QBrush(QColor(get_colors()["fg_hint"])))
    return item


def make_ddl_cell(base_font: QFont, width: int, due_display: str, days_left: int,
                  colors: dict) -> QLabel:
    """DDL 临期（3 天内）的富文本单元格。"""
    lbl = QLabel()
    lbl.setFont(base_font)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setMinimumWidth(max(0, width - 10))
    lbl.setWordWrap(False)
    lbl.setText(
        f'<span style="color:{colors["red"]};font-size: {SIZE_BODY_S}px;">{due_display}</span>'
        f' <span style="color:{colors["fg_secondary"]};font-size: {SIZE_BODY_S}px;">'
        f'{tr("panel.task.days_left", days=days_left)}</span>'
    )
    return lbl


def make_check_cell(task: dict, on_toggle: Callable[[str, bool], None]) -> QWidget:
    """完成复选框（`clicked(bool)`，不用 `toggled` —— R-008 的回环坑）。"""
    holder = QWidget()
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cb = QCheckBox()
    cb.setChecked(task.get("status") == "completed")
    task_id = str(task.get("id") or "")
    cb.clicked.connect(lambda checked, tid=task_id: on_toggle(tid, checked))
    lay.addWidget(cb)
    return holder


def make_detail_cell(task: dict, on_open: Callable[[str], None]) -> QWidget:
    """第 4 列：详情入口按钮 + "有内容"指示点（备注 / 附件）。"""
    cell = QWidget()
    cell.setObjectName("taskDetailCell")
    lay = QHBoxLayout(cell)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(SPACING["spacing_xs"])
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

    task_id = str(task.get("id") or "")
    btn = RoundedButton(tr("panel.task.btn_detail"))
    btn.setObjectName("taskDetailButton")
    btn.setStyleSheet(btn_secondary_qss())
    btn.setFixedHeight(CONTROLS["button_height_sm"])
    btn.setToolTip(detail_tooltip(task))
    btn.clicked.connect(lambda _checked=False, tid=task_id: on_open(tid))
    lay.addWidget(btn)

    if has_detail_content(task):
        badge = QLabel("●")
        badge.setObjectName("taskDetailBadge")
        badge.setToolTip(detail_tooltip(task))
        badge.setStyleSheet(
            f"color: {get_colors()['accent_text']}; background: transparent;"
            f" border: none; font-size: {SIZE_CAPTION}px;")
        lay.addWidget(badge)

    lay.addStretch()
    return cell


def detail_button(cell: QWidget) -> QWidget | None:
    """从单元格里取回详情按钮（测试与冒烟脚本用）。"""
    if cell is None:
        return None
    return cell.findChild(RoundedButton, "taskDetailButton")


def detail_badge(cell: QWidget) -> QLabel | None:
    """从单元格里取回"有内容"指示点（没有则 None）。"""
    if cell is None:
        return None
    return cell.findChild(QLabel, "taskDetailBadge")
