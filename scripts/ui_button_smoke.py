#!/usr/bin/env python
"""按钮级全量冒烟：**逐个点击**每个面板/侧边栏/状态栏/弹窗上的按钮。

与 `ui_walkthrough.py` 的区别：walkthrough 走"用户典型路径"，这里走**穷举**——
把 `QAbstractButton` 全部找出来点一遍，并捕获 Qt 槽里的异常。

安全：
- `QT_QPA_PLATFORM=offscreen`，数据目录是临时沙箱；
- `QDialog.exec` / `QMenu.exec` / `QMessageBox` / `QInputDialog` 全部替换成非阻塞替身；
- AI / 天气 / 邮件 / Git 等外部副作用在点击前替换成记录器。

用法：
    .venv/Scripts/python.exe scripts/ui_button_smoke.py
"""

import contextlib
import io
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path(tempfile.mkdtemp(prefix="lifeassistant-buttons-"))
os.environ["LIFE_ASSISTANT_DATA_DIR"] = str(SANDBOX)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
)

from scripts.ui_render import _seed  # noqa: E402
from src.services.ai_service import AIService  # noqa: E402
from src.services.api_service import ApiService  # noqa: E402
from src.services.data_manager import DataManager  # noqa: E402
from src.services.plugin_manager import PluginManager  # noqa: E402
from src.services.settings_manager import SettingsManager  # noqa: E402
from src.ui import animations  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402

ERRORS: list[dict] = []
CLICKED: list[str] = []


def _label(widget: QAbstractButton) -> str:
    name = widget.objectName() or "-"
    text = (widget.text() or "").replace("\n", " ")[:24]
    return f"{type(widget).__name__}({name}:{text})"


def _click(widget: QAbstractButton, context: str) -> None:
    """点一次；Qt 槽异常不一定抛出，所以同时捕获 stderr 里的 traceback。"""
    if widget is None:
        return
    try:
        from shiboken6 import isValid
        if not isValid(widget) or not widget.isEnabled():
            return
    except Exception:  # noqa: BLE001
        return
    CLICKED.append(f"{context} :: {_label(widget)}")
    buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(buf):
            widget.click()
        sys.stdout.flush()
    except Exception as exc:  # noqa: BLE001 - 冒烟要把异常收集起来而不是中断
        ERRORS.append({"context": context, "widget": _label(widget),
                       "error": "".join(traceback.format_exception(exc))})
    ERRORS_TEXT = buf.getvalue()
    if "Traceback (most recent call last)" in ERRORS_TEXT:
        ERRORS.append({"context": context, "widget": _label(widget),
                       "error": ERRORS_TEXT[-2000:]})


def _buttons(root) -> list[QAbstractButton]:
    return [w for w in root.findChildren(QAbstractButton)]


def _patch_environment(mw, ai) -> None:
    """把一切会阻塞/联网/落盘的副作用换成替身。"""
    from src.ui import main_window
    from src.ui.panels import (
        exam_panel,
        expense_panel,
        habit_panel,
        inventory_panel,
        task_panel,
    )
    from src.ui.widgets import course_table, menu, schedule_actions, schedule_view

    QDialog.exec = lambda self: 0
    QMenu.exec = lambda self, *a, **k: None
    # 菜单定位函数在多个模块里是**直接 import 的名字**，只 patch menu 模块不够；
    # 统一换成 no-op（否则 `QMenu.exec` 会进入模态循环，离屏脚本直接挂死）。
    for module in (main_window, exam_panel, expense_panel, habit_panel,
                   inventory_panel, task_panel, course_table, menu,
                   schedule_actions, schedule_view):
        for name in ("show_at", "show_at_cursor", "show_below"):
            if hasattr(module, name):
                setattr(module, name, lambda *a, **k: None)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
    ai.send_message = lambda text: None
    mw._weather_service.refresh = lambda: True
    ApiService.fetch_weather = lambda self, *a, **k: None
    ApiService.fetch_deepseek_balance = lambda self, *a, **k: None
    with contextlib.suppress(RuntimeError):
        mw._ai_panel.message_sent.disconnect()


