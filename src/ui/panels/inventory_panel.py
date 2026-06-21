"""Inventory panel — 14 cards/page, pagination, working QSS."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget,
    QDialog, QDialogButtonBox,
    QMessageBox, QMenu, QScrollArea, QSizePolicy,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE

PAGE_SIZE = 8


class InventoryPanel(QWidget):
    def __init__(self, dm: DataManager, parent=None):
        super().__init__(parent)
        self._dm = dm
        self._current_category = None  # None=categories, str=items in category
        self._current_group = None       # None=items view, str=items in group
        self._expanded_items: set[str] = set()  # item IDs currently expanded
        self._cat_filter = "全部"
        self._tag_filter = ""
        self._page = 0
        c = get_colors()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === Breadcrumb (hidden in category view) ===
        self._breadcrumb = QWidget()
        bc_layout = QHBoxLayout(self._breadcrumb)
        bc_layout.setContentsMargins(16, 4, 16, 4)
        bc_layout.setSpacing(4)

        self._back_btn = QPushButton("←")
        self._back_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {c['accent']}; border: none; padding: 2px 6px; font-size: 13px; font-weight: 600; }} QPushButton:hover {{ color: {c['fg_primary']}; }}")
        self._back_btn.clicked.connect(self._go_back)
        bc_layout.addWidget(self._back_btn)

        self._bc_cat = QPushButton()
        self._bc_cat.setStyleSheet(f"QPushButton {{ background: {c['bg_elevated']}; color: {c['fg_primary']}; border: none; border-radius: 4px; padding: 2px 8px; font-size: 12px; }} QPushButton:hover {{ background: {c['accent_bg']}; }}")
        self._bc_cat.clicked.connect(lambda: self._navigate_to(1))
        self._bc_cat.hide()
        bc_layout.addWidget(self._bc_cat)

        self._bc_sep1 = QLabel("›")
        self._bc_sep1.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none;")
        self._bc_sep1.hide()
        bc_layout.addWidget(self._bc_sep1)

        self._bc_group = QPushButton()
        self._bc_group.setStyleSheet(f"QPushButton {{ background: {c['bg_elevated']}; color: {c['fg_primary']}; border: none; border-radius: 4px; padding: 2px 8px; font-size: 12px; }} QPushButton:hover {{ background: {c['accent_bg']}; }}")
        self._bc_group.clicked.connect(lambda: self._navigate_to(2))
        self._bc_group.hide()
        bc_layout.addWidget(self._bc_group)

        self._bc_sep2 = QLabel("›")
        self._bc_sep2.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none;")
        self._bc_sep2.hide()
        bc_layout.addWidget(self._bc_sep2)

        self._bc_item = QLabel()
        self._bc_item.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 12px; border: none;")
        self._bc_item.hide()
        bc_layout.addWidget(self._bc_item)
        bc_layout.addStretch()
        layout.addWidget(self._breadcrumb)

        # === Toolbar ===
        bar = QWidget()
        bar.setObjectName("taskBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(6)

        title = QLabel("有什么")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bl.addWidget(title)

        bl.addStretch()

        self._cat_btn = QPushButton("全部分类")
        self._cat_btn.setStyleSheet(self._btn_qss())
        self._cat_btn.clicked.connect(self._show_cat_filter)
        bl.addWidget(self._cat_btn)

        self._tag_btn = QPushButton("全部标签")
        self._tag_btn.setStyleSheet(self._btn_qss())
        self._tag_btn.clicked.connect(self._show_tag_filter)
        bl.addWidget(self._tag_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(self._btn_qss())
        refresh_btn.clicked.connect(self._refresh)
        bl.addWidget(refresh_btn)

        layout.addWidget(bar)

        # === Card area ===
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._container = QWidget()
        self._card_layout = QVBoxLayout(self._container)
        self._card_layout.setContentsMargins(16, 8, 16, 8)
        self._card_layout.setSpacing(8)
        self._card_layout.addStretch()
        scroll.setWidget(self._container)
        layout.addWidget(scroll, stretch=1)

        # === Footer with pagination ===
        footer = QWidget()
        footer.setObjectName("taskFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 4, 16, 4)

        self._count_label = QLabel()
        self._count_label.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none;")
        fl.addWidget(self._count_label)
        fl.addStretch()

        for text, slot in [("< 上一页", self._prev_page), ("下一页 >", self._next_page)]:
            btn = QPushButton(text)
            btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {c['fg_hint']}; border: none; padding: 4px 8px; font-size: 13px; }} QPushButton:hover {{ color: {c['fg_primary']}; }}")
            btn.clicked.connect(slot)
            fl.addWidget(btn)

        layout.addWidget(footer)
        self._refresh()

    def _btn_qss(self) -> str:
        c = get_colors()
        return f"QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['fg_hint']}; border-radius: 8px; padding: 4px 12px; font-size: 13px; }} QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['fg_secondary']}; }} QPushButton::menu-indicator {{ image: none; }}"

    def _show_cat_filter(self) -> None:
        from src.ui.widgets.context_menu import ContextMenu
        
        menu = ContextMenu(self)
        menu.add_action("全部分类").triggered.connect(lambda: self._apply_cat_filter("全部"))
        menu.add_separator()
        cats = self._dm.inventory.categories
        for cat in cats:
            menu.add_action(cat).triggered.connect(lambda checked, c2=cat: self._apply_cat_filter(c2))
        menu.exec(self._cat_btn.mapToGlobal(self._cat_btn.rect().bottomLeft()))

    def _show_tag_filter(self) -> None:
        from src.ui.widgets.context_menu import ContextMenu
        
        menu = ContextMenu(self)
        menu.add_action("全部标签").triggered.connect(lambda: self._apply_tag_filter(""))
        menu.add_separator()
        for tag in self._dm.inventory.all_tags:
            menu.add_action(tag).triggered.connect(lambda checked, t=tag: self._apply_tag_filter(t))
        menu.exec(self._tag_btn.mapToGlobal(self._tag_btn.rect().bottomLeft()))

    def _apply_cat_filter(self, cat: str) -> None:
        self._cat_filter = cat
        self._cat_btn.setText(cat if cat != "全部" else "全部分类")
        self._page = 0
        self._refresh()

    def _apply_tag_filter(self, tag: str) -> None:
        self._tag_filter = tag
        self._tag_btn.setText(tag if tag else "全部标签")
        self._page = 0
        self._refresh()

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._refresh()

    def _next_page(self) -> None:
        items = self._get_filtered()
        max_page = max(0, (len(items) - 1) // PAGE_SIZE)
        if self._page < max_page:
            self._page += 1
            self._refresh()

    def _get_filtered(self) -> list[dict]:
        items = self._dm.inventory.items
        if self._cat_filter != "全部":
            items = [i for i in items if i.get("category") == self._cat_filter]
        if self._tag_filter:
            items = [i for i in items if self._tag_filter in i.get("tags", [])]
        return sorted(items, key=lambda x: (
            0 if x.get("status") == "需购" else 1 if x.get("status") == "不足" else 2,
            x.get("name", "")))

    def _navigate_to(self, level: int) -> None:
        if level <= 0:
            self._current_category = None
            self._current_group = None
            self._cat_filter = "全部"
        elif level == 1:
            self._current_group = None
        self._page = 0
        self._refresh()

    def _go_back(self) -> None:
        if self._current_group:
            self._current_group = None
            self._page = 0
        elif self._current_category:
            self._current_category = None
            self._current_group = None
            self._cat_filter = "全部"
            self._page = 0
        self._refresh()

    def _update_breadcrumb(self) -> None:
        self._bc_cat.hide(); self._bc_sep1.hide()
        self._bc_group.hide(); self._bc_sep2.hide(); self._bc_item.hide()
        if self._current_category:
            self._breadcrumb.show()
            self._bc_cat.setText(self._current_category); self._bc_cat.show()
            if self._current_group:
                self._bc_sep1.show()
                self._bc_group.setText(self._current_group); self._bc_group.show()
        else:
            self._breadcrumb.hide()

    def _enter_category(self, category: str) -> None:
        self._current_category = category
        self._current_group = None
        self._cat_filter = category
        self._page = 0
        self._refresh()

    def _enter_group(self, group_name: str) -> None:
        self._current_group = group_name
        self._page = 0
        self._refresh()

    def _refresh(self) -> None:
        while self._card_layout.count() > 1:
            it = self._card_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        c = get_colors()

        if self._current_category is None:
            self._refresh_categories(c)
        elif self._current_group:
            self._refresh_group_items(c)
        else:
            self._refresh_items(c)

    def _refresh_categories(self, c: dict) -> None:
        self._update_breadcrumb()

        cats = self._dm.inventory.categories
        total_items = len(self._dm.inventory.items)

        from collections import Counter
        counts = Counter()
        for it in self._dm.inventory.items:
            if self._tag_filter and self._tag_filter not in it.get("tags", []):
                continue
            counts[it.get("category", "其他")] += 1

        for cat_name in cats:
            count = counts.get(cat_name, 0)

            card = QWidget()
            card.setMinimumHeight(56)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setStyleSheet(f"background-color: {c['bg_elevated']}; border-radius: 8px;")
            # Only left-click enters category; right-click is blocked
            def _on_click(e, cn=cat_name):
                if e.button() == Qt.MouseButton.LeftButton:
                    self._enter_category(cn)
            card.mousePressEvent = _on_click

            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(8)

            name = QLabel(cat_name)
            name.setStyleSheet(f"color: {c['fg_primary']}; font-size: 15px; font-weight: 600; border: none; background: transparent;")
            cl.addWidget(name)
            cl.addStretch()

            cnt = QLabel(f"{count} 件")
            cnt.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none; background: transparent;")
            cl.addWidget(cnt)

            arrow = QLabel("›")
            arrow.setStyleSheet(f"color: {c['fg_hint']}; font-size: 18px; border: none; background: transparent;")
            cl.addWidget(arrow)

            self._card_layout.insertWidget(self._card_layout.count() - 1, card)

        self._count_label.setText(f"共 {total_items} 件物品")

    def _refresh_items(self, c: dict) -> None:
        self._update_breadcrumb()

        items = self._get_filtered()
        # Group items by their group field (non-empty) — Level 1 collapsing
        groups: dict[str, list[dict]] = {}
        standalone: list[dict] = []
        for it in items:
            g = it.get("group", "")
            if g:
                groups.setdefault(g, []).append(it)
            else:
                standalone.append(it)

        # Build display list: group cards first, then standalone items
        display_items: list[dict] = []
        for gname, gitems in groups.items():
            display_items.append({
                "_type": "group", "name": gname,
                "count": sum(it.get("quantity", 0) for it in gitems), "items": gitems,
            })
        for it in standalone:
            display_items.append({"_type": "item", **it})

        total = len(display_items)
        start = self._page * PAGE_SIZE
        page_items = display_items[start:start + PAGE_SIZE]
        max_page = max(0, (total - 1) // PAGE_SIZE)
        if self._page > max_page:
            self._page = max_page
            start = self._page * PAGE_SIZE
            page_items = display_items[start:start + PAGE_SIZE]

        for d in page_items:
            if d.get("_type") == "group":
                self._render_group_card(c, d)
            else:
                self._render_item_card(c, d)

        page_str = f"第{self._page + 1}/{max_page + 1}页" if total > PAGE_SIZE else ""
        self._count_label.setText(f"{total} 项  {page_str}")

    def _render_group_card(self, c: dict, d: dict) -> None:
        """Render a clickable group card at Level 1."""
        card = QWidget()
        card.setMinimumHeight(56)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(f"background-color: {c['accent_bg']}; border-radius: 8px;")
        # Only left-click enters group; right-click is blocked
        def _on_click(e, gn=d["name"]):
            if e.button() == Qt.MouseButton.LeftButton:
                self._enter_group(gn)
        card.mousePressEvent = _on_click

        cl = QHBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)

        icon = QLabel("📁")
        icon.setStyleSheet("font-size: 18px; border: none; background: transparent;")
        cl.addWidget(icon)

        name = QLabel(d["name"])
        name.setStyleSheet(f"color: {c['fg_primary']}; font-size: 15px; font-weight: 600; border: none; background: transparent;")
        cl.addWidget(name)
        cl.addStretch()

        cnt = QLabel(f"{d['count']} 件")
        cnt.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none; background: transparent;")
        cl.addWidget(cnt)

        arrow = QLabel("›")
        arrow.setStyleSheet(f"color: {c['fg_hint']}; font-size: 18px; border: none; background: transparent;")
        cl.addWidget(arrow)

        self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _render_item_card(self, c: dict, it: dict) -> None:
        """Render an individual item card with status badge and context menu."""
        card = QWidget()
        card.setMinimumHeight(64)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        status = it.get("status", "充足")
        if status == "需购":
            bg = c["red"] + "10"
        elif status == "不足":
            bg = c["orange"] + "10"
        else:
            bg = c["bg_elevated"]

        card.setStyleSheet(f"background-color: {bg}; border-radius: 8px;")

        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 10, 16, 10)
        cl.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        name = QLabel(it.get("name", ""))
        name.setStyleSheet(f"color: {c['fg_primary']}; font-size: 14px; font-weight: 600; border: none; background: transparent;")
        hdr.addWidget(name)
        hdr.addStretch()
        qty_text = self._format_quantity(it)
        dpu = it.get('doses_per_unit', 1)
        if dpu > 1:
            qty_text = f"x{it['quantity']} ({it['quantity'] * dpu}次)"
        qty = QLabel(qty_text)
        qty.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        hdr.addWidget(qty)

        bc = {"需购": c["red"], "不足": c["orange"], "充足": c["green"]}.get(status, c["green"])
        badge = QLabel({"需购": "需购", "不足": "不足", "充足": "充足"}.get(status, status))
        badge.setFixedWidth(42)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"color: {bc}; font-size: 11px; font-weight: 600; background: {bc}18; border-radius: 10px; padding: 2px 0; border: none;")
        hdr.addWidget(badge)
        cl.addLayout(hdr)

        parts = []
        for k in ["location", "notes"]:
            v = it.get(k, "")
            if v: parts.append(v)
        if parts:
            detail = QLabel(" · ".join(parts))
            detail.setWordWrap(True)
            detail.setStyleSheet(f"color: {c['fg_hint']}; font-size: 12px; border: none; background: transparent;")
            cl.addWidget(detail)

        tags = it.get("tags", [])
        if tags:
            tr = QHBoxLayout()
            tr.setSpacing(4)
            for tag in tags:
                t = QLabel(tag)
                t.setStyleSheet(f"color: {c['accent']}; font-size: 10px; font-weight: 500; background: {c['accent']}18; border-radius: 8px; padding: 1px 8px; border: none;")
                tr.addWidget(t)
            tr.addStretch()
            cl.addLayout(tr)

        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda _, i=it: self._context_menu(i))
        self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _refresh_group_items(self, c: dict) -> None:
        """Level 2: expandable type cards with instance sub-cards."""
        self._update_breadcrumb()

        items = [it for it in self._dm.inventory.items
                 if it.get("category") == self._current_category
                 and it.get("group") == self._current_group]
        if self._tag_filter:
            items = [it for it in items if self._tag_filter in it.get("tags", [])]

        total = len(items)
        for it in items:
            self._render_expandable_card(c, it)

        self._count_label.setText(f"{total} 类物品")

    def _render_expandable_card(self, c: dict, it: dict) -> None:
        """Render a type card that expands to show instances."""
        iid = it["id"]
        expanded = iid in self._expanded_items

        # Type card (always clickable)
        card = QWidget()
        card.setMinimumHeight(52)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(f"background-color: {c['bg_elevated']}; border-radius: 8px;")
        card.mousePressEvent = lambda e, id=iid: self._toggle_expand(id)

        cl = QHBoxLayout(card)
        cl.setContentsMargins(16, 10, 16, 10)
        cl.setSpacing(8)

        arrow_icon = "▼" if expanded else "▶"
        arrow = QLabel(arrow_icon)
        arrow.setStyleSheet(f"color: {c['accent']}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        cl.addWidget(arrow)

        name = QLabel(it.get("name", ""))
        name.setStyleSheet(f"color: {c['fg_primary']}; font-size: 14px; font-weight: 600; border: none; background: transparent;")
        cl.addWidget(name)
        cl.addStretch()

        qty = it.get("quantity", 0)
        qty_label = QLabel(self._format_quantity(it))
        qty_label.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        cl.addWidget(qty_label)

        self._card_layout.insertWidget(self._card_layout.count() - 1, card)

        # Instance cards (only when expanded)
        if expanded:
            instances = it.get("instances", [])
            if not instances:
                # Auto-generate instances from quantity
                instances = [{"tags": it.get("tags", []), "status": it.get("status", "充足"),
                              "notes": it.get("notes", ""), "location": it.get("location", "")}
                             for _ in range(qty)]
            for idx, inst in enumerate(instances):
                self._render_instance_card(c, iid, idx, inst, it)

    def _render_instance_card(self, c: dict, parent_id: str, idx: int, inst: dict, parent: dict) -> None:
        """Render an individual instance card with tags and context menu."""
        card = QWidget()
        card.setMinimumHeight(48)
        card.setStyleSheet(f"background-color: {c['bg_elevated']}; border-left: 3px solid {c['accent']}; border-radius: 0 8px 8px 0; margin-left: 24px;")

        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 8, 12, 8)
        cl.setSpacing(6)

        label = QLabel(f"#{idx + 1}")
        label.setStyleSheet(f"color: {c['fg_hint']}; font-size: 12px; font-weight: 600; border: none; background: transparent;")
        cl.addWidget(label)

        # Tags
        tags = inst.get("tags", [])
        if tags:
            for tag in tags:
                t = QLabel(tag)
                t.setStyleSheet(f"color: {c['accent']}; font-size: 10px; font-weight: 500; background: {c['accent']}18; border-radius: 8px; padding: 1px 8px; border: none;")
                cl.addWidget(t)

        # Status badge
        status = inst.get("status", "充足")
        bc = {"需购": c["red"], "不足": c["orange"], "充足": c["green"]}.get(status, c["green"])
        badge = QLabel({"需购": "需购", "不足": "不足", "充足": "充足"}.get(status, status))
        badge.setStyleSheet(f"color: {bc}; font-size: 10px; font-weight: 600; background: {bc}18; border-radius: 8px; padding: 1px 6px; border: none;")
        cl.addWidget(badge)

        # Notes
        note = inst.get("notes", "")
        if note:
            n = QLabel(note)
            n.setStyleSheet(f"color: {c['fg_hint']}; font-size: 11px; border: none; background: transparent;")
            cl.addWidget(n)

        cl.addStretch()

        # Instance context menu
        inst_item = {"id": f"{parent_id}_{idx}", "parent_id": parent_id, "index": idx,
                     "name": parent.get("name", ""), "tags": tags, "status": status, "notes": note,
                     "inst_data": inst}
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda _, i=inst_item: self._context_menu(i))
        self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _format_quantity(self, it: dict) -> str:
        cat = it.get("category", "")
        qty = it.get("quantity", 0)
        if cat == "虚拟品类":
            return f"×{qty}项"
        return f"×{qty}件"

    def _toggle_expand(self, iid: str) -> None:
        if iid in self._expanded_items:
            self._expanded_items.discard(iid)
        else:
            self._expanded_items.add(iid)
        self._refresh()

    # Per-category status labels
    CATEGORY_LABELS = {
        "衣物":       {"需购": "要买了", "不足": "要洗了", "充足": "可穿"},
        "虚拟品类":   {"需购": "要续费", "不足": "要到期了", "充足": "有效"},
        "数码电子":   {"需购": "需维修", "不足": "待更换", "充足": "正常"},
        "日常消耗品": {"需购": "需补货", "不足": "快用完", "充足": "充足"},
    }

    def _context_menu(self, item: dict) -> None:
        from PySide6.QtGui import QCursor
        c = get_colors()
        cat = item.get("category", "其他")
        labels = self.CATEGORY_LABELS.get(cat, {"需购": "需购", "不足": "不足", "充足": "充足"})
        st = item.get("status", "充足")

        from src.ui.widgets.context_menu import ContextMenu
        menu = ContextMenu(self)

        for target_status in ["需购", "不足", "充足"]:
            if st != target_status:
                menu.add_action(labels[target_status]).triggered.connect(
                    lambda checked, s=target_status: self._quick_update(item["id"], {"status": s}))

        ig = item.get("ignore_low_stock", False)
        menu.add_action("恢复库存提醒" if ig else "忽略库存不足提醒").triggered.connect(
            lambda: self._quick_update(item["id"], {"ignore_low_stock": not ig}))
        menu.add_separator()
        menu.add_action("设置邮件提醒").triggered.connect(lambda: self._email_reminder(item))
        menu.add_action("修改标签").triggered.connect(lambda: self._edit_tags(item))
        if cat != "虚拟品类":
            menu.add_action("删除").triggered.connect(lambda: self._delete_item(item["id"]))
        menu.exec()

    def _quick_update(self, iid, data) -> None:
        self._dm.inventory.update_item(iid, data); self._dm.inventory.save(); self._dm.data_changed.emit("inventory"); self._refresh()

    def _delete_item(self, iid) -> None:
        name = next((it.get("name", iid) for it in self._dm.inventory.items if it["id"] == iid), iid)
        if QMessageBox.question(self, "确认", f"删除「{name}」？") == QMessageBox.StandardButton.Yes:
            self._dm.inventory.delete_item(iid); self._dm.inventory.save(); self._dm.data_changed.emit("inventory"); self._refresh()

    def _edit_tags(self, item: dict) -> None:
        """Open dialog to add/remove/edit tags on an item."""
        c = get_colors()
        dlg = QDialog(self)
        dlg.setWindowTitle(f"修改标签 - {item.get('name', '')}")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet(f"QDialog {{ background-color: {c['card_bg']}; }} QLabel {{ color: {c['fg_primary']}; font-size: 13px; background: transparent; border: none; }} QLineEdit {{ background-color: {c['bg_input']}; color: {c['fg_primary']}; border: 1px solid {c['border']}; padding: 6px 10px; font-size: 13px; }} QPushButton {{ background-color: {c['accent_bg']}; color: {c['fg_primary']}; border: none; border-radius: 4px; padding: 4px 12px; font-size: 12px; }} QPushButton:hover {{ background-color: {c['accent']}; color: #fff; }}")
        layout = QVBoxLayout(dlg); layout.setSpacing(10); layout.setContentsMargins(20, 16, 20, 16)

        tag_list = QListWidget()
        tag_list.setStyleSheet(f"QListWidget {{ background-color: {c['bg_input']}; color: {c['fg_primary']}; border: 1px solid {c['border']}; border-radius: 4px; font-size: 13px; }}")
        tags = list(item.get("tags", []))
        for t in tags:
            tag_list.addItem(t)
        layout.addWidget(QLabel("当前标签 (双击编辑):"))
        layout.addWidget(tag_list)

        # Double-click to edit
        def edit_tag():
            row = tag_list.currentRow()
            if row >= 0:
                old = tag_list.item(row).text()
                new, ok = __import__('PySide6.QtWidgets').QInputDialog.getText(dlg, "编辑标签", "标签文本:", text=old)
                if ok and new.strip():
                    tag_list.item(row).setText(new.strip())

        tag_list.doubleClicked.connect(lambda _: edit_tag())

        # Add new tag
        add_row = QHBoxLayout()
        self._tag_input = QLineEdit(); self._tag_input.setPlaceholderText("新标签..."); add_row.addWidget(self._tag_input)
        add_btn = QPushButton("添加"); add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        def add_tag():
            t = self._tag_input.text().strip()
            if t and not any(tag_list.item(i).text() == t for i in range(tag_list.count())):
                tag_list.addItem(t)
                self._tag_input.clear()

        add_btn.clicked.connect(add_tag)
        self._tag_input.returnPressed.connect(add_tag)

        # Remove selected
        del_btn = QPushButton("删除选中"); del_btn.clicked.connect(lambda: tag_list.takeItem(tag_list.currentRow()) if tag_list.currentRow() >= 0 else None)
        layout.addWidget(del_btn)

        # OK / Cancel
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec():
            new_tags = [tag_list.item(i).text() for i in range(tag_list.count())]
            self._dm.inventory.update_item(item["id"], {"tags": new_tags})
            self._dm.inventory.save(); self._dm.data_changed.emit("inventory"); self._refresh()

    def _email_reminder(self, item) -> None:
        from PySide6.QtWidgets import QDateTimeEdit; from PySide6.QtCore import QLocale
        from datetime import datetime, timedelta
        c = get_colors()
        dlg = QDialog(self); dlg.setWindowTitle(f"邮件提醒 - {item.get('name','')}"); dlg.setMinimumWidth(320)
        dlg.setStyleSheet(f"QDialog {{ background-color: {c['card_bg']}; }} QLabel {{ color: {c['fg_primary']}; font-size: 13px; }}")
        layout = QVBoxLayout(dlg); layout.setSpacing(12)
        layout.addWidget(QLabel(f"为「{item.get('name','')}」设置补货提醒"))
        dt = QDateTimeEdit(); dt.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        dt.setCalendarPopup(True); dt.setDateTime(datetime.now() + timedelta(days=3)); dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        layout.addWidget(dt)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); layout.addWidget(btns)
        if dlg.exec(): self._dm.daily_logs.add_reminder("inventory", item.get("name", ""), datetime.now().strftime("%Y-%m-%d"), dt.dateTime().toPython().isoformat()); self._dm.daily_logs.save(); QMessageBox.information(self, "已设置", "已设置补货提醒")

    def refresh_theme(self) -> None: self._refresh()
