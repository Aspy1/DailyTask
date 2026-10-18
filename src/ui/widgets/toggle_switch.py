"""Toggle switch widget — custom painted, no native shadow."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from src.i18n.loader import tr
from src.ui.styles.theme import TOGGLE_H, TOGGLE_W, get_colors


class ToggleSwitch(QWidget):
    """开关：圆角轨道 + 圆形滑块（自绘，无原生阴影）。

    ⚠ **可达性**（审查 U7）：原来是 `QWidget` + 默认 `NoFocus` → **只有鼠标能操作**，
    Tab 到不了、键盘切不了。现在可聚焦、Space/Enter 可切、有可见焦点环。
    ⚠ `setChecked()` 是**程序性**赋值，**不发** `toggled` —— 否则"从数据刷新界面"会反过来
    触发写回（`R-008` 记的那类回环）；只有用户操作才发信号。
    """

    toggled = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(TOGGLE_W, TOGGLE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)          # ⚠ 可 Tab 到（U7）
        self.setAccessibleName(tr("widget.toggle"))
        self.setAccessibleDescription(tr("widget.toggle_hint"))

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        """**程序性**赋值：只改状态并重绘，不发信号（避免"刷新界面 → 又写回数据"）。"""
        if self._checked != checked:
            self._checked = checked
            self.update()

    def _toggle_by_user(self) -> None:
        self._checked = not self._checked
        self.update()
        self.toggled.emit(self._checked)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_by_user()

    def keyPressEvent(self, event) -> None:
        """Space / Enter 也能切（U7：不能只有鼠标路径）。"""
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._toggle_by_user()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        c = get_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_color = QColor(c["accent"]) if self._checked else QColor(c["fg_disabled"])
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 44, 24, 12, 12)

        painter.setBrush(QColor(c["fg_on_fill"]))
        painter.drawEllipse(22 if self._checked else 2, 2, 20, 20)

        if self.hasFocus():
            # 焦点环：全局关掉了系统焦点框却没补，键盘用户看不到自己在哪（U7）
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(c["focus_ring"]), 2))
            painter.drawRoundedRect(1, 1, 42, 22, 11, 11)
        painter.end()
