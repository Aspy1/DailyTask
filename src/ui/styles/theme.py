"""Design system — Warm Paper Study palette (light-first)."""

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

FONT_CN = "Microsoft YaHei"
FONT_MONO = "Consolas"

# ── Type scale (see DESIGN_TOKENS.md §2.2) ──────────────
SIZE_CAPTION  = 12   # table data, status bar
SIZE_BODY_S   = 13   # secondary text, labels, footnotes
SIZE_BODY     = 14   # body (default)
SIZE_BODY_L   = 16   # card titles, emphasized body
SIZE_SUBTITLE = 20   # section headings
SIZE_TITLE    = 28   # page titles
SIZE_HEADING  = 36   # hero / empty-state headings

# ── Design tokens (see DESIGN_TOKENS.md §1) ─────────────

TOKENS = {
    "light": {
        # Backgrounds
        "bg_root":          "#F2EFE9",
        "bg_surface":       "#E0DDD6",
        "bg_card":          "#FDFCFA",
        "bg_elevated":      "#FDFCFA",
        "bg_input":         "#F2EFE9",
        # Foregrounds
        "fg_primary":       "#2D2A26",
        "fg_secondary":     "#6E6B66",
        "fg_hint":          "#9E9B96",
        "fg_disabled":      "#C6C4BF",
        # Accent
        "accent":           "#B0823A",
        "accent_hover":     "#C99845",
        "accent_dim":       "#966C2E",
        "accent_bg":        "rgba(176,130,58,0.08)",
        # Borders
        "border":           "rgba(0,0,0,0.08)",
        "border_strong":    "rgba(0,0,0,0.12)",
        "divider":          "rgba(0,0,0,0.04)",
        # Functional
        "red":              "#D14343",
        "green":            "#4A8B5F",
        "yellow":           "#B0823A",
        "orange":           "#C5702A",
        # Navigation
        "sidebar_bg":       "#D0CCC4",
        "chat_bg":          "#FDFCFA",
        "input_bg":         "#F2EFE9",
        "input_border":     "rgba(0,0,0,0.10)",
        "btn_secondary_bg":       "rgba(0,0,0,0.04)",
        "btn_secondary_fg":       "#6E6B66",
        "btn_secondary_hover":    "rgba(0,0,0,0.06)",
        "btn_secondary_hover_fg": "#2D2A26",
        "table_alt":        "rgba(0,0,0,0.02)",
        "card_bg":          "#F9F6F0",
        "card_border":      "rgba(0,0,0,0.06)",
        "section_heading":  "#B0823A",
        "nav_bg":           "#D0CCC4",
        "status_bar_bg":    "#E3E0D9",
        "nav_selected_bg":  "rgba(176,130,58,0.10)",
        "nav_selected_fg":  "#966C2E",
    },
    "dark": {
        # Backgrounds — warm dark paper tones
        "bg_root":          "#1E1D1A",
        "bg_surface":       "#252421",
        "bg_card":          "#2C2B27",
        "bg_elevated":      "#33322E",
        "bg_input":         "#252421",
        # Foregrounds — warm off-white, never pure #FFF
        "fg_primary":       "#E8E5DF",
        "fg_secondary":     "#A8A59F",
        "fg_hint":          "#706D68",
        "fg_disabled":      "#504D48",
        # Accent — warmer amber for dark bg
        "accent":           "#D4A853",
        "accent_hover":     "#E0BC6B",
        "accent_dim":       "#C49840",
        "accent_bg":        "rgba(212,168,83,0.10)",
        # Borders — subtle
        "border":           "rgba(255,255,255,0.05)",
        "border_strong":    "rgba(255,255,255,0.09)",
        "divider":          "rgba(255,255,255,0.03)",
        # Functional — softened
        "red":              "#E06060",
        "green":            "#5FA87A",
        "yellow":           "#D4A853",
        "orange":           "#D48A40",
        # Navigation — darker sidebar, distinct
        "sidebar_bg":       "#1A1917",
        "chat_bg":          "#1E1D1A",
        "input_bg":         "#252421",
        "input_border":     "rgba(255,255,255,0.07)",
        "btn_secondary_bg":       "rgba(255,255,255,0.03)",
        "btn_secondary_fg":       "#A8A59F",
        "btn_secondary_hover":    "rgba(255,255,255,0.06)",
        "btn_secondary_hover_fg": "#E8E5DF",
        "table_alt":        "rgba(255,255,255,0.015)",
        "card_bg":          "#2C2B27",
        "card_border":      "rgba(255,255,255,0.06)",
        "section_heading":  "#D4A853",
        "nav_bg":           "#1A1917",
        "status_bar_bg":    "#2C2B27",
        "nav_selected_bg":  "rgba(212,168,83,0.12)",
        "nav_selected_fg":  "#D4A853",
    },
}

