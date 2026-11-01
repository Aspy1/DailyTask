"""和风天气服务"""
import contextlib
from datetime import datetime
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QThread, QTimer, Signal

from src.services import weather_store
from src.services.paths import get_data_dir

# 绝对路径：应用可能被自启（CWD 非项目根），禁止用相对 "data/..."（见 CODE_STANDARDS Q-E2）
_DATA_DIR = get_data_dir()
_STATS_FILE = _DATA_DIR / "weather_stats.json"
_CACHE_FILE = _DATA_DIR / "weather_cache.json"


class WeatherWorker(QThread):
    """天气 API 请求工作线程。

    ⚠ 自定义信号**不能叫 `finished` / `error`**：`QThread` 自带 `finished`，
    子类同名信号会把它**遮蔽**。旧代码 `worker.finished.connect(worker.deleteLater)`
    连的是自定义信号（在 `run()` 里发出、此时线程还没结束）→ QThread 在运行中被删，
    触发 `QThread: Destroyed while thread '' is still running`（2026-11-01 用户日志）。
    清理必须连 **QThread.finished**（线程真正结束后才发）。
    """

    result = Signal(dict, str)  # (data, api_type)
    failed = Signal(str, str)  # (error_msg, api_type)

    def __init__(self, host: str, key: str, location: str, api_type: str,
                 stats_file: Path) -> None:
        super().__init__()
        self._host = host
        self._key = key
        self._location = location
        self._api_type = api_type
        self._stats_file = stats_file

    def run(self) -> None:
        try:
            if self._api_type == "now":
                url = f"https://{self._host}/v7/weather/now?location={self._location}&key={self._key}"
            elif self._api_type == "7d":
                url = f"https://{self._host}/v7/weather/7d?location={self._location}&key={self._key}"
            else:
                self.failed.emit(f"未知API类型: {self._api_type}", self._api_type)
                return

            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "200":
                    self.result.emit(data, self._api_type)
                    # 记录调用统计
                    self._record_request()
                else:
                    self.failed.emit(f"API返回错误: {data.get('code')}", self._api_type)
            else:
                self.failed.emit(f"HTTP错误: {resp.status_code}", self._api_type)
        except Exception as e:  # noqa: BLE001
            # 边界捕获：Worker 线程入口，异常经信号回传，不允许逃逸（Q-I1）
            self.failed.emit(str(e), self._api_type)

    def _record_request(self) -> None:
        """记录 API 调用次数（原子写 + 加锁，见 `services/weather_store.py`）。"""
        weather_store.record_request(self._stats_file, self._api_type)


