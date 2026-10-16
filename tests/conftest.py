"""Pytest 全局配置。

- 把项目根与 tests/ 目录加入 sys.path，使 `import src...` / `import scripts.actions`
  和 `from helpers import ...` 在任意工作目录下都可用。
- 提供 `sandbox` fixture：把 actions.py 的数据目录重定向到临时目录，
  保证测试绝不触碰真实 data/。
"""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
for _p in (ROOT, TESTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import scripts.actions as actions  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch) -> Path:
    """actions.py 的 DATA 指向 tmp_path，读写都发生在临时目录。"""
    monkeypatch.setattr(actions, "DATA", tmp_path)
    return tmp_path


@pytest.fixture(scope="session")
def qapp() -> Iterator:
    """离屏 QApplication（Qt 控件测试用，避免依赖 pytest-qt）。"""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _cleanup_qt_leftovers() -> Iterator[None]:
    """每个测试结束后清掉 Qt 残留（控件 / 延迟删除事件）。

    为什么必须做：整个测试会话共用一个 QApplication，226 个测试累积下来的
    顶层控件与排队事件会让后面的 `processEvents()` **随机崩进程**
    （CI 上表现为 `Windows fatal exception: access violation`，
    栈顶永远落在某个 `processEvents()` 上）。
    """
    yield
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
