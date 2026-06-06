"""Habit tracking panel — card grid layout with attached tasks."""

from PySide6.QtCore import Qt, Signal, QRect, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialog, QLineEdit, QComboBox,
    QFormLayout, QDialogButtonBox, QMessageBox, QCheckBox,
    QScrollArea, QFrame, QSizePolicy, QMenu,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE

CARD_MIN_WIDTH = 210
CARD_HEIGHT = 135


class _HabitCard(QFrame):
    toggled = Signal(str)  # habit_id
    edit_requested = Signal(str)  # habit_id

    def __init__(self, habit: dict, active: bool, done: bool, parent=None):
        super().__init__(parent)
        self._hid = habit["id"]
        self._active = active
        self._done = done

        c = get_colors()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(CARD_MIN_WIDTH)
        self.setFixedHeight(CARD_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Card appearance
        if not active:
            bg = c["bg_surface"]
            border = c["border"]
            fg = c["fg_hint"]
            name_color = c["fg_hint"]
        elif done:
            bg = c["bg_surface"]
            border = c["border"]
            fg = c["fg_hint"]
            name_color = c["fg_hint"]
        else:
            bg = c["card_bg"]
            border = c["card_border"]
            fg = c["fg_primary"]
            name_color = c["fg_primary"]

        self.setStyleSheet(f"""
            _HabitCard {{ background-color: {bg}; border: 1px solid {border};
                border-radius: 12px; }}
            _HabitCard:hover {{ border-color: {c['accent']}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(6)

        # Top: name + schedule
        top = QHBoxLayout()
        top.setSpacing(6)
        name_lbl = QLabel(habit.get("name", ""))
        name_lbl.setFont(QFont(self.font().family(), 12))
        name_lbl.setStyleSheet(f"font-weight: 600; color: {name_color}; border: none; background: transparent;")
        name_lbl.setMinimumWidth(60)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._name_lbl = name_lbl
        top.addWidget(name_lbl)

        sched = habit.get("schedule", {})
        if sched.get("type") == "weekly":
            days = sched.get("days", [])
            dn = ["一", "二", "三", "四", "五", "六", "日"]
            sched_text = "每周" + "".join(dn[d - 1] for d in sorted(days))
        else:
            sched_text = f"每{sched.get('value',1)}天"
        rt = habit.get("reminder_time", "")
        if rt:
            sched_text += f" {rt}"
        sched_lbl = QLabel(sched_text)
        sched_lbl.setStyleSheet(f"color: {fg}; font-size: 13px; border: none; background: transparent;")
        top.addWidget(sched_lbl)
        top.addStretch()

        # Status indicator
        if not active:
            status = "—"
        elif done:
            status = "✓"
        else:
            status = "○"
        status_lbl = QLabel(status)
        status_lbl.setStyleSheet(
            f"color: {name_color}; font-size: 14px; border: none; background: transparent;"
        )
        top.addWidget(status_lbl)
        layout.addLayout(top)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"border: none; background-color: {c['divider']}; max-height: 1px;")
        layout.addWidget(div)

        # Total time
        ats = habit.get("attached_tasks", [])
        at_total = sum(at.get("duration_minutes", 0) for at in ats)
        total_min = habit.get("duration_minutes", 30) + at_total
        time_lbl = QLabel(f"预计总用时 {total_min} 分钟")
        time_lbl.setStyleSheet(
            f"color: {c['accent']}; font-size: 13px; font-weight: 600; border: none; background: transparent;"
        )
        layout.addWidget(time_lbl)

        # Attached tasks
        if ats:
            at_texts = []
            for at in ats[:3]:
                at_texts.append(at.get("name", ""))
            at_str = "、".join(at_texts)
            if len(ats) > 3:
                at_str += f" 等{len(ats)}项"
        else:
            at_str = "无附加事项"
        at_lbl = QLabel(at_str)
        at_lbl.setWordWrap(True)
        at_lbl.setStyleSheet(
            f"color: {fg}; font-size: 13px; border: none; background: transparent;"
        )
        layout.addWidget(at_lbl)
        layout.addStretch()

    def mouseDoubleClickEvent(self, ev):
        self.toggled.emit(self._hid)

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        edit_action = menu.addAction("编辑")
        edit_action.triggered.connect(lambda: self.edit_requested.emit(self._hid))
        menu.exec(ev.globalPos())


class _FlowGrid(QWidget):
    """Simple flow layout — arranges children in rows, re-wrapping on resize."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spacing = 12

    def setSpacing(self, s: int) -> None:
        self._spacing = s

    def sizeHint(self) -> QSize:
        return QSize(400, 200)

    def minimumSizeHint(self) -> QSize:
        return QSize(200, 200)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._layout_children()

    def _layout_children(self):
        w = self.width()
        x = 0
        y = 0
        row_h = 0
        for child in self.children():
            if not isinstance(child, QWidget) or child.isHidden():
                continue
            cw = child.minimumWidth()
            ch = child.height()
            if x > 0 and x + cw > w:
                x = 0
                y += row_h + self._spacing
                row_h = 0
            child.setGeometry(QRect(x, y, max(cw, CARD_MIN_WIDTH), ch))
            child.show()
            x += max(cw, CARD_MIN_WIDTH) + self._spacing
            row_h = max(row_h, ch)
        self.setMinimumHeight(y + row_h + self._spacing)
        self.updateGeometry()


class HabitPanel(QWidget):
    habit_logged = Signal(str, bool)

    def __init__(self, dm: DataManager, parent=None):
        super().__init__(parent)
        self._dm = dm

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)
        title = QLabel("生活习惯")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet("font-weight: 600; border: none;")
        bar_layout.addWidget(title)
        bar_layout.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(self._btn_qss())
        refresh_btn.clicked.connect(self._refresh)
        bar_layout.addWidget(refresh_btn)
        layout.addWidget(bar)

        # Scrollable card grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._grid = _FlowGrid()
        self._grid.setSpacing(12)
        scroll.setWidget(self._grid)
        layout.addWidget(scroll, stretch=1)

        # Floating + button
        c = get_colors()
        self._fab = QPushButton("+", self)
        self._fab.setFixedSize(48, 48)
        self._fab.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: #fff; border: none;
                border-radius: 12px; font-size: 24px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        self._fab.clicked.connect(self._add_habit)
        self._fab.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fab.raise_()

        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fab.move(self.width() - 64, self.height() - 64)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._fab.raise_()

    def _btn_qss(self) -> str:
        c = get_colors()
        return f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: 1px solid {c['border']}; border-radius: 8px; padding: 4px 12px; font-size: 13px; }}
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
        for h in self._dm.habits.habits:
            active = self._dm.habits.is_active_today(h["id"])
            done = self._dm.habits.is_done_today(h["id"])
            card = _HabitCard(h, active, done)
            card.toggled.connect(self._toggle_habit)
            card.edit_requested.connect(self._edit_habit)
            card.setParent(self._grid)
            card.show()
        self._grid._layout_children()
        self._grid.update()

    def refresh_theme(self) -> None:
        # Rebuild grid and fab style according to new theme
        c = get_colors()
        try:
            self._fab.setStyleSheet(f"""
                QPushButton {{ background-color: {c['accent']}; color: #fff; border: none;
                    border-radius: 12px; font-size: 24px; font-weight: 600; }}
                QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            """)
        except Exception:
            pass
        # Rebuild cards to pick up colors
        try:
            self._refresh()
        except Exception:
            pass

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
    def __init__(self, dm: DataManager, habit: dict | None = None, parent=None):
        super().__init__(parent)
        self._dm = dm
        self._habit = habit
        self._attached: list[dict] = list(habit.get("attached_tasks", [])) if habit else []

        c = get_colors()
        self.setWindowTitle("定义生活习惯")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_surface']}; color: {c['fg_primary']}; }}
            QLabel {{ color: {c['fg_primary']}; }}
            QLineEdit, QComboBox {{
                background-color: {c['input_bg']}; color: {c['fg_primary']};
                border: 1px solid {c['input_border']}; border-radius: 8px; padding: 5px 8px; font-size: 13px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 16, 24, 16)

        form = QFormLayout()
        form.setSpacing(8)

        self._name_input = QLineEdit(habit.get("name", "") if habit else "")
        self._name_input.setPlaceholderText("如：洗衣服")
        form.addRow("名称:", self._name_input)

        sched = habit.get("schedule", {}) if habit else {}
        sched_type = sched.get("type", "interval")

        self._sched_type_combo = QComboBox()
        self._sched_type_combo.addItems(["每N天", "每周固定日"])
        self._sched_type_combo.setCurrentIndex(0 if sched_type == "interval" else 1)
        self._sched_type_combo.currentIndexChanged.connect(self._on_sched_type_changed)

        self._interval_widget = QWidget()
        il = QHBoxLayout(self._interval_widget)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(4)
        il.addWidget(QLabel("每"))
        self._freq_value = QComboBox()
        self._freq_value.setEditable(True)
        self._freq_value.setFixedWidth(70)
        self._freq_value.setStyleSheet(self._num_combo_qss())
        self._freq_value.addItems(["1", "2", "3", "4", "5", "6", "7", "10", "14", "21", "30"])
        if sched_type == "interval":
            self._freq_value.setCurrentText(str(sched.get("value", 1)))
        il.addWidget(self._freq_value)
        il.addWidget(QLabel("天一次"))
        il.addStretch()

        self._weekly_widget = QWidget()
        wl = QHBoxLayout(self._weekly_widget)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(2)
        self._day_checks: list[QCheckBox] = []
        day_names = ["一", "二", "三", "四", "五", "六", "日"]
        weekly_days = sched.get("days", []) if sched_type == "weekly" else []
        for i, dn in enumerate(day_names):
            cb = QCheckBox(dn)
            cb.setChecked((i + 1) in weekly_days)
            wl.addWidget(cb)
            self._day_checks.append(cb)
        wl.addStretch()

        freq_row = QHBoxLayout()
        freq_row.addWidget(self._sched_type_combo)
        freq_row.addWidget(self._interval_widget)
        freq_row.addWidget(self._weekly_widget)
        freq_row.addStretch()
        self._on_sched_type_changed()
        form.addRow("周期:", freq_row)

        self._duration = QComboBox()
        self._duration.setEditable(True)
        self._duration.setFixedWidth(80)
        self._duration.setStyleSheet(self._num_combo_qss())
        self._duration.addItems(["15", "30", "45", "60", "90", "120", "180"])
        self._duration.setCurrentText(str(habit.get("duration_minutes", 30) if habit else "30"))
        dur_layout = QHBoxLayout()
        dur_layout.addWidget(self._duration)
        dur_layout.addWidget(QLabel("分钟"))
        dur_layout.addStretch()
        form.addRow("用时:", dur_layout)

        self._reminder_time = QLineEdit()
        self._reminder_time.setPlaceholderText("如 22:30（可选）")
        self._reminder_time.setText(habit.get("reminder_time", "") if habit else "")
        form.addRow("提醒时间:", self._reminder_time)

        layout.addLayout(form)

        sep = QLabel("附加事项（完成后自动添加为待办）")
        sep.setStyleSheet(f"color: {c['section_heading']}; font-weight: 600; font-size: 13px;")
        layout.addWidget(sep)

        at_list = QListWidget()
        at_list.setMaximumHeight(100)
        at_list.setStyleSheet(f"""
            QListWidget {{ background-color: {c['input_bg']}; border: 1px solid {c['input_border']}; border-radius: 8px; }}
            QListWidget::item {{ padding: 4px 8px; }}
        """)
        self._at_list = at_list
        self._refresh_at_list()
        layout.addWidget(at_list)

        at_btns = QHBoxLayout()
        for text, slot in [("+ 添加", self._add_attached), ("引用已有", self._use_existing), ("移除选中", self._remove_attached)]:
            btn = QPushButton(text)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                    border: 1px solid {c['border']}; border-radius: 8px; padding: 4px 10px; font-size: 13px; }}
                QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
            """)
            btn.clicked.connect(slot)
            at_btns.addWidget(btn)
        at_btns.addStretch()
        layout.addLayout(at_btns)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_sched_type_changed(self) -> None:
        is_interval = self._sched_type_combo.currentIndex() == 0
        self._interval_widget.setVisible(is_interval)
        self._weekly_widget.setVisible(not is_interval)

    def _num_combo_qss(self) -> str:
        c = get_colors()
        return f"""
            QComboBox {{ background-color: {c['input_bg']}; color: {c['fg_primary']};
                border: 1px solid {c['input_border']}; border-radius: 4px;
                padding: 3px 4px; font-size: 13px; text-align: center; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
        """

    def _refresh_at_list(self) -> None:
        self._at_list.clear()
        for at in self._attached:
            text = f"{at.get('name','')}  (延迟{at.get('delay_hours',24)}h, 用时{at.get('duration_minutes',15)}min)"
            self._at_list.addItem(text)

    def _add_attached(self) -> None:
        dialog = _AttachedTaskDialog(self)
        if dialog.exec():
            self._attached.append(dialog.result)
            self._refresh_at_list()

    def _use_existing(self) -> None:
        templates = self._dm.habits.attached_task_templates
        if not templates:
            QMessageBox.information(self, "提示", "暂无可用模板，请先创建。")
            return
        c = get_colors()
        dialog = QDialog(self)
        dialog.setWindowTitle("选择已有附加事项")
        dialog.setMinimumWidth(300)
        dialog.setStyleSheet(f"background-color: {c['bg_surface']}; color: {c['fg_primary']};")
        dl = QVBoxLayout(dialog)
        lst = QListWidget()
        lst.setStyleSheet(f"""
            QListWidget {{ background-color: {c['input_bg']}; border: 1px solid {c['input_border']}; border-radius: 8px; }}
            QListWidget::item {{ padding: 6px 10px; }}
        """)
        for t in templates:
            lst.addItem(f"{t['name']}  (延迟{t.get('delay_hours',24)}h)")
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

    def _validate_and_accept(self) -> None:
        if not self._name_input.text().strip():
            QMessageBox.warning(self, "错误", "请输入习惯名称。")
            return

        try:
            dur_val = int(self._duration.currentText())
        except ValueError:
            dur_val = 30

        if self._sched_type_combo.currentIndex() == 0:
            try:
                freq_val = int(self._freq_value.currentText())
            except ValueError:
                freq_val = 1
            schedule = {"type": "interval", "value": freq_val, "unit": "day"}
        else:
            days = [i + 1 for i, cb in enumerate(self._day_checks) if cb.isChecked()]
            if not days:
                QMessageBox.warning(self, "错误", "请至少选择一个工作日。")
                return
            schedule = {"type": "weekly", "days": days}

        self.result_data = {
            "name": self._name_input.text().strip(),
            "schedule": schedule,
            "duration_minutes": dur_val,
            "reminder_time": self._reminder_time.text().strip(),
            "attached_tasks": list(self._attached),
        }
        self.accept()


class _AttachedTaskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        c = get_colors()
        num_qss = f"""
            QComboBox {{ background-color: {c['input_bg']}; color: {c['fg_primary']};
                border: 1px solid {c['input_border']}; border-radius: 4px;
                padding: 3px 4px; font-size: 13px; text-align: center; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
        """
        self.setWindowTitle("定义附加事项")
        self.setMinimumWidth(320)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_surface']}; color: {c['fg_primary']}; }}
            QLabel {{ color: {c['fg_primary']}; }}
            QLineEdit {{
                background-color: {c['input_bg']}; color: {c['fg_primary']};
                border: 1px solid {c['input_border']}; border-radius: 8px; padding: 5px 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("如：收晾好的衣服")
        form.addRow("名称:", self._name)

        self._delay = QComboBox()
        self._delay.setEditable(True)
        self._delay.setFixedWidth(80)
        self._delay.setStyleSheet(num_qss)
        self._delay.addItems(["1", "2", "4", "6", "12", "24", "48", "72", "168"])
        self._delay.setCurrentText("24")
        delay_row = QHBoxLayout()
        delay_row.addWidget(self._delay)
        delay_row.addWidget(QLabel("小时"))
        delay_row.addStretch()
        form.addRow("延迟:", delay_row)

        self._duration = QComboBox()
        self._duration.setEditable(True)
        self._duration.setFixedWidth(80)
        self._duration.setStyleSheet(num_qss)
        self._duration.addItems(["5", "10", "15", "20", "30", "45", "60", "90"])
        self._duration.setCurrentText("15")
        dur_row = QHBoxLayout()
        dur_row.addWidget(self._duration)
        dur_row.addWidget(QLabel("分钟"))
        dur_row.addStretch()
        form.addRow("用时:", dur_row)

        save_tpl = QPushButton("同时保存为模板（方便下次引用）")
        save_tpl.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {c['accent']}; border: none; font-size: 13px; text-align: left; }}
        """)
        self._save_template = False
        save_tpl.clicked.connect(lambda: setattr(self, '_save_template', True))
        form.addRow(save_tpl)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _ok(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "错误", "请输入附加事项名称。")
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
