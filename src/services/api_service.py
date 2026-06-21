"""外部 API 服务 - 天气预报、DeepSeek 额度查询"""

import json
from datetime import datetime
from typing import Any

import requests
from PySide6.QtCore import QObject, Signal, QThread

from src.ui.styles.theme import get_colors


class _ApiWorker(QThread):
    """异步 API 请求 Worker"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, api_type: str, **kwargs):
        super().__init__()
        self._api_type = api_type
        self._kwargs = kwargs

    def run(self):
        try:
            if self._api_type == "weather":
                result = _fetch_weather_sync(**self._kwargs)
            elif self._api_type == "deepseek_balance":
                result = _fetch_deepseek_balance_sync(**self._kwargs)
            else:
                result = {"error": f"Unknown API type: {self._api_type}"}
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


def _fetch_weather_sync(lat: float = 31.23, lon: float = 121.47) -> dict[str, Any]:
    """同步获取天气预报（使用 Open-Meteo API，无需 API key）"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True,
        "hourly": "temperature_2m,relativehumidity_2m,weathercode",
        "timezone": "Asia/Shanghai",
        "forecast_days": 1,
    }
    resp = requests.get(url, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    current = data.get("current_weather", {})
    hourly = data.get("hourly", {})

    # 获取当前小时数据
    time_idx = 0
    temp = hourly.get("temperature_2m", [0])[time_idx]
    humidity = hourly.get("relativehumidity_2m", [0])[time_idx]
    weather_code = hourly.get("weathercode", [0])[time_idx]

    return {
        "temperature": temp,
        "humidity": humidity,
        "weather_code": weather_code,
        "wind_speed": current.get("windspeed", 0),
        "weather_text": _weather_code_to_text(weather_code),
        "location": f"{lat:.2f}°N, {lon:.2f}°E",
        "timestamp": datetime.now().isoformat(),
    }


def _fetch_deepseek_balance_sync(api_key: str) -> dict[str, Any]:
    """同步获取 DeepSeek 余额"""
    if not api_key or api_key.startswith("sk-..."):
        return {"error": "请先配置有效的 API Key"}

    url = "https://api.deepseek.com/user/balance"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    resp = requests.get(url, headers=headers, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    balance_infos = data.get("balance_infos", [])
    total_balance = 0.0
    for info in balance_infos:
        total_balance += float(info.get("total_balance", 0))

    return {
        "total_balance": total_balance,
        "currency": "CNY",
        "balance_infos": balance_infos,
        "is_available": total_balance > 0,
        "timestamp": datetime.now().isoformat(),
    }


def _weather_code_to_text(code: int) -> str:
    """天气代码转中文描述"""
    mapping = {
        0: "晴",
        1: "晴间多云",
        2: "多云",
        3: "阴",
        45: "雾",
        48: "霜雾",
        51: "小毛毛雨",
        53: "中毛毛雨",
        55: "大毛毛雨",
        56: "冻毛毛雨",
        57: "强冻毛毛雨",
        61: "小雨",
        63: "中雨",
        65: "大雨",
        66: "冻雨",
        67: "强冻雨",
        71: "小雪",
        73: "中雪",
        75: "大雪",
        77: "雪粒",
        80: "小阵雨",
        81: "中阵雨",
        82: "大阵雨",
        85: "小阵雪",
        86: "大阵雪",
        95: "雷暴",
        96: "雷暴伴冰雹",
        99: "强雷暴伴冰雹",
    }
    return mapping.get(code, "未知")


class ApiService(QObject):
    """外部 API 服务封装"""

    weather_ready = Signal(dict)
    balance_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._weather_cache: dict | None = None
        self._weather_cache_time: datetime | None = None
        self._balance_cache: dict | None = None
        self._balance_cache_time: datetime | None = None
        self._current_worker: _ApiWorker | None = None

    def fetch_weather(self, lat: float = 31.23, lon: float = 121.47) -> None:
        """异步获取天气预报（30分钟缓存）"""
        # 检查缓存（30分钟有效）
        if self._weather_cache and self._weather_cache_time:
            age = (datetime.now() - self._weather_cache_time).total_seconds()
            if age < 1800:  # 30分钟
                self.weather_ready.emit(self._weather_cache)
                return

        # 发起请求
        self._run_worker("weather", lat=lat, lon=lon)

    def fetch_deepseek_balance(self, api_key: str) -> None:
        """异步获取 DeepSeek 余额（每次强制刷新）"""
        self._run_worker("deepseek_balance", api_key=api_key)

    def _run_worker(self, api_type: str, **kwargs) -> None:
        """运行 Worker"""
        # 取消之前的请求
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.terminate()
            self._current_worker.wait()

        self._current_worker = _ApiWorker(api_type, **kwargs)
        self._current_worker.finished.connect(self._on_worker_finished)
        self._current_worker.error.connect(self._on_worker_error)
        self._current_worker.start()

    def _on_worker_finished(self, result: dict) -> None:
        """Worker 完成回调"""
        if "temperature" in result:  # 天气数据
            self._weather_cache = result
            self._weather_cache_time = datetime.now()
            self.weather_ready.emit(result)
        elif "total_balance" in result or "error" in result:  # 余额数据
            self._balance_cache = result
            self._balance_cache_time = datetime.now()
            self.balance_ready.emit(result)

    def _on_worker_error(self, error: str) -> None:
        """Worker 错误回调"""
        self.error_occurred.emit(error)

    def get_weather_sync(self, lat: float = 31.23, lon: float = 121.47) -> dict[str, Any]:
        """同步获取天气（用于测试）"""
        try:
            return _fetch_weather_sync(lat, lon)
        except Exception as e:
            return {"error": str(e)}

    def get_balance_sync(self, api_key: str) -> dict[str, Any]:
        """同步获取余额（用于测试）"""
        try:
            return _fetch_deepseek_balance_sync(api_key)
        except Exception as e:
            return {"error": str(e)}
