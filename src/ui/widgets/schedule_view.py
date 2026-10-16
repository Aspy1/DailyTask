"""Daily schedule view — courses, plans, habits by time slot with right-click menu."""

import logging
import os as _os
import shutil
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.models.course import PERIOD_TIMES, schedule_date
from src.services.data_manager import DataManager
from src.ui.components.click_label import ClickLabel
from src.ui.styles.theme import FONT_CN, SIZE_SUBTITLE, get_colors

logger = logging.getLogger(__name__)


class ScheduleView(QWidget):
    course_table_requested = Signal()
    task_focus_requested = Signal(str)
    quick_adjust_requested = Signal(str)  # AI prompt for schedule optimization
    arrange_requested = Signal(str)       # Quick-arrange: snapshot prompt → AI service

    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._day_offset = 0
        self._arrange_backup_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        c = get_colors()

        # Toolbar
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
                border-radius: 8px; padding: 3px 10px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        """)
        ct_btn.clicked.connect(self.course_table_requested.emit)
        bl.addWidget(ct_btn)

        bl.addStretch()

        # Undo + Save buttons (hidden until arrange done)
        self._undo_btn = QPushButton("撤销")
        self._undo_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['red']}30; color: {c['red']};
                border: 1px solid {c['red']}60; border-radius: 8px;
                padding: 3px 10px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['red']}50; }}
        """)
        self._undo_btn.clicked.connect(self._undo_arrange)
        self._undo_btn.hide()
        bl.addWidget(self._undo_btn)

        self._save_btn = QPushButton("保存")
        self._save_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['green']}30; color: {c['green']};
                border: 1px solid {c['green']}60; border-radius: 8px;
                padding: 3px 10px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['green']}50; }}
        """)
        self._save_btn.clicked.connect(self._save_arrange)
        self._save_btn.hide()
        bl.addWidget(self._save_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border-radius: 8px; padding: 3px 10px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        """)
        refresh_btn.clicked.connect(self._refresh)
        bl.addWidget(refresh_btn)

        # Quick arrange button
        self._arrange_btn = QPushButton("调整")
        self._arrange_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']};
                border-radius: 8px; padding: 3px 14px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        self._arrange_btn.clicked.connect(self._quick_arrange)
        bl.addWidget(self._arrange_btn)

        for text, slot in [("< 前一天", self._prev_day), ("今天", self._go_today), ("后一天 >", self._next_day)]:
            btn = QPushButton(text)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                    border-radius: 8px; padding: 3px 10px; font-size: 13px; }}
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

    # ── Quick Arrange ──────────────────────────────────────

    def _build_snapshot(self, days: int = 1) -> str:
        """构建供人与 AI 阅读的 N 天日程快照。"""
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        target = self._target_date
        today = date.today()
        lines = [
            f"========== 日程快照: {days}天 (从{target.isoformat()}起) ==========",
            "当前日期: " + today.isoformat(),
            "",
        ]
        lines += self._snapshot_ddl_lines()
        lines += self._snapshot_exam_lines(today)

        period_count = self._dm.courses.get_period_count()
        for d in range(days):
            day = target + timedelta(days=d)
            lines += self._snapshot_day_lines(day, day_names[day.weekday()], today, period_count)

        lines += self._snapshot_instructions(days)
        return "\n".join(lines)

    def _snapshot_ddl_lines(self) -> list[str]:
        """全局 DDL（各天共用）。"""
        pending = self._dm.tasks.pending
        out = [f"--- DDL/截止日期 (共{len(pending)}项, 不可移动的红线) ---"]
        for t in pending:
            due = t.get("due_date", "")[:16].replace("T", " ") if t.get("due_date") else "无截止"
            course = t.get("course_name", "") or ""
            c_str = f" [{course}]" if course else ""
            out.append(f"  ● {t.get('title', '')}{c_str}  截止: {due}")
        out.append("")
        return out

    def _snapshot_exam_lines(self, today) -> list[str]:
        """未来考试列表（无则空）。"""
        exams = getattr(self._dm, "exams", None)
        if exams is None:
            return []
        upcoming = [e for e in exams.exams if e.get("exam_date", "") >= today.isoformat()]
        if not upcoming:
            return []
        out = [f"--- 考试安排 (共{len(upcoming)}场) ---"]
        for e in sorted(upcoming, key=lambda x: x.get("exam_date", "")):
            scope = e.get("scope", "") or ""
            scope_str = f"  范围: {scope}" if scope else ""
            out.append(f"  📝 {e.get('course_name', '')}  {e.get('exam_date', '')}{scope_str}")
        out.append("")
        return out

    def _snapshot_day_lines(self, day, day_name: str, today, period_count: int) -> list[str]:
        """单天：课程 / 习惯 / 已有安排 / 空闲时段。"""
        day_str = day.isoformat()
        marker = " ★今天" if day == today else ""
        lines = [f"========== {day_str} {day_name}{marker} =========="]

        courses = self._dm.courses.get_courses_for_date(day)
        lines += self._snapshot_course_lines(courses)

        active = [h for h in self._dm.habits.habits if self._habit_active_on(h, day)]
        lines += self._snapshot_habit_lines(active)
        lines += self._snapshot_plan_lines(self._dm.daily_logs.get_plans(day_str))

        lines.append(f"  空闲: {self._free_slots_text(courses, period_count)}")
        lines.append("")
        return lines

    @staticmethod
    def _snapshot_course_lines(courses: list[dict]) -> list[str]:
        """单天课程块。"""
        lines = [f"  课程({len(courses)}门):"]
        for c in courses:
            slot_strs = [f"第{s.get('start', '?')}-{s.get('end', '?')}节"
                         for s in c.get("time_slots", [])]
            loc = c.get("location", "") or ""
            loc_str = f" @{loc}" if loc else ""
            lines.append(f"    [{','.join(slot_strs)}] {c.get('name', '')}{loc_str}")
        return lines

    @staticmethod
    def _snapshot_habit_lines(active: list[dict]) -> list[str]:
        """单天习惯块（无则空）。"""
        if not active:
            return []
        lines = [f"  习惯({len(active)}项):"]
        for h in active:
            rt = h.get("reminder_time", "") or ""
            rt_str = f" @{rt}" if rt else ""
            lines.append(f"    {h.get('name', '')}{rt_str} ({h.get('duration_minutes', 30)}分钟)")
        return lines

    @staticmethod
    def _snapshot_plan_lines(plans: list[dict]) -> list[str]:
        """单天已有安排块（无则提示(无)）。"""
        if not plans:
            return ["  已有安排: (无)"]
        lines = [f"  已有安排({len(plans)}项):"]
        for p in plans:
            lines.append(f"    第{p.get('time_slot', '?')}节: {p.get('title', '')}")
        return lines

    @staticmethod
    def _habit_active_on(habit: dict, day) -> bool:
        sched = habit.get("schedule", {})
        st = sched.get("type", "daily")
        if st in ("daily", "interval"):
            return True
        if st == "weekly":
            return (day.weekday() + 1) in sched.get("days", [])
        return False

    @staticmethod
    def _free_slots_text(courses: list[dict], period_count: int) -> str:
        occupied: set[int] = set()
        for c in courses:
            for s in c.get("time_slots", []):
                occupied.update(range(s["start"], s["end"] + 1))
        times = []
        for p in range(1, period_count + 1):
            if p in occupied:
                continue
            if p <= len(PERIOD_TIMES):
                st_t, en_t = PERIOD_TIMES[p - 1]
                times.append(f"第{p}节({st_t}-{en_t})")
            else:
                times.append(f"第{p}节")
        return ", ".join(times) if times else "(无)"

    @staticmethod
    def _snapshot_instructions(days: int) -> list[str]:
        return [
            "========== 安排指令 ==========",
            f"请为以上{days}天安排日程。规则：",
            "1. 课程时段不可占用，DDL截止时间不可移动",
            "2. 将习惯安排到对应日期的空闲时段",
            "3. 根据DDL紧迫度，将任务分配到各天空闲时段（越临近截止越优先）",
            "4. 如有考试，优先安排考前复习时间",
            "5. 允许在上课时段安排自习任务",
            "6. 用 ```sh 代码块输出 actions.py 命令（replace_plans / add_plan），不要用 JSON",
        ]


    def _quick_arrange(self, days: int = 3) -> None:
        """Generate snapshot, backup, call AI to arrange."""
        from PySide6.QtWidgets import QMessageBox
        try:
            snapshot = self._build_snapshot(days=days)

            snapshot_path = _os.path.join(str(self._dm.daily_logs.file_path.parent), "schedule_snapshot.txt")
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                f.write(snapshot)

            backup_path = str(self._dm.daily_logs.file_path) + ".bak"
            shutil.copy2(str(self._dm.daily_logs.file_path), backup_path)
            self._arrange_backup_path = backup_path

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
        except Exception as e:
            QMessageBox.warning(self, "错误", f"快速安排失败: {e}")
            self._arrange_btn.setText("调整")
            self._arrange_btn.setEnabled(True)

    def on_arrange_done(self, success: bool, msg: str = "") -> None:
        """Called by main_window when AI response is processed."""
        self._arrange_btn.setText("调整")
        self._arrange_btn.setEnabled(True)
        if success:
            self._undo_btn.show()
            self._save_btn.show()
            self._refresh()
        else:
            QMessageBox.warning(self, "安排失败", msg or "AI未能生成有效的安排方案。")

    def _save_arrange(self) -> None:
        """Accept the arrangement, dismiss undo/save buttons."""
        self._undo_btn.hide()
        self._save_btn.hide()
        # Keep backup for one more undo — actually, clear it
        if self._arrange_backup_path and _os.path.exists(self._arrange_backup_path):
            _os.remove(self._arrange_backup_path)
        self._arrange_backup_path = None

    def _undo_arrange(self) -> None:
        """Restore daily_logs.json from backup."""
        if not self._arrange_backup_path or not _os.path.exists(self._arrange_backup_path):
            QMessageBox.information(self, "撤销", "没有可撤销的备份。")
            return
        shutil.copy2(self._arrange_backup_path, str(self._dm.daily_logs.file_path))
        _os.remove(self._arrange_backup_path)
        self._arrange_backup_path = None
        self._undo_btn.hide()
        self._save_btn.hide()
        self._dm.reload_all()
        self._dm.data_changed.emit("plan")
        self._refresh()

    # ── Refresh 辅助方法（拆分自原 60 复杂度的 _refresh）────────

    @staticmethod
    def _slot_for_minutes(minutes: int, period_count: int | None = None) -> int | None:
        """把「当天分钟数」映射到节次（1 起）；不在任何时段返回 None。"""
        periods = PERIOD_TIMES if period_count is None else PERIOD_TIMES[:period_count]
        for i, (start_s, end_s) in enumerate(periods):
            s = int(start_s[:2]) * 60 + int(start_s[3:])
            e = int(end_s[:2]) * 60 + int(end_s[3:])
            if s <= minutes <= e:
                return i + 1
        return None

    def _current_slot(self) -> int | None:
        now = datetime.now()
        return self._slot_for_minutes(now.hour * 60 + now.minute)

    def _build_slot_data(self, courses: list, plans: list, habits: list) -> dict[int, list[dict]]:
        """把课程 / 计划 / 当日活跃习惯归入 1–6 时段。"""
        slot_data: dict[int, list[dict]] = {i: [] for i in range(1, 7)}

        for course in courses:
            self._add_course_to_slots(slot_data, course)

        for plan in plans:
            self._add_plan_to_slots(slot_data, plan)

        for h in habits:
            self._add_habit_to_slots(slot_data, h)
        return slot_data

    @staticmethod
    def _add_course_to_slots(slot_data: dict[int, list[dict]], course: dict) -> None:
        """把单门课程写入其占用的每个时段。"""
        for slot in course.get("time_slots", []):
            for s in range(slot["start"], slot["end"] + 1):
                if 1 <= s <= 6:
                    slot_data[s].append({
                        "type": "course",
                        "course": course,
                        "name": course.get("name", ""),
                        "location": course.get("location", ""),
                    })

    @staticmethod
    def _add_plan_to_slots(slot_data: dict[int, list[dict]], plan: dict) -> None:
        """把单条计划写入其时段。"""
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

    def _add_habit_to_slots(self, slot_data: dict[int, list[dict]], h: dict) -> None:
        """把单个当日活跃习惯按提醒时间归入时段。"""
        if not self._dm.habits.is_active_today(h["id"]):
            return
        rt = h.get("reminder_time", "").strip()
        h_min = 0
        if rt:
            try:
                hh, mm = rt.split(":")
                h_min = int(hh) * 60 + int(mm)
            except ValueError:
                h_min = 0
        slot = self._slot_for_minutes(h_min) or 1
        if 1 <= slot <= 6:
            slot_data[slot].append({
                "type": "habit",
                "habit": h,
                "name": h.get("name", ""),
                "duration": h.get("duration_minutes", 30),
                "reminder_time": rt,
            })

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
            slot = self._slot_for_minutes(minutes, period_count)
            if slot is None:  # 早于第一节 / 晚于最后一节 → 就近归入
                first_start = int(PERIOD_TIMES[0][0][:2]) * 60 + int(PERIOD_TIMES[0][0][3:])
                slot = 1 if minutes < first_start else period_count
            ddl_by_slot[slot].append(t)
        return ddl_by_slot

    @staticmethod
    def _content_hash(items: list[dict], ddls: list[dict], is_current: bool) -> str:
        """时段内容指纹，用于增量刷新时跳过未变的卡片。"""
        import hashlib
        import json
        content_key = json.dumps({
            'items': [{'t': i['type'], 'n': i.get('name', '') or i.get('title', ''),
                       'nt': i.get('note', ''), 'd': i.get('duration', 0),
                       'l': i.get('location', ''), 'rt': i.get('reminder_time', ''),
                       'pt': i.get('plan_type', ''), 'cn': i.get('course_name', '')}
                      for i in items],
            'ddls': [{'t': d.get('title', ''), 'd': d.get('due_date', '')[:16]} for d in ddls],
            'cur': is_current,
        }, sort_keys=True).encode()
        return hashlib.md5(content_key, usedforsecurity=False).hexdigest()

    def _create_slot_card(self, period: int, items: list[dict], ddls: list[dict],
                          plans: list[dict], is_current: bool, c: dict) -> QWidget:
        """构建单个时段卡片（时间头 + 条目 + DDL 标记）。"""
        if period <= len(PERIOD_TIMES):
            start_t, end_t = PERIOD_TIMES[period - 1]
            time_str = f"{start_t} - {end_t}"
        else:
            time_str = f"时段{period}"

        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{ background-color: {c['card_bg']}; border-radius: 8px; }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 8)
        cl.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        if is_current:
            arrow = QLabel("▶")
            arrow.setStyleSheet(f"color: {c['accent_text']}; font-size: 16px; font-weight: bold; border: none;")
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
                widget = self._create_item_widget(item, plans, c)
                if widget is not None:
                    cl.addWidget(widget)

        for t in ddls:
            cl.addWidget(self._create_ddl_label(t, c))
        return card

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
        course_card = QWidget()
        course_card.setStyleSheet(
            f"QWidget {{ background-color: {c['bg_elevated']}; border-radius: 8px; }}")
        course_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        course_card.customContextMenuRequested.connect(
            lambda pos, ci=item, card=course_card: self._course_menu(pos, ci, card))
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
                note_lbl.setStyleSheet(f"color: {c['accent_text']}; font-size: 16px; font-weight: 600;")
                note_lbl.setWordWrap(True)
                ccl.addWidget(note_lbl)
        return course_card

    def _create_plan_item(self, item: dict, c: dict) -> QWidget:
        plan_card = QWidget()
        plan_card.setStyleSheet(
            f"QWidget {{ background-color: {c['accent_bg']}; border-radius: 8px; }}")
        plan_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        plan_card.customContextMenuRequested.connect(
            lambda pos, pi=item, card=plan_card: self._plan_menu(pos, pi, card))
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
        return plan_card

    def _create_habit_item(self, item: dict, c: dict) -> QWidget:
        hab_card = QWidget()
        hab_card.setStyleSheet(
            f"QWidget {{ background-color: {c['bg_elevated']}; border-radius: 8px; }}")
        hab_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hab_card.customContextMenuRequested.connect(
            lambda pos, hi=item, card=hab_card: self._habit_menu(pos, hi, card))
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
            f"color: {c['fg_hint'] if done else c['fg_primary']}; font-size: 13px;")
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
        suffix = f" 截止 {due_time}" if due_time else ""
        ddl_label.setText(f"—— {t.get('title', '')}{suffix} ——")
        ddl_label.setStyleSheet(
            f"color: {c['red']}; font-size: 15px; font-weight: 600; border: none; background: transparent; padding: 6px 0;")
        ddl_label.clicked.connect(lambda cn=course_name: self.task_focus_requested.emit(cn))
        return ddl_label

    def _refresh(self, force: bool = False) -> None:
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
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
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
            new_hash = self._content_hash(items, ddls, is_current)

            if not force and period in self._slot_cards and self._slot_hashes.get(period) == new_hash:
                continue  # 未变，跳过重建

            if period in self._slot_cards:
                self._content_layout.removeWidget(self._slot_cards[period])
                self._slot_cards[period].deleteLater()

            card = self._create_slot_card(period, items, ddls, plans, is_current, c)
            self._content_layout.insertWidget(self._content_layout.count() - 1, card)
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
        """Re-render the schedule to pick up new theme colors."""
        try:
            self._refresh(force=True)
        except Exception:
            logger.debug("ScheduleView.refresh_theme 中忽略异常", exc_info=True)

    # ── Right-click menus ──────────────────────────────────

    def _add_email_reminder_dialog(self, item_type: str, item_name: str, item_date: str) -> None:
        """Show datetime picker and save a custom email reminder."""
        from PySide6.QtWidgets import QDateTimeEdit, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
        c = get_colors()
        dlg = QDialog(self)
        dlg.setWindowTitle("添加邮件提醒")
        dlg.setMinimumWidth(320)
        dlg.setStyleSheet(f"""
            QDialog {{ background-color: {c['card_bg']}; }}
            QLabel {{ color: {c['fg_primary']}; font-size: 13px; }}
            QDateTimeEdit {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 6px 10px; font-size: 13px; }}
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
            logger.debug("ScheduleView._add_email_reminder_dialog 中忽略异常", exc_info=True)
        dt.setDateTime(default)
        dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        layout.addWidget(dt)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border-radius: 8px; padding: 6px 18px; font-size: 13px; }}
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

    def _course_menu(self, pos, item, widget) -> None:
        from PySide6.QtGui import QCursor

        from src.ui.widgets.course_table import build_course_context_menu
        menu = build_course_context_menu(item["course"], widget)
        menu.addSeparator()
        course_name = item["course"].get("name", "")
        item_date = self._target_date.isoformat()
        if self._has_email_reminder("course", course_name, item_date):
            menu.addAction("📧 取消邮件提醒")
        else:
            menu.addAction("📧 添加邮件提醒")
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
        self._handle_course_action(action_type, payload, item)

    def _handle_course_action(self, action_type: str, payload, item) -> None:
        """执行课程右键菜单的编辑类操作。"""
        course_id = item["course"].get("id", "")
        if action_type == "rename":
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

    def _plan_menu(self, pos, item, widget) -> None:
        from src.ui.widgets.context_menu import ContextMenu

        menu = ContextMenu()
        done_action = menu.add_action("✓ 标记完成")
        menu.add_action("修改 DDL")
        remove_action = menu.add_action("✕ 移除")
        menu.add_separator()
        plan_name = item.get("title", "")
        plan_date = self._target_date.isoformat()
        if self._has_email_reminder("plan", plan_name, plan_date):
            menu.add_action("📧 取消邮件提醒")
        else:
            menu.add_action("📧 添加邮件提醒")
        menu.exec()

        action = menu.last_action
        if action and action.text == "📧 添加邮件提醒":
            self._add_email_reminder_dialog("plan", plan_name, plan_date)
            return
        if action and action.text == "📧 取消邮件提醒":
            self._remove_email_reminder("plan", plan_name, plan_date)
            return
        if action in (remove_action, done_action):
            # 「移除」与「标记完成」都按内容匹配删除该计划
            self._delete_plan_at(item)

    def _delete_plan_at(self, item) -> None:
        """按内容匹配删除当天该计划并刷新。"""
        date_str = self._target_date.isoformat()
        plans = self._dm.daily_logs.get_plans(date_str)
        for i, p in enumerate(plans):
            if p == item["plan"]:
                self._dm.daily_logs.delete_plan(date_str, i)
                self._dm.daily_logs.save()
                self._dm.data_changed.emit("plan")
                self._refresh()
                return

    def _habit_menu(self, pos, item, widget) -> None:
        from src.ui.widgets.context_menu import ContextMenu
        
        menu = ContextMenu()
        hid = item["habit"]["id"]
        done = self._dm.habits.is_done_today(hid)
        toggle_action = menu.add_action("○ 标记未完成") if done else menu.add_action("✓ 标记完成")
        postpone_action = menu.add_action("→ 推迟到明天")
        cancel_action = menu.add_action("✕ 取消今天")
        menu.add_separator()
        habit_name = item.get("name", "")
        habit_date = self._target_date.isoformat()
        if self._has_email_reminder("habit", habit_name, habit_date):
            menu.add_action("📧 取消邮件提醒")
        else:
            menu.add_action("📧 添加邮件提醒")
        menu.exec()
        
        action = menu.last_action
        if action and action.text == "📧 添加邮件提醒":
            self._add_email_reminder_dialog("habit", habit_name, habit_date)
            return
        if action and action.text == "📧 取消邮件提醒":
            self._remove_email_reminder("habit", habit_name, habit_date)
            return
        if action == toggle_action:
            self._dm.habits.log(hid, not done)
            self._dm.habits.save()
            self._dm.data_changed.emit("habit")
            self._refresh()
        elif action == postpone_action:
            tomorrow = (self._target_date + timedelta(days=1)).isoformat()
            self._dm.habits.postpone(hid, tomorrow)
            self._dm.habits.save()
            self._dm.data_changed.emit("habit")
            self._refresh()
        elif action == cancel_action:
            self._dm.habits.cancel_today(hid)
            self._dm.habits.save()
            self._dm.data_changed.emit("habit")
            self._refresh()
