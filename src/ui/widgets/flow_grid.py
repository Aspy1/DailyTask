"""通用流式网格：把子控件按可用宽度排成行，宽度变化时重排。

从 `habit_panel.py` 抽出来（那个文件 953 行，超「单文件 ≤800」的存量债 —— `Q-A1`）。
做成通用件是有意的：习惯卡用它排卡片，库存标签之类也能用（审查 U6 的"标签用 FlowLayout"）。

两条行为是审查 U6 明确要求的：

1. **列数自适应 + 均分余宽** —— 原来每项固定宽度，右侧留一大片空白；
2. **行高随内容** —— 取 `max(最小高度, sizeHint)`，长标题不再被固定高度裁掉。
"""

from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QWidget

DEFAULT_MIN_ITEM_WIDTH = 210


class FlowGrid(QWidget):
    """按行排列子控件，宽度变化时重排。"""

    def __init__(self, min_item_width: int = DEFAULT_MIN_ITEM_WIDTH, parent=None) -> None:
        super().__init__(parent)
        self._spacing = 12
        self._min_item_width = min_item_width

    def setSpacing(self, s: int) -> None:
        self._spacing = s

    def sizeHint(self) -> QSize:
        return QSize(400, 200)

    def minimumSizeHint(self) -> QSize:
        return QSize(200, 200)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._layout_children()

    def _layout_children(self) -> None:
        """列数自适应 + 均分余宽；行高由内容决定（审查 U6）。"""
        w = self.width()
        gap = self._spacing
        cols = max(1, (w + gap) // (self._min_item_width + gap))
        item_w = max(self._min_item_width, (w - gap * (cols - 1)) // cols)
        children = [ch for ch in self.children()
                    if isinstance(ch, QWidget) and not ch.isHidden()]
        x = y = row_h = 0
        for i, child in enumerate(children):
            if i and i % cols == 0:
                x, y, row_h = 0, y + row_h + gap, 0
            h = max(child.minimumHeight(), child.sizeHint().height())
            child.setGeometry(QRect(x, y, item_w, h))
            child.show()
            x += item_w + gap
            row_h = max(row_h, h)
        self.setMinimumHeight(y + row_h + gap)
        self.updateGeometry()
