"""Inventory panel — test: 20 cards with verified working QSS methods."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QFrame,
)
from PySide6.QtGui import QFont, QPalette, QColor, QPainter

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE


def make_style3(w, i, color):
    """Method 3: no-selector direct — CONFIRMED WORKING"""
    w.setStyleSheet(f"background-color: {color}; border-radius: 8px;")
    l = QHBoxLayout(w); l.setContentsMargins(12, 0, 12, 0)
    t = QLabel(f"#3 无选择器 {i+1}"); t.setStyleSheet("color: #fff; font-size: 13px; font-weight: 600; border: none; background: transparent;"); l.addWidget(t)

def make_style4(w, i, color):
    """Method 4: QPalette — CONFIRMED WORKING"""
    w.setAutoFillBackground(True)
    p = w.palette(); p.setColor(QPalette.ColorRole.Window, QColor(color)); w.setPalette(p)
    w.setStyleSheet("border-radius: 8px;")
    l = QHBoxLayout(w); l.setContentsMargins(12, 0, 12, 0)
    t = QLabel(f"#4 QPalette {i+1}"); t.setStyleSheet("color: #fff; font-size: 13px; font-weight: 600;"); l.addWidget(t)

def make_style5(w, i, color):
    """Method 5: QFrame StyledPanel — CONFIRMED WORKING (but needs QFrame parent)"""
    # Can't use here — requires QFrame subclass

def make_style11(w, i, color):
    """Method 11: WA_StyledBackground + direct — CONFIRMED WORKING"""
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    w.setStyleSheet(f"background-color: {color}; border-radius: 8px;")
    l = QHBoxLayout(w); l.setContentsMargins(12, 0, 12, 0)
    t = QLabel(f"#11 WA+QSS {i+1}"); t.setStyleSheet("color: #fff; font-size: 13px; font-weight: 600; border: none; background: transparent;"); l.addWidget(t)

def make_style13(w, i, color):
    """Method 13: paintEvent — CONFIRMED WORKING (needs subclass)"""


class PaintCard(QWidget):
    def __init__(self, i, color):
        super().__init__()
        self._color = QColor(color)
        self.setFixedHeight(70)
        l = QHBoxLayout(self); l.setContentsMargins(12, 0, 12, 0)
        t = QLabel(f"#13 paint {i+1}"); t.setStyleSheet("color: #fff; font-size: 13px; font-weight: 600;"); l.addWidget(t)
    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 8, 8)

# Design token colors — 10 distinct ones, repeated twice
TOKENS = [
    "#e74c3c", "#e67e22", "#f39c12", "#27ae60", "#1abc9c",
    "#3498db", "#9b59b6", "#e91e63", "#00bcd4", "#ff5722",
]
METHODS = [
    ("#3 无选择器", make_style3),
    ("#3 无选择器", make_style3),
    ("#4 QPalette", make_style4),
    ("#4 QPalette", make_style4),
    ("#11 WA+QSS", make_style11),
    ("#11 WA+QSS", make_style11),
    ("#13 paintEvent", None),  # handled separately
    ("#13 paintEvent", None),
    ("#3 无选择器(浅)", make_style3),
    ("#3 无选择器(浅)", make_style3),
    ("#11 WA+QSS(浅)", make_style11),
    ("#11 WA+QSS(浅)", make_style11),
    ("#4 QPalette(浅)", make_style4),
    ("#4 QPalette(浅)", make_style4),
    ("#3 无选择器(暖)", make_style3),
    ("#3 无选择器(暖)", make_style3),
    ("#11 WA+QSS(暖)", make_style11),
    ("#11 WA+QSS(暖)", make_style11),
    ("#4 QPalette", make_style4),
    ("#4 QPalette", make_style4),
]

LIGHT_COLORS = [
    "#F9F6F0", "#F5F0E8", "#F0EBE0", "#EDE5D5", "#E8DFCC",
    "#F9F6F0", "#F5F0E8", "#F0EBE0", "#EDE5D5", "#E8DFCC",
]

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
        title = QLabel("测试 — 20张卡片 (已验证方法)")
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
        grid.setSpacing(8)

        color_idx = 0
        for row in range(10):
            rl = QHBoxLayout()
            rl.setSpacing(8)
            for col in range(2):
                idx = row * 2 + col
                method_name, method_fn = METHODS[idx]

                if "paintEvent" in method_name:
                    card = PaintCard(idx, TOKENS[idx % 10])
                else:
                    card = QWidget()
                    card.setFixedHeight(70)
                    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                    color = TOKENS[idx % 10]
                    if "浅" in method_name:
                        color = LIGHT_COLORS[idx % 10]
                    elif "暖" in method_name:
                        color = "#F2EFE9"  # warm paper
                    method_fn(card, idx, color)

                rl.addWidget(card, stretch=1)
            grid.addLayout(rl)
        grid.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

    def _refresh(self): pass
    def refresh_theme(self): pass
