"""Design system — PCL-inspired blue monochrome palette."""

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

FONT_CN = "Microsoft YaHei"
FONT_MONO = "Consolas"

SIZE_CAPTION = 10
SIZE_BODY_S = 12
SIZE_BODY = 13
SIZE_BODY_L = 14
SIZE_TITLE = 15
SIZE_HEADING = 17

# ── PCL-inspired tokens ─────────────────────────────────────

TOKENS = {
    "dark": {
        "bg_root": "#0d1117", "bg_surface": "#161b22", "bg_card": "#1c2333",
        "bg_surface_hi": "#21262d", "bg_elevated": "#30363d",
        "fg_primary": "#c9d1d9", "fg_secondary": "#8b949e", "fg_hint": "#6e7681",
        "fg_disabled": "#484f58",
        "accent": "#1370f3", "accent_hover": "#1f6feb", "accent_dim": "#0d419d",
        "accent_bg": "rgba(19,112,243,0.12)",
        "border": "rgba(255,255,255,0.06)", "border_strong": "rgba(255,255,255,0.10)",
        "divider": "rgba(255,255,255,0.04)",
        "red": "#f85149", "green": "#3fb950", "yellow": "#d2991d", "orange": "#db6d28",
        "sidebar_bg": "#161b22", "chat_bg": "#0d1117",
        "input_bg": "#0d1117", "input_border": "rgba(255,255,255,0.08)",
        "btn_secondary_bg": "rgba(255,255,255,0.04)", "btn_secondary_fg": "#8b949e",
        "btn_secondary_hover": "rgba(255,255,255,0.08)", "btn_secondary_hover_fg": "#c9d1d9",
        "table_alt": "rgba(255,255,255,0.02)",
        "card_bg": "rgba(255,255,255,0.03)", "card_border": "rgba(255,255,255,0.05)",
        "section_heading": "rgba(19,112,243,0.65)",
        "nav_bg": "#161b22", "nav_selected_bg": "rgba(19,112,243,0.12)",
        "nav_selected_fg": "#58a6ff",
    },
    "light": {
        "bg_root": "#ffffff", "bg_surface": "#f6f8fa", "bg_card": "#ffffff",
        "bg_surface_hi": "#eaeef2", "bg_elevated": "#d0d7de",
        "fg_primary": "#1f2328", "fg_secondary": "#656d76", "fg_hint": "#8c959f",
        "fg_disabled": "#afb8c1",
        "accent": "#1370f3", "accent_hover": "#1f6feb", "accent_dim": "#0d419d",
        "accent_bg": "rgba(19,112,243,0.08)",
        "border": "rgba(0,0,0,0.06)", "border_strong": "rgba(0,0,0,0.10)",
        "divider": "rgba(0,0,0,0.04)",
        "red": "#cf222e", "green": "#1a7f37", "yellow": "#9a6700", "orange": "#bc4c00",
        "sidebar_bg": "#f6f8fa", "chat_bg": "#ffffff",
        "input_bg": "#f6f8fa", "input_border": "rgba(0,0,0,0.10)",
        "btn_secondary_bg": "rgba(0,0,0,0.04)", "btn_secondary_fg": "#656d76",
        "btn_secondary_hover": "rgba(0,0,0,0.08)", "btn_secondary_hover_fg": "#1f2328",
        "table_alt": "rgba(0,0,0,0.02)",
        "card_bg": "#ffffff", "card_border": "rgba(0,0,0,0.06)",
        "section_heading": "#1370f3",
        "nav_bg": "#f6f8fa", "nav_selected_bg": "rgba(19,112,243,0.10)",
        "nav_selected_fg": "#1370f3",
    },
}

_current_mode: str = "dark"


def get_mode() -> str:
    return _current_mode


def get_colors() -> dict:
    return TOKENS.get(_current_mode, TOKENS["dark"])


def switch_theme(mode: str) -> str:
    global _current_mode
    _current_mode = mode
    return build_theme(mode)


def _resolve_font() -> str:
    families = QFontDatabase.families()
    for name in ("Microsoft YaHei", "PingFang SC", "SimHei", "Noto Sans CJK SC"):
        if name in families:
            return name
    return "Microsoft YaHei"


def init_theme(app: QApplication, mode: str = "dark") -> str:
    global FONT_CN, _current_mode
    FONT_CN = _resolve_font()
    _current_mode = mode
    font = QFont(FONT_CN, SIZE_BODY)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)

    # Suppress focus rect dotted border on buttons
    from PySide6.QtWidgets import QProxyStyle, QStyle
    class _NoFocusStyle(QProxyStyle):
        def drawPrimitive(self, element, option, painter, widget):
            if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
                return
            super().drawPrimitive(element, option, painter, widget)
    app.setStyle(_NoFocusStyle(app.style()))

    return build_theme(mode)


