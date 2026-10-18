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
from src.models.inventory import (
    DATASETS,
    DEFAULT_DATASET,
    RESTOCK_DATASET,
    InventoryModel,
)


def _requested_dataset(args) -> str:
    """`--dataset` 的**显式**取值（没传 → 空串）。

    取值合法性（`local` / `home` / `all`）由 `actions_core.SPECS` 在入口统一校验，
    这里只负责"取出来"（两处各写一遍枚举就会漂移）。

    ⚠ `update_item` 必须用这个（而不是 `_dataset_arg`）：没传时**不能**回退成
    "当前数据集" —— 那会在用户正看着"家"的时候，把一条本地物品**误搬**到家里。
    """
    return str(getattr(args, "dataset", None) or "").strip()


def _current_dataset(data) -> str:
    """文件里的当前数据集（非法值归 `local`，与 `InventoryModel.current_dataset` 同口径）。"""
    name = str(data.get("current_dataset") or DEFAULT_DATASET)
    return name if name in DATASETS else DEFAULT_DATASET


def _dataset_arg(args, data) -> str:
    """`--dataset`：没传就用**当前数据集**（界面上切换的那一份，两个入口读同一份文件）。"""
    return _requested_dataset(args) or _current_dataset(data)


def _reject_home_location(dataset: str, args) -> None:
    """家数据集不使用位置（用户口径）—— 同时传 `--location` 就是参数矛盾，拒绝。"""
    if dataset == "home" and (getattr(args, "location", None) or "").strip():
        raise ActionError(
            "家数据集不使用位置（家里一律只表示「在家」）。去掉 --location，"
            "或用 --dataset local 记到本地。")


def _dataset_note(dataset: str) -> str:
    """回执里的归属标注：本地是默认不写，家要写清楚（否则看起来像写进了本地）。"""
    return " | 归属：家" if dataset == "home" else ""


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


def _new_item_units(args) -> dict:
    """单位相关字段：单位 / 片级下限 / 每份含量 / 标签 / 各件特征。"""
    return {
        "unit": getattr(args, "unit", None) or "件",
        # 片级下限：说"剩不到 N 片/包"时用它（`min_qty` 是**同单位**的下限）
        "min_doses": getattr(args, "min_doses", None) or 0,
        "doses_per_unit": getattr(args, "doses_per_unit", None) or 1,
        "tags": _split_tag_list(getattr(args, "tags", "") or ""),
        "instances": _parse_instances(getattr(args, "instances", None)),
    }


def _new_item(iid: str, args) -> dict:
    """按命令行参数造一条物品记录（状态由 `derive_status` 统一推导，不在这里写）。"""
    return {
        "id": iid, "name": args.name, "category": args.category or "其他",
        "group": args.group or "",
        "quantity": 1 if args.quantity is None else args.quantity,
        "min_quantity": args.min_qty or 1,
        **_new_item_units(args),
        "location": args.location or "", "notes": args.notes or "",
        "created_at": now_iso(), "updated_at": now_iso(),
    }


def cmd_add_item(args) -> None:
    data = load("inventory.json")
    data.setdefault("items", [])
    data.setdefault("current_dataset", DEFAULT_DATASET)   # 命令行建出来的文件也显式带这个键
    dataset = _dataset_arg(args, data)
    _reject_home_location(dataset, args)
    item = _new_item(gen_id(data["items"], "i"), args)
    item["dataset"] = dataset
    item["status"] = InventoryModel.derive_status(item)   # 建好再推导（规则只写一份）
    added_loc = (_ensure_location(data, item.get("location", ""))
                 if dataset == "local" else None)
    data["items"].append(item)
    save("inventory.json", data)
    note = f" | 新增位置 {added_loc}" if added_loc else ""
    print(f"OK add_item {item['id']} | {args.name}{note}{_dataset_note(dataset)}")


def cmd_set_locations(args) -> None:
    """整份设置**本地数据集**的"允许位置清单"（逗号分隔）。

    位置是自由文本，但 AI 重建 / 整理时**只应从这份清单里选** —— 提示词会把清单带给它
    （`AIService._inventory_prompt`）。家数据集不使用位置，所以只有这一份词表。例：
    `set_locations --values "衣柜左1,衣柜左2,书架1"`
    """
    data = load("inventory.json")
    data["locations"] = InventoryModel.normalize_locations(
        _split_tag_list(getattr(args, "values", "") or ""))
    save("inventory.json", data)
    print(f"OK set_locations | {len(data['locations'])} 个位置（本地数据集）")


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
        it["status"] = InventoryModel.derive_status(it)
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
    min_doses = getattr(args, "min_doses", None)
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
    if min_doses is not None:
        item["min_doses"] = min_doses
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
    target = _requested_dataset(args)          # 显式传了才动归属（寄回家 / 寄回来）
    for it in data.get("items", []):
        if it["id"] != args.id:
            continue
        if target:
            _reject_home_location(target, args)
        _apply_item_updates(it, args)
        it["updated_at"] = now_iso()
        moved = ""
        if target and target != InventoryModel.dataset_of(it):
            # 寄回家 / 寄回来 = **改归属字段**，不是删了再建（id 不变，不会丢件）
            it["dataset"] = target
            moved = f" | 归属：{'家' if target == 'home' else '本地'}"
        added_loc = (_ensure_location(data, it.get("location", ""))
                     if InventoryModel.dataset_of(it) == "local" else None)
        save("inventory.json", data)
        note = f" | 新增位置 {added_loc}" if added_loc else ""
        print(f"OK update_item {args.id}{moved}{note}")
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
    """要补货的东西 —— **只看本地数据集**（家里的东西在这儿买不了，提醒了也没用）。"""
    data = load("inventory.json")
    needs = [it for it in data.get("items", [])
             if InventoryModel.dataset_of(it) == RESTOCK_DATASET
             and it.get("status") in ("需购", "不足")]
    for it in needs:
        print(f"  [{it['id']}] {it['name']} ({it['quantity']}{it.get('unit','个')}) - {it['status']}")
    if not needs:
        print("无需购物品")

