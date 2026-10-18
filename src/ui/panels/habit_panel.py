"""Habit tracking panel — card grid layout with attached tasks."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.panels.habit_dialogs import HabitDialog
from src.ui.styles.cards import Card
from src.ui.styles.theme import FAB, SIZE_BODY, font, get_colors
from src.ui.widgets.flow_grid import FlowGrid
from src.ui.widgets.menu import (
    add_action,
    new_menu,
    show_at_cursor,
)
from src.ui.widgets.rounded_button import RoundedButton

CARD_MIN_WIDTH = 210
# **最小**高度（不是固定高度）：内容多就长高，不再一律截到 135（审查 U6）
CARD_MIN_HEIGHT = 135


logger = logging.getLogger(__name__)


class _HabitCard(Card):
    """Warm-paper card."""
    toggled = Signal(str)
    edit_requested = Signal(str)
    postpone_clicked = Signal(str)
    skip_clicked = Signal(str)

    def __init__(self, habit: dict, active: bool, done: bool, parent=None) -> None:
        c = get_colors()
        # 底色随完成状态变（传**令牌名**，卡片自绘时现取 → 切主题自动跟随）；
        # hover 高亮交给 Card 的 hover_bg，不再写 QSS
        super().__init__("item", pad="spacing_none",
                         bg="bg_surface" if done else "bg_card",
                         hover_bg="accent_bg", parent=parent)
        self._hid = habit["id"]
        self._active = active
        self._done = done

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(CARD_MIN_WIDTH)
        # ⚠ 原为 `setFixedHeight(CARD_HEIGHT)`：长标题/多标签会被硬裁掉（审查 U6）
        self.setMinimumHeight(CARD_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        # 识别钩子（不再是 QSS 选择器 —— 样式由 Card 自绘）：测试与验收脚本按它找习惯卡
        self.setObjectName("habitCard")

        # Determine habit type
        sched = habit.get("schedule", {})
        is_daily = sched.get("type") in ("daily", "interval")
        is_weekly = sched.get("type") == "weekly"

        # 文字色：完成态整体弱化
        if done:
            name_fg = c["fg_hint"]
            desc_fg = c["fg_disabled"]
        else:
            name_fg = c["fg_primary"]
            desc_fg = c["fg_secondary"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(4)

        # Row 1: name + tag
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        name_lbl = QLabel(habit.get("name", ""))
        name_lbl.setFont(font(SIZE_BODY))
        name_lbl.setWordWrap(True)                    # 长标题换行，不再被挤掉（U6）
        name_lbl.setToolTip(habit.get("name", ""))    # 超长时给完整内容（U6）
        name_lbl.setStyleSheet(
            f"font-weight: 600; color: {name_fg}; border: none; background: transparent;")
        row1.addWidget(name_lbl)
        row1.addStretch()

        # Tag logic
        tag_text, tag_bg, tag_fg = self._build_tag_style(
            habit, sched, done, active, is_daily, is_weekly, c)

        tag = QLabel(tag_text)
        tag.setStyleSheet(f"""
            color: {tag_fg}; font-size: 11px; font-weight: 500;
            padding: 2px 10px; border-radius: 4px;
            background-color: {tag_bg}; border: none;
        """)
        row1.addWidget(tag, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(row1)

        # Row 2: description
        desc = _build_description(habit, is_daily, is_weekly)
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"color: {desc_fg}; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(desc_lbl)
        layout.addStretch()

        # Row 3: buttons — only when active and not done
        if active and not done:
            layout.addLayout(self._build_action_row(c))

    def _build_tag_style(self, habit: dict, sched: dict, done: bool, active: bool,
                         is_daily: bool, is_weekly: bool,
                         c: dict) -> tuple[str, str, str]:
        """返回标签 (文本, 背景色, 前景色)。"""
        if done:
            return tr("task.status.completed"), c["green_tint"], c["green"]
        if not active:
            text = self._weekly_tag_text(sched) if is_weekly else _describe_schedule(sched)
            return text, "transparent", c["fg_hint"]
        if is_daily:
            streak = habit.get("streak", 0)
            if streak > 0:
                return tr("panel.habit.tag_streak", n=streak), c["green_tint"], c["green"]
            return tr("panel.habit.tag_not_checked_in"), c["red_tint"], c["red"]
        if is_weekly:
            return self._weekly_tag_text(sched), c["accent_bg"], c["accent"]
        return _describe_schedule(sched), c["accent_bg"], c["accent"]

    @staticmethod
    def _weekly_tag_text(sched: dict) -> str:
        """「每周一二三」形式的标签文本。"""
        days = sched.get("days", [])
        dn = [
            tr("panel.habit.day_mon"), tr("panel.habit.day_tue"),
            tr("panel.habit.day_wed"), tr("panel.habit.day_thu"),
            tr("panel.habit.day_fri"), tr("panel.habit.day_sat"),
            tr("panel.habit.day_sun"),
        ]
        return tr("panel.habit.weekly_prefix") + "".join(dn[d - 1] for d in sorted(days))

    def _build_action_row(self, c: dict) -> QHBoxLayout:
        """活跃且未完成时的「完成打卡 / 推迟 / 跳过」按钮行。"""
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        done_btn = RoundedButton(tr("panel.habit.btn_check_in"))
        done_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
                    border-radius: 8px; padding: 8px 12px; font-size: 13px; font-weight: 600;
                }}
                QPushButton:hover {{ background-color: {c['accent_hover']}; }}
                QPushButton:pressed {{ background-color: {c['accent_dim']}; }}
            """)
        done_btn.clicked.connect(lambda: self.toggled.emit(self._hid))
        btn_row.addWidget(done_btn)

        postpone_btn = RoundedButton(tr("panel.habit.btn_postpone"))
        postpone_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {c['fg_secondary']};
                    border: 1px solid {c['border_strong']};
                    border-radius: 8px; padding: 8px 12px; font-size: 13px;
                }}
                QPushButton:hover {{ background: {c['bg_input']}; }}
                QPushButton:pressed {{ background: {c['accent_bg']}; }}
            """)
        postpone_btn.clicked.connect(
            lambda: self.postpone_clicked.emit(self._hid))
        btn_row.addWidget(postpone_btn)

        skip_btn = RoundedButton(tr("panel.habit.btn_skip"))
        skip_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {c['fg_hint']}; border: none;
                    border-radius: 8px; padding: 8px 12px; font-size: 13px;
                }}
                QPushButton:hover {{ color: {c['fg_secondary']}; }}
                QPushButton:pressed {{ color: {c['fg_primary']}; }}
            """)
        skip_btn.clicked.connect(
            lambda: self.skip_clicked.emit(self._hid))
        btn_row.addWidget(skip_btn)
        btn_row.addStretch()
        return btn_row

    def mouseDoubleClickEvent(self, ev) -> None:
        if self._active and not self._done:
            self.toggled.emit(self._hid)

    def contextMenuEvent(self, ev) -> None:
        
        menu = new_menu(self)
        add_action(menu, tr("panel.habit.menu_edit"), lambda checked=False: self.edit_requested.emit(self._hid))
        show_at_cursor(menu)


