"""Inventory panel — card list with filters, tags, right-click menu."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QFormLayout, QComboBox, QSpinBox, QCheckBox,
    QDialogButtonBox, QMessageBox, QMenu, QScrollArea, QSizePolicy,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE


class _ItemCard(QWidget):
    """Long card for one inventory item."""

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self._item = item
        c = get_colors()

        self.setMinimumHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        status = item.get("status", "充足")
        ignored = item.get("ignore_low_stock", False)
        if status == "需购":
            bg, accent = c["red"] + "10", c["red"]
        elif status == "不足" and not ignored:
            bg, accent = c["orange"] + "10", c["orange"]
        else:
            bg, accent = c["card_bg"], c["green"]

        self.setStyleSheet(f"""
            _ItemCard {{ background-color: {bg}; border-radius: 10px; }}
            _ItemCard:hover {{ background-color: {c['accent_bg']}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 12, 8)
        layout.setSpacing(10)

        # Name + tags
        info = QVBoxLayout()
        info.setSpacing(3)
        name = QLabel(item.get("name", ""))
        name.setStyleSheet(f"color: {c['fg_primary']}; font-size: 14px; font-weight: 600; border: none; background: transparent;")
        info.addWidget(name)

        # Tags row
        tags = item.get("tags", [])
        if tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(4)
            for tag in tags:
                t = QLabel(tag)
                t.setStyleSheet(f"color: {c['accent']}; font-size: 10px; font-weight: 500; background: {c['accent']}18; border-radius: 8px; padding: 1px 8px; border: none;")
                tag_row.addWidget(t)
            tag_row.addStretch()
            info.addLayout(tag_row)

        layout.addLayout(info, stretch=1)

        # Right side: qty + category
        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignmentFlag.AlignRight)

        qty_unit = f"{item.get('quantity',0)}{item.get('unit','个')}"
        qty_lbl = QLabel(qty_unit)
        qty_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        qty_lbl.setStyleSheet(f"color: {accent}; font-size: 13px; font-weight: 600; border: none; background: transparent;")
        right.addWidget(qty_lbl)

        cat = item.get("category", "")
        if cat:
            cat_lbl = QLabel(cat)
            cat_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            cat_lbl.setStyleSheet(f"color: {c['fg_hint']}; font-size: 11px; border: none; background: transparent;")
            right.addWidget(cat_lbl)

        if ignored:
            ign = QLabel("已忽略")
            ign.setAlignment(Qt.AlignmentFlag.AlignRight)
            ign.setStyleSheet(f"color: {c['fg_disabled']}; font-size: 10px; border: none; background: transparent;")
            right.addWidget(ign)

        layout.addLayout(right)


