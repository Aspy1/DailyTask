import json
from pathlib import Path

class I18nLoader:
    _instance = None
    _strings: dict = {}
    _loaded: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, locale: str = "zh-CN") -> None:
        path = Path(__file__).parent / f"{locale}.json"
        if not path.exists():
            raise FileNotFoundError(f"Language file not found: {path}")
        with open(path, encoding="utf-8") as f:
            self._strings = json.load(f)
        self._loaded = True

    def tr(self, key: str, default: str = "") -> str:
        if not self._loaded:
            self.load()
        return self._strings.get(key, default or key)

t = I18nLoader()

def tr(key: str, default: str = "") -> str:
    return t.tr(key, default)
