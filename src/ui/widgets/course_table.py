"""课程表渲染：去网格 + 课程块（圆角/色条/两行）+ 今天列高亮 + 时段列降噪。

改造依据（2026-10-16 视觉审查）：
- 原来每个单元格都画 1px 边框 → 24 个格子变成 Excel；现在不画网格，只用极淡的
  横向分隔与"时段列底色"区分结构
- 原来课程只是"居中文本"，没有实体感；现在每节课是一个圆角块（左侧 3px 色条 +
  课程名 + 地点），连排多节次合并成一个块（`setSpan`）
- 表头降为 11px 常规字重；"今天"那一列用强调色
- 颜色索引改用 `crc32`：原来用 `hash()`，进程间随机化会导致**每次启动课程颜色都变**
"""

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QMenu,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.models.course import PERIOD_TIMES
from src.models.course_rules import slots_of
from src.ui.styles.theme import RADIUS, SIZE_BODY_S, SIZE_TINY, get_colors
from src.ui.widgets.menu import (
    add_action,
    add_separator,
    new_menu,
    show_at_cursor,
)

DAY_LABELS = [tr("day.monday"), tr("day.tuesday"), tr("day.wednesday"),
              tr("day.thursday"), tr("day.friday"), tr("day.saturday"), tr("day.sunday")]

# Right-click menu actions — extensible: just add a label
# 这些中文是**内部动作标识**（`data=("fill", label)` 与 AI prompt 都依赖它），保持原文。
COURSE_ACTIONS = [
    "布置了作业",
    "发布了考试通知",
    "发布了复习通知",
    "调课 / 停课通知",
    "其他事项",
]

# 与 COURSE_ACTIONS 一一对应的**显示文案**键（顺序必须保持一致）
_COURSE_ACTION_KEYS = [
    "widget.course_table.action_homework",
    "widget.course_table.action_exam_notice",
    "widget.course_table.action_review_notice",
    "widget.course_table.action_schedule_change",
    "widget.course_table.action_other",
]


