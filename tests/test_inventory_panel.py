"""`inventory_panel` 的卡片渲染守卫。

这个面板此前**没有任何测试覆盖**。这一批把它的 5 张卡从"内联 QSS 的 QWidget"
改成自绘 `Card`，并把"子项缩进"从 QSS `margin-left`（只改内容区、缩不了卡片本身）
改成外层**容器控件**。两处都容易悄悄退回去：

1. 子项卡必须挂在**容器控件**上 —— `_refresh()` 靠 `item.widget()` 清卡，
   若改用嵌套 layout，`item.widget()` 是 None → 旧卡不会被删、会留在屏幕上。
2. 刷新多次后卡片数不能累积（清卡确实生效）。

面板只读 `dm.inventory` 的 `items` / `categories` / `all_tags`，所以用 stub 驱动即可。
"""

from PySide6.QtCore import QCoreApplication, QEvent, QPoint
from PySide6.QtWidgets import QWidget

from src.ui.styles.cards import Card
from src.ui.styles.theme import SPACING

ITEM = {"id": "i_001", "name": "创可贴", "category": "药品", "group": "急救",
        "quantity": 2, "status": "充足", "tags": ["急救"], "instances": []}


class _StubInventory:
    def __init__(self, items: list[dict]) -> None:
        self.items = items

    @property
    def categories(self) -> list[str]:
        return sorted({it.get("category", "其他") for it in self.items})

    @property
    def all_tags(self) -> list[str]:
        return sorted({t for it in self.items for t in it.get("tags", [])})


class _StubDataManager:
    def __init__(self, items: list[dict]) -> None:
        self.inventory = _StubInventory(items)


def _panel(qapp, items: list[dict]) -> QWidget:
    from src.ui.panels.inventory_panel import InventoryPanel

    panel = InventoryPanel(_StubDataManager(items))
    panel.resize(420, 600)
    panel.show()
    qapp.processEvents()
    return panel


def _flush_deletes() -> None:
    """`deleteLater()` 是延迟删除，不等事件循环跑过就不会真的消失。"""
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_refresh_does_not_accumulate_cards(qapp) -> None:
    panel = _panel(qapp, [ITEM])
    first = len(panel.findChildren(Card))
    assert first > 0, "分类视图至少应渲染出一张卡片"

    for _ in range(3):
        panel._refresh()
        _flush_deletes()

    assert len(panel.findChildren(Card)) == first, "刷新不应累积旧卡片"


def test_instance_cards_are_indented_via_wrapper(qapp) -> None:
    panel = _panel(qapp, [ITEM])
    # 直接摆到"组视图 + 已展开"，省去逐级点击
    panel._current_category = "药品"
    panel._current_group = "急救"
    panel._expanded_items = {"i_001"}
    panel._refresh()
    qapp.processEvents()

    cards = panel.findChildren(Card)
    subs = [w for w in cards if w.variant == "sub"]
    assert subs, "展开的实例卡应使用 `sub` 变体"
    parent_card = next((w for w in cards if w.variant == "item"), None)
    assert parent_card is not None, "组视图应有一张 `item` 变体的类型卡"

    def x_in_container(w: QWidget) -> int:
        return w.mapTo(panel._container, QPoint(0, 0)).x()

    offset = x_in_container(subs[0]) - x_in_container(parent_card)
    assert offset == SPACING["spacing_xxl"], (
        f"实例卡相对类型卡应缩进 {SPACING['spacing_xxl']}px，实际 {offset}px")
