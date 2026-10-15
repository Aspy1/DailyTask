"""Design system — Warm Paper Study palette (light-first).

Tokens 的**单一真值**是同目录的 tokens.json（见 CODE_STANDARDS Q-H8）。
改色值/字号请改 tokens.json，本文件只负责加载并生成 QSS。
"""

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# ── Tokens：从单一真值 tokens.json 加载（CODE_STANDARDS Q-H8）──
_TOKENS_DATA = json.loads((Path(__file__).parent / "tokens.json").read_text(encoding="utf-8"))

FONT_CN = _TOKENS_DATA["font"]["cn"]
FONT_MONO = _TOKENS_DATA["font"]["mono"]

# ── Type scale ─────────────────────────────────────────
SIZE_TINY = _TOKENS_DATA["sizes"]["SIZE_TINY"]
SIZE_CAPTION = _TOKENS_DATA["sizes"]["SIZE_CAPTION"]
SIZE_BODY_S = _TOKENS_DATA["sizes"]["SIZE_BODY_S"]
SIZE_BODY = _TOKENS_DATA["sizes"]["SIZE_BODY"]
SIZE_BODY_M = _TOKENS_DATA["sizes"]["SIZE_BODY_M"]
SIZE_BODY_L = _TOKENS_DATA["sizes"]["SIZE_BODY_L"]
SIZE_ICON = _TOKENS_DATA["sizes"]["SIZE_ICON"]
SIZE_SUBTITLE = _TOKENS_DATA["sizes"]["SIZE_SUBTITLE"]
SIZE_TITLE = _TOKENS_DATA["sizes"]["SIZE_TITLE"]
SIZE_HEADING = _TOKENS_DATA["sizes"]["SIZE_HEADING"]
SIZE_FAB = _TOKENS_DATA["sizes"]["SIZE_FAB"]

# ── 圆角刻度（radius_sm/md/lg/pill）──────────────
RADIUS: dict = _TOKENS_DATA["radius"]

# ── Design tokens（colors：light / dark）───────────────
TOKENS: dict = _TOKENS_DATA["colors"]

_current_mode: str = "light"
_color_cache: dict | None = None


def get_mode() -> str:
    return _current_mode


def get_colors() -> dict:
    global _color_cache
    if _color_cache is None:
        _color_cache = TOKENS.get(_current_mode, TOKENS["light"])
    return _color_cache


def elide_text(text: str, font: QFont, max_width: int) -> str:
    """Ellipsize text to fit within max_width pixels.

    Usage:
        from src.ui.styles.theme import elide_text
        label.setText(elide_text(long_text, label.font(), 200))
    """
    from PySide6.QtGui import QFontMetrics
    metrics = QFontMetrics(font)
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max_width)


def switch_theme(mode: str) -> str:
    global _current_mode, _color_cache
    _current_mode = mode
    _color_cache = None
    app = QApplication.instance()
    if app is not None:
        apply_palette(app, mode)
    return build_theme(mode)


def _resolve_font() -> str:
    families = QFontDatabase.families()
    for name in ("Microsoft YaHei", "PingFang SC", "SimHei", "Noto Sans CJK SC"):
        if name in families:
            return name
    return "Microsoft YaHei"


def apply_palette(app: QApplication, mode: str) -> None:
    """把主题色写进 QPalette。

    ⚠ 只设 QSS 是不够的：**没有显式样式表的控件**（QScrollArea 的 viewport、
    QTableWidget 的交替行 AlternateBase、原生弹出菜单、工具提示等）会继续用
    平台默认调色板 —— 暗色模式下就是一块块浅灰（2026-10-16 视觉审查的
    主要问题）。QSS 负责"长相"，QPalette 负责"底座"。
    """
    from PySide6.QtGui import QColor, QPalette
    t = TOKENS.get(mode, TOKENS["light"])
    pal = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    pal.setColor(role.Window, QColor(t["bg_root"]))
    pal.setColor(role.WindowText, QColor(t["fg_primary"]))
    pal.setColor(role.Base, QColor(t["bg_card"]))
    pal.setColor(role.AlternateBase, QColor(t["table_alt"]))
    pal.setColor(role.Text, QColor(t["fg_primary"]))
    pal.setColor(role.PlaceholderText, QColor(t["fg_hint"]))
    pal.setColor(role.Button, QColor(t["bg_surface"]))
    pal.setColor(role.ButtonText, QColor(t["fg_primary"]))
    pal.setColor(role.BrightText, QColor(t["fg_on_fill"]))
    pal.setColor(role.Highlight, QColor(t["accent"]))
    pal.setColor(role.HighlightedText, QColor(t["fg_on_fill"]))
    pal.setColor(role.ToolTipBase, QColor(t["bg_elevated"]))
    pal.setColor(role.ToolTipText, QColor(t["fg_primary"]))
    pal.setColor(role.Link, QColor(t["accent_text"]))
    for r in (role.WindowText, role.Text, role.ButtonText):
        pal.setColor(group.Disabled, r, QColor(t["fg_disabled"]))
    app.setPalette(pal)


