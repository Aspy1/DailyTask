import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class BaseJsonModel:
    file_path: Path
    _data: dict[str, Any]

    def __init__(self, file_path: Path, default_data: dict[str, Any] | None = None):
        self.file_path = file_path
        self._default_data = default_data or {"_version": 1}
        self._data = {}
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self._data = dict(self._default_data)
            self.save()
        else:
            self.load()

    def load(self) -> dict[str, Any]:
        with open(self.file_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        return self._data

    def reload(self) -> None:
        """Re-read data from disk, discarding in-memory changes."""
        self.load()

    def save(self) -> None:
        self.atomic_write()

    def atomic_write(self) -> None:
        tmp_path = self.file_path.with_suffix(".tmp")
        bak_path = self.file_path.with_suffix(".bak")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)

            if self.file_path.exists():
                shutil.copy2(self.file_path, bak_path)

            # Retry on PermissionError (Windows Defender / file indexer lock)
            for attempt in range(5):
                try:
                    os.replace(tmp_path, self.file_path)
                    break
                except PermissionError:
                    if attempt < 4:
                        time.sleep(0.05)
                    else:
                        raise

            if bak_path.exists():
                bak_path.unlink()
        except Exception:
            if bak_path.exists() and not self.file_path.exists():
                shutil.copy2(bak_path, self.file_path)
            raise

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @data.setter
    def data(self, value: dict[str, Any]) -> None:
        self._data = value

    @property
    def version(self) -> int:
        return self._data.get("_version", 1)

    def migrate(self, target_version: int) -> None:
        current = self.version
        if current >= target_version:
            return
        method_name = f"_migrate_v{current}_to_v{target_version}"
        if hasattr(self, method_name):
            getattr(self, method_name)()
        self._data["_version"] = target_version
        self.save()
