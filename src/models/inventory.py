"""Inventory model — personal item library."""

import logging
from datetime import datetime
from pathlib import Path

from src.models.base import BaseJsonModel

# 数据集（用户口径 2026-10-18）：换季时把部分衣物寄回家、来年再寄回，所以需要一个
# **平行**的存放清单。
#   local = 本地（手边，区分位置）
#   home  = 家（寄回/存放，**不使用位置** —— 一律只表示"在家里"）
# 归属写在每条物品的 `dataset` 上；当前数据集记在顶层 `current_dataset` ——
# 界面与命令行读**同一份文件**，所以永远不会不一致（同 `semesters.json` 的 `current_semester`）。
DATASETS = ("local", "home")
DEFAULT_DATASET = "local"
# 补货只属于本地：家里的东西在这儿买不了，提醒了也没用（用户口径 2026-10-18）
RESTOCK_DATASET = "local"

DEFAULT_INVENTORY = {
    "_version": 1,
    "current_dataset": DEFAULT_DATASET,
    "items": [],
    "categories": ["日常消耗品", "数码电子", "衣物", "虚拟品类", "其他"],
    # **本地数据集**的允许位置清单（用户定的固定格位）。位置本身仍是自由文本，但
    # **AI 只应从这份清单里选** —— 提示词会把它带给模型（`AIService._inventory_prompt`）。
    # 家数据集不使用位置，所以只有这一份词表。
    "locations": [],
}


logger = logging.getLogger(__name__)


class InventoryModel(BaseJsonModel):
    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_INVENTORY)

    @property
    def items(self) -> list[dict]:
        """**全部**物品（两个数据集都在内）。

        ⚠ 别拿它做界面/AI 的展示 —— 用 `visible_items`。留全量是因为按 id 的增删改
        （`update_item` / `delete_item` / `consume`）必须能跨数据集找到条目，
        习惯面板挑关联物品时也不该受"当前在看哪一边"影响。
        """
        return self._data.get("items", [])

    # ── 数据集（本地 / 家）──────────────────────────────────────
    @property
    def current_dataset(self) -> str:
        """当前数据集。非法值一律归 `local`（读侧防御；写入侧由命令层校验）。"""
        name = str(self._data.get("current_dataset") or DEFAULT_DATASET)
        return name if name in DATASETS else DEFAULT_DATASET

    def set_dataset(self, name: str) -> bool:
        """切换当前数据集；非法名字返回 `False`（不改数据）。"""
        if name not in DATASETS:
            return False
        self._data["current_dataset"] = name
        return True

    @staticmethod
    def dataset_of(item: dict) -> str:
        """这条物品属于哪个数据集：老数据没有该字段 → 本地。"""
        name = str(item.get("dataset") or DEFAULT_DATASET)
        return name if name in DATASETS else DEFAULT_DATASET

    @property
    def visible_items(self) -> list[dict]:
        """**当前数据集**里的物品（界面与 AI 提示词都用它）。"""
        cur = self.current_dataset
        return [it for it in self.items if self.dataset_of(it) == cur]

    @property
    def allowed_locations(self) -> list[str]:
        """当前数据集**允许**的位置：家不使用位置（用户口径）→ 空。"""
        return self.locations if self.current_dataset == "local" else []

    def move_item(self, iid: str, dataset: str) -> bool:
        """把一条物品换数据集（寄回家 / 寄回来）。

        **改归属字段，不是删了再建** —— id 不变，所以不存在"删掉成功、新建失败"的丢件，
        也不会因为两个数据集各自都有 `i_001` 而撞车。这正是选"归属字段"而非
        "两个平行文件"的核心理由（见 `dev-logs/2026-10-18-库存数据集切换.md`）。
        """
        if dataset not in DATASETS:
            return False
        for it in self.items:
            if it["id"] == iid:
                it["dataset"] = dataset
                it["updated_at"] = datetime.now().isoformat()
                return True
        return False

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
            "dataset": data.get("dataset") or self.current_dataset,
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
    def need_restock(self) -> list[dict]:
        """需要补货的物品 —— **只看本地数据集**。

        家里的东西在这儿买不了，提醒了也没用（用户口径 2026-10-18）；所以这里**不看**
        `current_dataset`，与"用户正在看哪一边"无关。
        """
        return [it for it in self.items
                if self.dataset_of(it) == RESTOCK_DATASET
                and it.get("status") in ("需购", "不足")
                and not it.get("ignore_low_stock")]

    @property
    def locations(self) -> list[str]:
        """允许的位置清单（用户定的固定格位）；键缺失就补一份（老文件没有这个键）。"""
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
        """当前数据集的标签（界面标签筛选用；不该出现另一边的标签）。"""
        tags = set()
        for it in self.visible_items:
            for t in it.get("tags", []):
                tags.add(t)
        return sorted(tags)

    @property
    def stock_count(self) -> int:
        return len([it for it in self.visible_items if it.get("status") == "充足"])
