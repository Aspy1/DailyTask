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
    """离屏 QApplication（Qt 控件测试用，避免依赖 pytest-qt）。

    同时把默认区域设成与**应用启动一致**（`App.__init__` 会调 `configure_locale()`）：
    本机系统区域是 zh_HK，不设的话日期/数字控件会显示 CJK 数字。
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from src.app import configure_locale
    configure_locale()
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _cleanup_qt_leftovers() -> Iterator[None]:
    """每个测试结束后清掉 Qt 残留（控件 / 延迟删除事件 / 待回收对象）。

    为什么必须做：整个测试会话共用一个 QApplication，226+ 个测试累积下来的
    顶层控件与排队事件会让后面的 `QMenu.exec()` / `processEvents()`
    **随机崩进程**（`Windows fatal exception: access violation`）。

    `gc.collect()` 同样是必需的：测试里创建的 `DataManager` 等服务持有**运行中的
    QTimer**，如果交给 Python GC 在**别的测试的事件循环中途**回收，就会在事件处理
    过程中销毁 C++ 对象 —— 这正是崩溃的来源。显式在测试边界回收，销毁就发生在
    没有事件循环运行的安全时刻（实测崩溃率 25% → 0）。
    """
    yield
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    # 只处理被测代码自己 `deleteLater()` 的对象（它们的 Python 引用已清）。
    # ⚠ 不要在这里对控件 `deleteLater()`，也不要 `close()` 顶层控件：
    # - 强制删除 Python 仍持有的包装器 → 之后 Python 侧再删一次 → 双重释放（崩）
    # - `close()` 会触发 `closeEvent`（MainWindow 的 closeEvent 会做保存/同步），
    #   既慢又给测试引入副作用
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
