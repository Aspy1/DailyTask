"""AI 动作的**回执**与**领域验收**（专项审查 §3.2 / §3.3 的第一步，2026-10-19）。

为什么需要：命令返回 `OK` 只说明"handler 没报错"，**不说明用户要的状态成立了**
（审查 §2.2："格式正确、写盘成功、业务意图正确是不同层次"）。
所以执行之后要**回读数据**、按**确定性规则**判一次，把结论回喂给模型 ——
它才有机会针对差异返工 ✓。

判据一律是"读 JSON 比字段"，**不请模型自查** ✓（§2.3：模型不能自填"验证通过"当证据）。

范围：审查 §6 建议的**最小垂直链路** —— 扣减 / 移动 / 计划完成。
**没写验收器的操作明说"未验收"**，不假装通过 ✗（那比没有验收更糟）。

状态取值（§3.2）：
- `verified`      目标状态成立 ✓
- `verified_noop` 目标**本来就已经满足** —— 不是失败（§2.1：验证后的无变化也算成功）
- `mismatch`      状态**不成立** → 模型该针对差异返工（不是重复原命令）
- `failed`        命令自己就报错了（handler / 校验拒绝）
- `unverified`    没有验收器 / 读不到数据 → **不许当成通过** ✗
"""

import json
import re
from pathlib import Path

VERIFIED = "verified"
NOOP = "verified_noop"
MISMATCH = "mismatch"
FAILED = "failed"
UNVERIFIED = "unverified"

_ARG_RE = re.compile(r"--([a-z_]+)(?:[ =])(\"[^\"]*\"|'[^']*'|\S+)")


def parse_command(command: str) -> tuple[str, dict[str, str]]:
    """从命令行里取出 `(操作名, 参数)` —— 只认 `--k v` / `--k=v`（`actions.py` 的两种写法）。"""
    parts = str(command or "").split()
    operation = ""
    for i, token in enumerate(parts):
        if token.endswith("actions.py") and i + 1 < len(parts):
            operation = parts[i + 1]
            break
    args: dict[str, str] = {}
    for key, value in _ARG_RE.findall(str(command or "")):
        args[key] = value.strip("\"'")
    return operation, args


