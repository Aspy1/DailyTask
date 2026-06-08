"""Inventory panel — item list with status badges."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QFormLayout, QComboBox, QSpinBox,
    QDialogButtonBox, QMessageBox, QMenu, QScrollArea, QSizePolicy,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE


class _ItemCard(QWidget):
    """Card for one inventory item."""

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self._item = item
        c = get_colors()

        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        status = item.get("status", "充足")
        if status == "需购":
            bg = c["red"] + "10"
            accent = c["red"]
            status_text = "需购"
        elif status == "不足":
            bg = c["orange"] + "10"
            accent = c["orange"]
            status_text = "不足"
        else:
            bg = c["card_bg"]
            accent = c["green"]
            status_text = "充足"

        self.setStyleSheet(f"""
            _ItemCard {{ background-color: {bg}; border-radius: 10px; }}
            _ItemCard:hover {{ background-color: {c['accent_bg']}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # Left: name + details
        info = QVBoxLayout()
        info.setSpacing(3)

        name_lbl = QLabel(item.get("name", ""))
        name_lbl.setStyleSheet(f"color: {c['fg_primary']}; font-size: 15px; font-weight: 600; border: none; background: transparent;")
        info.addWidget(name_lbl)

        qty = item.get("quantity", 0)
        unit = item.get("unit", "个")
        min_q = item.get("min_quantity", 1)
        cat = item.get("category", "")
        loc = item.get("location", "")
        detail_parts = [f"{qty}{unit}"]
        if min_q > 1:
            detail_parts.append(f"最低{min_q}")
        if cat:
            detail_parts.append(cat)
        if loc:
            detail_parts.append(loc)
        detail = QLabel(" · ".join(detail_parts))
        detail.setStyleSheet(f"color: {c['fg_hint']}; font-size: 12px; border: none; background: transparent;")
        info.addWidget(detail)

        layout.addLayout(info, stretch=1)

        # Right: status badge
        badge = QLabel(status_text)
        badge.setFixedSize(48, 26)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"""
            color: {accent}; font-size: 11px; font-weight: 600;
            background: {accent}20; border-radius: 13px; border: none;
        """)
        layout.addWidget(badge)


class InventoryPanel(QWidget):
    def __init__(self, dm: DataManager, parent=None):
        super().__init__(parent)
        self._dm = dm
        c = get_colors()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bar.setObjectName("taskBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(8)

        title = QLabel("有什么")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bl.addWidget(title)

        # Quick stats
        need = len(self._dm.inventory.need_restock)
        total = len(self._dm.inventory.items)
        self._stats = QLabel(f"{total}件 · 需购{need}")
        self._stats.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none;")
        bl.addWidget(self._stats)
        bl.addStretch()

        add_btn = QPushButton("+ 添加")
        add_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: #fff; border: none;
                border-radius: 8px; padding: 4px 14px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        add_btn.clicked.connect(lambda: self._edit_item())
        bl.addWidget(add_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border-radius: 8px; padding: 4px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
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
        self._card_layout.setSpacing(8)
        self._card_layout.addStretch()
        scroll.setWidget(self._container)
        layout.addWidget(scroll, stretch=1)

        self._refresh()

    def _refresh(self) -> None:
        while self._card_layout.count() > 1:
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        items = sorted(self._dm.inventory.items,
                       key=lambda x: (0 if x.get("status") == "需购" else 1 if x.get("status") == "不足" else 2,
                                      x.get("name", "")))

        for it in items:
            card = _ItemCard(it)
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda pos, i=it: self._context_menu(pos, i))
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)

        need = len(self._dm.inventory.need_restock)
        self._stats.setText(f"{len(items)}件 · 需购{need}")

    def _edit_item(self, item: dict | None = None) -> None:
        dlg = ItemDialog(item, self)
        if dlg.exec():
            data = dlg.result_data
            if item:
                self._dm.inventory.update_item(item["id"], data)
            else:
                self._dm.inventory.add_item(data)
            self._dm.inventory.save()
            self._dm.data_changed.emit("inventory")
            self._refresh()

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
        menu.addAction("删除").triggered.connect(lambda: self._delete_item(item["id"]))
        # Quick status toggle
        status = item.get("status", "")
        if status != "需购":
            menu.addAction("标记需购").triggered.connect(
                lambda: self._quick_status(item["id"], "需购"))
        if status != "充足":
            menu.addAction("标记充足").triggered.connect(
                lambda: self._quick_status(item["id"], "充足"))
        menu.exec(self.mapToGlobal(pos))

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

    def _quick_status(self, iid: str, status: str) -> None:
        self._dm.inventory.update_item(iid, {"status": status})
        self._dm.inventory.save()
        self._dm.data_changed.emit("inventory")
        self._refresh()

    def refresh_theme(self) -> None:
        self._refresh()


class ItemDialog(QDialog):
    def __init__(self, item: dict | None = None, parent=None):
        super().__init__(parent)
        c = get_colors()
        editing = item is not None
        self.setWindowTitle("编辑物品" if editing else "添加物品")
        self.setMinimumWidth(380)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_card']}; color: {c['fg_primary']}; }}
            QLabel {{ color: {c['fg_primary']}; background: transparent; border: none; }}
            QLineEdit, QComboBox, QSpinBox {{
                background-color: {c['bg_input']}; color: {c['fg_primary']};
                border: 1px solid {c['border']}; padding: 6px 10px; font-size: 13px;
                border-radius: 6px;
            }}
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
        self._min_qty.setToolTip("低于此数量标记为不足")
        form.addRow("最低库存:", self._min_qty)

        self._location = QLineEdit(item.get("location", "") if item else "")
        self._location.setPlaceholderText("如：卫生间柜子")
        form.addRow("位置:", self._location)

        self._notes = QLineEdit(item.get("notes", "") if item else "")
        self._notes.setPlaceholderText("备注...")
        form.addRow("备注:", self._notes)

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
        if qty <= 0:
            status = "需购"
        elif qty < min_q:
            status = "不足"
        else:
            status = "充足"
        self.result_data = {
            "name": self._name.text().strip(),
            "category": self._category.currentText(),
            "quantity": qty,
            "unit": self._unit.currentText(),
            "min_quantity": min_q,
            "status": status,
            "location": self._location.text().strip(),
            "notes": self._notes.text().strip(),
        }
        self.accept()
