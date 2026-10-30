"""UI → 模型 的**字段契约**守卫（机械检查，防"静默丢字段"再发生）。

为什么需要：2026-10-19 实测到 —— **会员弹窗存不上** ✗：
`inventory_dialogs.edit_membership_dialog` 调 `update_item(iid, {"membership": …})`，
而 `update_item` 当时的手写白名单里**没有** `membership` → 静默丢弃，还返回 `True` ✗✗。

⚠ 为什么原有的测试全都没拦住：**物品的测试全走 CLI** ✗
（`scripts/actions_cmds_items.py` 直接改 dict，**不经过模型**），
所以"UI 走模型 API"这条路上的字段对不上，一直没人发现。

这条守卫做的事很土但很准：扫 `src/ui/**/*.py` 的 AST，凡是调
`update_item(...)` / `add_item(...)` / `update_exam(...)` 且**第二个实参是字面量 dict** 的，
把键拿出来对照模型的可写清单。**今天那个 `{"membership": …}` 就会被抓住** ✓。
（第二个实参不是字面量 dict 的调用**跳过** —— 静态看不出来，不硬猜 ✗。）
"""

import ast
from pathlib import Path

from src.models.exam import EXAM_FIELDS
from src.models.inventory import ITEM_FIELDS
from src.models.routine import ROUTINE_FIELDS

UI_DIR = Path(__file__).resolve().parent.parent / "src" / "ui"

# 方法名 → (要检查的**实参下标**, 该模型的**可写字段清单**)
# ⚠ 下标不能一刀切：`update_item(iid, data)` 的 dict 在**第 2 个**实参，
# 而 `add_item(data)` 在**第 1 个** —— 旧版统一要求"至少两个实参"，
# 于是所有 `add_item(...)` 调用**从未被检查过**（2026-10-19 审查 R10 点出的盲区）。
# ⚠ `update_item` 这个名字只在物品模型里有；「近期安排」用的是 `update_routine`
# （模型方法名不同才不会被当成物品的字段清单 —— 2026-10-30 A3）。
CHECKED = {
    "update_item": (1, ITEM_FIELDS),
    "add_item": (0, ITEM_FIELDS),
    "update_exam": (1, EXAM_FIELDS),
    "add_exam": (0, EXAM_FIELDS),
    "update_routine": (1, ROUTINE_FIELDS),
}


def _literal_str_keys(node: ast.AST) -> list[str] | None:
    """字面量 dict 的字符串键；不是字面量 dict / 有非字面量键 → `None`（跳过该调用）。"""
    if not isinstance(node, ast.Dict):
        return None
    keys: list[str] = []
    for key in node.keys:
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            return None
        keys.append(key.value)
    return keys


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def test_ui_update_calls_only_pass_writable_fields() -> None:
    problems: list[str] = []
    for path in sorted(UI_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            spec = CHECKED.get(_call_name(node))
            if spec is None:
                continue
            index, fields = spec
            if len(node.args) <= index:
                continue
            keys = _literal_str_keys(node.args[index])
            if keys is None:
                continue
            for key in keys:
                if key not in fields:
                    problems.append(
                        f"{path.relative_to(UI_DIR.parent.parent)}:{node.lineno} "
                        f"{_call_name(node)}(…) 传了模型不认识的字段 {key!r}")
    assert not problems, "UI 与模型的字段契约不一致：\n" + "\n".join(problems)
