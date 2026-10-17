"""Auto-commit and push data + source files when changes are detected."""

import logging
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal

logger = logging.getLogger(__name__)

# ── 同步范围（**唯一清单**）────────────────────────────────────
# 用户数据 = 要进版本库的东西；自动同步与手动同步都用这一份。
# ⚠ 新增数据文件必须在这里加一行 —— `tests/test_git_sync_scope.py` 拿
# `DataManager._models()` 对照，漏了就红（漏了比报错更糟：数据会**悄悄**不同步）。
# 为什么显式列名而不是 `data/*.json`：那个 glob 会连带命中派生文件
# （weather_cache / weather_stats / search_index），靠 .gitignore 兜住太隐式。
DATA_FILES = ("daily_logs.json", "expenses.json", "habits.json",
              "inventory.json", "semesters.json")
# 按学期的文件：整个目录 —— **不只当前学期**，旧学期的 courses/tasks/exams 也要同步
DATA_DIRS = ("semesters",)


def sync_paths(data_dir: Path, data_rel: str) -> list[str]:
    """要暂存的路径（仓库相对）。**只列存在的**。

    ⚠ `git add` 对不存在的路径会直接 `fatal: pathspec … did not match any files`，
    整条命令链就此中断（2026-10-17 用临时仓库实测到）—— 新机器 / 新克隆上必然踩。
    目录整个带上：新学期的文件还没进过版本库，也要能一次加进去。
    全都不存在时退回数据目录本身（`.gitignore` 会把派生文件挡住）。
    """
    paths = [f"{data_rel}/{n}" for n in DATA_FILES if (data_dir / n).exists()]
    paths += [f"{data_rel}/{d}" for d in DATA_DIRS if (data_dir / d).exists()]
    return paths or [data_rel]


def build_sync_commands(data_rel: str, message: str, paths: list[str]) -> list[list[str]]:
    """拼同步命令：add（只加用户数据）→ commit → push。**纯函数**，便于测试。

    ⚠ 手动同步**不再** `git add -A`（审查 2026-10-17 #4）：那会把开发中的源码一起
    提交。源码该由开发时显式提交 —— 两条路径的范围**完全一样**，只有提交信息不同。
    `-A -- <路径>`：路径内的**删除**也要暂存，而 `--` 后面是显式路径，扫不到源码。
    """
    return [["git", "add", "-A", "--", *paths],
            ["git", "commit", "-m", message],
            ["git", "push"]]


def is_nothing_to_commit(detail: str) -> bool:
    """"没东西可提交"不是错误 —— 不该中断后面的 push（审查 #4）。"""
    return "nothing to commit" in detail or "nothing added" in detail


def is_up_to_date(push_output: str) -> bool:
    """push 输出 "Everything up-to-date" → 没有任何东西被推上去。

    ⚠ 调用方要把 **stdout + stderr 合并**传进来：git 的推送进度与这句都走 stderr
    （只看 stdout 会一直判成"推过了"，2026-10-17 用临时仓库实测到）。
    """
    return "up-to-date" in push_output.lower()


def classify_sync(pushed: bool) -> str:
    """成功的两态：`pushed`（推送了提交）/ `up-to-date`（本来就没有待推送）。纯函数。"""
    return "pushed" if pushed else "up-to-date"


class _GitWorker(QThread):
    finished = Signal(bool, str, str)   # (ok, 失败详情, 状态：pushed / up-to-date)

    def __init__(self, repo_path: Path, commands: list[list[str]], parent=None) -> None:
        super().__init__(parent)
        self._repo = repo_path
        self._commands = commands

    def run(self) -> None:
        try:
            pushed = False
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
                    if is_nothing_to_commit(detail):
                        # "没东西可提交"不是错误 → **继续往下走**：后面还有 push，
                        # 之前可能攒着未推送的提交（旧实现在这里直接 return → push 不执行）
                        logger.info("git 无改动可提交，继续推送：%s", " ".join(cmd))
                        continue
                    self.finished.emit(False, f"{' '.join(cmd)}: {detail[-300:]}", "")
                    return
                if cmd[:2] == ["git", "push"]:
                    # stdout + stderr 合并：git 的推送信息走 stderr（实测）
                    pushed = not is_up_to_date(result.stdout + result.stderr)
            self.finished.emit(True, "", classify_sync(pushed))
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            self.finished.emit(False, str(e), "")


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
        """手动同步（托盘菜单）：范围与自动同步**完全一样**，只是提交信息不同。"""
        self._debounce.stop()
        self._sync(manual=True)

    def _data_rel(self) -> str:
        """数据目录相对仓库根的路径（通常是 `data`）。"""
        try:
            return self._data_dir.relative_to(self._repo).as_posix()
        except ValueError:                      # 数据目录不在仓库里 → 退回目录名
            return self._data_dir.name

    def _sync(self, manual: bool = False) -> None:
        if not (self._repo / ".git").exists():
            self.sync_status.emit("error: 不是 git 仓库")
            return
        if self._worker and self._worker.isRunning():
            self._debounce.start()
            return

        self.sync_status.emit("syncing")
        message = "data: manual sync [skip ci]" if manual else "data: auto-sync [skip ci]"
        paths = sync_paths(self._data_dir, self._data_rel())
        cmds = build_sync_commands(self._data_rel(), message, paths)
        self._worker = _GitWorker(self._repo, cmds, self)
        self._worker.finished.connect(self._on_done)
        self._worker.finished.connect(self._worker.deleteLater)  # 生命周期回收（Q-B5）
        self._worker.start()

    def _on_done(self, ok: bool, error: str, state: str = "") -> None:
        """三态：`done: pushed`（推送了提交）/ `done: up-to-date`（本来就没待推送）/ `error: …`。"""
        if not ok:
            self.sync_status.emit(f"error: {error}")
            logger.warning("Git sync failed: %s", error)
            return
        self.sync_status.emit(f"done: {state}" if state else "done")
        logger.info("Git sync: %s", state or "done")