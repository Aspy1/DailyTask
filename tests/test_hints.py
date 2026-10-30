"""「今日提示」的天气规则（C 类第 3 项）。

设计见 `src/services/hints.py`：提示由**代码规则**产生（不让模型判断该不该带伞 ✗），
而且是**纯函数**（好测、不碰界面）。
"""

import json
from datetime import datetime

from src.services.hints import Hint, is_rain, load_weather, today_hints, weather_hints

# 固定一个**不在吃饭窗口**的时刻（否则"空目录也该是空列表"那条会随跑测试的时间变红 ✗）
MORNING = datetime(2026, 10, 30, 9, 0)


def test_rain_codes_give_an_umbrella_hint() -> None:
    """下雨类代码（Open-Meteo 51-67 / 80-82 / 95-99）→ 带伞提示。"""
    for code in (51, 61, 65, 80, 82, 95, 99):
        assert is_rain(code) is True, code
        hints = weather_hints({"weathercode": code, "temp": 20})
        assert any("带伞" in h.text for h in hints), code
    for code in (0, 1, 3, 45, 71):      # 晴 / 多云 / 雾 / 雪 → 不提示带伞
        assert is_rain(code) is False, code


def test_temperature_hints() -> None:
    assert any("防暑" in h.text for h in weather_hints({"weathercode": 0, "temp": 36}))
    assert any("保暖" in h.text for h in weather_hints({"weathercode": 0, "temp": -3}))
    assert weather_hints({"weathercode": 0, "temp": 20}) == [], "温和天气不提示"


def test_no_weather_means_no_hints() -> None:
    assert weather_hints(None) == []
    assert weather_hints({}) == []


def test_hints_have_stable_keys() -> None:
    """`key` 是幂等键 —— 同一条提示今天只出现一次（界面靠它去重/记住点掉了）。"""
    hints = weather_hints({"weathercode": 61, "temp": 20})
    assert all(isinstance(h, Hint) and h.key for h in hints)
    assert hints[0].key == "weather.rain"


def test_today_hints_reads_the_cache(tmp_path) -> None:
    (tmp_path / "weather_cache.json").write_text(
        json.dumps({"now": {"weathercode": 61, "temp": 12}}), encoding="utf-8")
    assert load_weather(tmp_path)[0]["temp"] == 12
    assert any("带伞" in h.text for h in today_hints(tmp_path, now=MORNING))
    assert today_hints(tmp_path / "空目录", now=MORNING) == [], "读不到缓存就不提示（不报错）"
