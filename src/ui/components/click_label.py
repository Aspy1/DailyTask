"""Shared clickable label — left-click only, hand cursor."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel


class ClickLabel(QLabel):
    clicked = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)
