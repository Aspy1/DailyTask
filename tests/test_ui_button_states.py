"""UI 审查 U1 / U4 的回归守卫（`dev-logs/2026-10-18-UI审查整改第一批.md`）。

- **U1**：自绘按钮的伪状态必须从**选择器**里读。原来正则把选择器丢掉，于是每个块都落进
  `normal`、后写的覆盖先写的 —— 主按钮最后显示的是 disabled 灰、次级按钮长期用 pressed 色。
- **U4**：不能拿"拼 8 位十六进制"当加透明度用。Qt 的 QSS 把 8 位十六进制当
  **AARRGGBB**，`#B93B3B18` 会被解释成透明橄榄色，而不是浅红。
"""

import pytest

from src.ui.styles.theme import qcolor, rgba
from src.ui.widgets.rounded_button import _extract, _state_of

QSS = ("QPushButton { background: #111111; border: 1px solid #222222; border-radius: 8px; }"
       "QPushButton:hover { background: #333333; }"
       "QPushButton:pressed { background: #444444; }"
       "QPushButton:disabled { background: #555555; }")


def test_pseudo_states_are_parsed_from_the_selector() -> None:
    """⚠ U1 回归：四个状态各归各位，不再互相覆盖。"""
    colors, border, radius = _extract(QSS)

    assert colors["normal"] == qcolor("#111111")
    assert colors["hover"] == qcolor("#333333")
    assert colors["pressed"] == qcolor("#444444")
    assert colors["disabled"] == qcolor("#555555")
    assert border == qcolor("#222222")
    assert radius == 8


def test_state_priority_prefers_disabled_over_hover() -> None:
    """同时带多个伪状态时按优先级取（`:hover:disabled` 是禁用态）。"""
    assert _state_of("QPushButton:hover:disabled") == "disabled"
    assert _state_of("QPushButton:pressed:hover") == "pressed"
    assert _state_of("QPushButton:checked") == "checked"
    assert _state_of("QPushButton") == "normal"


def test_rgba_helper_is_not_hex_alpha_concatenation() -> None:
    """⚠ U4 回归：用 `rgba()`，不要拼 `{color}18`。"""
    out = rgba("#B93B3B", 0.1)
    assert out == "rgba(185, 59, 59, 0.100)"
    assert "#B93B3B18" not in out


def test_rgba_clamps_alpha() -> None:
    assert rgba("#000000", 5) == "rgba(0, 0, 0, 1.000)"
    assert rgba("#000000", -1) == "rgba(0, 0, 0, 0.000)"


def _luminance(color: str) -> float:
    """相对亮度（WCAG）—— 只看 `#RRGGBB`。"""
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    lo, hi = min(a, b), max(a, b)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_code_block_pair_has_enough_contrast(mode) -> None:
    """⚠ U8 回归：`code_bg` 是深色，文字必须配 `code_fg`。

    原来浅色主题的代码块继承正文色（深字 + 深底）→ 实测只有 1.32:1。
    """
    from src.ui.styles.theme import TOKENS

    pair = TOKENS[mode]
    ratio = _contrast(pair["code_fg"], pair["code_bg"])
    assert ratio >= 4.5, f"{mode}: code_fg/code_bg 只有 {ratio:.2f}:1"


def test_markdown_escapes_user_html() -> None:
    """⚠ U3 的一半：用户正文里的 `<b>` 不能被当成标签渲染。"""
    from src.ui.components.ai_panel import _md_to_html

    assert "&lt;b&gt;" in _md_to_html("<b>不是标签</b>")
    assert "<b>粗</b>" in _md_to_html("**粗**")