def _describe_schedule(sched: dict) -> str:
    st = sched.get("type", "daily")
    if st == "weekly":
        days = sched.get("days", [])
        dn = [
            tr("panel.habit.day_mon"), tr("panel.habit.day_tue"),
            tr("panel.habit.day_wed"), tr("panel.habit.day_thu"),
            tr("panel.habit.day_fri"), tr("panel.habit.day_sat"),
            tr("panel.habit.day_sun"),
        ]
        return tr("panel.habit.weekly_prefix") + "".join(dn[d - 1] for d in sorted(days))
    elif st == "monthly":
        return tr("panel.habit.freq_monthly", n=sched.get('value', 4))
    elif st == "interval":
        val = sched.get("value", 1)
        return tr("panel.habit.freq_daily") if val == 1 else tr("panel.habit.freq_every_n_days", n=val)
    else:  # daily
        tpd = sched.get("times_per_day", 1)
        return tr("panel.habit.freq_daily") if tpd == 1 else tr("panel.habit.freq_daily_n", n=tpd)


def _build_description(habit: dict, is_daily: bool, is_weekly: bool) -> str:
    parts = []
    dur = habit.get("duration_minutes", 30)
    if dur:
        parts.append(tr("panel.habit.desc_duration", n=dur))
    ats = habit.get("attached_tasks", [])
    if ats:
        names = [at.get("name", "") for at in ats[:2]]
        parts.append(" · ".join(names))
    return "  ·  ".join(parts) if parts else ""

