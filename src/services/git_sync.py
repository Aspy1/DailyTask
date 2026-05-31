"""Auto-commit and push data + source files when changes are detected."""

import logging
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QThread, Signal

logger = logging.getLogger("gitsync")


class _GitWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, repo_path: Path, commands: list[list[str]], parent=None):
        super().__init__(parent)
        self._repo = repo_path
        self._commands = commands

    def run(self) -> None:
        try:
            for cmd in self._commands:
                result = subprocess.run(
                    cmd, cwd=str(self._repo),
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode != 0:
                    self.finished.emit(False, f"{' '.join(cmd)}: {result.stderr.strip()}")
                    return
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


class GitSync(QObject):
    sync_status = Signal(str)  # "idle" | "syncing" | "done" | "error: ..."

    def __init__(self, repo_path: Path, data_dir: Path, parent=None):
        super().__init__(parent)
        self._repo = repo_path
        self._data_dir = data_dir
        self._worker: _GitWorker | None = None

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(30_000)
        self._debounce.timeout.connect(self._sync)
        self._last_status = "idle"

    def on_data_changed(self, key: str = "") -> None:
        self._debounce.start()

    def sync_now(self) -> None:
        """Manual sync — stage everything and push."""
        self._debounce.stop()
        self._sync(include_source=True)

    def _sync(self, include_source: bool = False) -> None:
        if not (self._repo / ".git").exists():
            self.sync_status.emit("error: 不是 git 仓库")
            return
        if self._worker and self._worker.isRunning():
            self._debounce.start()
            return

        self.sync_status.emit("syncing")
        if include_source:
            cmds = [
                ["git", "add", "-A"],
                ["git", "commit", "-m", "data: manual sync [skip ci]"],
                ["git", "push"],
            ]
        else:
            cmds = [
                ["git", "add", "data/*.json"],
                ["git", "commit", "-m", "data: auto-sync [skip ci]"],
                ["git", "push"],
            ]
        self._worker = _GitWorker(self._repo, cmds, self)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool, error: str) -> None:
        if error and "nothing to commit" not in error and "nothing added" not in error:
            self.sync_status.emit(f"error: {error}")
            logger.warning("Git sync failed: %s", error)
        else:
            self.sync_status.emit("done")