"""「今日提示」条：可点掉的提示（点掉只影响今天，**不写数据**）。

规则与设计见 `src/services/hints.py`。

**继承 `FlowGrid`**（自然宽度流式）而不是横排 —— 提示条会随数据变多
（天气 + 该洗 + 预算 + 出门三条 = 可能 6 条 ✗），横排会把最后几条**挤出屏幕** ✗。
2026-10-19 渲染实测：4 条就有一条被切掉 ✓ → 换成会**换行**的流式排布。
"""

from datetime import date

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
        self._dismissed_on = ""          # "已点掉"属于**哪一天**（跨天自动失效）
        self._hints: list[Hint] = []

    def refresh(self) -> None:
        """重新算一遍今天的提示并重画（换主题 / 数据变化都走这里）。"""
        self.show_hints(today_hints(self._data_dir) if self._data_dir else [])

    @staticmethod
    def _chip_qss(level: str, c: dict) -> str:
        """提示的配色**按级别分开**（2026-10-19 审查：原来所有提示都橙色，普通建议和警告一样抢眼）。

        - `warn`（预算超支这类）→ 橙色，要抢眼；
        - `info`（带伞 / 该洗 / 出门）→ 中性底，别和警告一样吵。
        """
        if level == "warn":
            bg, fg, hover = c["orange_tint"], c["orange"], c["orange_tint_weak"]
        else:
            bg, fg, hover = c["bg_elevated"], c["fg_secondary"], c["btn_secondary_hover"]
        return (f"QPushButton {{ background-color: {bg}; color: {fg}; border: none;"
                f" border-radius: 8px; padding: 4px 10px; font-size: 13px; }}"
                f" QPushButton:hover {{ background-color: {hover}; }}")

    @staticmethod
    def _wrap_text(text: str) -> str:
        """长提示**折成两行** —— `QPushButton` 不会自动换行（审查：单条长提示也要换行）。

        优先在「——」处断（那是"原因 —— 内容"的自然分界），否则按 24 字硬折。
        """
        if len(text) <= 24:
            return text
        cut = text.find("——")
        if 0 < cut < len(text) - 2:
            return text[:cut + 2].rstrip() + "\n" + text[cut + 2:].lstrip()
        return text[:24] + "\n" + text[24:]

    def show_hints(self, hints: list) -> None:
        """重画（已点掉的 key 不再出现）。

        ⚠ **跨天自动清**：以前靠外部调 `clear_dismissed()`，而**全仓没人调** ✗ ——
        常驻应用跨天后，昨天关掉的雨天/出门提示今天还被过滤着（2026-10-19 审查）。
        现在把"点掉"记在**当天**名下，`show_hints` 是唯一出口，跨天自己失效 ✓。
        """
        today = date.today().isoformat()
        if self._dismissed_on != today:
            self._dismissed.clear()
            self._dismissed_on = today
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
            chip = RoundedButton(f"{self._wrap_text(hint.text)}   ✕")
            chip.setParent(self)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(self._chip_qss(hint.level, c))
            chip.clicked.connect(lambda _checked=False, k=hint.key: self._dismiss(k))
            chip.show()
            shown += 1
        self._layout_children()
        self.update()
        self.setVisible(bool(shown))

    def _dismiss(self, key: str) -> None:
        self._dismissed.add(key)
        self._dismissed_on = date.today().isoformat()
        self.show_hints(self._hints)
