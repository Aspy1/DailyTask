"""Application singleton with system tray support and single-instance lock."""

import contextlib
import ctypes
import logging
import sys
import winreg
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from src.i18n.loader import t as i18n
from src.i18n.loader import tr
from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.services.git_sync import GitSync
from src.services.plugin_manager import PluginManager
from src.services.reminder_service import ReminderService
from src.services.settings_manager import SettingsManager, migrate_legacy_scene_location
from src.services.single_instance import (
    BAD_REQUEST_MESSAGE,
    SINGLE_INSTANCE_KEY,
    decode_request,
    encode_reply,
)
from src.ui.main_window import MainWindow
from src.ui.styles.theme import FONT_CN, SIZE_TITLE, init_theme

DATA_DIR = Path(__file__).parent.parent / "data"
# 单实例通道的 key 与委派协议见 `src/services/single_instance.py`
# （CLI 也要用同一个 key，所以别在这儿重定义 —— 见 PLAN.md P17 阶段 3）
REGISTRY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REGISTRY_NAME = "StudentScheduler"


logger = logging.getLogger(__name__)


def configure_locale() -> None:
    """把 Qt 默认区域固定为**用 ASCII 数字**的区域（本机 zh_HK 会出问题）。

    实现已移到 `ui/styles/theme.py`（由 `init_theme()` 统一调用，任何 UI 入口都覆盖），
    这里保留同名入口，方便"启动即设置"的语义更显式。
    """
    from src.ui.styles.theme import configure_locale as _configure

    _configure()


def _get_startup_command() -> str:
    """Build the command line for auto-start (uses pythonw to avoid console)."""
    main_py = str(Path(__file__).parent.parent / "main.py")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if pythonw.exists():
        return f'"{pythonw}" "{main_py}"'
    return f'"{sys.executable}" "{main_py}"'


