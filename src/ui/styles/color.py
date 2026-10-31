"""设计令牌的 QColor 解析（从 `theme.py` 分出：单文件 ≤800 行，Q-A1）。

`theme.py` 重新导出 `qcolor` / `rgba`，所以既有 import 路径不变。
"""

from PySide6.QtGui import QColor


def _qcolor_from_hash(css: str, alpha: float | None) -> QColor:
    """`#rrggbb` / `#rrggbbaa`（**CSS 语义：alpha 在后**）。

    ⚠ Qt 的 `QColor` 把 8 位 hex 按 `#AARRGGBB` 读，而 QSS 按 CSS 的 `#RRGGBBAA` 读 ——
    同一串颜色两种含义，混用会**静默画错色**（实测 `QColor("#d6454512")` →
    `rgba(69,69,18,214)`，一个橄榄绿）。这里统一按 CSS 语义解释。
    """
    if len(css) == 9:
        css = "#" + css[7:9] + css[1:7]
    color = QColor(css)
    if alpha is not None:
        color.setAlphaF(alpha)
    return color


def _qcolor_from_rgb(css: str, alpha: float | None) -> QColor:
    """`rgba(r,g,b,a)` / `rgb(r,g,b)`。"""
    parts = [p.strip() for p in css[css.index("(") + 1:css.rindex(")")].split(",")]
    r, g, b = (int(float(p)) for p in parts[:3])
    a = float(parts[3]) if len(parts) > 3 else 1.0
    if alpha is not None:
        a = alpha
    return QColor(r, g, b, int(a * 255))


def qcolor(css: str, alpha: float | None = None) -> QColor:
    """token 色值 → QColor（`#rrggbb` / `#rrggbbaa` / `rgba(...)`）。

    自绘控件族（输入/按钮/卡片）都要把令牌值交给 QPainter，`QColor("#rrggbb")`
    能直接吃，但 `rgba(...)` 不行 —— 所以统一在这里解析。
    """
    css = css.strip()
    if css.startswith("#"):
        return _qcolor_from_hash(css, alpha)
    if css.startswith("rgb"):
        return _qcolor_from_rgb(css, alpha)
    if css in ("transparent", "none", ""):
        return QColor(0, 0, 0, 0)
    return QColor(css)


def rgba(color: str, alpha: float) -> str:
    """把 `#RRGGBB` 加透明度 → `rgba(r, g, b, a)`。

    ⚠ 别写 `f"{color}18"`：Qt 的 QSS 把 8 位十六进制当 **AARRGGBB**（不是 RRGGBBAA），
    于是 `#B93B3B18` 被解释成"透明橄榄色"而不是"浅红"（审查 U4）。
    """
    col = qcolor(color)
    return (f"rgba({col.red()}, {col.green()}, {col.blue()}, "
            f"{max(0.0, min(1.0, alpha)):.3f})")
