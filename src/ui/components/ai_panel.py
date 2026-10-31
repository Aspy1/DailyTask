"""Column 4: AI chat panel."""

import html
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.ui.styles.theme import LAYOUT, SIZE_BODY, SIZE_BODY_S, SIZE_CAPTION, font, get_colors
from src.ui.widgets.rounded_button import RoundedButton


def _md_to_html(text: str) -> str:
    """Basic markdown to HTML: **bold**, *italic*, `code`, bullet lists.

    ⚠ 先 `html.escape` 再做 markdown：否则用户正文里的 `<b>` 会被 Qt 当标签渲染（审查 U3）。
    ⚠ 代码块用成对的 `code_bg`/`code_fg`：`code_bg` 是深色，正文色不能继承（审查 U8，
    浅色主题下正文/代码底只有 1.32:1）。
    ⚠ 项目符号**不用** `<ul>/<li>`：Qt 给列表项加的块间距很大，回复看着像被拉开
    （2026-10-18 用户反馈"行间距过大"）→ 直接用 `•` 拼 `<br>`；空行也折叠掉，同理。
    """
    colors = get_colors()
    code_bg, code_fg = colors["code_bg"], colors["code_fg"]
    text = html.escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`([^`\n]+?)`',
                  fr'<code style="background:{code_bg};color:{code_fg};padding:1px 4px;'
                  fr'border-radius: 4px;">\1</code>', text)
    out = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('- ') or stripped.startswith('• '):
            out.append(f'•&nbsp;{stripped[2:]}')
        elif stripped:
            out.append(stripped)      # 空行丢掉：靠 `margin-bottom` 分隔消息就够了
    return '<br>'.join(out)


class _ChatInput(QTextEdit):
    send_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMaximumHeight(LAYOUT["ai_input_max_height"])
        self.setMinimumHeight(LAYOUT["ai_input_min_height"])
        self.setFont(font(SIZE_CAPTION))
        self.setTabChangesFocus(True)
        c = get_colors()
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {c['input_bg']};
                color: {c['fg_primary']};
                border: 1px solid {c['input_border']};
                border-radius: 8px;
                padding: 6px 10px;
                font-family: "Microsoft YaHei UI", "Consolas", sans-serif;
                font-size: {SIZE_BODY}px;
            }}
            QTextEdit:focus {{ border-color: {c['focus_ring']}; }}
        """)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_requested.emit()
            return
        super().keyPressEvent(event)


class AIPanel(QWidget):
    message_sent = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        c = get_colors()
        self.setObjectName("aiPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(LAYOUT["ai_panel_min_width"])
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("aiHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 12, 12, 8)
        title = QLabel(tr("ai.title"))
        title.setFont(font(SIZE_BODY_S))
        title.setStyleSheet(f"font-weight: 600; color: {c['fg_primary']}; border: none;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self._status_indicator = QLabel("●")
        self._status_indicator.setStyleSheet(f"color: {c['fg_disabled']}; font-size: {SIZE_BODY}px; border: none;")
        header_layout.addWidget(self._status_indicator)
        layout.addWidget(header)

        # Chat display — QScrollArea + QLabel instead of QTextEdit
        self._scroll = QScrollArea()
        self._scroll.setObjectName("aiChat")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {c['chat_bg']}; border: none; }}"
        )

        # 消息按结构存（角色/正文/占位）：颜色烤进 HTML 会丢原文，换主题就没法重画（U3）
        self._messages: list[dict] = []
        self._chat_label = QLabel()
        self._chat_label.setWordWrap(True)
        self._chat_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._chat_label.setTextFormat(Qt.TextFormat.RichText)
        self._chat_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._chat_label.setStyleSheet(
            f"QLabel {{ background-color: {c['chat_bg']}; color: {c['fg_primary']}; padding: 8px; font-size: {SIZE_BODY}px; }}"
        )
        self._chat_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._scroll.setWidget(self._chat_label)
        layout.addWidget(self._scroll, stretch=1)

        # Input area
        input_container = QWidget()
        input_container.setObjectName("aiInputContainer")
        input_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(8)

        self._input = _ChatInput()
        self._input.send_requested.connect(self._on_send)
        input_layout.addWidget(self._input)

        self._send_btn = RoundedButton(tr("ai.send"))
        self._send_btn.setFixedSize(LAYOUT["ai_send_width"], LAYOUT["ai_input_min_height"])
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']};"
            f" border: none; border-radius: 8px; font-weight: 600; font-size: {SIZE_BODY}px; }}"
            f" QPushButton:hover {{ background-color: {c['accent_hover']}; }}"
            f" QPushButton:pressed {{ background-color: {c['accent_dim']}; }}"
            f" QPushButton:disabled {{ background-color: {c['fg_disabled']};"
            f" color: {c['fg_on_fill']}; }}")
        self._send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self._send_btn)

        layout.addWidget(input_container)

    def _on_send(self) -> None:
        if self._send_btn.isEnabled() is False:
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        self.append_message("user", text)
        self._input.clear()
        self._send_btn.setEnabled(False)
        self._input.setEnabled(False)
        self._send_btn.setText("...")
        self.set_status(True, thinking=True)
        self.message_sent.emit(text)

    def append_message(self, role: str, text: str, is_placeholder: bool = False) -> None:
        """追加一条消息（**存结构**，随后按当前主题整体重画）。

        ⚠ 原实现把颜色写进 HTML 再拼到 `QLabel` 上，原文就丢了 —— 换主题后历史消息
        仍是旧配色（审查 U3）。现在原文留在 `self._messages` 里，`refresh_theme()` 能重画。
        """
        if role == "ai" and not is_placeholder:
            # 真回复到了 → 先去掉"正在思考"的占位（原来是拿 `<!--ph-->` 做字符串手术）
            self._messages = [m for m in self._messages if not m["placeholder"]]
        self._messages.append({"role": role, "text": text, "placeholder": is_placeholder})
        self._render_messages()

    def _render_messages(self) -> None:
        """按**当前主题**重画全部消息（追加与换主题都走这里）。"""
        self._chat_label.setText("".join(self._message_html(m) for m in self._messages))
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _message_html(self, msg: dict) -> str:
        """一条消息 → HTML。颜色**每次现取**，不缓存（否则换主题不生效）。"""
        c = get_colors()
        if msg["role"] == "user":
            style = (f'background-color:{c["accent"]};color:{c["fg_on_fill"]};'
                     f'border-radius:12px;padding:8px 14px;')
            margin, body = "margin-left", html.escape(msg["text"])
        elif msg["placeholder"]:
            style = (f'color:{c["fg_hint"]};padding:4px 0;'
                     f'border-left:2px solid {c["accent"]};padding-left:12px;font-style:italic;')
            margin, body = "margin-right", html.escape(msg["text"])
        else:
            style = (f'color:{c["fg_primary"]};padding:4px 0;'
                     f'border-left:2px solid {c["border"]};padding-left:12px;')
            margin, body = "margin-right", _md_to_html(msg["text"])
        return (f'<div style="margin-bottom:12px;{margin}:24px;">'
                f'<div style="display:inline-block;max-width:100%;{style}'
                f'font-size: {SIZE_BODY_S}px;text-align:left;word-wrap:break-word;">'
                f'{body}</div></div>').replace("\n", "<br>")

    def append_message_ai(self, text: str) -> None:
        self.append_message("ai", text)
        self._on_response_done()

    def set_status(self, online: bool, thinking: bool = False) -> None:
        c = get_colors()
        if thinking:
            self._status_indicator.setStyleSheet(f"color: {c['yellow']}; font-size: {SIZE_BODY}px; border: none;")
            self._status_indicator.setToolTip(tr("ai.thinking"))
        elif online:
            self._status_indicator.setStyleSheet(f"color: {c['green']}; font-size: {SIZE_BODY}px; border: none;")
            self._status_indicator.setToolTip(tr("ai.online"))
        else:
            self._status_indicator.setStyleSheet(f"color: {c['fg_disabled']}; font-size: {SIZE_BODY}px; border: none;")
            self._status_indicator.setToolTip(tr("ai.offline"))

    def fill_input(self, text: str) -> None:
        self._input.setPlainText(text)
        self._input.setFocus()
        cursor = self._input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._input.setTextCursor(cursor)

    def _on_response_done(self) -> None:
        self._send_btn.setEnabled(True)
        self._input.setEnabled(True)
        self._send_btn.setText(tr("ai.send"))
        self._input.setFocus()

    def refresh_theme(self) -> None:
        c = get_colors()
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {c['chat_bg']}; border: none; }}"
        )
        self._chat_label.setStyleSheet(
            f"QLabel {{ background-color: {c['chat_bg']}; color: {c['fg_primary']}; padding: 8px; font-size: {SIZE_BODY}px; }}"
        )
        self._render_messages()      # ⚠ 历史消息的配色写在 HTML 里 → 必须重画（审查 U3）

