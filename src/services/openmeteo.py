"""Open-Meteo 天气适配器（**唯一**实现，无需 API key）。

**为什么单独成模块**：此前天气能力有 3 套实现（CODE_STANDARDS Q-A3）——
和风天气（`weather_service.py`）、Open-Meteo（`api_service.py` 内联）、
以及 `ai_service.py` 内联的 Open-Meteo 请求；"天气码 → 中文"映射还重复了两份。

现在各能力的归属：
- 和风天气（需 key，带配额/缓存）→ `weather_service.py`
- Open-Meteo（免 key，回退用）→ **本模块**（唯一实现）
- 天气码 → 中文映射 → 本模块（唯一一份）

调用方：`api_service._ApiWorker`（界面"API 测试"弹窗）与 `ai_service`（提示词回退路径）。

对外契约：`fetch_text_for_ai()` **永不抛异常**（失败返回可读提示文本），
因为它的消费方是"拼进 AI 提示词"的路径，不能因天气挂掉而中断。
"""

import logging
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_LAT = 31.23
DEFAULT_LON = 121.47
TIMEOUT = 5

# WMO 4677 天气码 → 中文（Open-Meteo 用的就是这套码）
WEATHER_CODES: dict[int, str] = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
    45: "雾", 48: "霜雾",
    51: "小毛毛雨", 53: "中毛毛雨", 55: "大毛毛雨",
    56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "中阵雨", 82: "大阵雨",
    85: "小阵雪", 86: "大阵雪",
    95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
}


def weather_code_to_text(code: int) -> str:
    """天气码 → 中文描述（未知码返回"未知"）。"""
    return WEATHER_CODES.get(code, "未知")


def _request(lat: float, lon: float, days: int, timeout: int = TIMEOUT) -> dict[str, Any]:
    """请求 Open-Meteo（失败时抛 requests/OSError 异常，由调用方决定文案）。"""
    resp = requests.get(API_URL, params={
        "latitude": lat,
        "longitude": lon,
        "current_weather": True,
        "hourly": "temperature_2m,relativehumidity_2m,weathercode,precipitation_probability",
        "timezone": "Asia/Shanghai",
        "forecast_days": days,
    }, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_current(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON,
                  timeout: int = TIMEOUT) -> dict[str, Any]:
    """当前天气（同步）。失败时抛异常，由调用方决定呈现方式。"""
    resp = requests.get(API_URL, params={
        "latitude": lat,
        "longitude": lon,
        "current_weather": True,
        "hourly": "temperature_2m,relativehumidity_2m,weathercode",
        "timezone": "Asia/Shanghai",
        "forecast_days": 1,
    }, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    current = data.get("current_weather", {})
    hourly = data.get("hourly", {})
    code = (hourly.get("weathercode") or [0])[0]
    return {
        "temperature": (hourly.get("temperature_2m") or [0])[0],
        "humidity": (hourly.get("relativehumidity_2m") or [0])[0],
        "weather_code": code,
        "wind_speed": current.get("windspeed", 0),
        "weather_text": weather_code_to_text(code),
        "location": f"{lat:.2f}°N, {lon:.2f}°E",
        "timestamp": datetime.now().isoformat(),
    }


def format_for_ai(data: dict[str, Any], days: int = 3) -> str:
    """把响应整理为「当前 + 未来 N 天」天气文本（纯函数，便于测试）。"""
    current = data.get("current_weather", {})
    hourly = data.get("hourly", {})

    temp = current.get("temperature", "?")
    wind = current.get("windspeed", "?")
    wtext = weather_code_to_text(current.get("weathercode", 0))
    lines = [f"  当前: {wtext}, {temp}°C, 风速{wind}km/h"]

    temps = hourly.get("temperature_2m", [])
    codes = hourly.get("weathercode", [])
    times = hourly.get("time", [])
    if temps and codes and times:
        seen_days: set[str] = set()
        for i, stamp in enumerate(times):
            if i >= len(temps) or i >= len(codes) or len(seen_days) >= days:
                break
            dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            day_key = dt.strftime("%m-%d")
            if day_key in seen_days:
                continue
            seen_days.add(day_key)
            lines.append(f"  {day_key}: {weather_code_to_text(codes[i])}, {temps[i]}°C")

    return "\n".join(lines)


def fetch_text_for_ai(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON,
                      days: int = 3) -> str:
    """取「当前 + 未来 N 天」天气文本给 AI 用；**永不抛异常**。"""
    try:
        data = _request(lat, lon, days)
    except requests.HTTPError:
        logger.warning("Open-Meteo 返回非 2xx", exc_info=True)
        return "  天气查询失败"
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.debug("Open-Meteo 请求失败", exc_info=True)
        return f"  天气信息暂不可用 ({e})"
    return format_for_ai(data, days=days)
