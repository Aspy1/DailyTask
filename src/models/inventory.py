"""Inventory model — personal item library."""

from datetime import datetime
from pathlib import Path

from src.models.base import BaseJsonModel

DEFAULT_INVENTORY = {
    "_version": 1,
    "items": [],
    "categories": ["日用品", "食品饮料", "学习用品", "数码电子", "衣物", "药品", "其他"],
}


class InventoryModel(BaseJsonModel):
    def __init__(self, file_path: Path):
        super().__init__(file_path, DEFAULT_INVENTORY)

    @property
    def items(self) -> list[dict]:
        return self._data.get("items", [])

    @property
    def categories(self) -> list[str]:
        return self._data.get("categories", ["其他"])

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
            "quantity": data.get("quantity", 1),
            "unit": data.get("unit", "个"),
            "status": data.get("status", "充足"),  # 充足/不足/需购
            "min_quantity": data.get("min_quantity", 1),
            "location": data.get("location", ""),
            "notes": data.get("notes", ""),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        items.append(item)
        return iid

    def update_item(self, iid: str, data: dict) -> bool:
        for it in self.items:
            if it["id"] == iid:
                for k in ("name", "category", "quantity", "unit", "status",
                          "min_quantity", "location", "notes"):
                    if k in data:
                        it[k] = data[k]
                it["updated_at"] = datetime.now().isoformat()
                # Auto-set status based on quantity vs min
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

    @property
    def need_restock(self) -> list[dict]:
        return [it for it in self.items if it.get("status") in ("需购", "不足")]

    @property
    def stock_count(self) -> int:
        return len([it for it in self.items if it.get("status") == "充足"])
