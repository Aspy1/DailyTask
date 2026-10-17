"""卡片（内容/展示类圆角框）的**唯一实现** + 变体表。

## 为什么要自绘

QSS 的 `border-radius` ①**不裁剪**控件 ②绘制时**不开抗锯齿** → 在非整数缩放
（125%/150%）下圆弧被量化成台阶（`design/INDEX.md` §5）。卡片虽然不像输入框那样
必须裁内容，但「大圆角 + 高对比 + 非整数缩放」三样凑齐时，四角的台阶是看得见的，
所以和输入/按钮一样走自绘（`QPainter` + `Antialiasing`）。

## 怎么用

```python
from src.ui.styles.cards import card

box = card("item")            # 变体名，**不传任何像素尺寸**
lay = QVBoxLayout(box)        # 内边距已由变体设好（contentsMargins）
lay.addWidget(...)
```

- 改「所有卡片」→ 改 `design/tokens.json`（颜色/圆角/间距）
- 改「某一类卡片」→ 改本文件 `CARD_VARIANTS` 的**一行**
- 新增一类卡片 → 加**一行**（然后补进 `design/INDEX.md`）

**尺寸不给卡片函数**：长宽由 layout 决定（卡片是弹性的）。固定尺寸只在
「图标按钮 / 对齐用输入框宽」这类确有必要的场景使用，且必须走令牌。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame

from src.ui.styles.theme import RADIUS, SPACING, get_colors, qcolor

# 变体表：值全部是令牌名 / spacing 档位名（不写像素）
CARD_VARIANTS: dict[str, dict] = {
    "panel":  {"radius": "radius_md", "bg": "bg_card", "pad": "spacing_lg",
               "border": False},
    "item":   {"radius": "radius_md", "bg": "bg_elevated", "pad": "spacing_md",
               "border": False},
    "chip":   {"radius": "radius_sm", "bg": "bg_input", "pad": "spacing_xs",
               "border": False},
    "bubble": {"radius": "radius_lg", "bg": "bg_elevated", "pad": "spacing_sm",
               "border": False},
    "pill":   {"radius": "radius_pill", "bg": "bg_input", "pad": "spacing_xs",
               "border": False},
}

DEFAULT_VARIANT = "panel"


class Card(QFrame):
    """自绘圆角的内容卡片（用 `card()` 造，别自己写 QSS）。

    颜色在 `paintEvent` 里**现取令牌** → 切主题时全局重绘会自动带上新颜色，
    不需要逐个卡片接线（对比：写死样式表的控件必须显式 `refresh_theme()`）。
    """

    def __init__(self, variant: str = DEFAULT_VARIANT, pad: str | None = None,
                 bg: str | None = None, hover_bg: str | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._variant = variant if variant in CARD_VARIANTS else DEFAULT_VARIANT
        spec = CARD_VARIANTS[self._variant]
        # bg / hover_bg 传**令牌名**（如 "bg_surface" / "accent_bg"）覆盖变体默认；
        # 在 paintEvent 里现取令牌 → 切主题自动跟随
        self._bg = bg or spec["bg"]
        self._hover_bg = hover_bg
        self._hovered = False
        # pad=None → 用变体默认；pad="spacing_none" → 内边距交给内容（有些面板的
        # 每一行自带 16/12 的内边距，卡片再设一次就会**双重内边距**）
        gap = SPACING[pad if pad in SPACING else spec["pad"]]
        # 调用方拿到控件后直接挂自己的 layout：内边距已经就位
        self.setContentsMargins(gap, gap, gap, gap)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    @property
    def variant(self) -> str:
        return self._variant

    def enterEvent(self, event) -> None:
        if self._hover_bg:
            self._hovered = True
            self.update()

    def leaveEvent(self, event) -> None:
        if self._hover_bg:
            self._hovered = False
            self.update()

    def paintEvent(self, event) -> None:
        spec = CARD_VARIANTS[self._variant]
        c = get_colors()
        rect = self.rect().adjusted(0, 0, -1, -1)
        # pill 的 999 必须钳到一半，否则 QPainterPath 画不出
        radius = min(RADIUS[spec["radius"]], rect.height() / 2, rect.width() / 2)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        bg_name = self._hover_bg if (self._hovered and self._hover_bg) else self._bg
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillPath(path, qcolor(c[bg_name]))
        if spec.get("border"):
            pen = QPen(qcolor(c["border"]))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawPath(path)
        painter.end()


def card(variant: str = DEFAULT_VARIANT, pad: str | None = None,
         bg: str | None = None, hover_bg: str | None = None, parent=None) -> Card:
    """造一张卡片（唯一入口）。**不要**传尺寸 —— 长宽交给 layout。

    `pad` 传 spacing 令牌名可覆盖变体默认（`"spacing_none"` = 内边距由内容自己管）；
    `bg` / `hover_bg` 传**令牌名**可覆盖底色（可点击卡用 `hover_bg="accent_bg"`）。
    """
    return Card(variant, pad, bg, hover_bg, parent)
