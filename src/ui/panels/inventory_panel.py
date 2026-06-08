"""Inventory panel — item cards with working QSS (#id selectors)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QFormLayout, QComboBox, QSpinBox, QCheckBox,
    QDialogButtonBox, QMessageBox, QMenu, QScrollArea, QSizePolicy,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE


class ItemCard(QWidget):
    """Card using #objectName selector — verified working on Windows."""

    _counter = 0

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self._item = item
        c = get_colors()

        ItemCard._counter += 1
        oid = f"ic_{ItemCard._counter}"
        self.setObjectName(oid)

        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        status = item.get("status", "充足")
        if status == "需购":
            bg = c["red"] + "10"
        elif status == "不足":
            bg = c["orange"] + "10"
        else:
            bg = c["bg_elevated"]

        self.setStyleSheet(f"#{oid} {{ background-color: {bg}; border-radius: 8px; }} #{oid}:hover {{ background-color: {c['accent_bg']}; }}")

        main = QVBoxLayout(self)
        main.setContentsMargins(16, 10, 16, 10)
        main.setSpacing(4)

        # Row 1: name + qty + badge
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        name = QLabel(item.get("name", ""))
        name.setStyleSheet(f"color: {c['fg_primary']}; font-size: 14px; font-weight: 600; border: none; background: transparent;")
        hdr.addWidget(name)
        hdr.addStretch()
        qty = QLabel(f"x{item.get('quantity',0)}")
        qty.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        hdr.addWidget(qty)

        badge_color = {"需购": c["red"], "不足": c["orange"], "充足": c["green"]}.get(status, c["green"])
        badge = QLabel({"需购": "需购", "不足": "不足", "充足": "充足"}.get(status, status))
        badge.setFixedWidth(42)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"color: {badge_color}; font-size: 11px; font-weight: 600; background: {badge_color}18; border-radius: 10px; padding: 2px 0; border: none;")
        hdr.addWidget(badge)
        main.addLayout(hdr)

        # Row 2: category / location / notes
        parts = []
        for k in ["category", "location", "notes"]:
            v = item.get(k, "")
            if v:
                parts.append(v)
        if parts:
            detail = QLabel(" · ".join(parts))
            detail.setWordWrap(True)
            detail.setStyleSheet(f"color: {c['fg_hint']}; font-size: 12px; border: none; background: transparent;")
            main.addWidget(detail)

        # Row 3: tags
        tags = item.get("tags", [])
        if tags:
            tr = QHBoxLayout()
            tr.setSpacing(4)
            for tag in tags:
                t = QLabel(tag)
                t.setStyleSheet(f"color: {c['accent']}; font-size: 10px; font-weight: 500; background: {c['accent']}18; border-radius: 8px; padding: 1px 8px; border: none;")
                tr.addWidget(t)
            tr.addStretch()
            main.addLayout(tr)


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

        bar = QWidget()
        bar.setObjectName("taskBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(6)
        title = QLabel("有什么")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bl.addWidget(title)

        self._cat_btn = QPushButton("全部分类")
        self._cat_btn.setStyleSheet(self._btn_qss())
        self._cat_btn.clicked.connect(self._show_cat_filter)
        bl.addWidget(self._cat_btn)

        self._tag_btn = QPushButton("全部标签")
        self._tag_btn.setStyleSheet(self._btn_qss())
        self._tag_btn.clicked.connect(self._show_tag_filter)
        bl.addWidget(self._tag_btn)

        bl.addStretch()

        add_btn = QPushButton("添加")
        add_btn.setObjectName("invAddBtn")
        add_btn.setStyleSheet(f"#invAddBtn {{ background-color: {c['accent']}; color: #fff; border: none; border-radius: 8px; padding: 5px 16px; font-size: 13px; font-weight: 600; }} #invAddBtn:hover {{ background-color: {c['accent_hover']}; }}")
        add_btn.clicked.connect(lambda: self._edit_item())
        bl.addWidget(add_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(self._btn_qss())
        refresh_btn.clicked.connect(self._refresh)
        bl.addWidget(refresh_btn)
        layout.addWidget(bar)

        scroll = QScrollArea()
        scroll.setObjectName("invScroll")
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("#invScroll { background: transparent; border: none; }")
        self._container = QWidget()
        self._card_layout = QVBoxLayout(self._container)
        self._card_layout.setContentsMargins(16, 8, 16, 16)
        self._card_layout.setSpacing(8)
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
        menu.setObjectName("invMenu")
        menu.setStyleSheet(f"#invMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }} #invMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }} #invMenu::item:selected {{ background-color: {c['accent_bg']}; }}")
        menu.addAction("全部分类").triggered.connect(lambda: self._apply_cat_filter("全部"))
        menu.addSeparator()
        cats = sorted(set(it.get("category", "") for it in self._dm.inventory.items if it.get("category")))
        for cat in cats:
            menu.addAction(cat).triggered.connect(lambda checked, c2=cat: self._apply_cat_filter(c2))
        menu.exec(self._cat_btn.mapToGlobal(self._cat_btn.rect().bottomLeft()))

    def _show_tag_filter(self) -> None:
        c = get_colors()
        menu = QMenu(self)
        menu.setObjectName("invMenu2")
        menu.setStyleSheet(f"#invMenu2 {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }} #invMenu2::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }} #invMenu2::item:selected {{ background-color: {c['accent_bg']}; }}")
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
            it = self._card_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        ItemCard._counter = 0
        items = self._dm.inventory.items
        if self._cat_filter != "全部":
            items = [i for i in items if i.get("category") == self._cat_filter]
        tag = self._tag_filter
        if tag:
            items = [i for i in items if tag in i.get("tags", [])]

        items = sorted(items, key=lambda x: (0 if x.get("status") == "需购" else 1 if x.get("status") == "不足" else 2, x.get("name", "")))

        for it in items:
            card = ItemCard(it)
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda pos, i=it: self._context_menu(pos, i))
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _context_menu(self, pos, item: dict) -> None:
        c = get_colors()
        menu = QMenu(self)
        menu.setObjectName("ctxMenu")
        menu.setStyleSheet(f"#ctxMenu {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']}; border-radius: 8px; padding: 4px; }} #ctxMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }} #ctxMenu::item:selected {{ background-color: {c['accent_bg']}; }}")
        menu.addAction("编辑").triggered.connect(lambda: self._edit_item(item))
        st = item.get("status", "")
        if st != "需购":
            menu.addAction("标记需购").triggered.connect(lambda: self._quick_update(item["id"], {"status": "需购"}))
        if st != "充足":
            menu.addAction("标记充足").triggered.connect(lambda: self._quick_update(item["id"], {"status": "充足"}))
        ig = item.get("ignore_low_stock", False)
        menu.addAction("恢复库存提醒" if ig else "忽略库存不足提醒").triggered.connect(lambda: self._quick_update(item["id"], {"ignore_low_stock": not ig}))
        menu.addSeparator()
        menu.addAction("设置邮件提醒").triggered.connect(lambda: self._email_reminder(item))
        menu.addAction("删除").triggered.connect(lambda: self._delete_item(item["id"]))
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
                name = it.get("name", iid); break
        if QMessageBox.question(self, "确认", f"删除「{name}」？") == QMessageBox.StandardButton.Yes:
            self._dm.inventory.delete_item(iid)
            self._dm.inventory.save()
            self._dm.data_changed.emit("inventory")
            self._refresh()

    def _email_reminder(self, item: dict) -> None:
        from PySide6.QtWidgets import QDateTimeEdit
        from PySide6.QtCore import QLocale
        from datetime import datetime, timedelta
        c = get_colors()
        dlg = QDialog(self)
        dlg.setObjectName("reminderDlg")
        dlg.setWindowTitle(f"邮件提醒 - {item.get('name','')}")
        dlg.setMinimumWidth(320)
        dlg.setStyleSheet(f"#reminderDlg {{ background-color: {c['card_bg']}; }} QLabel {{ color: {c['fg_primary']}; font-size: 13px; border: none; background: transparent; }}")
        layout = QVBoxLayout(dlg); layout.setSpacing(12)
        layout.addWidget(QLabel(f"为「{item.get('name','')}」设置补货提醒"))
        dt = QDateTimeEdit()
        dt.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        dt.setCalendarPopup(True); dt.setDateTime(datetime.now() + timedelta(days=3))
        dt.setDisplayFormat("yyyy-MM-dd HH:mm"); layout.addWidget(dt)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); layout.addWidget(btns)
        if dlg.exec():
            self._dm.daily_logs.add_reminder("inventory", item.get("name", ""), datetime.now().strftime("%Y-%m-%d"), dt.dateTime().toPython().isoformat())
            self._dm.daily_logs.save()
            QMessageBox.information(self, "已设置", f"将在提醒补货")

    def refresh_theme(self) -> None:
        self._refresh()


