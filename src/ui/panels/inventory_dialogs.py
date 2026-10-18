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
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
)

from src.i18n.loader import tr
from src.models.inventory import days_until
from src.ui.styles.theme import RADIUS, get_colors
from src.ui.widgets.dialog_shell import DialogShell, action_row, form_row
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
    """改标签。返回 `True` = 改过了（调用方负责发信号并刷新）。

    走 `DialogShell`（审查 U9）：限高 + 中间滚动 + 底部按钮固定。
    """
    dlg = DialogShell(parent, tr("panel.inventory.dialog_edit_tags_title",
                                 name=item.get('name', '')))
    layout = dlg.body
    c = get_colors()

    tag_list = QListWidget()
    for t in item.get("tags", []):
        tag_list.addItem(t)
    # 每项给一层**统一的淡底**并把行距收紧：全局 `QListWidget::item` 是 8px 12px 内边距、
    # 没有底色 → 三项之间又高又分不清（2026-10-18 用户看渲染图反馈）
    tag_list.setStyleSheet(
        f"QListWidget::item {{ background-color: {c['item_bg']};"
        f" border-radius: {RADIUS['radius_sm']}px; padding: 2px 10px; margin: 2px 0; }}"
        f" QListWidget::item:selected {{ background-color: {c['accent_bg']}; }}")
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
    layout.addStretch()

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
    layout.addWidget(action_row(tr("widget.dialog.btn_confirm"), dlg.accept,
                                on_cancel=dlg.reject))
    if not dlg.exec():
        return                       # 取消 → 什么都不写，也**不报成功**（审查 F4 / P2）
    dm.daily_logs.add_reminder("inventory", item.get("name", ""),
                               datetime.now().strftime("%Y-%m-%d"),
                               dt.dateTime().toPython().isoformat())
    if not dm.daily_logs.save():
        # 保存被拒（磁盘被别人改过）→ 同样不许报成功
        QMessageBox.warning(parent, tr("panel.inventory.msg_reminder_failed_title"),
                            tr("panel.inventory.msg_reminder_failed"))
        return
    QMessageBox.information(parent, tr("panel.inventory.msg_reminder_set_title"),
                            tr("panel.inventory.msg_reminder_set"))


def _labeled_field(layout, label_key: str, initial: str, hint: str = "") -> RoundedLineEdit:
    """"标签 + 输入框"一行（行工厂见 `dialog_shell.form_row`，`Q-H9`）。

    ⚠ 原来这里是"标签在**上**、输入框在下"，与其它弹窗的"标签在左"不是一套东西；
    现在统一走工厂。
    """
    edit = RoundedLineEdit()
    edit.setText(initial)
    if hint:
        edit.setPlaceholderText(hint)
    layout.addWidget(form_row(tr(label_key), edit))
    return edit


def _membership_from_form(user, expires, auto, months) -> dict:
    """把会员弹窗里的输入收成 `membership` 字典（空字段就不写）。"""
    membership: dict = {}
    if user.text().strip():
        membership["username"] = user.text().strip()
    if expires.text().strip():
        membership["expires_on"] = expires.text().strip()
    if auto.isChecked():
        membership["auto_renew"] = True
    if months.text().strip().isdigit():
        membership["renew_months"] = int(months.text().strip())
    return membership


def edit_membership_dialog(parent, dm, item: dict) -> bool:
    """编辑会员信息（虚拟品类）。返回 `True` = 改过了。

    ⚠ **手机号只在这里录**：它写进 `dm.membership_contacts`（私有文件 —— 不进仓库、
    不进 AI 提示词）。用户名 / 到期日 / 自动续费 / 续费月数写进 `inventory.json`。

    走 `DialogShell`（审查 U9）：限高 + 中间滚动 + 底部按钮固定。
    """
    m = item.get("membership") or {}
    dlg = DialogShell(parent, tr("panel.inventory.dialog_membership_title",
                                 name=item.get("name", "")))
    layout = dlg.body

    user = _labeled_field(layout, "panel.inventory.membership_username",
                          str(m.get("username") or ""))
    expires = _labeled_field(layout, "panel.inventory.membership_expires_label",
                             str(m.get("expires_on") or ""),
                             tr("panel.inventory.membership_date_hint"))
    auto = QCheckBox(tr("panel.inventory.membership_auto_renew_label"))
    auto.setChecked(bool(m.get("auto_renew")))
    layout.addWidget(auto)
    months = _labeled_field(layout, "panel.inventory.membership_renew_months",
                            str(m.get("renew_months") or ""), "12")
    phone = _labeled_field(layout, "panel.inventory.membership_phone",
                           dm.membership_contacts.phone_of(item["id"]))
    hint = QLabel(tr("panel.inventory.membership_phone_hint"))
    hint.setWordWrap(True)
    layout.addWidget(hint)
    layout.addStretch()

    if not dlg.exec():
        return False
    date_text = expires.text().strip()
    if date_text and days_until(date_text) is None:
        # 日期写错就别写进去 —— 解析不了的到期日会**静默**不参与状态（更难查）
        QMessageBox.warning(parent,
                            tr("panel.inventory.dialog_membership_title",
                               name=item.get("name", "")),
                            tr("panel.inventory.membership_bad_date"))
        return False
    membership = _membership_from_form(user, expires, auto, months)
    dm.inventory.update_item(item["id"], {"membership": membership})
    dm.inventory.save()
    dm.membership_contacts.set_phone(item["id"], phone.text())
    dm.membership_contacts.save()
    return True
