import configparser
from pathlib import Path

DEFAULT_SETTINGS = {
    "General": {
        "language": "zh-CN",
        "theme": "light",
        "auto_start": "false",
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
        "max_tokens": "4096",
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
}

class SettingsManager:
    def __init__(self, file_path: Path):
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
