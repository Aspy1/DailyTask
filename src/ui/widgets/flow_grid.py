"""通用流式排布：把子控件按可用宽度排成行，宽度变化时重排。

从 `habit_panel.py` 抽出来（那个文件超「单文件 ≤800」的存量债 —— `Q-A1`），做成通用件：
习惯卡用它排**等宽卡片**，库存标签用它排**自然宽度**的小标签（审查 U6）。

两种模式：

- `uniform=True`（默认）：按列网格排，**列数自适应 + 均分余宽** —— 排卡片；
- `uniform=False`：每项用**自己的**宽度，放不下就换行 —— 排标签。

高度由内容算：`heightForWidth()` + `hasHeightForWidth()`，所以它能直接塞进 layout，
不会像原来那样报一个固定高度（审查 U6）。
"""

from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QSizePolicy, QWidget

DEFAULT_MIN_ITEM_WIDTH = 210


class FlowGrid(QWidget):
    """按行排列子控件，宽度变化时重排（等宽网格 / 自然宽度流式）。"""

    def __init__(self, min_item_width: int = DEFAULT_MIN_ITEM_WIDTH,
                 uniform: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._spacing = 12
        self._min_item_width = min_item_width
        self._uniform = uniform
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)      # ⚠ 少了这句，layout 不会问 heightForWidth
        self.setSizePolicy(policy)

    def setSpacing(self, s: int) -> None:
        self._spacing = s

    def _items(self) -> list[QWidget]:
        return [ch for ch in self.children()
                if isinstance(ch, QWidget) and not ch.isHidden()]

    def _metrics(self, width: int) -> tuple[int, int]:
        """等宽模式下的 (列数, 每项宽度)。"""
        gap = self._spacing
        cols = max(1, (width + gap) // (self._min_item_width + gap))
        return cols, max(self._min_item_width, (width - gap * (cols - 1)) // cols)

    def _item_size(self, child: QWidget, width: int) -> tuple[int, int]:
        """这一项在这个宽度下占 (宽, 高)。"""
        if self._uniform:
            _, item_w = self._metrics(width)
        else:
            item_w = max(child.sizeHint().width(), child.minimumWidth())
        item_h = max(child.minimumHeight(), child.sizeHint().height())
        return item_w, item_h

    def _layout_at(self, width: int, apply: bool) -> int:
        """按 `width` 排一遍，返回所需高度；`apply=False` 时只算不摆（供 `heightForWidth`）。"""
        items = self._items()
        if not items:
            return 0
        gap = self._spacing
        cols = self._metrics(width)[0] if self._uniform else 0
        x = y = row_h = 0
        for i, child in enumerate(items):
            item_w, item_h = self._item_size(child, width)
            wrapped = (i and i % cols == 0) if self._uniform else (x and x + item_w > width)
            if wrapped:
                x, y, row_h = 0, y + row_h + gap, 0
            if apply:
                child.setGeometry(QRect(x, y, item_w, item_h))
                child.show()
            x += item_w + gap
            row_h = max(row_h, item_h)
        return y + row_h

    def _layout_children(self) -> None:
        """按当前宽度排一遍，并把所需高度报给上层（`resizeEvent` 与调用方都用它）。"""
        self.setMinimumHeight(self._layout_at(self.width(), apply=True) + self._spacing)
        self.updateGeometry()

    def heightForWidth(self, width: int) -> int:
        """给定宽度需要多高 —— 放进 layout 时靠它拿高度（审查 U6）。"""
        return self._layout_at(width, apply=False) + self._spacing

    def hasHeightForWidth(self) -> bool:
        return True

    def sizeHint(self) -> QSize:
        width = self.width() or self._min_item_width
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        return QSize(self._min_item_width, self.heightForWidth(self._min_item_width))

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._layout_children()
