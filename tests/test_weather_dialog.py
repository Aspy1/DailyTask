"""天气详情弹窗 + QThread 生命周期回归（2026-11-01 用户报障）。"""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.services.weather_service import WeatherService
from src.ui.styles import theme
from src.ui.widgets.weather_dialog import WeatherDetailDialog

FORECAST = [
    {"fxDate": "2026-11-01", "textDay": "小雨", "tempMin": 8, "tempMax": 15,
     "precip": "0.0"},
    {"fxDate": "2026-11-02", "textDay": "多云", "tempMin": 9, "tempMax": 17,
     "precip": "0.0"},
    {"fxDate": "2026-11-03", "textDay": "晴", "tempMin": 10, "tempMax": 19,
     "precip": "0.0"},
]


class FakeWeather(QObject):
    weather_updated = Signal(dict)
    forecast_updated = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, now=None, forecast=None, refresh_ok=True) -> None:
        super().__init__()
        self._now = now or {}
        self._forecast = forecast or []
        self._refresh_ok = refresh_ok

    def get_now(self) -> dict:
        return self._now

    def get_now_updated_at(self) -> datetime:
        return datetime(2026, 11, 1, 11, 30)

    def get_forecast(self) -> list:
        return self._forecast

    def refresh(self) -> bool:
        if not self._refresh_ok:
            self.error_occurred.emit("未配置天气服务（测试替身）")
            return False
        return True


def test_forecast_rows_show_weather_text_and_temperature(qapp) -> None:
    """⭐ 回归：旧实现只把日期标签插进布局，天气/温度/降水标签是孤儿 → 只显示日期。"""
    dlg = WeatherDetailDialog(FakeWeather(
        now={"temp": 12, "text": "小雨", "feelsLike": 10, "humidity": 80,
             "windDir": "北", "windScale": "3"},
        forecast=FORECAST))
    dlg.show()
    qapp.processEvents()
    try:
        rows = dlg._forecast_rows
        assert rows[0]["date"].text() == "2026-11-01"
        assert rows[0]["text"].text() == "小雨"
        assert "8°C" in rows[0]["temp"].text() and "15°C" in rows[0]["temp"].text()
        assert rows[0]["text"].isVisible()
        assert rows[1]["text"].text() == "多云"
        assert rows[2]["text"].text() == "晴"
    finally:
        dlg.close()


def test_refresh_without_credentials_reenables_and_shows_reason(qapp) -> None:
    dlg = WeatherDetailDialog(FakeWeather(refresh_ok=False))
    dlg.show()
    qapp.processEvents()
    try:
        dlg._refresh_btn.click()
        qapp.processEvents()
        assert dlg._refresh_btn.isEnabled()
        assert dlg._refresh_btn.text() != "..."
        assert dlg._error_label.isVisible()
        assert "未配置" in dlg._error_label.text()
    finally:
        dlg.close()


def test_weather_service_refresh_without_credentials_returns_false(qapp, tmp_path) -> None:
    svc = WeatherService(data_dir=tmp_path)
    errors: list[str] = []
    svc.error_occurred.connect(errors.append)
    assert svc.refresh() is False
    assert errors and "未配置" in errors[-1]
    svc.shutdown()


def test_qthread_subclasses_do_not_shadow_finished() -> None:
    """⭐ 自定义结果信号不能叫 finished（会遮蔽 QThread.finished → 线程运行中被删）。"""
    from src.services.api_service import _ApiWorker
    from src.services.git_sync import _GitWorker
    from src.services.weather_service import WeatherWorker

    for cls in (WeatherWorker, _ApiWorker, _GitWorker):
        assert "finished" not in cls.__dict__, cls
    assert "result" in WeatherWorker.__dict__ and "failed" in WeatherWorker.__dict__
    assert "result" in _ApiWorker.__dict__ and "failed" in _ApiWorker.__dict__
    assert "done" in _GitWorker.__dict__


def test_translation_dirs_contain_a_real_qm() -> None:
    """翻译目录不能只信 `QLibraryInfo`（本机可能指向 anaconda 的 Qt）。"""
    dirs = theme._translation_dirs()
    assert any((Path(p) / "qt_zh_CN.qm").exists() for p in dirs), dirs


def test_install_translations_keeps_a_reference(qapp) -> None:
    theme._install_qt_translations(qapp)
    assert getattr(qapp, "_qt_translator", None) is not None
