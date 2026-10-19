"""库存的**界面文字**：数量展示的唯一口径。

为什么单独一个文件：
1. `inventory_panel.py` 已顶到尺寸上限（文件 800 行 / 类 400 行，存量见
   `scripts/quality_baseline.json`），**不能再往里塞**；
2. 数量口径本来就只该有一处 —— 2026-10-19 审查 R2：真值（`remaining_doses`）
   算对了，但界面 / `lookup_item` / AI 摘要**各自重算**，于是 1 盒 24 片扣 1 片
   仍然显示成 `x0`，用户和模型都以为没库存了。

（CLI / AI 摘要走 `InventoryModel.stock_text()`，纯文本、不带 i18n。）
"""

from src.i18n.loader import tr
from src.models.inventory import InventoryModel


def quantity_text(it: dict) -> str:
    """一张卡上的数量：**一律以 `remaining_doses` 为真值**，不许拿盒数硬乘。

    有分装、且整包装为 0 时，散装的量**必须**露出来（`x0 (23次)`）——
    否则读起来就是"没了"。
    """
    boxes, loose, dpu = InventoryModel.stock_parts(it)
    if it.get("category", "") == "虚拟品类":
        return tr("panel.inventory.qty_virtual_items", n=boxes)
    if dpu > 1 and loose:
        return tr("panel.inventory.qty_with_doses", n=boxes, doses=loose)
    return tr("panel.inventory.qty_pieces", n=boxes)
