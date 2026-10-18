"""焦点（focus）是一等**交互状态**，必须有自己的令牌。

起因（第四批遗留「令牌体系 §3 · 交互状态成套」）：焦点描边散着用 `accent`，
而 `ToggleSwitch` 的焦点环用的是 **`accent_text`** —— 那是个**文字**令牌，语义错位：
文字色要满足正文对比度（4.5:1），焦点环是**非文本**（3:1 即可），两者要求不同。
现在统一到 `focus_ring`（每模式取**最显眼**的强调色变体）。
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))

# `:focus` 行里不许出现的替身（都该换成 focus_ring）
FORBIDDEN = re.compile(r"""\b(accent_text|accent)\b""")


@pytest.fixture(autouse=True)
def _drop_widgets_created_here(qapp) -> Iterator[None]:
    """本文件造顶层控件；测完按**安全顺序**清掉（见 `test_ui_button_states.py` 的说明）。

    不清理的话解释器退出时 Qt 会乱序销毁 → CI 的 3.12 job 偶发"全过但退出码 1"。
    """
    from PySide6.QtWidgets import QApplication

    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    QApplication.processEvents()


def test_focus_ring_is_defined_for_both_modes() -> None:
    for mode in ("dark", "light"):
        value = TOKENS["colors"][mode].get("focus_ring")
        assert value, f"{mode} 缺 focus_ring"
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value), f"{mode}.focus_ring 不是实色：{value!r}"
    assert "focus_ring" in TOKENS["color_notes"], "focus_ring 没写说明"


def test_focus_rules_use_the_focus_ring_token() -> None:
    """`:focus` 的描边只能用 `focus_ring`，不许再拿 accent / accent_text 顶替。"""
    bad = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ":focus" not in line:
                continue
            if FORBIDDEN.search(line):
                bad.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:90]}")
    assert not bad, "`:focus` 用了 accent / accent_text（应改用 focus_ring）：\n" + "\n".join(bad)


def test_toggle_switch_focus_ring_uses_the_token(qapp) -> None:
    """⚠ U7 回归：开关的焦点环不能再用**文字**令牌画。"""
    from src.ui.widgets.toggle_switch import ToggleSwitch

    src = (ROOT / "src" / "ui" / "widgets" / "toggle_switch.py").read_text(encoding="utf-8")
    assert 'c["focus_ring"]' in src, "开关焦点环没用 focus_ring"
    switch = ToggleSwitch()
    switch.setFocus()
    switch.repaint()          # 只要求不炸：环的颜色必须能取到