def _smoke_dialogs(mw, dm) -> None:
    """已知的独立弹窗：构造后把里面的按钮点一遍。"""
    from src.services.weather_service import WeatherService
    from src.ui.panels.exam_panel import ExamDialog
    from src.ui.panels.habit_panel import HabitDialog
    from src.ui.panels.study_dialogs import (
        MistakeDialog,
        MockDialog,
        StudySessionDialog,
        StudyTargetDialog,
    )
    from src.ui.widgets.api_test_dialog import ApiTestDialog
    from src.ui.widgets.course_detail_dialog import CourseDetailDialog
    from src.ui.widgets.semester_dialog import SemesterDialog
    from src.ui.widgets.weather_dialog import WeatherDetailDialog

    factories = [
        ("dialog/semester", lambda: SemesterDialog(dm, mw)),
        ("dialog/habit", lambda: HabitDialog(dm, parent=mw)),
        ("dialog/exam", lambda: ExamDialog(parent=mw)),
        ("dialog/course", lambda: CourseDetailDialog(dm, "高等数学", mw)),
        ("dialog/api", lambda: ApiTestDialog(ApiService(), mw)),
        ("dialog/weather", lambda: WeatherDetailDialog(
            WeatherService(data_dir=dm.data_dir), mw)),
        ("dialog/study-session", lambda: StudySessionDialog(dm, mw)),
        ("dialog/study-mistake", lambda: MistakeDialog(dm, mw)),
        ("dialog/study-mock", lambda: MockDialog(dm, mw)),
        ("dialog/study-target", lambda: StudyTargetDialog(dm, mw)),
    ]
    for context, build in factories:
        try:
            dialog = build()
        except Exception as exc:  # noqa: BLE001
            ERRORS.append({"context": context + "/construct", "widget": "-",
                           "error": "".join(traceback.format_exception(exc))})
            continue
        dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        dialog.show()
        QApplication.processEvents()
        for button in _buttons(dialog):
            _click(button, context)
        dialog.close()
        dialog.deleteLater()
        QApplication.processEvents()


def _smoke_status_targets(mw) -> None:
    """底栏不是 QAbstractButton（ClickLabel），单独点它们的点击信号。"""
    for name, label in (
        ("status/weather", mw._weather_label),
        ("status/course", mw._course_info_label),
        ("status/ddl", mw._ddl_alert_label),
        ("status/exam", mw._exam_alert_label),
        ("status/semester", mw._semester_label),
    ):
        try:
            label.clicked.emit()
        except Exception as exc:  # noqa: BLE001
            ERRORS.append({"context": name, "widget": type(label).__name__,
                           "error": "".join(traceback.format_exception(exc))})
        QApplication.processEvents()


def main() -> int:
    import faulthandler
    faulthandler.dump_traceback_later(30, repeat=True)
    app = QApplication.instance() or QApplication([])
    animations.set_enabled(False)
    from src.ui.styles.theme import init_theme
    app.setStyleSheet(init_theme(app, "light"))

    settings = SettingsManager(SANDBOX / "settings.ini")
    settings.set("AI", "api_key", "sk-test-not-real")
    settings.save()
    dm = DataManager(SANDBOX)
    _seed(dm)
    ai = AIService(settings, dm)
    plugins = PluginManager(SANDBOX / "plugins", settings, dm, app)
    plugins.load_plugins()
    mw = MainWindow(settings, ai, dm, plugins)
    mw.resize(1200, 800)
    mw.show()
    _patch_environment(mw, ai)
    app.processEvents()

    # 侧边栏：每个导航项 + AI 开关 + 更多
    for button in _buttons(mw._sidebar):
        _click(button, "sidebar")
        app.processEvents()

    # 每个面板：切换过去，点它的全部按钮（包括隐藏的撤销/保存等）
    for key in mw._workspace._panel_map:
        try:
            mw._workspace.switch_to(key)
        except Exception as exc:  # noqa: BLE001
            ERRORS.append({"context": f"switch/{key}", "widget": "-",
                           "error": "".join(traceback.format_exception(exc))})
            continue
        app.processEvents()
        panel = mw._workspace._stack.currentWidget()
        for button in _buttons(panel):
            _click(button, f"panel/{key}")

    _smoke_status_targets(mw)
    _smoke_dialogs(mw, dm)

    mw.shutdown()
    mw.close()
    app.processEvents()
    print(f"buttons clicked: {len(CLICKED)}")
    print(f"errors: {len(ERRORS)}")
    for entry in ERRORS[:30]:
        print(f"\n[{entry['context']}] {entry['widget']}\n{entry['error'][-1200:]}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
