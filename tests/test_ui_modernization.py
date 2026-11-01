"""现代化改动的回归：侧边栏同步 / 窄窗口汇总卡 / 天气缓存 / 错误钩子。"""

import json
import logging
import sys

from src.services import weather_service
from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager
from src.ui.main_window import MainWindow


def _window(tmp_path, qapp) -> tuple[MainWindow, DataManager]:
    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    return MainWindow(settings, AIService(settings, dm), dm, None), dm


def test_programmatic_panel_switch_updates_sidebar(tmp_path, qapp) -> None:
    """状态栏 DDL/考试/课程跳转也要同步左侧高亮。"""
    mw, _dm = _window(tmp_path, qapp)
    mw._workspace.switch_to("inventory")
    assert mw._sidebar._current_nav == "inventory"


def test_expense_summary_wraps_in_narrow_window(tmp_path, qapp) -> None:
    """窄窗口 + AI 时 5 张汇总卡不能互相裁切。"""
    mw, _dm = _window(tmp_path, qapp)
    mw.resize(990, 638)
    mw.show()
    mw._workspace.switch_to("expenses")
    mw._on_ai_toggle(True)
    qapp.processEvents()
    panel = mw._workspace._expense_panel
    cards = [panel._sum_month, panel._sum_today, panel._sum_budget,
             panel._sum_saved, panel._forecast]
    for card in cards:
        assert card.width() >= card.minimumWidth()
    # 每张卡都在面板宽度内（不再被挤到可视区外）
    assert all(card.geometry().right() <= panel.width() for card in cards)


def test_weather_service_loads_offline_cache(tmp_path, qapp) -> None:
    cache = tmp_path / "weather_cache.json"
    cache.write_text(json.dumps({
        "now": {"temp": 12, "text": "小雨"},
        "now_time": "2026-11-01T11:30:00",
        "forecast": [{"fxDate": "2026-11-02", "textDay": "多云",
                      "tempMin": 9, "tempMax": 17, "precip": "0.0"}],
        "forecast_time": "2026-11-01T11:30:00",
    }), encoding="utf-8")
    svc = weather_service.WeatherService(data_dir=tmp_path)
    assert svc.get_now()["text"] == "小雨"
    assert svc.get_forecast()[0]["textDay"] == "多云"
    assert svc.get_now_updated_at().isoformat() == "2026-11-01T11:30:00"
    svc.shutdown()


def test_statusbar_shows_cached_weather_on_startup(tmp_path, qapp) -> None:
    (tmp_path / "weather_cache.json").write_text(json.dumps({
        "now": {"temp": 8, "text": "小雨"},
        "now_time": "2026-11-01T11:30:00",
        "forecast": [],
    }), encoding="utf-8")
    mw, _dm = _window(tmp_path, qapp)
    assert "小雨" in mw._weather_label.text()


def test_empty_state_action_is_clickable(qapp) -> None:
    from src.ui.widgets.empty_state import empty_state
    from src.ui.widgets.rounded_button import RoundedButton

    calls: list[bool] = []
    widget = empty_state("暂无内容", "点下面的按钮新建一条。", "新建",
                         lambda: calls.append(True))
    widget.show()
    qapp.processEvents()
    assert widget.width() >= 420
    button = widget.findChild(RoundedButton)
    assert button is not None
    button.click()
    assert calls == [True]
    widget.close()


def test_weather_dialog_does_not_repeat_window_title(qapp) -> None:
    from test_weather_dialog import FakeWeather

    from src.ui.widgets.weather_dialog import WeatherDetailDialog

    dlg = WeatherDetailDialog(FakeWeather())
    assert dlg._title.text() != dlg.windowTitle()
    dlg.close()


def test_task_table_sorting_stays_disabled(tmp_path, qapp) -> None:
    mw, _dm = _window(tmp_path, qapp)
    panel = mw._workspace._task_panel
    panel._refresh()
    assert panel._table.isSortingEnabled() is False


def test_error_hook_logs_unhandled_exception(caplog) -> None:
    from src.services import error_hook

    error_hook.install_exception_hooks()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        with caplog.at_level(logging.ERROR, logger=error_hook.LOGGER_NAME):
            sys.excepthook(*sys.exc_info())
    assert any("boom" in record.getMessage() for record in caplog.records)
