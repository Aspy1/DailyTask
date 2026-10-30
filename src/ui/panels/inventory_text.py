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
from src.models.billing import (
    due_day_of,
    installments_of,
    is_active,
    is_billing,
    monthly_amount,
    remaining,
)
from src.models.inventory import MEMBERSHIP_CATEGORY, InventoryModel


def quantity_text(it: dict) -> str:
    """一张卡上的数量：**一律以 `remaining_doses` 为真值**，不许拿盒数硬乘。

    有分装、且整包装为 0 时，散装的量**必须**露出来（`x0 (23次)`）——
    否则读起来就是"没了"。
    """
    boxes, loose, dpu = InventoryModel.stock_parts(it)
    if it.get("category", "") == MEMBERSHIP_CATEGORY:
        return tr("panel.inventory.qty_virtual_items", n=boxes)
    if dpu > 1 and loose:
        return tr("panel.inventory.qty_with_doses", n=boxes, doses=loose)
    return tr("panel.inventory.qty_pieces", n=boxes)


def billing_text(it: dict) -> str:
    """月付 / 分期的账单行（不是账单 → 空串）。

    用户口径（2026-10-31）：只填「每月几号」；分期**只填不算** —— 所以这里只复述
    用户填的数字（几期、每期多少），不显示"总价 / 剩余本金"这类**算出来的**东西 ✗。
    """
    if not is_billing(it):
        return ""
    amount = f"{monthly_amount(it):g}"
    day = due_day_of(it) or 0
    total = installments_of(it)
    if not is_active(it):
        if total:
            return tr("panel.inventory.billing_done", total=total)
        return tr("panel.inventory.billing_stopped")
    if total is None:
        return tr("panel.inventory.billing_monthly", amount=amount, day=day)
    return tr("panel.inventory.billing_installment", amount=amount, total=total,
              left=remaining(it) or 0, day=day)
