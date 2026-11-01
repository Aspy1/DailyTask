"""统一的空态卡片：标题 + 一句说明 + 可选主操作。

现代界面的空页面不该只留一大片空白：要告诉用户"这里是什么 / 为什么空 / 下一步点哪"。
从「近期安排 / 考试」开始统一（2026-11-01 截图审查）。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.ui.styles.cards import card
from src.ui.styles.theme import (
    LAYOUT,
    SIZE_BODY_S,
    SIZE_SUBTITLE,
    SPACING,
    font,
    get_colors,
    mark_accent_button,
    size_small_button,
)
from src.ui.widgets.rounded_button import RoundedButton


def empty_state(title: str, body: str, action_text: str = "",
                on_action=None, parent=None) -> QWidget:
    """返回一张居中空态卡片（可直接 `addWidget`）。"""
    colors = get_colors()
    box = card("item", pad="spacing_lg", bg="bg_card", parent=parent)
    # 固定一个舒适阅读宽度：只给 maxWidth 时 QLabel 会按 sizeHint 缩到 250px 左右，
    # 换行后的高度没被布局算进去 → 文字被裁/重叠（2026-11-01 截图实测）。
    box.setMinimumWidth(LAYOUT["dialog_width_lg"])
    box.setMaximumWidth(LAYOUT["dialog_width_xxl"])
    layout = QVBoxLayout(box)
    margin = SPACING["spacing_lg"]
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(8)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    title_label = QLabel(title)
    title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_label.setFont(font(SIZE_SUBTITLE, weight=600))
    title_label.setStyleSheet(f"color: {colors['fg_primary']};")
    layout.addWidget(title_label)

    body_label = QLabel(body)
    body_label.setWordWrap(True)
    body_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    body_label.setFixedWidth(
        LAYOUT["dialog_width_lg"] - 2 * SPACING["spacing_lg"])
    body_label.setStyleSheet(
        f"color: {colors['fg_hint']}; font-size: {SIZE_BODY_S}px;")
    layout.addWidget(body_label)

    if action_text:
        action = RoundedButton(action_text)
        mark_accent_button(action)
        size_small_button(action)
        if on_action is not None:
            # 不用 clicked(bool) 直接连：像 `_add_exam(exam=None)` 会把 bool 当参数
            action.clicked.connect(lambda: on_action())
        layout.addWidget(action, alignment=Qt.AlignmentFlag.AlignCenter)
    return box
