"""物品（「有什么」）命令：增 / 改 / 删 / 查 / 需购。

从 `scripts/actions.py` 搬出来（那里 807 行，超「单文件 ≤800」）。这一组命令
自成一个领域，依赖的读写/校验工具都在 `actions_core.py`。
"""

from scripts.actions_core import (
    ActionError,  # noqa: F401 — 与其它命令模块保持一致的导出面
    gen_id,
    load,
    now_iso,
    save,
)


def cmd_add_item(args) -> None:
    data = load("inventory.json")
    data.setdefault("items", [])
    iid = gen_id(data["items"], "i")
    qty = 1 if args.quantity is None else args.quantity
    item = {"id": iid, "name": args.name, "category": args.category or "其他",
            "group": args.group or "",
            "quantity": qty, "unit": "件",
            "status": "需购" if qty <= 0 else "充足",
            "min_quantity": args.min_qty or 1,
            "location": args.location or "", "notes": args.notes or "",
            "created_at": now_iso(), "updated_at": now_iso()}
    data["items"].append(item)
    save("inventory.json", data)
    print(f"OK add_item {iid} | {args.name}")

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
    if quantity is not None:
        item["quantity"] = quantity
    if unit:
        item["unit"] = unit
    if status:
        item["status"] = status
    if min_qty is not None:
        item["min_quantity"] = min_qty


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
