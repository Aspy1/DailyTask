"""Main window — sidebar + content area layout (warm-paper design)."""

from datetime import date, datetime, time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QLabel, QPushButton, QMessageBox, QMenu, QApplication,
)
from PySide6.QtGui import QAction, QFont, QPalette

from src.i18n.loader import tr
from src.models.course import PERIOD_TIMES, schedule_date
from src.ui.styles.theme import get_colors
from src.services.settings_manager import SettingsManager
from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.ui.components.main_workspace import MainWorkspace
from src.ui.components.sidebar import Sidebar
from src.ui.components.ai_panel import AIPanel


class _ClickLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)
        self.clicked.emit()


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager, ai_service: AIService,
                 data_manager: DataManager, plugin_manager=None):
        super().__init__()
        self.setWindowTitle(tr("app.name"))
        self.setMinimumSize(900, 580)
        self.resize(1100, 720)

        self._settings = settings
        self._ai_service = ai_service
        self._data_manager = data_manager
        self._plugin_manager = plugin_manager
        self._ai_visible = False
        self._arrange_pending = False

        self._setup_ui()
        self._setup_statusbar()
        self._connect_ai()

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(30_000)
        self._refresh_status()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar (left) ─────────────────────────────────────
        self._sidebar = Sidebar()
        root.addWidget(self._sidebar)

        # ── Content area (workspace + optional AI panel) ───────
        self._workspace = MainWorkspace(
            self._settings, self._ai_service, self._data_manager,
            self._plugin_manager)
        self._ai_panel = AIPanel()
        self._ai_panel.hide()

        self._content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._content_splitter.addWidget(self._workspace)
        self._content_splitter.addWidget(self._ai_panel)
        self._content_splitter.setSizes([800, 0])
        self._content_splitter.setHandleWidth(1)
        c = get_colors()
        self._content_splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {c['border']}; }}")

        root.addWidget(self._content_splitter, stretch=1)

        # ── Wire sidebar signals ───────────────────────────────
        self._sidebar.nav_changed.connect(self._on_sidebar_nav)
        self._sidebar.ai_toggled.connect(self._on_ai_toggle)

        # Course table → AI prompt fill
        self._connect_course_table()

    def _connect_course_table(self) -> None:
        cp = self._workspace.course_panel
        if cp is not None:
            cp.table.fill_ai_prompt.connect(self._ai_panel.fill_input)

    # ── Navigation ─────────────────────────────────────────────

    def _on_sidebar_nav(self, key: str) -> None:
        if key == "about":
            self._show_about()
            return
        if key == "more":
            self._show_more_menu()
            return
        self._workspace.switch_to(key)

    def _on_ai_toggle(self, visible: bool) -> None:
        self._ai_visible = visible
        if visible:
            self._ai_panel.show()
            self._content_splitter.setSizes([self.width() - 340, 340])
        else:
            self._ai_panel.hide()
            self._content_splitter.setSizes([self.width(), 0])

    def _show_more_menu(self) -> None:
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border: 1px solid {c['border_strong']}; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        """)

        # Theme submenu
        theme_menu = QMenu("切换主题", menu)
        theme_menu.setStyleSheet(menu.styleSheet())
        current_theme = self._settings.get("General", "theme", "dark")
        for mode, label in [("dark", "深色"), ("light", "浅色")]:
            prefix = "● " if mode == current_theme else "    "
            action = theme_menu.addAction(f"{prefix}{label}")
            action.triggered.connect(lambda checked, m=mode: self._switch_theme(m))
        menu.addMenu(theme_menu)

        menu.addAction(tr("menu.help.about"), self._show_about)
        menu.addSeparator()
        menu.addAction(tr("tray.exit"), self.close)
        menu.exec(self._sidebar.mapToGlobal(
            self._sidebar.rect().bottomRight()))

    def _switch_theme(self, mode: str) -> None:
        from src.ui.styles.theme import switch_theme
        self._settings.set("General", "theme", mode)
        self._settings.save()
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(switch_theme(mode))
        try:
            self._ai_panel.refresh_theme()
        except Exception:
            pass
        try:
            if hasattr(self, "_workspace") and hasattr(self._workspace, "refresh_theme"):
                self._workspace.refresh_theme()
        except Exception:
            pass

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout
        c = get_colors()
        dlg = QDialog(self)
        dlg.setWindowTitle("关于")
        dlg.setFixedSize(360, 240)
        dlg.setStyleSheet(f"""
            QDialog {{
                background-color: {c['bg_card']};
                border: 1px solid {c['border']};
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(8)

        name = QLabel(tr("app.name"))
        name.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {c['fg_primary']};")
        layout.addWidget(name)

        ver = QLabel(f"v{tr('app.version')}")
        ver.setStyleSheet(
            f"font-size: 13px; color: {c['fg_hint']};")
        layout.addWidget(ver)

        layout.addSpacing(12)

        desc = QLabel("AI 驱动的学生时间管理与生活助手")
        desc.setStyleSheet(
            f"font-size: 13px; color: {c['fg_secondary']};")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addStretch()

        link = QLabel(
            '<a href="https://github.com/Aspy1/DailyTask" '
            f'style="color:{c["accent"]};text-decoration:none;">'
            'GitHub 仓库</a>')
        link.setOpenExternalLinks(True)
        link.setStyleSheet("font-size: 12px;")
        layout.addWidget(link)

        dlg.exec()

    # ── Status bar ─────────────────────────────────────────────

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        c = get_colors()
        self._statusbar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {c['status_bar_bg']};
                color: {c['fg_secondary']}; font-size: 12px;
                border-top: 1px solid {c['border']};
                padding: 4px 16px;
            }}
            QLabel {{ color: {c['fg_secondary']}; font-size: 12px; border: none; background: transparent; }}
        """)

        self._course_info_label = QLabel()
        self._statusbar.addWidget(self._course_info_label)

        self._statusbar.addPermanentWidget(QLabel(""))  # spacer

        self._expense_label = QLabel()
        self._statusbar.addPermanentWidget(self._expense_label)

        sep1 = QLabel("|")
        sep1.setStyleSheet(f"color: {c['border_strong']}; margin: 0 8px;")
        self._statusbar.addPermanentWidget(sep1)

        self._ddl_alert_label = _ClickLabel()
        self._ddl_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ddl_alert_label.setStyleSheet(
            f"color: {c['red']}; font-size: 12px; font-weight: 600;"
            f"padding: 1px 6px;")
        self._ddl_alert_label.setToolTip("点击查看即将截止的任务")
        self._ddl_alert_label.clicked.connect(self._on_ddl_alert_click)
        self._ddl_alert_label.hide()
        self._statusbar.addPermanentWidget(self._ddl_alert_label)

        sep2 = QLabel("|")
        sep2.setStyleSheet(f"color: {c['border_strong']}; margin: 0 8px;")
        self._statusbar.addPermanentWidget(sep2)

        self._habit_count_label = QLabel()
        self._statusbar.addPermanentWidget(self._habit_count_label)

        sep3 = QLabel("|")
        sep3.setStyleSheet(f"color: {c['border_strong']}; margin: 0 8px;")
        self._statusbar.addPermanentWidget(sep3)

        self._exam_alert_label = _ClickLabel()
        self._exam_alert_label.setStyleSheet(
            f"color: {c['orange']}; font-size: 12px; font-weight: 600; padding: 1px 6px;")
        self._exam_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exam_alert_label.setToolTip("点击查看考试安排")
        self._exam_alert_label.clicked.connect(self._on_exam_alert_click)
        self._statusbar.addPermanentWidget(self._exam_alert_label)

        sep_exam = QLabel("|")
        sep_exam.setStyleSheet(f"color: {c['border_strong']}; margin: 0 8px;")
        self._statusbar.addPermanentWidget(sep_exam)

        self._shopping_label = QLabel()
        self._statusbar.addPermanentWidget(self._shopping_label)

        sep4 = QLabel("|")
        sep4.setStyleSheet(f"color: {c['border_strong']}; margin: 0 8px;")
        self._statusbar.addPermanentWidget(sep4)

        self._date_label = QLabel()
        self._statusbar.addPermanentWidget(self._date_label)

        self._showing_tomorrow = False


    def _connect_ai(self) -> None:
        self._ai_panel.message_sent.connect(self._on_ai_message)
        self._ai_service.response_received.connect(
            self._ai_panel.append_message_ai)
        self._ai_service.error_occurred.connect(self._on_ai_error)
        self._ai_service.instructions_executed.connect(
            self._on_instructions_done)

        # Schedule quick arrange
        self._workspace._schedule_view.arrange_requested.connect(
            self._on_quick_arrange)

    # ── AI ─────────────────────────────────────────────────────

    def _on_ai_message(self, text: str) -> None:
        if not self._ai_visible:
            self._on_ai_toggle(True)
        self._ai_panel.set_status(True, thinking=True)
        self._ai_service.send_message(text)

    def _on_quick_arrange(self, prompt: str) -> None:
        """Handle schedule quick-arrange: send to AI, execute instructions, notify view."""
        sv = self._workspace._schedule_view
        self._course_info_label.setText("AI 正在整理日程...")
        self._arrange_pending = True
        try:
            self._ai_service.send_message(prompt)
        except Exception as e:
            self._arrange_pending = False
            self._course_info_label.setText(f"安排失败: {e}")
            sv.on_arrange_done(False, str(e))

    def _on_ai_error(self, error_msg: str) -> None:
        if getattr(self, '_arrange_pending', False):
            self._arrange_pending = False
            self._course_info_label.setText(f"安排失败: {error_msg}")
            self._workspace._schedule_view.on_arrange_done(False, error_msg)
            return
        self._ai_panel.append_message("ai", f"错误: {error_msg}")
        self._ai_panel._on_response_done()

    def _on_instructions_done(self, text: str, instructions: list) -> None:
        if getattr(self, '_arrange_pending', False):
            self._arrange_pending = False
            self._course_info_label.setText(f"日程调整完成，{len(instructions)} 条指令")
            self._workspace._schedule_view.on_arrange_done(True,
                f"已安排 {len(instructions)} 条指令")
            return
        self._ai_panel.append_message("ai", text)
        self._ai_panel._on_response_done()

    # ── Status refresh ─────────────────────────────────────────

    def _refresh_status(self) -> None:
        self._update_date()
        self._update_next_course()
        self._update_expense()
        self._update_habit_count()
        self._update_exam_alert()
        self._update_shopping()

    def _update_date(self) -> None:
        now = datetime.now()
        semester = self._data_manager.courses.get_semester(
            self._data_manager.courses.current_semester)
        week_str = ""
        if semester:
            try:
                start = date.fromisoformat(semester["start_date"])
                delta = (now.date() - start).days
                week = max(1, delta // 7 + 1) if delta >= 0 else 1
                total = semester.get("total_weeks", "?")
                week_str = f"第{week}/{total}周 "
            except (KeyError, ValueError):
                pass
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        self._date_label.setText(
            f"{week_str}{day_names[now.weekday()]} {now.strftime('%H:%M')}  |  {date.today().isoformat()}")

    def _update_next_course(self) -> None:
        if self._showing_tomorrow:
            self._update_tomorrow_preview()
            return
        today_courses = self._data_manager.courses.get_today_courses()
        now = datetime.now().time()
        past_midnight = schedule_date() != date.today()
        if not today_courses:
            self._course_info_label.setText(tr("status.no_course"))
            return
        entries = []
        for c in today_courses:
            slots = c.get("time_slots", [])
            if not slots:
                continue
            first = min(s["start"] for s in slots) - 1
            last = max(s["end"] for s in slots) - 1
            if first < 0 or first >= len(PERIOD_TIMES):
                continue
            start_str, _ = PERIOD_TIMES[first]
            _, end_str = PERIOD_TIMES[min(last, len(PERIOD_TIMES) - 1)]
            entries.append(
                (time.fromisoformat(start_str), time.fromisoformat(end_str), c))
        if not entries:
            self._course_info_label.setText(tr("status.no_course"))
            return
        entries.sort(key=lambda e: e[0])
        total = len(entries)
        finished = total if past_midnight else sum(
            1 for e in entries if e[1] < now)
        upcoming = None
        if not past_midnight:
            for start_t, end_t, course in entries:
                if start_t > now:
                    upcoming = (start_t, course)
                    break
        if upcoming is None:
            self._course_info_label.setText(
                f"共{total}节课，已上{finished}节，今日课已上完  ▸")
            return
        start_t, course = upcoming
        name = course.get("name", "")
        self._course_info_label.setText(
            f"共{total}节课，已上{finished}节，下一节: {name} "
            f"{start_t.strftime('%H:%M')}  ▸")

    def _update_tomorrow_preview(self) -> None:
        c = get_colors()
        from datetime import timedelta, datetime as dt, time as dt_time

        tomorrow = schedule_date() + timedelta(days=1)
        courses = self._data_manager.courses.get_courses_for_date(tomorrow)
        day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
            tomorrow.weekday()]

        # DDL
        threshold = (tomorrow + timedelta(days=2)).isoformat()
        pending = self._data_manager.tasks.pending
        urgent = [t for t in pending
                  if t.get("due_date", "") and t["due_date"] < threshold]
        ddl_text = f"  |  {len(urgent)}项DDL" if urgent else ""

        if not courses:
            self._course_info_label.setText(
                f"⏎ 明日({day_name}): 无课  |  不用早起{ddl_text}  ▸")
            return

        first = courses[0]
        slots = first.get("time_slots", [])
        first_start = PERIOD_TIMES[slots[0]["start"] - 1][0] if slots else "08:30"
        is_early = first_start <= "08:30"

        start_t = dt_time.fromisoformat(first_start)
        wake_dt = dt.combine(schedule_date(), start_t) - timedelta(minutes=30)
        wake_time = wake_dt.strftime("%H:%M")

        prefix = f"⏎ 明日({day_name}): {len(courses)}节课  |  "
        if is_early:
            text = (
                f'{prefix}<span style="color:{c['red']};">需要早起</span>'
                f"  最早{first_start}  建议{wake_time}起床{ddl_text}  ▸"
            )
        else:
            text = f"{prefix}不用早起  最早{first_start}{ddl_text}  ▸"

        self._course_info_label.setText(text)

    def _toggle_day_view(self) -> None:
        self._showing_tomorrow = not self._showing_tomorrow
        self._refresh_status()

    def _update_expense(self) -> None:
        total = self._data_manager.expenses.today_total()
        self._expense_label.setText(f"¥{total:.0f}")

    
    def _update_habit_count(self) -> None:
        today_habits = [h for h in self._data_manager.habits.habits
                        if self._data_manager.habits.is_active_today(h["id"])]
        done = sum(1 for h in today_habits
                   if self._data_manager.habits.is_done_today(h["id"]))
        total = len(today_habits)
        self._habit_count_label.setText(f"日常{done}/{total}")

    def _update_exam_alert(self) -> None:
        today = date.today()
        c = get_colors()
        upcoming = self._data_manager.exams.get_upcoming(5)
        count = len(upcoming)
        if count == 0:
            self._exam_alert_label.setText("")
            self._exam_alert_label.hide()
            return
        nearest = upcoming[0]
        try:
            delta = (date.fromisoformat(nearest.get("exam_date", "")) - today).days
        except (ValueError, TypeError):
            delta = 999
        if delta <= 7:
            color = c["red"]
        elif delta <= 15:
            color = c["orange"]
        else:
            color = c["fg_secondary"]
        self._exam_alert_label.setText(f"备考{count}科")
        self._exam_alert_label.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 600; padding: 1px 6px;")
        self._exam_alert_label.show()

    def _on_exam_alert_click(self) -> None:
        self._workspace.switch_to("exams")

    def _update_shopping(self) -> None:
        has_inventory = hasattr(self._data_manager, 'inventory')
        if has_inventory:
            items = getattr(self._data_manager.inventory, 'items', [])
            needs = [i for i in items if i.get('status') == 'need']
            if needs:
                self._shopping_label.setText(f"需购{len(needs)}")
                self._shopping_label.show()
            else:
                self._shopping_label.hide()
        else:
            self._shopping_label.hide()

    def _on_ddl_alert_click(self) -> None:
        self._workspace.show_ddl_tasks()

    def set_ddl_alert(self, count: int) -> None:
        c = get_colors()
        if count > 0:
            self._ddl_alert_label.setText(f"{count}项DDL")
            self._ddl_alert_label.setStyleSheet(
                f"color: {c['red']}; font-size: 12px; font-weight: 600;"
                f"padding: 1px 6px;")
            self._ddl_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self._ddl_alert_label.setText("暂无即将截止的事项")
            self._ddl_alert_label.setStyleSheet(
                f"color: {c['fg_hint']}; font-size: 12px;"
                f"padding: 1px 6px;")
            self._ddl_alert_label.setCursor(Qt.CursorShape.ArrowCursor)
        self._ddl_alert_label.show()

    @property
    def ai_panel(self) -> AIPanel:
        return self._ai_panel
