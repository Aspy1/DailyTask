"""方案 B 的宿主集成实测（`MD-files/PERFORMANCE_WORKFLOW.md` §3.2-1/3）。

测量本机 QtWebEngine 的首周和换周就绪时间。也可以导出相同的合成页面，
供 WebView2 独立宿主测量。页面就绪采用 DOM 检查与两次动画帧回调。

用法：
    .venv\\Scripts\\python.exe scripts/perf_week_web.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import perf_bench as bench  # noqa: E402

from src.ui.widgets import week_web_prototype as proto  # noqa: E402


def _courses(n: int = 30) -> list[dict]:
    return [{"name": f"课程 {i}", "day_of_week": 1 + (i % 7),
             "time_slots": [{"start": 1 + (i % 5), "end": 1 + (i % 5),
                             "location": f"A{100 + i}"}]}
            for i in range(1, n + 1)]


def instrument_week(html: str, token: str) -> str:
    """Add a readiness marker understood by both browser hosts."""
    probe = (
        "<script>requestAnimationFrame(() => requestAnimationFrame(() => {"
        "if (document.querySelectorAll('#head th').length === 7 && "
        "document.querySelectorAll('#body td').length === 7) "
        f"document.title = '{token}';"
        "}));</script>"
    )
    return html.replace("</body>", probe + "</body>", 1)


def wait_for_week(view, html: str, serial: int) -> None:
    """Wait for this navigation's DOM and a rendering opportunity."""
    from PySide6.QtCore import QEventLoop, QTimer

    token = f"week-ready-{serial}"
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)

    def on_title(title: str) -> None:
        if title == token:
            loop.quit()

    def on_load(ok: bool) -> None:
        if not ok:
            loop.quit()

    view.titleChanged.connect(on_title)
    view.loadFinished.connect(on_load)
    try:
        timer.start(15_000)
        view.setHtml(instrument_week(html, token))
        if view.title() != token:
            loop.exec()
        if view.title() != token:
            raise RuntimeError(f"Week rendering did not acknowledge {token}")
    finally:
        timer.stop()
        view.titleChanged.disconnect(on_title)
        view.loadFinished.disconnect(on_load)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-fixtures", type=Path)
    args = parser.parse_args()
    if args.export_fixtures:
        args.export_fixtures.mkdir(parents=True, exist_ok=True)
        for serial, count in enumerate((30, 31)):
            html = proto.build_html(proto.week_payload(_courses(count)))
            (args.export_fixtures / f"week-{serial}.html").write_text(
                instrument_week(html, f"week-ready-{serial}"), encoding="utf-8")
        return 0
    print("— 环境 —")
    for key in ("platform", "python", "qt", "cpu_count"):
        print(f"  {key}: {bench.machine_profile().get(key)}")

    print(f"\n  QtWebEngine 可用: {proto.web_engine_available()}")
    if not proto.web_engine_available():
        print("  运行时缺失 → 调用方退回 Qt 周视图（`render_week` 返回 False）")
        return 2

    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    week = proto.week_payload(_courses())
    html = proto.build_html(week)
    print(f"  页面大小: {len(html.encode('utf-8')) / 1024:.1f} KiB（自包含，无网络）")

    started = time.perf_counter_ns()
    view = QWebEngineView()
    view.resize(990, 638)
    view.show()
    create_ms = (time.perf_counter_ns() - started) / 1e6
    print(f"\n  首次创建 QWebEngineView: {create_ms:.1f} ms")

    try:
        started = time.perf_counter_ns()
        wait_for_week(view, html, 0)
        ready_ms = (time.perf_counter_ns() - started) / 1e6
        print(f"  首周就绪（DOM + 两次 rAF）: {ready_ms:.1f} ms")
        alternates = [proto.build_html(proto.week_payload(_courses(n))) for n in (31, 30)]
        serial = 0

        def switch_week() -> None:
            nonlocal serial
            serial += 1
            wait_for_week(view, alternates[(serial - 1) % len(alternates)], serial)

        sample = bench.measure(switch_week, label="换周·页面就绪", repeat=10, warmup=1)
        print(f"  换周就绪中位: {sample.median:.1f} ms  "
              f"P95: {sample.p95:.1f} ms  失败: {sample.failures}")
        return int(bool(sample.failures))
    finally:
        view.close()
        view.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    sys.exit(main())
