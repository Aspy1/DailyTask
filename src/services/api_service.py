"""外部 API 服务 —— Qt 异步外壳（天气 / DeepSeek 余额）。

**职责边界（CODE_STANDARDS Q-A3）**：本模块只负责"起线程 + 发信号"，
真正的 HTTP 与解析在**共享适配器**里，各只有一份实现：

- 天气 → `src/services/openmeteo.py`（`fetch_current`）
- 余额 → `src/services/deepseek.py`（`fetch_balance`）

此前本模块自带一份天气码映射与一份余额解析，和 `ai_service` 内的实现重复。
"""

from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from src.services import deepseek, openmeteo


class _ApiWorker(QThread):
    """异步 API 请求 Worker"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, api_type: str, **kwargs: Any) -> None:
        super().__init__()
        self._api_type = api_type
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            if self._api_type == "weather":
                result = openmeteo.fetch_current(**self._kwargs)
            elif self._api_type == "deepseek_balance":
                result = deepseek.fetch_balance(**self._kwargs)
            else:
                result = {"error": f"Unknown API type: {self._api_type}"}
            self.finished.emit(result)
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class ApiService(QObject):
    """外部 API 服务封装（异步）。"""

    weather_ready = Signal(dict)
    balance_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._weather_cache: dict | None = None
        self._weather_cache_time: datetime | None = None
        self._balance_cache: dict | None = None
        self._balance_cache_time: datetime | None = None
        self._current_worker: _ApiWorker | None = None

    def fetch_weather(self, lat: float = openmeteo.DEFAULT_LAT,
                      lon: float = openmeteo.DEFAULT_LON) -> None:
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

    def _run_worker(self, api_type: str, **kwargs: Any) -> None:
        """启动后台请求。

        不再使用 `QThread.terminate()`（强制终止线程不安全，见 CODE_STANDARDS Q-B3）。
        改为：旧请求自然跑完，其结果在回调中按 `sender()` 丢弃。
        """
        worker = _ApiWorker(api_type, **kwargs)
        self._current_worker = worker
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()

    def _on_worker_finished(self, result: dict) -> None:
        """Worker 完成回调"""
        if self.sender() is not self._current_worker:
            return  # 旧请求的结果，丢弃
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
