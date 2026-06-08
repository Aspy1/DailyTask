"""Column 4: AI chat panel."""

import re

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QSizePolicy, QScrollArea,
)
from PySide6.QtGui import QFont, QKeyEvent

from src.i18n.loader import tr
from src.ui.styles.theme import get_colors


def _md_to_html(text: str) -> str:
    """Basic markdown to HTML: **bold**, *italic*, `code`, bullet lists."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`([^`\n]+?)`', r'<code style="background:#3a3a40;padding:1px 4px;border-radius: 4px;">\1</code>', text)
    # Bullet points: lines starting with - or • become <li>
    lines = text.split('\n')
    in_list = False
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('- ') or stripped.startswith('• '):
            if not in_list:
                out.append('<ul style="margin:2px 0;padding-left:16px;">')
                in_list = True
            out.append(f'<li>{stripped[2:]}</li>')
        else:
            if in_list:
                out.append('</ul>')
                in_list = False
            out.append(line)
    if in_list:
        out.append('</ul>')
    return '<br>'.join(out)


class _ChatInput(QTextEdit):
    send_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumHeight(72)
        self.setMinimumHeight(36)
        self.setFont(QFont("Microsoft YaHei UI", 11))
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
                font-size: 14px;
            }}
            QTextEdit:focus {{ border-color: {c['accent']}; }}
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

    def __init__(self, parent=None):
        super().__init__(parent)
        c = get_colors()
        self.setObjectName("aiPanel")
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("aiHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 12, 12, 8)
        title = QLabel(tr("ai.title"))
        title.setFont(QFont(self.font().family(), 13))
        title.setStyleSheet(f"font-weight: 600; color: {c['fg_primary']}; border: none;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self._status_indicator = QLabel("●")
        self._status_indicator.setStyleSheet(f"color: {c['fg_disabled']}; font-size: 14px; border: none;")
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

        self._chat_label = QLabel()
        self._chat_label.setWordWrap(True)
        self._chat_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._chat_label.setTextFormat(Qt.TextFormat.RichText)
        self._chat_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._chat_label.setStyleSheet(
            f"QLabel {{ background-color: {c['chat_bg']}; color: {c['fg_primary']}; padding: 8px; font-size: 14px; }}"
        )
        self._chat_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._scroll.setWidget(self._chat_label)
        layout.addWidget(self._scroll, stretch=1)

        # Input area
        input_container = QWidget()
        input_container.setObjectName("aiInputContainer")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(8)

        self._input = _ChatInput()
        self._input.send_requested.connect(self._on_send)
        input_layout.addWidget(self._input)

        self._send_btn = QPushButton(tr("ai.send"))
        self._send_btn.setFixedSize(64, 36)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['accent']}; color: #fff; border: none;
                border-radius: 8px; font-weight: 600; font-size: 14px;
            }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            QPushButton:pressed {{ background-color: {c['accent_dim']}; }}
            QPushButton:disabled {{ background-color: {c['fg_disabled']}; color: #fff; }}
        """)
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
        c = get_colors()
        if role == "user":
            bubble_bg = c["accent"]
            bubble_fg = "#fff"
            align = "right"
            prefix = ''
            bubble_style = f'background-color:{bubble_bg};color:{bubble_fg};border-radius:12px;padding:8px 14px;'
        elif is_placeholder:
            bubble_bg = "transparent"
            bubble_fg = c["fg_hint"]
            align = "left"
            prefix = ''
            bubble_style = f'color:{bubble_fg};padding:4px 0;border-left:2px solid {c["accent"]};padding-left:12px;font-style:italic;'
        else:
            bubble_bg = "transparent"
            bubble_fg = c["fg_primary"]
            align = "left"
            prefix = ''
            bubble_style = f'color:{bubble_fg};padding:4px 0;border-left:2px solid {c["border"]};padding-left:12px;'
            text = _md_to_html(text)

        escaped = text.replace("\n", "<br>")
        margin_dir = "margin-left" if align == "right" else "margin-right"
        marker = "<!--ph-->" if is_placeholder else ""
        msg = (
            f'{marker}<div style="margin-bottom:12px;{margin_dir}:24px;">'
            f'<div style="display:inline-block;max-width:100%;'
            f'{bubble_style}font-size:13px;text-align:left;word-wrap:break-word;">'
            f'{escaped}'
            f'</div>'
            f'</div>'
        )
        current = self._chat_label.text()
        # Replace placeholder if real AI message arrives
        if role == "ai" and not is_placeholder:
            ph = "<!--ph-->"
            if ph in current:
                # Find and remove the placeholder block
                idx_ph = current.rfind(ph)
                # Find the end of this div block (next </div></div> pair)
                end_ph = current.find("</div></div>", idx_ph)
                if end_ph > 0:
                    # Find the closing </div> (there might be nested divs in placeholder)
                    # Simple: remove from <!--ph--> to next </div> after the block
                    nest_end = current.find("</div></div>", end_ph + 13)
                    if nest_end > 0:
                        current = current[:idx_ph] + current[nest_end + 13:]
                    else:
                        current = current[:idx_ph] + current[end_ph + 13:]
        self._chat_label.setText(current + msg)
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def append_message_ai(self, text: str) -> None:
        self.append_message("ai", text)
        self._on_response_done()

    def set_status(self, online: bool, thinking: bool = False) -> None:
        c = get_colors()
        if thinking:
            self._status_indicator.setStyleSheet(f"color: {c['yellow']}; font-size: 14px; border: none;")
            self._status_indicator.setToolTip(tr("ai.thinking"))
        elif online:
            self._status_indicator.setStyleSheet(f"color: {c['green']}; font-size: 14px; border: none;")
            self._status_indicator.setToolTip(tr("ai.online"))
        else:
            self._status_indicator.setStyleSheet(f"color: {c['fg_disabled']}; font-size: 14px; border: none;")
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
            f"QLabel {{ background-color: {c['chat_bg']}; color: {c['fg_primary']}; padding: 8px; font-size: 14px; }}"
        )

