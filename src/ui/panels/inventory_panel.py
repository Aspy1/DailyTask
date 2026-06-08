"""Inventory panel — test: 20 colored cards in 2-column grid."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE

# Test colors
COLORS = ["#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#1abc9c",
          "#3498db", "#9b59b6", "#e91e63", "#00bcd4", "#ff5722",
          "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#1abc9c",
          "#3498db", "#9b59b6", "#e91e63", "#00bcd4", "#ff5722"]


class _TestCard(QWidget):
    def __init__(self, index, color, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"_TestCard {{ background-color: {color}; border-radius: 8px; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        lbl = QLabel(f"卡片 #{index+1}")
        lbl.setStyleSheet("color: #fff; font-size: 14px; font-weight: 600; border: none; background: transparent;")
        layout.addWidget(lbl)


class InventoryPanel(QWidget):
    def __init__(self, dm: DataManager, parent=None):
        super().__init__(parent)
        self._dm = dm
        c = get_colors()
        self.setStyleSheet(f"InventoryPanel {{ background-color: {c['bg_root']}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bar.setObjectName("taskBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        title = QLabel("有什么 (测试)")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bl.addWidget(title)
        bl.addStretch()
        layout.addWidget(bar)

        # Scrollable 2-column grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background-color: {c['bg_root']}; border: none; }}")

        container = QWidget()
        container.setStyleSheet(f"background-color: {c['bg_root']};")
        grid = QVBoxLayout(container)
        grid.setContentsMargins(16, 8, 16, 16)
        grid.setSpacing(8)

        # 10 rows, 2 columns
        for row in range(10):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)
            for col in range(2):
                idx = row * 2 + col
                card = _TestCard(idx, COLORS[idx])
                row_layout.addWidget(card, stretch=1)
            grid.addLayout(row_layout)

        grid.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

    def _refresh(self):
        pass

    def refresh_theme(self):
        pass
