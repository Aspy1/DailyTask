"""「今日提示」条：可点掉的提示（点掉只影响今天，**不写数据**）。

规则与设计见 `src/services/hints.py`。

**继承 `FlowGrid`**（自然宽度流式）而不是横排 —— 提示条会随数据变多
（天气 + 该洗 + 预算 + 出门三条 = 可能 6 条 ✗），横排会把最后几条**挤出屏幕** ✗。
2026-10-19 渲染实测：4 条就有一条被切掉 ✓ → 换成会**换行**的流式排布。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from src.services.hints import Hint, today_hints
from src.ui.styles.theme import get_colors
from src.ui.widgets.flow_grid import FlowGrid
from src.ui.widgets.rounded_button import RoundedButton


class HintBar(FlowGrid):
    """今天的提示（一行放不下就换行）；没有（或全点掉了）就整条隐藏。"""

    def __init__(self, data_dir=None, parent=None) -> None:
        super().__init__(uniform=False, parent=parent)
        self._data_dir = data_dir
        self.setSpacing(6)
        self._dismissed: set[str] = set()
        self._hints: list[Hint] = []

    def refresh(self) -> None:
        """重新算一遍今天的提示并重画（换主题 / 数据变化都走这里）。"""
        self.show_hints(today_hints(self._data_dir) if self._data_dir else [])

    def show_hints(self, hints: list) -> None:
        """重画（已点掉的 key 不再出现）。"""
        self._hints = list(hints)
        for child in list(self.children()):
            if isinstance(child, QWidget):
                child.setParent(None)
                child.deleteLater()
        c = get_colors()
        shown = 0
        for hint in self._hints:
            if hint.key in self._dismissed:
                continue
            chip = RoundedButton(f"{hint.text}   ✕")
            chip.setParent(self)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                f"QPushButton {{ background-color: {c['orange_tint']};"
                f" color: {c['orange']}; border: none; border-radius: 8px;"
                f" padding: 4px 10px; font-size: 13px; }}"
                f" QPushButton:hover {{ background-color: {c['orange_tint_weak']}; }}")
            chip.clicked.connect(lambda _checked=False, k=hint.key: self._dismiss(k))
            chip.show()
            shown += 1
        self._layout_children()
        self.update()
        self.setVisible(bool(shown))

    def _dismiss(self, key: str) -> None:
        self._dismissed.add(key)
        self.show_hints(self._hints)

    def clear_dismissed(self) -> None:
        """换天时清掉"已点掉"记录（提示是**今天**的）。"""
        self._dismissed.clear()
