"""Task panel — table with filters, pagination, checkboxes, archive, notes."""

import logging
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.panels.task_cells import (
    COLUMN_COUNT,
    COURSE_COL,
    DETAIL_COL,
    DONE_COL,
    DUE_COL,
    TITLE_COL,
    commit_status,
    is_near_ddl,
    make_check_cell,
    make_course_item,
    make_ddl_cell,
    make_detail_cell,
    make_due_item,
    make_title_item,
)
from src.ui.panels.task_detail_dialog import TaskDetailDialog
from src.ui.styles.theme import LAYOUT, SIZE_BODY_S, font, get_colors
from src.ui.widgets.empty_state import empty_state
from src.ui.widgets.menu import (
    add_action,
    add_separator,
    new_menu,
    show_below,
)
from src.ui.widgets.rounded_button import RoundedButton

# 每页行数也是令牌（`layout.task_page_size`），别在面板里写 10
PAGE_SIZE = LAYOUT["task_page_size"]

TIME_BUCKETS = [
    (tr("panel.task.filter_all"), None),
    (tr("panel.task.bucket_today"), "today"),
    (tr("panel.task.bucket_tomorrow"), "tomorrow"),
    (tr("panel.task.bucket_this_week"), "this_week"),
    (tr("panel.task.bucket_next_week"), "next_week"),
    (tr("panel.task.bucket_this_month"), "this_month"),
    (tr("panel.task.bucket_overdue"), "overdue"),
    (tr("panel.task.bucket_no_date"), "no_date"),
]


logger = logging.getLogger(__name__)


def _parse_due(due_str) -> date | None:
    if not due_str or due_str == "None" or due_str is None:
        return None
    try:
        return date.fromisoformat(due_str[:10])
    except (ValueError, TypeError):
        return None


def _blank_item() -> QTableWidgetItem:
    """占位 item（空文字）。

    ⚠ 只有 `cellWidget` 的列**必须**再放一个 item：Qt 的交替行底色 / 网格 / 行高
    都是按 **item** 画的，格子里只有 widget 时那一列会缺一块背景（A1）。
    文本留空，widget 盖在上面，用户看不到它。
    """
    return QTableWidgetItem("")


def _match_time_bucket(due_str: str, bucket: str | None) -> bool:
    if bucket is None:
        return True
    due = _parse_due(due_str)
    today = date.today()
    if due is None:
        return bucket == "no_date"
    if bucket == "overdue":
        return due < today
    if bucket == "today":
        return due == today
    if bucket == "tomorrow":
        return due == today + timedelta(days=1)
    if bucket == "this_week":
        weekday = today.weekday()
        week_start = today - timedelta(days=weekday)
        week_end = week_start + timedelta(days=6)
        return week_start <= due <= week_end
    if bucket == "next_week":
        weekday = today.weekday()
        week_start = today - timedelta(days=weekday) + timedelta(days=7)
        week_end = week_start + timedelta(days=6)
        return week_start <= due <= week_end
    if bucket == "this_month":
        return due.year == today.year and due.month == today.month
    return True


