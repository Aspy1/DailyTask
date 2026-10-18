"""Design system — Warm Paper Study palette (light-first).

Tokens 的**单一真值**是 `design/tokens.json`（见 `design/INDEX.md` 与 CODE_STANDARDS Q-H8）。
改色值/字号请改 tokens.json，本文件只负责加载并生成 QSS。
"""

import contextlib
import json
import re
from pathlib import Path

from PySide6.QtCore import QEvent, QLocale, QObject, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

# ── Tokens：从单一真值 design/tokens.json 加载（CODE_STANDARDS Q-H8）──
# src/ui/styles/theme.py → 上溯 3 层是仓库根，令牌真值在 design/
_TOKENS_FILE = Path(__file__).resolve().parents[3] / "design" / "tokens.json"
_TOKENS_DATA = json.loads(_TOKENS_FILE.read_text(encoding="utf-8"))

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

# ── 间距刻度（spacing_xs…xxxl，4px 网格）──────────
# 用途：卡片内边距、页面边距、行内间隙。此前这些数字散落在 86 处
# `setContentsMargins(...)` 里（6/7/10/14/28 这种脱网格值也混在里面）。
SPACING: dict = _TOKENS_DATA["spacing"]

# 输入类控件统一高度（一行一个字段；高度不一致会让文字被裁）
FIELD_H = 34

# 小按钮（设置/记账面板的「保存」「测试」「添加」这类）：**固定高 + 最小宽**。
# 不要固定宽 —— 文案换语言或变长就会被裁（此前 72/80/56/70 几个宽度都是手工调出来的）
BTN_H_SM = 30
BTN_W_SM = 72


def size_small_button(btn, min_width: int = BTN_W_SM) -> None:
    """把小按钮设成统一尺寸（理由见上方常量注释）。"""
    btn.setFixedHeight(BTN_H_SM)
    btn.setMinimumWidth(min_width)

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


def _qcolor_from_hash(css: str, alpha: float | None) -> QColor:
    """`#rrggbb` / `#rrggbbaa`（**CSS 语义：alpha 在后**）。

    ⚠ Qt 的 `QColor` 把 8 位 hex 按 `#AARRGGBB` 读，而 QSS 按 CSS 的 `#RRGGBBAA` 读 ——
    同一串颜色两种含义，混用会**静默画错色**（实测 `QColor("#d6454512")` →
    `rgba(69,69,18,214)`，一个橄榄绿）。这里统一按 CSS 语义解释。
    """
    if len(css) == 9:
        css = "#" + css[7:9] + css[1:7]
    color = QColor(css)
    if alpha is not None:
        color.setAlphaF(alpha)
    return color


def _qcolor_from_rgb(css: str, alpha: float | None) -> QColor:
    """`rgba(r,g,b,a)` / `rgb(r,g,b)`。"""
    parts = [p.strip() for p in css[css.index("(") + 1:css.rindex(")")].split(",")]
    r, g, b = (int(float(p)) for p in parts[:3])
    a = float(parts[3]) if len(parts) > 3 else 1.0
    if alpha is not None:
        a = alpha
    return QColor(r, g, b, int(a * 255))


def qcolor(css: str, alpha: float | None = None) -> QColor:
    """token 色值 → QColor（`#rrggbb` / `#rrggbbaa` / `rgba(...)`）。

    自绘控件族（输入/按钮/卡片）都要把令牌值交给 QPainter，`QColor("#rrggbb")`
    能直接吃，但 `rgba(...)` 不行 —— 所以统一在这里解析（此前
    `rounded_input` 与 `rounded_button` 各有一份私有实现）。
    """
    css = css.strip()
    if css.startswith("#"):
        return _qcolor_from_hash(css, alpha)
    if css.startswith("rgb"):
        return _qcolor_from_rgb(css, alpha)
    if css in ("transparent", "none", ""):
        return QColor(0, 0, 0, 0)
    return QColor(css)


def elide_text(text: str, font: QFont, max_width: int) -> str:
    """Ellipsize text to fit within max_width pixels.

    Usage:
        from src.ui.styles.theme import elide_text
        label.setText(elide_text(long_text, label.font(), 200))
    """
    from PySide6.QtGui import QFontMetrics
    metrics = QFontMetrics(font)
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max_width)


