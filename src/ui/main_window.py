"""Main window — sidebar + content area layout (warm-paper design)."""

from datetime import date, datetime, time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QLabel, QPushButton, QMessageBox, QMenu, QApplication,
    QDialog, QFrame,
)
from PySide6.QtGui import QAction, QFont, QPalette

from src.i18n.loader import tr
from src.models.course import PERIOD_TIMES, schedule_date
from src.ui.styles.theme import get_colors
from src.services.settings_manager import SettingsManager
from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.services.weather_service import WeatherService
from src.ui.components.main_workspace import MainWorkspace
from src.ui.components.click_label import ClickLabel
from src.ui.components.sidebar import Sidebar
from src.ui.components.ai_panel import AIPanel


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager, ai_service: AIService,
                 data_manager: DataManager, plugin_manager=None):
        super().__init__()
        self.setWindowTitle(tr("app.name"))
        self.setMinimumSize(990, 638)
        self.resize(1210, 792)

        self._settings = settings
        self._ai_service = ai_service
        self._data_manager = data_manager
        self._plugin_manager = plugin_manager
        self._ai_visible = False
        self._arrange_pending = False

        # 天气服务
        self._weather_service = WeatherService()
        if settings.weather_api_key and settings.weather_api_host:
            self._weather_service.set_credentials(
                settings.weather_api_host, settings.weather_api_key)
            if settings.weather_auto_update:
                self._weather_service.start_auto_update()
        self._weather_service.weather_updated.connect(self._on_weather_updated)

        # 将天气服务传递给AI服务
        ai_service.set_weather_service(self._weather_service)

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
            cp.table.fill_ai_prompt.connect(self._on_course_fill_ai)

    def _on_course_fill_ai(self, prompt: str) -> None:
        if not self._ai_visible:
            self._on_ai_toggle(True)
        self._ai_panel.fill_input(prompt)

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
        sep1.setStyleSheet(f"color: {c['border_strong']}; margin: 0 5px;")
        self._statusbar.addPermanentWidget(sep1)

        self._ddl_alert_label = ClickLabel()
        self._ddl_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ddl_alert_label.setStyleSheet(
            f"color: {c['red']}; font-size: 12px; font-weight: 600;"
            f"padding: 0 3px;")
        self._ddl_alert_label.clicked.connect(self._on_ddl_alert_click)
        self._ddl_alert_label.hide()
        self._statusbar.addPermanentWidget(self._ddl_alert_label)

        sep2 = QLabel("|")
        sep2.setStyleSheet(f"color: {c['border_strong']}; margin: 0 5px;")
        self._statusbar.addPermanentWidget(sep2)

        self._habit_count_label = QLabel()
        self._statusbar.addPermanentWidget(self._habit_count_label)

        sep3 = QLabel("|")
        sep3.setStyleSheet(f"color: {c['border_strong']}; margin: 0 5px;")
        self._statusbar.addPermanentWidget(sep3)

        self._exam_alert_label = ClickLabel()
        self._exam_alert_label.setStyleSheet(
            f"color: {c['orange']}; font-size: 12px; font-weight: 600; padding: 0 3px;")
        self._exam_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exam_alert_label.clicked.connect(self._on_exam_alert_click)
        self._statusbar.addPermanentWidget(self._exam_alert_label)

        sep_exam = QLabel("|")
        sep_exam.setStyleSheet(f"color: {c['border_strong']}; margin: 0 5px;")
        self._statusbar.addPermanentWidget(sep_exam)

        # 天气显示
        self._weather_label = ClickLabel()
        self._weather_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._weather_label.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 12px;")
        self._weather_label.clicked.connect(self._on_weather_click)
        self._weather_label.setText("天气: --")
        self._statusbar.addPermanentWidget(self._weather_label)

        sep_weather = QLabel("|")
        sep_weather.setStyleSheet(f"color: {c['border_strong']}; margin: 0 5px;")
        self._statusbar.addPermanentWidget(sep_weather)

        self._date_label = QLabel()
        self._statusbar.addPermanentWidget(self._date_label)

        self._showing_tomorrow = False


    def _connect_ai(self) -> None:
        self._ai_panel.message_sent.connect(self._on_ai_message)
        self._ai_service.response_received.connect(
            self._on_ai_response)
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

    def _on_ai_response(self, text: str) -> None:
        """Handle AI text response. Route arrange results through arrange_pending check."""
        if getattr(self, '_arrange_pending', False):
            self._arrange_pending = False
            self._course_info_label.setText("日程调整完成")
            self._workspace._schedule_view.on_arrange_done(True, "AI 已响应")
        self._ai_panel.append_message_ai(text)

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

    # ── Weather ───────────────────────────────────────────────

    def _on_weather_updated(self, data: dict) -> None:
        """天气数据更新"""
        if data:
            temp = data.get("temp", "?")
            text = data.get("text", "?")
            self._weather_label.setText(f"天气: {temp}°C {text}")

    def _on_weather_click(self) -> None:
        """点击天气标签，显示详细天气"""
        dialog = WeatherDetailDialog(self._weather_service, self)
        dialog.exec()

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
        c3 = get_colors()
        if total > 0:
            self._habit_count_label.setText(f"日常{done}/{total}")
            self._habit_count_label.setStyleSheet(f"color: {c3['green'] if done == total else c3['fg_secondary']}; font-size: 12px; padding: 0 3px;")
        else:
            self._habit_count_label.setText("今日无事")
            self._habit_count_label.setStyleSheet(f"color: {c3['fg_hint']}; font-size: 12px; padding: 0 3px;")

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
            f"color: {color}; font-size: 12px; font-weight: 600; padding: 0 3px;")
        self._exam_alert_label.show()

    def _on_exam_alert_click(self) -> None:
        self._workspace.switch_to("exams")

    def _update_shopping(self) -> None:
        if not hasattr(self, '_shopping_label'):
            return
        c2 = get_colors()
        needs = self._data_manager.inventory.need_restock
        if needs:
            self._shopping_label.setText(f"需购{len(needs)}")
            self._shopping_label.setStyleSheet(
                f"color: {c2['red']}; font-size: 12px; font-weight: 600; padding: 0 3px;")
            self._shopping_label.show()
        else:
            self._shopping_label.hide()

    def _on_ddl_alert_click(self) -> None:
        self._workspace.show_ddl_tasks()

    def set_ddl_alert(self, count: int) -> None:
        c = get_colors()
        if count > 0:
            self._ddl_alert_label.setText(f"DDL {count}")
            self._ddl_alert_label.setStyleSheet(
                f"color: {c['red']}; font-size: 12px; font-weight: 600;"
                f"padding: 0 3px;")
            self._ddl_alert_label.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self._ddl_alert_label.setText("暂无DDL")
            self._ddl_alert_label.setStyleSheet(
                f"color: {c['fg_hint']}; font-size: 12px;"
                f"padding: 0 3px;")
            self._ddl_alert_label.setCursor(Qt.CursorShape.ArrowCursor)
        self._ddl_alert_label.show()

    @property
    def ai_panel(self) -> AIPanel:
        return self._ai_panel