def init_theme(app: QApplication, mode: str = "light") -> str:
    global FONT_CN, _current_mode, _color_cache
    FONT_CN = _resolve_font()
    _current_mode = mode
    _color_cache = None
    font = QFont(FONT_CN, SIZE_BODY)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)

    # Suppress focus rect dotted border on buttons
    from PySide6.QtWidgets import QProxyStyle, QStyle
    class _NoFocusStyle(QProxyStyle):
        def drawPrimitive(self, element, option, painter, widget) -> None:
            if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
                return
            super().drawPrimitive(element, option, painter, widget)
    app.setStyle(_NoFocusStyle(app.style()))
    apply_palette(app, mode)

    return build_theme(mode)


def build_theme(mode: str) -> str:
    t = TOKENS.get(mode, TOKENS["light"])
    return f"""
* {{ font-family: "{FONT_CN}", "Microsoft YaHei", sans-serif; }}

/* ── Base ────────────────────────────────── */


QFrame[frameShape="4"] {{ border: none; background: transparent; color: transparent; }} /* HLine dividers */

QMainWindow {{ background-color: {t["bg_root"]}; }}

/* ── Top nav bar ─────────────────────────── */
#topNav {{ background-color: {t["nav_bg"]}; border-bottom: 1px solid {t["border"]}; }}
#topNav QPushButton {{
    background-color: transparent; color: {t["fg_secondary"]}; border: none;
    border-radius: 8px; padding: 6px 16px; font-size: {SIZE_BODY}px;
    min-height: 32px;
}}
#topNav QPushButton:hover {{
    background-color: {t["accent_bg"]}; color: {t["fg_primary"]};
}}
#topNav QPushButton:checked {{
    background-color: {t["nav_selected_bg"]}; color: {t["nav_selected_fg"]}; font-weight: 500;
}}

/* ── Menus ───────────────────────────────── */
QMenuBar {{ background-color: {t["bg_surface"]}; color: {t["fg_primary"]}; border-bottom: 1px solid {t["border"]}; padding: 2px 0; font-size: {SIZE_BODY_S}px; }}
QMenuBar::item:selected {{ background-color: {t["bg_elevated"]}; border-radius: 4px; }}
QMenu {{ background-color: {t["bg_elevated"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_strong"]}; padding: 4px; }}
QMenu::item {{ padding: 6px 32px 6px 12px; }}
QMenu::item:selected {{ background-color: {t["accent_bg"]}; color: {t["fg_primary"]}; }}
QMenu::separator {{ height: 1px; background-color: {t["divider"]}; margin: 4px 8px; }}

/* ── Buttons ─────────────────────────────── */
QPushButton {{ background-color: transparent; border: none; color: {t["fg_primary"]}; padding: 8px 16px; border-radius: {RADIUS["radius_md"]}px; font-size: {SIZE_BODY}px; }}
QPushButton:hover {{ background-color: {t["bg_hover"]}; }}

/* ── Labels ──────────────────────────────── */
QLabel {{ color: {t["fg_primary"]}; background: transparent; }}

/* ── List ────────────────────────────────── */
QListWidget {{ background-color: transparent; color: {t["fg_primary"]}; border: none; outline: none; font-size: {SIZE_BODY_S}px; }}
QListWidget::item {{ padding: 8px 12px; border-radius: 4px; }}
QListWidget::item:selected {{ background-color: {t["accent_bg"]}; }}
QListWidget::item:hover {{ background-color: {t["bg_hover"]}; }}

/* ── Inputs ──────────────────────────────── */
QTextEdit, QPlainTextEdit {{ background-color: {t["input_bg"]}; color: {t["fg_primary"]}; border: 1px solid {t["border"]}; border-radius: 4px; padding: 8px 12px; font-size: {SIZE_BODY}px; selection-background-color: {t["accent_bg"]}; }}
QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {t["accent"]}; }}
QLineEdit {{ background-color: {t["input_bg"]}; color: {t["fg_primary"]}; border: 1px solid {t["border"]}; border-radius: 4px; padding: 8px 12px; font-size: {SIZE_BODY}px; }}
QLineEdit:focus {{ border-color: {t["accent"]}; }}

/* ── Scroll bars ─────────────────────────── */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 0; }}
QScrollBar::handle:vertical {{ background-color: {t["fg_disabled"]}; min-height: 36px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background-color: {t["fg_hint"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0 4px; }}
QScrollBar::handle:horizontal {{ background-color: {t["fg_disabled"]}; min-width: 36px; border-radius: 4px; }}
QScrollBar::handle:horizontal:hover {{ background-color: {t["fg_hint"]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Splitter ────────────────────────────── */
QSplitter::handle {{ background-color: {t["bg_surface"]}; }}
QSplitter::handle:horizontal {{ width: 1px; }}

/* ── Status bar ──────────────────────────── */
QStatusBar {{ background-color: {t["status_bar_bg"]}; color: {t["fg_primary"]}; font-size: {SIZE_BODY_S}px; padding: 4px 16px; border-top: 1px solid {t["border_strong"]}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {t["fg_secondary"]}; padding: 0; }}

/* ── Checkbox ────────────────────────────── */
QCheckBox {{ color: {t["fg_primary"]}; spacing: 8px; font-size: {SIZE_BODY}px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 2px solid {t["fg_hint"]}; border-radius: 4px; background: transparent; }}
QCheckBox::indicator:checked {{ background-color: {t["accent"]}; border-color: {t["accent"]}; }}

/* ── Combo box ───────────────────────────── */
QComboBox {{ background-color: {t["input_bg"]}; color: {t["fg_primary"]}; border: 1px solid {t["border"]}; border-radius: 4px; padding: 8px 12px; font-size: {SIZE_BODY}px; }}
QComboBox:hover {{ border-color: {t["border_strong"]}; }}
QComboBox:focus {{ border-color: {t["accent"]}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background-color: {t["bg_elevated"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_strong"]}; selection-background-color: {t["accent_bg"]}; outline: none; }}

/* ── Scroll area ─────────────────────────── */
/* viewport 与其内容控件默认会用调色板 Base 上色 → 暗色下变亮灰块，必须显式透明 */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QAbstractScrollArea::corner {{ background: transparent; }}

/* ── Table ───────────────────────────────── */
QTableWidget {{ background-color: {t["bg_root"]}; alternate-background-color: {t["table_alt"]}; color: {t["fg_primary"]}; gridline-color: {t["divider"]}; border: none; font-size: {SIZE_BODY_S}px; }}
QHeaderView::section {{ background-color: {t["bg_surface"]}; color: {t["fg_secondary"]}; border: none; border-bottom: 1px solid {t["border"]}; padding: 8px 12px; font-weight: 600; font-size: {SIZE_BODY_S}px; }}
QToolTip {{ background-color: {t["bg_elevated"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_strong"]}; border-radius: 8px; padding: 6px 10px; font-size: {SIZE_CAPTION}px; }}

/* ── Named widgets ───────────────────────── */
#fnTabs, #aiPanel, #courseBar, #courseFooter, #taskBar, #taskFooter {{ background-color: transparent; }}
#courseBar, #taskBar {{ background-color: {t["bg_surface"]}; border-bottom: 1px solid {t["divider"]}; }}
#courseFooter, #taskFooter {{ border-top: 1px solid {t["divider"]}; }}
#aiChat {{ background-color: {t["chat_bg"]}; border: none; }}
#aiHeader {{ background-color: {t["sidebar_bg"]}; border-bottom: 1px solid {t["border"]}; }}
#aiInputContainer {{ background-color: {t["sidebar_bg"]}; border-top: 1px solid {t["border"]}; }}
#courseCount, #taskCount {{ color: {t["fg_hint"]}; font-size: {SIZE_TINY}px; border: none; }}
#taskTable {{ background-color: {t["bg_root"]}; color: {t["fg_primary"]}; border: none; font-size: 12px; }}
#taskTable::item {{ padding: 8px 12px; min-height: 32px; border-bottom: 1px solid {t["divider"]}; }}
#taskTable::item:alternate {{ background-color: {t["table_alt"]}; }}
"""


