"""Main window — PCL-style top nav + content area."""

from datetime import date, datetime, time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QLabel, QPushButton, QMessageBox, QMenu, QButtonGroup,
)
from PySide6.QtGui import QAction, QFont, QPalette

from src.i18n.loader import tr
from src.models.course import PERIOD_TIMES, schedule_date
from src.ui.styles.theme import get_colors
from src.services.settings_manager import SettingsManager
from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.ui.components.main_workspace import MainWorkspace
from src.ui.components.ai_panel import AIPanel

NAV_HEIGHT = 50


class _ClickLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)
        self.clicked.emit()


class NavButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager, ai_service: AIService, data_manager: DataManager, plugin_manager=None):
        super().__init__()
        self.setWindowTitle(tr("app.name"))
        self.setMinimumSize(900, 580)
        self.resize(1100, 720)

        self._settings = settings
        self._ai_service = ai_service
        self._data_manager = data_manager
        self._plugin_manager = plugin_manager
        self._ai_visible = False

        self._setup_ui()
        self._setup_statusbar()
        self._connect_ai()
        self._connect_course_table()

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(30_000)
        self._refresh_status()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top nav ──────────────────────────────────────────
        nav = QWidget()
        nav.setObjectName("topNav")
        nav.setFixedHeight(NAV_HEIGHT)
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(16, 8, 16, 8)
        nav_layout.setSpacing(4)

        # App name
        name_label = QLabel(tr("app.name"))
        name_label.setFont(QFont(self.font().family(), 13))
        name_label.setStyleSheet("font-weight: 600; border: none; padding: 0 12px 0 0;")
        nav_layout.addWidget(name_label)

        # Nav tabs
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        tabs = [("学习", "study"), ("生活", "life"), ("小功能", "widgets"), ("设置", "settings"), ("更多", "more")]
        for label, tab_id in tabs:
            btn = NavButton(label)
            btn.clicked.connect(lambda checked, tid=tab_id: self._on_nav(tid))
            nav_layout.addWidget(btn)
            self._nav_group.addButton(btn)
            if tab_id == "study":
                btn.setChecked(True)
                self._current_nav = "study"

        nav_layout.addStretch()

        # AI toggle
        self._ai_toggle_btn = NavButton("AI")
        self._ai_toggle_btn.clicked.connect(self._toggle_ai_panel)
        nav_layout.addWidget(self._ai_toggle_btn)

        root.addWidget(nav)

        # ── Content area ─────────────────────────────────────
        self._workspace = MainWorkspace(self._settings, self._ai_service, self._data_manager, self._plugin_manager)
        self._ai_panel = AIPanel()
        self._ai_panel.hide()

        self._content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._content_splitter.addWidget(self._workspace)
        self._content_splitter.addWidget(self._ai_panel)
        self._content_splitter.setSizes([800, 0])
        self._content_splitter.setHandleWidth(1)
        c = get_colors()
        self._content_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {c['border']}; }}")

        root.addWidget(self._content_splitter, stretch=1)

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        self._next_course_label = _ClickLabel()
        self._next_course_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_course_label.setToolTip("点击切换今日/明日")
        self._next_course_label.clicked.connect(self._toggle_day_view)
        self._statusbar.addWidget(self._next_course_label)

        self._ddl_alert_label = _ClickLabel()
        self._ddl_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
        c = get_colors()
        self._ddl_alert_label.setStyleSheet(
            f"color: #fff; background-color: {c['red']}; border-radius: 4px; "
            "padding: 1px 8px; font-weight: 600; font-size: 11px;"
        )
        self._ddl_alert_label.setToolTip("点击查看即将截止的任务")
        self._ddl_alert_label.clicked.connect(self._on_ddl_alert_click)
        self._ddl_alert_label.hide()
        self._statusbar.addWidget(self._ddl_alert_label)

        self._date_label = QLabel()
        self._statusbar.addPermanentWidget(self._date_label)
        self._expense_label = QLabel()
        self._statusbar.addPermanentWidget(self._expense_label)

        self._showing_tomorrow = False

    def _connect_ai(self) -> None:
        self._ai_panel.message_sent.connect(self._on_ai_message)
        self._ai_service.response_received.connect(self._ai_panel.append_message_ai)
        self._ai_service.error_occurred.connect(self._on_ai_error)
        self._ai_service.instructions_executed.connect(self._on_instructions_done)

    def _connect_course_table(self) -> None:
        cp = self._workspace.course_panel
        if cp is not None:
            cp.table.fill_ai_prompt.connect(self._ai_panel.fill_input)

    # ── Navigation ──────────────────────────────────────────

    def _on_nav(self, tab_id: str) -> None:
        self._current_nav = tab_id
        if tab_id == "more":
            self._show_more_menu()
            return
        self._workspace.switch_to(tab_id)

    def _show_more_menu(self) -> None:
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
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
        btn = self._nav_group.buttons()[-1]
        menu.aboutToHide.connect(lambda: btn.setChecked(False))
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _switch_theme(self, mode: str) -> None:
        from src.ui.styles.theme import switch_theme
        self._settings.set("General", "theme", mode)
        self._settings.save()
        # Apply stylesheet on the QApplication so it cascades to all windows/widgets
        from PySide6.QtWidgets import QApplication
        qss = switch_theme(mode)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)

        # Refresh theme-aware panels
        try:
            self._ai_panel.refresh_theme()
        except Exception:
            pass
        try:
            if hasattr(self, "_workspace") and hasattr(self._workspace, "refresh_theme"):
                self._workspace.refresh_theme()
        except Exception:
            pass

    def _toggle_theme(self) -> None:
        current = self._settings.get("General", "theme", "dark")
        new_theme = "light" if current == "dark" else "dark"
        self._switch_theme(new_theme)

    def _toggle_ai_panel(self) -> None:
        self._ai_visible = not self._ai_visible
        if self._ai_visible:
            self._ai_panel.show()
            self._content_splitter.setSizes([self.width() - 340, 340])
            self._ai_toggle_btn.setChecked(True)
        else:
            self._ai_panel.hide()
            self._content_splitter.setSizes([self.width(), 0])
            self._ai_toggle_btn.setChecked(False)

    def _show_about(self) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle(tr("menu.help.about"))
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            f"<b>{tr('app.name')} v{tr('app.version')}</b><br><br>"
            f"AI 驱动的学生时间管理与生活助手<br><br>"
            f"<a href='https://github.com/Aspy1/DailyTask'>GitHub 仓库</a><br>"
            f"<a href='https://github.com/Aspy1/DailyTask/commits/master'>开发日志（GitHub）</a>"
        )
        msg.exec()

    # ── AI ──────────────────────────────────────────────────

    def _on_ai_message(self, text: str) -> None:
        if not self._ai_visible:
            self._toggle_ai_panel()
        self._ai_panel.set_status(True, thinking=True)
        self._ai_service.send_message(text)

    def _on_ai_error(self, error_msg: str) -> None:
        self._ai_panel.append_message("ai", f"错误: {error_msg}")
        self._ai_panel._on_response_done()

    def _on_instructions_done(self, text: str, instructions: list) -> None:
        self._ai_panel.append_message("ai", text)
        self._ai_panel._on_response_done()

    # ── Status bar ──────────────────────────────────────────

    def _refresh_status(self) -> None:
        self._update_date()
        self._update_next_course()
        self._update_expense()

    def _update_date(self) -> None:
        now = datetime.now()
        semester = self._data_manager.courses.get_semester(self._data_manager.courses.current_semester)
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
        self._date_label.setText(f"{week_str}{day_names[now.weekday()]} {now.strftime('%H:%M')}")

    def _update_next_course(self) -> None:
        if self._showing_tomorrow:
            self._update_tomorrow_preview()
            return
        today_courses = self._data_manager.courses.get_today_courses()
        now = datetime.now().time()
        past_midnight = schedule_date() != date.today()
        if not today_courses:
            self._next_course_label.setText(tr("status.no_course"))
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
            entries.append((time.fromisoformat(start_str), time.fromisoformat(end_str), c))
        if not entries:
            self._next_course_label.setText(tr("status.no_course"))
            return
        entries.sort(key=lambda e: e[0])
        total = len(entries)
        finished = total if past_midnight else sum(1 for e in entries if e[1] < now)
        upcoming = None
        if not past_midnight:
            for start_t, end_t, course in entries:
                if start_t > now:
                    upcoming = (start_t, course)
                    break
        if upcoming is None:
            self._next_course_label.setText(f"共{total}节课，已上{finished}节，今日课已上完  ▸")
            return
        start_t, course = upcoming
        name = course.get("name", "")
        self._next_course_label.setText(
            f"共{total}节课，已上{finished}节，下一节: {name} {start_t.strftime('%H:%M')}  ▸"
        )

    def _update_tomorrow_preview(self) -> None:
        c = get_colors()
        from datetime import timedelta, datetime as dt, time as dt_time

        tomorrow = schedule_date() + timedelta(days=1)
        courses = self._data_manager.courses.get_courses_for_date(tomorrow)
        day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][tomorrow.weekday()]

        # DDL
        threshold = (tomorrow + timedelta(days=2)).isoformat()
        pending = self._data_manager.tasks.pending
        urgent = [t for t in pending if t.get("due_date", "") and t["due_date"] < threshold]
        ddl_text = f"  |  {len(urgent)}项DDL" if urgent else ""

        if not courses:
            self._next_course_label.setText(
                f"⏎ 明日({day_name}): 无课  |  不用早起{ddl_text}  ▸"
            )
            return

        first = courses[0]
        slots = first.get("time_slots", [])
        first_start = PERIOD_TIMES[slots[0]["start"] - 1][0] if slots else "08:30"
        is_early = first_start <= "08:30"

        # Wake-up time: 30 min before first class
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

        self._next_course_label.setText(text)

    def _toggle_day_view(self) -> None:
        self._showing_tomorrow = not self._showing_tomorrow
        self._refresh_status()

    def _update_expense(self) -> None:
        total = self._data_manager.expenses.today_total()
        self._expense_label.setText(f"{tr('status.today_expense')}: ¥{total:.2f}")

    def _on_ddl_alert_click(self) -> None:
        self._on_nav("study")
        self._workspace.show_ddl_tasks()

    def set_ddl_alert(self, count: int) -> None:
        if count > 0:
            self._ddl_alert_label.setText(f" {count} 项任务即将截止 ")
            self._ddl_alert_label.show()
        else:
            self._ddl_alert_label.hide()

    @property
    def ai_panel(self) -> AIPanel:
        return self._ai_panel
