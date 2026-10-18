"""Inventory panel — 14 cards/page, pagination, working QSS."""

from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.models.inventory import (
    DEFAULT_LOCATION,
    HOME_LOCATION,
    MEMBERSHIP_CATEGORY,
    SIDE_HOME,
    SIDE_SCHOOL,
    InventoryModel,
)
from src.services.data_manager import DataManager

# 面板里"每张卡"的局部变量就叫 `card` → 工厂用**别名**导入，避免同名遮蔽（ERRORS #047）
from src.ui.panels.inventory_dialogs import (
    edit_membership_dialog,
    edit_tags_dialog,
    email_reminder_dialog,
)
from src.ui.styles.cards import card as make_card
from src.ui.styles.theme import FONT_CN, RADIUS, SIZE_SUBTITLE, SPACING, get_colors, rgba
from src.ui.widgets.menu import (
    add_action,
    add_separator,
    new_menu,
    show_at_cursor,
    show_below,
)
from src.ui.widgets.rounded_button import RoundedButton

PAGE_SIZE = 8


def _membership_summary(it: dict) -> str:
    """会员摘要（用户名 / 到期日 / 自动续费）—— 文本走 i18n，**手机号不显示**。"""
    m = InventoryModel.membership_of(it)
    if not m:
        return ""
    bits = [str(m["username"])] if m.get("username") else []
    if m.get("expires_on"):
        bits.append(tr("panel.inventory.membership_expires", date=m["expires_on"]))
    if m.get("auto_renew"):
        bits.append(tr("panel.inventory.membership_auto_renew"))
    return " · ".join(bits)


def _detail_parts(it: dict) -> list[str]:
    """卡片第二行：位置 / 备注 / 会员摘要（家那一侧不显示位置）。

    放在**类外**：`InventoryPanel` 的尺寸早就贴上上限（`Q-A1`），能挪出去的就挪。
    """
    keys = ("notes",) if InventoryModel.side_of(it) == SIDE_HOME else ("location", "notes")
    parts = [v for k in keys if (v := it.get(k, ""))]
    member = _membership_summary(it)
    return [*parts, member] if member else parts