# ── Public style helpers (see DESIGN_TOKENS.md §5-7) ──────────────

def btn_primary_qss() -> str:
    """主按钮样式 - accent 填充 + 白色文字"""
    c = get_colors()
    return f"""
        QPushButton {{
            background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
            border-radius: 8px; padding: 8px 12px; font-size: {SIZE_BODY_S}px; font-weight: 500;
        }}
        QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton:pressed {{ background-color: {c['accent_dim']}; }}
        QPushButton:disabled {{ background-color: {c['fg_disabled']}; color: {c['fg_on_fill']}; }}
    """


def btn_secondary_qss() -> str:
    """次按钮样式 - 透明背景 + 边框"""
    c = get_colors()
    return f"""
        QPushButton {{
            background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
            border: 1px solid {c['border_strong']}; border-radius: 8px;
            padding: 8px 12px; font-size: {SIZE_BODY_S}px;
        }}
        QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        QPushButton:pressed {{ background-color: {c['btn_pressed_bg']}; }}
        QPushButton:disabled {{ color: {c['fg_disabled']}; border-color: {c['divider']}; }}
    """


def btn_ghost_qss() -> str:
    """文字按钮样式 - 完全透明 + accent 文字"""
    c = get_colors()
    return f"""
        QPushButton {{
            background: transparent; color: {c['accent_text']}; border: none;
            border-radius: 8px; padding: 8px 12px; font-size: {SIZE_BODY_S}px;
        }}
        QPushButton:hover {{ color: {c['accent_hover']}; }}
        QPushButton:pressed {{ color: {c['accent_dim']}; }}
        QPushButton:disabled {{ color: {c['fg_disabled']}; }}
    """


