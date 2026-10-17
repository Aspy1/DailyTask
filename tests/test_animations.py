"""动效模板的测试（CODE_STANDARDS Q-H16 + R-008 动画条）。

守住的边界：
1. 只做 opacity / 位移：**模块里不得出现几何动画**（`geometry` / `setFixedHeight` 之类）
2. 动画对象保引用（被 GC 会中断）
3. 时长 ≤180ms、缓动 `OutCubic`
4. 数值滚动最终落到目标值；总开关能一键关掉
"""

import time
from pathlib import Path

from PySide6.QtWidgets import QLabel, QWidget

from src.ui import animations


def _settle(ms: int = 260) -> None:
    """等动画跑完（Qt 动画靠事件循环推进）。

    ⚠ **不要**在这里 `gc.collect()`：中途强制回收会碰到"Python 包装器还在、
    C++ 对象已销毁"的控件 → 崩在 collect 里（2026-10-17 CI 实测）。
    回收统一放在测试边界的 conftest `_cleanup_qt_leftovers`（那里没有事件循环在跑），
    并先停掉服务类残留定时器。
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_fade_in_only_animates_opacity(qapp) -> None:
    """结构守卫：动效模块不得动几何（R-008 禁止动画化布局尺寸）。"""
    source = Path(animations.__file__).read_text(encoding="utf-8")
    for banned in ("b\"geometry\"", "b'geometry'", "setFixedHeight", "setFixedWidth",
                   "b\"pos\"", "resize("):
        assert banned not in source, f"动效模块里出现了几何动画：{banned}"


def test_fade_in_reaches_full_opacity_then_drops_effect(qapp) -> None:
    """淡入结束后必须摘掉透明效果，且**渲染像素与未动画时一致**（不能发虚）。"""
    widget = QWidget()
    widget.resize(80, 40)
    widget.show()
    _settle(60)
    before = widget.grab().toImage()

    first = animations.fade_in(widget)
    assert first is not None
    assert first.duration() <= 180
    assert first.easingCurve().type() == animations.QEasingCurve.Type.OutCubic
    assert id(widget) in animations._RUNNING      # 保引用

    _settle()
    assert widget.graphicsEffect() is None        # 效果已摘掉

    after = widget.grab().toImage()
    assert before == after, "动画结束后像素应与动画前一致（否则说明留有离屏渲染的虚化）"

    animations.fade_in(widget)                    # 再淡入一次仍然可用
    assert widget.graphicsEffect() is not None


def test_fade_popup_uses_window_opacity(qapp) -> None:
    from PySide6.QtWidgets import QMenu

    menu = QMenu()
    anim = animations.fade_popup(menu)
    assert anim is not None
    assert anim.duration() <= 180
    assert menu.windowOpacity() == 0.0            # 先透明，再淡入

    _settle()
    assert menu.windowOpacity() > 0.9


def test_count_to_lands_on_target(qapp) -> None:
    label = QLabel("¥0")
    assert animations.count_to(label, 96.93, fmt="¥{:.0f}") is not None
    _settle(320)
    assert label.text() == "¥97"


def test_count_to_is_noop_when_equal(qapp) -> None:
    label = QLabel("¥12")
    assert animations.count_to(label, 12, fmt="¥{:.0f}") is None
    assert label.text() == "¥12"


def test_global_switch_disables_motion(qapp) -> None:
    widget = QWidget()
    try:
        animations.set_enabled(False)
        assert animations.fade_in(widget) is None
        assert widget.graphicsEffect() is None
        label = QLabel("¥0")
        assert animations.count_to(label, 50, fmt="¥{:.0f}") is None
        assert label.text() == "¥50"              # 关掉动效也要落到目标值
    finally:
        animations.set_enabled(True)


def test_panel_switch_triggers_fade(qapp, monkeypatch) -> None:
    """面板切换必须走淡入模板（而不是各自写动画）。"""
    from src.services.ai_service import AIService
    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager
    from src.ui.components import main_workspace

    calls: list[object] = []
    monkeypatch.setattr(main_workspace, "fade_in", lambda w, **k: calls.append(w))

    import tempfile
    from pathlib import Path as _Path

    tmp = _Path(tempfile.mkdtemp())
    settings = SettingsManager(tmp / "settings.ini")
    settings.load()
    dm = DataManager(tmp)
    ws = main_workspace.MainWorkspace(settings, AIService(settings, dm), dm, None)

    ws.switch_to("tasks")
    assert calls and calls[-1] is ws._task_panel