_current_mode: str = "light"


def get_mode() -> str:
    return _current_mode


def get_colors() -> dict:
    return TOKENS.get(_current_mode, TOKENS["light"])


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


def init_theme(app: QApplication, mode: str = "light") -> str:
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
    t = TOKENS.get(mode, TOKENS["light"])
    nav_h = 52  # DESIGN_TOKENS.md §3.3
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
QPushButton {{ background-color: transparent; border: none; color: {t["fg_primary"]}; padding: 8px 16px; border-radius: 8px; font-size: {SIZE_BODY}px; }}
QPushButton:hover {{ background-color: rgba(0,0,0,0.04); }}

/* ── Labels ──────────────────────────────── */
QLabel {{ color: {t["fg_primary"]}; background: transparent; }}

/* ── List ────────────────────────────────── */
QListWidget {{ background-color: transparent; color: {t["fg_primary"]}; border: none; outline: none; font-size: {SIZE_BODY_S}px; }}
QListWidget::item {{ padding: 8px 12px; border-radius: 4px; }}
QListWidget::item:selected {{ background-color: {t["accent_bg"]}; }}
QListWidget::item:hover {{ background-color: rgba(0,0,0,0.04); }}

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
QScrollArea {{ border: none; background: transparent; }}

/* ── Table ───────────────────────────────── */
QTableWidget {{ background-color: {t["bg_root"]}; color: {t["fg_primary"]}; gridline-color: {t["divider"]}; border: none; font-size: {SIZE_BODY_S}px; }}
QHeaderView::section {{ background-color: {t["bg_surface"]}; color: {t["fg_secondary"]}; border: none; border-bottom: 1px solid {t["border"]}; padding: 8px 12px; font-weight: 600; font-size: {SIZE_BODY_S}px; }}
QToolTip {{ background-color: {t["bg_elevated"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_strong"]}; border-radius: 8px; padding: 6px 10px; font-size: {SIZE_CAPTION}px; }}

/* ── Named widgets ───────────────────────── */
#fnTabs, #aiPanel, #courseBar, #courseFooter, #taskBar, #taskFooter {{ background-color: transparent; }}
#courseBar, #taskBar {{ background-color: {t["bg_surface"]}; border-bottom: 1px solid {t["divider"]}; }}
#courseFooter, #taskFooter {{ border-top: 1px solid {t["divider"]}; }}
#aiChat {{ background-color: {t["chat_bg"]}; border: none; }}
#aiHeader {{ background-color: {t["sidebar_bg"]}; border-bottom: 1px solid {t["border"]}; }}
#aiInputContainer {{ background-color: {t["sidebar_bg"]}; border-top: 1px solid {t["border"]}; }}
#courseCount, #taskCount {{ color: {t["fg_hint"]}; font-size: 10px; border: none; }}
#taskTable {{ background-color: {t["bg_root"]}; color: {t["fg_primary"]}; border: none; font-size: 12px; }}
#taskTable::item {{ padding: 8px 12px; min-height: 32px; border-bottom: 1px solid {t["divider"]}; }}
#taskTable::item:alternate {{ background-color: {t["table_alt"]}; }}
"""
