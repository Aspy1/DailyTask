"""Field-level verification for inventory actions."""

from __future__ import annotations

import json
from pathlib import Path

from src.models.inventory import canonical_location, runs_out_date, worn_since_date
from src.services.ai_verify import MISMATCH, NOOP, UNVERIFIED, VERIFIED, _item, _read

_DIRECT_FIELDS = {
    "name": "name", "group": "group", "category": "category",
    "quantity": "quantity", "status": "status", "min_qty": "min_quantity",
    "min_doses": "min_doses", "notes": "notes", "unit": "unit",
    "doses_per_unit": "doses_per_unit", "stock_target": "stock_target",
    "due_day": "due_day", "installments": "installments",
}
_INTEGER_FIELDS = frozenset({
    "quantity", "min_qty", "min_doses", "doses_per_unit",
    "stock_target", "due_day", "installments",
})
_EMPTY_IGNORED_FIELDS = frozenset({"name", "category", "status", "unit"})
_BILLING_FIELDS = frozenset({
    "billing_type", "amount", "due_day", "installments",
    "paid_count", "billing_active", "last_charged_on",
})


def observe_update_item(args: dict, data_dir: Path) -> dict:
    """Capture only the affected fields and quantity inputs before the write."""
    item = _item(_read(data_dir, "inventory.json"), args.get("id", ""))
    if not item:
        return {}
    expected, removed = _expected_item_updates(args, item)
    fields = set(expected) | removed
    before = {"fields": {key: _field_state(item, key) for key in fields},
              "basis": {key: item.get(key) for key in ("quantity", "doses_per_unit")}}
    for field in ("location", "quantity"):
        if field in fields:
            before[field] = item.get(field)
    return before


def _field_state(item: dict, field: str) -> dict:
    return {"present": field in item, "value": item.get(field)}


def check_update_item(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """Verify every requested field, plus fields derived from a quantity edit."""
    item = _item(_read(data_dir, "inventory.json"), args.get("id", ""))
    if not item:
        return MISMATCH, f"物品 {args.get('id', '')} 不在了"
    expected, removed = _expected_item_updates(args, before.get("basis", item))
    fields = set(expected) | removed
    if not fields:
        return UNVERIFIED, "未验收（这条改动物品的命令没有可核对字段）"
    problems = _mismatches(item, expected, removed)
    if problems:
        return _mismatch_detail(item, expected, problems)
    if not _fields_changed(before, item, fields):
        return _noop_detail(item, expected)
    return _verified_detail(item, expected, fields)


def _mismatches(item: dict, expected: dict, removed: set[str]) -> list[str]:
    problems = [key for key, value in expected.items() if item.get(key) != value]
    return sorted(problems + [key for key in removed if key in item])


def _fields_changed(before: dict, item: dict, fields: set[str]) -> bool:
    previous = before.get("fields", {})
    if not previous:
        previous = {key: _field_state(before, key) for key in fields if key in before}
    return any(previous.get(key, {}).get("present") != (key in item)
               or previous.get(key, {}).get("value") != item.get(key) for key in fields)


def _mismatch_detail(item: dict, expected: dict, problems: list[str]) -> tuple[str, str]:
    if problems == ["location"]:
        return MISMATCH, f"位置是「{item.get('location', '')}」，期望「{expected['location']}」"
    if problems == ["quantity"]:
        return MISMATCH, f"数量是 {item.get('quantity')}，期望 {expected['quantity']}"
    return MISMATCH, f"物品字段未达到请求状态：{', '.join(problems)}"


def _noop_detail(item: dict, expected: dict) -> tuple[str, str]:
    if set(expected) == {"location"}:
        return NOOP, f"位置本来就是「{item.get('location', '')}」（没变化，不算失败）"
    if set(expected) == {"quantity", "remaining_doses"}:
        return NOOP, f"数量本来就是 {item.get('quantity')}"
    return NOOP, "物品字段原本已符合请求"


def _verified_detail(item: dict, expected: dict, fields: set[str]) -> tuple[str, str]:
    if set(expected) == {"location"}:
        return VERIFIED, f"位置已更新为「{item.get('location', '')}」"
    if set(expected) == {"quantity", "remaining_doses"}:
        return VERIFIED, f"数量现在是 {item.get('quantity')}"
    return VERIFIED, f"物品字段已核对：{', '.join(sorted(fields))}"


def _expected_item_updates(args: dict, basis: dict) -> tuple[dict, set[str]]:
    expected = _direct_values(args)
    removed: set[str] = set()
    if not _json_values(args, expected, removed):
        return {}, set()
    _date_values(args, expected)
    _billing_values(args, expected, removed)
    _derived_values(args, basis, expected)
    return expected, removed


def _direct_values(args: dict) -> dict:
    expected = {}
    for source, target in _DIRECT_FIELDS.items():
        if source not in args:
            continue
        value = args[source]
        if not value and source in _EMPTY_IGNORED_FIELDS:
            continue
        expected[target] = int(value) if source in _INTEGER_FIELDS else value
    if args.get("location"):
        expected["location"] = canonical_location(args["location"])
    if "tags" in args:
        expected["tags"] = [tag.strip() for tag in args["tags"].split(",") if tag.strip()]
    return expected


def _json_values(args: dict, expected: dict, removed: set[str]) -> bool:
    if not _instances_value(args, expected):
        return False
    return _membership_value(args, expected, removed)


def _instances_value(args: dict, expected: dict) -> bool:
    if "instances" not in args:
        return True
    try:
        instances = json.loads(args["instances"] or "[]")
    except (TypeError, ValueError):
        return False
    if not isinstance(instances, list) or not all(isinstance(row, dict) for row in instances):
        return False
    expected["instances"] = instances
    return True


def _membership_value(args: dict, expected: dict, removed: set[str]) -> bool:
    membership_raw = args.get("membership", "")
    if not membership_raw.strip():
        return True
    try:
        membership = json.loads(membership_raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(membership, dict):
        return False
    if membership:
        expected["membership"] = membership
    else:
        removed.add("membership")
    return True


def _date_values(args: dict, expected: dict) -> None:
    if args.get("runs_out"):
        expected["runs_out_on"] = args["runs_out"]
    if "runs_out_months" in args:
        expected["runs_out_on"] = runs_out_date(int(args["runs_out_months"]))
    if args.get("expires"):
        expected["expires_on"] = args["expires"]
    if "worn_days" in args:
        expected["worn_since"] = worn_since_date(int(args["worn_days"]))
    if args.get("needs_wash") in ("yes", "no"):
        expected["needs_wash"] = args["needs_wash"] == "yes"
    if "remind_before" in args:
        expected["remind_before_days"] = int(args["remind_before"])


def _billing_values(args: dict, expected: dict, removed: set[str]) -> None:
    billing_type = args.get("billing_type", "")
    if billing_type == "none":
        removed.update(_BILLING_FIELDS)
    elif billing_type:
        expected["billing_type"] = billing_type
    if "amount" in args:
        expected["amount"] = float(args["amount"])


def _derived_values(args: dict, basis: dict, expected: dict) -> None:
    if "quantity" in args or "doses_per_unit" in args:
        quantity = int(args.get("quantity", basis.get("quantity", 0)) or 0)
        doses = int(args.get("doses_per_unit", basis.get("doses_per_unit", 1)) or 1)
        expected["remaining_doses"] = quantity * doses
    if args.get("status"):
        expected["status_locked"] = True
