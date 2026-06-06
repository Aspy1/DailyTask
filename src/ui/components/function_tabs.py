"""Sidebar navigation — function tab bar."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QSizePolicy
from PySide6.QtGui import QFont

from src.i18n.loader import tr
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_BODY_S

TAB_WIDTH = 56


class FunctionTabs(QWidget):
    tab_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        c = get_colors()
        self.setObjectName("fnTabs")
        self.setFixedWidth(TAB_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._tabs: list[QPushButton] = []
        self._current_tab: str = "study"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(4)

        tabs = [
            ("study", tr("tab.study")),
            ("life", tr("tab.life")),
            ("overview", tr("tab.overview")),
            ("settings", tr("tab.settings")),
            ("about", tr("tab.about")),
        ]

        btn_w = TAB_WIDTH - 16
        for tab_id, label in tabs:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(tab_id == "study")
            btn.setFixedSize(btn_w, 44)
            btn.setFont(QFont(FONT_CN, SIZE_BODY_S))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    border-radius: 8px;
                    color: {c['fg_hint']};
                    padding: 8px 4px;
                    text-align: center;
                    font-size: {SIZE_BODY_S}px;
                }}
                QPushButton:hover {{
                    background-color: {c['btn_secondary_bg']};
                    color: {c['fg_secondary']};
                }}
                QPushButton:checked {{
                    background-color: {c['accent_bg']};
                    color: {c['accent']};
                    font-weight: 500;
                }}
            """)
            btn.clicked.connect(lambda checked, tid=tab_id: self._on_tab_clicked(tid))
            self._tabs.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

    def _on_tab_clicked(self, tab_id: str) -> None:
        if tab_id == self._current_tab:
            return
        self._current_tab = tab_id
        tab_ids = ["study", "life", "overview", "settings", "about"]
        for i, _ in enumerate(self._tabs):
            self._tabs[i].setChecked(i == tab_ids.index(tab_id) if tab_id in tab_ids else False)
        self.tab_changed.emit(tab_id)