class ItemDialog(QDialog):
    def __init__(self, item: dict | None, dm: DataManager, parent=None):
        super().__init__(parent); self._dm = dm; c = get_colors()
        self.setObjectName("itemDlg")
        self.setWindowTitle("编辑物品" if item else "添加物品"); self.setMinimumWidth(400)
        self.setStyleSheet(f"#itemDlg {{ background-color: {c['bg_card']}; color: {c['fg_primary']}; }} QLabel {{ color: {c['fg_primary']}; background: transparent; border: none; }} QLineEdit, QComboBox, QSpinBox {{ background-color: {c['bg_input']}; color: {c['fg_primary']}; border: 1px solid {c['border']}; padding: 6px 10px; font-size: 13px; }} QCheckBox {{ color: {c['fg_primary']}; spacing: 4px; }}")
        layout = QVBoxLayout(self); layout.setSpacing(12); layout.setContentsMargins(24, 20, 24, 16)
        form = QFormLayout(); form.setSpacing(10)
        self._name = QLineEdit(item.get("name", "") if item else ""); self._name.setPlaceholderText("如：洗发水")
        form.addRow("名称:", self._name)
        self._category = QComboBox(); self._category.setEditable(True)
        cats = ["日用品","食品饮料","学习用品","数码电子","衣物","药品","其他"]
        self._category.addItems(cats)
        if item: self._category.setCurrentIndex(cats.index(item.get("category","其他")) if item.get("category","其他") in cats else 0)
        form.addRow("分类:", self._category)
        self._quantity = QSpinBox(); self._quantity.setRange(0, 999); self._quantity.setValue(item.get("quantity",1) if item else 1)
        form.addRow("数量 (件):", self._quantity)
        self._min_qty = QSpinBox(); self._min_qty.setRange(0, 99); self._min_qty.setValue(item.get("min_quantity",1) if item else 1)
        form.addRow("最低库存:", self._min_qty)
        self._location = QLineEdit(item.get("location","") if item else ""); self._location.setPlaceholderText("如：卫生间柜子")
        form.addRow("位置:", self._location)
        self._tags = QLineEdit(",".join(item.get("tags",[])) if item else ""); self._tags.setPlaceholderText("逗号分隔")
        form.addRow("标签:", self._tags)
        self._notes = QLineEdit(item.get("notes","") if item else ""); self._notes.setPlaceholderText("备注...")
        form.addRow("备注:", self._notes)
        self._ignore = QCheckBox("忽略库存不足提醒"); self._ignore.setChecked(item.get("ignore_low_stock",False) if item else False)
        form.addRow("", self._ignore)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject); layout.addWidget(btns)

    def _ok(self) -> None:
        if not self._name.text().strip(): QMessageBox.warning(self, "错误", "请输入物品名称。"); return
        qty = self._quantity.value(); min_q = self._min_qty.value()
        tags = [t.strip() for t in self._tags.text().split(",") if t.strip()]
        status = "需购" if qty <= 0 else ("不足" if qty < min_q else "充足")
        self.result_data = {"name": self._name.text().strip(), "category": self._category.currentText(),
            "quantity": qty, "unit": "件", "min_quantity": min_q, "status": status,
            "location": self._location.text().strip(), "tags": tags,
            "notes": self._notes.text().strip(), "ignore_low_stock": self._ignore.isChecked()}
        self.accept()
