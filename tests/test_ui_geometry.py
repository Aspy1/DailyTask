"""§6.3 运行时几何边界（第四批「布局适应」的收尾）。

三条边界各一个守卫，全部**跑真控件**（不是读代码）：

1. **数据边界**：空库存 → 新增一个缺货物品 → 卡片要出来。
   典型退化是"空过一次就再也不刷新"（提前 return / 缓存的空列表）。
2. **内容边界**：很多标签在窄宽度下必须**换行增高**，且不能溢出网格右边界。
3. **空间边界**：AI 面板被压到很窄时仍保住可用宽度（输入框不能被挤成 0）。

⚠ 本文件会造顶层控件：测完按**安全顺序**清掉（见 `test_ui_button_states.py` 的说明），
否则解释器退出时 Qt 乱序销毁 → CI 的 3.12 job 偶发"全过但退出码 1"。
"""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from src.models.inventory import InventoryModel
from src.ui.styles.cards import Card


@pytest.fixture(autouse=True)
def _drop_widgets_created_here(qapp) -> Iterator[None]:
    from PySide6.QtWidgets import QApplication

    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    QApplication.processEvents()


class _StubDataManager:
    """面板只用到 `dm.inventory` —— 挂**真模型**、只预置 `items`（同 `test_inventory_panel`）。"""

    def __init__(self, items: list[dict], tmp_path) -> None:
        self.inventory = InventoryModel(tmp_path / "inventory.json")
        self.inventory.data["items"] = items


def _panel(qapp, items: list[dict], tmp_path) -> tuple[QWidget, _StubDataManager]:
    from src.ui.panels.inventory_panel import InventoryPanel

    stub = _StubDataManager(items, tmp_path)
    panel = InventoryPanel(stub)
    panel.resize(420, 600)
    panel.show()
    qapp.processEvents()
    return panel, stub


OUT_OF_STOCK = {"id": "i_001", "name": "牙膏", "category": "日常消耗品", "group": "",
                "quantity": 0, "min_quantity": 1, "unit": "支", "status": "需购",
                "tags": [], "instances": []}


def _labels(widget) -> str:
    return " ".join(w.text() for w in widget.findChildren(QLabel))


def test_inventory_panel_renders_after_empty_then_out_of_stock(qapp, tmp_path) -> None:
    """空库存 → 新增一个缺货物品 → 计数与卡片都要出来。

    典型退化是"空过一次就再也不刷新"（提前 return / 缓存了空列表）。
    """
    panel, stub = _panel(qapp, [], tmp_path)
    assert "共 0 件物品" in _labels(panel), "空库存时计数应为 0"

    stub.inventory.data["items"] = [dict(OUT_OF_STOCK)]
    panel._refresh()
    qapp.processEvents()

    assert "共 1 件物品" in _labels(panel), "新增后计数要更新"
    assert panel.findChildren(Card), "新增物品后应渲染出卡片"


def test_out_of_stock_item_lands_in_its_category(qapp, tmp_path) -> None:
    """缺货物品要出现在它分类的计数里 —— 分类卡是入口，计数错了用户就找不到它。"""
    panel, _ = _panel(qapp, [dict(OUT_OF_STOCK)], tmp_path)
    labels = _labels(panel)
    assert "日常消耗品" in labels
    assert "1 件" in labels


def test_many_tags_wrap_instead_of_overflowing(qapp) -> None:
    """标签自然宽度流式：窄宽度下换行增高，且不越出网格右边界。"""
    from src.ui.widgets.flow_grid import FlowGrid

    grid = FlowGrid(uniform=False)
    grid.resize(240, 100)
    for i in range(12):
        QLabel(f"标签{i}很长的一段文字", grid).show()
    grid._layout_children()
    qapp.processEvents()

    labels = [w for w in grid.children() if isinstance(w, QLabel)]
    assert len(labels) == 12
    right = max(w.x() + w.width() for w in labels)
    assert right <= grid.width() + 1, f"标签溢出右边界：{right} > {grid.width()}"
    assert grid.heightForWidth(240) > grid.heightForWidth(900), "窄了应当更高（换行）"


def test_ai_panel_keeps_usable_width_when_narrow(qapp) -> None:
    """AI 面板被压窄时保住可用宽度 —— 输入框不能被挤成 0。"""
    from src.ui.components.ai_panel import AIPanel

    panel = AIPanel()
    panel.resize(300, 600)
    panel.show()
    qapp.processEvents()

    assert panel.minimumWidth() == 260, "窄窗口下限"
    assert panel._input.width() > 100, f"输入框被挤到 {panel._input.width()}"
