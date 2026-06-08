"""Inventory panel — QSS rendering test: 20 methods."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QFrame,
)
from PySide6.QtGui import QFont, QPalette, QColor, QPainter, QLinearGradient, QBrush

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE

METHODS = [
    "1.setStyleSheet直接",
    "2.#objectName",
    "3.无选择器直接",
    "4.QPalette+AutoFill",
    "5.QFrame.StyledPanel",
    "6.rgba(255,0,0,0.3)",
    "7.!important",
    "8.QColor命名",
    "9.渐变色背景",
    "10.border+bg组合",
    "11.WA_StyledBackground",
    "12.父级继承QSS",
    "13.paintEvent覆盖",
    "14.动态属性prop",
    "15.f-string token",
    "16.background简写",
    "17.::after测试",
    "18.QSS+内联混合",
    "19.backgroundColor驼峰",
    "20.setStyleSheet('')",
]


def _color(i):
    return QColor(
        (i * 37 + 10) % 256,
        (i * 73 + 50) % 256,
        (i * 127 + 100) % 256
    )


class Card1(QWidget):
    """1. setStyleSheet with class selector"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet(f"Card1 {{ background-color: #e74c3c; border-radius: 4px; }}")
        self._label(i)

    def _label(self, i):
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card2(QWidget):
    """2. #objectName selector"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setObjectName("card2")
        self.setFixedHeight(70)
        self.setStyleSheet("#card2 { background-color: #e67e22; border-radius: 4px; }")
        self._label(i)
    def _label(self, i):
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card3(QWidget):
    """3. setStyleSheet without selector (direct)"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("background-color: #f1c40f; border-radius: 4px;")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #333; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card4(QWidget):
    """4. QPalette + setAutoFillBackground"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor("#2ecc71"))
        self.setPalette(p)
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px;"); l.addWidget(t)


class Card5(QFrame):
    """5. QFrame with StyledPanel"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setFixedHeight(70)
        self.setStyleSheet("QFrame { background-color: #1abc9c; border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px;"); l.addWidget(t)


class Card6(QWidget):
    """6. rgba() color in QSS"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("Card6 { background-color: rgba(52, 152, 219, 0.8); border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card7(QWidget):
    """7. !important"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("Card7 { background-color: #9b59b6 !important; border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card8(QWidget):
    """8. Named color: 'red', 'blue', etc"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("Card8 { background-color: teal; border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card9(QWidget):
    """9. Gradient via stylesheet qlineargradient"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("Card9 { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #e74c3c,stop:1 #3498db); border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card10(QWidget):
    """10. border + background combination"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("Card10 { background-color: #ff5722; border: 2px solid #333; border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card11(QWidget):
    """11. setAttribute WA_StyledBackground + stylesheet"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("Card11 { background-color: #00bcd4; border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card12(QWidget):
    """12. Parent inherits QSS to child (applied on parent)"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        inner = QWidget(self)
        inner.setObjectName("inner12")
        inner.setStyleSheet("#inner12 { background-color: #e91e63; border-radius: 4px; }")
        vl = QVBoxLayout(self); vl.setContentsMargins(0,0,0,0)
        vl.addWidget(inner)
        il = QHBoxLayout(inner); il.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); il.addWidget(t)


class Card13(QWidget):
    """13. paintEvent override"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self._bg = _color(i)
        self.setFixedHeight(70)
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px;"); l.addWidget(t)
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 4, 4)


class Card14(QWidget):
    """14. Dynamic property selector [status='on']"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setProperty("status", "on")
        self.setStyleSheet("Card14[status='on'] { background-color: #ff9800; border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card15(QWidget):
    """15. f-string with token variable"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        bg = "#673ab7"
        self.setFixedHeight(70)
        self.setStyleSheet(f"Card15 {{ background-color: {bg}; border-radius: 4px; }}")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card16(QWidget):
    """16. background shorthand (no -color suffix)"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("Card16 { background: #4caf50; border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card17(QWidget):
    """17. ::after pseudo (not supported by Qt)"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("Card17 { background-color: #009688; border-radius: 4px; } Card17::after { content: ''; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card18(QWidget):
    """18. QSS + inline palette mix"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("Card18 { background-color: #795548; border-radius: 4px; }")
        self.setAutoFillBackground(True)
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card19(QWidget):
    """19. backgroundColor camelCase"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("Card19 { backgroundColor: #607d8b; border-radius: 4px; }")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #fff; font-size: 11px; border: none; background: transparent;"); l.addWidget(t)


class Card20(QWidget):
    """20. setStyleSheet with empty string (no style)"""
    def __init__(self, i, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("")
        l = QHBoxLayout(self); l.setContentsMargins(8,0,8,0)
        t = QLabel(METHODS[i]); t.setStyleSheet("color: #333; font-size: 11px;"); l.addWidget(t)


CARD_CLASSES = [Card1, Card2, Card3, Card4, Card5, Card6, Card7, Card8, Card9, Card10,
                Card11, Card12, Card13, Card14, Card15, Card16, Card17, Card18, Card19, Card20]


class InventoryPanel(QWidget):
    def __init__(self, dm: DataManager, parent=None):
        super().__init__(parent)
        self._dm = dm
        c = get_colors()
        self.setStyleSheet(f"InventoryPanel {{ background-color: {c['bg_root']}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("taskBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        title = QLabel("QSS 渲染测试 (20种方法)")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bl.addWidget(title)
        bl.addStretch()
        layout.addWidget(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        grid = QVBoxLayout(container)
        grid.setContentsMargins(16, 8, 16, 16)
        grid.setSpacing(6)

        for row in range(10):
            rl = QHBoxLayout()
            rl.setSpacing(6)
            for col in range(2):
                idx = row * 2 + col
                card = CARD_CLASSES[idx](idx)
                rl.addWidget(card, stretch=1)
            grid.addLayout(rl)
        grid.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

    def _refresh(self): pass
    def refresh_theme(self): pass
