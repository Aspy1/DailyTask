"""Custom context menu widget - avoids Windows native shadow."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QFrame
from PySide6.QtGui import QFont, QCursor, QMouseEvent
from PySide6.QtCore import Qt, Signal, QObject

from src.ui.styles.theme import get_colors, SIZE_BODY_S, FONT_CN


class MenuAction(QObject):
    """Represents a menu action - can be compared to determine which was clicked."""
    
    triggered = Signal(bool)
    
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._clicked = False
        self._data: tuple | None = None
        self._checkable = False
        self._checked = False
    
    def __eq__(self, other):
        if isinstance(other, MenuAction):
            return self is other
        return False
    
    @property
    def text(self) -> str:
        return self._text
    
    @property
    def data(self) -> tuple | None:
        return self._data
    
    @property
    def checked(self) -> bool:
        return self._checked
    
    def setData(self, data: tuple) -> None:
        """Set action data (compatible with QAction.setData)."""
        self._data = data
    
    def setCheckable(self, checkable: bool) -> None:
        """Set whether action is checkable."""
        self._checkable = checkable
    
    def setChecked(self, checked: bool) -> None:
        """Set checked state."""
        self._checked = checked
    
    def trigger(self):
        self._clicked = True
        self.triggered.emit(self._checked)


class ContextMenuItem(QPushButton):
    clicked = Signal(str)
    triggered = Signal()

    def __init__(self, text: str, action: MenuAction = None, parent=None):
        super().__init__(text, parent)
        self._action = action
        c = get_colors()
        
        # Show checkmark if action is checkable and checked
        check_prefix = ""
        if action and action._checkable:
            check_prefix = "✓ " if action._checked else "    "
        
        self.setText(check_prefix + text)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {c['fg_primary']};
                border: none; border-radius: 4px;
                padding: 8px 12px; font-size: {SIZE_BODY_S}px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {c['accent_bg']};
            }}
            QPushButton:pressed {{
                background-color: {c['accent_bg']};
            }}
        """)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        if self._action:
            # Toggle checked state if checkable BEFORE triggering
            if self._action._checkable:
                self._action._checked = not self._action._checked
            self._action.trigger()
        # Find parent ContextMenu and close it
        p = self.parent()
        while p and not isinstance(p, ContextMenu):
            p = p.parent()
        if p:
            p._last_action = self._action
            p.close()


class ContextMenuSeparator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        c = get_colors()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"color: {c['divider']}; margin: 4px 8px;")


class ContextMenu(QWidget):
    """Custom context menu using QWidget - avoids Windows native shadow.
    
    Features:
        - No native shadow, fully styled with QSS
        - Proper rounded corners
        - Hover/pressed states
        - Auto-close on click outside
        - Supports separators
        - Returns clicked action for comparison
    
    Usage (callback style):
        menu = ContextMenu()
        menu.add_item("编辑", lambda: self._edit())
        menu.add_item("删除", lambda: self._delete())
        menu.exec()
    
    Usage (action comparison style - compatible with QMenu pattern):
        menu = ContextMenu()
        edit_action = menu.add_action("编辑")
        delete_action = menu.add_action("删除")
        menu.exec()
        if menu.last_action == edit_action:
            self._edit()
        elif menu.last_action == delete_action:
            self._delete()
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        c = get_colors()
        
        self._last_action: MenuAction | None = None
        
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        
        self._content = QWidget()
        self._content.setStyleSheet(f"""
            QWidget {{
                background-color: {c['bg_elevated']};
                border: 1px solid {c['border_strong']};
                border-radius: 8px;
            }}
        """)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(0)
        self._layout.addWidget(self._content)

    def add_item(self, text: str, callback=None) -> None:
        """Add menu item with callback."""
        item = ContextMenuItem(text, None, self._content)
        if callback:
            item.clicked.connect(callback)
        self._content_layout.addWidget(item)

    def add_action(self, text: str) -> MenuAction:
        """Add menu item and return action for comparison. Compatible with QMenu pattern."""
        action = MenuAction(text, self)
        item = ContextMenuItem(text, action, self._content)
        self._content_layout.addWidget(item)
        return action

    def add_separator(self) -> None:
        sep = ContextMenuSeparator()
        self._content_layout.addWidget(sep)

    @property
    def last_action(self) -> MenuAction | None:
        """Returns the last clicked action. Use for comparison pattern."""
        return self._last_action

    def exec(self, pos=None) -> None:
        if pos is None:
            pos = QCursor.pos()
        
        self._last_action = None
        self.adjustSize()
        screen_geo = self.screen().geometry()
        x = pos.x()
        y = pos.y()
        
        if x + self.width() > screen_geo.width():
            x = screen_geo.width() - self.width()
        if y + self.height() > screen_geo.height():
            y = screen_geo.height() - self.height()
        
        self.move(x, y)
        self.show()
        
        # Block until menu is closed (like QMenu.exec)
        from PySide6.QtCore import QEventLoop
        loop = QEventLoop()
        self.destroyed.connect(loop.quit)
        loop.exec()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if not self.rect().contains(ev.pos()):
            self.close()
        super().mousePressEvent(ev)