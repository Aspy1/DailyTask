"""Habit tracking panel — card grid layout with attached tasks."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.styles.cards import Card
from src.ui.styles.theme import SIZE_BODY, SIZE_SUBTITLE, font, get_colors
from src.ui.widgets.flow_grid import FlowGrid
from src.ui.widgets.menu import (
    add_action,
    new_menu,
    show_at_cursor,
)
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.rounded_input import RoundedComboBox, RoundedLineEdit

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
        row1.addWidget(tag)
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
            return tr("task.status.completed"), c["green"] + "20", c["green"]
        if not active:
            text = self._weekly_tag_text(sched) if is_weekly else _describe_schedule(sched)
            return text, "transparent", c["fg_hint"]
        if is_daily:
            streak = habit.get("streak", 0)
            if streak > 0:
                return tr("panel.habit.tag_streak", n=streak), c["green"] + "20", c["green"]
            return tr("panel.habit.tag_not_checked_in"), c["red"] + "18", c["red"]
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
        title.setFont(font(SIZE_SUBTITLE))
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
        self._fab.setFixedSize(48, 48)
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


# ── HabitDialog (unchanged, kept below) ────────────────────────

class HabitDialog(QDialog):
    def __init__(self, dm: DataManager, habit: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._habit = habit
        self._attached: list[dict] = list(habit.get("attached_tasks", [])) if habit else []
        self._linked_data: list[dict] = list(habit.get("linked_items", [])) if habit else []

        c = get_colors()
        editing = habit is not None
        self.setWindowTitle(tr("panel.habit.dialog_title_edit") if editing
                            else tr("panel.habit.dialog_title_add"))
        self.setMinimumWidth(440)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_card']}; color: {c['fg_primary']}; }}
            QLabel {{ color: {c['fg_primary']}; background: transparent; border: none; }}
            QLineEdit, QComboBox {{
                background-color: {c['bg_input']}; color: {c['fg_primary']};
                border: 1px solid {c['border']}; padding: 5px 8px; font-size: 13px;
            }}
            QCheckBox {{ color: {c['fg_primary']}; spacing: 2px; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 16)

        form = QFormLayout()
        form.setSpacing(10)

        self._name_input = QLineEdit(habit.get("name", "") if habit else "")
        self._name_input.setPlaceholderText(tr("panel.habit.placeholder_name"))
        form.addRow(tr("panel.habit.label_name"), self._name_input)

        # ── Schedule type ──
        sched = habit.get("schedule", {}) if habit else {}
        sched_type = sched.get("type", "daily")

        self._sched_type_combo = RoundedComboBox()
        self._sched_type_combo.addItems([
            tr("panel.habit.freq_daily"),
            tr("panel.habit.freq_type_weekly"),
            tr("panel.habit.freq_type_monthly"),
        ])
        type_map = {"daily": 0, "weekly": 1, "monthly": 2, "interval": 0}
        self._sched_type_combo.setCurrentIndex(type_map.get(sched_type, 0))
        self._sched_type_combo.currentIndexChanged.connect(self._on_sched_type_changed)

        # Daily: times per day
        self._daily_widget = self._build_daily_widget(sched, sched_type)

        # Weekly: day checkboxes
        self._weekly_widget = self._build_weekly_widget(sched, sched_type)

        # Monthly: N times
        self._monthly_widget = self._build_monthly_widget(sched, sched_type)

        sched_row = QHBoxLayout()
        sched_row.addWidget(self._sched_type_combo)
        sched_row.addWidget(self._daily_widget)
        sched_row.addWidget(self._weekly_widget)
        sched_row.addWidget(self._monthly_widget)
        sched_row.addStretch()
        self._on_sched_type_changed()
        form.addRow(tr("panel.habit.label_schedule"), sched_row)

        # Duration
        self._duration = RoundedComboBox()
        self._duration.setEditable(True)
        self._duration.setFixedWidth(80)
        self._duration.addItems(["15", "30", "45", "60", "90", "120", "180"])
        self._duration.setCurrentText(str(habit.get("duration_minutes", 30) if habit else "30"))
        dur_layout = QHBoxLayout()
        dur_layout.addWidget(self._duration)
        dur_layout.addWidget(QLabel(tr("panel.habit.unit_minutes")))
        dur_layout.addStretch()
        form.addRow(tr("panel.habit.label_duration"), dur_layout)

        # Reminder
        self._reminder_time = RoundedLineEdit()
        self._reminder_time.setPlaceholderText(tr("panel.habit.placeholder_reminder"))
        self._reminder_time.setText(habit.get("reminder_time", "") if habit else "")
        form.addRow(tr("panel.habit.label_reminder"), self._reminder_time)

        layout.addLayout(form)

        # Attached tasks section
        sep = QLabel(tr("panel.habit.section_attached"))
        sep.setStyleSheet(f"color: {c['section_heading']}; font-weight: 600; font-size: 13px;")
        layout.addWidget(sep)

        at_list = QListWidget()
        at_list.setMaximumHeight(100)
        at_list.setStyleSheet(f"""
            QListWidget {{ background-color: {c['bg_input']}; border: 1px solid {c['border']}; }}
            QListWidget::item {{ padding: 4px 8px; }}
        """)
        self._at_list = at_list
        self._refresh_at_list()
        layout.addWidget(at_list)

        at_btns = QHBoxLayout()
        for text, slot in [(tr("panel.habit.btn_add_attached"), self._add_attached),
                           (tr("panel.habit.btn_use_existing"), self._use_existing),
                           (tr("panel.habit.btn_remove"), self._remove_attached)]:
            btn = RoundedButton(text)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                    border: none; border-radius: 4px; padding: 4px 10px; font-size: 12px; }}
                QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
            """)
            btn.clicked.connect(slot)
            at_btns.addWidget(btn)
        at_btns.addStretch()
        layout.addLayout(at_btns)

        # ── Linked items ──
        sep2 = QLabel(tr("panel.habit.section_linked"))
        sep2.setStyleSheet(f"color: {c['section_heading']}; font-weight: 600; font-size: 13px;")
        layout.addWidget(sep2)
        self._linked_list = QListWidget()
        self._linked_list.setMaximumHeight(80)
        self._linked_list.setStyleSheet(f"QListWidget {{ background-color: {c['bg_input']}; border: 1px solid {c['border']}; }} QListWidget::item {{ padding: 4px 8px; }}")
        self._refresh_linked()
        layout.addWidget(self._linked_list)
        lk_btns = QHBoxLayout()
        for text, slot in [(tr("panel.habit.btn_add_linked"), self._add_linked), (tr("panel.habit.btn_remove"), self._remove_linked)]:
            btn = RoundedButton(text)
            btn.setStyleSheet(self._btn_secondary_qss())
            btn.clicked.connect(slot)
            lk_btns.addWidget(btn)
        lk_btns.addStretch()
        layout.addLayout(lk_btns)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_daily_widget(self, sched: dict, sched_type: str) -> QWidget:
        """「每日/间隔」：每天次数控件。"""
        w = QWidget()
        dl = QHBoxLayout(w)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(4)
        dl.addWidget(QLabel(tr("panel.habit.label_per_day")))
        self._times_per_day = RoundedComboBox()
        self._times_per_day.setEditable(True)
        self._times_per_day.setFixedWidth(60)
        self._times_per_day.addItems(["1", "2", "3"])
        if sched_type in ("daily", "interval"):
            val = sched.get("times_per_day") or sched.get("value", 1)
            self._times_per_day.setCurrentText(str(val))
        dl.addWidget(self._times_per_day)
        dl.addWidget(QLabel(tr("panel.habit.unit_times")))
        dl.addStretch()
        return w

    def _build_weekly_widget(self, sched: dict, sched_type: str) -> QWidget:
        """「每周几」：星期复选框控件。"""
        w = QWidget()
        wl = QHBoxLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(2)
        self._day_checks: list[QCheckBox] = []
        day_names = [
            tr("panel.habit.day_mon"), tr("panel.habit.day_tue"),
            tr("panel.habit.day_wed"), tr("panel.habit.day_thu"),
            tr("panel.habit.day_fri"), tr("panel.habit.day_sat"),
            tr("panel.habit.day_sun"),
        ]
        weekly_days = sched.get("days", []) if sched_type == "weekly" else []
        for i, dn in enumerate(day_names):
            cb = QCheckBox(dn)
            cb.setChecked((i + 1) in weekly_days)
            wl.addWidget(cb)
            self._day_checks.append(cb)
        wl.addStretch()
        return w

    def _build_monthly_widget(self, sched: dict, sched_type: str) -> QWidget:
        """「每月N次」：每月次数控件。"""
        w = QWidget()
        ml = QHBoxLayout(w)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(4)
        ml.addWidget(QLabel(tr("panel.habit.label_monthly")))
        self._monthly_times = RoundedComboBox()
        self._monthly_times.setEditable(True)
        self._monthly_times.setFixedWidth(60)
        self._monthly_times.addItems(["1", "2", "3", "4", "5", "8", "10", "15", "20", "30"])
        if sched_type == "monthly":
            self._monthly_times.setCurrentText(str(sched.get("value", 4)))
        ml.addWidget(self._monthly_times)
        ml.addWidget(QLabel(tr("panel.habit.unit_times")))
        ml.addStretch()
        return w

    def _on_sched_type_changed(self) -> None:
        idx = self._sched_type_combo.currentIndex()
        self._daily_widget.setVisible(idx == 0)
        self._weekly_widget.setVisible(idx == 1)
        self._monthly_widget.setVisible(idx == 2)

    def _num_combo_qss(self) -> str:
        c = get_colors()
        return f"""
            QComboBox {{ background-color: {c['bg_input']}; color: {c['fg_primary']};
                border: 1px solid {c['border']}; padding: 3px 4px; font-size: 13px; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
        """

    def _btn_secondary_qss(self) -> str:
        c = get_colors()
        return f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: none; border-radius: 8px; padding: 8px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
            QPushButton:pressed {{ background-color: {c['accent_bg']}; }}
        """

    def _refresh_at_list(self) -> None:
        self._at_list.clear()
        for at in self._attached:
            text = tr("panel.habit.item_attached",
                      name=at.get('name', ''),
                      delay=at.get('delay_hours', 24),
                      duration=at.get('duration_minutes', 15))
            self._at_list.addItem(text)

    def _add_attached(self) -> None:
        dialog = _AttachedTaskDialog(self)
        if dialog.exec():
            self._attached.append(dialog.result)
            self._refresh_at_list()

    def _use_existing(self) -> None:
        templates = self._dm.habits.attached_task_templates
        if not templates:
            QMessageBox.information(self, tr("panel.habit.msg_title_tip"),
                                    tr("panel.habit.msg_no_templates"))
            return
        c = get_colors()
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("panel.habit.dialog_title_select_attached"))
        dialog.setMinimumWidth(300)
        dialog.setStyleSheet(f"background-color: {c['bg_card']}; color: {c['fg_primary']};")
        dl = QVBoxLayout(dialog)
        lst = QListWidget()
        lst.setStyleSheet(f"""
            QListWidget {{ background-color: {c['bg_input']}; border: 1px solid {c['border']}; }}
            QListWidget::item {{ padding: 6px 10px; }}
        """)
        for t in templates:
            lst.addItem(tr("panel.habit.item_template", name=t['name'],
                           delay=t.get('delay_hours', 24)))
        lst.itemDoubleClicked.connect(lambda: dialog.accept())
        dl.addWidget(lst)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        dl.addWidget(btns)
        if dialog.exec() and lst.currentItem():
            idx = lst.currentRow()
            if 0 <= idx < len(templates):
                t = templates[idx]
                self._attached.append({
                    "name": t["name"],
                    "delay_hours": t.get("delay_hours", 24),
                    "duration_minutes": t.get("duration_minutes", 15),
                })
                self._refresh_at_list()

    def _remove_attached(self) -> None:
        row = self._at_list.currentRow()
        if 0 <= row < len(self._attached):
            self._attached.pop(row)
            self._refresh_at_list()

    def _refresh_linked(self) -> None:
        self._linked_list.clear()
        for li in self._linked_data:
            item_id = li.get("item_id", "")
            name = item_id
            for it in self._dm.inventory.items:
                if it["id"] == item_id:
                    name = it["name"]
                    break
            consume = li.get("consume_per_use", 1)
            self._linked_list.addItem(tr("panel.habit.item_linked", name=name, consume=consume))

    def _add_linked(self) -> None:
        items = self._dm.inventory.items
        if not items:
            QMessageBox.information(self, tr("panel.habit.msg_title_tip"),
                                    tr("panel.habit.msg_no_items"))
            return
        c = get_colors()
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("panel.habit.dialog_title_select_linked"))
        dlg.setMinimumWidth(350)
        dlg.setStyleSheet(f"QDialog {{ background-color: {c['bg_card']}; color: {c['fg_primary']}; }}")
        layout = QVBoxLayout(dlg)
        lst = QListWidget()
        lst.setStyleSheet(f"QListWidget {{ background-color: {c['bg_input']}; border: 1px solid {c['border']}; }} QListWidget::item {{ padding: 6px 10px; }}")
        for it in items:
            lst.addItem(tr("panel.habit.item_inventory", id=it['id'], name=it['name'],
                           qty=it['quantity']))
        lst.itemDoubleClicked.connect(dlg.accept)
        layout.addWidget(lst)
        form = QFormLayout()
        self._consume_spin = QSpinBox()
        self._consume_spin.setRange(1,99)
        self._consume_spin.setValue(1)
        form.addRow(tr("panel.habit.label_consume"), self._consume_spin)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        if dlg.exec() and lst.currentItem():
            idx = lst.currentRow()
            if 0 <= idx < len(items):
                self._linked_data.append({"item_id": items[idx]["id"], "consume_per_use": self._consume_spin.value()})
                self._refresh_linked()

    def _remove_linked(self) -> None:
        row = self._linked_list.currentRow()
        if 0 <= row < len(self._linked_data):
            self._linked_data.pop(row)
            self._refresh_linked()

    def _validate_and_accept(self) -> None:
        if not self._name_input.text().strip():
            QMessageBox.warning(self, tr("panel.habit.msg_title_error"),
                                tr("panel.habit.msg_need_name"))
            return

        try:
            dur_val = int(self._duration.currentText())
        except ValueError:
            dur_val = 30

        idx = self._sched_type_combo.currentIndex()
        if idx == 0:  # daily
            try:
                tpd = int(self._times_per_day.currentText())
            except ValueError:
                tpd = 1
            schedule = {"type": "daily", "times_per_day": tpd}
        elif idx == 1:  # weekly
            days = [i + 1 for i, cb in enumerate(self._day_checks) if cb.isChecked()]
            if not days:
                QMessageBox.warning(self, tr("panel.habit.msg_title_error"),
                                    tr("panel.habit.msg_need_weekday"))
                return
            schedule = {"type": "weekly", "days": days}
        else:  # monthly
            try:
                mval = int(self._monthly_times.currentText())
            except ValueError:
                mval = 4
            schedule = {"type": "monthly", "value": mval}

        self.result_data = {
            "name": self._name_input.text().strip(),
            "schedule": schedule,
            "duration_minutes": dur_val,
            "reminder_time": self._reminder_time.text().strip(),
            "attached_tasks": list(self._attached),
            "linked_items": list(self._linked_data),
        }
        self.accept()



class _AttachedTaskDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        c = get_colors()
        num_qss = f"""
            QComboBox {{ background-color: {c['input_bg']}; color: {c['fg_primary']};
                border-radius: 4px;
                padding: 3px 4px; font-size: 13px; text-align: center; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
        """
        self.setWindowTitle(tr("panel.habit.dialog_title_define_attached"))
        self.setMinimumWidth(320)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_surface']}; color: {c['fg_primary']}; }}
            QLabel {{ color: {c['fg_primary']}; }}
            QLineEdit {{
                background-color: {c['input_bg']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 5px 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = RoundedLineEdit()
        self._name.setPlaceholderText(tr("panel.habit.placeholder_attached_name"))
        form.addRow(tr("panel.habit.label_name"), self._name)

        self._delay = RoundedComboBox()
        self._delay.setEditable(True)
        self._delay.setFixedWidth(80)
        self._delay.setStyleSheet(num_qss)
        self._delay.addItems(["1", "2", "4", "6", "12", "24", "48", "72", "168"])
        self._delay.setCurrentText("24")
        delay_row = QHBoxLayout()
        delay_row.addWidget(self._delay)
        delay_row.addWidget(QLabel(tr("panel.habit.unit_hours")))
        delay_row.addStretch()
        form.addRow(tr("panel.habit.label_delay"), delay_row)

        self._duration = RoundedComboBox()
        self._duration.setEditable(True)
        self._duration.setFixedWidth(80)
        self._duration.setStyleSheet(num_qss)
        self._duration.addItems(["5", "10", "15", "20", "30", "45", "60", "90"])
        self._duration.setCurrentText("15")
        dur_row = QHBoxLayout()
        dur_row.addWidget(self._duration)
        dur_row.addWidget(QLabel(tr("panel.habit.unit_minutes")))
        dur_row.addStretch()
        form.addRow(tr("panel.habit.label_duration"), dur_row)

        save_tpl = RoundedButton(tr("panel.habit.btn_save_template"))
        save_tpl.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {c['accent_text']}; border: none; font-size: 13px; text-align: left; }}
        """)
        self._save_template = False
        save_tpl.clicked.connect(lambda: setattr(self, '_save_template', True))
        form.addRow(save_tpl)
        layout.addLayout(form)

        # ── Linked items ──
        sep2 = QLabel(tr("panel.habit.section_linked"))
        sep2.setStyleSheet(f"color: {c['section_heading']}; font-weight: 600; font-size: 13px;")
        layout.addWidget(sep2)
        self._linked_list = QListWidget()
        self._linked_list.setMaximumHeight(80)
        self._linked_list.setStyleSheet(f"QListWidget {{ background-color: {c['bg_input']}; border: 1px solid {c['border']}; }} QListWidget::item {{ padding: 4px 8px; }}")
        self._refresh_linked()
        layout.addWidget(self._linked_list)
        lk_btns = QHBoxLayout()
        for text, slot in [(tr("panel.habit.btn_add_linked"), self._add_linked), (tr("panel.habit.btn_remove"), self._remove_linked)]:
            btn = RoundedButton(text)
            btn.setStyleSheet(f"QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']}; border: none; border-radius: 8px; padding: 8px 12px; font-size: 13px; }} QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }} QPushButton:pressed {{ background-color: {c['accent_bg']}; }}")
            btn.clicked.connect(slot)
            lk_btns.addWidget(btn)
        lk_btns.addStretch()
        layout.addLayout(lk_btns)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _ok(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, tr("panel.habit.msg_title_error"),
                                tr("panel.habit.msg_need_attached_name"))
            return
        try:
            delay = int(self._delay.currentText())
        except ValueError:
            delay = 24
        try:
            dur = int(self._duration.currentText())
        except ValueError:
            dur = 15
        self.result = {
            "name": self._name.text().strip(),
            "delay_hours": delay,
            "duration_minutes": dur,
        }
        self.accept()