class TaskPanel(QWidget):
    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._page = 0
        self._selected_courses: set[str] = set()
        self._time_bucket: str | None = None
        self._highlight_ddl = False
        self._status_filter = "pending"  # "pending" | "completed" | "all"
        # 当前页的行 → 任务（双击 / 详情按钮靠它定位；不要靠 item 文本反查）
        self._row_tasks: list[dict] = []
        self._detail_factory = TaskDetailDialog   # 测试可替换成假弹窗（不真 exec）
        # 外框按钮（工具栏 + 翻页）：`refresh_theme` **只**重刷这些 —— 列表里的详情按钮
        # 走 `btn_secondary_qss()` + `remap_stylesheets()`，一并重设会覆盖它们自己的样式（A3）
        self._chrome_buttons: list[RoundedButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_bar())

        self._table = self._build_table()
        layout.addWidget(self._table, stretch=1)

        # 0 行时顶替表格（不放空表格：那只会剩一片空白）
        self._empty = self._build_empty_state()
        layout.addWidget(self._empty, stretch=1)

        layout.addWidget(self._build_footer())
        self._refresh()

    # ── 结构 ──────────────────────────────────────────────────

    def _build_bar(self) -> QWidget:
        """工具栏（标题 + 四个筛选/刷新按钮）。抽出来是因为 `__init__` 有行数上限（Q-A1）。"""
        c = get_colors()
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)
        bar_layout.setSpacing(8)

        title = QLabel(tr("panel.task.heading"))
        title.setFont(font("pageTitle"))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bar_layout.addWidget(title)
        bar_layout.addStretch()

        self._filter_btn = self._add_chrome_button(
            bar_layout, tr("panel.task.btn_course_filter"), self._show_course_filter)
        self._time_btn = self._add_chrome_button(
            bar_layout, tr("panel.task.btn_time_filter"), self._show_time_filter)
        self._status_btn = self._add_chrome_button(
            bar_layout, tr("panel.task.status_pending"), self._toggle_status_filter)
        self._add_chrome_button(
            bar_layout, tr("panel.task.btn_refresh"), lambda _checked=False: self._refresh())
        return bar

    def _build_footer(self) -> QWidget:
        """页脚（计数 + 翻页）。底色由全局 QSS 的 `#taskFooter` 给（chrome 表面）。"""
        footer = QWidget()
        footer.setObjectName("taskFooter")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 4, 16, 4)

        # ⚠ 字号 / 颜色**只**由全局 QSS 的 `#taskCount` 定义：这里再设一次会和它打架
        # （此前 refresh_theme 用 SIZE_BODY_S 覆盖了全局的 SIZE_TINY，见 A5）
        self._count_label = QLabel()
        self._count_label.setObjectName("taskCount")
        fl.addWidget(self._count_label)
        fl.addStretch()

        self._add_chrome_button(fl, tr("panel.task.btn_prev_page"), self._prev_page)
        self._add_chrome_button(fl, tr("panel.task.btn_next_page"), self._next_page)
        return footer

    def _build_empty_state(self) -> QWidget:
        """空态卡片（默认隐藏；`_sync_empty_state` 按行数切换）。"""
        box = empty_state(tr("panel.task.empty_title"), tr("panel.task.empty_body"))
        box.hide()
        return box

    def _add_chrome_button(self, layout, text: str, slot) -> RoundedButton:
        """造一个外框按钮：样式一律走 `_btn_qss()`（唯一工厂），并登记进 `_chrome_buttons`。"""
        btn = RoundedButton(text)
        btn.setStyleSheet(self._btn_qss())
        btn.clicked.connect(slot)
        layout.addWidget(btn)
        self._chrome_buttons.append(btn)
        return btn

    def _build_table(self) -> QTableWidget:
        """表格本体（从 `__init__` 抽出：Q-A1 的函数行数上限）。"""
        table = QTableWidget(0, COLUMN_COUNT)
        table.setObjectName("taskTable")
        table.setHorizontalHeaderLabels([
            tr("panel.task.col_course"), tr("panel.task.col_due"),
            tr("panel.task.col_title"), tr("panel.task.col_done"),
            tr("panel.task.col_detail"),
        ])
        header = table.horizontalHeader()
        header.setSectionResizeMode(COURSE_COL, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(DUE_COL, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(TITLE_COL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(DONE_COL, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(DETAIL_COL, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(COURSE_COL, LAYOUT["task_col_course_width"])
        table.setColumnWidth(DUE_COL, LAYOUT["task_col_due_width"])
        table.setColumnWidth(DONE_COL, LAYOUT["task_col_done_width"])
        table.setColumnWidth(DETAIL_COL, LAYOUT["task_detail_col_width"])
        header.setStretchLastSection(False)
        # 表头与课程表**同一档**高度/内边距（令牌 `layout.table_header_height`）
        header.setMinimumHeight(LAYOUT["table_header_height"])
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col in range(COLUMN_COUNT):
            _align_header_item(table, col)
        header.setSortIndicatorShown(False)
        header.setSectionsClickable(False)
        table.setSortingEnabled(False)
        table.verticalHeader().setVisible(False)
        # 行高按内容（原来固定 48 会裁掉换行标题 —— U6）；默认行高用令牌兜底
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setDefaultSectionSize(LAYOUT["table_row_height"])
        table.setWordWrap(True)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        # 双击任意一行 = 打开详情（详情列本身有按钮，双击是给"手快"的用户留的入口）
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        return table

    def _btn_qss(self) -> str:
        """外框按钮（工具栏 / 翻页）的**唯一**样式工厂。

        ⚠ `__init__` 与 `refresh_theme` 必须用同一份：此前两处各写一套，初始化那份
        **没有描边**、换主题那份有 `border: 1px` —— 于是切一次主题按钮就高 2px、
        文字色也换了（A2）。
        """
        c = get_colors()
        return f"""
            QPushButton {{ background-color: {c["btn_secondary_bg"]}; color: {c["fg_hint"]};
                border: none; border-radius: 8px;
                padding: 4px 12px; font-size: {SIZE_BODY_S}px; }}
            QPushButton:hover {{ background-color: {c["btn_secondary_hover"]}; color: {c["fg_secondary"]}; }}
            QPushButton::menu-indicator {{ image: none; }}
        """

    def fade_target(self) -> QTableWidget:
        """切页淡入只作用于**内容区**（表格）。工具栏 / 页脚是静态外框，不参与淡入。"""
        return self._table

    # ── Data ──────────────────────────────────────────────────

    def _get_filtered(self) -> list[dict]:
        tasks = self._status_filtered()
        if self._selected_courses:
            tasks = [t for t in tasks if (t.get("course_name", "") or "—") in self._selected_courses]
        if self._time_bucket is not None:
            tasks = [t for t in tasks if _match_time_bucket(t.get("due_date", ""), self._time_bucket)]
        return tasks

    def _status_filtered(self) -> list[dict]:
        """按完成状态筛选（全部 / 未完成 / 已完成）。"""
        tasks = self._dm.tasks.active
        if self._status_filter == "completed":
            return [t for t in tasks if t.get("status") == "completed"]
        if self._status_filter == "pending":
            return [t for t in tasks if t.get("status") != "completed"]
        return tasks

    def _course_set(self) -> list[str]:
        names = set()
        for t in self._dm.tasks.active:
            cn = t.get("course_name", "") or ""
            if cn:
                names.add(cn)
        return sorted(names)

    def _show_course_filter(self) -> None:
        self._highlight_ddl = False
        menu = new_menu(self)

        add_action(menu, tr("panel.task.filter_all_courses"),
                   lambda checked=False: self._apply_course_filter(set()),
                   checkable=True, checked=not self._selected_courses)

        add_separator(menu)

        for cn in self._course_set():
            add_action(menu, cn,
                       lambda checked=False, c=cn: self._toggle_course(c),
                       checkable=True, checked=cn in self._selected_courses)

        show_below(menu, self._filter_btn)

    def _toggle_course(self, course: str) -> None:
        sel = set(self._selected_courses)
        if course in sel:
            sel.discard(course)
        else:
            sel.add(course)
        self._apply_course_filter(sel)

    def show_ddl_highlight(self) -> None:
        self._highlight_ddl = True
        self._time_bucket = None
        self._selected_courses = set()
        self._filter_btn.setText(tr("panel.task.btn_course_filter"))
        self._time_btn.setText(tr("panel.task.btn_time_filter"))
        self._page = 0
        self._refresh()

    def filter_by_course(self, course_name: str) -> None:
        self._selected_courses = {course_name}
        self._page = 0
        self._filter_btn.setText(tr("panel.task.filter_course_prefix", name=course_name))
        # 旧实现只改了筛选项、没刷新表格：从课程表点"查看事项"后仍显示全部任务
        self._refresh()

    def _apply_course_filter(self, sel: set[str]) -> None:
        self._selected_courses = sel
        self._page = 0
        if sel:
            self._filter_btn.setText(tr("panel.task.filter_course_count", n=len(sel)))
        else:
            self._filter_btn.setText(tr("panel.task.btn_course_filter"))
        self._refresh()

    def _show_time_filter(self) -> None:
        menu = new_menu(self)
        for label, key in TIME_BUCKETS:
            add_action(menu, label,
                       lambda checked=False, k=key: self._apply_time_filter(k),
                       checkable=True, checked=key == self._time_bucket)
        show_below(menu, self._time_btn)

    def _apply_time_filter(self, bucket: str | None) -> None:
        self._time_bucket = bucket
        self._page = 0
        if bucket:
            label = next((lbl for lbl, k in TIME_BUCKETS if k == bucket), bucket)
            self._time_btn.setText(tr("panel.task.filter_time_prefix", label=label))
        else:
            self._time_btn.setText(tr("panel.task.btn_time_filter"))
        self._refresh()

    def _refresh(self, preserve_scroll: bool = True) -> None:
        """按当前筛选重画表格。

        `preserve_scroll`：保留滚动位置。原来 `setRowCount(0)` 后滚动条跳回顶部 ——
        勾一条完成、或从详情弹窗回来，人就被"弹"回第一行。

        重建期间 `setUpdatesEnabled(False)`：逐行插入会触发 N 次重排/重绘，整表的**中间
        状态**（半张表 + 抖动的滚动条）会被画出来；关掉更新后只画最终态。
        """
        table = self._table
        scroll = table.verticalScrollBar().value() if preserve_scroll else 0
        table.setUpdatesEnabled(False)
        try:
            self._rebuild_rows()
        finally:
            table.setUpdatesEnabled(True)
        if preserve_scroll:
            table.verticalScrollBar().setValue(scroll)

    def _rebuild_rows(self) -> None:
        """清空并按当前页重新填表（`_refresh` 的"无闪烁"版）。"""
        table = self._table
        table.setSortingEnabled(False)
        table.horizontalHeader().setSortIndicatorShown(False)
        table.setRowCount(0)

        tasks = self._get_filtered()
        total = len(tasks)
        max_page = max(0, (total - 1) // PAGE_SIZE)
        if self._page > max_page:
            self._page = max_page
        start = self._page * PAGE_SIZE
        self._row_tasks = list(tasks[start:start + PAGE_SIZE])

        colors = get_colors()
        for i, task in enumerate(self._row_tasks):
            table.insertRow(i)
            table.setItem(i, COURSE_COL, make_course_item(task))
            self._fill_due_cell(i, task, colors)
            table.setItem(i, TITLE_COL, make_title_item(task))
            # ⚠ 下面两列只有 widget：先放空 item 占位，否则交替行底色在这两格缺失（A1）
            table.setItem(i, DONE_COL, _blank_item())
            table.setCellWidget(i, DONE_COL, make_check_cell(task, self._on_check))
            table.setItem(i, DETAIL_COL, _blank_item())
            table.setCellWidget(i, DETAIL_COL, make_detail_cell(task, self._open_detail))

        self._update_footer(total, max_page)
        self._sync_empty_state(bool(self._row_tasks))

    def _fill_due_cell(self, row: int, task: dict, colors: dict) -> None:
        """截止列：临期（3 天内）用富文本 QLabel，其余走普通 item。"""
        due = task.get("due_date", "")
        due_display = due[:16].replace("T", " ") if due and due != "None" else "—"
        due_date = _parse_due(due)
        if is_near_ddl(due_date, self._highlight_ddl):
            self._table.setItem(row, DUE_COL, _blank_item())
            self._table.setCellWidget(
                row, DUE_COL,
                make_ddl_cell(self._table.font(), self._table.columnWidth(DUE_COL),
                              due_display, (due_date - date.today()).days, colors))
        else:
            self._table.setItem(row, DUE_COL, make_due_item(due_display))

    def _update_footer(self, total: int, max_page: int) -> None:
        page_str = (tr("panel.task.page_info", page=self._page + 1, total=max_page + 1)
                    if total > PAGE_SIZE else "")
        self._count_label.setText(tr("panel.task.count", total=total, page=page_str))

    def _sync_empty_state(self, has_rows: bool) -> None:
        """0 行时用空态卡片顶替表格：只留一片空白不算"空态"，得说明为什么空。"""
        self._empty.setVisible(not has_rows)
        self._table.setVisible(has_rows)

    # ── 详情 ──────────────────────────────────────────────────

    def _open_detail(self, task_id: str) -> None:
        """打开作业详情（备注 + 附件）。保存后刷新本页，筛选状态保持不变。"""
        task = next((t for t in self._dm.tasks.active if t.get("id") == task_id), None)
        if task is None:
            logger.debug("详情：任务已不存在 %s", task_id)
            self._refresh()
            return
        dialog = self._detail_factory(self._dm, task, self)
        dialog.exec()
        self._refresh()

    def _on_cell_double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._row_tasks):
            self._open_detail(str(self._row_tasks[row].get("id") or ""))

    def _on_check(self, task_id: str, checked: bool) -> None:
        """勾选 → 提交 → 刷新。**提交成功才刷新和广播**（审计 2026-11-21 P1）。

        旧实现先改内存再 `save()`，完全不看返回值：落盘被拒（磁盘被外部改过 /
        文件损坏）时界面显示已完成、磁盘还是未完成，广播还会让别的面板按内存态重画。
        失败时内存已回滚，这里照常重画（显示的就是磁盘上的状态）。
        """
        commit_status(self._dm, task_id, checked, self)
        self._refresh()

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._refresh()

    def _next_page(self) -> None:
        tasks = self._get_filtered()
        max_page = max(0, (len(tasks) - 1) // PAGE_SIZE)
        if self._page < max_page:
            self._page += 1
            self._refresh()

    def refresh_theme(self) -> None:
        """换主题：**只**重刷外框按钮。

        ⚠ 列表里的详情按钮（`task_cells.make_detail_cell`）不在重刷范围：它们用
        `btn_secondary_qss()`，换主题时由 `theme.remap_stylesheets()` 按色值映射更新。
        这里一并重设会把它们的原始样式覆盖成外框样式（A3）。
        """
        btn_qss = self._btn_qss()
        for btn in self._chrome_buttons:
            btn.setStyleSheet(btn_qss)
        # 计数标签**不**在这里设字号/颜色：唯一来源是全局 QSS 的 `#taskCount`（A5）

    def _toggle_status_filter(self) -> None:
        cycle = {"pending": "completed", "completed": "all", "all": "pending"}
        labels = {"pending": tr("panel.task.status_pending"),
                  "completed": tr("task.status.completed"),
                  "all": tr("panel.task.filter_all")}
        self._status_filter = cycle[self._status_filter]
        self._status_btn.setText(labels[self._status_filter])
        self._page = 0
        self._refresh()

    def _show_archive(self) -> None:
        archived = self._dm.tasks.archived
        if not archived:
            QMessageBox.information(self, tr("panel.task.dialog_archived_title"),
                                    tr("panel.task.dialog_archived_empty"))
            return
        lines = []
        for t in archived[-20:]:
            name = t.get("title", "")
            due = (t.get("due_date", "") or "")[:10]
            lines.append(tr("panel.task.archive_line", name=name, due=due))
        QMessageBox.information(
            self, tr("panel.task.dialog_archived_recent_title"),
            "\n".join(lines) if lines else tr("panel.task.dialog_archived_none"))


def _align_header_item(table: QTableWidget, col: int) -> None:
    """表头**逐列**与正文对齐（标题列正文左对齐，表头也必须左对齐）。

    原来整个表头统一 `AlignCenter`，而标题列的正文是左对齐 → 表头与内容错位（A5）。
    """
    item = table.horizontalHeaderItem(col)
    if item is None:
        return
    item.setTextAlignment(
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if col == TITLE_COL else Qt.AlignmentFlag.AlignCenter)