class InventoryPanel(QWidget):
    def __init__(self, dm: DataManager, parent=None):
        super().__init__(parent)
        self._dm = dm
        self._cat_filter = "全部"
        self._tag_filter = ""
        c = get_colors()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bar.setObjectName("taskBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(6)

        title = QLabel("有什么")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bl.addWidget(title)

        # Category filter
        self._cat_combo = QComboBox()
        self._cat_combo.setMinimumWidth(90)
        self._cat_combo.setStyleSheet(f"""
            QComboBox {{ background: transparent; color: {c['fg_secondary']}; border: none; padding: 3px 10px; font-size: 12px; }}
        """)
        self._cat_combo.currentTextChanged.connect(self._on_filter_changed)
        bl.addWidget(self._cat_combo)

        # Tag filter
        self._tag_combo = QComboBox()
        self._tag_combo.setMinimumWidth(80)
        self._tag_combo.setStyleSheet(f"""
            QComboBox {{ background: transparent; color: {c['fg_secondary']}; border: none; padding: 3px 10px; font-size: 12px; }}
        """)
        self._tag_combo.currentTextChanged.connect(self._on_filter_changed)
        bl.addWidget(self._tag_combo)

        bl.addStretch()

        add_btn = QPushButton("添加")
        add_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: #fff; border: none;
                border-radius: 8px; padding: 5px 16px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        add_btn.clicked.connect(lambda: self._edit_item())
        bl.addWidget(add_btn)

        bl.addSpacing(4)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(self._btn_qss())
        refresh_btn.clicked.connect(self._refresh)
        bl.addWidget(refresh_btn)

        layout.addWidget(bar)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._container = QWidget()
        self._card_layout = QVBoxLayout(self._container)
        self._card_layout.setContentsMargins(16, 8, 16, 16)
        self._card_layout.setSpacing(6)
        self._card_layout.addStretch()
        scroll.setWidget(self._container)
        layout.addWidget(scroll, stretch=1)

        self._refresh()

    def _btn_qss(self) -> str:
        c = get_colors()
        return f"QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['fg_hint']}; border-radius: 8px; padding: 4px 12px; font-size: 13px; }} QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['fg_secondary']}; }} QPushButton::menu-indicator {{ image: none; }}"

    def _show_cat_filter(self) -> None:
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }} QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }} QMenu::item:selected {{ background-color: {c['accent_bg']}; }}")
        menu.addAction("全部分类").triggered.connect(lambda: self._apply_cat_filter("全部"))
        menu.addSeparator()
        cats = sorted(set(it.get("category", "") for it in self._dm.inventory.items if it.get("category")))
        for cat in cats:
            menu.addAction(cat).triggered.connect(lambda checked, c2=cat: self._apply_cat_filter(c2))
        menu.exec(self._cat_btn.mapToGlobal(self._cat_btn.rect().bottomLeft()))

    def _show_tag_filter(self) -> None:
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }} QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }} QMenu::item:selected {{ background-color: {c['accent_bg']}; }}")
        menu.addAction("全部标签").triggered.connect(lambda: self._apply_tag_filter(""))
        menu.addSeparator()
        for tag in self._dm.inventory.all_tags:
            menu.addAction(tag).triggered.connect(lambda checked, t=tag: self._apply_tag_filter(t))
        menu.exec(self._tag_btn.mapToGlobal(self._tag_btn.rect().bottomLeft()))

    def _apply_cat_filter(self, cat: str) -> None:
        self._cat_filter = cat
        self._cat_btn.setText(cat if cat != "全部" else "全部分类")
        self._refresh()

    def _apply_tag_filter(self, tag: str) -> None:
        self._tag_filter = tag
        self._tag_btn.setText(tag if tag else "全部标签")
        self._refresh()

    def _refresh(self) -> None:
        while self._card_layout.count() > 1:
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cat = self._cat_filter
        tag = self._tag_filter
        items = self._dm.inventory.items

        if cat != "全部":
            items = [it for it in items if it.get("category") == cat]
        if tag != "全部标签":
            items = [it for it in items if tag in it.get("tags", [])]

        items = sorted(items, key=lambda x: (
            0 if x.get("status") == "需购" else 1 if x.get("status") == "不足" else 2,
            x.get("name", "")))

        for it in items:
            card = _ItemCard(it)
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda pos, i=it: self._context_menu(pos, i))
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _context_menu(self, pos, item: dict) -> None:
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        """)

        menu.addAction("编辑").triggered.connect(lambda: self._edit_item(item))

        # Status toggle
        status = item.get("status", "")
        if status != "需购":
            menu.addAction("标记需购").triggered.connect(
                lambda: self._quick_update(item["id"], {"status": "需购"}))
        if status != "充足":
            menu.addAction("标记充足").triggered.connect(
                lambda: self._quick_update(item["id"], {"status": "充足"}))

        # Ignore low-stock
        ignored = item.get("ignore_low_stock", False)
        if ignored:
            menu.addAction("恢复库存提醒").triggered.connect(
                lambda: self._quick_update(item["id"], {"ignore_low_stock": False}))
        else:
            menu.addAction("忽略库存不足提醒").triggered.connect(
                lambda: self._quick_update(item["id"], {"ignore_low_stock": True}))

        menu.addSeparator()
        menu.addAction("📧 设置邮件提醒").triggered.connect(
            lambda: self._email_reminder(item))
        menu.addAction("删除").triggered.connect(
            lambda: self._delete_item(item["id"]))
        menu.exec(self.mapToGlobal(pos))

    def _edit_item(self, item: dict | None = None) -> None:
        dlg = ItemDialog(item, self._dm, self)
        if dlg.exec():
            data = dlg.result_data
            if item:
                self._dm.inventory.update_item(item["id"], data)
            else:
                self._dm.inventory.add_item(data)
            self._dm.inventory.save()
            self._dm.data_changed.emit("inventory")
            self._refresh()

    def _quick_update(self, iid: str, data: dict) -> None:
        self._dm.inventory.update_item(iid, data)
        self._dm.inventory.save()
        self._dm.data_changed.emit("inventory")
        self._refresh()

    def _delete_item(self, iid: str) -> None:
        name = iid
        for it in self._dm.inventory.items:
            if it["id"] == iid:
                name = it.get("name", iid)
                break
        if QMessageBox.question(self, "确认", f"删除「{name}」？") == QMessageBox.StandardButton.Yes:
            self._dm.inventory.delete_item(iid)
            self._dm.inventory.save()
            self._dm.data_changed.emit("inventory")
            self._refresh()

    def _email_reminder(self, item: dict) -> None:
        # Open a simple time picker to set email reminder for this item
        from PySide6.QtWidgets import QDateTimeEdit
        from PySide6.QtCore import QLocale
        from datetime import datetime, timedelta
        c = get_colors()
        dlg = QDialog(self)
        dlg.setWindowTitle(f"邮件提醒 - {item.get('name','')}")
        dlg.setMinimumWidth(320)
        dlg.setStyleSheet(f"""
            QDialog {{ background-color: {c['card_bg']}; }}
            QLabel {{ color: {c['fg_primary']}; font-size: 13px; }}
            QDateTimeEdit {{ background-color: {c['bg_input']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 6px 10px; font-size: 13px; }}
        """)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.addWidget(QLabel(f"为「{item.get('name','')}」设置补货提醒"))
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
            notify_time = dt.dateTime().toPython().isoformat()
            self._dm.daily_logs.add_reminder(
                "inventory", item.get("name", ""),
                datetime.now().strftime("%Y-%m-%d"), notify_time)
            self._dm.daily_logs.save()
            QMessageBox.information(self, "已设置", f"将在 {notify_time[:16]} 提醒补货")

    def refresh_theme(self) -> None:
        self._refresh()


class ItemDialog(QDialog):
    def __init__(self, item: dict | None, dm: DataManager, parent=None):
        super().__init__(parent)
        self._dm = dm
        c = get_colors()
        editing = item is not None
        self.setWindowTitle("编辑物品" if editing else "添加物品")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_card']}; color: {c['fg_primary']}; }}
            QLabel {{ color: {c['fg_primary']}; background: transparent; border: none; }}
            QLineEdit, QComboBox, QSpinBox {{
                background-color: {c['bg_input']}; color: {c['fg_primary']};
                border: 1px solid {c['border']}; padding: 6px 10px; font-size: 13px;
            }}
            QCheckBox {{ color: {c['fg_primary']}; spacing: 4px; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 16)
        form = QFormLayout()
        form.setSpacing(10)

        self._name = QLineEdit(item.get("name", "") if item else "")
        self._name.setPlaceholderText("如：洗发水")
        form.addRow("名称:", self._name)

        self._category = QComboBox()
        self._category.setEditable(True)
        cats = ["日用品", "食品饮料", "学习用品", "数码电子", "衣物", "药品", "其他"]
        self._category.addItems(cats)
        if item:
            cat = item.get("category", "其他")
            idx = cats.index(cat) if cat in cats else 0
            self._category.setCurrentIndex(idx)
        form.addRow("分类:", self._category)

        qty_row = QHBoxLayout()
        self._quantity = QSpinBox()
        self._quantity.setRange(0, 999)
        self._quantity.setValue(item.get("quantity", 1) if item else 1)
        qty_row.addWidget(self._quantity)
        self._unit = QComboBox()
        self._unit.setEditable(True)
        self._unit.addItems(["个", "瓶", "包", "盒", "箱", "袋", "双", "件", "卷", "支"])
        if item:
            unit = item.get("unit", "个")
            idx = self._unit.findText(unit)
            if idx >= 0:
                self._unit.setCurrentIndex(idx)
            else:
                self._unit.setCurrentText(unit)
        qty_row.addWidget(self._unit)
        qty_row.addStretch()
        form.addRow("数量:", qty_row)

        self._min_qty = QSpinBox()
        self._min_qty.setRange(0, 99)
        self._min_qty.setValue(item.get("min_quantity", 1) if item else 1)
        form.addRow("最低库存:", self._min_qty)

        self._location = QLineEdit(item.get("location", "") if item else "")
        self._location.setPlaceholderText("如：卫生间柜子")
        form.addRow("位置:", self._location)

        self._tags = QLineEdit(
            ",".join(item.get("tags", [])) if item else "")
        self._tags.setPlaceholderText("逗号分隔，如：超市优惠,618")
        form.addRow("标签:", self._tags)

        self._notes = QLineEdit(item.get("notes", "") if item else "")
        self._notes.setPlaceholderText("备注...")
        form.addRow("备注:", self._notes)

        self._ignore = QCheckBox("忽略库存不足提醒")
        self._ignore.setChecked(item.get("ignore_low_stock", False) if item else False)
        form.addRow("", self._ignore)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _ok(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "错误", "请输入物品名称。")
            return
        qty = self._quantity.value()
        min_q = self._min_qty.value()
        tags = [t.strip() for t in self._tags.text().split(",") if t.strip()]
        status = "需购" if qty <= 0 else ("不足" if qty < min_q else "充足")
        self.result_data = {
            "name": self._name.text().strip(),
            "category": self._category.currentText(),
            "quantity": qty, "unit": self._unit.currentText(),
            "min_quantity": min_q, "status": status,
            "location": self._location.text().strip(),
            "tags": tags, "notes": self._notes.text().strip(),
            "ignore_low_stock": self._ignore.isChecked(),
        }
        self.accept()
