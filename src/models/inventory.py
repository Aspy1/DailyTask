"""Inventory model — personal item library."""

import logging
from datetime import datetime
from pathlib import Path

from src.models.base import BaseJsonModel

DEFAULT_INVENTORY = {
    "_version": 1,
    "items": [],
    "categories": ["日常消耗品", "数码电子", "衣物", "虚拟品类", "其他"],
}


logger = logging.getLogger(__name__)


class InventoryModel(BaseJsonModel):
    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_INVENTORY)

    @property
    def items(self) -> list[dict]:
        return self._data.get("items", [])

    @property
    def categories(self) -> list[str]:
        cats = self._data.get("categories")
        if not cats:
            # Repair: file created before categories key existed
            cats = list(DEFAULT_INVENTORY["categories"])
            self._data["categories"] = cats
        return cats

    def add_item(self, data: dict) -> str:
        items = self._data.setdefault("items", [])
        existing = set()
        for it in items:
            try:
                num = int(it["id"].split("_")[1])
                existing.add(num)
            except (KeyError, ValueError):
                logger.debug("InventoryModel.add_item 中忽略异常", exc_info=True)
        n = 1
        while n in existing:
            n += 1
        iid = f"i_{n:03d}"
        item = {
            "id": iid,
            "name": data.get("name", ""),
            "category": data.get("category", "其他"),
            "group": data.get("group", ""),
            "quantity": data.get("quantity", 1),
            "unit": "件",
            "status": data.get("status", "充足"),  # 充足/不足/需购
            "min_quantity": data.get("min_quantity", 1),
            "location": data.get("location", ""),
            "notes": data.get("notes", ""),
            "tags": data.get("tags", []),
            "instances": data.get("instances", []),
            "ignore_low_stock": data.get("ignore_low_stock", False),
            "doses_per_unit": data.get("doses_per_unit", 1),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        items.append(item)
        return iid

    @staticmethod
    def derive_status(quantity: int, min_quantity: int) -> str:
        """按数量与下限推导状态：`<=0` → 需购；低于下限 → 不足；否则充足。

        **规则只写一份**：`scripts/actions_cmds_items.py` 的 add / update / consume
        也调它（`CODE_STANDARDS` 的"单一真值"）。
        """
        if quantity <= 0:
            return "需购"
        if quantity < min_quantity:
            return "不足"
        return "充足"

    def update_item(self, iid: str, data: dict) -> bool:
        for it in self.items:
            if it["id"] == iid:
                for k in ("name", "category", "group", "quantity", "unit", "status",
                          "min_quantity", "location", "notes", "tags", "instances", "ignore_low_stock", "doses_per_unit"):
                    if k in data:
                        it[k] = data[k]
                it["updated_at"] = datetime.now().isoformat()
                # 状态自动推导（`ignore_low_stock` 的物品跳过 —— 那是显式豁免）。
                # ⚠ 现在**也会回到"充足"**：补货之后不该还挂着"需购"（原来不清）
                if not it.get("ignore_low_stock"):
                    it["status"] = self.derive_status(it["quantity"], it["min_quantity"])
                return True
        return False

    def delete_item(self, iid: str) -> bool:
        items = self._data.get("items", [])
        for i, it in enumerate(items):
            if it["id"] == iid:
                items.pop(i)
                return True
        return False

    def consume(self, iid: str, amount: int = 1) -> bool:
        """Consume N doses. Returns True if item still has stock."""
        for it in self.items:
            if it["id"] == iid:
                dpu = it.get("doses_per_unit", 1)
                total_doses = it["quantity"] * dpu
                total_doses -= amount
                it["quantity"] = max(0, total_doses // dpu)
                it["status"] = self.derive_status(it["quantity"], it.get("min_quantity", 1))
                if not it.get("ignore_low_stock"):
                    it["updated_at"] = __import__("datetime").datetime.now().isoformat()
                return it["quantity"] > 0
        return False

    def remaining_doses(self, iid: str) -> int:
        for it in self.items:
            if it["id"] == iid:
                return it["quantity"] * it.get("doses_per_unit", 1)
        return 0

    @property
    def need_restock(self) -> list[dict]:
        return [it for it in self.items
                if it.get("status") in ("需购", "不足") and not it.get("ignore_low_stock")]

    @property
    def all_tags(self) -> list[str]:
        tags = set()
        for it in self.items:
            for t in it.get("tags", []):
                tags.add(t)
        return sorted(tags)

    @property
    def stock_count(self) -> int:
        return len([it for it in self.items if it.get("status") == "充足"])
