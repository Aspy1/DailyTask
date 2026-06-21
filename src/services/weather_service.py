"""和风天气服务"""
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer, QThread

from src.models.scene_archive import SceneArchive


class WeatherWorker(QThread):
    """天气API请求工作线程"""
    finished = Signal(dict, str)  # (data, api_type)
    error = Signal(str, str)  # (error_msg, api_type)

    def __init__(self, host: str, key: str, location: str, api_type: str):
        super().__init__()
        self._host = host
        self._key = key
        self._location = location
        self._api_type = api_type

    def run(self):
        try:
            if self._api_type == "now":
                url = f"https://{self._host}/v7/weather/now?location={self._location}&key={self._key}"
            elif self._api_type == "7d":
                url = f"https://{self._host}/v7/weather/7d?location={self._location}&key={self._key}"
            else:
                self.error.emit(f"未知API类型: {self._api_type}", self._api_type)
                return

            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "200":
                    self.finished.emit(data, self._api_type)
                    # 记录调用统计
                    self._record_request()
                else:
                    self.error.emit(f"API返回错误: {data.get('code')}", self._api_type)
            else:
                self.error.emit(f"HTTP错误: {resp.status_code}", self._api_type)
        except Exception as e:
            self.error.emit(str(e), self._api_type)

    def _record_request(self):
        """记录API调用次数"""
        stats_file = Path("data/weather_stats.json")
        stats = {}
        if stats_file.exists():
            stats = json.loads(stats_file.read_text())

        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")

        # 日统计
        if "daily" not in stats:
            stats["daily"] = {}
        if today not in stats["daily"]:
            stats["daily"][today] = {"now": 0, "7d": 0, "warning": 0, "total": 0}
        stats["daily"][today][self._api_type] = stats["daily"][today].get(self._api_type, 0) + 1
        stats["daily"][today]["total"] += 1

        # 月统计
        if "monthly" not in stats:
            stats["monthly"] = {}
        if month not in stats["monthly"]:
            stats["monthly"][month] = {"now": 0, "7d": 0, "warning": 0, "total": 0}
        stats["monthly"][month][self._api_type] = stats["monthly"][month].get(self._api_type, 0) + 1
        stats["monthly"][month]["total"] += 1

        # 最后请求时间
        stats["last_request"] = {
            "time": datetime.now().isoformat(),
            "type": self._api_type
        }

        stats_file.write_text(json.dumps(stats, indent=2))


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

    def __init__(self, scene_archive: SceneArchive = None):
        super().__init__()
        self._scene = scene_archive
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

        # 当前工作线程
        self._worker: WeatherWorker = None

    def set_credentials(self, host: str, key: str):
        """设置API凭证"""
        self._host = host
        self._key = key

    def set_scene_archive(self, scene: SceneArchive):
        """设置场景存档"""
        self._scene = scene

    def get_location(self) -> str:
        """获取当前位置（经纬度）"""
        if self._scene:
            loc = self._scene.get_location()
            return f"{loc['lon']},{loc['lat']}"
        return "121.47,31.23"  # 默认上海

    def start_auto_update(self):
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

    def _check_and_fetch_7d(self):
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

    def stop_auto_update(self):
        """停止定时更新"""
        self._timer_now.stop()
        self._timer_7d.stop()

    def check_quota(self) -> tuple[bool, str]:
        """检查调用配额"""
        stats_file = Path("data/weather_stats.json")
        if not stats_file.exists():
            return True, "OK"

        stats = json.loads(stats_file.read_text())
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
        stats_file = Path("data/weather_stats.json")
        if not stats_file.exists():
            return {"daily": 0, "monthly": 0}

        stats = json.loads(stats_file.read_text())
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")

        return {
            "daily": stats.get("daily", {}).get(today, {}).get("total", 0),
            "monthly": stats.get("monthly", {}).get(month, {}).get("total", 0),
            "daily_by_type": stats.get("daily", {}).get(today, {}),
            "monthly_by_type": stats.get("monthly", {}).get(month, {})
        }

    def _fetch_now(self, force: bool = False):
        """获取实时天气"""
        if not self._host or not self._key:
            return

        # 检查缓存（除非force=True）
        if not force and self._now_cache and self._now_cache_time:
            if (datetime.now() - self._now_cache_time).total_seconds() < self.CACHE_NOW:
                self.weather_updated.emit(self._now_cache)
                return

        # 检查配额
        ok, msg = self.check_quota()
        if not ok:
            self.error_occurred.emit(msg)
            return

        # 发起请求
        if self._worker and self._worker.isRunning():
            return

        self._worker = WeatherWorker(self._host, self._key, self.get_location(), "now")
        self._worker.finished.connect(self._on_now_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _fetch_7d(self, force: bool = False):
        """获取7天预报"""
        if not self._host or not self._key:
            return

        # 检查缓存（除非force=True）
        if not force and self._7d_cache and self._7d_cache_time:
            if (datetime.now() - self._7d_cache_time).total_seconds() < self.CACHE_7D:
                self.forecast_updated.emit(self._7d_cache)
                return

        # 检查配额
        ok, msg = self.check_quota()
        if not ok:
            self.error_occurred.emit(msg)
            return

        if self._worker and self._worker.isRunning():
            return

        self._worker = WeatherWorker(self._host, self._key, self.get_location(), "7d")
        self._worker.finished.connect(self._on_7d_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_now_finished(self, data: dict, api_type: str):
        """实时天气请求完成"""
        self._now_cache = data.get("now", {})
        self._now_cache_time = datetime.now()
        self.weather_updated.emit(self._now_cache)
        # 写入缓存文件供脚本读取
        self._write_cache_to_file()

    def _on_7d_finished(self, data: dict, api_type: str):
        """7天预报请求完成"""
        self._7d_cache = data.get("daily", [])
        self._7d_cache_time = datetime.now()
        self.forecast_updated.emit(self._7d_cache)
        # 写入缓存文件供脚本读取
        self._write_cache_to_file()

    def _write_cache_to_file(self):
        """将天气缓存写入文件，供scripts/actions.py读取"""
        import json
        cache_file = Path("data/weather_cache.json")
        cache_data = {
            "now": self._now_cache or {},
            "now_time": self._now_cache_time.isoformat() if self._now_cache_time else "",
            "forecast": self._7d_cache or [],
            "forecast_time": self._7d_cache_time.isoformat() if self._7d_cache_time else "",
        }
        cache_file.write_text(json.dumps(cache_data, ensure_ascii=False))

    def _on_error(self, msg: str, api_type: str):
        """错误处理"""
        self.error_occurred.emit(f"[{api_type}] {msg}")

    def get_now(self) -> dict:
        """获取当前实时天气（同步，返回缓存）"""
        return self._now_cache or {}

    def get_forecast(self) -> list:
        """获取7天预报（同步，返回缓存）"""
        return self._7d_cache or []

    def refresh(self):
        """强制刷新所有天气数据（用户主动触发）"""
        self._fetch_now(force=True)
        self._fetch_7d(force=True)

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
            for i, day in enumerate(forecast[:3]):
                date = day.get('fxDate', '?')
                text += f"{date}: {day.get('textDay', '?')} {day.get('tempMin', '?')}-{day.get('tempMax', '?')}°C"
                precip = day.get('precip', '0')
                if precip and float(precip) > 0:
                    text += f" 降雨{precip}mm"
                text += "\n"

        return text