class InventoryPanel(QWidget):
    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._current_category = None  # None=categories, str=items in category
        self._current_group = None       # None=items view, str=items in group
        self._expanded_items: set[str] = set()  # item IDs currently expanded
        self._cat_filter = "全部"
        self._tag_filter = ""
        self._page = 0
        self._side = SIDE_SCHOOL   # 看哪一边（**视图状态**，不写数据文件）
        c = get_colors()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === Breadcrumb (hidden in category view) ===
        layout.addWidget(self._build_breadcrumb())

        # === Toolbar ===
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(6)

        title = QLabel(tr("panel.inventory.title"))
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bl.addWidget(title)

        bl.addStretch()

        # 看哪一边（学校 / 家）：换季把衣物寄回家、来年寄回。照 `_cat_btn` / `_tag_btn`
        # 的现成做法（标签显示当前值、点开菜单选），不另建一套控件。
        self._ds_btn = RoundedButton(self._side_label())
        self._ds_btn.setStyleSheet(self._btn_qss())
        self._ds_btn.clicked.connect(self._show_side_menu)
        bl.addWidget(self._ds_btn)

        self._cat_btn = RoundedButton(tr("panel.inventory.filter_all_categories"))
        self._cat_btn.setStyleSheet(self._btn_qss())
        self._cat_btn.clicked.connect(self._show_cat_filter)
        bl.addWidget(self._cat_btn)

        self._tag_btn = RoundedButton(tr("panel.inventory.filter_all_tags"))
        self._tag_btn.setStyleSheet(self._btn_qss())
        self._tag_btn.clicked.connect(self._show_tag_filter)
        bl.addWidget(self._tag_btn)

        refresh_btn = RoundedButton(tr("panel.inventory.btn_refresh"))
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
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 4, 16, 4)

        self._count_label = QLabel()
        self._count_label.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none;")
        fl.addWidget(self._count_label)
        fl.addStretch()

        for text, slot in [(tr("panel.inventory.btn_prev_page"), self._prev_page),
                           (tr("panel.inventory.btn_next_page"), self._next_page)]:
            btn = RoundedButton(text)
            btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {c['fg_hint']}; border: none; padding: 4px 8px; font-size: 13px; }} QPushButton:hover {{ color: {c['fg_primary']}; }}")
            btn.clicked.connect(slot)
            fl.addWidget(btn)

        layout.addWidget(footer)
        self._refresh()

    def _build_breadcrumb(self) -> QWidget:
        """面包屑（分类视图下隐藏）。

        从 `__init__` 抽出来：那个函数原来 127 行，超「函数 ≤60」（`Q-A1`）。
        """
        c = get_colors()
        self._breadcrumb = QWidget()
        bc_layout = QHBoxLayout(self._breadcrumb)
        bc_layout.setContentsMargins(16, 4, 16, 4)
        bc_layout.setSpacing(4)

        self._back_btn = RoundedButton("←")
        self._back_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {c['accent_text']}; border: none; padding: 2px 6px; font-size: 13px; font-weight: 600; }} QPushButton:hover {{ color: {c['fg_primary']}; }}")
        self._back_btn.clicked.connect(self._go_back)
        bc_layout.addWidget(self._back_btn)

        self._bc_cat = RoundedButton()
        self._bc_cat.setStyleSheet(f"QPushButton {{ background: {c['bg_elevated']}; color: {c['fg_primary']}; border: none; border-radius: 4px; padding: 2px 8px; font-size: 12px; }} QPushButton:hover {{ background: {c['accent_bg']}; }}")
        self._bc_cat.clicked.connect(lambda: self._navigate_to(1))
        self._bc_cat.hide()
        bc_layout.addWidget(self._bc_cat)

        self._bc_sep1 = QLabel("›")
        self._bc_sep1.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none;")
        self._bc_sep1.hide()
        bc_layout.addWidget(self._bc_sep1)

        self._bc_group = RoundedButton()
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
        return self._breadcrumb

    def _btn_qss(self) -> str:
        c = get_colors()
        return f"QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['fg_hint']}; border-radius: 8px; padding: 4px 12px; font-size: 13px; }} QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['fg_secondary']}; }} QPushButton::menu-indicator {{ image: none; }}"

    def _side_label(self) -> str:
        """切换按钮上的文字：学校 / 家（按 i18n 取，代码里不出现中文 —— Q-N5）。"""
        if self._side == SIDE_HOME:
            return tr("panel.inventory.side_home")
        return tr("panel.inventory.side_school")

    def _side_items(self) -> list[dict]:
        """当前这一边的物品（归属由**位置**推导，见 `InventoryModel.side_of`）。"""
        return [it for it in self._dm.inventory.items
                if InventoryModel.side_of(it) == self._side]

    def _show_side_menu(self) -> None:
        menu = new_menu(self)
        for side, key in ((SIDE_SCHOOL, "panel.inventory.side_school"),
                          (SIDE_HOME, "panel.inventory.side_home")):
            add_action(menu, tr(key),
                       lambda checked=False, s=side: self._apply_side(s))
        show_below(menu, self._ds_btn)

    def _apply_side(self, side: str) -> None:
        """切换"看哪一边"（学校 / 家）。

        归属由**位置**推导，所以这只是**视图状态**：不写数据文件、不进 git 同步，
        命令行那边也不需要知道（"没说位置就默认学校"是常量，不依赖界面）。
        切完清掉一切"按视图"的状态（分类/标签筛选、分页、展开），否则会带着旧视图的空结果。
        """
        self._side = side
        self._tag_filter = ""
        self._expanded_items.clear()
        self._cat_btn.setText(tr("panel.inventory.filter_all_categories"))
        self._tag_btn.setText(tr("panel.inventory.filter_all_tags"))
        # 复用现成的"回到顶层"逻辑（清分类/分组/筛选/分页并刷新）—— 不另写一遍 `"全部"`
        # 字面量，否则 i18n 计数会再多一笔（Q-N5）
        self._navigate_to(0)

    def _show_cat_filter(self) -> None:
        menu = new_menu(self)
        add_action(menu, tr("panel.inventory.filter_all_categories"), lambda checked=False: self._apply_cat_filter("全部"))
        add_separator(menu)
        for cat in self._dm.inventory.categories:
            add_action(menu, cat,
                       lambda checked=False, c2=cat: self._apply_cat_filter(c2))
        show_below(menu, self._cat_btn)

    def _show_tag_filter(self) -> None:
        menu = new_menu(self)
        add_action(menu, tr("panel.inventory.filter_all_tags"), lambda checked=False: self._apply_tag_filter(""))
        add_separator(menu)
        for tag in self._dm.inventory.all_tags:
            add_action(menu, tag,
                       lambda checked=False, t=tag: self._apply_tag_filter(t))
        show_below(menu, self._tag_btn)

    def _apply_cat_filter(self, cat: str) -> None:
        self._cat_filter = cat
        self._cat_btn.setText(cat if cat != "全部" else tr("panel.inventory.filter_all_categories"))
        self._page = 0
        self._refresh()

    def _apply_tag_filter(self, tag: str) -> None:
        self._tag_filter = tag
        self._tag_btn.setText(tag if tag else tr("panel.inventory.filter_all_tags"))
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
        items = self._side_items()
        if self._cat_filter != "全部":
            items = [i for i in items if i.get("category") == self._cat_filter]
        if self._tag_filter:
            items = [i for i in items if self._tag_filter in i.get("tags", [])]
        return sorted(items, key=lambda x: (
            0 if InventoryModel.effective_status(x) == "需购"
            else 1 if InventoryModel.effective_status(x) == "不足" else 2,
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
        self._bc_cat.hide()
        self._bc_sep1.hide()
        self._bc_group.hide()
        self._bc_sep2.hide()
        self._bc_item.hide()
        if self._current_category:
            self._breadcrumb.show()
            self._bc_cat.setText(self._current_category)
            self._bc_cat.show()
            if self._current_group:
                self._bc_sep1.show()
                self._bc_group.setText(self._current_group)
                self._bc_group.show()
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
        self._ds_btn.setText(self._side_label())   # 视图状态在本对象里，改过就同步按钮
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
        side_items = self._side_items()
        total_items = len(side_items)

        from collections import Counter
        counts = Counter()
        for it in side_items:
            if self._tag_filter and self._tag_filter not in it.get("tags", []):
                continue
            counts[it.get("category", "其他")] += 1

        for cat_name in cats:
            count = counts.get(cat_name, 0)

            card = make_card("item", pad="spacing_none")
            card.setMinimumHeight(56)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            # Only left-click enters category; right-click is blocked
            def _on_click(e, cn=cat_name) -> None:
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

            cnt = QLabel(tr("panel.inventory.count_pieces", n=count))
            cnt.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none; background: transparent;")
            cl.addWidget(cnt)

            arrow = QLabel("›")
            arrow.setStyleSheet(f"color: {c['fg_hint']}; font-size: 18px; border: none; background: transparent;")
            cl.addWidget(arrow)

            self._card_layout.insertWidget(self._card_layout.count() - 1, card)

        self._count_label.setText(tr("panel.inventory.count_total_items", n=total_items))

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

        page_str = tr("panel.inventory.page_indicator", cur=self._page + 1,
                      total=max_page + 1) if total > PAGE_SIZE else ""
        self._count_label.setText(tr("panel.inventory.count_summary", n=total, page=page_str))

    def _render_group_card(self, c: dict, d: dict) -> None:
        """Render a clickable group card at Level 1."""
        card = make_card("item", pad="spacing_none", bg="accent_bg")
        card.setMinimumHeight(56)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        # Only left-click enters group; right-click is blocked
        def _on_click(e, gn=d["name"]) -> None:
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

        cnt = QLabel(tr("panel.inventory.count_pieces", n=d['count']))
        cnt.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none; background: transparent;")
        cl.addWidget(cnt)

        arrow = QLabel("›")
        arrow.setStyleSheet(f"color: {c['fg_hint']}; font-size: 18px; border: none; background: transparent;")
        cl.addWidget(arrow)

        self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _render_item_card(self, c: dict, it: dict) -> None:
        """Render an individual item card with status badge and context menu."""
        status = InventoryModel.effective_status(it)
        # 底色按状态取**令牌名**（此前是 `c["red"] + "10"` 这类派生色，绕过了令牌体系）
        bg_key = {"需购": "red_tint", "不足": "orange_tint"}.get(status, "bg_elevated")
        card = make_card("item", pad="spacing_none", bg=bg_key)
        card.setMinimumHeight(64)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

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
            qty_text = tr("panel.inventory.qty_with_doses", n=it['quantity'], doses=it['quantity'] * dpu)
        qty = QLabel(qty_text)
        qty.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        hdr.addWidget(qty)

        bc = {"需购": c["red"], "不足": c["orange"], "充足": c["green"]}.get(status, c["green"])
        badge = QLabel({"需购": "需购", "不足": "不足", "充足": "充足"}.get(status, status))
        badge.setFixedWidth(42)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"color: {bc}; font-size: 11px; font-weight: 600; background: {rgba(bc, 0.1)}; border-radius: 10px; padding: 2px 0; border: none;")
        hdr.addWidget(badge)
        cl.addLayout(hdr)

        # 家那一侧不显示位置（用户口径）：那边的位置一律是"家"，显示出来是废话
        parts = _detail_parts(it)
        if parts:
            detail = QLabel(" · ".join(parts))
            detail.setWordWrap(True)
            detail.setStyleSheet(f"color: {c['fg_hint']}; font-size: 12px; border: none; background: transparent;")
            cl.addWidget(detail)

        tags = it.get("tags", [])
        if tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(4)
            for tag in tags:
                t = QLabel(tag)
                t.setStyleSheet(f"color: {c['accent_text']}; font-size: 10px; font-weight: 500; background: {rgba(c['accent'], 0.1)}; border-radius: 8px; padding: 1px 8px; border: none;")
                tag_row.addWidget(t)
            tag_row.addStretch()
            cl.addLayout(tag_row)

        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda _, i=it: self._context_menu(i))
        self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _refresh_group_items(self, c: dict) -> None:
        """Level 2: expandable type cards with instance sub-cards."""
        self._update_breadcrumb()

        items = [it for it in self._side_items()
                 if it.get("category") == self._current_category
                 and it.get("group") == self._current_group]
        if self._tag_filter:
            items = [it for it in items if self._tag_filter in it.get("tags", [])]

        total = len(items)
        for it in items:
            self._render_expandable_card(c, it)

        self._count_label.setText(tr("panel.inventory.count_types", n=total))

    def _render_expandable_card(self, c: dict, it: dict) -> None:
        """Render a type card that expands to show instances."""
        iid = it["id"]
        expanded = iid in self._expanded_items

        # Type card (always clickable)
        card = make_card("item", pad="spacing_none")
        card.setMinimumHeight(52)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda e, id=iid: self._toggle_expand(id)

        cl = QHBoxLayout(card)
        cl.setContentsMargins(16, 10, 16, 10)
        cl.setSpacing(8)

        arrow_icon = "▼" if expanded else "▶"
        arrow = QLabel(arrow_icon)
        arrow.setStyleSheet(f"color: {c['accent_text']}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
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
        card = make_card("sub", pad="spacing_none")
        card.setMinimumHeight(48)

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
                t.setStyleSheet(f"color: {c['accent_text']}; font-size: 10px; font-weight: 500; background: {rgba(c['accent'], 0.1)}; border-radius: 8px; padding: 1px 8px; border: none;")
                cl.addWidget(t)

        # Status badge
        status = inst.get("status", "充足")
        bc = {"需购": c["red"], "不足": c["orange"], "充足": c["green"]}.get(status, c["green"])
        badge = QLabel({"需购": "需购", "不足": "不足", "充足": "充足"}.get(status, status))
        badge.setStyleSheet(f"color: {bc}; font-size: 10px; font-weight: 600; background: {rgba(bc, 0.1)}; border-radius: 8px; padding: 1px 6px; border: none;")
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
        # 层级缩进：QSS 的 `margin-left` 只改内容区，缩不了卡片本身 → 外面套一层带左边距的行。
        # ⚠ 用**容器控件**而不是嵌套 layout：`_refresh()` 靠 `item.widget()` 清卡，
        # 嵌套 layout 的 `item.widget()` 是 None → 旧卡不会被删、会留在屏幕上。
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(SPACING["spacing_xxl"], 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(card)
        self._card_layout.insertWidget(self._card_layout.count() - 1, row)

    def _format_quantity(self, it: dict) -> str:
        cat = it.get("category", "")
        qty = it.get("quantity", 0)
        if cat == "虚拟品类":
            return tr("panel.inventory.qty_virtual_items", n=qty)
        return tr("panel.inventory.qty_pieces", n=qty)

    def _toggle_expand(self, iid: str) -> None:
        if iid in self._expanded_items:
            self._expanded_items.discard(iid)
        else:
            self._expanded_items.add(iid)
        self._refresh()

    # Per-category status labels（常量：ClassVar 明确非实例状态，见 Q-B2/RUF012）
    CATEGORY_LABELS: ClassVar[dict[str, dict[str, str]]] = {
        "衣物":       {"需购": tr("panel.inventory.label_clothing_need_buy"),
                       "不足": tr("panel.inventory.label_clothing_need_wash"),
                       "充足": tr("panel.inventory.label_clothing_wearable")},
        "虚拟品类":   {"需购": tr("panel.inventory.label_virtual_need_renew"),
                       "不足": tr("panel.inventory.label_virtual_expiring"),
                       "充足": tr("panel.inventory.label_virtual_valid")},
        "数码电子":   {"需购": tr("panel.inventory.label_digital_need_repair"),
                       "不足": tr("panel.inventory.label_digital_to_replace"),
                       "充足": tr("panel.inventory.label_digital_normal")},
        "日常消耗品": {"需购": tr("panel.inventory.label_consumable_need_restock"),
                       "不足": tr("panel.inventory.label_consumable_running_low"),
                       "充足": tr("panel.inventory.label_consumable_ample")},
    }

    def _context_menu(self, item: dict) -> None:
        cat = item.get("category", "其他")
        labels = self.CATEGORY_LABELS.get(cat, {"需购": "需购", "不足": "不足", "充足": "充足"})
        st = item.get("status", "充足")

        menu = new_menu(self)

        for target_status in ["需购", "不足", "充足"]:
            if st != target_status:
                add_action(menu, labels[target_status],
                           lambda checked=False, s=target_status:
                           self._quick_update(item["id"], {"status": s}))

        ig = item.get("ignore_low_stock", False)
        add_action(menu,
                   tr("panel.inventory.action_restore_stock_reminder") if ig
                   else tr("panel.inventory.action_ignore_low_stock"),
                   lambda checked=False: self._quick_update(item["id"], {"ignore_low_stock": not ig}))
        add_separator(menu)
        # 寄回家 / 寄回来 = 改位置（位置就是归属）。只对**真实条目**显示 ——
        # 实例卡片传进来的是合成 dict（带 `parent_id`），按它的 id 操作会找不到条目
        if "parent_id" not in item:
            if InventoryModel.side_of(item) == SIDE_HOME:
                add_action(menu, tr("panel.inventory.action_send_back"),
                           lambda checked=False: self._set_location(
                               item["id"], DEFAULT_LOCATION))
            else:
                add_action(menu, tr("panel.inventory.action_send_home"),
                           lambda checked=False: self._set_location(
                               item["id"], HOME_LOCATION))
            add_separator(menu)
        add_action(menu, tr("panel.inventory.action_set_email_reminder"),
                   lambda checked=False: self._email_reminder(item))
        add_action(menu, tr("panel.inventory.action_edit_tags"),
                   lambda checked=False: self._edit_tags(item))
        # 会员（虚拟品类）：账号绑定信息（手机号只在这条弹窗里录）。
        # 只对**真实条目**显示 —— 实例卡片传进来的是合成 dict（带 `parent_id`）。
        if cat == MEMBERSHIP_CATEGORY and "parent_id" not in item:
            add_action(menu, tr("panel.inventory.action_edit_membership"),
                       lambda checked=False: self._edit_membership(item))
        if cat != "虚拟品类":
            add_action(menu, tr("panel.inventory.action_delete"),
                       lambda checked=False: self._delete_item(item["id"]))
        show_at_cursor(menu)

    def _quick_update(self, iid, data) -> None:
        self._dm.inventory.update_item(iid, data)
        self._dm.inventory.save()
        self._dm.data_changed.emit("inventory")
        self._refresh()

    def _set_location(self, iid: str, location: str) -> None:
        """把一条物品挪到某个位置（"寄回家 / 寄回来"就是这个 —— 位置就是归属）。

        改的是 `location` 字段：id 不变、条数不变，不会出现"删了再建"那种丢件。
        """
        self._dm.inventory.update_item(iid, {"location": location})
        self._dm.inventory.save()
        self._dm.data_changed.emit("inventory")
        self._refresh()

    def _delete_item(self, iid) -> None:
        name = next((it.get("name", iid) for it in self._dm.inventory.items if it["id"] == iid), iid)
        if QMessageBox.question(self, tr("panel.inventory.msg_confirm_delete_title"),
                                tr("panel.inventory.msg_confirm_delete", name=name)) == QMessageBox.StandardButton.Yes:
            self._dm.inventory.delete_item(iid)
            self._dm.inventory.save()
            self._dm.data_changed.emit("inventory")
            self._refresh()

    def _edit_membership(self, item: dict) -> None:
        """编辑会员信息（对话框在 `inventory_dialogs`；手机号只在那里录）。"""
        if edit_membership_dialog(self, self._dm, item):
            self._dm.data_changed.emit("inventory")
            self._refresh()

    def _edit_tags(self, item: dict) -> None:
        """改标签（对话框在 `inventory_dialogs`，见那里的说明）。"""
        if edit_tags_dialog(self, self._dm, item):
            self._dm.data_changed.emit("inventory")
            self._refresh()

    def _email_reminder(self, item: dict) -> None:
        """设补货邮件提醒（对话框在 `inventory_dialogs`）。"""
        email_reminder_dialog(self, self._dm, item)

    def _restyle_chrome(self) -> None:
        """重刷面包屑/返回按钮（颜色在 __init__ 里写死）。"""
        c = get_colors()
        self._back_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {c['accent_text']};"
            f" border: none; padding: 2px 6px; font-size: 13px; font-weight: 600; }}"
            f" QPushButton:hover {{ color: {c['fg_primary']}; }}")
        bc_btn_qss = (
            f"QPushButton {{ background: {c['bg_elevated']}; color: {c['fg_primary']};"
            f" border: none; border-radius: {RADIUS['radius_sm']}px; padding: 2px 8px;"
            f" font-size: 12px; }}"
            f" QPushButton:hover {{ background: {c['accent_bg']}; }}")
        for btn in (self._bc_cat, self._bc_group):
            btn.setStyleSheet(bc_btn_qss)
        for sep in (self._bc_sep1, self._bc_sep2):
            sep.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none;")

    def refresh_theme(self) -> None:
        self._restyle_chrome()
        self._refresh()
