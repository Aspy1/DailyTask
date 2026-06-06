"""Task panel — table with filters, pagination, checkboxes, archive, notes."""

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCheckBox, QMenu, QMessageBox,
)
from PySide6.QtGui import QFont, QColor, QBrush

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors

PAGE_SIZE = 10

TIME_BUCKETS = [
    ("全部", None),
    ("今天", "today"),
    ("明天", "tomorrow"),
    ("本周", "this_week"),
    ("下周", "next_week"),
    ("本月", "this_month"),
    ("已过期", "overdue"),
    ("无截止日期", "no_date"),
]


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
    def __init__(self, dm: DataManager, parent=None):
        c = get_colors()
        super().__init__(parent)
        self._dm = dm
        self._page = 0
        self._selected_courses: set[str] = set()
        self._time_bucket: str | None = None
        self._highlight_ddl = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)
        bar_layout.setSpacing(8)

        title = QLabel("作业")
        title.setFont(QFont(self.font().family(), 13))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bar_layout.addWidget(title)

        bar_layout.addStretch()

        self._filter_btn = QPushButton("课程筛选 ")
        self._filter_btn.setStyleSheet(self._btn_qss())
        self._filter_btn.clicked.connect(self._show_course_filter)
        bar_layout.addWidget(self._filter_btn)

        self._time_btn = QPushButton("时间筛选 ")
        self._time_btn.setStyleSheet(self._btn_qss())
        self._time_btn.clicked.connect(self._show_time_filter)
        bar_layout.addWidget(self._time_btn)

        archive_btn = QPushButton("已归档")
        archive_btn.setStyleSheet(self._btn_qss())
        archive_btn.clicked.connect(self._show_archive)
        bar_layout.addWidget(archive_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(self._btn_qss())
        refresh_btn.clicked.connect(self._refresh)
        bar_layout.addWidget(refresh_btn)

        layout.addWidget(bar)

        # ── Table ────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setObjectName("taskTable")
        self._table.setHorizontalHeaderLabels(["课程", "截止时间", "事项", "完成"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 120)
        self._table.setColumnWidth(1, 170)
        self._table.setColumnWidth(3, 50)
        self._table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.horizontalHeader().setSectionsClickable(False)
        self._table.horizontalHeader().setSortIndicatorShown(False)
        layout.addWidget(self._table, stretch=1)

        # ── Footer ───────────────────────────────────────────
        footer = QWidget()
        footer.setObjectName("taskFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 4, 16, 4)

        self._count_label = QLabel()
        self._count_label.setObjectName("taskCount")
        fl.addWidget(self._count_label)
        fl.addStretch()

        for text, slot in [("< 上一页", self._prev_page), ("下一页 >", self._next_page)]:
            btn = QPushButton(text)
            btn.setStyleSheet(self._btn_qss())
            btn.clicked.connect(slot)
            fl.addWidget(btn)

        layout.addWidget(footer)
        self._refresh()

    def _btn_qss(self) -> str:
        c = get_colors()
        return """
            QPushButton { background-color: {c["btn_secondary_bg"]}; color: {c["fg_hint"]};
                border: 1px solid {c["border"]}; border-radius: 8px;
                padding: 4px 12px; font-size: 11px; }
            QPushButton:hover { background-color: {c["btn_secondary_hover"]}; color: {c["fg_secondary"]}; }
            QPushButton::menu-indicator { image: none; }
        """

    # ── Data ──────────────────────────────────────────────────

    def _get_filtered(self) -> list[dict]:
        tasks = self._dm.tasks.active
        if self._selected_courses:
            tasks = [t for t in tasks if (t.get("course_name", "") or "—") in self._selected_courses]
        if self._time_bucket is not None:
            tasks = [t for t in tasks if _match_time_bucket(t.get("due_date", ""), self._time_bucket)]
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
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
            QMenu::separator {{ height: 1px; background-color: {c['divider']}; margin: 4px 8px; }}
        """)

        all_action = menu.addAction("全部课程")
        all_action.setCheckable(True)
        all_action.setChecked(not self._selected_courses)
        all_action.triggered.connect(lambda: self._apply_course_filter(set()))

        menu.addSeparator()

        courses = self._course_set()
        for cn in courses:
            action = menu.addAction(cn)
            action.setCheckable(True)
            action.setChecked(cn in self._selected_courses)
            action.triggered.connect(lambda checked, c=cn: self._toggle_course(c))

        menu.exec(self._filter_btn.mapToGlobal(self._filter_btn.rect().bottomLeft()))

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
        self._filter_btn.setText("课程筛选 ")
        self._time_btn.setText("时间筛选 ")
        self._page = 0
        self._refresh()

    def filter_by_course(self, course_name: str) -> None:
        self._selected_courses = {course_name}
        self._page = 0
        self._filter_btn.setText(f"课程: {course_name} ")

    def _apply_course_filter(self, sel: set[str]) -> None:
        self._selected_courses = sel
        self._page = 0
        if sel:
            self._filter_btn.setText(f"课程 ({len(sel)}) ")
        else:
            self._filter_btn.setText("课程筛选 ")
        self._refresh()

    def _show_time_filter(self) -> None:
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        """)
        for label, key in TIME_BUCKETS:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == self._time_bucket)
            action.triggered.connect(lambda checked, k=key: self._apply_time_filter(k))
        menu.exec(self._time_btn.mapToGlobal(self._time_btn.rect().bottomLeft()))

    def _apply_time_filter(self, bucket: str | None) -> None:
        self._time_bucket = bucket
        self._page = 0
        if bucket:
            label = next((l for l, k in TIME_BUCKETS if k == bucket), bucket)
            self._time_btn.setText(f"时间: {label} ")
        else:
            self._time_btn.setText("时间筛选 ")
        self._refresh()

    def _refresh(self) -> None:
        self._table.setSortingEnabled(False)
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

        for i, t in enumerate(page_tasks):
            self._table.insertRow(i)

            course_name = t.get("course_name", "") or "" or "—"
            course_item = QTableWidgetItem(course_name)
            course_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            course_item.setToolTip(course_name)
            self._table.setItem(i, 0, course_item)

            due = t.get("due_date", "")
            due_display = due[:16].replace("T", " ") if due and due != "None" else "—"
            # Highlight DDL within 3 days — use QLabel for mixed-color text
            if self._highlight_ddl and due and due != "None":
                due_date = _parse_due(due)
                if due_date and due_date <= date.today() + timedelta(days=3):
                    days_left = (due_date - date.today()).days
                    c = get_colors()
                    lbl = QLabel()
                    lbl.setFont(self._table.font())
                    lbl.setTextFormat(Qt.TextFormat.RichText)
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    lbl.setFixedWidth(self._table.columnWidth(1))
                    lbl.setWordWrap(False)
                    lbl.setText(
                        f'<span style="color:#e74856;font-size:11px;">{due_display}</span>'
                        f' <span style="color:{c["fg_secondary"]};font-size:11px;">({days_left}天后)</span>'
                    )
                    lbl.setToolTip(due_display)
                    self._table.setCellWidget(i, 1, lbl)
                    # skip setItem below
                    title_item = QTableWidgetItem(t.get("title", ""))
                    title_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                    title_item.setToolTip(t.get("title", ""))
                    if t.get("status") == "completed":
                        title_item.setForeground(QBrush(QColor("#6e6e73")))
                    self._table.setItem(i, 2, title_item)
                    # Checkbox
                    cb = QCheckBox()
                    cb.setChecked(t.get("status") == "completed")
                    cb.setToolTip("标记完成" if t.get("status") != "completed" else "已完成的勾选仅作提示。右键可取消完成。")
                    tid = t["id"]
                    cb.toggled.connect(lambda checked, tid=tid: self._on_check(tid, checked))
                    self._table.setCellWidget(i, 3, cb)
                    continue
            due_item = QTableWidgetItem(due_display)
            due_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            due_item.setToolTip(due_display)
            self._table.setItem(i, 1, due_item)

            title_item = QTableWidgetItem(t.get("title", ""))
            title_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            title_item.setToolTip(t.get("title", ""))
            if t.get("status") == "completed":
                title_item.setForeground(QBrush(QColor("#6e6e73")))
            self._table.setItem(i, 2, title_item)

            # Checkbox
            cb = QCheckBox()
            cb.setChecked(t.get("status") == "completed")
            cb.setToolTip("标记完成" if t.get("status") != "completed" else "已完成的勾选仅作提示。右键可取消完成。")
            tid = t["id"]
            cb.toggled.connect(lambda checked, tid=tid: self._on_check(tid, checked))
            self._table.setCellWidget(i, 3, cb)

        self._table.setSortingEnabled(True)
        page_str = f"第{self._page + 1}/{max_page + 1}页" if total > PAGE_SIZE else ""
        self._count_label.setText(f"{total} 个任务  {page_str}")

    def _on_check(self, task_id: str, checked: bool) -> None:
        if checked:
            self._dm.tasks.complete(task_id)
        else:
            self._dm.tasks.uncomplete(task_id)
        self._dm.tasks.save()
        self._dm.data_changed.emit("task_status")

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
                border: 1px solid {c['border']}; border-radius: 8px; padding: 4px 12px; font-size: 11px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
            QPushButton::menu-indicator {{ image: none; }}
        """
        for btn in self.findChildren(QPushButton):
            try:
                # accent buttons heuristic
                txt = (btn.text() or "").strip()
                if txt in ("添加", "记一笔", "开始", "保存", "打开") or txt == "+":
                    btn.setStyleSheet(f"QPushButton {{ background-color: {c['accent']}; color: #fff; border: none; border-radius:6px; padding:4px 10px; font-weight:600; }}")
                else:
                    btn.setStyleSheet(btn_qss)
            except Exception:
                pass

        # table styling - let QSS do heavy lifting; ensure header/footer labels use fg_primary
        try:
            for lbl in self.findChildren(QLabel):
                if lbl.objectName() in ("taskCount",):
                    lbl.setStyleSheet(f"color: {c['fg_hint']}; font-size: 11px;")
        except Exception:
            pass

    def _show_archive(self) -> None:
        archived = self._dm.tasks.archived
        if not archived:
            QMessageBox.information(self, "已归档", "暂无已归档任务。")
            return
        lines = []
        for t in archived[-20:]:
            name = t.get("title", "")
            due = (t.get("due_date", "") or "")[:10]
            lines.append(f"  • {name}  (截止: {due})")
        QMessageBox.information(self, "已归档（最近20条）", "\n".join(lines) if lines else "无")
