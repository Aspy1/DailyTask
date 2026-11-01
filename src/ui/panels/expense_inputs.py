"""记账面板的两条输入行（支出 / 存钱）。

从 `expense_panel.py` 拆出（Q-A1 类/函数行数上限；也便于单独测试输入行布局）。
"""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.i18n.loader import tr
from src.ui.styles.theme import (
    LAYOUT,
    RADIUS,
    SIZE_BODY_S,
    get_colors,
    mark_accent_button,
    size_small_button,
)
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.rounded_input import RoundedComboBox, RoundedLineEdit


def build_add_row(categories: list[dict], input_qss: str, combo_qss: str,
                  band_qss: str, label_qss: str, on_add) -> tuple:
    """返回 (行控件, 金额输入, 分类下拉, 备注输入)。"""
    row = QWidget()
    row.setStyleSheet(band_qss)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(16, 4, 16, 4)
    layout.setSpacing(8)

    label = QLabel(tr("panel.expense.label_expense"))
    label.setFixedWidth(LAYOUT["input_width_md"])
    label.setStyleSheet(label_qss)
    layout.addWidget(label)

    amount = RoundedLineEdit()
    amount.setPlaceholderText(tr("expense.amount"))
    amount.setFixedWidth(LAYOUT["input_width_md"])
    amount.setStyleSheet(input_qss)
    layout.addWidget(amount)

    combo = RoundedComboBox()
    combo.setFixedWidth(LAYOUT["input_width_lg"])
    combo.setStyleSheet(combo_qss)
    for cat in categories:
        combo.addItem(cat.get("name", cat["id"]), cat["id"])
    layout.addWidget(combo)

    note = RoundedLineEdit()
    note.setPlaceholderText(tr("panel.expense.placeholder_note"))
    note.setStyleSheet(input_qss)
    layout.addWidget(note)

    button = RoundedButton(tr("panel.expense.btn_add"))
    size_small_button(button, 56)
    c = get_colors()
    button.setStyleSheet(f"""
        QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
            border-radius: {RADIUS['radius_md']}px; padding: 5px 12px; font-weight: 600;
            font-size: {SIZE_BODY_S}px; }}
        QPushButton:hover {{ background-color: {c['accent_hover']}; }}
    """)
    button.clicked.connect(on_add)
    mark_accent_button(button)
    layout.addWidget(button)
    return row, amount, combo, note


def build_savings_row(input_qss: str, band_qss: str, label_qss: str,
                      on_save) -> tuple:
    """返回 (行控件, 金额输入, 备注输入)。"""
    row = QWidget()
    row.setStyleSheet(band_qss)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(16, 4, 16, 4)
    layout.setSpacing(8)

    label = QLabel(tr("panel.expense.label_saving"))
    label.setFixedWidth(LAYOUT["input_width_md"])
    label.setStyleSheet(label_qss)
    layout.addWidget(label)

    amount = RoundedLineEdit()
    amount.setPlaceholderText(tr("panel.expense.placeholder_saving_amount"))
    amount.setFixedWidth(LAYOUT["input_width_md"])
    amount.setStyleSheet(input_qss)
    layout.addWidget(amount)

    note = RoundedLineEdit()
    note.setPlaceholderText(tr("panel.expense.placeholder_saving_note"))
    note.setStyleSheet(input_qss)
    layout.addWidget(note)

    button = RoundedButton(tr("panel.expense.btn_record_saving"))
    size_small_button(button, 70)
    c = get_colors()
    button.setStyleSheet(f"""
        QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
            border: 1px solid {c['border_strong']}; border-radius: {RADIUS['radius_md']}px;
            padding: 5px 12px; font-size: {SIZE_BODY_S}px; }}
        QPushButton:hover {{ background-color: {c['btn_secondary_hover']};
            color: {c['btn_secondary_hover_fg']}; }}
    """)
    button.clicked.connect(on_save)
    layout.addWidget(button)
    layout.addStretch()
    return row, amount, note