def build_theme(mode: str) -> str:
    t = TOKENS.get(mode, TOKENS["dark"])
    return f"""
* {{ font-family: "{FONT_CN}", "Microsoft YaHei", sans-serif; }}

QMainWindow {{ background-color: {t["bg_root"]}; }}

/* ── Top nav bar ─────────────────────────── */
#topNav {{ background-color: {t["nav_bg"]}; border-bottom: 1px solid {t["border"]}; }}
#topNav QPushButton {{
    background-color: transparent; color: {t["fg_secondary"]}; border: none;
    border-radius: 14px; padding: 6px 18px; font-size: {SIZE_BODY}px;
    min-height: 30px;
}}
#topNav QPushButton:hover {{
    background-color: {t["accent_bg"]}; color: {t["fg_primary"]};
}}
#topNav QPushButton:checked {{
    background-color: {t["nav_selected_bg"]}; color: {t["nav_selected_fg"]}; font-weight: 600;
}}

/* ── Menus ───────────────────────────────── */
QMenuBar {{ background-color: {t["bg_surface"]}; color: {t["fg_primary"]}; border-bottom: 1px solid {t["border"]}; padding: 2px 0; font-size: {SIZE_BODY_S}px; }}
QMenuBar::item:selected {{ background-color: {t["bg_surface_hi"]}; border-radius: 4px; }}
QMenu {{ background-color: {t["bg_surface_hi"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_strong"]}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 32px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {t["accent_bg"]}; color: {t["fg_primary"]}; }}
QMenu::separator {{ height: 1px; background-color: {t["divider"]}; margin: 4px 8px; }}

/* ── Buttons ─────────────────────────────── */
QPushButton {{ background-color: transparent; border: none; color: {t["fg_primary"]}; padding: 6px 12px; border-radius: 6px; }}
QPushButton:hover {{ background-color: {t["bg_surface_hi"]}; }}

/* ── Labels ──────────────────────────────── */
QLabel {{ color: {t["fg_primary"]}; background: transparent; }}

/* ── List ────────────────────────────────── */
QListWidget {{ background-color: transparent; color: {t["fg_primary"]}; border: none; outline: none; font-size: {SIZE_BODY_S}px; }}
QListWidget::item {{ padding: 6px 10px; border-radius: 6px; }}
QListWidget::item:selected {{ background-color: {t["accent_bg"]}; }}
QListWidget::item:hover {{ background-color: {t["bg_surface_hi"]}; }}

/* ── Inputs ──────────────────────────────── */
QTextEdit, QPlainTextEdit {{ background-color: {t["input_bg"]}; color: {t["fg_primary"]}; border: 1px solid {t["border"]}; border-radius: 8px; padding: 8px 10px; font-size: {SIZE_BODY}px; selection-background-color: {t["accent_bg"]}; }}
QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {t["accent"]}; }}
QLineEdit {{ background-color: {t["input_bg"]}; color: {t["fg_primary"]}; border: 1px solid {t["border"]}; border-radius: 8px; padding: 7px 10px; font-size: {SIZE_BODY}px; }}
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
QSplitter::handle {{ background-color: {t["border"]}; }}
QSplitter::handle:horizontal {{ width: 1px; }}

/* ── Status bar ──────────────────────────── */
QStatusBar {{ background-color: {t["bg_surface"]}; color: {t["fg_secondary"]}; font-size: {SIZE_CAPTION}px; padding: 3px 10px; border-top: 1px solid {t["border"]}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {t["fg_secondary"]}; padding: 0; }}

/* ── Checkbox ────────────────────────────── */
QCheckBox {{ color: {t["fg_primary"]}; spacing: 8px; font-size: {SIZE_BODY}px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 2px solid {t["fg_hint"]}; border-radius: 4px; background: transparent; }}
QCheckBox::indicator:checked {{ background-color: {t["accent"]}; border-color: {t["accent"]}; }}

/* ── Combo box ───────────────────────────── */
QComboBox {{ background-color: {t["input_bg"]}; color: {t["fg_primary"]}; border: 1px solid {t["border"]}; border-radius: 8px; padding: 7px 10px; font-size: {SIZE_BODY}px; }}
QComboBox:hover {{ border-color: {t["border_strong"]}; }}
QComboBox:focus {{ border-color: {t["accent"]}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background-color: {t["bg_surface_hi"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_strong"]}; border-radius: 6px; selection-background-color: {t["accent_bg"]}; outline: none; }}

/* ── Scroll area ─────────────────────────── */
QScrollArea {{ border: none; background: transparent; }}

/* ── Table ───────────────────────────────── */
QTableWidget {{ background-color: {t["bg_root"]}; color: {t["fg_primary"]}; gridline-color: {t["divider"]}; border: none; font-size: {SIZE_CAPTION}px; }}
QHeaderView::section {{ background-color: {t["bg_surface"]}; color: {t["fg_secondary"]}; border: none; border-bottom: 1px solid {t["border"]}; padding: 8px 4px; font-weight: 600; font-size: {SIZE_BODY_S}px; }}
QToolTip {{ background-color: {t["bg_elevated"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_strong"]}; border-radius: 6px; padding: 6px 10px; font-size: {SIZE_CAPTION}px; }}

/* ── Named widgets ───────────────────────── */
#fnTabs, #aiPanel, #courseBar, #courseFooter, #taskBar, #taskFooter {{ background-color: {t["sidebar_bg"]}; }}
#courseBar, #taskBar {{ border-bottom: 1px solid {t["divider"]}; }}
#courseFooter, #taskFooter {{ border-top: 1px solid {t["divider"]}; }}
#aiChat {{ background-color: {t["chat_bg"]}; border: none; }}
#aiHeader {{ background-color: {t["sidebar_bg"]}; border-bottom: 1px solid {t["border"]}; }}
#aiInputContainer {{ background-color: {t["sidebar_bg"]}; border-top: 1px solid {t["border"]}; }}
#courseCount, #taskCount {{ color: {t["fg_hint"]}; font-size: 10px; border: none; }}
#taskTable {{ background-color: {t["bg_root"]}; color: {t["fg_primary"]}; border: none; font-size: 12px; }}
#taskTable::item {{ padding: 8px 6px; border-bottom: 1px solid {t["divider"]}; }}
#taskTable::item:alternate {{ background-color: {t["table_alt"]}; }}
"""
