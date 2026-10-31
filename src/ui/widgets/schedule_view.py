"""Daily schedule view — courses, plans, habits by time slot with right-click menu."""

import logging
import os as _os
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.models.course import PERIOD_TIMES, schedule_date
from src.services.data_manager import DataManager
from src.ui.components.click_label import ClickLabel
from src.ui.panels.course_panel import CoursePanel
from src.ui.styles.cards import card
from src.ui.styles.theme import (
    LAYOUT,
    SIZE_BODY_L,
    SIZE_BODY_M,
    SIZE_BODY_S,
    SIZE_CAPTION,
    font,
    get_colors,
)
from src.ui.widgets.hint_bar import HintBar
from src.ui.widgets.menu import (
    add_action,
    add_separator,
    new_menu,
    show_at_cursor,
)
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.schedule_actions import plans_snapshot, set_plan_category, undo_arrange
from src.ui.widgets.schedule_filter import CategoryFilter, add_category_actions, visible
from src.ui.widgets.schedule_slots import (
    add_course_to_slots,
    add_habit_to_slots,
    add_plan_to_slots,
    slot_for_minutes,
)

logger = logging.getLogger(__name__)


def slot_content_hash(items: list[dict], ddls: list[dict], is_current: bool) -> str:
    """时段内容指纹，用于增量刷新时跳过未变的卡片。

    ⚠ 完成状态（`done`）必须参与指纹：不参与时打卡后卡片不会重建，
    显示仍是 ○ / 未划线 —— 这是 hash 增量刷新的经典漏项。
    """
    import hashlib
    import json

    content_key = json.dumps({
        'items': [{'t': i['type'], 'n': i.get('name', '') or i.get('title', ''),
                   'nt': i.get('note', ''), 'd': i.get('duration', 0),
                   'l': i.get('location', ''), 'rt': i.get('reminder_time', ''),
                   'pt': i.get('plan_type', ''), 'cn': i.get('course_name', ''),
                   'done': bool(i.get('done'))}
                  for i in items],
        'ddls': [{'t': d.get('title', ''), 'd': d.get('due_date', '')[:16]} for d in ddls],
        'cur': is_current,
    }, sort_keys=True).encode()
    return hashlib.md5(content_key, usedforsecurity=False).hexdigest()


def slot_layout_index(slot_cards: dict, period: int) -> int:
    """时段卡片在布局里的**位置**：比它小的 period 有几张，就插第几位。

    为什么要这个（审查 R5）：`_refresh_day` 是 hash 增量刷新（未变的时段跳过重建），
    但重建的卡片原来一律 `insertWidget(count - 1)` = 插到**末尾** —— 切分类筛选只改变
    一部分时段，于是那几张跑到时间轴后面去（实测 `[1,2,3,4,5]` 变 `[2,3,4,5,1]`）。
    布局里除卡片只有末尾那个 stretch，所以"比它小的有几张"就是它的正确位置。

    放**模块级**而不是类方法：`ScheduleView` 已顶到类的尺寸上限（基线只允许减少），
    塞进去会直接红；而 `_refresh_day` 内联又会把它的圈复杂度推到 C（门禁 ≤ B）。
    """
    return sum(1 for p in slot_cards if p < period)


def secondary_button(text: str, c: dict, slot=None) -> "RoundedButton":
    """次级按钮（刷新 / 上一天 / 今天 / 下一天）：统一的次级配色与圆角。

    放**模块级**是为了给类减负：`ScheduleView` 已顶到类的尺寸基线（只允许减少），
    而这四处的样式块本来是一字不差抄了四遍（审查 R6 顺手收掉）。
    """
    btn = RoundedButton(text)
    btn.setStyleSheet(f"""
        QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
            border-radius: 8px; padding: 3px 10px; font-size: {SIZE_BODY_S}px; }}
        QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
    """)
    if slot is not None:
        btn.clicked.connect(slot)
    return btn


