"""Column 2: Context sidebar — clickable navigation items."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QLabel, QListWidget
from PySide6.QtGui import QFont

from src.i18n.loader import tr
from src.ui.styles.theme import get_colors


class ContextSidebar(QWidget):
    nav_item_clicked = Signal(str, str)  # tab_id, item_key

    _items = {
        "study": ["sidebar.courses", "sidebar.tasks"],  # tasks i18n key now shows "作业清单"
        "life": ["sidebar.habits", "sidebar.expenses"],
        "overview": ["sidebar.calendar"],
        "settings": [],
        "about": [],
    }

    _item_keys = {
        "sidebar.courses": "courses",
        "sidebar.tasks": "tasks",
        "sidebar.habits": "habits",
        "sidebar.expenses": "expenses",
        "sidebar.calendar": "calendar",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ctxSidebar")
        self.setMinimumWidth(180)
        self.setMaximumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self._nav_lists: dict[str, QListWidget] = {}

        for tab_id in ["study", "life", "overview", "settings", "about"]:
            self._stack.addWidget(self._create_page(tab_id))

    def _create_page(self, tab_id: str) -> QWidget:
        c = get_colors()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(6)

        heading = QLabel(tr(f"tab.{tab_id}"))
        heading.setFont(QFont(self.font().family(), 11))
        heading.setStyleSheet(f"""
            color: {c['section_heading']}; font-weight: 600;
            padding: 0 4px 4px 4px;
        """)
        layout.addWidget(heading)

        nav = QListWidget()
        nav.setSpacing(2)

        for key in self._items.get(tab_id, []):
            nav.addItem(tr(key))

        if nav.count() > 0:
            nav.setCurrentRow(0)

        nav.currentRowChanged.connect(
            lambda row, tid=tab_id, n=nav: self._on_nav_clicked(tid, n, row)
        )
        self._nav_lists[tab_id] = nav

        layout.addWidget(nav)
        return page

    def _on_nav_clicked(self, tab_id: str, nav: QListWidget, row: int) -> None:
        if row < 0:
            return
        item_text = nav.item(row).text()
        for key in self._items.get(tab_id, []):
            if tr(key) == item_text:
                item_key = self._item_keys.get(key, key)
                self.nav_item_clicked.emit(tab_id, item_key)
                return

    def switch_to(self, tab_id: str) -> None:
        mapping = {"study": 0, "life": 1, "overview": 2, "settings": 3, "about": 4}
        idx = mapping.get(tab_id, 0)
        self._stack.setCurrentIndex(idx)
