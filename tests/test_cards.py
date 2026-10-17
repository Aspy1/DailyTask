"""卡片自绘（`src/ui/styles/cards.py`）的形状守卫。

卡片是**自绘**的（`QPainter` + 抗锯齿），形状对不对没法读样式表验证 —— 只能看
画出来的像素。这里钉住最容易"被简化掉"的两处几何：

1. `sub` 变体：左侧色条 + **左两角改方** + 右两角仍圆。改方靠 `QPainterPath` 的
   **并集**（`WindingFill` + `addRect`）；谁把 `setFillRule` 删了，默认的奇偶填充
   就会把重叠区**挖空** → 左角静默退化成缺口。
2. 四角之外必须露父背景（不是卡片底色）。

⚠ 探针位置有讲究：测"方角"必须落在**色条宽度之外**，否则色条会替方角画上，
即使 `WindingFill` 丢了也照样通过。下方 `CORNER_X = 5` 就是为此选的
（色条 4px、圆角 8px → x=5 恰好在"圆角会挖掉、方角才保留"的那几个像素里）。
"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from src.ui.styles.cards import card
from src.ui.styles.theme import get_colors, qcolor

CARD_H = 40
# 圆角外但方角内、且**不被左色条覆盖**的横坐标（见模块 docstring）
CORNER_X = 5
# 卡片路径为给描边留 1px，最后一行不画 → 用倒数第二行探四角
CORNER_ROW = CARD_H - 2


def _two_cards(qapp) -> tuple[QWidget, object, object]:
    """宿主 200×90，竖排 `item` + `sub` 两张等高卡（紧贴、无间距）。"""
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    item, sub = card("item"), card("sub")
    for w in (item, sub):
        w.setFixedHeight(CARD_H)
        lay.addWidget(w)
    host.resize(200, 2 * CARD_H + 10)
    lay.activate()
    qapp.processEvents()
    return host, item, sub


def _px(img, x: int, y: int) -> tuple[int, int, int]:
    c = img.pixelColor(x, y)
    return (c.red(), c.green(), c.blue())


def _colors() -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    c = get_colors()
    return (tuple(qcolor(c["accent"]).getRgb()[:3]),
            tuple(qcolor(c["bg_elevated"]).getRgb()[:3]))


def test_sub_variant_has_left_bar(qapp) -> None:
    host, item, sub = _two_cards(qapp)
    img = host.grab().toImage()
    accent, bg = _colors()

    assert _px(img, 1, sub.geometry().top() + CARD_H // 2) == accent
    # 对照：item 同位置是卡片底色，没有色条
    assert _px(img, 1, item.geometry().top() + CARD_H // 2) == bg


def test_sub_variant_squares_left_corners(qapp) -> None:
    host, item, sub = _two_cards(qapp)
    img = host.grab().toImage()
    _accent, bg = _colors()
    row = CORNER_ROW

    # sub 的左下角在**方角**内 → 卡片底色
    assert _px(img, CORNER_X, sub.geometry().top() + row) == bg
    # 对照：item 同位置在圆角外 → 不是卡片底色
    assert _px(img, CORNER_X, item.geometry().top() + row) != bg


def test_sub_variant_keeps_right_corners_rounded(qapp) -> None:
    host, _item, sub = _two_cards(qapp)
    img = host.grab().toImage()
    _accent, bg = _colors()
    sy = sub.geometry().top()
    right = img.width() - 2

    assert _px(img, right, sy + CORNER_ROW) != bg     # 右下角仍在圆弧外
    assert _px(img, right, sy + CARD_H // 2) == bg    # 右边缘中段是卡片底色