class ScheduleView(QWidget):
    course_table_requested = Signal()
    task_focus_requested = Signal(str)
    quick_adjust_requested = Signal(str)  # AI prompt for schedule optimization
    arrange_requested = Signal(str)       # Quick-arrange: snapshot prompt → AI service
    fill_ai_prompt = Signal(str)          # 课程右键"布置了作业" → 填充 AI 输入框

    # 快速安排的撤销快照：只记 `plans`（撤销不该连带回滚 `logs`/`reminders`，审查 #3）。
    # 放**类级**而不是 `__init__`：`__init__` 是 SIZE 存量项，门禁只防新增/加重
    _arrange_before: dict | None = None   # 安排前
    _arrange_after: dict | None = None    # 安排后（校验期间没被改过）
    _arrange_scope: tuple[str, ...] = ()  # 本次安排覆盖的日期（撤销只回滚这些天）

    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._day_offset = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        c = get_colors()

        # Toolbar
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 两行工具栏（审查 R6）：窄窗口（990×638 且展开 AI）下 11 个控件挤一行会**互相重叠**、
        # 日期被截断 —— 把"分类筛选 + 日期导航"分到第二行，两行各自留最小内容宽度。
        bar_box = QVBoxLayout(bar)
        bar_box.setContentsMargins(16, 8, 16, 8)
        bar_box.setSpacing(6)
        bl = QHBoxLayout()
        bl.setSpacing(6)
        bl2 = QHBoxLayout()
        bl2.setSpacing(6)
        bar_box.addLayout(bl)
        bar_box.addLayout(bl2)

        title = QLabel(tr("widget.schedule.title"))
        title.setFont(font("pageTitle"))
        title.setStyleSheet("font-weight: 600; border: none;")
        bl.addWidget(title)

        # 日 / 周 切换（合并 B：课程表并入日程，不再是独立导航项）
        self._view_mode = "day"
        self._mode_day = RoundedButton(tr("widget.schedule.mode_day"))
        self._mode_week = RoundedButton(tr("widget.schedule.mode_week"))
        for btn, mode in ((self._mode_day, "day"), (self._mode_week, "week")):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedWidth(LAYOUT["view_mode_width"])
            btn.clicked.connect(lambda checked=False, m=mode: self._set_mode(m))
            bl.addWidget(btn)

        bl.addStretch()

        self._build_action_row(bl, c)
        # 分类筛选挪到第二行（与日期导航同属"浏览"类，和"操作"类分开 —— 审查 R6）
        bl.removeWidget(self._category_filter)
        bl2.insertWidget(0, self._category_filter)
        bl2.addStretch()

        refresh_btn = secondary_button(tr("widget.schedule.btn_refresh"), c, self._refresh)
        bl.addWidget(refresh_btn)
        self._refresh_btn = refresh_btn

        # Quick arrange button
        self._arrange_btn = RoundedButton(tr("widget.schedule.btn_quick_arrange"))
        self._arrange_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']};
                border-radius: 8px; padding: 3px 14px; font-size: {SIZE_BODY_S}px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        self._arrange_btn.clicked.connect(self._quick_arrange)
        bl.addWidget(self._arrange_btn)

        self._nav_buttons = []
        for text, slot in [(tr("widget.schedule.btn_prev_day"), self._prev_day),
                           (tr("widget.schedule.btn_today"), self._go_today),
                           (tr("widget.schedule.btn_next_day"), self._next_day)]:
            btn = secondary_button(text, c, slot)
            bl2.addWidget(btn)
            self._nav_buttons.append(btn)

        self._date_label = QLabel()
        self._date_label.setStyleSheet(f"color: {c['fg_secondary']}; font-size: {SIZE_BODY_S}px; min-width: 100px;")
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl2.addWidget(self._date_label)

        layout.addWidget(bar)

        self._hint_bar = HintBar(self._dm.data_dir, data_manager=self._dm)
        layout.addWidget(self._hint_bar)

        # 日 / 周 两页：日 = 时段卡片；周 = 课程表（含"事项行"）
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 8, 16, 16)
        self._content_layout.setSpacing(12)
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        self._stack.addWidget(scroll)                     # 0：日

        self._course_panel = CoursePanel(dm)              # 周视图复用课程表面板
        self._stack.addWidget(self._course_panel)         # 1：周

        self._style_mode_buttons()
        self._refresh()

    # ── 日 / 周 切换 ────────────────────────────────────────

    def _set_mode(self, mode: str) -> None:
        """切到日视图或周视图。

        周视图 = `CoursePanel`（课程块 + 本周的 DDL/考试/计划"事项行"），
        解决"没课的日子一片空白，看着像这周什么都没有"。
        """
        self._view_mode = mode
        day = mode == "day"
        self._stack.setCurrentIndex(0 if day else 1)
        for widget in (*self._nav_buttons, self._arrange_btn, self._date_label,
                       self._refresh_btn):
            widget.setVisible(day)
        self._style_mode_buttons()
        if day:
            self._refresh()
        else:
            self._course_panel._refresh()
            self.course_table_requested.emit()

    def _build_action_row(self, bl, c: dict) -> None:
        for name, key, tone, slot in (("_undo_btn", "btn_undo", "danger", self._undo_arrange),
                                      ("_save_btn", "btn_save", "success", self._save_arrange)):
            btn = RoundedButton(tr(f"widget.schedule.{key}"))
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {c[f'btn_{tone}_bg']};"
                f" color: {c[f'btn_{tone}_fg']}; border: 1px solid {c[f'btn_{tone}_border']};"
                f" border-radius: 8px; padding: 3px 10px; font-size: {SIZE_BODY_S}px; font-weight: 600; }}"
                f" QPushButton:hover {{ background-color: {c[f'btn_{tone}_bg_hover']}; }}")
            btn.clicked.connect(slot)
            btn.hide()
            bl.addWidget(btn)
            setattr(self, name, btn)
        self._category_filter = CategoryFilter(lambda _k: self._refresh())
        bl.addWidget(self._category_filter)

    def _style_mode_buttons(self) -> None:
        c = get_colors()
        active = f"""
            QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']};
                border: none; border-radius: 8px; padding: 3px 10px;
                font-size: {SIZE_BODY_S}px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """
        idle = f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border-radius: 8px; padding: 3px 10px; font-size: {SIZE_BODY_S}px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']};
                color: {c['btn_secondary_hover_fg']}; }}
        """
        self._mode_day.setStyleSheet(active if self._view_mode == "day" else idle)
        self._mode_week.setStyleSheet(active if self._view_mode == "week" else idle)

    @property
    def course_panel(self) -> CoursePanel:
        return self._course_panel

    @property
    def view_mode(self) -> str:
        return self._view_mode

    @property
    def _target_date(self) -> date:
        return schedule_date() + timedelta(days=self._day_offset)

    def _prev_day(self) -> None:
        self._day_offset -= 1
        self._refresh()

    def _next_day(self) -> None:
        self._day_offset += 1
        self._refresh()

    def _go_today(self) -> None:
        self._day_offset = 0
        self._refresh()

    # ── Quick Arrange ──────────────────────────────────────

    def _build_snapshot(self, days: int = 1) -> str:
        """构建供人与 AI 阅读的 N 天日程快照（实现在 `schedule_snapshot`）。"""
        from src.ui.widgets.schedule_snapshot import build_snapshot

        return build_snapshot(self._dm, self._target_date, days)


    def _quick_arrange(self, days: int = 3) -> None:
        """Generate snapshot, backup, call AI to arrange."""
        from PySide6.QtWidgets import QMessageBox
        try:
            snapshot = self._build_snapshot(days=days)

            snapshot_path = _os.path.join(str(self._dm.daily_logs.file_path.parent), "schedule_snapshot.txt")
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                f.write(snapshot)

            self._arrange_before = plans_snapshot(self._dm.daily_logs)
            # 本次安排覆盖的日期（与快照同一口径）：撤销**只回滚这些天**，
            # 免得把等待期间用户给别的日期加的计划一起删掉（审查 2026-10-17 #4）
            self._arrange_scope = tuple(
                (self._target_date + timedelta(days=i)).isoformat() for i in range(days))
            self._arrange_after = None

            period_count = self._dm.courses.get_period_count()
            prompt = f"""请根据以下日程快照，为未来{days}天重新安排日程计划。

