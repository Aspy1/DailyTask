"""Accordion sidebar — instant expand/collapse, no animation."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles.theme import FONT_CN, SIZE_BODY_M, get_colors


class SectionHeader(QPushButton):
    """Clickable group header. No arrow — just bold text."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """重新按当前主题上色（切主题时由 Sidebar 调用）。"""
        c = get_colors()
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {c['fg_secondary']}; font-size: 12px; font-weight: 600;
                text-align: left; padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {c['accent_bg']};
            }}
        """)


class NavItem(QPushButton):
    clicked_with_key = Signal(str)

    def __init__(self, key: str, text: str, indent: bool = True, parent=None) -> None:
        super().__init__(text, parent)
        self._key = key
        self._indent = indent
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda: self.clicked_with_key.emit(self._key))
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """重新按当前主题上色（切主题时由 Sidebar 调用）。"""
        c = get_colors()
        pl = "36px" if self._indent else "16px"
        fs = "13px" if self._indent else "12px"
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {c['fg_secondary']}; font-size: {fs}; font-weight: 500;
                text-align: left; padding: 7px 16px 7px {pl};
            }}
            QPushButton:hover {{
                background-color: {c['accent_bg']};
                color: {c['fg_primary']};
            }}
            QPushButton:checked {{
                background-color: {c['accent_bg']};
                color: {c['accent_text']};
                font-weight: 600;
            }}
        """)

    @property
    def nav_key(self) -> str:
        return self._key


class SidebarSection(QWidget):
    """Group: header + collapsible item list. No animation."""

    def __init__(self, section_id: str, header_text: str,
                 items: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self._section_id = section_id
        self._expanded = False
        self._nav_items: dict[str, NavItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = SectionHeader(header_text)
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        self._items_container = QWidget()
        self._items_container.setStyleSheet("background: transparent;")
        il = QVBoxLayout(self._items_container)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(1)

        for key, label in items:
            item = NavItem(key, label)
            il.addWidget(item)
            self._nav_items[key] = item

        layout.addWidget(self._items_container)
        self._items_container.hide()

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self._items_container.show()
        else:
            self._items_container.hide()

    def set_expanded(self, val: bool) -> None:
        """展开 / 收起该分区（即时切换，不做动画 —— 见 R-008）。"""
        self._expanded = val
        if val:
            self._items_container.show()
        else:
            self._items_container.hide()

    def nav_items(self) -> dict[str, NavItem]:
        return self._nav_items

    def refresh_theme(self) -> None:
        """切主题时重新给本分区的标题与条目上色。"""
        self._header.refresh_theme()
        for item in self._nav_items.values():
            item.refresh_theme()

    @property
    def expanded(self) -> bool:
        return self._expanded


class Sidebar(QWidget):
    """Left sidebar — instant accordion, no animation."""

    nav_changed = Signal(str)
    ai_toggled = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(184)

        self._sections: dict[str, SidebarSection] = {}
        self._nav_items: dict[str, NavItem] = {}
        self._current_nav: str | None = None
        self._ai_on = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(0)

        self._title = QLabel("生活助手")
        self._title.setFont(QFont(FONT_CN, SIZE_BODY_M, QFont.Weight.Bold))
        layout.addWidget(self._title)

        func_section = SidebarSection("func", "功能", [
            ("schedule", "日程总览"), ("courses", "课程表"),
            ("tasks", "作业管理"), ("exams", "考试")])
        life_section = SidebarSection("life", "生活", [
            ("daily", "日常"), ("expenses", "记账"),
            ("inventory", "有什么"), ("meals", "吃什么")])
        self._sections["func"] = func_section
        self._sections["life"] = life_section
        layout.addWidget(func_section)
        layout.addWidget(life_section)

        for sec in self._sections.values():
            for nav in sec.nav_items().values():
                nav.clicked_with_key.connect(self._on_nav_clicked)
                self._nav_items[nav.nav_key] = nav

        func_section.set_expanded(True)
        self.set_active("schedule")

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(spacer)

        self._bottom = QWidget()
        self._bottom.setObjectName("sidebarBottom")
        self._bottom.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bl = QVBoxLayout(self._bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        for key, label in [("settings", "设置"), ("about", "关于"), ("more", "更多…")]:
            btn = NavItem(key, label, indent=False)
            btn.clicked_with_key.connect(self._on_nav_clicked)
            self._nav_items[key] = btn
            bl.addWidget(btn)
        layout.addWidget(self._bottom)

        self._ai_btn = QPushButton("AI 助手")
        self._ai_btn.setFlat(True)
        self._ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ai_btn.clicked.connect(self._toggle_ai)
        layout.addWidget(self._ai_btn)

        self.refresh_theme()

    def refresh_theme(self) -> None:
        """按当前主题重上色（切主题时由 MainWindow 调用）。

        侧边栏/导航条/底部条的颜色是构造时写进各自样式表的，换主题不重刷就会
        留着上一个主题的颜色（2026-10-16 视觉审查）。
        """
        c = get_colors()
        self.setStyleSheet(
            f"#sidebar {{ background-color: {c['sidebar_bg']}; }}")
        self._title.setStyleSheet(f"""
            color: {c['fg_primary']}; background: transparent;
            padding: 0 16px 16px 16px;
        """)
        self._bottom.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                border-top: 1px solid {c['border_strong']};
                padding-top: 4px;
            }}
        """)
        self._ai_btn.setStyleSheet(self._ai_btn_qss(c))
        for sec in self._sections.values():
            sec.refresh_theme()

    def _ai_btn_qss(self, c: dict) -> str:
        """AI 按钮样式（选中态用强调色文字，未选中用次要文字）。"""
        color = c['accent_text'] if self._ai_on else c['fg_secondary']
        weight = "font-weight: 600;" if self._ai_on else ""
        return f"""
            QPushButton {{
                background: transparent; border: none;
                color: {color}; font-size: 12px; {weight}
                text-align: left; padding: 8px 16px;
            }}
            QPushButton:hover {{ color: {c['accent_text']}; }}
        """

    def _on_nav_clicked(self, key: str) -> None:
        self.set_active(key)
        self.nav_changed.emit(key)

    def set_active(self, key: str) -> None:
        if self._current_nav == key:
            return
        self._current_nav = key
        for nav in self._nav_items.values():
            nav.setChecked(nav.nav_key == key)
        for sec_id, sec in self._sections.items():
            if key in sec.nav_items() and not sec.expanded:
                self._expand_section_accordion(sec_id)

    def _expand_section_accordion(self, target_id: str) -> None:
        for sec_id, sec in self._sections.items():
            if sec_id != target_id and sec.expanded:
                sec.set_expanded(False)
        self._sections[target_id].set_expanded(True)

    def _toggle_ai(self) -> None:
        self._ai_on = not self._ai_on
        self._ai_btn.setStyleSheet(self._ai_btn_qss(get_colors()))
        self.ai_toggled.emit(self._ai_on)