def _theme_color_maps(from_mode: str, to_mode: str) -> tuple[dict[str, str], dict[str, str]]:
    """两个主题之间的色值映射，**按用途分成两份**：(文字色, 填充色)。

    ⚠ 按**色值**做键本身有损：浅色里 `accent` 与 `accent_text` 可能同色、深色里却不同 ——
    这时只能靠**属性角色**消歧（`color:` 查文字映射、`background:`/`border:` 查填充映射）。
    审查 U2 实测：浅色的 accent_text 被换成了深色的**填充**色 `#8F6E33`（应为 `#D9AE58`）。
    """
    old, new = TOKENS.get(from_mode, {}), TOKENS.get(to_mode, {})
    text: dict[str, str] = {}
    fill: dict[str, str] = {}
    for key, val in old.items():
        if not _is_color(val):
            continue
        new_val = new.get(key)
        if not _is_color(new_val) or new_val == val:
            continue
        (text if _is_text_token(key) else fill).setdefault(val, new_val)
    return text, fill


def _is_color(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("#", "rgb"))


def _is_text_token(key: str) -> bool:
    """这个 token 是**文字色**吗（`fg_*` / `*_text`）—— 用来消解"两个 token 同色"的歧义。"""
    return key.startswith("fg_") or key.endswith("_text")


def rgba(color: str, alpha: float) -> str:
    """把 `#RRGGBB` 加透明度 → `rgba(r, g, b, a)`。

    ⚠ 别写 `f"{color}18"`：Qt 的 QSS 把 8 位十六进制当 **AARRGGBB**（不是 RRGGBBAA），
    于是 `#B93B3B18` 被解释成"透明橄榄色"而不是"浅红"（审查 U4）。
    """
    col = qcolor(color)
    return (f"rgba({col.red()}, {col.green()}, {col.blue()}, "
            f"{max(0.0, min(1.0, alpha)):.3f})")


_DECL_RE = re.compile(r"(?P<prop>[a-zA-Z-]+)\s*:\s*(?P<value>[^;{}]+)")


def _is_fill_prop(prop: str) -> bool:
    """这个属性画的是"填充"吗 —— 是则查填充映射，否则查文字映射（`color:` 等）。"""
    return prop.startswith(("background", "border", "outline"))


def remap_colors(qss: str, maps: tuple[dict[str, str], dict[str, str]]) -> str:
    """按**属性角色**替换色值：`color:` 用文字映射，`background`/`border` 用填充映射。

    逐条声明处理，而不是整串替换 —— 否则"同色不同用途"的两个 token 会换错（审查 U2）。
    """
    text_map, fill_map = maps

    def _sub(m: re.Match) -> str:
        prop, value = m.group("prop"), m.group("value")
        table = fill_map if _is_fill_prop(prop) else text_map
        out = value
        for old_val, new_val in table.items():
            out = re.sub(re.escape(old_val), new_val, out, flags=re.IGNORECASE)
        return f"{prop}: {out}"

    return _DECL_RE.sub(_sub, qss)


def _remap_qss(qss: str, maps: tuple[dict[str, str], dict[str, str]]) -> str:
    """把样式表里的旧色值换成新色值（大小写不敏感）。"""
    return remap_colors(qss, maps)


def remap_stylesheets(app: QApplication, from_mode: str, to_mode: str) -> int:
    """把已存在内联样式表里的旧主题色，整体替换成新主题色。

    背景：大量部件是 `w.setStyleSheet(f"...{c['card_bg']}...")` 这样在**构造时**
    把颜色写死的。换主题时这些样式不会自动更新，于是出现"切换不完全"：
    浅色界面里留着深色卡片、深色界面里留着浅色卡片、字色与底色撞在一起。

    与其给每个部件补 `refresh_theme()`（永远会漏），不如做一次**色值映射**：
    遍历所有部件的样式表，把 from_mode 的色值替换为 to_mode 的同名 token 值。
    返回被改写的部件数（便于测试断言）。
    """
    maps = _theme_color_maps(from_mode, to_mode)
    if not maps[0] and not maps[1]:
        return 0
    changed = 0
    for widget in app.allWidgets():
        # 自绘控件的底色**不在 styleSheet() 里**（被摘掉了）→ 让它们自己重算（审查 U1）
        remap_own = getattr(widget, "remap_theme_colors", None)
        if remap_own is not None and remap_own(maps):
            changed += 1
        qss = widget.styleSheet()
        if not qss:
            continue
        new_qss = _remap_qss(qss, maps)
        if new_qss != qss:
            widget.setStyleSheet(new_qss)
            changed += 1
    return changed


