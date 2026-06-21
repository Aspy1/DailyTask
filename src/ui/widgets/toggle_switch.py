"""Toggle switch widget — custom painted, no native shadow."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QMouseEvent

from src.ui.styles.theme import get_colors


class ToggleSwitch(QWidget):
    """Toggle switch: rounded track + circular thumb."""
    
    toggled = Signal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def isChecked(self) -> bool:
        return self._checked
    
    def setChecked(self, checked: bool) -> None:
        if self._checked != checked:
            self._checked = checked
            self.update()
            self.toggled.emit(checked)
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
    
    def paintEvent(self, event) -> None:
        c = get_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Track
        track_color = QColor(c['accent']) if self._checked else QColor(c['fg_disabled'])
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 44, 24, 12, 12)
        
        # Thumb (circle)
        thumb_color = QColor("#FFFFFF")
        painter.setBrush(thumb_color)
        thumb_x = 22 if self._checked else 2
        painter.drawEllipse(thumb_x, 2, 20, 20)
        
        painter.end()
