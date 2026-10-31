"""命令输出的线程隔离（Q-B4）。

旧实现用 `contextlib.redirect_stdout` 捕获命令输出 —— `sys.stdout` 是进程级全局，
AI 工作线程重定向期间，其它线程的 print 会被混进命令结果。现在 `emit()` 写线程局部缓冲。
"""

import threading
import time

from scripts.actions_core import capture_output, emit


def test_emit_capture_is_thread_local() -> None:
    outputs: dict[str, str] = {}
    errors: list[BaseException] = []

    def work(name: str) -> None:
        try:
            with capture_output() as buf:
                time.sleep(0.01)          # 两个线程的捕获窗口重叠
                emit(f"hello {name}")
                emit(f"bye {name}")
                outputs[name] = buf.getvalue()
        except BaseException as exc:      # noqa: BLE001 - 测试线程里把异常带回主线程
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert outputs["a"].strip().splitlines() == ["hello a", "bye a"]
    assert outputs["b"].strip().splitlines() == ["hello b", "bye b"]


def test_capture_restores_previous_stream() -> None:
    with capture_output() as outer:
        emit("outer")
        with capture_output() as inner:
            emit("inner")
        emit("outer2")
    assert inner.getvalue().strip() == "inner"
    assert outer.getvalue().strip().splitlines() == ["outer", "outer2"]
