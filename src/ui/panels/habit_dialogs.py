"""「日常」面板的两个弹窗：习惯编辑 / 附属事项。

从 `habit_panel.py` 抽出来（那个文件 909 行，超「单文件 ≤800」的存量债 —— `Q-A1`）。
两个弹窗**不引用面板里的任何东西**，所以是最干净的抽离点。
"""


from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.styles.theme import LAYOUT, SIZE_BODY_S, SIZE_CAPTION, get_colors
from src.ui.widgets.dialog_shell import action_row, cap_height, form_row, make_scrollable
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.rounded_input import RoundedComboBox, RoundedLineEdit


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
        self.setMinimumWidth(LAYOUT["dialog_width_xl"])
        self.setStyleSheet(
            f"QDialog {{ background-color: {c['bg_card']}; color: {c['fg_primary']}; }}"
            f" QLabel {{ color: {c['fg_primary']}; background: transparent; border: none; }}"
            f" QLineEdit, QComboBox {{ background-color: {c['bg_input']}; color: {c['fg_primary']};"
            f" border: 1px solid {c['border']}; padding: 5px 8px; font-size: {SIZE_BODY_S}px; }}"
            f" QCheckBox {{ color: {c['fg_primary']}; spacing: 2px; }}")

        outer = QVBoxLayout(self)
        # 内容可滚动 + 限高（审查 U9）；⚠ 按钮行挂在 `outer` 上，不跟着内容滚
        layout = make_scrollable(outer)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 16)

        self._name_input = RoundedLineEdit(habit.get("name", "") if habit else "")
        self._name_input.setPlaceholderText(tr("panel.habit.placeholder_name"))
        layout.addWidget(form_row(tr("panel.habit.label_name"), self._name_input))

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
        layout.addWidget(form_row(tr("panel.habit.label_schedule"), sched_row))

        # Duration
        self._duration = RoundedComboBox()
        self._duration.setEditable(True)
        self._duration.setFixedWidth(LAYOUT["input_width_md"])
        self._duration.addItems(["15", "30", "45", "60", "90", "120", "180"])
        self._duration.setCurrentText(str(habit.get("duration_minutes", 30) if habit else "30"))
        dur_layout = QHBoxLayout()
        dur_layout.addWidget(self._duration)
        dur_layout.addWidget(QLabel(tr("panel.habit.unit_minutes")))
        dur_layout.addStretch()
        layout.addWidget(form_row(tr("panel.habit.label_duration"), dur_layout))

        # Reminder
        self._reminder_time = RoundedLineEdit()
        self._reminder_time.setPlaceholderText(tr("panel.habit.placeholder_reminder"))
        self._reminder_time.setText(habit.get("reminder_time", "") if habit else "")
        layout.addWidget(form_row(tr("panel.habit.label_reminder"), self._reminder_time))

        # Attached tasks section
        sep = QLabel(tr("panel.habit.section_attached"))
        sep.setStyleSheet(f"color: {c['section_heading']}; font-weight: 600; font-size: {SIZE_BODY_S}px;")
        layout.addWidget(sep)

        at_list = QListWidget()
        at_list.setMaximumHeight(LAYOUT["list_max_height_md"])
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
                    border: none; border-radius: 4px; padding: 4px 10px; font-size: {SIZE_CAPTION}px; }}
                QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
            """)
            btn.clicked.connect(slot)
            at_btns.addWidget(btn)
        at_btns.addStretch()
        layout.addLayout(at_btns)

        # ── Linked items ──
        sep2 = QLabel(tr("panel.habit.section_linked"))
        sep2.setStyleSheet(f"color: {c['section_heading']}; font-weight: 600; font-size: {SIZE_BODY_S}px;")
        layout.addWidget(sep2)
        self._linked_list = QListWidget()
        self._linked_list.setMaximumHeight(LAYOUT["list_max_height_sm"])
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

        outer.addWidget(action_row(tr("widget.dialog.btn_confirm"), self._validate_and_accept,
                                   on_cancel=self.reject))
        cap_height(self)

    def _build_daily_widget(self, sched: dict, sched_type: str) -> QWidget:
        """「每日/间隔」：每天次数控件。"""
        w = QWidget()
        dl = QHBoxLayout(w)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(4)
        dl.addWidget(QLabel(tr("panel.habit.label_per_day")))
        self._times_per_day = RoundedComboBox()
        self._times_per_day.setEditable(True)
        self._times_per_day.setFixedWidth(LAYOUT["input_width_sm"])
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
        self._monthly_times.setFixedWidth(LAYOUT["input_width_sm"])
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
                border: 1px solid {c['border']}; padding: 3px 4px; font-size: {SIZE_BODY_S}px; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
        """

    def _btn_secondary_qss(self) -> str:
        c = get_colors()
        return f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: none; border-radius: 8px; padding: 8px 12px; font-size: {SIZE_BODY_S}px; }}
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
            # 「保存为模板」按钮以前只改了一个没人读的布尔值（死功能）；现在真的存模板
            if getattr(dialog, "_save_template", False):
                self._dm.habits.add_template(dict(dialog.result))
                self._dm.habits.save()
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
        dialog.setMinimumWidth(LAYOUT["dialog_width_xs"])
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
        dl.addWidget(action_row(tr("widget.dialog.btn_confirm"), dialog.accept,
                                on_cancel=dialog.reject))
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
        dlg.setMinimumWidth(LAYOUT["dialog_width_md"])
        dlg.setStyleSheet(f"QDialog {{ background-color: {c['bg_card']}; color: {c['fg_primary']}; }}")
        layout = QVBoxLayout(dlg)
        lst = QListWidget()
        lst.setStyleSheet(f"QListWidget {{ background-color: {c['bg_input']}; border: 1px solid {c['border']}; }} QListWidget::item {{ padding: 6px 10px; }}")
        for it in items:
            lst.addItem(tr("panel.habit.item_inventory", id=it['id'], name=it['name'],
                           qty=it['quantity']))
        lst.itemDoubleClicked.connect(dlg.accept)
        layout.addWidget(lst)
        self._consume_spin = QSpinBox()
        self._consume_spin.setRange(1,99)
        self._consume_spin.setValue(1)
        layout.addWidget(form_row(tr("panel.habit.label_consume"), self._consume_spin))
        layout.addWidget(action_row(tr("widget.dialog.btn_confirm"), dlg.accept,
                                    on_cancel=dlg.reject))
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
                padding: 3px 4px; font-size: {SIZE_BODY_S}px; text-align: center; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
        """
        self.setWindowTitle(tr("panel.habit.dialog_title_define_attached"))
        self.setMinimumWidth(LAYOUT["dialog_width_sm"])
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_surface']}; color: {c['fg_primary']}; }}
            QLabel {{ color: {c['fg_primary']}; }}
            QLineEdit {{
                background-color: {c['input_bg']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 5px 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        self._name = RoundedLineEdit()
        self._name.setPlaceholderText(tr("panel.habit.placeholder_attached_name"))
        layout.addWidget(form_row(tr("panel.habit.label_name"), self._name))

        self._delay = RoundedComboBox()
        self._delay.setEditable(True)
        self._delay.setFixedWidth(LAYOUT["input_width_md"])
        self._delay.setStyleSheet(num_qss)
        self._delay.addItems(["1", "2", "4", "6", "12", "24", "48", "72", "168"])
        self._delay.setCurrentText("24")
        delay_row = QHBoxLayout()
        delay_row.addWidget(self._delay)
        delay_row.addWidget(QLabel(tr("panel.habit.unit_hours")))
        delay_row.addStretch()
        layout.addWidget(form_row(tr("panel.habit.label_delay"), delay_row))

        self._duration = RoundedComboBox()
        self._duration.setEditable(True)
        self._duration.setFixedWidth(LAYOUT["input_width_md"])
        self._duration.setStyleSheet(num_qss)
        self._duration.addItems(["5", "10", "15", "20", "30", "45", "60", "90"])
        self._duration.setCurrentText("15")
        dur_row = QHBoxLayout()
        dur_row.addWidget(self._duration)
        dur_row.addWidget(QLabel(tr("panel.habit.unit_minutes")))
        dur_row.addStretch()
        layout.addWidget(form_row(tr("panel.habit.label_duration"), dur_row))

        save_tpl = RoundedButton(tr("panel.habit.btn_save_template"))
        save_tpl.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {c['accent_text']}; border: none; font-size: {SIZE_BODY_S}px; text-align: left; }}
        """)
        self._save_template = False
        save_tpl.clicked.connect(lambda: setattr(self, '_save_template', True))
        layout.addWidget(save_tpl)

        # ⚠ 这里原先从 `HabitDialog` 复制了一段「关联物品」UI，但
        # `_refresh_linked/_add_linked/_remove_linked` 只定义在 `HabitDialog` 上 →
        # 打开本弹窗第一步就 AttributeError（功能直接崩）。附属事项本来也不消费
        # `linked_items`，整段删除。

        layout.addWidget(action_row(tr("widget.dialog.btn_confirm"), self._ok,
                                    on_cancel=self.reject))

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