def _read(data_dir: Path, name: str) -> dict:
    """读一个数据文件；读不到 → 空 dict（验收读不到就报"未验收"，不猜 ✗）。"""
    try:
        return json.loads((Path(data_dir) / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _item(data: dict, iid: str) -> dict:
    return next((it for it in data.get("items", []) if it.get("id") == iid), {})


def observe(command: str, data_dir: Path) -> dict:
    """执行**之前**记下这条命令关心的字段（回执的 `before`，也是"本来已满足"的判据）。"""
    operation, args = parse_command(command)
    if not data_dir:
        return {}
    return _OBSERVERS.get(operation, _no_state)(args, data_dir)


def _no_state(args: dict, data_dir: Path) -> dict:
    return {}


def _observe_consume(args: dict, data_dir: Path) -> dict:
    item = _item(_read(data_dir, "inventory.json"), args.get("id", ""))
    return {"remaining_doses": item.get("remaining_doses")} if item else {}


def _observe_update_item(args: dict, data_dir: Path) -> dict:
    """改物品：记下**这条命令关心的**字段（位置 / 数量）—— 别的字段没有验收器。"""
    item = _item(_read(data_dir, "inventory.json"), args.get("id", ""))
    if not item:
        return {}
    out: dict = {}
    if args.get("location"):
        out["location"] = item.get("location")
    if "quantity" in args:
        out["quantity"] = item.get("quantity")
    return out


def _observe_complete_plan(args: dict, data_dir: Path) -> dict:
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(args.get("date", ""))
    try:
        plan = (plans or [])[int(args.get("index", "-1"))]
    except (IndexError, ValueError):
        return {}
    return {"done": bool(plan.get("done"))}


def _observe_add_item(args: dict, data_dir: Path) -> dict:
    items = _read(data_dir, "inventory.json").get("items") or []
    return {"exists": any(it.get("name") == args.get("name") for it in items)}


def _observe_add_task(args: dict, data_dir: Path) -> dict:
    tasks = _read_semester(data_dir, "tasks.json").get("tasks") or []
    return {"exists": any(t.get("title") == args.get("title") for t in tasks)}


def _observe_delete_item(args: dict, data_dir: Path) -> dict:
    items = _read(data_dir, "inventory.json").get("items") or []
    return {"exists": any(it.get("id") == args.get("id") for it in items)}


_OBSERVERS = {
    "consume": _observe_consume,
    "update_item": _observe_update_item,
    "complete_plan": _observe_complete_plan,
    "add_item": _observe_add_item,
    "add_task": _observe_add_task,
    "delete_item": _observe_delete_item,
}


def label_of(command: str, data_dir: Path) -> str:
    """这条命令操作的**对象名**（事实行要写"哪个东西"）。读不到 → 空串。

    ⚠ 必须在**执行前**取：像 `delete_item` 执行完，对象就没了 ✗。
    """
    operation, args = parse_command(command)
    fallback = str(args.get("name") or "")
    if not data_dir:
        return fallback
    if operation in ("consume", "update_item", "delete_item"):
        item = _item(_read(data_dir, "inventory.json"), args.get("id", ""))
        return str(item.get("name") or fallback)
    if operation in ("complete_plan", "delete_plan"):
        plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(args.get("date", ""))
        try:
            return str((plans or [])[int(args.get("index", "-1"))].get("title") or "")
        except (IndexError, ValueError):
            return ""
    return fallback


def _read_semester(data_dir: Path, name: str) -> dict:
    """读**按学期分**的数据文件（`tasks.json` 这类在 `semesters/<id>/` 下）。"""
    from src.models import semester_paths

    try:
        return _read(data_dir, str(Path(semester_paths.resolve(Path(data_dir), name))
                                  .relative_to(Path(data_dir))))
    except (OSError, ValueError):
        return {}


def check(command: str, before: dict, result: str, data_dir: Path) -> tuple[str, str]:
    """执行**之后**回读数据验收 → `(状态, 给模型看的一句话)`。

    ⚠ 顺序：**命令自己报错就不用再验收**（`failed`）—— 别把"执行失败"说成"验收不通过"。
    验收器按**操作**查表（`_CHECKS`）；没登记的操作明说"未验收" ✗（不许当成通过）。
    """
    operation, args = parse_command(command)
    if not str(result).startswith("OK"):
        return FAILED, f"命令没成功（{str(result)[:80]}）"
    verifier = _CHECKS.get(operation)
    if verifier is None:
        return UNVERIFIED, "未验收（这条命令没有验收器）"
    if not data_dir or not before:
        return UNVERIFIED, "未验收（读不到数据，没法核对）"
    return verifier(before, args, data_dir)


def _check_add_item(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """新增物品：那条**真的在**（名字对得上）—— 不是"handler 说 OK"。"""
    name = args.get("name", "")
    items = _read(data_dir, "inventory.json").get("items") or []
    if any(it.get("name") == name for it in items):
        return VERIFIED, f"「{name}」在清单里"
    return MISMATCH, f"清单里找不到「{name}」"


def _check_add_task(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """记作业：那条**真的在**（标题对得上）。"""
    title = args.get("title", "")
    tasks = _read_semester(data_dir, "tasks.json").get("tasks") or []
    if any(t.get("title") == title for t in tasks):
        return VERIFIED, f"作业「{title}」在列表里"
    return MISMATCH, f"作业列表里找不到「{title}」"


def _check_delete_item(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """删物品：那条**真的没了**（而且原来是在的）。"""
    iid = args.get("id", "")
    items = _read(data_dir, "inventory.json").get("items") or []
    gone = not any(it.get("id") == iid for it in items)
    if gone and before.get("exists"):
        return VERIFIED, f"{iid} 已删除"
    if not gone:
        return MISMATCH, f"{iid} 还在，没删掉"
    return NOOP, f"本来就没有 {iid}"


def _check_update_item(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """改物品：位置走专门的核对；只改数量时核对**数量**。"""
    if args.get("location"):
        return _check_location(before, args, data_dir)
    if "quantity" in args:
        item = _item(_read(data_dir, "inventory.json"), args.get("id", ""))
        if not item:
            return MISMATCH, f"物品 {args.get('id', '')} 不在了"
        want = int(args["quantity"])
        if int(item.get("quantity", -1)) == want:
            return VERIFIED, f"数量现在是 {want}"
        return MISMATCH, f"数量是 {item.get('quantity')}，期望 {want}"
    return UNVERIFIED, "未验收（这条改动物品的命令没有核对项）"




def _check_consume(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """扣减：余量必须**正好**少掉 `--amount`（默认 1）。

    ⚠ 特别注意"命令说 OK 但余量没变" —— 那是**不一致**，不是"无变化也算成功" ✗。
    """
    amount = int(args.get("amount", "1") or 1)
    item = _item(_read(data_dir, "inventory.json"), args.get("id", ""))
    if not item:
        return MISMATCH, f"物品 {args.get('id', '')} 不在了"
    was, now = before.get("remaining_doses"), item.get("remaining_doses")
    if not isinstance(was, int) or not isinstance(now, int):
        return UNVERIFIED, "余量字段读不到，未验收"
    if now == was - amount:
        return VERIFIED, f"余量 {was} → {now}（正好扣了 {amount}）"
    if now == was:
        return MISMATCH, f"命令说成功，但余量还是 {now}（没扣掉）"
    return MISMATCH, f"余量变成了 {now}，期望 {was - amount}（扣减量对不上）"


def _check_location(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """移动：位置必须等于**归一化之后**的目标位置（词表口径见 `canonical_location`）。"""
    from src.models.inventory import canonical_location

    item = _item(_read(data_dir, "inventory.json"), args.get("id", ""))
    if not item:
        return MISMATCH, f"物品 {args.get('id', '')} 不在了"
    want = canonical_location(args.get("location", ""))
    now = str(item.get("location") or "")
    if now == want:
        if before.get("location") == want:
            return NOOP, f"位置本来就是「{want}」（没变化，不算失败）"
        return VERIFIED, f"位置 {before.get('location') or '（空）'} → {now}"
    return MISMATCH, f"位置还是「{now}」，期望「{want}」"


def _check_complete_plan(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """计划完成：那一条的 `done` 必须为真。"""
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(args.get("date", ""))
    try:
        plan = (plans or [])[int(args.get("index", "-1"))]
    except (IndexError, ValueError):
        return MISMATCH, "那条计划不在了"
    if plan.get("done"):
        if before.get("done"):
            return NOOP, "那条计划本来就是完成状态"
        return VERIFIED, "计划已标记完成"
    return MISMATCH, "那条计划**没有**被标记完成"


def summarize(verdicts: list[tuple[str, str]]) -> str:
    """把一批验收结论拼成给模型看的一段（附在工具结果后面）。"""
    if not verdicts:
        return ""
    return "\n[验收]\n" + "\n".join(f"  {state}: {detail}" for state, detail in verdicts)


def mismatches(verdicts: list[tuple[str, str]]) -> list[str]:
    """**没达到预期**的那些（`mismatch`）—— 给"汇报权归代码"用。

    `failed` 不在这里：命令自己报错已经由写失败那条路径汇报了（别重复报）。
    """
    return [detail for state, detail in verdicts if state == MISMATCH]


_CHECKS = {
    "consume": _check_consume,
    "complete_plan": _check_complete_plan,
    "update_item": _check_update_item,
    "add_item": _check_add_item,
    "add_task": _check_add_task,
    "delete_item": _check_delete_item,
}
