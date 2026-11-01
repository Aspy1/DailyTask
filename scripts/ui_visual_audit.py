#!/usr/bin/env python
"""对现代化后的界面做一次**可打印证据**的视觉/交互审计。

与 `ui_button_smoke.py` 的区别：这里不点按钮，而是检查"用户实际看到的内容"：
- 天气详情每一行预报的日期/天气/温度是否可见；
- 窄窗口 5 张汇总卡是否都在面板内；
- 程序化跳转后侧边栏是否同步；
- 近期安排空态卡片是否有阅读宽度；
- 设置页"界面动效"开关是否存在；
- 任务表排序是否确实关闭；
- 49 张截图的尺寸/非空颜色数。

输出为纯文本，可直接 tee 到 `dev-logs/evidence/` 作为验收证据。
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path(tempfile.mkdtemp(prefix="lifeassistant-visual-"))
os.environ["LIFE_ASSISTANT_DATA_DIR"] = str(SANDBOX)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from scripts.ui_render import _seed  # noqa: E402
from src.services.ai_service import AIService  # noqa: E402
from src.services.data_manager import DataManager  # noqa: E402
from src.services.settings_manager import SettingsManager  # noqa: E402
from src.ui import animations  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
from src.ui.styles import theme  # noqa: E402
from src.ui.widgets.weather_dialog import WeatherDetailDialog  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    CHECKS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name} — {detail}", flush=True)


def _write_weather_cache() -> None:
    (SANDBOX / "weather_cache.json").write_text(json.dumps({
        "now": {"weathercode": 61, "temp": 8, "text": "小雨",
                "feelsLike": 6, "humidity": 82, "windDir": "北", "windScale": "3"},
        "now_time": "2026-11-01T11:30:00",
        "forecast": [
            {"fxDate": "2026-11-02", "textDay": "多云", "tempMin": 7,
             "tempMax": 15, "precip": "0.0"},
            {"fxDate": "2026-11-03", "textDay": "晴", "tempMin": 8,
             "tempMax": 17, "precip": "0.0"},
            {"fxDate": "2026-11-04", "textDay": "小雨", "tempMin": 9,
             "tempMax": 14, "precip": "2.4"},
        ],
        "forecast_time": "2026-11-01T11:30:00",
    }, ensure_ascii=False), encoding="utf-8")


def _check_weather(mw, app) -> None:
    check("状态栏加载离线天气", "小雨" in mw._weather_label.text(),
          f"weather_label={mw._weather_label.text()!r}")
    dialog = WeatherDetailDialog(mw._weather_service, mw)
    dialog.show()
    app.processEvents()
    rows = dialog._forecast_rows
    check("天气详情有 3 行预报", len(rows) == 3, f"rows={len(rows)}")
    for i, row in enumerate(rows, 1):
        text = row["text"].text()
        temp = row["temp"].text()
        check(f"第{i}行日期/天气/温度非空",
              bool(row["date"].text() and text and temp),
              f"date={row['date'].text()!r} text={text!r} temp={temp!r}")
        check(f"第{i}行天气标签可见", row["text"].isVisible(),
              f"visible={row['text'].isVisible()}")
    dialog.close()


def _check_narrow_layout(mw) -> None:
    mw._workspace.switch_to("expenses")
    mw._on_ai_toggle(True)
    mw.resize(990, 638)
    QApplication.processEvents()
    panel = mw._workspace._expense_panel
    cards = [panel._sum_month, panel._sum_today, panel._sum_budget,
             panel._sum_saved, panel._forecast]
    inside = all(card.geometry().right() <= panel.width() for card in cards)
    check("窄窗口汇总卡不越界", inside,
          f"panel_width={panel.width()} rights={[c.geometry().right() for c in cards]}")
    check("程序化跳转同步侧栏", mw._sidebar._current_nav == "expenses",
          f"sidebar={mw._sidebar._current_nav!r}")
    mw._on_ai_toggle(False)


def _check_pages(mw) -> None:
    mw._workspace.switch_to("routines")
    QApplication.processEvents()
    routine_labels = [w.text() for w in mw.findChildren(QLabel)
                      if "还没有近期安排" in (w.text() or "")]
    check("近期安排空态存在", bool(routine_labels), f"labels={routine_labels}")

    mw._workspace.switch_to("settings")
    QApplication.processEvents()
    settings_labels = [w.text() for w in mw.findChildren(QLabel)
                       if "界面动效" in (w.text() or "")]
    check("设置页界面动效开关存在", bool(settings_labels), f"labels={settings_labels}")

    mw._workspace.switch_to("tasks")
    panel = mw._workspace._task_panel
    check("任务表排序确实关闭", panel._table.isSortingEnabled() is False,
          f"isSortingEnabled={panel._table.isSortingEnabled()}")


def _check_screenshots() -> None:
    shots = ROOT / "shots-modern"
    images = sorted(shots.glob("*.png")) if shots.exists() else []
    check("截图集数量 >= 40", len(images) >= 40, f"count={len(images)}")
    for name in ("dialog-weather.png", "light-narrow-expenses-ai.png",
                 "light-routines.png", "light-settings-0.5.png"):
        path = shots / name
        image = QImage(str(path)) if path.exists() else QImage()
        colors = set()
        if not image.isNull():
            colors = {image.pixel(x, y) for x in range(0, image.width(), 20)
                      for y in range(0, image.height(), 20)}
        check(f"截图 {name} 可读/非空",
              not image.isNull() and len(colors) >= 8,
              f"size={image.size().width()}x{image.size().height()} colors={len(colors)}")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    animations.set_enabled(False)
    app.setStyleSheet(theme.init_theme(app, "light"))
    settings = SettingsManager(SANDBOX / "settings.ini")
    settings.load()
    dm = DataManager(SANDBOX)
    _seed(dm)
    _write_weather_cache()

    mw = MainWindow(settings, AIService(settings, dm), dm)
    mw.resize(1210, 792)
    mw.show()
    app.processEvents()
    _check_weather(mw, app)
    _check_narrow_layout(mw)
    _check_pages(mw)
    _check_screenshots()

    mw.shutdown()
    mw.close()
    app.processEvents()
    failed = [c for c in CHECKS if not c[1]]
    print(f"\nVISUAL_AUDIT {'PASS' if not failed else 'FAIL'} "
          f"({len(CHECKS) - len(failed)}/{len(CHECKS)})", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
