"""物品（「有什么」）命令：增 / 改 / 删 / 查 / 需购。

从 `scripts/actions.py` 搬出来（那里 807 行，超「单文件 ≤800」）。这一组命令
自成一个领域，依赖的读写/校验工具都在 `actions_core.py`。
"""

import json

from scripts.actions_core import (
    ActionError,
    gen_id,
    load,
    now_iso,
    save,
)
from src.models.inventory import InventoryModel


def _parse_instances(raw: str | None) -> list[dict]:
    """`--instances` 传 JSON 数组（写法同 `replace_plans --plans`）。

    每项是这一"件"的特征，例如
    `[{"tags": ["Type-C"], "notes": "1 米"}, {"tags": ["Lightning"]}]`。
    **同类物品不同特征**靠它表达（一条物品 + 多个 instances），
    而不是硬拆成两条互不相关的物品。
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ActionError(f"--instances 不是合法 JSON：{e}") from e
    if not isinstance(parsed, list) or not all(isinstance(x, dict) for x in parsed):
        raise ActionError("--instances 必须是 JSON 对象数组")
    return parsed


def cmd_add_item(args) -> None:
    data = load("inventory.json")
    data.setdefault("items", [])
    iid = gen_id(data["items"], "i")
    qty = 1 if args.quantity is None else args.quantity
    min_qty = args.min_qty or 1
    item = {"id": iid, "name": args.name, "category": args.category or "其他",
            "group": args.group or "",
            "quantity": qty, "unit": getattr(args, "unit", None) or "件",
            # 状态按数量与下限推导（原来只判 qty<=0 → "1 件 / 下限 5" 也记成充足 ✗）
            "status": InventoryModel.derive_status(qty, min_qty),
            "min_quantity": min_qty,
            "location": args.location or "", "notes": args.notes or "",
            "tags": _split_tag_list(getattr(args, "tags", "") or ""),
            "instances": _parse_instances(getattr(args, "instances", None)),
            "doses_per_unit": getattr(args, "doses_per_unit", None) or 1,
            "created_at": now_iso(), "updated_at": now_iso()}
    data["items"].append(item)
    save("inventory.json", data)
    print(f"OK add_item {iid} | {args.name}")


def cmd_consume(args) -> None:
    """消耗 N 份（默认 1）：按 `doses_per_unit` 扣减 + 重算状态。

    "用掉一瓶洗手液" → `consume --id i_003`，不必先查数量再手算（原来只能
    `lookup_item` 查完再 `update_item --quantity N-1`）。
    """
    data = load("inventory.json")
    amount = args.amount or 1
    for it in data.get("items", []):
        if it["id"] != args.id:
            continue
        dpu = it.get("doses_per_unit", 1) or 1
        it["quantity"] = max(0, (it.get("quantity", 0) * dpu - amount) // dpu)
        it["status"] = InventoryModel.derive_status(it["quantity"],
                                                    it.get("min_quantity", 1))
        it["updated_at"] = now_iso()
        save("inventory.json", data)
        print(f"OK consume {args.id} | 剩 {it['quantity']}{it.get('unit', '件')}"
              f"（{it['status']}）")
        return
    raise ActionError(f"没有 id 为 {args.id} 的物品 —— 先用 lookup_item 查一下")

def _apply_item_quantity_fields(item: dict, args) -> None:
    """数量/单位/状态/下限：仅当显式传值才覆盖。

    ⚠ 全部走 `getattr`：`update_*` 不注入默认值，属性可能不存在
    （旧实现直接 `args.quantity` → AttributeError，日志里那条
    `ERROR 'Namespace' object has no attribute 'unit'` 就是这个）。
    """
    quantity = getattr(args, "quantity", None)
    unit = getattr(args, "unit", None)
    status = getattr(args, "status", None)
    min_qty = getattr(args, "min_qty", None)
    dpu = getattr(args, "doses_per_unit", None)
    instances = getattr(args, "instances", None)
    if quantity is not None:
        item["quantity"] = quantity
    if unit:
        item["unit"] = unit
    if status:
        item["status"] = status
    if min_qty is not None:
        item["min_quantity"] = min_qty
    if dpu is not None:
        item["doses_per_unit"] = dpu
    if instances is not None:
        item["instances"] = _parse_instances(instances)


def _split_tag_list(tags: str) -> list[str]:
    """逗号分隔标签 → 去空白后的非空列表。"""
    return [t.strip() for t in tags.split(",") if t.strip()]


def _apply_item_updates(item: dict, args) -> None:
    """把命令行传入的非空字段写回物品条目（保持原有字段写入顺序）。"""
    name = getattr(args, "name", None)
    group = getattr(args, "group", None)
    category = getattr(args, "category", None)
    location = getattr(args, "location", None)
    tags = getattr(args, "tags", None)
    if name:
        item["name"] = name
    if group:
        item["group"] = group
    if category:
        item["category"] = category
    _apply_item_quantity_fields(item, args)
    if location:
        item["location"] = location
    if tags:
        item["tags"] = _split_tag_list(tags)


def cmd_update_item(args) -> None:
    data = load("inventory.json")
    for it in data.get("items", []):
        if it["id"] != args.id:
            continue
        _apply_item_updates(it, args)
        it["updated_at"] = now_iso()
        save("inventory.json", data)
        print(f"OK update_item {args.id}")
        return
    print(f"ERROR item not found: {args.id}")

def cmd_delete_item(args) -> None:
    data = load("inventory.json")
    iid = args.id
    items = data.get("items", [])
    for i, it in enumerate(items):
        if it["id"] == iid:
            removed = items.pop(i)
            save("inventory.json", data)
            print(f"OK delete_item {iid} | {removed.get('name','')}")
            return
    print(f"ERROR item not found: {iid}")


def cmd_need_restock(args) -> None:
    data = load("inventory.json")
    needs = [it for it in data.get("items", []) if it.get("status") in ("需购", "不足")]
    for it in needs:
        print(f"  [{it['id']}] {it['name']} ({it['quantity']}{it.get('unit','个')}) - {it['status']}")
    if not needs:
        print("无需购物品")

def cmd_lookup_item(args) -> None:
    data = load("inventory.json")
    name = args.name.strip().lower()
    matches = []
    for it in data.get("items", []):
        iname = it["name"].lower()
        if name in iname or iname in name:
            matches.append(it)
    if matches:
        for m in matches:
            loc = m.get("location", "")
            loc_str = f" @{loc}" if loc else ""
            print(f"  [{m['id']}] {m['name']} ({m['quantity']}件) - {m['status']}{loc_str}")
        print(f"FOUND {len(matches)}")
    else:
        print("NOT_FOUND")
