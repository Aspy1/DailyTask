"""Auto-commit and push data + source files when changes are detected."""

import logging
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal

logger = logging.getLogger(__name__)


class _GitWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, repo_path: Path, commands: list[list[str]], parent=None) -> None:
        super().__init__(parent)
        self._repo = repo_path
        self._commands = commands

    def run(self) -> None:
        try:
            for cmd in self._commands:
                result = subprocess.run(  # noqa: S603 — 固定参数列表，无 shell
                    cmd, cwd=str(self._repo),
                    capture_output=True, text=True, timeout=60,
                    # ⚠ 必须显式指定编码：`text=True` 默认用**本机区域编码**（本机 gbk），
                    # 而 git 的输出里可能带非 ASCII（仓库里有中文文件名）→
                    # UnicodeDecodeError 会让整次同步失败（2026-10-16 全量验收发现）
                    encoding="utf-8", errors="replace",
                )
                if result.returncode != 0:
                    # ⚠ 失败原因可能只在 stdout（如 git 的用法错误、hook 输出），
                    # 只看 stderr 会得到"冒号后什么都没有"的日志（全量验收发现）
                    detail = (result.stderr.strip() or result.stdout.strip()
                              or f"退出码 {result.returncode}")
                    self.finished.emit(False, f"{' '.join(cmd)}: {detail[-300:]}")
                    return
            self.finished.emit(True, "")
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            self.finished.emit(False, str(e))


class GitSync(QObject):
    sync_status = Signal(str)  # "idle" | "syncing" | "done" | "error: ..."

    def __init__(self, repo_path: Path, data_dir: Path, parent=None) -> None:
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
                # 按学期分文件后，课程/作业/考试在 data/semesters/<id>/ 下 —— 必须一并同步
                ["git", "add", "data/*.json", "data/semesters"],
                ["git", "commit", "-m", "data: auto-sync [skip ci]"],
                ["git", "push"],
            ]
        self._worker = _GitWorker(self._repo, cmds, self)
        self._worker.finished.connect(self._on_done)
        self._worker.finished.connect(self._worker.deleteLater)  # 生命周期回收（Q-B5）
        self._worker.start()

    def _on_done(self, ok: bool, error: str) -> None:
        if error and "nothing to commit" not in error and "nothing added" not in error:
            self.sync_status.emit(f"error: {error}")
            logger.warning("Git sync failed: %s", error)
        else:
            self.sync_status.emit("done")