"""天气/余额适配的守卫（CODE_STANDARDS Q-A3：同一外部能力只保留一套适配）。

背景：此前天气有 3 套实现（和风 / Open-Meteo 内联在 `api_service` / `ai_service` 内联），
天气码映射重复两份；余额也有两份（`api_service` 与 `ai_service` 各一份 HTTP 解析）。
现在统一到 `services/openmeteo.py`（天气）与 `services/deepseek.py`（余额），
`api_service` 退化为只起线程的 Qt 外壳。
"""

from pathlib import Path

import pytest

from src.services import openmeteo

ROOT = Path(__file__).resolve().parent.parent


def test_weather_code_to_text_known_and_unknown() -> None:
    assert openmeteo.weather_code_to_text(0) == "晴"
    assert openmeteo.weather_code_to_text(63) == "中雨"
    assert openmeteo.weather_code_to_text(12345) == "未知"


def test_format_for_ai_current_and_days() -> None:
    payload = {
        "current_weather": {"temperature": 21.5, "windspeed": 8.0, "weathercode": 61},
        "hourly": {
            "time": ["2026-10-16T08:00", "2026-10-16T09:00", "2026-10-17T08:00"],
            "temperature_2m": [20, 21, 19],
            "weathercode": [61, 61, 0],
        },
    }
    text = openmeteo.format_for_ai(payload, days=3)
    lines = text.splitlines()
    assert lines[0] == "  当前: 小雨, 21.5°C, 风速8.0km/h"
    assert lines[1] == "  10-16: 小雨, 20°C"      # 同一天只取一次
    assert lines[2] == "  10-17: 晴, 19°C"


def test_format_for_ai_tolerates_empty_payload() -> None:
    assert openmeteo.format_for_ai({}).startswith("  当前: 晴")


def test_fetch_text_for_ai_never_raises_on_http_error(monkeypatch) -> None:
    import requests

    def boom(*_a: object, **_kw: object) -> None:
        raise requests.HTTPError("500")

    monkeypatch.setattr(openmeteo, "_request", boom)
    assert openmeteo.fetch_text_for_ai() == "  天气查询失败"


def test_fetch_text_for_ai_never_raises_on_os_error(monkeypatch) -> None:
    def boom(*_a: object, **_kw: object) -> None:
        raise OSError("no network")

    monkeypatch.setattr(openmeteo, "_request", boom)
    assert openmeteo.fetch_text_for_ai().startswith("  天气信息暂不可用")


@pytest.mark.parametrize("needle", ["小毛毛雨", "强雷暴伴冰雹"])
def test_weather_code_mapping_has_single_implementation(needle: str) -> None:
    """Q-A3 守卫：天气码→中文映射只能存在于一个模块。"""
    hits = [f.relative_to(ROOT).as_posix()
            for f in (ROOT / "src").rglob("*.py")
            if needle in f.read_text(encoding="utf-8")]
    assert hits == ["src/services/openmeteo.py"], hits


def test_open_meteo_endpoint_defined_once() -> None:
    """Q-A3 守卫：Open-Meteo 的 URL 只能出现一处。"""
    hits = [f.relative_to(ROOT).as_posix()
            for f in (ROOT / "src").rglob("*.py")
            if "api.open-meteo.com" in f.read_text(encoding="utf-8")]
    assert hits == ["src/services/openmeteo.py"], hits


def test_ai_service_delegates_to_shared_adapter() -> None:
    """AI 侧不得再自带天气码映射 / 内联 Open-Meteo / 内联余额解析。"""
    src = (ROOT / "src/services/ai_service.py").read_text(encoding="utf-8")
    assert "openmeteo.fetch_text_for_ai" in src
    assert "deepseek.fetch_balance" in src
    assert "def _weather_code_to_text" not in src
    assert "api.open-meteo.com" not in src
    assert "api.deepseek.com/user/balance" not in src


def test_api_service_is_only_a_qt_shell() -> None:
    """`api_service` 只负责起线程 + 发信号，不得再自带 HTTP 解析。"""
    src = (ROOT / "src/services/api_service.py").read_text(encoding="utf-8")
    assert "openmeteo.fetch_current" in src
    assert "deepseek.fetch_balance" in src
    assert "api.open-meteo.com" not in src
    assert "api.deepseek.com/user/balance" not in src
    assert "def _weather_code_to_text" not in src


def test_deepseek_balance_endpoint_defined_once() -> None:
    """Q-A3 守卫：DeepSeek 余额接口只能出现一处。"""
    hits = [f.relative_to(ROOT).as_posix()
            for f in (ROOT / "src").rglob("*.py")
            if "api.deepseek.com/user/balance" in f.read_text(encoding="utf-8")]
    assert hits == ["src/services/deepseek.py"], hits


def test_fetch_balance_guards_placeholder_key() -> None:
    """占位 key 不发请求，直接返回 config 类错误。"""
    from src.services import deepseek

    result = deepseek.fetch_balance("sk-...")
    assert result["error_kind"] == "config"
    assert "error" in result


def test_fetch_current_shape(monkeypatch) -> None:
    """`fetch_current` 的返回结构必须满足 API 测试弹窗的字段契约。"""
    from src.services import openmeteo

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "current_weather": {"temperature": 20.0, "windspeed": 5.0, "weathercode": 3},
                "hourly": {"temperature_2m": [19.5], "relativehumidity_2m": [60],
                           "weathercode": [3]},
            }

    monkeypatch.setattr(openmeteo.requests, "get", lambda *a, **kw: _Resp())
    result = openmeteo.fetch_current(31.23, 121.47)

    assert set(result) == {"temperature", "humidity", "weather_code", "wind_speed",
                           "weather_text", "location", "timestamp"}
    assert result["weather_text"] == "阴"
    assert result["humidity"] == 60
