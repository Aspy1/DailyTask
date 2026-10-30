import configparser
import json
import logging
import pathlib
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "General": {
        "language": "zh-CN",
        "theme": "light",
        "auto_start": "true",
        "minimize_to_tray": "true",
        "reminder_enabled": "true",
        "reminder_check_interval_minutes": "1",
        "first_run": "true",
    },
    "AI": {
        "provider": "deepseek",
        "api_key": "",
        "api_endpoint": "https://api.deepseek.com",
        "model": "deepseek-chat",
        # 输出预算：这类模型先推理再输出，4096 容易被推理吃光（content 变空）
        "max_tokens": "8192",
        "temperature": "0.3",
    },
    "Semester": {
        "current": "",
    },
    "Window": {
        "geometry": "",
        "sidebar_visible": "true",
        "ai_panel_visible": "true",
        "sidebar_width": "200",
        "ai_panel_width": "320",
    },
    "Backup": {
        "auto_backup_enabled": "true",
        "backup_interval_days": "3",
        "max_backups": "10",
    },
    "Email": {
        "smtp_host": "smtp.qq.com",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_pass": "",
        "last_reminder_check": "",
    },
    "Balance": {
        "campus_card_enabled": "false",
        "campus_card_balance": "",
        "campus_card_threshold": "20",
        "water_card_enabled": "false",
        "water_card_balance": "",
        "water_card_threshold": "10",
        "electricity_enabled": "false",
        "electricity_balance": "",
        "electricity_threshold": "30",
        "last_balance_notify_date": "",
    },
    "Weather": {
        "provider": "qweather",
        "api_key": "",
        "api_host": "",
        "auto_update": "true",
        "show_aqi": "false",
    },
}

class SettingsManager:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._config = configparser.ConfigParser()
        if self.file_path.exists():
            self._config.read(self.file_path, encoding="utf-8")
        self._apply_defaults()
        self.save()

    def _ensure_file(self) -> None:
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self._apply_defaults()
            self.save()

    def _apply_defaults(self) -> None:
        for section, items in DEFAULT_SETTINGS.items():
            if not self._config.has_section(section):
                self._config.add_section(section)
            for key, value in items.items():
                if not self._config.has_option(section, key):
                    self._config.set(section, key, value)

    def load(self) -> None:
        self._config.read(self.file_path, encoding="utf-8")
        self._apply_defaults()

    def save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            self._config.write(f)

    def get(self, section: str, key: str, fallback: str = "") -> str:
        return self._config.get(section, key, fallback=fallback)

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        return self._config.getboolean(section, key, fallback=fallback)

    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        return self._config.getint(section, key, fallback=fallback)

    def get_float(self, section: str, key: str, fallback: float = 0.0) -> float:
        return self._config.getfloat(section, key, fallback=fallback)

    def set(self, section: str, key: str, value: str) -> None:
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config.set(section, key, str(value))

    @property
    def api_key(self) -> str:
        return self.get("AI", "api_key")

    @api_key.setter
    def api_key(self, value: str) -> None:
        self.set("AI", "api_key", value)

    @property
    def is_first_run(self) -> bool:
        return self.get_bool("General", "first_run", fallback=True)

    @is_first_run.setter
    def is_first_run(self, value: bool) -> None:
        self.set("General", "first_run", str(value).lower())

    @property
    def weather_lat(self) -> str:
        return self.get("Weather", "lat", "31.23")

    @weather_lat.setter
    def weather_lat(self, value: str) -> None:
        self.set("Weather", "lat", value)

    @property
    def weather_lon(self) -> str:
        return self.get("Weather", "lon", "121.47")

    @weather_lon.setter
    def weather_lon(self, value: str) -> None:
        self.set("Weather", "lon", value)

    @property
    def weather_api_key(self) -> str:
        return self.get("Weather", "api_key")

    @weather_api_key.setter
    def weather_api_key(self, value: str) -> None:
        self.set("Weather", "api_key", value)

    @property
    def weather_api_host(self) -> str:
        return self.get("Weather", "api_host")

    @weather_api_host.setter
    def weather_api_host(self, value: str) -> None:
        self.set("Weather", "api_host", value)

    @property
    def weather_auto_update(self) -> bool:
        return self.get_bool("Weather", "auto_update", fallback=True)

    @weather_auto_update.setter
    def weather_auto_update(self, value: bool) -> None:
        self.set("Weather", "auto_update", str(value).lower())


def migrate_legacy_scene_location(data_dir: pathlib.Path, settings: SettingsManager) -> bool:
    """把旧「场景存档」里的位置迁到天气设置（场景功能已弃用）。

    旧数据在 `data/scenes_meta.json` 的当前场景 `location{lat,lon}`。
    若设置里还没有 `[Weather] lat/lon`，就写进去；返回是否发生了迁移（幂等）。
    """
    if settings.get("Weather", "lat") or settings.get("Weather", "lon"):
        return False
    meta = data_dir / "scenes_meta.json"
    if not meta.exists():
        return False
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("scenes_meta.json 无法解析，跳过位置迁移")
        return False

    scenes = data.get("scenes", {})
    scene = scenes.get(data.get("current_scene", "")) or next(iter(scenes.values()), {})
    loc = (scene or {}).get("location") or {}
    lat, lon = loc.get("lat"), loc.get("lon")
    if lat is None or lon is None:
        return False

    settings.weather_lat, settings.weather_lon = str(lat), str(lon)
    settings.save()
    logger.info("已把旧场景位置迁移到天气设置：%s,%s", lat, lon)
    return True