def _rgba(color: str, alpha: float | None = None) -> QColor:
    """token 的 `rgba(r,g,b,a)` / `#rrggbb` → QColor（可覆盖 alpha）。"""
    m = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", color)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        a = float(m.group(4)) if alpha is None else alpha
        return QColor(r, g, b, int(a * 255))
    if color.startswith("#"):
        h = color[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        c = QColor(f"#{h}")
        if alpha is not None:
            c.setAlpha(int(alpha * 255))
        return c
    return QColor(color)


class _CourseChip(QFrame):
    """一节课的视觉块：圆角 + 左侧色条 + 课程名/地点两行。

    `reminder` 是给"作业截止 / 会点名"这类备注预留的槽位（数据模型待定，见 PLAN F-7）。
    """

    def __init__(self, course: dict, location: str, reminder: dict | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("courseChip")

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(40)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        body = QVBoxLayout(self)
        body.setContentsMargins(10, 7, 10, 7)
        body.setSpacing(2)

        self._name = QLabel(course.get("name", ""))
        self._name.setWordWrap(True)
        body.addWidget(self._name)

        self._loc = QLabel(location or "")
        self._loc.setWordWrap(True)
        body.addWidget(self._loc)

        self._reminder = QLabel("")
        self._reminder.setWordWrap(True)
        body.addWidget(self._reminder)

        body.addStretch()

        self.set_reminder(reminder)
        self.refresh_theme()

    def set_reminder(self, reminder: dict | None) -> None:
        """块上的提醒徽章（如「作业截止」「会点名」）；无则隐藏。"""
        text = (reminder or {}).get("text", "")
        self._reminder.setText(f"⚑ {text}" if text else "")
        self._reminder.setVisible(bool(text))

    def refresh_theme(self) -> None:
        c = get_colors()
        # 中性块：底 bg_surface + 细描边；不再逐课配色（用户要求"不用多余颜色"）
        self.setStyleSheet(
            f"#courseChip {{ background-color: {c['bg_surface']};"
            f" border: 1px solid {c['border']};"
            f" border-radius: {RADIUS['radius_md']}px; }}")
        self._name.setStyleSheet(
            f"color: {c['fg_primary']}; font-size: {SIZE_BODY_S}px; font-weight: 600;"
            f" background: transparent;")
        self._loc.setStyleSheet(
            f"color: {c['fg_secondary']}; font-size: {SIZE_TINY}px; background: transparent;")
        self._reminder.setStyleSheet(
            f"color: {c['accent_text']}; font-size: {SIZE_TINY}px; font-weight: 600;"
            f" background: transparent;")


class _ConflictChip(QFrame):
    """同一时段有两门课：一块里把两门都列出来。

    为什么需要：原来 `setCellWidget` 直接放块，**同一格的第二门课会覆盖第一门** ——
    选修/重修撞课时，课表看起来"只有一门课"，用户不知道要请假。
    """

    def __init__(self, courses: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("courseConflictChip")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(40)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._courses = courses

        body = QVBoxLayout(self)
        body.setContentsMargins(10, 7, 10, 7)
        body.setSpacing(2)

        self._header = QLabel(tr("widget.course_table.conflict_header"))
        self._header.setWordWrap(True)
        body.addWidget(self._header)

        self._names: list[QLabel] = []
        for course in courses:
            label = QLabel(course.get("name", ""))
            label.setWordWrap(True)
            body.addWidget(label)
            self._names.append(label)
        body.addStretch()
        self.refresh_theme()

    @property
    def courses(self) -> list[dict]:
        return self._courses

    def refresh_theme(self) -> None:
        c = get_colors()
        self.setStyleSheet(
            f"#courseConflictChip {{ background-color: {c['accent_bg']};"
            f" border: 1px solid {c['accent']};"
            f" border-radius: {RADIUS['radius_md']}px; }}")
        self._header.setStyleSheet(
            f"color: {c['accent_text']}; font-size: {SIZE_TINY}px; font-weight: 600;"
            f" background: transparent;")
        for label in self._names:
            label.setStyleSheet(
                f"color: {c['fg_primary']}; font-size: {SIZE_BODY_S}px; font-weight: 600;"
                f" background: transparent;")


def build_conflict_menu(courses: list[dict], parent=None) -> QMenu:
    """冲突块的右键菜单：逐门课提供"查看事项"（重命名/删除请走非冲突处的课程块）。"""
    menu = new_menu(parent)
    header = add_action(menu, tr("widget.course_table.conflict_header"))
    header.setEnabled(False)
    add_separator(menu)
    for course in courses:
        add_action(menu, tr("widget.course_table.menu_view_tasks"),
                   data=("view_tasks", course.get("name", "")))
    return menu


def build_course_context_menu(course: dict, parent=None) -> QMenu:
    """课程右键菜单（课程表与日程视图共用）。"""
    menu = new_menu(parent)
    course_id = course.get("id", "")

    add_action(menu, tr("widget.course_table.menu_rename"), data=("rename", course_id))
    add_action(menu, tr("widget.course_table.menu_delete"), data=("delete", course_id))
    add_action(menu, tr("widget.course_table.menu_view_tasks"),
               data=("view_tasks", course.get("name", "")))

    add_separator(menu)

    for action_label, key in zip(COURSE_ACTIONS, _COURSE_ACTION_KEYS, strict=True):
        add_action(menu, tr(key), data=("fill", action_label))

    return menu


def _build_context_prompt(course: dict, action: str) -> str:
    """Build a detailed AI prompt with course context and next class date."""
    from datetime import date, timedelta

    name = course.get("name", "未知课程")
    day = course.get("day_of_week", 0)
    day_names = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    day_str = day_names[day] if 0 < day <= 7 else ""

    slots = course.get("time_slots", [])
    time_str = ""
    if slots and slots[0]["start"] - 1 < len(PERIOD_TIMES):
        start_t = PERIOD_TIMES[slots[0]["start"] - 1][0]
        last_end = max(s["end"] for s in slots) - 1
        end_t = PERIOD_TIMES[min(last_end, len(PERIOD_TIMES) - 1)][1]
        time_str = f"{start_t}-{end_t}"

    weeks = course.get("weeks", {})
    week_str = f"第{weeks.get('start','?')}-{weeks.get('end','?')}周" if weeks else ""
    location = course.get("location", "")

    today = date.today()
    days_ahead = day - today.isoweekday()
    if days_ahead <= 0:
        days_ahead += 7
    date_str = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    extras = [x for x in [day_str, time_str, week_str, location] if x]
    context = "（" + " / ".join(extras) + "）" if extras else ""

    return (
        f"今天是{today.strftime('%Y-%m-%d')}。"
        f"在《{name}》{context}这门课上，{action}。"
        f"下次上课是{date_str}（{day_str}）。"
        f"请帮我把这件事加入日程（课程名={name}）："
    )


class CourseTable(QTableWidget):
    """Course grid. Emits signals for context menu actions."""

    fill_ai_prompt = Signal(str)
    course_rename_requested = Signal(str)
    course_delete_requested = Signal(str)
    view_course_tasks = Signal(str)  # course_name

    def __init__(self, period_count: int = 5, parent=None) -> None:
        self._period_count = max(1, period_count)
        self._marker_row = self._period_count      # 末行：当日事项（DDL / 考试 / 计划）
        labels = [*self._build_labels(), tr("widget.course_table.row_items")]

        super().__init__(self._period_count + 1, 7, parent)
        self.setHorizontalHeaderLabels(DAY_LABELS)
        self.setVerticalHeaderLabels(labels)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # 事项行按内容自适应高度（其它行均分）
        self.verticalHeader().setSectionResizeMode(
            self._marker_row, QHeaderView.ResizeMode.ResizeToContents)
        self.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verticalHeader().setMinimumWidth(64)

        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setShowGrid(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self._cell_courses: dict[tuple[int, int], dict] = {}
        self._chips: dict[tuple[int, int], QWidget] = {}
        self._marker_labels: dict[int, QLabel] = {}
        self._last_courses: list[dict] = []
        self._last_week: int | None = None
        self._last_markers: dict[int, list[str]] = {}
        self._last_conflicts: dict[tuple[int, int], list[dict]] = {}
        self._apply_qss()

    # ── 样式 ────────────────────────────────────────────────

    def _apply_qss(self) -> None:
        """表格样式（切主题时重跑）。无网格线，只留极淡的横向分隔。"""
        c = get_colors()
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {c['bg_root']};
                border: none;
                gridline-color: transparent;
            }}
            QTableWidget::item {{
                padding: 0;
                border: none;
                border-bottom: 1px solid {c['divider']};
            }}
            QHeaderView::section {{
                background-color: {c['bg_root']};
                color: {c['fg_hint']};
                border: none;
                border-bottom: 1px solid {c['divider']};
                padding: 8px 4px;
                font-size: {SIZE_TINY}px;
                font-weight: 500;
            }}
            QHeaderView::section:vertical {{
                background-color: {c['bg_surface']};
                color: {c['fg_secondary']};
                border: none;
                border-right: 1px solid {c['divider']};
                border-bottom: 1px solid {c['divider']};
                padding: 4px;
                font-size: {SIZE_TINY}px;
                font-weight: 400;
            }}
        """)
        self._highlight_today_header()

    def _highlight_today_header(self) -> None:
        """「今天」那一列的表头用强调色 + 浅底。"""
        from datetime import date

        c = get_colors()
        today_col = date.today().isoweekday() - 1
        for col in range(7):
            item = self.horizontalHeaderItem(col)
            if item is None:
                continue
            font = item.font()
            if col == today_col:
                item.setForeground(QColor(c["accent_text"]))
                item.setBackground(_rgba(c["accent_bg"]))
                font.setBold(True)
            else:
                item.setForeground(QColor(c["fg_hint"]))
                item.setBackground(QColor(Qt.GlobalColor.transparent))
                font.setBold(False)
            item.setFont(font)

    def _build_labels(self) -> list[str]:
        labels = []
        for i in range(self._period_count):
            if i < len(PERIOD_TIMES):
                start, end = PERIOD_TIMES[i]
                labels.append(f"{start}\n{end}")
            else:
                labels.append(tr("widget.course_table.period_nth", n=i + 1))
        return labels

    @property
    def period_count(self) -> int:
        return self._period_count

    def refresh_theme(self) -> None:
        """切主题后重刷：样式表 + 课程块（块内颜色是写死的，必须重建）。"""
        self._apply_qss()
        self.set_courses(self._last_courses, self._last_week,
                         self._last_markers, self._last_conflicts)

    # ── 数据 → 视图 ─────────────────────────────────────────

    def set_courses(self, courses: list[dict], week: int | None = None,
                    markers: dict[int, list[str]] | None = None,
                    conflicts: dict[tuple[int, int], list[dict]] | None = None) -> None:
        """`markers`：`{isoweekday(1-7): [文案, ...]}` —— 当天的事项（DDL/考试/计划）。
        `conflicts`：`{(day_of_week, 节次): [课程, ...]}` —— 同一时段两门课的格子。
        """
        self._last_courses, self._last_week = courses, week
        self._last_markers = markers or {}
        self._last_conflicts = conflicts or {}

        self._clear_cells()
        self._place_all(courses)
        self._render_markers()

    def _clear_cells(self) -> None:
        self.clearSpans()
        for chip in self._chips.values():
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        self._cell_courses.clear()
        self.clearContents()

    def _place_all(self, courses: list[dict]) -> None:
        """逐门课放块；冲突格只画一次（一个块里列出两门课）。"""
        drawn: set[tuple[int, int]] = set()
        for course in courses:
            day = course.get("day_of_week", 1) - 1
            if day < 0 or day > 6:
                continue
            for slot in course.get("time_slots", []):
                start = slot["start"] - 1
                end = min(slot["end"], self._period_count)
                if start < 0 or start >= end:
                    continue
                cell = (course.get("day_of_week", 1), slot["start"])
                if cell in self._last_conflicts:
                    if cell in drawn:
                        continue
                    drawn.add(cell)
                    self._place_conflict(day, self._last_conflicts[cell])
                    continue
                location = slot.get("location", course.get("location", ""))
                self._place_course(start, end, day, course, location)

    def _place_conflict(self, col: int, courses: list[dict]) -> None:
        """冲突格：按两门课合起来的节次范围放一个"列出两门课"的块。"""
        rows = [slot for course in courses for slot in slots_of(course)]
        start = max(0, (min(rows) if rows else 1) - 1)
        end = min(self._period_count, max(rows) if rows else 1)
        if start >= end:
            end = start + 1
        if end - start > 1:
            self.setSpan(start, col, end - start, 1)

        chip = _ConflictChip(courses, self)
        chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        chip.customContextMenuRequested.connect(
            lambda pos, c=chip: self._show_conflict_menu(c))
        self.setCellWidget(start, col, chip)
        self._chips[(start, col)] = chip

        item = QTableWidgetItem("")
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.setItem(start, col, item)
        for row in range(start, end):
            self._cell_courses.setdefault((row, col), courses[0])

    def _show_conflict_menu(self, chip: _ConflictChip) -> None:
        menu = build_conflict_menu(chip.courses, self)
        chosen = show_at_cursor(menu)
        if chosen is None or chosen.data() is None:
            return
        action_type, payload = chosen.data()
        if action_type == "view_tasks":
            self.view_course_tasks.emit(payload)

    def _render_markers(self) -> None:
        """末行列出当天事项。

        为什么要它：周视图只有课程块时，**没课的日子一片空白** —— 用户会以为
        "这周什么都没有"，而实际上有作业截止、考试、日程计划。这里把它们列出来。
        """
        c = get_colors()
        for label in self._marker_labels.values():
            label.setParent(None)
            label.deleteLater()
        self._marker_labels.clear()

        markers = self._last_markers
        self.setRowHidden(self._marker_row, not any(markers.values()))
        for col in range(7):
            items = markers.get(col + 1, [])
            if not items:
                self.removeCellWidget(self._marker_row, col)
                continue
            label = QLabel("\n".join(items))
            label.setWordWrap(True)
            label.setContentsMargins(8, 6, 8, 6)
            label.setStyleSheet(
                f"color: {c['fg_secondary']}; font-size: {SIZE_TINY}px;"
                f" background: transparent;")
            self.setCellWidget(self._marker_row, col, label)
            self._marker_labels[col] = label

    def _place_course(self, start: int, end: int, col: int, course: dict,
                      location: str) -> None:
        """连排多节次合并成一个块（`setSpan`），而不是每格重复一遍。"""
        span = end - start
        if span > 1:
            self.setSpan(start, col, span, 1)

        chip = _CourseChip(course, location, course.get("reminder"), self)
        chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        chip.customContextMenuRequested.connect(
            lambda pos, c=chip: self._open_menu_at(c.mapTo(self.viewport(), pos)))
        self.setCellWidget(start, col, chip)
        self._chips[(start, col)] = chip

        item = QTableWidgetItem("")            # 占位：让 indexAt() 在 cellWidget 之下仍可用
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.setItem(start, col, item)
        for row in range(start, end):
            self._cell_courses[(row, col)] = course

    # ── 右键 ────────────────────────────────────────────────

    def _on_context_menu(self, pos) -> None:
        self._open_menu_at(pos)

    def _open_menu_at(self, pos) -> None:
        index = self.indexAt(pos)
        if not index.isValid():
            return
        course = self._cell_courses.get((index.row(), index.column()))
        if course is None:
            return

        menu = build_course_context_menu(course, self)
        chosen = show_at_cursor(menu)
        if chosen is None or chosen.data() is None:
            return

        action_type, payload = chosen.data()
        course_id = course.get("id", "")
        if action_type == "rename":
            self.course_rename_requested.emit(course_id)
        elif action_type == "delete":
            self.course_delete_requested.emit(course_id)
        elif action_type == "view_tasks":
            self.view_course_tasks.emit(payload)
        elif action_type == "fill":
            self.fill_ai_prompt.emit(_build_context_prompt(course, payload))