def switch_theme(mode: str) -> str:
    global _current_mode, _color_cache
    previous = _current_mode
    _current_mode = mode
    _color_cache = None
    app = QApplication.instance()
    if app is not None:
        apply_palette(app, mode)
        if previous != mode:
            remap_stylesheets(app, previous, mode)
    return build_theme(mode)


def _resolve_font() -> str:
    families = QFontDatabase.families()
    for name in ("Microsoft YaHei", "PingFang SC", "SimHei", "Noto Sans CJK SC"):
        if name in families:
            return name
    return "Microsoft YaHei"


class _RoundedFrameFixer(QObject):
    """关掉输入类控件的**原生方框**。

    `QLineEdit` / `QComboBox` / `QAbstractSpinBox` 默认 `frame=True`：Windows 上原生方框是
    **直角**的，会从 QSS 的圆角之外露出来，看起来就是"圆角框周围有角点"
    （R-008 记的"QComboBox 禁止 border-radius（产生角点）"就是同一个原因）。

    这里用全局事件钩子统一处理：凡是**样式表里带 `border-radius`** 的输入类控件，
    在显示时关掉原生方框，让 QSS 独占绘制。这样不用去改几十处调用点。
    """

    _TYPES = ("QLineEdit", "QComboBox", "QAbstractSpinBox", "QTextEdit", "QPlainTextEdit")

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.Show or type(obj).__name__ not in self._TYPES:
            return False
        # ⚠ 必须先确认 C++ 对象还活着：长测试会话里会累积"Python 包装器还在、
        # C++ 对象已销毁"的控件，直接碰它们可能**崩进程**（access violation，
        # 不是 Python 异常，try/except 与 suppress 都拦不住）。
        if not isValid(obj):
            return False
        # 不再要求控件自带 border-radius：全局 QSS 也会给它们圆角，
        # 只查自带样式表会漏掉一半（角点残留的根因之一）
        with contextlib.suppress(RuntimeError, AttributeError):
            if hasattr(obj, "setFrame"):
                obj.setFrame(False)
        return False


_ACCENT_PROPERTY = "accentButton"


def configure_locale() -> None:
    """把 Qt 默认区域固定为**用 ASCII 数字**的区域（本机 zh_HK 会出问题）。

    为什么必须做：zh_HK 等区域在 CLDR 里用 **CJK 数字**，于是 `QDateEdit` /
    `QSpinBox` / `QDateTimeEdit` 会把 `2026-10-19` 显示成 `〢〇〢〦-〡〇-〡〩`
    （〇〡〢〣 是汉字/杭州码数字）—— 用户根本看不懂。

    此前项目里已有两处各自打补丁（`inventory_panel` / `schedule_view` 给单个控件
    `setLocale(English, US)`），但只要新增日期/数字控件就会再中一次
    （`habit_panel` 的 QSpinBox、`semester_dialog` 的 QDateEdit 都中过）。

    放在这里并由 `init_theme()` 调用：**任何 UI 入口**都会经过 `init_theme`，
    这样就不会有"忘了设区域"的入口（`App.__init__` 也显式调一次，见 `src/app.py`）。
    """
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))


def mark_accent_button(button) -> None:
    """把按钮标为"主按钮"（强调色填充）。

    ⚠ 样式刷新只能看这个**属性**，不能看按钮**文案**：文案会随措辞/i18n 改动而变，
    用文案判断会让高亮"静默失效"（2026-10-16 修：`task_panel` 曾用
    `txt in ("添加", "记一笔", ...)`，实际一个按钮都没匹配上 —— 是死代码；
    `expense_panel` 则要靠同步改文案才不失效）。
    """
    button.setProperty(_ACCENT_PROPERTY, True)


def is_accent_button(widget) -> bool:
    """该控件是否被标为主按钮（见 `mark_accent_button`）。"""
    return bool(widget.property(_ACCENT_PROPERTY))