class WeatherDetailDialog(QDialog):
    """天气详情对话框（支持刷新后自动更新）"""

    def __init__(self, weather_service, parent=None):
        super().__init__(parent)
        self._ws = weather_service
        c = get_colors()

        self.setWindowTitle("天气详情")
        self.setMinimumWidth(360)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_card']}; }}
            QLabel {{ background: transparent; border: none; }}
        """)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(16)

        # 标题栏
        title_row = QHBoxLayout()
        self._title = QLabel("天气详情")
        self._title.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {c['fg_primary']};")
        title_row.addWidget(self._title)

        # 最后更新时间
        self._update_time_label = QLabel()
        self._update_time_label.setStyleSheet(
            f"font-size: 11px; color: {c['fg_hint']}; margin-left: 8px;")
        title_row.addWidget(self._update_time_label)
        title_row.addStretch()

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['accent']};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            QPushButton:disabled {{
                background-color: {c['fg_hint']};
                color: {c['bg_card']};
            }}
        """)
        self._refresh_btn.clicked.connect(self._on_refresh)
        title_row.addWidget(self._refresh_btn)
        self._layout.addLayout(title_row)

        # 实时天气区域
        self._now_card = None
        self._temp_label = None
        self._info_label = None
        self._hum_label = None
        self._wind_label = None
        self._no_data_label = None

        # 预报区域
        self._forecast_rows = []  # 保存预报行的引用

        # 首次加载
        self._build_ui()
        self._update_content()

        # 连接信号
        self._ws.weather_updated.connect(self._update_content)
        self._ws.forecast_updated.connect(self._update_content)

    def _build_ui(self):
        """构建UI结构"""
        c = get_colors()
        self._layout.removeWidget(self._no_data_label) if self._no_data_label else None

        # 实时天气卡片
        if self._now_card:
            self._layout.removeWidget(self._now_card)
        self._now_card = QFrame()
        self._now_card.setStyleSheet(f"""
            QFrame {{ background-color: {c['bg_elevated']}; border-radius: 8px; padding: 12px; }}
        """)
        card_layout = QVBoxLayout(self._now_card)
        card_layout.setSpacing(8)

        self._temp_label = QLabel()
        self._temp_label.setStyleSheet(
            f"font-size: 28px; font-weight: 700; color: {c['fg_primary']};")
        card_layout.addWidget(self._temp_label)

        self._info_label = QLabel()
        self._info_label.setStyleSheet(
            f"font-size: 14px; color: {c['fg_secondary']};")
        card_layout.addWidget(self._info_label)

        row = QHBoxLayout()
        row.setSpacing(16)
        self._hum_label = QLabel()
        self._hum_label.setStyleSheet(f"font-size: 13px; color: {c['fg_hint']};")
        row.addWidget(self._hum_label)

        self._wind_label = QLabel()
        self._wind_label.setStyleSheet(f"font-size: 13px; color: {c['fg_hint']};")
        row.addWidget(self._wind_label)
        row.addStretch()
        card_layout.addLayout(row)

        self._layout.insertWidget(1, self._now_card)

        # 预报标题
        self._forecast_title = QLabel("未来3天预报")
        self._forecast_title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {c['fg_primary']};")
        self._layout.insertWidget(2, self._forecast_title)

        # 预报行（3天）
        for i in range(3):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(12)

            date_lbl = QLabel()
            date_lbl.setStyleSheet(
                f"font-size: 13px; color: {c['fg_secondary']}; min-width: 80px;")
            row_layout.addWidget(date_lbl)

            text_lbl = QLabel()
            text_lbl.setStyleSheet(f"font-size: 13px; color: {c['fg_primary']};")
            row_layout.addWidget(text_lbl)

            rain_lbl = QLabel()
            rain_lbl.setStyleSheet(f"font-size: 12px; color: {c['accent']};")
            row_layout.addWidget(rain_lbl)

            temp_lbl = QLabel()
            temp_lbl.setStyleSheet(
                f"font-size: 13px; color: {c['fg_secondary']};")
            temp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row_layout.addWidget(temp_lbl)

            self._layout.insertWidget(3 + i, row_layout.itemAt(0).widget())
            self._forecast_rows.append({
                "date": date_lbl,
                "text": text_lbl,
                "rain": rain_lbl,
                "temp": temp_lbl
            })

    def _update_content(self):
        """更新内容"""
        c = get_colors()

        # 更新最后更新时间
        now_cache_time = self._ws._now_cache_time
        if now_cache_time:
            self._update_time_label.setText(f"最后更新: {now_cache_time.strftime('%H:%M')}")
        else:
            self._update_time_label.setText("")

        # 恢复刷新按钮状态
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("刷新")

        # 更新实时天气
        now = self._ws.get_now()
        if now:
            if self._now_card:
                self._now_card.show()
            if self._temp_label:
                self._temp_label.setText(f"{now.get('temp', '?')}°C")
            if self._info_label:
                self._info_label.setText(
                    f"{now.get('text', '?')}  ·  体感 {now.get('feelsLike', '?')}°C")
            if self._hum_label:
                self._hum_label.setText(f"湿度 {now.get('humidity', '?')}%")
            if self._wind_label:
                self._wind_label.setText(
                    f"{now.get('windDir', '?')} {now.get('windScale', '?')}级")
        else:
            if self._now_card:
                self._now_card.hide()

        # 更新预报
        forecast = self._ws.get_forecast()
        for i, row in enumerate(self._forecast_rows):
            if i < len(forecast):
                day = forecast[i]
                row["date"].setText(day.get('fxDate', '?'))
                row["text"].setText(day.get('textDay', '?'))
                precip = day.get('precip', '0')
                if precip and float(precip) > 0:
                    row["rain"].setText(f"雨量{precip}mm")
                    row["rain"].show()
                else:
                    row["rain"].hide()
                row["temp"].setText(
                    f"{day.get('tempMin', '?')}°C ~ {day.get('tempMax', '?')}°C")
            else:
                row["date"].setText("")
                row["text"].setText("")
                row["rain"].hide()
                row["temp"].setText("")

    def _on_refresh(self):
        """刷新按钮点击"""
        # 禁用按钮并显示加载状态
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("...")
        # 触发刷新
        self._ws.refresh()

    def closeEvent(self, event):
        """关闭时断开信号连接"""
        try:
            self._ws.weather_updated.disconnect(self._update_content)
            self._ws.forecast_updated.disconnect(self._update_content)
        except RuntimeError:
            pass
        super().closeEvent(event)
