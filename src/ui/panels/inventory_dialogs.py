"""「有什么」面板的两个对话框：改标签 / 设补货邮件提醒。

从 `inventory_panel.py` 抽出来 —— 那个文件超「单文件 ≤800」（`Q-A1`）、`InventoryPanel`
类也超 400 行。这两个对话框自成一体：只依赖传入的 `parent` / `dm` / `item`，不碰面板的
视图状态（分类筛选、分页、展开），所以是最干净的抽离点。

⚠ 行为与样式**照搬**，只换了落点（外加把 `__import__('PySide6.QtWidgets').QInputDialog`
换成正常 import）。样式里的 `border-radius: 4px` 是存量写法，未一并整改。
"""

from datetime import datetime, timedelta

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
)

from src.i18n.loader import tr
from src.ui.styles.theme import get_colors
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.rounded_input import RoundedLineEdit


def _tag_input_row(layout, tag_list) -> None:
    """「新标签」输入行 + 添加按钮（回车或点按钮都能加）。

    从 `edit_tags_dialog` 抽出来：那个函数原来 64 行，超「函数 ≤60」（`Q-A1`）。
    """
    add_row = QHBoxLayout()
    tag_input = RoundedLineEdit()
    tag_input.setPlaceholderText(tr("panel.inventory.placeholder_new_tag"))
    add_row.addWidget(tag_input)
    add_btn = RoundedButton(tr("panel.inventory.btn_add"))
    add_row.addWidget(add_btn)
    layout.addLayout(add_row)

    def add_tag() -> None:
        t = tag_input.text().strip()
        if t and not any(tag_list.item(i).text() == t for i in range(tag_list.count())):
            tag_list.addItem(t)
            tag_input.clear()

    add_btn.clicked.connect(add_tag)
    tag_input.returnPressed.connect(add_tag)


def edit_tags_dialog(parent, dm, item: dict) -> bool:
    """改标签。返回 `True` = 改过了（调用方负责发信号并刷新）。"""
    c = get_colors()
    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("panel.inventory.dialog_edit_tags_title", name=item.get('name', '')))
    dlg.setMinimumWidth(360)
    dlg.setStyleSheet(f"QDialog {{ background-color: {c['card_bg']}; }} QLabel {{ color: {c['fg_primary']}; font-size: 13px; background: transparent; border: none; }} QLineEdit {{ background-color: {c['bg_input']}; color: {c['fg_primary']}; border: 1px solid {c['border']}; padding: 6px 10px; font-size: 13px; }} QPushButton {{ background-color: {c['accent_bg']}; color: {c['fg_primary']}; border: none; border-radius: 4px; padding: 4px 12px; font-size: 12px; }} QPushButton:hover {{ background-color: {c['accent']}; color: {c['fg_on_fill']}; }}")
    layout = QVBoxLayout(dlg)
    layout.setSpacing(10)
    layout.setContentsMargins(20, 16, 20, 16)

    tag_list = QListWidget()
    tag_list.setStyleSheet(f"QListWidget {{ background-color: {c['bg_input']}; color: {c['fg_primary']}; border: 1px solid {c['border']}; border-radius: 4px; font-size: 13px; }}")
    for t in item.get("tags", []):
        tag_list.addItem(t)
    layout.addWidget(QLabel(tr("panel.inventory.label_current_tags")))
    layout.addWidget(tag_list)

    def edit_tag() -> None:
        """双击某一行改文字。"""
        row = tag_list.currentRow()
        if row >= 0:
            old = tag_list.item(row).text()
            new, ok = QInputDialog.getText(
                dlg, tr("panel.inventory.dialog_edit_tag_title"),
                tr("panel.inventory.label_tag_text"), text=old)
            if ok and new.strip():
                tag_list.item(row).setText(new.strip())

    tag_list.doubleClicked.connect(lambda _: edit_tag())
    _tag_input_row(layout, tag_list)

    del_btn = RoundedButton(tr("panel.inventory.btn_delete_selected"))
    del_btn.clicked.connect(lambda: tag_list.takeItem(tag_list.currentRow())
                            if tag_list.currentRow() >= 0 else None)
    layout.addWidget(del_btn)

    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    layout.addWidget(btns)

    if not dlg.exec():
        return False
    dm.inventory.update_item(item["id"], {
        "tags": [tag_list.item(i).text() for i in range(tag_list.count())]})
    dm.inventory.save()
    return True


def email_reminder_dialog(parent, dm, item: dict) -> None:
    """设补货邮件提醒：写进 `daily_logs` 的自定义提醒。

    ⚠ 行为照搬：确认框**取消时也会弹**（既有行为，本次未改）。
    """
    c = get_colors()
    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("panel.inventory.dialog_email_title", name=item.get('name', '')))
    dlg.setMinimumWidth(320)
    dlg.setStyleSheet(f"QDialog {{ background-color: {c['card_bg']}; }} QLabel {{ color: {c['fg_primary']}; font-size: 13px; }}")
    layout = QVBoxLayout(dlg)
    layout.setSpacing(12)
    layout.addWidget(QLabel(tr("panel.inventory.label_email_prompt", name=item.get('name', ''))))
    dt = QDateTimeEdit()
    dt.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    dt.setCalendarPopup(True)
    dt.setDateTime(datetime.now() + timedelta(days=3))
    dt.setDisplayFormat("yyyy-MM-dd HH:mm")
    layout.addWidget(dt)
    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    layout.addWidget(btns)
    if dlg.exec():
        dm.daily_logs.add_reminder("inventory", item.get("name", ""),
                                   datetime.now().strftime("%Y-%m-%d"),
                                   dt.dateTime().toPython().isoformat())
    dm.daily_logs.save()
    QMessageBox.information(parent, tr("panel.inventory.msg_reminder_set_title"),
                            tr("panel.inventory.msg_reminder_set"))
