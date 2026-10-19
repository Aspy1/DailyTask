"""自绘抗锯齿圆角按钮：接管 QSS 里的"背景/描边/圆角"，其余（文字/内边距/字号）仍走 QSS。

为什么要它（见 `design/INDEX.md` §"渲染路径"）：
QSS 的 `border-radius` 由 `QStyleSheetStyle` 绘制，**不开抗锯齿、也不裁剪控件**，
在非整数缩放下圆角会被量化成台阶（"角点"）。要彻底消除只有一条路：**自己画**。

设计取舍：**调用点只改类名**。类在首次显示时把自带 QSS 里的
`background-color` / `background` / `border` / `border-radius` **读出来并从 QSS 里摘掉**
（换成 `background: transparent; border: none;`），由 `paintEvent` 用 `QPainter` + 抗锯齿重画。
这样各面板原有的内联样式（颜色、hover、pressed、padding、字号）都不用改。
"""

import re
from typing import Any

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionButton

from src.ui.styles.theme import RADIUS, get_colors, qcolor
from src.ui.styles.theme import remap_colors as _remap_colors

_DECL = r"(?:background(?:-color)?|border|border-radius)\s*:\s*[^;{}]+;?"

# 伪状态的判定顺序（一个选择器可能同时带多个，如 `:hover:disabled`）
_STATE_PRIORITY = ("disabled", "pressed", "checked", "hover")


def _state_of(selector: str) -> str:
    """从**选择器**里读出伪状态。

    ⚠ 原来是从**声明块**里找 `:hover` —— 而正则把选择器丢掉了，于是每个块都落进
    `normal`、后写的覆盖先写的（主按钮最后显示的是 disabled 灰、次级按钮长期用 pressed 色）。
    审查 U1。
    """
    for state in _STATE_PRIORITY:
        if f":{state}" in selector:
            return state
    return "normal"


def _extract(qss: str) -> tuple[dict[str, QColor], QColor | None, int]:
    """从 QSS 里读出 (各状态底色, 描边色, 圆角)，并把这些声明从 QSS 中摘掉。"""
    colors: dict[str, QColor] = {}
    border: QColor | None = None
    radius = RADIUS["radius_md"]

    for selector, block in re.findall(r"(QPushButton[^{]*)\{([^}]*)\}", qss):
        state = _state_of(selector)
        m = re.search(r"background(?:-color)?\s*:\s*([^;]+);", block)
        if m:
            colors[state] = qcolor(m.group(1))
        m = re.search(r"border\s*:\s*([^;]+);", block)
        if m and state == "normal":
            spec = m.group(1)
            mc = re.search(r"(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))", spec)
            border = qcolor(mc.group(1)) if mc else None
            if "none" in spec:
                border = None
        m = re.search(r"border-radius\s*:\s*(\d+)px", block)
        if m and state == "normal":
            radius = int(m.group(1))

    cleaned = re.sub(_DECL, "", qss)
    cleaned = cleaned.replace("QPushButton {", "QPushButton { background: transparent; border: none;", 1)
    return colors, border, radius