def menu_qss() -> str:
    """下拉菜单样式"""
    c = get_colors()
    return f"""
        QMenu {{
            background-color: {c['bg_elevated']};
            border: 1px solid {c['border_strong']};
            border-radius: 8px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 8px 12px;
            border-radius: 4px;
            color: {c['fg_primary']};
        }}
        QMenu::item:selected {{
            background-color: {c['accent_bg']};
        }}
        QMenu::item:disabled {{
            color: {c['fg_disabled']};
        }}
        QMenu::separator {{
            height: 1px;
            background-color: {c['divider']};
            margin: 4px 8px;
        }}
    """


def create_context_menu(parent=None) -> object:
    """创建右键菜单（自动应用样式和去阴影）
    
    使用方式：
        from src.ui.styles.theme import create_context_menu
        
        menu = create_context_menu(self)
        menu.add_item("编辑", self._edit)
        menu.add_item("删除", self._delete)
        menu.exec()
    
    关键点：
        1. 使用自定义 QWidget 实现，完全避免 Windows 原生阴影
        2. 自动显示在鼠标当前位置
        3. 点击外部自动关闭
    """
    from src.ui.widgets.context_menu import ContextMenu
    
    return ContextMenu(parent)


def dialog_qss() -> str:
    """对话框样式"""
    c = get_colors()
    return f"""
        QDialog {{
            background-color: {c['bg_elevated']};
        }}
        QLabel {{
            color: {c['fg_primary']};
            font-size: {SIZE_BODY_S}px;
            background: transparent;
        }}
        QLineEdit {{
            background-color: {c['bg_input']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 8px 12px;
            font-size: {SIZE_BODY_S}px;
            color: {c['fg_primary']};
        }}
        QLineEdit:focus {{
            border: 1px solid {c['accent']};
        }}
        QListWidget {{
            background-color: {c['bg_input']};
            border: 1px solid {c['border']};
            border-radius: 8px;
            font-size: {SIZE_BODY_S}px;
            color: {c['fg_primary']};
        }}
        QListWidget::item {{
            padding: 8px 12px;
            border-radius: 4px;
        }}
        QListWidget::item:selected {{
            background-color: {c['accent_bg']};
        }}
    """


def fab_qss() -> str:
    """浮动操作按钮样式 - 完全圆形"""
    c = get_colors()
    return f"""
        QPushButton {{
            background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
            border-radius: {RADIUS['radius_pill']}px; font-size: {SIZE_FAB}px; font-weight: 600;
        }}
        QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton:pressed {{ background-color: {c['accent_dim']}; }}
    """


def toggle_switch_qss() -> str:
    """Toggle switch 样式 - 圆角框 + 圆形滑块"""
    c = get_colors()
    return f"""
        QCheckBox {{ spacing: 8px; font-size: {SIZE_BODY_S}px; color: {c['fg_primary']}; }}
        QCheckBox::indicator {{
            width: 40px; height: 22px;
            border-radius: 11px;
            background-color: {c['fg_disabled']};
            border: none;
        }}
        QCheckBox::indicator:checked {{
            background-color: {c['accent']};
        }}
        QCheckBox::indicator::handle {{
            width: 18px; height: 18px;
            border-radius: 9px;
            background-color: {c['fg_on_fill']};
            margin: 2px;
        }}
        QCheckBox::indicator:checked::handle {{
            margin-left: 20px;
        }}
    """


def card_qss() -> str:
    """卡片样式"""
    c = get_colors()
    return f"""
        background-color: {c['card_bg']};
        border-radius: 8px;
    """


def tag_qss() -> str:
    """标签样式"""
    return f"""
        font-size: {SIZE_CAPTION}px;
        font-weight: 500;
        padding: 2px 10px;
        border-radius: 4px;
        border: none;
    """
