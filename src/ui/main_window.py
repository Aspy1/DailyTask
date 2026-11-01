"""Main window — sidebar + content area layout (warm-paper design)."""

import logging
from datetime import date, datetime, time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.models.course import PERIOD_TIMES, schedule_date
from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager
from src.services.weather_service import WeatherService
from src.ui.animations import count_to
from src.ui.components.ai_panel import AIPanel
from src.ui.components.click_label import ClickLabel
from src.ui.components.main_workspace import MainWorkspace
from src.ui.components.semester_text import ALERT_STATES, semester_state_text
from src.ui.components.sidebar import Sidebar
from src.ui.styles.theme import (
    LAYOUT,
    SIZE_BODY_S,
    SIZE_CAPTION,
    SIZE_SUBTITLE,
    get_colors,
)
from src.ui.widgets.menu import add_action, new_menu, show_at_cursor, show_below
from src.ui.widgets.semester_dialog import SemesterDialog
from src.ui.widgets.weather_dialog import WeatherDetailDialog

logger = logging.getLogger(__name__)


def _statusbar_sep(c: dict) -> QLabel:
    """状态栏分隔符（`|`，弱对比）。"""
    sep = QLabel("|")
    sep.setStyleSheet(f"color: {c['border_strong']}; margin: 0 5px;")
    return sep


def _install_statusbar(window) -> None:
    """构建状态栏（从 `MainWindow` 抽出：类/函数尺寸门禁 Q-A1）。"""
    window._statusbar = QStatusBar()
    window.setStatusBar(window._statusbar)
    c = get_colors()
    window._statusbar.setStyleSheet(window._statusbar_qss(c))
    _install_statusbar_left(window, c)
    _install_statusbar_right(window, c)
    window._showing_tomorrow = False


def _install_statusbar_left(window, c: dict) -> None:
    """左侧：课程信息 + 支出 + DDL 告警。"""
    window._course_info_label = ClickLabel()
    window._course_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
    window._course_info_label.setToolTip(tr("window.status.toggle_day_tooltip"))
    window._course_info_label.clicked.connect(window._toggle_day_view)
    window._statusbar.addWidget(window._course_info_label)

    window._expense_label = QLabel()
    window._statusbar.addPermanentWidget(window._expense_label)
    window._statusbar.addPermanentWidget(_statusbar_sep(c))

    window._ddl_alert_label = ClickLabel()
    window._ddl_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
    window._ddl_alert_label.setStyleSheet(
        f"color: {c['red']}; font-size: {SIZE_CAPTION}px; font-weight: 600;"
        f"padding: 0 3px;")
    window._ddl_alert_label.clicked.connect(window._on_ddl_alert_click)
    window._ddl_alert_label.hide()
    window._statusbar.addPermanentWidget(window._ddl_alert_label)
    window._statusbar.addPermanentWidget(_statusbar_sep(c))