{snapshot}

请用 ```sh 代码块输出修改命令（不要用JSON）:
- 替换某天全部计划: python scripts/actions.py replace_plans --date "YYYY-MM-DD" --plans '[{{"title":"标题","time_slot":时段编号,"type":"custom","note":"备注"}}]'
- 添加单个计划: python scripts/actions.py add_plan --date "YYYY-MM-DD" --title "标题" --slot 时段编号
- 删除计划: python scripts/actions.py delete_plan --date "YYYY-MM-DD" --index 序号
- time_slot编号: {', '.join(str(i) for i in range(1, period_count + 1))}

注意: 习惯不要作为plan重复添加。优先为最近截止的DDL安排复习时间。有考试则优先安排考前复习。**必须为快照中的每一天都输出replace_plans**。"""

            self._arrange_btn.setText("...")
            self._arrange_btn.setEnabled(False)
            self.arrange_requested.emit(prompt)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("widget.schedule.msg_error_title"),
                                tr("widget.schedule.msg_quick_arrange_failed", e=e))
            self._arrange_btn.setText(tr("widget.schedule.btn_quick_arrange"))
            self._arrange_btn.setEnabled(True)

    def on_arrange_done(self, success: bool, msg: str = "") -> None:
        """Called by main_window when AI response is processed."""
        self._arrange_btn.setText(tr("widget.schedule.btn_quick_arrange"))
        self._arrange_btn.setEnabled(True)
        if success:
            self._arrange_after = plans_snapshot(self._dm.daily_logs)
            self._undo_btn.show()
            self._save_btn.show()
            self._refresh()
        else:
            QMessageBox.warning(self, tr("widget.schedule.msg_arrange_failed_title"),
                                msg or tr("widget.schedule.msg_ai_error"))

    def _save_arrange(self) -> None:
        """确认这次安排：丢掉撤销快照。"""
        self._undo_btn.hide()
        self._save_btn.hide()
        self._arrange_before = None
        self._arrange_after = None

    def _undo_arrange(self) -> None:
        """只回滚本次安排涉及的 `plans`（实现见 `schedule_actions.undo_arrange`）。"""
        if not undo_arrange(self, self._dm, self._arrange_before, self._arrange_after,
                            self._arrange_scope):
            return                    # 无快照 / 期间被改过 / 写盘被拒 → 已提示，快照保留
        self._arrange_before = None
        self._arrange_after = None
        self._arrange_scope = ()
        self._undo_btn.hide()
        self._save_btn.hide()
        self._dm.data_changed.emit("plan")
        self._refresh()

    # ── Refresh 辅助方法（拆分自原 60 复杂度的 _refresh）────────

    def _current_slot(self) -> int | None:
        now = datetime.now()
        return slot_for_minutes(now.hour * 60 + now.minute)

    def _build_slot_data(self, courses: list, plans: list, habits: list) -> dict[int, list[dict]]:
        slot_data: dict[int, list[dict]] = {i: [] for i in range(1, 7)}
        courses, plans, habits = ([x for x in xs if visible(self._category_filter.value, kind, x)]
                                  for xs, kind in ((courses, "course"), (plans, "plan"), (habits, "habit")))

        for course in courses:
            add_course_to_slots(slot_data, course)

        for plan in plans:
            add_plan_to_slots(slot_data, plan)

        for h in habits:
            add_habit_to_slots(slot_data, h, self._dm)
        return slot_data

    def _build_ddl_by_slot(self, target, period_count: int) -> dict[int, list[dict]]:
        """收集「今日截止」的任务，并按截止时刻归入节次。"""
        ddl_by_slot: dict[int, list[dict]] = {i: [] for i in range(1, period_count + 1)}
        for t in self._dm.tasks.pending:
            due_str = t.get("due_date", "")
            if not due_str or due_str == "None":
                continue
            try:
                due_dt = datetime.fromisoformat(due_str)
            except (ValueError, TypeError):
                continue
            if due_dt.date() != target:
                continue
            minutes = due_dt.hour * 60 + due_dt.minute
            slot = slot_for_minutes(minutes, period_count)
            if slot is None:  # 早于第一节 / 晚于最后一节 → 就近归入
                first_start = int(PERIOD_TIMES[0][0][:2]) * 60 + int(PERIOD_TIMES[0][0][3:])
                slot = 1 if minutes < first_start else period_count
            ddl_by_slot[slot].append(t)
        return ddl_by_slot

    @staticmethod
    def _add_slot_empty(layout: QVBoxLayout, c: dict) -> None:
        """空态也是正文：fg_disabled 在浅色下只有 1.78:1（几乎看不见）。"""
        empty = QLabel(tr("widget.schedule.slot_empty"))
        empty.setStyleSheet(f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px; padding: 4px 0;")
        layout.addWidget(empty)

    def _add_slot_items(self, layout: QVBoxLayout, items: list[dict],
                        plans: list[dict], c: dict) -> None:
        """时段内容：撞课提示（同一时段两门课 → 记得请假）+ 各条目。"""
        if len([i for i in items if i.get("type") == "course"]) > 1:
            warn = QLabel(tr("widget.schedule.slot_conflict"))
            warn.setStyleSheet(
                f"color: {c['accent_text']}; font-size: {SIZE_CAPTION}px; font-weight: 600;"
                f" background: transparent; padding: 2px 0;")
            layout.addWidget(warn)
        for item in items:
            widget = self._create_item_widget(item, plans, c)
            if widget is not None:
                layout.addWidget(widget)

    def _create_slot_card(self, period: int, items: list[dict], ddls: list[dict],
                          plans: list[dict], is_current: bool, c: dict) -> QWidget:
        """构建单个时段卡片（时间头 + 条目 + DDL 标记）。"""
        if period <= len(PERIOD_TIMES):
            start_t, end_t = PERIOD_TIMES[period - 1]
            time_str = f"{start_t} - {end_t}"
        else:
            time_str = tr("widget.schedule.slot_fallback", n=period)

        slot_card = card("panel", pad="spacing_none")
        cl = QVBoxLayout(slot_card)
        cl.setContentsMargins(16, 12, 16, 8)
        cl.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        if is_current:
            arrow = QLabel("▶")
            arrow.setStyleSheet(f"color: {c['accent_text']}; font-size: {SIZE_BODY_L}px; font-weight: bold; border: none;")
            hdr.addWidget(arrow)
        time_label = QLabel(time_str)
        time_label.setStyleSheet(
            f"color: {c['accent'] if is_current else c['fg_hint']}; font-size: {SIZE_BODY_L}px; font-weight: 600;"
        )
        hdr.addWidget(time_label)
        hdr.addStretch()
        cl.addLayout(hdr)

        if not items:
            self._add_slot_empty(cl, c)
        else:
            self._add_slot_items(cl, items, plans, c)

        for t in ddls:
            cl.addWidget(self._create_ddl_label(t, c))
        return slot_card

    def _create_item_widget(self, item: dict, plans: list[dict], c: dict) -> QWidget | None:
        """按条目类型构建卡片内的小部件。"""
        if item["type"] == "course":
            return self._create_course_item(item, plans, c)
        if item["type"] == "plan":
            return self._create_plan_item(item, c)
        if item["type"] == "habit":
            return self._create_habit_item(item, c)
        return None

    def _create_course_item(self, item: dict, plans: list[dict], c: dict) -> QWidget:
        course_card = card("item", pad="spacing_none")
        course_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        course_card.customContextMenuRequested.connect(
            lambda pos, ci=item, card=course_card: self._course_menu(pos, ci, card))
        ccl = QVBoxLayout(course_card)
        ccl.setContentsMargins(12, 8, 12, 8)
        ccl.setSpacing(4)
        name_lbl = QLabel(f"📖 {item['name']}")
        name_lbl.setStyleSheet(f"color: {c['fg_primary']}; font-size: {SIZE_BODY_S}px; font-weight: 600;")
        name_lbl.setWordWrap(True)
        ccl.addWidget(name_lbl)
        loc = item.get("location", "")
        if loc:
            loc_lbl = QLabel(loc)
            loc_lbl.setStyleSheet(f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px;")
            ccl.addWidget(loc_lbl)
        for plan in plans:
            if plan.get("course_name") == item["name"] and plan.get("type") == "course_note":
                note_lbl = QLabel(f"📌 {plan.get('title', '')}")
                note_lbl.setStyleSheet(f"color: {c['accent_text']}; font-size: {SIZE_BODY_L}px; font-weight: 600;")
                note_lbl.setWordWrap(True)
                ccl.addWidget(note_lbl)
        return course_card

    def _create_plan_item(self, item: dict, c: dict) -> QWidget:
        done = bool(item.get("done"))
        plan_card = card("item", pad="spacing_none", bg="accent_bg")
        plan_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        plan_card.customContextMenuRequested.connect(
            lambda pos, pi=item, card=plan_card: self._plan_menu(pos, pi, card))
        pcl = QVBoxLayout(plan_card)
        pcl.setContentsMargins(12, 8, 12, 8)
        pcl.setSpacing(4)
        # 已完成：✅ 前缀 + 变灰 + 删除线（一眼看出"这条做过了"）
        prefix = "✅" if done else ("📅" if item.get("plan_type") == "custom" else "🔄")
        title_lbl = QLabel(f"{prefix} {item['title']}")
        strike = " text-decoration: line-through;" if done else ""
        title_lbl.setStyleSheet(
            f"color: {c['fg_hint'] if done else c['fg_primary']};"
            f" font-size: {SIZE_BODY_S}px; font-weight: 600;{strike}")
        title_lbl.setWordWrap(True)
        pcl.addWidget(title_lbl)
        note = item.get("note", "")
        if note:
            n = QLabel(note)
            n.setStyleSheet(
                f"color: {c['fg_hint'] if done else c['fg_secondary']}; font-size: {SIZE_BODY_S}px;")
            n.setWordWrap(True)
            pcl.addWidget(n)
        return plan_card

    def _create_habit_item(self, item: dict, c: dict) -> QWidget:
        hab_card = card("item", pad="spacing_none")
        hab_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hab_card.customContextMenuRequested.connect(
            lambda pos, hi=item, card=hab_card: self._habit_menu(pos, hi, card))
        hcl = QVBoxLayout(hab_card)
        hcl.setContentsMargins(12, 8, 12, 8)
        hcl.setSpacing(4)
        done = bool(item.get("done"))
        status = "✓" if done else "○"
        dur = item.get("duration", 30)
        rt = item.get("reminder_time", "")
        rt_str = f" {rt}" if rt else ""
        name_lbl = QLabel(f"{status} {item['name']}{rt_str}  ({tr('widget.schedule.habit_minutes', dur=dur)})")
        name_lbl.setStyleSheet(
            f"color: {c['fg_hint'] if done else c['fg_primary']}; font-size: {SIZE_BODY_S}px;")
        hcl.addWidget(name_lbl)
        return hab_card

    def _create_ddl_label(self, t: dict, c: dict) -> ClickLabel:
        due_str = t.get("due_date", "")
        try:
            due_time = datetime.fromisoformat(due_str).strftime("%H:%M")
        except (ValueError, TypeError):
            due_time = ""
        course_name = t.get("course_name", "") or ""
        ddl_label = ClickLabel()
        ddl_label.setWordWrap(False)
        ddl_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        suffix = tr("widget.schedule.ddl_due", time=due_time) if due_time else ""
        ddl_label.setText(f"—— {t.get('title', '')}{suffix} ——")
        ddl_label.setStyleSheet(
            f"color: {c['red']}; font-size: {SIZE_BODY_M}px; font-weight: 600; border: none; background: transparent; padding: 6px 0;")
        ddl_label.clicked.connect(lambda cn=course_name: self.task_focus_requested.emit(cn))
        return ddl_label

    def _refresh(self, force: bool = False) -> None:
        """刷新**当前视图**：日视图重建时段卡片；周视图交给课程表面板。"""
        self._hint_bar.refresh()
        if self._view_mode == "week":
            self._course_panel._refresh()
            return
        self._refresh_day(force)

    def _refresh_day(self, force: bool = False) -> None:
        """重建当日时段视图（hash 增量：内容未变的时段跳过）。

        `force=True` 用于**主题切换**：卡片颜色是创建时写死进各自样式表的，
        内容没变也必须在换主题后重建，否则会留着上一个主题的颜色
        （2026-10-16：深色模式下白卡片）。
        """
        if not hasattr(self, '_slot_cards'):
            self._slot_cards = {}
            self._slot_hashes = {}

        c = get_colors()
        target = self._target_date
        target_str = target.isoformat()
        day_names = [tr("day.monday"), tr("day.tuesday"), tr("day.wednesday"), tr("day.thursday"),
                     tr("day.friday"), tr("day.saturday"), tr("day.sunday")]
        self._date_label.setText(f"{target_str} {day_names[target.weekday()]}")

        courses = self._dm.courses.get_courses_for_date(target)
        plans = self._dm.daily_logs.get_plans(target_str)
        current_slot = self._current_slot()
        period_count = self._dm.courses.get_period_count()

        slot_data = self._build_slot_data(courses, plans, self._dm.habits.habits)
        ddl_by_slot = self._build_ddl_by_slot(target, period_count)

        for period in range(1, period_count + 1):
            items = slot_data.get(period, [])
            ddls = ddl_by_slot.get(period, [])
            is_current = (period == current_slot and self._day_offset == 0)
            new_hash = slot_content_hash(items, ddls, is_current)

            if not force and period in self._slot_cards and self._slot_hashes.get(period) == new_hash:
                continue  # 未变，跳过重建

            if period in self._slot_cards:
                self._content_layout.removeWidget(self._slot_cards[period])
                self._slot_cards[period].deleteLater()

            card = self._create_slot_card(period, items, ddls, plans, is_current, c)
            self._content_layout.insertWidget(slot_layout_index(self._slot_cards, period), card)
            self._slot_cards[period] = card
            self._slot_hashes[period] = new_hash

        # 清理已消失的时段（如 period_count 变小）
        for p in list(self._slot_cards.keys()):
            if p > period_count:
                self._content_layout.removeWidget(self._slot_cards[p])
                self._slot_cards[p].deleteLater()
                del self._slot_cards[p]
                del self._slot_hashes[p]


    def refresh_theme(self) -> None:
        try:
            self._style_mode_buttons()
            self._hint_bar.refresh()
            self._category_filter.refresh_theme()
            self._course_panel.refresh_theme()
            self._refresh(force=True)
        except Exception:
            logger.debug("ScheduleView.refresh_theme 中忽略异常", exc_info=True)

    # ── Right-click menus ──────────────────────────────────

    def _add_email_reminder_dialog(self, item_type: str, item_name: str, item_date: str) -> None:
        """弹时间选择框保存自定义邮件提醒（实现见 `schedule_actions`）。"""
        from src.ui.widgets.schedule_actions import add_email_reminder_dialog

        add_email_reminder_dialog(self._dm, self, item_type, item_name, item_date)

    def _remove_email_reminder(self, item_type: str, item_name: str, item_date: str) -> None:
        """Remove all email reminders for a specific item."""
        count = self._dm.daily_logs.delete_reminders_by_item(item_type, item_name, item_date)
        if count > 0:
            self._dm.daily_logs.save()

    def _has_email_reminder(self, item_type: str, item_name: str, item_date: str) -> bool:
        return self._dm.daily_logs.find_reminder(item_type, item_name, item_date) is not None

    def _course_menu(self, pos, item, widget) -> None:
        from src.ui.widgets.course_table import build_course_context_menu
        menu = build_course_context_menu(item["course"], widget)
        add_separator(menu)
        course_name = item["course"].get("name", "")
        item_date = self._target_date.isoformat()
        if self._has_email_reminder("course", course_name, item_date):
            # 用**回调**而不是"exec() 之后比较文案"（Q-H15）：比较文案会随措辞/i18n 失效
            add_action(menu, tr("widget.schedule.menu_email_remove"),
                       lambda checked=False: self._remove_email_reminder(
                           "course", course_name, item_date))
        else:
            add_action(menu, tr("widget.schedule.menu_email_add"),
                       lambda checked=False: self._add_email_reminder_dialog(
                           "course", course_name, item_date))
        chosen = show_at_cursor(menu)
        if chosen is None or chosen.data() is None:
            return
        action_type, payload = chosen.data()
        self._handle_course_action(action_type, payload, item)

    def _handle_course_action(self, action_type: str, payload, item) -> None:
        """执行课程右键菜单的编辑类操作。"""
        course_id = item["course"].get("id", "")
        if action_type == "toggle_attendance":
            from src.ui.widgets.course_table import toggle_course_attendance
            toggle_course_attendance(self._dm, course_id)
            self._refresh()
        elif action_type == "rename":
            # Simple rename dialog
            from PySide6.QtWidgets import QInputDialog

            name, ok = QInputDialog.getText(self, tr("widget.schedule.dlg_rename_course"),
                                            tr("widget.schedule.dlg_rename_new_name"))
            if ok and name.strip():
                self._dm.courses.update_course(course_id, {"name": name.strip()})
                self._dm.courses.save()
                self._dm.data_changed.emit("course")
                self._refresh()
        elif action_type == "delete":
            self._dm.courses.delete_course(course_id)
            self._dm.courses.save()
            self._dm.data_changed.emit("course")
            self._refresh()
        elif action_type == "view_tasks":
            from src.ui.widgets.course_detail_dialog import CourseDetailDialog
            CourseDetailDialog(self._dm, payload, self).exec()
        elif action_type == "fill":
            from src.ui.widgets.course_table import _build_context_prompt
            prompt = _build_context_prompt(item["course"], payload)
            # 旧实现把 prompt 塞进 `data_changed.emit("fill_prompt:…")`：没人消费，
            # 反而触发全界面刷新。现在走正式信号 → MainWindow 展开 AI 面板并填入。
            self.fill_ai_prompt.emit(prompt)

    def _plan_menu(self, pos, item, widget) -> None:
        menu = new_menu()
        plan_name = item.get("title", "")
        plan_date = self._target_date.isoformat()
        # 「标记完成」= 真的打 `done` 标记（以前是直接删掉，看不出做过什么）；
        # 已完成的那条给「取消完成」。
        if item.get("done"):
            add_action(menu, tr("widget.schedule.menu_mark_undone"),
                       lambda checked=False: self._set_plan_done(item, False))
        else:
            add_action(menu, tr("widget.schedule.menu_mark_done"),
                       lambda checked=False: self._set_plan_done(item, True))
        add_action(menu, tr("widget.schedule.menu_remove"),
                   lambda checked=False: self._delete_plan_at(item))
        add_category_actions(menu, item, lambda k: set_plan_category(
            self._dm, self._target_date, item, k) and self._refresh())
        add_separator(menu)
        if self._has_email_reminder("plan", plan_name, plan_date):
            add_action(menu, tr("widget.schedule.menu_email_remove"),
                       lambda checked=False: self._remove_email_reminder("plan", plan_name, plan_date))
        else:
            add_action(menu, tr("widget.schedule.menu_email_add"),
                       lambda checked=False: self._add_email_reminder_dialog("plan", plan_name, plan_date))
        show_at_cursor(menu)

    def _delete_plan_at(self, item) -> None:
        """按内容匹配删除当天该计划并刷新（实现见 `schedule_actions`）。"""
        from src.ui.widgets.schedule_actions import delete_plan_at

        if delete_plan_at(self._dm, self._target_date, item):
            self._refresh()

    def _set_plan_done(self, item, done: bool) -> None:
        """按内容匹配标记完成 / 取消完成并刷新（实现见 `schedule_actions`）。"""
        from src.ui.widgets.schedule_actions import set_plan_done

        if set_plan_done(self._dm, self._target_date, item, done):
            self._refresh()

    def _habit_menu(self, pos, item, widget) -> None:
        menu = new_menu()
        hid = item["habit"]["id"]
        done = self._dm.habits.is_done_today(hid)
        habit_name = item.get("name", "")
        habit_date = self._target_date.isoformat()

        def _apply(mutate) -> None:
            mutate()
            self._dm.habits.save()
            self._dm.data_changed.emit("habit")
            self._refresh()

        add_action(menu, tr("widget.schedule.menu_mark_undone") if done else tr("widget.schedule.menu_mark_done"),
                   lambda checked=False: _apply(lambda: self._dm.habits.log(hid, not done)))
        add_action(menu, tr("widget.schedule.menu_postpone"),
                   lambda checked=False: _apply(lambda: self._dm.habits.postpone(
                       hid, (self._target_date + timedelta(days=1)).isoformat())))
        add_action(menu, tr("widget.schedule.menu_cancel_today"),
                   lambda checked=False: _apply(lambda: self._dm.habits.cancel_today(hid)))
        add_separator(menu)
        if self._has_email_reminder("habit", habit_name, habit_date):
            add_action(menu, tr("widget.schedule.menu_email_remove"),
                       lambda checked=False: self._remove_email_reminder("habit", habit_name, habit_date))
        else:
            add_action(menu, tr("widget.schedule.menu_email_add"),
                       lambda checked=False: self._add_email_reminder_dialog("habit", habit_name, habit_date))
        show_at_cursor(menu)
