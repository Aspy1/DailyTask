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
)

from src.models.course import PERIOD_TIMES
from src.ui.styles.theme import RADIUS, SIZE_BODY_S, SIZE_TINY, get_colors
from src.ui.widgets.menu import (
    add_action,
    add_separator,
    new_menu,
    show_at_cursor,
)

DAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# Right-click menu actions — extensible: just add a label
COURSE_ACTIONS = [
    "布置了作业",
    "发布了考试通知",
    "发布了复习通知",
    "调课 / 停课通知",
    "其他事项",
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


def build_course_context_menu(course: dict, parent=None) -> QMenu:
    """课程右键菜单（课程表与日程视图共用）。"""
    menu = new_menu(parent)
    course_id = course.get("id", "")

    add_action(menu, "修改课程名称", data=("rename", course_id))
    add_action(menu, "删除这门课", data=("delete", course_id))
    add_action(menu, "查看关于这门课的事项", data=("view_tasks", course.get("name", "")))

    add_separator(menu)

    for action_label in COURSE_ACTIONS:
        add_action(menu, action_label, data=("fill", action_label))

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
        labels = self._build_labels()

        super().__init__(self._period_count, 7, parent)
        self.setHorizontalHeaderLabels(DAY_LABELS)
        self.setVerticalHeaderLabels(labels)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verticalHeader().setMinimumWidth(64)

        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setShowGrid(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self._cell_courses: dict[tuple[int, int], dict] = {}
        self._chips: dict[tuple[int, int], _CourseChip] = {}
        self._last_courses: list[dict] = []
        self._last_week: int | None = None
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
                labels.append(f"第{i + 1}节")
        return labels

    @property
    def period_count(self) -> int:
        return self._period_count

    def refresh_theme(self) -> None:
        """切主题后重刷：样式表 + 课程块（块内颜色是写死的，必须重建）。"""
        self._apply_qss()
        self.set_courses(self._last_courses, self._last_week)

    # ── 数据 → 视图 ─────────────────────────────────────────

    def set_courses(self, courses: list[dict], week: int | None = None) -> None:
        self._last_courses, self._last_week = courses, week

        self.clearSpans()
        for chip in self._chips.values():
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        self._cell_courses.clear()
        self.clearContents()

        for course in courses:
            day = course.get("day_of_week", 1) - 1
            if day < 0 or day > 6:
                continue
            for slot in course.get("time_slots", []):
                location = slot.get("location", course.get("location", ""))
                start = slot["start"] - 1
                end = min(slot["end"], self._period_count)
                if start < 0 or start >= end:
                    continue
                self._place_course(start, end, day, course, location)

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
