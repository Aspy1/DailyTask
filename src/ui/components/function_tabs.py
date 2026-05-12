"""Column 1: Function tab icon bar — Pure Live NavigationRail style."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QSizePolicy
from PySide6.QtGui import QFont

from src.i18n.loader import tr

TAB_WIDTH = 52


class FunctionTabs(QWidget):
    tab_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fnTabs")
        self.setFixedWidth(TAB_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._tabs: list[QPushButton] = []
        self._current_tab: str = "study"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(2)

        tabs = [
            ("study", tr("tab.study")),
            ("life", tr("tab.life")),
            ("overview", tr("tab.overview")),
            ("settings", tr("tab.settings")),
            ("about", tr("tab.about")),
        ]

        for tab_id, label in tabs:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(tab_id == "study")
            btn.setFixedSize(TAB_WIDTH - 8, 42)
            btn.setFont(QFont(self.font().family(), 10))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 8px;
                    color: #9a9a9e;
                    padding: 4px 2px;
                    text-align: center;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: rgba(255,255,255,0.04);
                    color: #c0c0c4;
                }
                QPushButton:checked {
                    background-color: rgba(0,120,212,0.12);
                    color: #4daaf5;
                    font-weight: 600;
                }
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
