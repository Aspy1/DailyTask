"""Pytest 全局配置。

- 把项目根与 tests/ 目录加入 sys.path，使 `import src...` / `import scripts.actions`
  和 `from helpers import ...` 在任意工作目录下都可用。
- 提供 `sandbox` fixture：把 actions.py 的数据目录重定向到临时目录，
  保证测试绝不触碰真实 data/。
"""

import gc
import sys
import weakref
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
for _p in (ROOT, TESTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import scripts.actions as actions  # noqa: E402
import scripts.actions_core as actions_core  # noqa: E402

# ── 服务实例注册表（只给"清理残留定时器"用，见 _stop_leftover_service_timers）──
# 在构造时登记：比每个测试都 `gc.get_objects()` 全堆扫描快两个数量级。
_SERVICE_REFS: list = []


def _register_service(cls) -> None:
    """把某服务类的实例登记进 `_SERVICE_REFS`（测试专用，不改产品代码语义）。"""
    original = cls.__init__

    def _init(self, *args: object, **kwargs: object) -> None:
        original(self, *args, **kwargs)
        _SERVICE_REFS.append(weakref.ref(self))

    cls.__init__ = _init


def _install_service_registry() -> None:
    from src.services.data_manager import DataManager
    from src.services.reminder_service import ReminderService

    for cls in (DataManager, ReminderService):
        if not getattr(cls.__init__, "_service_registered", False):
            _register_service(cls)
            cls.__init__._service_registered = True  # type: ignore[attr-defined]


_install_service_registry()


@pytest.fixture
def sandbox(tmp_path, monkeypatch) -> Path:
    """actions 的数据目录指向 tmp_path，读写都发生在临时目录。

    ⚠ 必须**同时**改 `actions_core.DATA`：真正决定写到哪里的是核心层里的那个
    `DATA`（`_path`/`load`/`save` 都读它）。只改 `actions.DATA`（命令层的再导出）
    等于没改，测试会直接写进用户真实 `data/` —— 这正是 helpers.run() 要拦的事故。
    """
    monkeypatch.setattr(actions_core, "DATA", tmp_path)
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
    _stop_leftover_service_timers()
    # 只处理被测代码自己 `deleteLater()` 的对象（它们的 Python 引用已清）。
    # ⚠ 不要在这里对控件 `deleteLater()`，也不要 `close()` 顶层控件：
    # - 强制删除 Python 仍持有的包装器 → 之后 Python 侧再删一次 → 双重释放（崩）
    # - `close()` 会触发 `closeEvent`（MainWindow 的 closeEvent 会做保存/同步），
    #   既慢又给测试引入副作用
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()


def _stop_leftover_service_timers() -> None:
    """停掉本测试留下的"服务类"定时器（DataManager / ReminderService）。

    为什么单独做这一步：这些服务**自建 QTimer 并在构造时就 start()**。测试结束后
    对象进入 GC 队列，但定时器仍挂在事件循环上 —— 它会在**后面某个测试**的
    `processEvents()` 里触发，而那时宿主对象可能正被回收 → 在事件处理中途销毁
    C++ 对象 → `Windows fatal exception: access violation`
    （2026-10-17 CI 反复崩在 `test_animations._settle`，就是这个）。

    ⚠ 只 `stop()`，不 delete / 不 close（删/关都会造成双重释放）。
    ⚠ 用**注册表**（构造时登记）而不是 `gc.get_objects()` 全堆扫描：
       全堆扫描每个测试要多花 ~0.15s，整个套件会从 30s 变成 85s。
    """
    import contextlib

    live = []
    for ref in _SERVICE_REFS:
        obj = ref()
        if obj is not None:
            live.append(ref)
            for attr in ("_reload_timer", "_timer"):
                timer = getattr(obj, attr, None)
                if timer is not None:
                    with contextlib.suppress(RuntimeError):
                        timer.stop()
    _SERVICE_REFS[:] = live
