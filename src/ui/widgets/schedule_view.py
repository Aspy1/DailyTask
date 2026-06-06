"""Daily schedule view — courses, plans, habits by time slot with right-click menu."""

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QPushButton, QMenu,
)
from PySide6.QtGui import QFont

from src.models.course import PERIOD_TIMES, schedule_date
from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE


class ScheduleView(QWidget):
    course_table_requested = Signal()
    task_focus_requested = Signal(str)  # course_name to filter tasks by

    def __init__(self, dm: DataManager, parent=None):
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
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(6)

        title = QLabel("日程")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet("font-weight: 600; border: none;")
        bl.addWidget(title)

        # Course table button
        ct_btn = QPushButton("课程表")
        ct_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: 1px solid {c['border']}; border-radius: 8px; padding: 3px 10px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        """)
        ct_btn.clicked.connect(self.course_table_requested.emit)
        bl.addWidget(ct_btn)

        bl.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: 1px solid {c['border']}; border-radius: 8px; padding: 3px 10px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        """)
        refresh_btn.clicked.connect(self._refresh)
        bl.addWidget(refresh_btn)

        for text, slot in [("< 前一天", self._prev_day), ("今天", self._go_today), ("后一天 >", self._next_day)]:
            btn = QPushButton(text)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                    border: 1px solid {c['border']}; border-radius: 8px; padding: 3px 10px; font-size: 13px; }}
                QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
            """)
            btn.clicked.connect(slot)
            bl.addWidget(btn)

        self._date_label = QLabel()
        self._date_label.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 13px; min-width: 100px;")
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self._date_label)

        layout.addWidget(bar)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 8, 16, 16)
        self._content_layout.setSpacing(12)
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        layout.addWidget(scroll, stretch=1)

        self._refresh()

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

    def _refresh(self) -> None:
        self._dm.reload_all()
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        c = get_colors()
        target = self._target_date
        target_str = target.isoformat()

        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        self._date_label.setText(f"{target_str} {day_names[target.weekday()]}")

        courses = self._dm.courses.get_courses_for_date(target)
        plans = self._dm.daily_logs.get_plans(target_str)
        habits = self._dm.habits.habits

        # Now: for time axis indicator
        now = datetime.now().time()
        now_minutes = now.hour * 60 + now.minute
        current_slot = None
        for i, (start_s, end_s) in enumerate(PERIOD_TIMES):
            s = int(start_s[:2]) * 60 + int(start_s[3:])
            e = int(end_s[:2]) * 60 + int(end_s[3:])
            if s <= now_minutes <= e:
                current_slot = i + 1
                break

        # Build slot data
        slot_data: dict[int, list[dict]] = {i: [] for i in range(1, 7)}

        # Courses
        for course in courses:
            for slot in course.get("time_slots", []):
                for s in range(slot["start"], slot["end"] + 1):
                    if 1 <= s <= 6:
                        slot_data[s].append({
                            "type": "course",
                            "course": course,
                            "name": course.get("name", ""),
                            "location": course.get("location", ""),
                        })

        # Plans
        for plan in plans:
            ts = plan.get("time_slot", 0)
            if 1 <= ts <= 6:
                slot_data[ts].append({
                    "type": "plan",
                    "plan": plan,
                    "plan_type": plan.get("type", "custom"),
                    "title": plan.get("title", ""),
                    "course_name": plan.get("course_name", ""),
                    "note": plan.get("note", ""),
                })

        # Habits — only active today, insert by reminder_time
        for h in habits:
            if not self._dm.habits.is_active_today(h["id"]):
                continue
            rt = h.get("reminder_time", "").strip()
            if rt:
                try:
                    hh, mm = rt.split(":")
                    h_min = int(hh) * 60 + int(mm)
                except ValueError:
                    h_min = 0
            else:
                h_min = 0
            # Map to time slot
            slot = 1
            for i, (start_s, end_s) in enumerate(PERIOD_TIMES):
                s = int(start_s[:2]) * 60 + int(start_s[3:])
                e = int(end_s[:2]) * 60 + int(end_s[3:])
                if s <= h_min <= e:
                    slot = i + 1
                    break
            if 1 <= slot <= 6:
                slot_data[slot].append({
                    "type": "habit",
                    "habit": h,
                    "name": h.get("name", ""),
                    "duration": h.get("duration_minutes", 30),
                    "reminder_time": rt,
                })

        period_count = self._dm.courses.get_period_count()

        # ── DDL markers: collect tasks due today ────────────
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
            due_minutes = due_dt.hour * 60 + due_dt.minute
            # Map to period
            slot = None
            for i, (start_s, end_s) in enumerate(PERIOD_TIMES[:period_count]):
                s = int(start_s[:2]) * 60 + int(start_s[3:])
                e = int(end_s[:2]) * 60 + int(end_s[3:])
                if s <= due_minutes <= e:
                    slot = i + 1
                    break
            if slot is None:
                # Before first slot or after last — put in nearest
                first_start = int(PERIOD_TIMES[0][0][:2]) * 60 + int(PERIOD_TIMES[0][0][3:])
                if due_minutes < first_start:
                    slot = 1
                else:
                    slot = period_count
            ddl_by_slot[slot].append(t)

        for period in range(1, period_count + 1):
            items = slot_data.get(period, [])
            if period <= len(PERIOD_TIMES):
                start_t, end_t = PERIOD_TIMES[period - 1]
                time_str = f"{start_t} - {end_t}"
            else:
                time_str = f"时段{period}"

            is_current = (period == current_slot and self._day_offset == 0)

            card = QFrame()
            card.setAttribute(Qt.WA_StyledBackground, True)
            card.setStyleSheet(f"""
                QFrame {{ background-color: {c['card_bg']}; border: 1px solid {c['border_strong']}; border-radius: 8px; }}
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 8)
            cl.setSpacing(8)

            # Time header row with optional arrow indicator
            hdr = QHBoxLayout()
            hdr.setSpacing(6)

            if is_current:
                arrow = QLabel("▶")
                arrow.setStyleSheet(f"color: {c['accent']}; font-size: 16px; font-weight: bold; border: none;")
                hdr.addWidget(arrow)

            time_label = QLabel(time_str)
            time_label.setStyleSheet(
                f"color: {c['accent'] if is_current else c['fg_hint']}; font-size: 16px; font-weight: 600;"
            )
            hdr.addWidget(time_label)
            hdr.addStretch()
            cl.addLayout(hdr)

            if not items:
                empty = QLabel("空闲")
                empty.setStyleSheet(f"color: {c['fg_disabled']}; font-size: 13px; padding: 4px 0;")
                cl.addWidget(empty)
            else:
                for item in items:
                    if item["type"] == "course":
                        course_card = QFrame()
                        course_card.setAttribute(Qt.WA_StyledBackground, True)
                        course_card.setStyleSheet(
                            f"QFrame {{ background-color: {c['bg_elevated']}; border-radius: 8px; }}"
                        )
                        course_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                        course_card.customContextMenuRequested.connect(
                            lambda pos, ci=item: self._course_menu(pos, ci, course_card)
                        )
                        ccl = QVBoxLayout(course_card)
                        ccl.setContentsMargins(12, 8, 12, 8)
                        ccl.setSpacing(4)
                        name_lbl = QLabel(f"📖 {item['name']}")
                        name_lbl.setStyleSheet(f"color: {c['fg_primary']}; font-size: 13px; font-weight: 600;")
                        name_lbl.setWordWrap(True)
                        ccl.addWidget(name_lbl)
                        loc = item.get("location", "")
                        if loc:
                            loc_lbl = QLabel(loc)
                            loc_lbl.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px;")
                            ccl.addWidget(loc_lbl)
                        for plan in plans:
                            if plan.get("course_name") == item["name"] and plan.get("type") == "course_note":
                                note_lbl = QLabel(f"📌 {plan.get('title', '')}")
                                note_lbl.setStyleSheet(f"color: {c['accent']}; font-size: 16px; font-weight: 600;")
                                note_lbl.setWordWrap(True)
                                ccl.addWidget(note_lbl)
                        cl.addWidget(course_card)

                    elif item["type"] == "plan":
                        plan_card = QFrame()
                        plan_card.setAttribute(Qt.WA_StyledBackground, True)
                        plan_card.setStyleSheet(
                            f"QFrame {{ background-color: {c['accent_bg']}; border-radius: 8px; }}"
                        )
                        plan_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                        plan_card.customContextMenuRequested.connect(
                            lambda pos, pi=item: self._plan_menu(pos, pi, plan_card)
                        )
                        pcl = QVBoxLayout(plan_card)
                        pcl.setContentsMargins(12, 8, 12, 8)
                        pcl.setSpacing(4)
                        prefix = "📅" if item.get("plan_type") == "custom" else "🔄"
                        title_lbl = QLabel(f"{prefix} {item['title']}")
                        title_lbl.setStyleSheet(f"color: {c['fg_primary']}; font-size: 13px; font-weight: 600;")
                        title_lbl.setWordWrap(True)
                        pcl.addWidget(title_lbl)
                        note = item.get("note", "")
                        if note:
                            n = QLabel(note)
                            n.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 13px;")
                            n.setWordWrap(True)
                            pcl.addWidget(n)
                        cl.addWidget(plan_card)

                    elif item["type"] == "habit":
                        hab_card = QFrame()
                        hab_card.setAttribute(Qt.WA_StyledBackground, True)
                        hab_card.setStyleSheet(
                            f"QFrame {{ background-color: {c['bg_elevated']}; border-radius: 8px; }}"
                        )
                        hab_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                        hab_card.customContextMenuRequested.connect(
                            lambda pos, hi=item: self._habit_menu(pos, hi, hab_card)
                        )
                        hcl = QVBoxLayout(hab_card)
                        hcl.setContentsMargins(12, 8, 12, 8)
                        hcl.setSpacing(4)
                        done = self._dm.habits.is_done_today(item["habit"]["id"])
                        status = "✓" if done else "○"
                        dur = item.get("duration", 30)
                        rt = item.get("reminder_time", "")
                        rt_str = f" {rt}" if rt else ""
                        name_lbl = QLabel(f"{status} {item['name']}{rt_str}  ({dur}分钟)")
                        name_lbl.setStyleSheet(
                            f"color: {c['fg_hint'] if done else c['fg_primary']}; font-size: 13px;"
                        )
                        hcl.addWidget(name_lbl)
                        cl.addWidget(hab_card)

            # ── DDL markers for this slot ──────────────────────
            for t in ddl_by_slot.get(period, []):
                due_str = t.get("due_date", "")
                try:
                    due_dt = datetime.fromisoformat(due_str)
                    due_time = due_dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    due_time = ""
                task_title = t.get("title", "")
                course_name = t.get("course_name", "") or ""
                ddl_divider = QFrame()
                ddl_divider.setAttribute(Qt.WA_StyledBackground, True)
                ddl_divider.setStyleSheet(f"QFrame {{ border: none; background: transparent; }}")
                ddl_layout = QHBoxLayout(ddl_divider)
                ddl_layout.setContentsMargins(0, 4, 0, 4)
                ddl_label = QLabel()
                ddl_label.setTextFormat(Qt.TextFormat.RichText)
                ddl_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ddl_label.setWordWrap(True)
                ddl_label.setMaximumWidth(
                    self._content.width() - 48
                )
                ddl_label.setText(
                    f'<span style="color:{c["fg_hint"]};">——————————</span>'
                    f'<a href="task" style="color:{c['red']};font-weight:bold;text-decoration:none;">{task_title}</a>'
                    f'<span style="color:{c["fg_hint"]};"> 在此时截止 ({due_time}) ——————————</span>'
                )
                ddl_label.linkActivated.connect(
                    lambda cn=course_name: self.task_focus_requested.emit(cn)
                )
                ddl_layout.addWidget(ddl_label)
                cl.addWidget(ddl_divider)

            self._content_layout.insertWidget(self._content_layout.count() - 1, card)

    def refresh_theme(self) -> None:
        """Re-render the schedule to pick up new theme colors."""
        try:
            self._refresh()
        except Exception:
            pass

    # ── Right-click menus ──────────────────────────────────

    def _add_email_reminder_dialog(self, item_type: str, item_name: str, item_date: str) -> None:
        """Show datetime picker and save a custom email reminder."""
        from PySide6.QtWidgets import (
    QFrame,QDialog, QVBoxLayout, QDateTimeEdit,
                                        QPushButton, QLabel, QHBoxLayout)
        c = get_colors()
        dlg = QDialog(self)
        dlg.setWindowTitle("添加邮件提醒")
        dlg.setMinimumWidth(320)
        dlg.setStyleSheet(f"""
            QDialog {{ background-color: {c['card_bg']}; }}
            QLabel {{ color: {c['fg_primary']}; font-size: 13px; }}
            QDateTimeEdit {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border: 1px solid {c['border']}; border-radius: 8px; padding: 6px 10px; font-size: 13px; }}
            QPushButton {{ background-color: {c['accent']}; color: white; border: none;
                border-radius: 8px; padding: 6px 18px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        layout.addWidget(QLabel(f"为「{item_name}」添加邮件提醒"))
        layout.addWidget(QLabel(f"日期: {item_date}"))

        dt = QDateTimeEdit()
        from PySide6.QtCore import QLocale
        dt.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        dt.setCalendarPopup(True)
        from datetime import datetime, timedelta
        # Default to 30 min from now, or 8:00 AM if viewing a future date
        default = datetime.now() + timedelta(minutes=30)
        try:
            target = datetime.fromisoformat(item_date + "T08:00:00")
            if target.date() > datetime.now().date():
                default = target
        except ValueError:
            pass
        dt.setDateTime(default)
        dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        layout.addWidget(dt)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: 1px solid {c['border']}; border-radius: 8px; padding: 6px 18px; font-size: 13px; }}
        """)
        cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel)
        confirm = QPushButton("确认")
        confirm.clicked.connect(dlg.accept)
        btn_row.addWidget(confirm)
        layout.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            from PySide6.QtWidgets import QMessageBox
            selected = dt.dateTime().toPython()
            if selected <= datetime.now():
                QMessageBox.warning(self, "时间无效", "提醒时间不能是过去的时间。")
                return
            notify_time = selected.isoformat()
            self._dm.daily_logs.add_reminder(item_type, item_name, item_date, notify_time)
            self._dm.daily_logs.save()

    def _remove_email_reminder(self, item_type: str, item_name: str, item_date: str) -> None:
        """Remove all email reminders for a specific item."""
        count = self._dm.daily_logs.delete_reminders_by_item(item_type, item_name, item_date)
        if count > 0:
            self._dm.daily_logs.save()

    def _has_email_reminder(self, item_type: str, item_name: str, item_date: str) -> bool:
        return self._dm.daily_logs.find_reminder(item_type, item_name, item_date) is not None

    def _course_menu(self, pos, item, widget):
        from PySide6.QtGui import QCursor
        from src.ui.widgets.course_table import build_course_context_menu
        menu = build_course_context_menu(item["course"], widget)
        menu.addSeparator()
        course_name = item["course"].get("name", "")
        item_date = self._target_date.isoformat()
        if self._has_email_reminder("course", course_name, item_date):
            cancel_rem = menu.addAction("📧 取消邮件提醒")
        else:
            add_rem = menu.addAction("📧 添加邮件提醒")
        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return
        if chosen.text() == "📧 添加邮件提醒":
            self._add_email_reminder_dialog("course", course_name, item_date)
            return
        if chosen.text() == "📧 取消邮件提醒":
            self._remove_email_reminder("course", course_name, item_date)
            return
        if chosen.data() is None:
            return
        action_type, payload = chosen.data()
        course_id = item["course"].get("id", "")
        if action_type == "rename":
            from src.ui.widgets.course_table import CourseTableWidget
            # Simple rename dialog
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(self, "重命名课程", "新名称:")
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
            # Emit via a signal we need to add
            self._dm.data_changed.emit("fill_prompt:" + prompt)

    def _plan_menu(self, pos, item, widget):
        from PySide6.QtGui import QCursor
        c = get_colors()
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        """)
        done = menu.addAction("✓ 标记完成")
        modify = menu.addAction("修改 DDL")
        remove = menu.addAction("✕ 移除")
        menu.addSeparator()
        plan_name = item.get("title", "")
        plan_date = self._target_date.isoformat()
        if self._has_email_reminder("plan", plan_name, plan_date):
            cancel_rem = menu.addAction("📧 取消邮件提醒")
        else:
            add_rem = menu.addAction("📧 添加邮件提醒")
        action = menu.exec(QCursor.pos())
        if action and action.text() == "📧 添加邮件提醒":
            self._add_email_reminder_dialog("plan", plan_name, plan_date)
            return
        if action and action.text() == "📧 取消邮件提醒":
            self._remove_email_reminder("plan", plan_name, plan_date)
            return
        if action == remove:
            plans = self._dm.daily_logs.get_plans(self._target_date.isoformat())
            for i, p in enumerate(plans):
                if p == item["plan"]:
                    self._dm.daily_logs.delete_plan(self._target_date.isoformat(), i)
                    self._dm.daily_logs.save()
                    self._dm.data_changed.emit("plan")
                    self._refresh()
                    return
        elif action == done:
            # Treat plan as completed — remove it
            plans = self._dm.daily_logs.get_plans(self._target_date.isoformat())
            for i, p in enumerate(plans):
                if p == item["plan"]:
                    self._dm.daily_logs.delete_plan(self._target_date.isoformat(), i)
                    self._dm.daily_logs.save()
                    self._dm.data_changed.emit("plan")
                    self._refresh()
                    return

    def _habit_menu(self, pos, item, widget):
        from PySide6.QtGui import QCursor
        c = get_colors()
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        """)
        hid = item["habit"]["id"]
        done = self._dm.habits.is_done_today(hid)
        if done:
            toggle = menu.addAction("○ 标记未完成")
        else:
            toggle = menu.addAction("✓ 标记完成")
        postpone = menu.addAction("→ 推迟到明天")
        cancel = menu.addAction("✕ 取消今天")
        menu.addSeparator()
        habit_name = item.get("name", "")
        habit_date = self._target_date.isoformat()
        if self._has_email_reminder("habit", habit_name, habit_date):
            cancel_rem = menu.addAction("📧 取消邮件提醒")
        else:
            add_rem = menu.addAction("📧 添加邮件提醒")
        action = menu.exec(QCursor.pos())
        if action and action.text() == "📧 添加邮件提醒":
            self._add_email_reminder_dialog("habit", habit_name, habit_date)
            return
        if action and action.text() == "📧 取消邮件提醒":
            self._remove_email_reminder("habit", habit_name, habit_date)
            return
        if action == toggle:
            self._dm.habits.log(hid, not done)
            self._dm.habits.save()
            self._dm.data_changed.emit("habit")
            self._refresh()
        elif action == postpone:
            tomorrow = (self._target_date + timedelta(days=1)).isoformat()
            self._dm.habits.postpone(hid, tomorrow)
            self._dm.habits.save()
            self._dm.data_changed.emit("habit")
            self._refresh()
        elif action == cancel:
            self._dm.habits.cancel_today(hid)
            self._dm.habits.save()
            self._dm.data_changed.emit("habit")
            self._refresh()
