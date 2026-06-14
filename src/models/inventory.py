"""Inventory model — personal item library."""

from datetime import datetime
from pathlib import Path

from src.models.base import BaseJsonModel

DEFAULT_INVENTORY = {
    "_version": 1,
    "items": [],
    "categories": ["日常消耗品", "数码电子", "衣物", "虚拟品类", "其他"],
}


class InventoryModel(BaseJsonModel):
    def __init__(self, file_path: Path):
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
                pass
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

    def update_item(self, iid: str, data: dict) -> bool:
        for it in self.items:
            if it["id"] == iid:
                for k in ("name", "category", "group", "quantity", "unit", "status",
                          "min_quantity", "location", "notes", "tags", "instances", "ignore_low_stock", "doses_per_unit"):
                    if k in data:
                        it[k] = data[k]
                it["updated_at"] = datetime.now().isoformat()
                # Auto-set status (skip if ignore_low_stock)
                if not it.get("ignore_low_stock"):
                    if it["quantity"] <= 0:
                        it["status"] = "需购"
                    elif it["quantity"] < it["min_quantity"]:
                        it["status"] = "不足"
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
                if it["quantity"] <= 0:
                    it["status"] = "需购"
                elif it["quantity"] < it.get("min_quantity", 1):
                    it["status"] = "不足"
                else:
                    it["status"] = "充足"
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
