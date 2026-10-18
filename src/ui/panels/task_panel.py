"""Task panel — table with filters, pagination, checkboxes, archive, notes."""

import logging
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.styles.theme import SIZE_SUBTITLE, font, get_colors
from src.ui.widgets.menu import (
    add_action,
    add_separator,
    new_menu,
    show_below,
)
from src.ui.widgets.rounded_button import RoundedButton

PAGE_SIZE = 10

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
        c = get_colors()
        super().__init__(parent)
        self._dm = dm
        self._page = 0
        self._selected_courses: set[str] = set()
        self._time_bucket: str | None = None
        self._highlight_ddl = False
        self._status_filter = "pending"  # "pending" | "completed" | "all"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)
        bar_layout.setSpacing(8)

        title = QLabel(tr("panel.task.heading"))
        title.setFont(font(SIZE_SUBTITLE))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bar_layout.addWidget(title)

        bar_layout.addStretch()

        self._filter_btn = RoundedButton(tr("panel.task.btn_course_filter"))
        self._filter_btn.setStyleSheet(self._btn_qss())
        self._filter_btn.clicked.connect(self._show_course_filter)
        bar_layout.addWidget(self._filter_btn)

        self._time_btn = RoundedButton(tr("panel.task.btn_time_filter"))
        self._time_btn.setStyleSheet(self._btn_qss())
        self._time_btn.clicked.connect(self._show_time_filter)
        bar_layout.addWidget(self._time_btn)

        self._status_btn = RoundedButton(tr("panel.task.status_pending"))
        self._status_btn.setStyleSheet(self._btn_qss())
        self._status_btn.clicked.connect(self._toggle_status_filter)
        bar_layout.addWidget(self._status_btn)

        refresh_btn = RoundedButton(tr("panel.task.btn_refresh"))
        refresh_btn.setStyleSheet(self._btn_qss())
        refresh_btn.clicked.connect(self._refresh)
        bar_layout.addWidget(refresh_btn)

        layout.addWidget(bar)

        # ── Table ────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setObjectName("taskTable")
        self._table.setHorizontalHeaderLabels([
            tr("panel.task.col_course"), tr("panel.task.col_due"),
            tr("panel.task.col_title"), tr("panel.task.col_done"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 120)
        self._table.setColumnWidth(1, 175)
        self._table.setColumnWidth(3, 50)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setSortingEnabled(False)
        self._table.horizontalHeader().setSortIndicatorShown(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(48)  # tall rows for red text
        self._table.verticalHeader().setMinimumSectionSize(40)
        self._table.setWordWrap(True)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.horizontalHeader().setSortIndicatorShown(False)
        self._table.horizontalHeader().setSectionsClickable(False)
        self._table.horizontalHeader().setSortIndicatorShown(False)
        layout.addWidget(self._table, stretch=1)

        # ── Footer ───────────────────────────────────────────
        footer = QWidget()
        footer.setObjectName("taskFooter")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 4, 16, 4)

        self._count_label = QLabel()
        self._count_label.setObjectName("taskCount")
        fl.addWidget(self._count_label)
        fl.addStretch()

        for text, slot in [(tr("panel.task.btn_prev_page"), self._prev_page),
                           (tr("panel.task.btn_next_page"), self._next_page)]:
            btn = RoundedButton(text)
            btn.setStyleSheet(self._btn_qss())
            btn.clicked.connect(slot)
            fl.addWidget(btn)

        layout.addWidget(footer)
        self._refresh()

    def _btn_qss(self) -> str:
        c = get_colors()
        return f"""
            QPushButton {{ background-color: {c["btn_secondary_bg"]}; color: {c["fg_hint"]};
                border-radius: 8px;
                padding: 4px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c["btn_secondary_hover"]}; color: {c["fg_secondary"]}; }}
            QPushButton::menu-indicator {{ image: none; }}
        """

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

    def _refresh(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.horizontalHeader().setSortIndicatorShown(False)
        self._table.setRowCount(0)

        tasks = self._get_filtered()
        total = len(tasks)
        start = self._page * PAGE_SIZE
        page_tasks = tasks[start:start + PAGE_SIZE]
        max_page = max(0, (total - 1) // PAGE_SIZE)
        if self._page > max_page:
            self._page = max_page
            start = self._page * PAGE_SIZE
            page_tasks = tasks[start:start + PAGE_SIZE]

        c = get_colors()
        for i, t in enumerate(page_tasks):
            self._table.insertRow(i)

            self._set_course_item(i, t)

            due = t.get("due_date", "")
            due_display = due[:16].replace("T", " ") if due and due != "None" else "—"
            # Highlight DDL within 3 days — use QLabel for mixed-color text
            if self._is_near_ddl(due):
                due_date = _parse_due(due)
                self._table.setCellWidget(
                    i, 1, self._make_ddl_cell(
                        due_display, (due_date - date.today()).days, c))
            else:
                self._set_due_item(i, due_display)

            title_item = QTableWidgetItem(t.get("title", ""))
            title_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if t.get("status") == "completed":
                title_item.setForeground(QBrush(QColor(c['fg_hint'])))
            self._table.setItem(i, 2, title_item)

            self._set_check_cell(i, t)

        self._table.setSortingEnabled(True)
        page_str = (tr("panel.task.page_info", page=self._page + 1, total=max_page + 1)
                    if total > PAGE_SIZE else "")
        self._count_label.setText(tr("panel.task.count", total=total, page=page_str))

    def _set_course_item(self, row: int, t: dict) -> None:
        """第 0 列：课程名。"""
        course_item = QTableWidgetItem(t.get("course_name", "") or "—")
        course_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 0, course_item)

    def _is_near_ddl(self, due: str) -> bool:
        """是否需要按 DDL 临期（3 天内）高亮截止列。"""
        if not (self._highlight_ddl and due and due != "None"):
            return False
        due_date = _parse_due(due)
        return bool(due_date and due_date <= date.today() + timedelta(days=3))

    def _set_check_cell(self, row: int, t: dict) -> None:
        """第 3 列：完成复选框。"""
        cb = QCheckBox()
        cb.setChecked(t.get("status") == "completed")
        tid = t["id"]
        cb.clicked.connect(lambda checked, tid=tid: self._on_check(tid, checked))
        self._table.setCellWidget(row, 3, cb)

    def _make_ddl_cell(self, due_display: str, days_left: int, c: dict) -> QLabel:
        """DDL 临期（3 天内）的富文本单元格。"""
        lbl = QLabel()
        lbl.setFont(self._table.font())
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setMinimumWidth(self._table.columnWidth(1) - 10)
        lbl.setWordWrap(False)
        lbl.setText(
            f'<span style="color:{c["red"]};font-size: 13px;">{due_display}</span>'
            f' <span style="color:{c["fg_secondary"]};font-size: 13px;">'
            f'{tr("panel.task.days_left", days=days_left)}</span>'
        )
        return lbl

    def _set_due_item(self, row: int, due_display: str) -> None:
        """普通截止日期单元格。"""
        due_item = QTableWidgetItem(due_display)
        due_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 1, due_item)

    def _on_check(self, task_id: str, checked: bool) -> None:
        if checked:
            self._dm.tasks.complete(task_id)
        else:
            self._dm.tasks.uncomplete(task_id)
        self._dm.tasks.save()
        self._dm.data_changed.emit("task_status")
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
        c = get_colors()
        # rebuild button qss based on colors
        btn_qss = f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: 1px solid {c['border']}; border-radius: 8px; padding: 4px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
            QPushButton::menu-indicator {{ image: none; }}
        """
        for btn in self.findChildren(QPushButton):
            try:
                # 本面板没有"主按钮"：全部走次级样式（此前这里按按钮文案判断强调色，
                # 而列表里的文案一个都匹配不上 —— 是死代码，已删）
                btn.setStyleSheet(btn_qss)
            except Exception:
                logger.debug("TaskPanel.refresh_theme 中忽略异常", exc_info=True)

        # table styling - let QSS do heavy lifting; ensure header/footer labels use fg_primary
        try:
            for lbl in self.findChildren(QLabel):
                if lbl.objectName() in ("taskCount",):
                    lbl.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px;")
        except Exception:
            logger.debug("TaskPanel.refresh_theme 中忽略异常", exc_info=True)

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
