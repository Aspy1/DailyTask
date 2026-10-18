"""「今日提示」条：一行可点掉的提示（点掉只影响今天，**不写数据**）。

规则与设计见 `src/services/hints.py`。这里只负责画 + 记住"今天点掉了哪些"。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from src.ui.styles.theme import get_colors
from src.ui.widgets.rounded_button import RoundedButton


class HintBar(QWidget):
    """把 `hints.Hint` 列表渲染成一行；没有（或全点掉了）就整条隐藏。

    自己从 `data_dir` 读天气（派生缓存）—— 调用方只管 `refresh()`，不用管数据从哪来。
    """

    def __init__(self, data_dir=None, parent=None) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(6)
        self._dismissed: set[str] = set()
        self._hints: list = []

    def refresh(self) -> None:
        """重新算一遍今天的提示并重画（换主题 / 数据变化都走这里）。"""
        from src.services.hints import today_hints

        self.show_hints(today_hints(self._data_dir) if self._data_dir else [])

    def show_hints(self, hints: list) -> None:
        """重画（已点掉的 key 不再出现）。每次调用都重画 —— 换主题也走这里。"""
        self._hints = list(hints)
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        c = get_colors()
        shown = 0
        for hint in self._hints:
            if hint.key in self._dismissed:
                continue
            chip = RoundedButton(f"{hint.text}   ✕")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                f"QPushButton {{ background-color: {c['orange_tint']};"
                f" color: {c['orange']}; border: none; border-radius: 8px;"
                f" padding: 4px 10px; font-size: 13px; }}"
                f" QPushButton:hover {{ background-color: {c['orange_tint_weak']}; }}")
            chip.clicked.connect(lambda _checked=False, k=hint.key: self._dismiss(k))
            self._row.addWidget(chip)
            shown += 1
        self._row.addStretch()
        self.setVisible(bool(shown))

    def _dismiss(self, key: str) -> None:
        self._dismissed.add(key)
        self.show_hints(self._hints)

    def clear_dismissed(self) -> None:
        """换天时清掉"已点掉"记录（提示是**今天**的）。"""
        self._dismissed.clear()
