"""settings.ini 的读写（**原子写 + 只回写改动过的键**）。

历史坑（`ERRORS #044`）：应用每个提醒 tick 都把整份配置写回，于是外部脚本改的配置
会被**静默回滚**。这里改成：

- `set()` 只登记**脏键**；`save()` 先重读磁盘、只覆盖这些键 → 外部改的其它键保留；
- 写入走 `.tmp` + `os.replace`（崩溃/断电不会留下半份配置）；
- `ConfigParser(interpolation=None)`：邮箱授权码里出现 `%` 不再抛异常；
- 没有脏键时 `save()` **不写文件**（少一次 IO，也少一次回滚机会）。
"""

import configparser
import logging
import os
import shutil
import threading
from datetime import datetime
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
        "animations_enabled": "true",
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
    """配置对象。线程安全：所有读写都在同一把可重入锁内。"""

    def __init__(self, file_path: Path) -> None:
        self.file_path = Path(file_path)
        self._lock = threading.RLock()
        self._config = self._new_parser()
        self._dirty: set[tuple[str, str]] = set()
        existed = self.file_path.exists()
        if existed:
            self._read_disk_into(self._config)
        self._apply_defaults()
        if not existed:
            # 首次运行：把默认值真正落盘（否则用户打开设置文件会是空的）
            self._dirty = {(section, key)
                           for section, items in DEFAULT_SETTINGS.items()
                           for key in items}
            self.save()

    @staticmethod
    def _new_parser() -> configparser.ConfigParser:
        """`interpolation=None`：授权码/密码里的 `%` 必须原样保存。

        默认的 `BasicInterpolation` 会把 `%` 当占位符 → `save()` 抛
        `InterpolationSyntaxError`，而异常发生在设置面板的保存按钮里（用户看不懂）。
        """
        return configparser.ConfigParser(interpolation=None)

    def _read_disk_into(self, target: configparser.ConfigParser) -> bool:
        """把磁盘内容读进 `target`；读不出来返回 False（保留现场，不覆盖）。"""
        try:
            with open(self.file_path, encoding="utf-8") as f:
                target.read_file(f)
            return True
        except (OSError, configparser.Error, UnicodeDecodeError) as e:
            logger.error("settings.ini 无法解析：%s", e)
            return False

    def _apply_defaults(self) -> None:
        for section, items in DEFAULT_SETTINGS.items():
            if not self._config.has_section(section):
                self._config.add_section(section)
            for key, value in items.items():
                if not self._config.has_option(section, key):
                    self._config.set(section, key, value)

    def load(self) -> None:
        """重新从磁盘加载（丢弃内存里的未保存改动）。"""
        with self._lock:
            fresh = self._new_parser()
            self._read_disk_into(fresh)
            self._config = fresh
            self._apply_defaults()
            self._dirty.clear()

    def save(self) -> bool:
        """只回写**改动过的键**；没有改动 / 磁盘已经一致 → 不写。返回是否写了。"""
        with self._lock:
            if not self._dirty:
                return False

            disk = self._new_parser()
            disk_ok = (not self.file_path.exists()) or self._read_disk_into(disk)
            if not disk_ok:
                # 磁盘那份坏了：先留档再重写，绝不静默覆盖现场（Q-I2 / ERRORS #041 同类）
                self._quarantine_corrupt()
                disk = self._new_parser()

            changed = False
            for section, key in sorted(self._dirty):
                if not self._config.has_section(section):
                    continue
                value = self._config.get(section, key, fallback="", raw=True)
                if disk.has_option(section, key) and disk.get(section, key) == value:
                    continue
                if not disk.has_section(section):
                    disk.add_section(section)
                disk.set(section, key, value)
                changed = True

            if changed:
                self._atomic_write(disk)
                self._config = disk
            self._dirty.clear()
            return changed

    def _atomic_write(self, config: configparser.ConfigParser) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file_path.with_name(self.file_path.name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                config.write(f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.file_path)
        finally:
            tmp.unlink(missing_ok=True)

    def _quarantine_corrupt(self) -> None:
        """把坏掉的 settings.ini 改名留档（保留密钥现场，便于人工恢复）。"""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        keep = self.file_path.with_name(
            f"{self.file_path.stem}.corrupt-{stamp}{self.file_path.suffix}")
        try:
            shutil.copy2(self.file_path, keep)
            logger.error("settings.ini 损坏，已留档到 %s（将重建一份）", keep)
        except OSError:
            logger.error("settings.ini 损坏且留档失败：%s", self.file_path, exc_info=True)

    # ── getters / setters ───────────────────────────────────

    def get(self, section: str, key: str, fallback: str = "") -> str:
        with self._lock:
            return self._config.get(section, key, fallback=fallback)

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        with self._lock:
            return self._config.getboolean(section, key, fallback=fallback)

    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        with self._lock:
            return self._config.getint(section, key, fallback=fallback)

    def get_float(self, section: str, key: str, fallback: float = 0.0) -> float:
        with self._lock:
            return self._config.getfloat(section, key, fallback=fallback)

    def set(self, section: str, key: str, value: str) -> None:
        """设置一个键；值没变就不登记脏键（避免无意义写盘）。"""
        text = str(value)
        with self._lock:
            if not self._config.has_section(section):
                self._config.add_section(section)
            current = (self._config.get(section, key, fallback=None)
                       if self._config.has_option(section, key) else None)
            if current == text:
                return
            self._config.set(section, key, text)
            self._dirty.add((section, key))

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


def migrate_legacy_scene_location(data_dir: Path, settings: SettingsManager) -> bool:
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
        import json

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