class HabitPanel(QWidget):
    habit_logged = Signal(str, bool)

    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)
        title = QLabel(tr("panel.habit.title"))
        title.setFont(font("pageTitle"))
        title.setStyleSheet("font-weight: 600; border: none;")
        bar_layout.addWidget(title)
        bar_layout.addStretch()

        refresh_btn = RoundedButton(tr("panel.habit.btn_refresh"))
        refresh_btn.setStyleSheet(self._btn_qss())
        refresh_btn.clicked.connect(self._refresh)
        bar_layout.addWidget(refresh_btn)
        layout.addWidget(bar)

        # Scrollable card grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._grid = FlowGrid(CARD_MIN_WIDTH)
        self._grid.setSpacing(12)
        scroll.setWidget(self._grid)
        layout.addWidget(scroll, stretch=1)

        # Floating + button
        c = get_colors()
        self._fab = RoundedButton("+", self)
        self._fab.setFixedSize(FAB, FAB)
        self._fab.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
                border-radius: 24px; font-size: 24px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            QPushButton:pressed {{ background-color: {c['accent_dim']}; }}
        """)
        self._fab.clicked.connect(self._add_habit)
        self._fab.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fab.raise_()

        self._refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fab.move(self.width() - 64, self.height() - 64)

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        self._fab.raise_()

    def _btn_qss(self) -> str:
        c = get_colors()
        return f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border-radius: 8px; padding: 4px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """

    def _clear_grid(self) -> None:
        for child in list(self._grid.children()):
            if isinstance(child, QWidget):
                child.hide()
                child.setParent(None)
                child.deleteLater()

    def _refresh(self) -> None:
        self._clear_grid()
        visible_count = 0
        for h in self._dm.habits.habits:
            active = self._dm.habits.is_active_today(h["id"])
            # Only show cards that are either active today or already done today
            done = self._dm.habits.is_done_today(h["id"])
            if not active and not done:
                continue
            visible_count += 1
            card = _HabitCard(h, active, done)
            card.toggled.connect(self._toggle_habit)
            card.edit_requested.connect(self._edit_habit)
            card.postpone_clicked.connect(self._postpone_habit)
            card.skip_clicked.connect(self._skip_habit)
            card.setParent(self._grid)
            card.show()
        if visible_count == 0:
            # 空态：今天没有要做的日常（习惯不在今天 / 都已打卡）—— 不给提示的话整页空白，
            # 用户会以为面板坏了（2026-10-16 全量验收发现）
            self._add_empty_hint()
        self._grid._layout_children()
        self._grid.update()

    def _add_empty_hint(self) -> None:
        c = get_colors()
        hint = QLabel(tr("panel.habit.empty_today"))
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {c['fg_hint']}; font-size: 13px; padding: 16px 4px;"
            f" background: transparent;")
        hint.setParent(self._grid)
        hint.show()

    def refresh_theme(self) -> None:
        # Rebuild grid and fab style according to new theme
        c = get_colors()
        try:
            self._fab.setStyleSheet(f"""
                QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
                    border-radius: 12px; font-size: 24px; font-weight: 600; }}
                QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            """)
        except Exception:
            logger.debug("HabitPanel.refresh_theme 中忽略异常", exc_info=True)
        # Rebuild cards to pick up colors
        try:
            self._refresh()
        except Exception:
            logger.debug("HabitPanel.refresh_theme 中忽略异常", exc_info=True)

    

    def _postpone_habit(self, hid: str) -> None:
        """Postpone habit to tomorrow."""
        from datetime import date, timedelta
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self._dm.habits.postpone(hid, tomorrow)
        self._dm.habits.save()
        self._dm.data_changed.emit("habit")
        self._refresh()

    def _skip_habit(self, hid: str) -> None:
        """Skip today's habit."""
        self._dm.habits.cancel_today(hid)
        self._dm.habits.save()
        self._dm.data_changed.emit("habit")
        self._refresh()

    def _toggle_habit(self, hid: str) -> None:
        done = self._dm.habits.is_done_today(hid)
        attached = self._dm.habits.log(hid, not done)
        self._dm.habits.save()
        for at in attached:
            self._dm.tasks.add(at)
        if attached:
            self._dm.tasks.save()
        self._dm.data_changed.emit("habit")
        self._refresh()

    def _add_habit(self) -> None:
        dialog = HabitDialog(self._dm, parent=self)
        if dialog.exec():
            data = dialog.result_data
            self._dm.habits.add_habit(data)
            for at in data.get("attached_tasks", []):
                existing_names = {t["name"] for t in self._dm.habits.attached_task_templates}
                if at["name"] not in existing_names:
                    self._dm.habits.add_template(dict(at))
            self._dm.habits.save()
            self._dm.data_changed.emit("habit")
            self._refresh()

    def _edit_habit(self, hid: str) -> None:
        habit = None
        for h in self._dm.habits.habits:
            if h["id"] == hid:
                habit = h
                break
        if not habit:
            return
        dialog = HabitDialog(self._dm, habit, parent=self)
        if dialog.exec():
            data = dialog.result_data
            self._dm.habits.update_habit(hid, data)
            self._dm.habits.save()
            self._dm.data_changed.emit("habit")
            self._refresh()