class WeatherService(QObject):
    """和风天气服务"""
    # 信号
    weather_updated = Signal(dict)  # 实时天气更新
    forecast_updated = Signal(list)  # 7天预报更新
    error_occurred = Signal(str)  # 错误
    quota_warning = Signal(str)  # 调用次数警告

    # 缓存时间（秒）
    CACHE_NOW = 600      # 10分钟
    CACHE_7D = 21600     # 6小时

    # 调用限制
    DAILY_LIMIT = 1000
    MONTHLY_WARN = 45000
    MONTHLY_LIMIT = 49900

    # 位置并入天气设置（settings.ini [Weather] lat/lon）；未配置时用默认值
    DEFAULT_LAT = "31.23"
    DEFAULT_LON = "121.47"

    def __init__(self, settings=None, data_dir: Path | None = None) -> None:
        super().__init__()
        # 数据目录可注入：应用传 DataManager.data_dir，测试传 tmp_path。
        # 不注入时退回模块默认（仓库 data/），与旧行为一致。
        self._data_dir = Path(data_dir) if data_dir is not None else _DATA_DIR
        self._cache_file = self._data_dir / "weather_cache.json"
        self._stats_file = self._data_dir / "weather_stats.json"
        self._settings = settings
        self._host = ""
        self._key = ""

        # 缓存
        self._now_cache: dict = None
        self._now_cache_time: datetime = None
        self._7d_cache: list = None
        self._7d_cache_time: datetime = None

        # 定时器
        self._timer_now = QTimer()
        self._timer_now.timeout.connect(self._fetch_now)
        self._timer_7d = QTimer()
        self._timer_7d.timeout.connect(self._check_and_fetch_7d)

        # 当前工作线程（按接口类型分开，避免 now/7d 互相覆盖）
        self._workers: dict[str, WeatherWorker] = {}
        # 离线也有数据：读上次成功写下的派生缓存（启动/断网时状态栏与详情不再空白）
        self._load_cache()

    def _load_cache(self) -> None:
        cache = weather_store.read_json_safe(self._cache_file)
        if not cache:
            return
        now = cache.get("now")
        if isinstance(now, dict) and now:
            self._now_cache = now
        forecast = cache.get("forecast")
        if isinstance(forecast, list) and forecast:
            self._7d_cache = forecast
        for key, attr in (("now_time", "_now_cache_time"),
                          ("forecast_time", "_7d_cache_time")):
            raw = str(cache.get(key) or "")
            if not raw:
                continue
            try:
                setattr(self, attr, datetime.fromisoformat(raw))
            except ValueError:
                continue

    def set_credentials(self, host: str, key: str) -> None:
        """设置API凭证"""
        self._host = host
        self._key = key

    def get_location(self) -> str:
        """当前位置（和风天气要求「经度,纬度」）。"""
        lat = self._settings.weather_lat if self._settings else self.DEFAULT_LAT
        lon = self._settings.weather_lon if self._settings else self.DEFAULT_LON
        return f"{lon},{lat}"

    def start_auto_update(self) -> None:
        """启动定时更新"""
        if not self._host or not self._key:
            return

        # 立即获取一次
        self._fetch_now()
        self._fetch_7d()

        # 启动实时天气定时器（每10分钟）
        self._timer_now.start(self.CACHE_NOW * 1000)

        # 启动7天预报定时器（每分钟检查一次是否到达固定时间点）
        self._timer_7d.start(60000)  # 60秒检查一次

    def _check_and_fetch_7d(self) -> None:
        """检查是否到达固定时间点并刷新7天预报"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        # 固定刷新时间点：早上7:45和中午12:00
        refresh_times = ["07:45", "12:00"]

        if current_time in refresh_times:
            # 检查是否已经在这个时间点刷新过（避免重复刷新）
            if self._7d_cache_time:
                last_refresh_date = self._7d_cache_time.strftime("%Y-%m-%d")
                last_refresh_time = self._7d_cache_time.strftime("%H:%M")
                if last_refresh_date == now.strftime("%Y-%m-%d") and last_refresh_time == current_time:
                    return  # 今天这个时间点已经刷新过
            self._fetch_7d(force=True)

    def stop_auto_update(self) -> None:
        """停止定时更新"""
        self._timer_now.stop()
        self._timer_7d.stop()

    def check_quota(self) -> tuple[bool, str]:
        """检查调用配额"""
        stats_file = self._stats_file
        if not stats_file.exists():
            return True, "OK"

        stats = weather_store.read_json_safe(stats_file)      # 坏文件不让界面崩
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")

        # 日限制
        daily_total = stats.get("daily", {}).get(today, {}).get("total", 0)
        if daily_total >= self.DAILY_LIMIT:
            return False, f"今日调用已达{self.DAILY_LIMIT}次上限"

        # 月限制
        monthly_total = stats.get("monthly", {}).get(month, {}).get("total", 0)
        if monthly_total >= self.MONTHLY_LIMIT:
            return False, f"月调用已达{self.MONTHLY_LIMIT}次上限"

        # 月警告
        if monthly_total >= self.MONTHLY_WARN:
            self.quota_warning.emit(f"警告：月调用已达{monthly_total}次，接近上限")

        return True, "OK"

    def get_stats(self) -> dict:
        """获取调用统计"""
        stats_file = self._stats_file
        if not stats_file.exists():
            return {"daily": 0, "monthly": 0}

        stats = weather_store.read_json_safe(stats_file)
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")

        return {
            "daily": stats.get("daily", {}).get(today, {}).get("total", 0),
            "monthly": stats.get("monthly", {}).get(month, {}).get("total", 0),
            "daily_by_type": stats.get("daily", {}).get(today, {}),
            "monthly_by_type": stats.get("monthly", {}).get(month, {})
        }

    def _start_worker(self, api_type: str, on_ok) -> bool:
        """按接口类型管理 worker：同类型不并发，**线程结束后**才回收。

        原实现共用一个 `self._worker` 槽，导致 `start_auto_update()` 里
        `_fetch_now()` 后紧跟的 `_fetch_7d()` 被 `isRunning()` 挡掉（**预报永不刷新**）。
        清理连 `QThread.finished`（不是自定义结果信号）—— 见 `WeatherWorker` 的说明。
        """
        running = self._workers.get(api_type)
        if running is not None and running.isRunning():
            return False
        worker = WeatherWorker(self._host, self._key, self.get_location(), api_type,
                               self._stats_file)
        self._workers[api_type] = worker
        worker.result.connect(on_ok)
        worker.failed.connect(self._on_error)
        worker.finished.connect(lambda t=api_type: self._workers.pop(t, None))
        worker.finished.connect(worker.deleteLater)
        worker.start()
        return True

    def shutdown(self) -> None:
        """停止定时器并**等线程收尾**（退出时不能让 QThread 在运行中被销毁）。"""
        self.stop_auto_update()
        for worker in list(self._workers.values()):
            with contextlib.suppress(RuntimeError):
                # 单次请求 10s 超时；最多等 11s，不用 terminate（Q-B3）
                worker.wait(11_000)
        self._workers.clear()

    def _fetch_now(self, force: bool = False) -> None:
        """获取实时天气"""
        if not self._host or not self._key:
            return

        # 检查缓存（除非force=True）
        if (not force and self._now_cache and self._now_cache_time
                and (datetime.now() - self._now_cache_time).total_seconds() < self.CACHE_NOW):
            self.weather_updated.emit(self._now_cache)
            return

        # 检查配额
        ok, msg = self.check_quota()
        if not ok:
            self.error_occurred.emit(msg)
            return

        # 发起请求
        self._start_worker("now", self._on_now_finished)

    def _fetch_7d(self, force: bool = False) -> None:
        """获取7天预报"""
        if not self._host or not self._key:
            return

        # 检查缓存（除非force=True）
        if (not force and self._7d_cache and self._7d_cache_time
                and (datetime.now() - self._7d_cache_time).total_seconds() < self.CACHE_7D):
            self.forecast_updated.emit(self._7d_cache)
            return

        # 检查配额
        ok, msg = self.check_quota()
        if not ok:
            self.error_occurred.emit(msg)
            return

        self._start_worker("7d", self._on_7d_finished)

    def _on_now_finished(self, data: dict, api_type: str) -> None:
        """实时天气请求完成"""
        self._now_cache = data.get("now", {})
        self._now_cache_time = datetime.now()
        self.weather_updated.emit(self._now_cache)
        # 写入缓存文件供脚本读取
        self._write_cache_to_file()

    def _on_7d_finished(self, data: dict, api_type: str) -> None:
        """7天预报请求完成"""
        self._7d_cache = data.get("daily", [])
        self._7d_cache_time = datetime.now()
        self.forecast_updated.emit(self._7d_cache)
        # 写入缓存文件供脚本读取
        self._write_cache_to_file()

    def _write_cache_to_file(self) -> None:
        """将天气缓存写入文件，供 scripts/actions.py 读取（原子写）。"""
        cache_data = {
            "now": self._now_cache or {},
            "now_time": self._now_cache_time.isoformat() if self._now_cache_time else "",
            "forecast": self._7d_cache or [],
            "forecast_time": self._7d_cache_time.isoformat() if self._7d_cache_time else "",
        }
        weather_store.write_json_atomic(self._cache_file, cache_data)

    def _on_error(self, msg: str, api_type: str) -> None:
        """错误处理"""
        self.error_occurred.emit(f"[{api_type}] {msg}")

    def get_now(self) -> dict:
        """获取当前实时天气（同步，返回缓存）"""
        return self._now_cache or {}

    def get_now_updated_at(self) -> datetime | None:
        """实时天气缓存的更新时间（UI 不直接读私有字段）。"""
        return self._now_cache_time

    def get_forecast(self) -> list:
        """获取7天预报（同步，返回缓存）"""
        return self._7d_cache or []

    def refresh(self) -> bool:
        """强制刷新所有天气数据（用户主动触发）。

        返回是否**发起**了请求；未配置凭证时发 `error_occurred` 并返回 False，
        让界面可以把"..."恢复成"刷新"并显示原因（旧实现会永远卡在"..."）。
        """
        if not self._host or not self._key:
            self.error_occurred.emit("未配置天气服务（API Host / Key），请先在设置里填写。")
            return False
        self._fetch_now(force=True)
        self._fetch_7d(force=True)
        return True

    def get_weather_text_for_ai(self) -> str:
        """生成AI助手可用的天气文本"""
        text = "【天气信息】\n"

        # 实时天气
        now = self.get_now()
        if now:
            text += f"当前: {now.get('text', '未知')} {now.get('temp', '?')}°C "
            text += f"体感{now.get('feelsLike', '?')}°C 湿度{now.get('humidity', '?')}% "
            text += f"{now.get('windDir', '?')}{now.get('windScale', '?')}级\n"

        # 未来3天
        forecast = self.get_forecast()
        if forecast:
            for _i, day in enumerate(forecast[:3]):
                date = day.get('fxDate', '?')
                text += f"{date}: {day.get('textDay', '?')} {day.get('tempMin', '?')}-{day.get('tempMax', '?')}°C"
                precip = day.get('precip', '0')
                try:
                    has_rain = float(precip) > 0
                except (TypeError, ValueError):
                    has_rain = False
                if has_rain:
                    text += f" 降雨{precip}mm"
                text += "\n"

        return text