"""库存面板的「单件卡片」渲染。

从 `inventory_panel.py` 抽出来（那个文件与 `InventoryPanel` 类都顶在尺寸上限上，
加一行就得挪一行 —— 见 `scripts/quality_baseline.json`）。

只依赖面板传进来的两个属性（`_context_menu` / `_card_layout`），不动面板状态。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.i18n.loader import tr
from src.ui.styles.cards import card as make_card
from src.ui.styles.theme import (
    CONTROLS,
    SIZE_BODY_S,
    SIZE_CAPTION,
    SIZE_TINY,
    SPACING,
    rgba,
)

STATUS_COLORS = {"需购": "red", "不足": "orange", "充足": "green"}
BADGE_RADIUS = 8


def render_instance_card(panel, c: dict, parent_id: str, idx: int, inst: dict,
                         parent: dict) -> None:
    """一条"件"卡片：#序号 + 标签 + 状态徽章 + 备注 + 右键菜单。"""
    card = make_card("sub", pad="spacing_none")
    card.setMinimumHeight(CONTROLS["circle_badge"])

    cl = QHBoxLayout(card)
    cl.setContentsMargins(12, 8, 12, 8)
    cl.setSpacing(6)

    label = QLabel(f"#{idx + 1}")
    label.setStyleSheet(
        f"color: {c['fg_hint']}; font-size: {SIZE_CAPTION}px; font-weight: 600;"
        " border: none; background: transparent;")
    cl.addWidget(label)

    tags = inst.get("tags", [])
    for tag in tags:
        t = QLabel(tag)
        t.setStyleSheet(
            f"color: {c['accent_text']}; font-size: {SIZE_TINY}px; font-weight: 500;"
            f" background: {rgba(c['accent'], 0.1)}; border-radius: {BADGE_RADIUS}px;"
            " padding: 1px 8px; border: none;")
        cl.addWidget(t)

    status = inst.get("status") or tr("panel.inventory.label_consumable_ample")
    bc = c[STATUS_COLORS.get(status, "green")]
    badge = QLabel(status)
    badge.setStyleSheet(
        f"color: {bc}; font-size: {SIZE_TINY}px; font-weight: 600;"
        f" background: {rgba(bc, 0.1)}; border-radius: {BADGE_RADIUS}px;"
        " padding: 1px 6px; border: none;")
    cl.addWidget(badge)

    note = inst.get("notes", "")
    if note:
        n = QLabel(note)
        n.setStyleSheet(
            f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px;"
            " border: none; background: transparent;")
        cl.addWidget(n)

    cl.addStretch()

    inst_item = {"id": f"{parent_id}_{idx}", "parent_id": parent_id, "index": idx,
                 "name": parent.get("name", ""), "tags": tags, "status": status,
                 "notes": note, "inst_data": inst}
    card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    card.customContextMenuRequested.connect(
        lambda _, i=inst_item: panel._context_menu(i))
    # 层级缩进：QSS 的 `margin-left` 只改内容区，缩不了卡片本身 → 外面套一层带左边距的行。
    # ⚠ 用**容器控件**而不是嵌套 layout：`_refresh()` 靠 `item.widget()` 清卡，
    # 嵌套 layout 的 `item.widget()` 是 None → 旧卡不会被删、会留在屏幕上。
    row = QWidget()
    rl = QHBoxLayout(row)
    rl.setContentsMargins(SPACING["spacing_xxl"], 0, 0, 0)
    rl.setSpacing(0)
    rl.addWidget(card)
    panel._card_layout.insertWidget(panel._card_layout.count() - 1, row)
