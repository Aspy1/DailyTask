"""「近期安排」的新增 / 编辑弹窗。

只收两样东西：**做什么**（标题）和**备注**（买什么 / 背到哪一课）。
排序不走弹窗（在面板上拖动），所以这里故意没有"序号"字段。
"""

from PySide6.QtWidgets import QWidget

from src.i18n.loader import tr
from src.ui.styles.theme import FIELD_H
from src.ui.widgets.dialog_shell import DialogShell, form_row
from src.ui.widgets.rounded_input import RoundedLineEdit


def ask_routine(parent: QWidget, item: dict | None = None) -> tuple[str, str] | None:
    """弹窗收集 `(标题, 备注)`；取消或标题为空 → `None`。"""
    title_key = ("panel.routine.dialog_title_edit" if item
                 else "panel.routine.dialog_title_add")
    dlg = DialogShell(parent, tr(title_key), min_width=380)
    title = RoundedLineEdit(item.get("title", "") if item else "")
    title.setPlaceholderText(tr("panel.routine.placeholder_title"))
    note = RoundedLineEdit(item.get("note", "") if item else "")
    note.setPlaceholderText(tr("panel.routine.placeholder_note"))
    for field in (title, note):
        field.setFixedHeight(FIELD_H)
    dlg.body.addWidget(form_row(tr("panel.routine.label_title"), title))
    dlg.body.addWidget(form_row(tr("panel.routine.label_note"), note))
    dlg.body.addStretch()
    title.setFocus()
    if not dlg.exec():
        return None
    text = title.text().strip()
    if not text:
        return None
    return text, note.text().strip()
