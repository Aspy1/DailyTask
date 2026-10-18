"""自绘抗锯齿圆角的输入控件（CODE_STANDARDS Q-H17 的第二层方案）。

**为什么需要自绘**：QSS 的 `border-radius` 只负责"画一个圆角矩形"，它
① 不会裁剪控件本身，② 绘制时**不开抗锯齿**。在非整数缩放（125%/150%）下，
圆弧会被量化成台阶；再叠加原生方框（已由 `theme.install_rounded_frame_fixer` 关掉），
角上就会看到"角点"。

所以这里把圆角交给 `QPainter` + `Antialiasing`，QSS 只留
`background: transparent; border: none;`（由 `theme.input_qss()` 给出）。

用法：把 `QLineEdit()` / `QComboBox()` 换成 `RoundedLineEdit()` / `RoundedComboBox()`，
其余（样式表、信号、取值）都不用改。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QComboBox, QLineEdit

from src.ui.styles.theme import RADIUS, combo_qss, get_colors, input_qss, qcolor


class _RoundedField:
    """自绘圆角底 + 描边的混入（抗锯齿）。"""

    def _paint_rounded(self) -> None:
        c = get_colors()
        focused = self.hasFocus()  # type: ignore[attr-defined]
        fill = qcolor(c["input_bg"])
        border = qcolor(c["focus_ring"] if focused else c["border"])
        radius = RADIUS["radius_md"]

        painter = QPainter(self)  # type: ignore[arg-type]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 用半个像素内缩，让 1px 描边完整落在控件内
        rect = self.rect().adjusted(0, 0, -1, -1)  # type: ignore[attr-defined]
        painter.setBrush(fill)
        painter.setPen(border)
        painter.drawRoundedRect(rect, radius, radius)
        painter.end()


class RoundedLineEdit(_RoundedField, QLineEdit):
    """自绘圆角的单行输入框。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(input_qss())

    def paintEvent(self, event) -> None:
        self._paint_rounded()
        super().paintEvent(event)          # 文字/光标仍交给 QLineEdit


class RoundedComboBox(_RoundedField, QComboBox):
    """自绘圆角的下拉框（可编辑时内嵌 QLineEdit 由 QSS 保持透明）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(combo_qss())
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def paintEvent(self, event) -> None:
        self._paint_rounded()
        super().paintEvent(event)