def set_autostart(enabled: bool) -> None:
    """Write or remove the Windows registry Run entry for auto-start."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_RUN_KEY, 0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
        )
    except OSError:
        return

    try:
        if enabled:
            winreg.SetValueEx(key, APP_REGISTRY_NAME, 0, winreg.REG_SZ, _get_startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_REGISTRY_NAME)
            except OSError:
                logger.debug("set_autostart 中忽略异常", exc_info=True)
    finally:
        key.Close()


_RESOURCES_DIR = Path(__file__).parent.parent / "resources"
_ICON_PATH = _RESOURCES_DIR / "image.png"


def _make_icon(color: str = "#007acc") -> QIcon:  # token-check: ignore（图标底色，非 QSS）
    if _ICON_PATH.exists():
        pm = QPixmap(str(_ICON_PATH))
        if not pm.isNull():
            # 48x48 is the best size for Windows taskbar — larger sizes cause distortion
            return QIcon(pm.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    font = QFont(FONT_CN, SIZE_TITLE)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))  # token-check: ignore（图标绘制，非 QSS）
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    painter.end()
    return QIcon(pixmap)


class App(QApplication):
    def __init__(self, args: list[str]) -> None:
        # 必须在任何控件创建前：本机 zh_HK 会让日期/数字控件显示 CJK 数字
        configure_locale()
        super().__init__(args)

        # Single-instance: try to contact existing instance
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        sock = QLocalSocket()
        sock.connectToServer(SINGLE_INSTANCE_KEY)
        if sock.waitForConnected(1000):
            sock.disconnectFromServer()
            sock.close()
            self.is_secondary = True
            return
        sock.close()
        self.is_secondary = False

        self.setApplicationName(tr("app.name"))
        self.setQuitOnLastWindowClosed(False)

        # Windows: 设置 AppUserModelID 让任务栏图标正确（失败不影响运行）
        with contextlib.suppress(Exception):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LifeAssistant.StudentScheduler")

        app_icon = _make_icon()
        self._icon_normal = app_icon
        self._icon_alert = _make_icon("#e74856")  # token-check: ignore（告警图标，非 QSS）
        self.setWindowIcon(app_icon)

        self._settings = SettingsManager(DATA_DIR / "settings.ini")
        self._settings.load()
        # 场景功能已弃用：把旧场景里的位置迁到天气设置（一次性、幂等）
        migrate_legacy_scene_location(DATA_DIR, self._settings)

        i18n.load(self._settings.get("General", "language", "zh-CN"))

        theme_mode = self._settings.get("General", "theme", "dark")
        qss = init_theme(self, theme_mode)
        self.setStyleSheet(qss)

        # Sync auto-start registry entry on every launch
        set_autostart(self._settings.get_bool("General", "auto_start"))

        self._data_manager = DataManager(DATA_DIR)
        self._ai_service = AIService(self._settings, self._data_manager)
        self._reminder = ReminderService(self._settings, self._data_manager)
        self._reminder.reminder_notify.connect(self._show_reminder_notify)
        self._reminder.ddl_alert.connect(self._on_ddl_alert)
        self._git_sync = GitSync(DATA_DIR.parent, DATA_DIR, self)
        self._data_manager.data_changed.connect(self._git_sync.on_data_changed)
        self._git_sync.sync_status.connect(self._on_sync_status)

        # 插件管理器：扫描 ./plugins 并加载可注册的面板工厂
        plugins_dir = Path(__file__).parent.parent / "plugins"
        self._plugin_manager = PluginManager(plugins_dir, self._settings, self._data_manager, self)
        self._plugin_manager.load_plugins()

        self._window = MainWindow(self._settings, self._ai_service, self._data_manager, self._plugin_manager)
        self._data_manager.save_conflict.connect(self._on_save_conflict)
        self._window.setWindowIcon(app_icon)

        self._setup_tray(app_icon)  # tray must be ready before window shows (auto-start behavior)

        self._window.show()  # show with tray already present

        # Flash state (before reminder.start() — _on_ddl_alert uses _flash_timer)
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash_tick)
        self._flash_on = False
        self._ddl_count = 0

        self._reminder.start()  # after _window + _flash_timer exist

        self._instance_server = QLocalServer(self)
        if not self._instance_server.listen(SINGLE_INSTANCE_KEY):
            self.is_secondary = True
            return
        self._instance_server.newConnection.connect(self._on_second_instance)

    def _on_second_instance(self) -> None:
        """有进程连上来：带命令的（CLI 委派）执行后回结果；空手的（第二次启动）前置窗口。"""
        sock = self._instance_server.nextPendingConnection()
        if sock is None:
            return
        sock.readyRead.connect(lambda s=sock: self._on_instance_message(s))
        sock.disconnected.connect(lambda s=sock: self._on_instance_closed(s))

    def _on_instance_message(self, sock) -> None:
        """收到一行请求 `{"argv": [...]}` → 执行（与 CLI/AI 同一条路径）+ 重载 + 回结果。"""
        from scripts.actions import run_argv_in_process

        argv = decode_request(bytes(sock.readAll()).decode("utf-8", "replace").strip())
        if argv is None:
            sock.write(encode_reply(False, f"ERROR {BAD_REQUEST_MESSAGE}"))
            sock.flush()
            return
        sock.setProperty("delegated", True)
        out = run_argv_in_process(argv)
        self._data_manager.reload_all()
        self._data_manager.data_changed.emit("ai_action")
        sock.write(encode_reply(True, out))
        sock.flush()
        sock.disconnectFromServer()

    def _on_instance_closed(self, sock) -> None:
        if not sock.property("delegated"):
            self._bring_to_front()      # 第二次启动：只把窗口叫出来
        sock.deleteLater()

    def _show_reminder_notify(self, title: str, body: str) -> None:
        if hasattr(self, "_tray") and self._tray.supportsMessages():
            self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 8000)

    def _manual_sync(self) -> None:
        self._git_sync.sync_now()

    def _on_sync_status(self, status: str) -> None:
        if status == "syncing":
            if hasattr(self, "_tray"):
                self._tray.setToolTip(f"{tr('app.name')}{tr('app.sync.syncing')}")
        elif status.startswith("done"):
            if hasattr(self, "_tray"):
                self._tray.setToolTip(f"{tr('app.name')}{tr('app.sync.synced')}")
                self._tray.showMessage(tr("app.sync.done_title"), tr("app.sync.done_body"),
                                       QSystemTrayIcon.MessageIcon.Information, 3000)
        elif status == "idle":
            if hasattr(self, "_tray"):
                self._tray.setToolTip(tr("app.name"))
        elif status.startswith("error") and hasattr(self, "_tray"):
            self._tray.setToolTip(f"{tr('app.name')}{tr('app.sync.failed')}")

    def _on_ddl_alert(self, count: int) -> None:
        self._ddl_count = count
        self._window.set_ddl_alert(count)
        if count > 0:
            if not self._flash_timer.isActive():
                self._flash_timer.start(800)  # toggle every 800ms
        else:
            self._flash_timer.stop()
            if hasattr(self, "_tray"):
                self._tray.setIcon(self._icon_normal)

    def _flash_tick(self) -> None:
        if not hasattr(self, "_tray"):
            return
        self._flash_on = not self._flash_on
        self._tray.setIcon(self._icon_alert if self._flash_on else self._icon_normal)

    def _bring_to_front(self) -> None:
        if self._window.isMinimized():
            self._window.showNormal()
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _setup_tray(self, icon: QIcon) -> None:
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(tr("app.name"))

        tray_menu = QMenu()
        show_action = QAction(tr("tray.show"), self)
        show_action.triggered.connect(self._window.show)
        tray_menu.addAction(show_action)
        hide_action = QAction(tr("tray.hide"), self)
        hide_action.triggered.connect(self._window.hide)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        sync_action = QAction(tr("app.sync.to_github"), self)
        sync_action.triggered.connect(self._manual_sync)
        tray_menu.addAction(sync_action)
        restart_action = QAction(tr("tray.restart"), self)
        restart_action.triggered.connect(self._restart)
        tray_menu.addAction(restart_action)
        quit_action = QAction(tr("tray.exit"), self)
        quit_action.triggered.connect(self.quit)
        tray_menu.addAction(quit_action)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._bring_to_front()

    def _on_save_conflict(self, name: str, path: str) -> None:
        """保存冲突：磁盘上这份数据被别人改过 → 没覆盖，留了副本（审查 2026-10-17 #1）。"""
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(self._window, tr("window.save_conflict.title"),
                            tr("window.save_conflict.body", name=name, path=path))

    def _restart(self) -> None:
        self._data_manager.flush_on_exit()
        self._settings.save()
        self._window.hide()
        self._instance_server.close()
        from PySide6.QtCore import QProcess
        QProcess.startDetached(sys.executable, sys.argv)
        self.quit()

    def quit(self) -> None:
        self._data_manager.flush_on_exit()
        self._settings.save()
        self._window.close()
        super().quit()
