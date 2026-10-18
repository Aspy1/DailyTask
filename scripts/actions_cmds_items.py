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
from src.models.inventory import DEFAULT_LOCATION, SIDE_SCHOOL, InventoryModel, apply_consume

# `--membership` 允许的键（用户名 / 到期日 / 自动续费 / 续费月数）。
# **手机号不在这里** —— 它不进 `inventory.json`（见 `models/membership_contacts.py`）。
MEMBERSHIP_KEYS = ("username", "expires_on", "auto_renew", "renew_months")


def _default_location(item: dict, args) -> str:
    """**没说位置时的默认归属**：学校（用户口径 2026-10-18）。

    位置是唯一的归属信号，所以"没说位置"必须落在一个**确定的值**上 —— 不让模型自己挑。

    ⚠ 虚拟品类（会员之类）不吃这个默认 —— "学校"对它们没有意义，留空更诚实。
    """
    explicit = (getattr(args, "location", None) or "").strip()
    if explicit:
        return explicit
    if (item.get("category") or "") == "虚拟品类":
        return ""
    return DEFAULT_LOCATION


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


def _parse_membership(raw: str | None) -> dict:
    """`--membership` 传 JSON 对象（写法同 `--instances`）。

    例：`{"username":"my_qq","expires_on":"2027-03-15","auto_renew":true,"renew_months":12}`

    ⚠ **不要**在这里放手机号 —— `inventory.json` 会同步到 GitHub，手机号是私有的
    （只在面板弹窗里录，见 `models/membership_contacts.py`）。写进来直接拒绝。
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ActionError(f"--membership 不是合法 JSON：{e}") from e
    if not isinstance(parsed, dict):
        raise ActionError("--membership 必须是 JSON 对象")
    if "phone" in parsed or "手机号" in parsed:
        raise ActionError(
            "手机号不能写进 inventory.json（它会同步到 GitHub）。"
            "请在面板的会员弹窗里录，或放 data/private/memberships.json")
    unknown = set(parsed) - set(MEMBERSHIP_KEYS)
    if unknown:
        raise ActionError(
            f"--membership 只接受 {'、'.join(MEMBERSHIP_KEYS)}，收到 {sorted(unknown)}")
    return parsed


def _apply_membership(item: dict, args) -> None:
    """把 `--membership` 写进物品（**整组替换**）；没传就什么都不做。

    传空对象 `{}` = 清掉会员信息（键一并删掉，不留空壳）。
    """
    raw = getattr(args, "membership", None)
    if raw is None or not str(raw).strip():
        return
    parsed = _parse_membership(raw)
    if parsed:
        item["membership"] = parsed
    else:
        item.pop("membership", None)


def cmd_add_item(args) -> None:
    data = load("inventory.json")
    data.setdefault("items", [])
    item = _new_item(gen_id(data["items"], "i"), args)
    item["location"] = _default_location(item, args)      # 没说位置 → 默认「学校」
    _apply_membership(item, args)                         # 会员信息（有到期日就由它定状态）
    InventoryModel.sync_units(item)                       # 精确余量（片）= 盒数 × 每份含量
    item["status"] = InventoryModel.derive_status(item)   # 建好再推导（规则只写一份）
    added_loc = _ensure_location(data, item["location"])
    data["items"].append(item)
    save("inventory.json", data)
    note = f" | 新增位置 {added_loc}" if added_loc else ""
    print(f"OK add_item {item['id']} | {args.name}{note}")


def cmd_set_locations(args) -> None:
    """整份设置"允许的位置清单"（逗号分隔）。

    位置是自由文本，但 AI 重建 / 整理时**只应从这份清单里选** —— 提示词会把清单带给它
    （`AIService._inventory_prompt`）。清单里应有宿舍格位 + 「学校」「家」两个粗格位
    （「家」= 寄回/存放那一侧）。例：
    `set_locations --values "衣柜左1,衣柜左2,书架1,学校,家"`
    """
    data = load("inventory.json")
    data["locations"] = InventoryModel.normalize_locations(
        _split_tag_list(getattr(args, "values", "") or ""))
    save("inventory.json", data)
    print(f"OK set_locations | {len(data['locations'])} 个位置")


def cmd_consume(args) -> None:
    """消耗 N 个**小单位**（默认 1）：扣精确余量 + 重算状态。

    "用掉一瓶洗手液" → `consume --id i_003`。扣减算法与模型共用
    （`inventory.apply_consume`）—— 老实现两边各写一份，且用整除把散片丢掉（F1 / P1）。
    """
    data = load("inventory.json")
    amount = args.amount or 1
    for it in data.get("items", []):
        if it["id"] != args.id:
            continue
        apply_consume(it, amount)
        it["status"] = InventoryModel.derive_status(it)
        it["updated_at"] = now_iso()
        save("inventory.json", data)
        print(f"OK consume {args.id} | 剩 {it['remaining_doses']} "
              f"（{it['quantity']}{it.get('unit', '件')} · {it['status']}）")
        return
    raise ActionError(f"没有 id 为 {args.id} 的物品 —— 先用 lookup_item 查一下")

def _sync_remainder(item: dict, recompute: bool) -> None:
    """同步**精确余量**（片）：`recompute` 时按用户填的**盒数**重算，否则只做展示换算。

    抽出来是为了压 `_apply_item_quantity_fields` 的圈复杂度（加了分支就到 C(11)，RADON 拦下）。
    """
    if recompute:
        dpu = item.get("doses_per_unit", 1) or 1
        item["remaining_doses"] = int(item.get("quantity", 0)) * dpu
    InventoryModel.sync_units(item)


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
    # 用户填的 `quantity` 是**盒数** → 显式改了数量/每份含量时重算精确余量（片）
    _sync_remainder(item, quantity is not None or dpu is not None)


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
    _apply_membership(item, args)


def cmd_update_item(args) -> None:
    data = load("inventory.json")
    for it in data.get("items", []):
        if it["id"] != args.id:
            continue
        _apply_item_updates(it, args)
        it["updated_at"] = now_iso()
        # 状态：显式 `--status` 优先（用户手改的不能被覆盖）；否则重算
        # （会员按到期日，其余按数量 —— 数量改了状态就该跟着变）
        if not it.get("ignore_low_stock") and not getattr(args, "status", None):
            it["status"] = InventoryModel.derive_status(it)
        added_loc = _ensure_location(data, it.get("location", ""))
        save("inventory.json", data)
        note = f" | 新增位置 {added_loc}" if added_loc else ""
        print(f"OK update_item {args.id}{note}")
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
    """要补货 / 续费的东西 —— **只看学校那一侧**（家里的东西在这儿买不了，提醒了也没用）。

    状态**按当前日期重新推导**（会员的"需购"来自到期日，存下来的快照会过期）。
    """
    data = load("inventory.json")
    needs = [it for it in data.get("items", []) if _needs_restock(it)]
    for it in needs:
        print(f"  [{it['id']}] {it['name']} ({it['quantity']}{it.get('unit','个')}) - {it['status']}")
    if not needs:
        print("无需购物品")

def _membership_extra(it: dict) -> str:
    """会员摘要（用户名 / 到期日 / 自动续费）；不是会员就空串。

    ⚠ 这里**没有手机号** —— 它不进提示词（也不会进仓库）。
    """
    m = InventoryModel.membership_of(it)
    if not m:
        return ""
    bits = [str(m["username"])] if m.get("username") else []
    if m.get("expires_on"):
        bits.append(f"{m['expires_on']} 到期")
    if m.get("auto_renew"):
        bits.append(f"自动续费{m.get('renew_months') or '?'}个月")
    return "会员:" + "/".join(bits) if bits else ""


def _item_extra(it: dict) -> str:
    """括号里的补充信息：片数 / 下限 / 各件数 / 标签 / 会员。"""
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
    member = _membership_extra(it)
    if member:
        extra.append(member)
    return f" ({' · '.join(extra)})" if extra else ""


def _item_line(it: dict) -> str:
    """一行摘要：id 名称 数量单位 @位置 - 状态（附片数/阈值/各件数/标签/会员）。

    状态**按当前日期重新推导** —— 会员的"需购"来自到期日，存下来的快照会过期。
    """
    loc = f" @{it['location']}" if it.get("location") else ""
    return (f"  [{it['id']}] {it['name']} {it.get('quantity', 0)}{it.get('unit', '')}"
            f"{loc} - {InventoryModel.effective_status(it)}{_item_extra(it)}")


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
    """给位置清单**追加**一个（不替换原有；整份替换用 `set_locations`）。"""
    data = load("inventory.json")
    name = (getattr(args, "name", "") or "").strip()
    added = _ensure_location(data, name)
    save("inventory.json", data)
    print(f"OK add_location {name}" if added else f"OK add_location {name}（已存在）")


def _needs_restock(it: dict) -> bool:
    """需购 / 不足（**按当前日期算**），且没被显式豁免 —— 与 `need_restock` 同一口径。"""
    return (not it.get("ignore_low_stock")
            and InventoryModel.side_of(it) == SIDE_SCHOOL
            and InventoryModel.effective_status(it) in ("需购", "不足"))


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
        # 只看需补货的 —— 与 `need_restock` 同一口径（学校侧 + 按当前日期重算状态）
        active.append(_needs_restock)
    return active


def cmd_lookup_item(args) -> None:
    """按**任意组合**的条件找物品：名字 / 分类 / 标签 / 位置 / 只列需补货。

    不带条件 = 列出全部（两边都在内 —— 位置本身就说明了在哪一边）。
    **只查不写** —— "先查后加"的两步流程照旧。
    """
    data = load("inventory.json")
    filters = _lookup_filters(args)
    matches = [it for it in data.get("items", [])
               if all(f(it) for f in filters)]

    if not matches:
        print("NOT_FOUND")
        return
    for m in matches:
        print(_item_line(m))
    print(f"FOUND {len(matches)}")
