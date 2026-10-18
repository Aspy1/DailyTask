"""Inventory model — personal item library."""

import logging
from datetime import datetime
from pathlib import Path

from src.models.base import BaseJsonModel

# 位置是**唯一的归属信号**（用户口径 2026-10-18）：换季把衣物寄回家、来年寄回，所以
# "在哪一边"要能表达出来 —— 但**不单独存字段**，而是**由位置推导**：
#   说了位置 → 就用那个位置；没说 → 默认「学校」。
# 这样模型只需要会**抄位置**，不用去猜"家里"指哪边（flash 模型中文不稳，靠猜必错 ——
# 2026-10-18 探针实测：它把"家里抽纸"记成了"寄回家的那批"）。
DEFAULT_LOCATION = "学校"
# 「家」那一侧的位置（`HOME_LOCATION` 是主格位，"老家"是同义写法）。**其余位置（宿舍格位、
# "学校"、后来新增的）都算学校侧。** 判断"哪一边"只有这一处规则 —— 一律走 `side_of()`。
HOME_LOCATION = "家"
HOME_LOCATIONS = (HOME_LOCATION, "老家")
SIDE_SCHOOL = "school"
SIDE_HOME = "home"

DEFAULT_INVENTORY = {
    "_version": 1,
    "items": [],
    "categories": ["日常消耗品", "数码电子", "衣物", "虚拟品类", "其他"],
    # 允许的位置清单（用户定的固定格位 + 「学校」「家」两个粗格位）。位置本身仍是自由文本，
    # 但**AI 只应从这份清单里选** —— 提示词会把它带给模型（`AIService._inventory_prompt`）。
    "locations": [DEFAULT_LOCATION, *HOME_LOCATIONS],
}


logger = logging.getLogger(__name__)


class InventoryModel(BaseJsonModel):
    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_INVENTORY)

    @property
    def items(self) -> list[dict]:
        """全部物品（两边都在内）—— 界面按 `side_of()` 分边显示。"""
        return self._data.get("items", [])

    # ── 归属（学校 / 家）：由**位置**推导，不存字段 ──────────────
    @staticmethod
    def side_of(item: dict) -> str:
        """这条物品在**哪一边**：位置属于「家」那一侧 → `home`，否则 `school`。

        判断规则**只有这一处**（`HOME_LOCATIONS`）—— 界面切换、补货范围、命令回执都用它，
        免得"哪边算家"在多处各写一遍。
        """
        return SIDE_HOME if item.get("location") in HOME_LOCATIONS else SIDE_SCHOOL

    @property
    def need_restock(self) -> list[dict]:
        """需要补货的物品 —— **只看学校那一侧**。

        家里的东西在这儿买不了，提醒了也没用（用户口径 2026-10-18）。
        """
        return [it for it in self.items
                if self.side_of(it) == SIDE_SCHOOL
                and it.get("status") in ("需购", "不足")
                and not it.get("ignore_low_stock")]

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
            "status": data.get("status") or self.derive_status(data),
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
    def derive_status(item: dict) -> str:
        """按**单位级**下限 `min_quantity` 与**片级**下限 `min_doses` 推导状态。

        规则（`CODE_STANDARDS` 单一真值）：`quantity <= 0` → 需购；低于下限 → 不足；
        否则充足。两个下限同时给了**以片级为准**（`quantity × doses_per_unit < min_doses`）
        —— 它才对应"剩不到 5 片就提醒我买"（2026-10-18 探针发现的单位错位：
        `--min_qty 5` 是"5 盒"，与用户说的"5 片"差 24 倍）。
        """
        quantity = item.get("quantity", 1)
        if quantity <= 0:
            return "需购"
        min_doses = item.get("min_doses", 0) or 0
        if min_doses > 0:
            doses = quantity * (item.get("doses_per_unit", 1) or 1)
            return "不足" if doses < min_doses else "充足"
        return "不足" if quantity < item.get("min_quantity", 1) else "充足"

    def update_item(self, iid: str, data: dict) -> bool:
        for it in self.items:
            if it["id"] == iid:
                for k in ("name", "category", "group", "quantity", "unit", "status",
                          "min_quantity", "min_doses", "location", "notes", "tags",
                          "instances", "ignore_low_stock", "doses_per_unit"):
                    if k in data:
                        it[k] = data[k]
                it["updated_at"] = datetime.now().isoformat()
                # 状态自动推导（`ignore_low_stock` 的物品跳过 —— 那是显式豁免）。
                # ⚠ 现在**也会回到"充足"**：补货之后不该还挂着"需购"（原来不清）
                if not it.get("ignore_low_stock"):
                    it["status"] = self.derive_status(it)
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
                it["status"] = self.derive_status(it)
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
    def locations(self) -> list[str]:
        """允许的位置清单（用户定的固定格位 + 「学校」「家」）；键缺失就补一份（老文件没有）。"""
        locs = self._data.get("locations")
        if not locs:
            locs = list(DEFAULT_INVENTORY["locations"])
            self._data["locations"] = locs
        return locs

    @staticmethod
    def normalize_locations(values: list[str]) -> list[str]:
        """去空白 + 去重，保持传入顺序（命令层与界面共用同一套规则）。"""
        seen: list[str] = []
        for v in values:
            name = v.strip()
            if name and name not in seen:
                seen.append(name)
        return seen

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