class RoundedButton(QPushButton):
    """带自绘抗锯齿圆角的按钮（会自动接管 QSS 里的背景/描边/圆角）。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._bg: dict[str, QColor] = {}
        self._border: QColor | None = None
        self._radius = RADIUS["radius_md"]
        self._absorbed = False
        # 调用方给的**原始** QSS（带颜色）。自绘底色从这里读 ——
        # `styleSheet()` 里那份已经被摘掉颜色了，换主题时靠它才能重算（审查 U1）
        self._original_qss = ""
        self._absorbing = False
        self._applied_qss = ""          # 我们自己写回去的那份（用来区分"谁改的样式"）

    def _absorb_qss(self) -> None:
        """把 QSS 里的背景/描边/圆角搬到自己身上（**每次样式变化都要重做**）。"""
        if self._absorbed:
            return
        qss = self._original_qss or self.styleSheet()
        if not qss:
            # ⚠ 首次 paint 可能发生在调用方 setStyleSheet 之前：
            # 这里**不能**锁死，否则之后永远不再吸收，QSS 底色会与自绘叠加（实测色偏深）
            return
        self._absorbed = True
        colors, border, radius = _extract(qss)
        self._bg, self._border, self._radius = colors, border, radius
        cleaned = re.sub(_DECL, "", qss)
        # 基底规则补上透明底（否则 QSS 仍会画方形底）
        cleaned = re.sub(r"(QPushButton\s*\{)", r"\1 background: transparent; border: none;",
                         cleaned, count=1)
        self._absorbing = True          # 别把自己的这次 setStyleSheet 当成"外部换样式"
        try:
            self.setStyleSheet(cleaned)
            self._applied_qss = cleaned
        finally:
            self._absorbing = False

    def changeEvent(self, event) -> None:
        """样式表被换掉（含换主题的 `remap_stylesheets`）→ 作废缓存，下次 paint 重新吸收。

        ⚠ **只有"调用方重新给了样式"才算新的原始样式**（2026-10-19 审查 R4）：
        全局 `app.setStyleSheet(...)` 也会发 StyleChange ✗，但那时 `styleSheet()` 已经是我们
        自己写回去的**剥掉背景**的那份 —— 拿它当"原始样式"，按钮底色就全没了（实测四个背景
        状态塌成一个透明 normal ✗）。区分办法：跟自己最后写回去的那份比。
        """
        if event.type() == QEvent.Type.StyleChange and not self._absorbing:
            current = self.styleSheet()
            if current != self._applied_qss:
                self._original_qss = current      # 外部真的换了样式 → 这才是新的原始样式
            self._absorbed = False                # 全局换主题也要重新吸收（色值由 remap 更新）
        super().changeEvent(event)

    def remap_theme_colors(self, maps: tuple[dict[str, str], dict[str, str]]) -> bool:
        """换主题时由 `theme.remap_stylesheets()` 调用。

        ⚠ 为什么需要它：自绘底色**不在 `styleSheet()` 里**（已经被摘掉），
        所以按样式表做色值替换根本碰不到它 —— 换主题后按钮还是旧底色（审查 U1）。
        """
        if not self._original_qss:
            return False
        new_qss = _remap_colors(self._original_qss, maps)
        if new_qss == self._original_qss:
            return False
        self._original_qss = new_qss
        self._absorbed = False
        return True

    def showEvent(self, event) -> None:
        self._absorb_qss()
        super().showEvent(event)

    def paintEvent(self, event) -> None:
        self._absorb_qss()
        if self._bg:
            c = get_colors()
            if not self.isEnabled():
                fill = self._bg.get("disabled", self._bg.get("normal", QColor(0, 0, 0, 0)))
            elif self.isDown():
                fill = self._bg.get("pressed", self._bg.get("hover", self._bg["normal"]))
            elif self.isChecked():
                fill = self._bg.get("checked", self._bg.get("hover", self._bg["normal"]))
            elif self.underMouse():
                fill = self._bg.get("hover", self._bg["normal"])
            else:
                fill = self._bg["normal"]
            if fill.alpha() > 0:
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                rect = self.rect().adjusted(0, 0, -1, -1)
                painter.setBrush(fill)
                if self._border is not None:
                    painter.setPen(self._border)
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect, self._radius, self._radius)
                painter.end()
            elif self._border is not None:
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(self._border)
                painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1),
                                        self._radius, self._radius)
                painter.end()
            _ = c
        # 只画"文字/图标"这一层：`super().paintEvent()` 会把**原生按钮底面**也画出来，
        # 它会从自绘的半透明底色下透出来（次级按钮会看起来像原生按钮）。
        # CE_PushButtonLabel 仍由 QStyleSheetStyle 处理，QSS 的 color / padding / 字号照旧生效。
        option = QStyleOptionButton()
        self.initStyleOption(option)
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButtonLabel, option, painter, self)
        painter.end()