def _install_statusbar_right(window, c: dict) -> None:
    """右侧：习惯 / 考试 / 天气 / 日期 / 学期。"""
    window._habit_count_label = QLabel()
    window._statusbar.addPermanentWidget(window._habit_count_label)
    window._statusbar.addPermanentWidget(_statusbar_sep(c))

    window._exam_alert_label = ClickLabel()
    window._exam_alert_label.setStyleSheet(
        f"color: {c['orange']}; font-size: {SIZE_CAPTION}px; font-weight: 600;"
        f" padding: 0 3px;")
    window._exam_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
    window._exam_alert_label.clicked.connect(window._on_exam_alert_click)
    window._statusbar.addPermanentWidget(window._exam_alert_label)
    window._statusbar.addPermanentWidget(_statusbar_sep(c))

    window._weather_label = ClickLabel()
    window._weather_label.setCursor(Qt.CursorShape.PointingHandCursor)
    window._weather_label.setStyleSheet(
        f"color: {c['fg_secondary']}; font-size: {SIZE_CAPTION}px;")
    window._weather_label.clicked.connect(window._on_weather_click)
    window._weather_label.setText(tr("window.status.weather_placeholder"))
    window._statusbar.addPermanentWidget(window._weather_label)
    window._statusbar.addPermanentWidget(_statusbar_sep(c))

    window._date_label = QLabel()
    window._statusbar.addPermanentWidget(window._date_label)
    window._statusbar.addPermanentWidget(_statusbar_sep(c))

    window._semester_label = ClickLabel()
    window._semester_label.setCursor(Qt.CursorShape.PointingHandCursor)
    window._semester_label.setToolTip(tr("semester.tooltip"))
    window._semester_label.clicked.connect(window._on_semester_click)
    window._statusbar.addPermanentWidget(window._semester_label)


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager, ai_service: AIService,
                 data_manager: DataManager, plugin_manager=None) -> None:
        super().__init__()
        self.setWindowTitle(tr("app.name"))
        self.setMinimumSize(LAYOUT["window_min_width"], LAYOUT["window_min_height"])
        self.resize(1210, 792)

        self._settings = settings
        self._ai_service = ai_service
        self._data_manager = data_manager
        self._plugin_manager = plugin_manager
        self._ai_visible = False
        self._arrange_pending = False

        self._weather_service = WeatherService(
            settings, data_dir=self._data_manager.data_dir)
        if settings.weather_api_key and settings.weather_api_host:
            self._weather_service.set_credentials(
                settings.weather_api_host, settings.weather_api_key)
            if settings.weather_auto_update:
                self._weather_service.start_auto_update()
        self._weather_service.weather_updated.connect(self._on_weather_updated)

        ai_service.set_weather_service(self._weather_service)

        self._setup_ui()
        self._setup_statusbar()
        if self._weather_service.get_now():
            self._on_weather_updated(self._weather_service.get_now())
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
        # 程序化跳转（状态栏 DDL/考试、课程"查看事项"）也同步侧边栏高亮
        self._workspace.panel_changed.connect(self._sidebar.set_active)
        # 数据变化 → **立即**刷新状态栏。
        self._data_manager.data_changed.connect(self._on_data_changed)

        # Course table / schedule day view → AI prompt fill
        self._connect_course_table()
        self._workspace.fill_ai_prompt.connect(self._on_course_fill_ai)

    def _connect_course_table(self) -> None:
        cp = self._workspace.course_panel
        if cp is not None:
            cp.table.fill_ai_prompt.connect(self._on_course_fill_ai)

    def _on_course_fill_ai(self, prompt: str) -> None:
        if not self._ai_visible:
            self._on_ai_toggle(True)
        self._ai_panel.fill_input(prompt)


    def _on_sidebar_nav(self, key: str) -> None:
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
        """「更多…」菜单：锚在该导航项下方（原来是写死在侧边栏右下角）。

        用统一模板（Q-H15）：无原生阴影、token 配色、QMenu 负责贴边翻转。
        """
        menu = new_menu(self)
        current_theme = self._settings.get("General", "theme", "dark")

        theme_menu = new_menu(menu)
        theme_menu.setTitle(tr("menu.view.toggle_theme"))
        for mode, label in [("dark", tr("window.theme.dark")),
                            ("light", tr("window.theme.light"))]:
            prefix = "● " if mode == current_theme else "    "
            action = theme_menu.addAction(f"{prefix}{label}")
            action.triggered.connect(lambda checked, m=mode: self._switch_theme(m))
        menu.addMenu(theme_menu)

        add_action(menu, tr("tray.exit"), lambda checked=False: self.close())

        anchor = self._sidebar.nav_item("more")
        if anchor is not None:
            show_below(menu, anchor)
        else:
            show_at_cursor(menu)

    def _switch_theme(self, mode: str) -> None:
        from src.ui.styles.theme import switch_theme
        self._settings.set("General", "theme", mode)
        self._settings.save()
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(switch_theme(mode))
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """切主题后重刷"颜色写死在样式表里"的自有部件。

        面板们自己有 refresh_theme；但侧边栏、状态栏、分隔条、AI 面板是
        MainWindow 自己建的，不重刷就会留着上一个主题的颜色。
        """
        c = get_colors()
        for step, fn in (
            ("sidebar", lambda: self._sidebar.refresh_theme()),
            ("statusbar", lambda: self._statusbar.setStyleSheet(self._statusbar_qss(c))),
            ("splitter", lambda: self._content_splitter.setStyleSheet(
                f"QSplitter::handle {{ background-color: {c['border']}; }}")),
            ("ai_panel", lambda: self._ai_panel.refresh_theme()),
            ("workspace", lambda: self._workspace.refresh_theme()),
        ):
            try:
                fn()
            except Exception:
                logger.debug("MainWindow.refresh_theme(%s) 中忽略异常", step, exc_info=True)

    def _show_about(self) -> None:
        c = get_colors()
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("menu.help.about"))
        dlg.setFixedSize(LAYOUT["about_width"], LAYOUT["about_height"])
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
            f"font-size: {SIZE_SUBTITLE}px; font-weight: 700; color: {c['fg_primary']};")
        layout.addWidget(name)

        ver = QLabel(f"v{tr('app.version')}")
        ver.setStyleSheet(
            f"font-size: {SIZE_BODY_S}px; color: {c['fg_hint']};")
        layout.addWidget(ver)

        layout.addSpacing(12)

        desc = QLabel(tr("window.about.description"))
        desc.setStyleSheet(
            f"font-size: {SIZE_BODY_S}px; color: {c['fg_secondary']};")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addStretch()

        link = QLabel(
            '<a href="https://github.com/Aspy1/DailyTask" '
            f'style="color: {c['accent_text']};text-decoration:none;">'
            f'{tr("window.about.github_link")}</a>')
        link.setOpenExternalLinks(True)
        link.setStyleSheet(f"font-size: {SIZE_CAPTION}px;")
        layout.addWidget(link)

        dlg.exec()


    @staticmethod
    def _statusbar_qss(c: dict) -> str:
        return f"""
            QStatusBar {{
                background-color: {c['status_bar_bg']};
                color: {c['fg_secondary']}; font-size: {SIZE_CAPTION}px;
                border-top: 1px solid {c['border']};
                padding: 4px 16px;
            }}
            QLabel {{ color: {c['fg_secondary']}; font-size: {SIZE_CAPTION}px; border: none; background: transparent; }}
        """

    def _setup_statusbar(self) -> None:
        _install_statusbar(self)


    def _connect_ai(self) -> None:
        self._ai_panel.message_sent.connect(self._on_ai_message)
        self._ai_service.response_received.connect(
            self._on_ai_response)
        self._ai_service.error_occurred.connect(self._on_ai_error)
        self._ai_service.instructions_executed.connect(
            self._on_instructions_done)

        self._workspace._schedule_view.arrange_requested.connect(
            self._on_quick_arrange)


    def _on_ai_message(self, text: str) -> None:
        if not self._ai_visible:
            self._on_ai_toggle(True)
        self._ai_panel.set_status(True, thinking=True)
        self._ai_service.send_message(text)

    def _on_ai_response(self, text: str) -> None:
        """Handle AI text response. Route arrange results through arrange_pending check."""
        if getattr(self, '_arrange_pending', False):
            self._arrange_pending = False
            self._course_info_label.setText(tr("window.arrange.done"))
            self._workspace._schedule_view.on_arrange_done(True, "")
        self._ai_panel.append_message_ai(text)

    def _on_quick_arrange(self, prompt: str) -> None:
        """Handle schedule quick-arrange: send to AI, execute instructions, notify view."""
        sv = self._workspace._schedule_view
        self._course_info_label.setText(tr("window.arrange.progress"))
        self._arrange_pending = True
        try:
            self._ai_service.send_message(prompt)
        except Exception as e:  # noqa: BLE001
            self._arrange_pending = False
            self._course_info_label.setText(tr("window.arrange.failed", err=e))
            sv.on_arrange_done(False, str(e))

    def _on_ai_error(self, error_msg: str) -> None:
        if getattr(self, '_arrange_pending', False):
            self._arrange_pending = False
            self._course_info_label.setText(
                tr("window.arrange.failed", err=error_msg))
            self._workspace._schedule_view.on_arrange_done(False, error_msg)
            return
        self._ai_panel.append_message("ai", tr("window.ai.error", err=error_msg))
        self._ai_panel._on_response_done()

    def _on_instructions_done(self, text: str, instructions: list) -> None:
        if getattr(self, '_arrange_pending', False):
            self._arrange_pending = False
            self._course_info_label.setText(
                tr("window.arrange.done_count", n=len(instructions)))
            self._workspace._schedule_view.on_arrange_done(True, "")
            return
        self._ai_panel.append_message("ai", text)
        self._ai_panel._on_response_done()


    def _refresh_status(self) -> None:
        self._update_date()
        self._update_next_course()
        self._update_expense()
        self._update_habit_count()
        self._update_exam_alert()

    def _on_data_changed(self, _action: str = "") -> None:
        """数据变更时刷新状态栏（`data_changed` 带一个字符串参数，故用带参槽）。"""
        self._refresh_status()


    def _on_weather_updated(self, data: dict) -> None:
        """天气数据更新"""
        if data:
            temp = data.get("temp", "?")
            text = data.get("text", "?")
            self._weather_label.setText(
                tr("window.status.weather", temp=temp, text=text))

    def _on_weather_click(self) -> None:
        """点击天气标签，显示详细天气"""
        dialog = WeatherDetailDialog(self._weather_service, self)
        dialog.exec()

    def _update_date(self) -> None:
        now = datetime.now()
        self._render_semester()
        day_names = [tr(k) for k in ("day.monday", "day.tuesday", "day.wednesday",
                                     "day.thursday", "day.friday", "day.saturday",
                                     "day.sunday")]
        self._date_label.setText(
            f"{day_names[now.weekday()]} {now.strftime('%H:%M')}  |  {date.today().isoformat()}")

    def _render_semester(self) -> None:
        """状态栏的学期片段（**唯一口径**见 `models/semester.py`）。

        此前这里自己算周次且**不钳上界** —— 学期过期后显示"第 32 / 16 周"这种没意义的数字。
        现在过期/未开学/数据异常会直接说明状态，并用强调色提示"点我处理"。
        """
        c = get_colors()
        status = self._data_manager.courses.semester_status()
        self._semester_label.setText(semester_state_text(status))
        alert = status.get("state") in ALERT_STATES
        self._semester_label.setStyleSheet(
            f"color: {c['accent_text'] if alert else c['fg_secondary']}; font-size: {SIZE_CAPTION}px;"
            + (" font-weight: 600;" if alert else ""))

    def _on_semester_click(self) -> None:
        dialog = SemesterDialog(self._data_manager, self)
        if dialog.exec():
            self._render_semester()
            self._workspace.schedule_view.refresh_theme()

    def _update_next_course(self) -> None:
        if self._showing_tomorrow:
            self._update_tomorrow_preview()
            return
        today_courses = self._data_manager.courses.get_today_courses()
        if not today_courses:
            self._course_info_label.setText(tr("status.no_course"))
            return
        entries = self._build_course_entries(today_courses)
        if not entries:
            self._course_info_label.setText(tr("status.no_course"))
            return
        now = datetime.now().time()
        past_midnight = schedule_date() != date.today()
        self._course_info_label.setText(
            self._make_next_course_text(entries, now, past_midnight))

    @staticmethod
    def _build_course_entries(courses: list) -> list[tuple]:
        """把课程列表解析为 (开始时间, 结束时间, 课程) 并按开始时间排序。"""
        entries = []
        for c in courses:
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
        entries.sort(key=lambda e: e[0])
        return entries

    @staticmethod
    def _make_next_course_text(entries: list[tuple], now: time,
                               past_midnight: bool) -> str:
        """生成状态栏「今日课程/下一节课」文案。"""
        total = len(entries)
        finished = total if past_midnight else sum(
            1 for e in entries if e[1] < now)
        upcoming = None
        if not past_midnight:
            for start_t, _end_t, course in entries:
                if start_t > now:
                    upcoming = (start_t, course)
                    break
        if upcoming is None:
            return tr("window.status.course_all_done", total=total,
                      finished=finished)
        start_t, course = upcoming
        name = course.get("name", "")
        return tr("window.status.course_next", total=total, finished=finished,
                  name=name, start=start_t.strftime('%H:%M'))

    def _update_tomorrow_preview(self) -> None:
        c = get_colors()
        from datetime import datetime as dt
        from datetime import time as dt_time
        from datetime import timedelta

        tomorrow = schedule_date() + timedelta(days=1)
        courses = self._data_manager.courses.get_courses_for_date(tomorrow)
        day_name = [tr(k) for k in ("day.monday", "day.tuesday", "day.wednesday",
                                    "day.thursday", "day.friday", "day.saturday",
                                    "day.sunday")][tomorrow.weekday()]

        threshold = (tomorrow + timedelta(days=2)).isoformat()
        pending = self._data_manager.tasks.pending
        urgent = [t for t in pending
                  if t.get("due_date", "") and t["due_date"] < threshold]
        ddl_text = tr("window.status.ddl_count", n=len(urgent)) if urgent else ""

        if not courses:
            self._course_info_label.setText(
                tr("window.status.tomorrow_no_course", day=day_name, ddl=ddl_text))
            return

        first = courses[0]
        slots = first.get("time_slots") or []
        try:
            first_start = PERIOD_TIMES[int(slots[0]["start"]) - 1][0]
        except (IndexError, KeyError, TypeError, ValueError):
            first_start = "08:30"          # 坏数据不崩，按最早一节处理
        is_early = first_start <= "08:30"

        start_t = dt_time.fromisoformat(first_start)
        wake_dt = dt.combine(schedule_date(), start_t) - timedelta(minutes=30)
        wake_time = wake_dt.strftime("%H:%M")

        prefix = tr("window.status.tomorrow_prefix", day=day_name,
                    n=len(courses))
        if is_early:
            text = (
                f'{prefix}<span style="color:{c['red']};">'
                f'{tr("window.status.need_early")}</span>'
                + tr("window.status.tomorrow_early", first=first_start,
                     wake=wake_time, ddl=ddl_text)
            )
        else:
            text = prefix + tr("window.status.tomorrow_normal",
                               first=first_start, ddl=ddl_text)

        self._course_info_label.setText(text)

    def _toggle_day_view(self) -> None:
        self._showing_tomorrow = not self._showing_tomorrow
        self._refresh_status()

    def _update_expense(self) -> None:
        total = self._data_manager.expenses.today_total()
        count_to(self._expense_label, total, fmt="¥{:.0f}")

    
    def _update_habit_count(self) -> None:
        today_habits = [h for h in self._data_manager.habits.habits
                        if self._data_manager.habits.is_active_today(h["id"])]
        done = sum(1 for h in today_habits
                   if self._data_manager.habits.is_done_today(h["id"]))
        total = len(today_habits)
        c3 = get_colors()
        if total > 0:
            self._habit_count_label.setText(
                tr("window.status.habit_count", done=done, total=total))
            self._habit_count_label.setStyleSheet(f"color: {c3['green'] if done == total else c3['fg_secondary']}; font-size: {SIZE_CAPTION}px; padding: 0 3px;")
        else:
            self._habit_count_label.setText(tr("window.status.habit_none"))
            self._habit_count_label.setStyleSheet(f"color: {c3['fg_hint']}; font-size: {SIZE_CAPTION}px; padding: 0 3px;")

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
        self._exam_alert_label.setText(tr("window.status.exam_count", n=count))
        self._exam_alert_label.setStyleSheet(
            f"color: {color}; font-size: {SIZE_CAPTION}px; font-weight: 600; padding: 0 3px;")
        self._exam_alert_label.show()

    def _on_exam_alert_click(self) -> None:
        self._workspace.switch_to("exams")

    def _on_ddl_alert_click(self) -> None:
        self._workspace.show_ddl_tasks()

    def set_ddl_alert(self, count: int) -> None:
        c = get_colors()
        if count > 0:
            self._ddl_alert_label.setText(tr("window.status.ddl_alert", n=count))
            self._ddl_alert_label.setStyleSheet(
                f"color: {c['red']}; font-size: {SIZE_CAPTION}px; font-weight: 600;"
                f"padding: 0 3px;")
            self._ddl_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self._ddl_alert_label.setText(tr("window.status.ddl_none"))
            self._ddl_alert_label.setStyleSheet(
                f"color: {c['fg_hint']}; font-size: {SIZE_CAPTION}px;"
                f"padding: 0 3px;")
            self._ddl_alert_label.setCursor(Qt.CursorShape.ArrowCursor)
        self._ddl_alert_label.show()

    @property
    def ai_panel(self) -> AIPanel:
        return self._ai_panel

    def shutdown(self) -> None:
        """退出前停掉本窗口的定时器与后台线程（不等 QThread 会报 still running）。"""
        self._status_timer.stop()
        self._weather_service.shutdown()
