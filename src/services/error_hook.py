"""未捕获异常的统一落日志（主线程 + 子线程）。

Qt 的 Python 槽异常通常由 PySide 打印到 stderr；但**线程里的异常**默认只打印一次，
应用日志（`data/app.log`）里看不到。这里把两类都接到 `logging`，用户报障时能直接查日志。

⚠ 不弹模态框：未捕获异常可能发生在任意线程；弹窗会阻塞/递归。
"""

import logging
import sys
import threading
import traceback

LOGGER_NAME = "unhandled"
_INSTALLED = False


def install_exception_hooks() -> None:
    """安装一次（重复调用无副作用）。"""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    previous = sys.excepthook

    def _hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        logging.getLogger(LOGGER_NAME).error("主线程未捕获异常：%s", "".join(
            traceback.format_exception(exc_type, exc, tb)))
        # 保留默认行为（stderr 仍可见，便于开发时直接看到）
        previous(exc_type, exc, tb)

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        name = getattr(args.thread, "name", "?")
        logging.getLogger(LOGGER_NAME).error("线程 %s 未捕获异常：%s", name, "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

    sys.excepthook = _hook
    threading.excepthook = _thread_hook
