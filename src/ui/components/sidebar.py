"""Accordion sidebar navigation — warm-paper design system."""

from PySide6.QtCore import (
    Qt, Signal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
    QTimer
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QGraphicsOpacityEffect, QApplication,
)
from PySide6.QtGui import QFont, QPainter, QTransform

from src.ui.styles.theme import get_colors, FONT_CN


# ─── Section header with animated arrow ───────────────────────

class _ArrowIcon(QLabel):
    """A small ▶/▼ label that rotates via QTransform instead of CSS."""

    def __init__(self, parent=None):
        super().__init__("▶", parent)
        self._angle = 0.0
        self.setFixedSize(14, 14)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_angle(self, degrees: float):
        self._angle = degrees
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QTransform, QFont
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(self.palette().color(self.foregroundRole()))
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        # rotate around center
        cx = self.width() / 2
        cy = self.height() / 2
        p.translate(cx, cy)
        p.rotate(self._angle)
        p.translate(-cx, -cy)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "▶")
        p.end()


class SectionHeader(QPushButton):
    """Clickable group header that expands / collapses its child items."""

    collapsed = Signal()

    def __init__(self, text: str, parent=None):
        c = get_colors()
        super().__init__(text, parent)
        self.setCheckable(False)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._arrow = _ArrowIcon(self)
        self._expanded = False

        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {c['fg_secondary']}; font-size: 12px; font-weight: 600;
                text-align: left; padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: {c['accent_bg']};
            }}
        """)
        self._arrow.setStyleSheet(f"color: {c['fg_hint']}; background: transparent;")

        self.clicked.connect(self._toggle)

    def _toggle(self):
        self._expanded = not self._expanded
        self._animate_arrow()
        if not self._expanded:
            self.collapsed.emit()

    def _animate_arrow(self):
        target = 90.0 if self._expanded else 0.0
        anim = QPropertyAnimation(self._arrow, b"_angle_dummy")
        start_val = self._arrow._angle
        end_val = target

        # Use a simple easing timer since QPropertyAnimation can't animate plain float
        duration = 250
        steps = 15
        step_ms = duration // steps
        delta = (end_val - start_val) / steps

        def step(i=0):
            if i >= steps:
                self._arrow.set_angle(end_val)
                # Swap text at midpoint for clarity
                self._arrow.setText("▼" if self._expanded else "▶")
                if self._expanded:
                    self._arrow.set_angle(0)  # reset after showing ▼
                return
            self._arrow.set_angle(start_val + delta * (i + 1))
            QTimer.singleShot(step_ms, lambda s=i+1: step(s))

        step(0)

    def animate_to_angle(self, target: float, on_finish=None):
        """Public API for external animation control."""
        duration = 250
        steps = 15
        step_ms = duration // steps
        start = self._arrow._angle
        delta = (target - start) / steps

        def step(i=0):
            if i >= steps:
                self._arrow.set_angle(target)
                if target == 90.0:
                    self._arrow.setText("▼")
                    self._arrow.set_angle(0)
                elif target == 0.0:
                    self._arrow.setText("▶")
                if on_finish:
                    on_finish()
                return
            self._arrow.set_angle(start + delta * (i + 1))
            QTimer.singleShot(step_ms, lambda s=i+1: step(s))

        step(0)

    @property
    def expanded(self) -> bool:
        return self._expanded

    @expanded.setter
    def expanded(self, val: bool):
        self._expanded = val
        self._arrow.setText("▼" if val else "▶")
        self._arrow.set_angle(0)


# ─── Nav item ────────────────────────────────────────────────

class NavItem(QPushButton):
    """Single navigation row in the sidebar."""

    clicked_with_key = Signal(str)

    def __init__(self, key: str, text: str, indent: bool = True, parent=None):
        c = get_colors()
        super().__init__(text, parent)
        self._key = key
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        pl = "36px" if indent else "16px"
        fs = "12px" if indent else "11px"
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {c['fg_secondary']}; font-size: {fs}; font-weight: 500;
                text-align: left; padding: 6px 16px 6px {pl};
            }}
            QPushButton:hover {{
                background-color: {c['accent_bg']};
                color: {c['fg_primary']};
            }}
            QPushButton:checked {{
                background-color: {c['accent_bg']};
                color: {c['accent']};
                font-weight: 600;
            }}
        """)
        self.clicked.connect(lambda: self.clicked_with_key.emit(self._key))

    @property
    def nav_key(self) -> str:
        return self._key