def install_rounded_frame_fixer(app: QApplication) -> _RoundedFrameFixer:
    """装上"原生方框"修复钩子（init_theme 会调用；重复调用只装一个）。"""
    existing = getattr(app, "_rounded_frame_fixer", None)
    if existing is not None:
        return existing
    fixer = _RoundedFrameFixer(app)
    app.installEventFilter(fixer)
    app._rounded_frame_fixer = fixer
    return fixer


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


def font(size: int, weight: int | QFont.Weight | None = None) -> QFont:
    """按**像素**字号造字体 —— 与 QSS 的 `font-size: Npx` 同单位。

    ⚠ `QFont(family, size)` 的第二个参数是 **point**（本机 20pt ≈ 27 逻辑像素），
    而 QSS 用的是 px。两套单位混用会让"标题 / 标签 / 输入内容"比例不一致（审查 U5）——
    这里统一走 `setPixelSize`，QSS 不用换算，调用点也只改这一行。
    """
    f = QFont(FONT_CN)
    f.setPixelSize(int(size))
    if weight is not None:
        f.setWeight(QFont.Weight(weight))
    return f


def init_theme(app: QApplication, mode: str = "light") -> str:
    global FONT_CN, _current_mode, _color_cache
    configure_locale()          # 日期/数字控件必须用 ASCII 数字（本机 zh_HK 会出 CJK 数字）
    FONT_CN = _resolve_font()
    _current_mode = mode
    _color_cache = None
    font_ = QFont(FONT_CN)
    font_.setPixelSize(int(SIZE_BODY))          # ⚠ 用像素：QSS 也是 px（审查 U5）
    font_.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font_)

    # Suppress focus rect dotted border on buttons
    from PySide6.QtWidgets import QProxyStyle, QStyle
    class _NoFocusStyle(QProxyStyle):
        def drawPrimitive(self, element, option, painter, widget) -> None:
            if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
                return
            super().drawPrimitive(element, option, painter, widget)
    app.setStyle(_NoFocusStyle(app.style()))
    apply_palette(app, mode)
    install_rounded_frame_fixer(app)

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
QLineEdit {{ background-color: {t["input_bg"]}; color: {t["fg_primary"]}; border: 1px solid {t["border"]}; border-radius: {RADIUS["radius_md"]}px; padding: 0 10px; font-size: {SIZE_BODY_S}px; min-height: {FIELD_H}px; }}
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
QComboBox {{ background-color: {t["input_bg"]}; color: {t["fg_primary"]}; border: 1px solid {t["border"]}; border-radius: {RADIUS["radius_md"]}px; padding: 0 10px; font-size: {SIZE_BODY_S}px; min-height: {FIELD_H}px; }}
QComboBox:hover {{ border-color: {t["border_strong"]}; }}
QComboBox:focus {{ border-color: {t["accent"]}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background-color: {t["bg_elevated"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_strong"]}; selection-background-color: {t["accent_bg"]}; outline: none; }}

/* ── Scroll area ─────────────────────────── */
/* viewport + inner widgets default to palette Base → light grey block in dark mode;
   must be explicitly transparent (explanation kept in English: i18n metric counts
   Chinese literals that are not UI text) */
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


# ── Public style helpers（见 design/INDEX.md 与 design/DESIGN_TOKENS.md）──

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


def input_qss() -> str:
    """**唯一**的输入框样式（Q-H18）。各面板不要自己再写一份。

    统一半径 / 高度 / 字号 / 边框；`:focus` 用强调色。
    """
    c = get_colors()
    return f"""
        QLineEdit {{
            background: transparent; color: {c['fg_primary']};
            border: none;
            padding: 0 10px; font-size: {SIZE_BODY_S}px;
            min-height: {FIELD_H}px;
        }}
    """


def combo_qss() -> str:
    """**唯一**的下拉框样式（Q-H18）。可编辑下拉的内嵌 QLineEdit 必须重置 padding。"""
    c = get_colors()
    return f"""
        QComboBox {{
            background: transparent; color: {c['fg_primary']};
            border: none;
            padding: 0 10px; font-size: {SIZE_BODY_S}px;
            min-height: {FIELD_H}px;
        }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox QLineEdit {{ background: transparent; border: none; padding: 0; }}
        QComboBox QAbstractItemView {{
            background-color: {c['bg_elevated']}; color: {c['fg_primary']};
            border: 1px solid {c['border_strong']};
            selection-background-color: {c['accent_bg']}; outline: none;
        }}
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
