"""Course schedule grid widget — time labels, context menu, signals."""

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
)
from PySide6.QtGui import QFont, QColor, QBrush, QAction

from src.models.course import PERIOD_TIMES
from src.ui.styles.theme import get_colors


DAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

COURSE_COLORS = [
    "#4a9eff", "#5cb8a5", "#c97d60", "#b896d6",
    "#7dae82", "#d69d6c", "#6ba8c7", "#c47d8f",
    "#5e9ec4", "#ae8bcf", "#6eaa78", "#c4a35e",
]

CELL_TEXT = "#ffffff"

# Right-click menu actions — extensible: just add a label
COURSE_ACTIONS = [
    "布置了作业",
    "发布了考试通知",
    "发布了复习通知",
    "调课 / 停课通知",
    "其他事项",
]


def build_course_context_menu(course: dict, parent=None) -> QMenu:
    """Create a standalone course context menu — usable from schedule view too."""
    from PySide6.QtWidgets import QMenu
    c = get_colors()
    menu = QMenu(parent)
    menu.setStyleSheet(f"""
        QMenu {{ background-color: {c['bg_surface_hi']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
        QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
        QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        QMenu::separator {{ height: 1px; background-color: {c['divider']}; margin: 4px 8px; }}
    """)
    course_id = course.get("id", "")
    menu.addAction("修改课程名称").setData(("rename", course_id))
    menu.addAction("删除这门课").setData(("delete", course_id))
    menu.addAction("查看关于这门课的事项").setData(("view_tasks", course.get("name", "")))
    menu.addSeparator()
    for action_label in COURSE_ACTIONS:
        menu.addAction(action_label).setData(("fill", action_label))
    return menu


def _build_context_prompt(course: dict, action: str) -> str:
    """Build a detailed AI prompt with course context and next class date."""
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
    week_str = ""
    if weeks:
        week_str = f"第{weeks.get('start','?')}-{weeks.get('end','?')}周"

    location = course.get("location", "")

    # Calculate next class date
    today = date.today()
    days_ahead = day - today.isoweekday()
    if days_ahead <= 0:
        days_ahead += 7
    next_date = today + timedelta(days=days_ahead)
    date_str = next_date.strftime("%Y-%m-%d")

    extras = [x for x in [day_str, time_str, week_str, location] if x]
    context = ""
    if extras:
        context = "（" + " / ".join(extras) + "）"

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

    def __init__(self, period_count: int = 5, parent=None):
        self._period_count = max(1, period_count)
        labels = self._build_labels()

        super().__init__(self._period_count, 7, parent)
        self.setHorizontalHeaderLabels(DAY_LABELS)
        self.setVerticalHeaderLabels(labels)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verticalHeader().setMinimumWidth(60)

        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setShowGrid(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        # Store course ref per cell for context lookups
        self._cell_courses: dict[tuple[int, int], dict] = {}

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

    def set_courses(self, courses: list[dict], week: int | None = None) -> None:
        self.clearContents()
        self._cell_courses.clear()
        for course in courses:
            day = course.get("day_of_week", 1) - 1
            if day < 0 or day > 6:
                continue
            for slot in course.get("time_slots", []):
                slot_loc = slot.get("location", course.get("location", ""))
                start = slot["start"] - 1
                end = min(slot["end"], self._period_count)
                for row in range(start, end):
                    key = (row, day)
                    existing = self.item(row, day)
                    if existing is not None:
                        existing.setText(
                            existing.text() + "\n" + self._format_cell(course, slot_loc, week)
                        )
                    else:
                        self._set_cell(row, day, course, slot_loc, week)
                    self._cell_courses[key] = course

    def _format_cell(self, course: dict, location: str, week: int | None = None) -> str:
        name = course.get("name", "")
        parts = [name]
        if location:
            parts.append(location)
        return "\n".join(parts)

    def _set_cell(self, row: int, col: int, course: dict, location: str, week: int | None = None) -> None:
        cid = course.get("id", course.get("name", ""))
        color_idx = hash(cid) % len(COURSE_COLORS)
        bg = COURSE_COLORS[color_idx]
        item = QTableWidgetItem(self._format_cell(course, location, week))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFont(QFont("Microsoft YaHei", 10))
        item.setBackground(QBrush(QColor(bg)))
        item.setForeground(QBrush(QColor(CELL_TEXT)))
        self.setItem(row, col, item)

    def _on_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None:
            return
        row, col = item.row(), item.column()
        course = self._cell_courses.get((row, col))
        if course is None:
            return
        course_id = course.get("id", "")

        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_surface_hi']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
            QMenu::separator {{ height: 1px; background-color: {c['divider']}; margin: 4px 8px; }}
        """)

        # Section 1: course management
        rename_action = menu.addAction("修改课程名称")
        rename_action.setData(("rename", course_id))
        delete_action = menu.addAction("删除这门课")
        delete_action.setData(("delete", course_id))
        view_tasks_action = menu.addAction("查看关于这门课的事项")
        view_tasks_action.setData(("view_tasks", course.get("name", "")))

        menu.addSeparator()

        # Section 2: task creation → fill AI prompt
        for action_label in COURSE_ACTIONS:
            action = menu.addAction(action_label)
            action.setData(("fill", action_label))

        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen is None or chosen.data() is None:
            return

        action_type, payload = chosen.data()
        if action_type == "rename":
            self.course_rename_requested.emit(course_id)
        elif action_type == "delete":
            self.course_delete_requested.emit(course_id)
        elif action_type == "view_tasks":
            self.view_course_tasks.emit(payload)
        elif action_type == "fill":
            prompt = _build_context_prompt(course, payload)
            self.fill_ai_prompt.emit(prompt)
