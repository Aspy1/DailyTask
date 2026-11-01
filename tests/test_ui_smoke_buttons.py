"""全量 UI 冒烟（按钮级）+ 截图渲染的 CI 守卫。

这两个脚本都以**子进程**运行：它们各自创建离屏 QApplication 与沙箱，
避免和 pytest 的 qapp / 真实 data 互相污染。
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, *args], cwd=str(ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def test_every_button_can_be_clicked() -> None:
    """⭐ 每个面板/侧边栏/状态栏/弹窗的按钮都点一遍，槽异常必须为 0。"""
    proc = _run(["scripts/ui_button_smoke.py"], timeout=240)
    assert proc.returncode == 0, (proc.stdout[-2000:], proc.stderr[-2000:])
    assert "errors: 0" in proc.stdout, proc.stdout[-2000:]
    assert "buttons clicked: " in proc.stdout


def test_screenshot_render_is_complete_and_nonblank(tmp_path) -> None:
    """截图集完整、非空；用 QImage 检查不是空白画布。"""
    from PySide6.QtGui import QImage

    out = tmp_path / "shots"
    proc = _run(["scripts/ui_render.py", "--out", str(out)], timeout=240)
    assert proc.returncode == 0, (proc.stdout[-2000:], proc.stderr[-2000:])
    images = sorted(out.glob("*.png"))
    assert len(images) >= 40, [p.name for p in images]
    for path in images:
        image = QImage(str(path))
        assert not image.isNull(), path
        # 面板图必须覆盖窄窗口（990×638 起）；弹窗本身只有 320–600 宽
        min_w, min_h = (320, 240) if path.name.startswith("dialog-") else (900, 600)
        assert image.width() >= min_w and image.height() >= min_h, (path, image.size())
        # 非空白：纯色画布只有 1 种颜色；小弹窗文字少，阈值放宽
        colors = {image.pixel(x, y) for x in range(0, image.width(), 20)
                  for y in range(0, image.height(), 20)}
        min_colors = 8 if path.name.startswith("dialog-") else 20
        assert len(colors) >= min_colors, (path, len(colors))