# ─── Collapsible section ─────────────────────────────────────

class SidebarSection(QWidget):
    """A group: header + collapsible item list with height animation."""

    sectionToggled = Signal(str, bool)  # section_id, expanded

    def __init__(self, section_id: str, header_text: str, items: list[tuple[str, str]],
                 parent=None):
        """
        section_id: internal key (e.g. 'func', 'life')
        header_text: display text (e.g. '功能', '生活')
        items: list of (key, label) tuples
        """
        c = get_colors()
        super().__init__(parent)
        self._section_id = section_id
        self._expanded = False
        self._nav_items: dict[str, NavItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = SectionHeader(header_text)
        layout.addWidget(self._header)

        # Container for nav items — we animate its maximumHeight
        self._items_container = QWidget()
        self._items_container.setStyleSheet("background: transparent;")
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(0)

        for key, label in items:
            item = NavItem(key, label)
            self._items_layout.addWidget(item)
            self._nav_items[key] = item

        layout.addWidget(self._items_container)

        self._items_container.setMaximumHeight(0)
        self._items_container.setVisible(False)

        self._header.clicked.connect(self._on_header_click)

    def _on_header_click(self):
        was_expanded = self._expanded
        self._expanded = not self._expanded
        self._animate_height()

        if not self._expanded:
            # Let parent Sidebar handle accordion via signal
            self.sectionToggled.emit(self._section_id, self._expanded)

    def set_expanded(self, val: bool, animated: bool = True):
        if self._expanded == val:
            return
        self._expanded = val
        self._header.expanded = val
        if animated:
            self._animate_height()
        else:
            self._apply_height()

    def _animate_height(self):
        if self._expanded:
            self._items_container.setVisible(True)
            # Measure content height
            h = self._items_container.sizeHint().height()
            self._anim = QPropertyAnimation(self._items_container, b"maximumHeight")
            self._anim.setDuration(250)
            self._anim.setStartValue(0)
            self._anim.setEndValue(h)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.start()
        else:
            # Wait for accordion close signal before collapsing container
            self._collapse()

    def _collapse(self):
        h = self._items_container.height()
        self._anim = QPropertyAnimation(self._items_container, b"maximumHeight")
        self._anim.setDuration(250)
        self._anim.setStartValue(h)
        self._anim.setEndValue(0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(lambda: self._items_container.setVisible(False))
        self._anim.start()

    def _apply_height(self):
        if self._expanded:
            self._items_container.setVisible(True)
            h = self._items_container.sizeHint().height()
            self._items_container.setMaximumHeight(h)
        else:
            self._items_container.setMaximumHeight(0)
            self._items_container.setVisible(False)

    def nav_items(self) -> dict[str, NavItem]:
        return self._nav_items

    @property
    def expanded(self) -> bool:
        return self._expanded


# ─── Sidebar ─────────────────────────────────────────────────

class Sidebar(QWidget):
    """Full sidebar with accordion sections, bottom items, and AI toggle."""

    nav_changed = Signal(str)       # key of selected nav item
    ai_toggled = Signal(bool)

    def __init__(self, parent=None):
        c = get_colors()
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(180)
        self.setStyleSheet(f"""
            #sidebar {{
                background-color: {c['bg_surface']};
            }}
        """)

        self._sections: dict[str, SidebarSection] = {}
        self._nav_items: dict[str, NavItem] = {}
        self._current_nav: str | None = None
        self._ai_on = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(0)

        # ── Title ──
        title = QLabel("生活助手")
        title.setFont(QFont(FONT_CN, 15, QFont.Weight.Bold))
        title.setStyleSheet(f"""
            color: {c['fg_primary']}; background: transparent;
            padding: 0 16px; margin-bottom: 16px; letter-spacing: 0.5px;
        """)
        layout.addWidget(title)

        # ── Sections ──
        func_section = SidebarSection(
            "func", "功能",
            [("schedule", "日程总览"), ("courses", "课程表"), ("tasks", "作业管理")]
        )
        life_section = SidebarSection(
            "life", "生活",
            [("daily", "日常"), ("expenses", "记账"),
             ("inventory", "有什么"), ("meals", "吃什么")]
        )
        self._sections["func"] = func_section
        self._sections["life"] = life_section
        layout.addWidget(func_section)
        layout.addWidget(life_section)

        # Wire nav items
        for sec in self._sections.values():
            for nav in sec.nav_items().values():
                nav.clicked_with_key.connect(self._on_nav_clicked)
                self._nav_items[nav.nav_key] = nav
            sec.sectionToggled.connect(self._on_section_toggled)

        # Default: expand "功能", select "日程总览"
        func_section.set_expanded(True, animated=False)
        self.set_active("schedule")

        # ── Spacer ──
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(spacer)

        # ── Bottom ──
        bottom = QWidget()
        bottom.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                border-top: 1px solid {c['border_strong']};
                padding-top: 8px;
            }}
        """)
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        settings_btn = NavItem("settings", "设置", indent=False)
        about_btn = NavItem("about", "关于", indent=False)
        settings_btn.clicked_with_key.connect(self._on_nav_clicked)
        about_btn.clicked_with_key.connect(self._on_nav_clicked)
        self._nav_items["settings"] = settings_btn
        self._nav_items["about"] = about_btn
        bl.addWidget(settings_btn)
        bl.addWidget(about_btn)
        layout.addWidget(bottom)

        # ── AI Toggle ──
        ai_toggle = QPushButton("AI 助手")
        ai_toggle.setFlat(True)
        ai_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {c['fg_hint']}; font-size: 11px;
                text-align: left; padding: 6px 16px;
            }}
            QPushButton:hover {{ color: {c['accent']}; }}
        """)
        ai_toggle.clicked.connect(self._toggle_ai)
        self._ai_toggle_btn = ai_toggle
        layout.addWidget(ai_toggle)

    def _on_nav_clicked(self, key: str):
        self.set_active(key)
        self.nav_changed.emit(key)

    def _on_section_toggled(self, section_id: str, expanding: bool):
        """Accordion: close other sections."""
        if expanding:
            return  # already handled by section itself
        # When one closes, we don't auto-open another — accordion allows all-closed
        pass

    def set_active(self, key: str):
        if self._current_nav == key:
            return
        self._current_nav = key
        for nav in self._nav_items.values():
            nav.setChecked(nav.nav_key == key)

        # Auto-expand the section containing the selected item
        for sec_id, sec in self._sections.items():
            if key in sec.nav_items():
                if not sec.expanded:
                    self._expand_section_accordion(sec_id)

    def _expand_section_accordion(self, target_id: str):
        """Expand target; collapse others."""
        # Collapse others first
        for sec_id, sec in self._sections.items():
            if sec_id != target_id and sec.expanded:
                sec.set_expanded(False)
        # Expand target
        self._sections[target_id].set_expanded(True)

    def _toggle_ai(self):
        c = get_colors()
        self._ai_on = not self._ai_on
        if self._ai_on:
            self._ai_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {c['accent']}; font-size: 11px; font-weight: 600;
                    text-align: left; padding: 6px 16px;
                }}
                QPushButton:hover {{ color: {c['accent_hover']}; }}
            """)
        else:
            self._ai_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {c['fg_hint']}; font-size: 11px;
                    text-align: left; padding: 6px 16px;
                }}
                QPushButton:hover {{ color: {c['accent']}; }}
            """)
        self.ai_toggled.emit(self._ai_on)

    def refresh_theme(self):
        """Re-apply styles after theme change."""
        pass  # Styles are applied in __init__ via get_colors()