def _item_extra(it: dict) -> str:
    """括号里的补充信息：片数 / 下限 / 各件数 / 标签（没有就返回空串）。"""
    extra = []
    dpu = it.get("doses_per_unit", 1) or 1
    if dpu != 1:
        extra.append(f"{it.get('quantity', 0) * dpu}片")
    if it.get("min_doses"):
        extra.append(f"下限{it['min_doses']}片")
    elif it.get("min_quantity"):
        extra.append(f"下限{it['min_quantity']}{it.get('unit', '')}")
    if it.get("instances"):
        extra.append(f"{len(it['instances'])}件各自特征")
    if it.get("tags"):
        extra.append("/".join(it["tags"]))
    return f" ({' · '.join(extra)})" if extra else ""


def _item_line(it: dict) -> str:
    """一行摘要：id 名称 数量单位 @位置 - 状态（附片数/阈值/各件数/标签）。

    家数据集**不显示位置**（用户口径），改标 `[家]` —— 否则跨数据集查找时分不清是哪边的。
    """
    ds = InventoryModel.dataset_of(it)
    loc = f" @{it['location']}" if it.get("location") and ds == "local" else ""
    tag = " [家]" if ds == "home" else ""
    return (f"  [{it['id']}] {it['name']} {it.get('quantity', 0)}{it.get('unit', '')}"
            f"{tag}{loc} - {it.get('status', '')}{_item_extra(it)}")


def _ensure_location(data: dict, location: str) -> str | None:
    """位置必须来自清单；不在就**自动加进去**（用户允许 AI 自行添加）。

    返回新加的位置名（没新增则 None），供命令回执里说明。
    """
    name = (location or "").strip()
    if not name:
        return None
    locs = data.setdefault("locations", [])
    if name in locs:
        return None
    locs.append(name)
    return name


def cmd_add_location(args) -> None:
    """给**本地数据集**的位置清单**追加**一个（不替换原有；整份替换用 `set_locations`）。"""
    data = load("inventory.json")
    name = (getattr(args, "name", "") or "").strip()
    added = _ensure_location(data, name)
    save("inventory.json", data)
    print(f"OK add_location {name}（本地数据集）" if added
          else f"OK add_location {name}（已存在）")


def _lookup_filters(args) -> list:
    """把**非空**的筛选条件变成一组判定函数（空条件不参与筛选）。

    数据驱动而不是一串 `if`：`cmd_lookup_item` 的圈复杂度会随条件数线性上涨
    （2026-10-18 一度到 D(21)，被 radon 门禁拦下）。
    """
    raw = {k: (getattr(args, k, None) or "").strip()
           for k in ("name", "category", "tag", "location")}
    checks = {
        # 名字用**双向**子串匹配：用户可能说得比记录更长（"我的纸巾盒" → "纸巾"）
        "name": lambda it: raw["name"].lower() in it["name"].lower()
        or it["name"].lower() in raw["name"].lower(),
        "category": lambda it: it.get("category", "") == raw["category"],
        "tag": lambda it: raw["tag"] in (it.get("tags") or []),
        "location": lambda it: it.get("location", "") == raw["location"],
    }
    active = [checks[k] for k in checks if raw[k]]
    if str(getattr(args, "restock", None) or "").strip() == "yes":
        # 只看需补货的 —— 与 `need_restock` 同一口径：**补货只属于本地**
        active.append(lambda it: InventoryModel.dataset_of(it) == RESTOCK_DATASET
                      and it.get("status") in ("需购", "不足"))
    return active


def cmd_lookup_item(args) -> None:
    """按**任意组合**的条件找物品：名字 / 分类 / 标签 / 位置 / 只列需补货。

    默认只查**当前数据集**（"我都有什么"问的是正在看的那一边）；`--dataset home`
    查另一边，`--dataset all` 两边都查（跨数据集找一件东西时用）。家那边的条目会
    带 `[家]` 标记、且不显示位置。

    **只查不写** —— "先查后加"的两步流程照旧。
    """
    data = load("inventory.json")
    scope = _dataset_arg(args, data)
    pool = [it for it in data.get("items", [])
            if scope == "all" or InventoryModel.dataset_of(it) == scope]
    filters = _lookup_filters(args)
    matches = [it for it in pool if all(f(it) for f in filters)]

    if not matches:
        print("NOT_FOUND")
        return
    for m in matches:
        print(_item_line(m))
    print(f"FOUND {len(matches)}")
