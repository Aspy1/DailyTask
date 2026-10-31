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

from src.i18n.loader import tr
from src.ui.styles.theme import LAYOUT, SIZE_BODY_M, SIZE_CAPTION, font, get_colors
from src.ui.widgets.rounded_button import RoundedButton

# 导航分组：`(分组 id, 分组标题键, [(导航键, 文案键), …])` —— 顺序即界面顺序。
# 加一项只改这里；`tests/test_ui_wiring.py` 会检查每个键都能切到对应面板。
_SECTION_ITEMS = (
    ("func", "sidebar.section.func", (
        ("schedule", "sidebar.nav.schedule"),
        ("tasks", "sidebar.nav.tasks"),
        ("exams", "sidebar.nav.exams"),
    )),
    ("life", "sidebar.section.life", (
        ("daily", "sidebar.nav.daily"),
        ("routines", "sidebar.nav.routines"),
        ("study", "sidebar.nav.study"),
        ("expenses", "sidebar.nav.expenses"),
        ("inventory", "sidebar.nav.inventory"),
        ("meals", "sidebar.nav.meals"),
    )),
)


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
                color: {c['fg_secondary']}; font-size: {SIZE_CAPTION}px; font-weight: 600;
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
        # 底部那两项（设置 / 更多…，`indent=False`）**居中**，与「AI 助手」一致；
        # 主功能区仍左对齐（2026-10-18 用户口径）
        align = "left" if self._indent else "center"
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {c['fg_secondary']}; font-size: {fs}; font-weight: 500;
                text-align: {align}; padding: 7px 16px 7px {pl};
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
        self.setFixedWidth(LAYOUT["sidebar_width"])

        self._sections: dict[str, SidebarSection] = {}
        self._nav_items: dict[str, NavItem] = {}
        self._current_nav: str | None = None
        self._ai_on = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(0)

        self._title = QLabel(tr("app.name"))
        self._title.setFont(font(SIZE_BODY_M, QFont.Weight.Bold))
        layout.addWidget(self._title)

        self._build_sections(layout)
        self._sections["func"].set_expanded(True)
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
        for key, label in [("settings", tr("sidebar.nav.settings")), ("more", tr("sidebar.nav.more"))]:
            btn = NavItem(key, label, indent=False)
            btn.clicked_with_key.connect(self._on_nav_clicked)
            self._nav_items[key] = btn
            bl.addWidget(btn)
        layout.addWidget(self._bottom)

        self._ai_btn = RoundedButton(tr("ai.title"))
        self._ai_btn.setFlat(True)
        self._ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ai_btn.clicked.connect(self._toggle_ai)
        layout.addWidget(self._ai_btn)

        self.refresh_theme()

    def _build_sections(self, layout: QVBoxLayout) -> None:
        """建"功能 / 生活"两组导航（内容见 `_SECTION_ITEMS`），并接线。"""
        for section_id, header_key, items in _SECTION_ITEMS:
            section = SidebarSection(
                section_id, tr(header_key),
                [(key, tr(label_key)) for key, label_key in items])
            self._sections[section_id] = section
            layout.addWidget(section)
            for nav in section.nav_items().values():
                nav.clicked_with_key.connect(self._on_nav_clicked)
                self._nav_items[nav.nav_key] = nav

    def nav_item(self, key: str) -> NavItem | None:
        """按导航键取条目（用于把菜单锚在对应按钮下方）。"""
        return self._nav_items.get(key)

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
                color: {color}; font-size: {SIZE_CAPTION}px; {weight}
                text-align: center; padding: 8px 16px;
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
