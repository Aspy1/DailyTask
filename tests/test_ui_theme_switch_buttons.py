"""主题切换不许破坏按钮样式与伪状态选择器 —— 2026-10-19 审查 R4 的回归。

两个独立病灶：

1. **`remap_colors` 的正则扫整段 QSS** ✗ —— `QPushButton:hover` 里的 `hover` 被当成属性名，
   输出变成 `QPushButton: hover`，伪状态选择器全被改坏（hover/pressed/disabled 失效）。
2. **全局 `app.setStyleSheet(...)` 也发 StyleChange** ✗ —— `RoundedButton.changeEvent`
   拿"已经剥掉背景的 `styleSheet()`"当原始样式覆盖掉 `_original_qss`，
   于是自绘底色塌成透明（实测四个背景状态变成一个 alpha=0 的 normal）。
"""

from src.ui.styles.theme import remap_colors
from src.ui.widgets.rounded_button import RoundedButton

# (文字映射, 填充映射)
MAPS = ({"#111111": "#222222"}, {"#333333": "#444444"})


# ── 病灶 1：只改花括号里的声明 ──────────────────────────────

def test_remap_colors_keeps_pseudo_state_selectors() -> None:
    """⭐ `hover` / `pressed` / `disabled` 是**伪状态**，不是属性名。"""
    qss = ("QPushButton { background: #333333; color: #111111; }"
           "QPushButton:hover { background: #111111; }"
           "QPushButton:disabled { color: #333333; }")
    out = remap_colors(qss, MAPS)
    assert "QPushButton:hover" in out and "QPushButton:disabled" in out
    assert "QPushButton: hover" not in out and "QPushButton: disabled" not in out
    # 色值该换的换了（填充走填充映射、文字走文字映射）
    assert "#444444" in out and "#222222" in out


def test_remap_colors_still_handles_bare_declarations() -> None:
    """部件级 `setStyleSheet("color: …")`（**没有选择器**）仍然要能换色。"""
    assert remap_colors("color: #111111; font-size: 13px;", MAPS) == \
        "color: #222222; font-size: 13px;"


# ── 病灶 2：全局换样式不许覆盖原始样式 ──────────────────────

def test_global_stylesheet_change_does_not_clobber_original_qss(qapp) -> None:
    """⭐ 应用换主题走 `app.setStyleSheet(...)` —— 那时**原始样式必须保持不动**。"""
    btn = RoundedButton("发送")
    btn.setStyleSheet("QPushButton { background: #333333; color: #111111; }")
    btn.show()
    qapp.processEvents()
    btn.repaint()                      # 触发一次吸收
    qapp.processEvents()
    original = btn._original_qss
    assert original, "应当已经吸收到原始样式"

    qapp.setStyleSheet("QLabel { color: #888888; }")      # 模拟换主题的全局设置
    qapp.processEvents()
    assert btn._original_qss == original, "全局换样式把原始样式覆盖了（底色会塌成透明）"

    # 正反多次切换也要稳
    for qss in ("QLabel { color: #999999; }", "", "QLabel { color: #aaaaaa; }"):
        qapp.setStyleSheet(qss)
        qapp.processEvents()
        assert btn._original_qss == original
    qapp.setStyleSheet("")


def test_external_restyle_is_still_adopted(qapp) -> None:
    """反向：**调用方自己**重新 `setStyleSheet` 时，新样式必须被当成新的原始样式。"""
    btn = RoundedButton("发送")
    btn.setStyleSheet("QPushButton { background: #333333; }")
    btn.show()
    qapp.processEvents()
    btn.repaint()
    qapp.processEvents()

    btn.setStyleSheet("QPushButton { background: #555555; }")
    qapp.processEvents()
    assert "#555555" in btn._original_qss, "外部重新设的样式必须被采纳"
