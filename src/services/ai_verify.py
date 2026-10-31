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
from datetime import date
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
    return _read_path(Path(data_dir) / name)


def _read_path(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
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
    return {"count": len(items)}


def _observe_add_task(args: dict, data_dir: Path) -> dict:
    tasks = _read_semester(data_dir, "tasks.json").get("tasks") or []
    return {"count": len(tasks)}


def _observe_delete_item(args: dict, data_dir: Path) -> dict:
    items = _read(data_dir, "inventory.json").get("items") or []
    return {"exists": any(it.get("id") == args.get("id") for it in items)}


def _observe_complete_task(args: dict, data_dir: Path) -> dict:
    data = _read_semester(data_dir, "tasks.json")
    tid = args.get("id", "")
    task = next((t for t in data.get("tasks") or [] if t.get("id") == tid), {})
    return {"exists": bool(task), "completed": task.get("status") == "completed"}


def _label_item(args: dict, data_dir: Path) -> str:
    item = _item(_read(data_dir, "inventory.json"), args.get("id", ""))
    return str(item.get("name") or "")


def _label_course(args: dict, data_dir: Path) -> str:
    return str(_course_by_id(data_dir, args.get("id", "")).get("name") or "")


def _label_plan_index(args: dict, data_dir: Path) -> str:
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(args.get("date", ""))
    try:
        return str((plans or [])[int(args.get("index", "-1"))].get("title") or "")
    except (IndexError, ValueError):
        return ""


def _label_title_or_date(args: dict, data_dir: Path) -> str:
    return str(args.get("title") or args.get("date") or "")


def _label_note(args: dict, data_dir: Path) -> str:
    return str(args.get("note") or "")


def _label_task(args: dict, data_dir: Path) -> str:
    tid = args.get("id", "")
    data = _read_semester(data_dir, "tasks.json")
    for task in (data.get("tasks") or []) + (data.get("archived") or []):
        if task.get("id") == tid:
            return str(task.get("title") or "")
    return ""


def label_of(command: str, data_dir: Path) -> str:
    """这条命令操作的**对象名**（事实行要写"哪个东西"）。读不到 → 空串。

    ⚠ 必须在**执行前**取：像 `delete_item` 执行完，对象就没了 ✗。
    """
    operation, args = parse_command(command)
    fallback = str(args.get("name") or "")
    if not data_dir:
        return fallback
    labeler = _LABELERS.get(operation)
    return (labeler(args, data_dir) if labeler is not None else "") or fallback


def _read_semester(data_dir: Path, name: str) -> dict:
    """读**按学期分**的数据文件（`tasks.json` 这类在 `semesters/<id>/` 下）。

    ⚠ 不调用 `semester_paths.resolve()`：它在注册表缺失时会**创建**默认学期（写盘）——
    验收是只读路径，不该产生副作用。这里只按现有注册表**读**。
    """
    from src.models import semester_paths

    registry = semester_paths.read_registry(Path(data_dir))
    sid = str(registry.get("current_semester") or "")
    if not sid:
        return {}
    return _read_path(semester_paths.semester_dir(Path(data_dir), sid) / name)


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
    """新增物品：**数量增加 + 名字对得上**（同名不同位置是两件独立物品）。"""
    name = args.get("name", "")
    items = _read(data_dir, "inventory.json").get("items") or []
    hit = any(it.get("name") == name for it in items)
    if len(items) > int(before.get("count", -1)) and hit:
        return VERIFIED, f"「{name}」在清单里"
    return MISMATCH, f"清单里找不到新写入的「{name}」"


def _check_add_task(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """记作业：**数量增加 + 标题对得上**（同名作业可能有多条）。"""
    title = args.get("title", "")
    tasks = _read_semester(data_dir, "tasks.json").get("tasks") or []
    hit = any(t.get("title") == title for t in tasks)
    if len(tasks) > int(before.get("count", -1)) and hit:
        return VERIFIED, f"作业「{title}」在列表里"
    return MISMATCH, f"作业列表里找不到新写入的「{title}」"


def _check_complete_task(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """完成作业：任务必须在 `archived` 里且状态为 completed。"""
    tid = args.get("id", "")
    data = _read_semester(data_dir, "tasks.json")
    archived = next((t for t in data.get("archived") or []
                     if t.get("id") == tid and t.get("status") == "completed"), None)
    if archived:
        if before.get("completed"):
            return NOOP, "这条作业本来就已经完成"
        return VERIFIED, f"作业「{archived.get('title', '')}」已完成"
    if any(t.get("id") == tid for t in data.get("tasks") or []):
        return MISMATCH, f"作业 {tid} 还在待办里"
    return MISMATCH, f"作业 {tid} 不在列表里"


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


# ── 课程表 ──────────────────────────────────────────────────

def _courses(data_dir: Path) -> list[dict]:
    return _read_semester(data_dir, "courses.json").get("courses") or []


def _course_by_id(data_dir: Path, cid: str) -> dict:
    return next((c for c in _courses(data_dir) if c.get("id") == cid), {})


def _observe_add_course(args: dict, data_dir: Path) -> dict:
    return {"count": len(_courses(data_dir))}


def _observe_update_course(args: dict, data_dir: Path) -> dict:
    course = _course_by_id(data_dir, args.get("id", ""))
    if not course:
        return {}
    return {
        "name": course.get("name"),
        "day": course.get("day_of_week"),
        "weeks": course.get("weeks"),
        "slots": [(s.get("start"), s.get("end"))
                  for s in course.get("time_slots") or []],
        "parity": course.get("week_parity"),
        "teacher": course.get("teacher"),
        "location": course.get("location"),
    }


def _observe_delete_course(args: dict, data_dir: Path) -> dict:
    return {"exists": bool(_course_by_id(data_dir, args.get("id", "")))}


def _check_add_course(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    name = args.get("name", "")
    courses = _courses(data_dir)
    if len(courses) > int(before.get("count", -1)) and any(
            c.get("name") == name for c in courses):
        return VERIFIED, f"课程「{name}」已写入"
    return MISMATCH, f"课程表里找不到新写入的「{name}」"


def _field_problem(label: str, want, actual) -> str | None:
    """只在命令**显式传了**这个字段时比较；不一致时返回一句可读的差异。"""
    if want in (None, ""):
        return None
    return None if str(want) == str(actual) else f"{label}是 {actual}"


def _check_update_course(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """改课程：逐个核对**显式传入**的字段（没传的字段不该被改）。"""
    course = _course_by_id(data_dir, args.get("id", ""))
    if not course:
        return MISMATCH, f"课程 {args.get('id', '')} 不在了"
    weeks = course.get("weeks") or {}
    slot = (course.get("time_slots") or [{}])[0]
    checks = (
        _field_problem("名称", args.get("name"), course.get("name")),
        _field_problem("星期", args.get("day"), course.get("day_of_week")),
        _field_problem("单双周", args.get("parity"), course.get("week_parity")),
        _field_problem("教师", args.get("teacher"), course.get("teacher")),
        _field_problem("地点", args.get("location"), course.get("location")),
        _field_problem("周次", args.get("weeks"),
                       f"{weeks.get('start')}-{weeks.get('end')}"),
        _field_problem("节次", args.get("slots"),
                       f"{slot.get('start')}-{slot.get('end')}"),
    )
    problems = [problem for problem in checks if problem]
    if problems:
        return MISMATCH, "；".join(problems)
    return VERIFIED, f"课程 {args.get('id', '')} 的改动已核对"


def _check_delete_course(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    cid = args.get("id", "")
    gone = not any(c.get("id") == cid for c in _courses(data_dir))
    if gone and before.get("exists"):
        return VERIFIED, f"课程 {cid} 已删除"
    if not gone:
        return MISMATCH, f"课程 {cid} 还在，没删掉"
    return NOOP, f"本来就没有课程 {cid}"


# ── 考试 / 习惯 / 日程计划 ──────────────────────────────────

def _observe_add_exam(args: dict, data_dir: Path) -> dict:
    return {"count": len(_read_semester(data_dir, "exams.json").get("exams") or [])}


def _check_add_exam(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    course = args.get("course", "")
    exams = _read_semester(data_dir, "exams.json").get("exams") or []
    hit = any(e.get("course_name") == course and e.get("exam_date") == args.get("date")
              for e in exams)
    if len(exams) > int(before.get("count", -1)) and hit:
        return VERIFIED, f"考试「{course}」已写入"
    return MISMATCH, f"考试列表里找不到「{course}」"


def _observe_add_habit(args: dict, data_dir: Path) -> dict:
    return {"count": len(_read(data_dir, "habits.json").get("habits") or [])}


def _check_add_habit(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    name = args.get("name", "")
    habits = _read(data_dir, "habits.json").get("habits") or []
    if len(habits) > int(before.get("count", -1)) and any(
            h.get("name") == name for h in habits):
        return VERIFIED, f"习惯「{name}」已写入"
    return MISMATCH, f"习惯列表里找不到「{name}」"


def _observe_log_habit(args: dict, data_dir: Path) -> dict:
    hid = args.get("id", "")
    entry = ((_read(data_dir, "habits.json").get("logs") or {})
             .get(date.today().isoformat(), {}).get(hid) or {})
    return {"completed": bool(entry.get("completed"))}


def _check_log_habit(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    hid = args.get("id", "")
    entry = ((_read(data_dir, "habits.json").get("logs") or {})
             .get(date.today().isoformat(), {}).get(hid) or {})
    if entry.get("completed"):
        if before.get("completed"):
            return NOOP, "今天本来就已经打过卡"
        return VERIFIED, "习惯已打卡"
    return MISMATCH, "习惯打卡没有生效"


def _observe_add_plan(args: dict, data_dir: Path) -> dict:
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    return {"count": len(plans)}


def _check_add_plan(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    day = args.get("date", "")
    title = args.get("title", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    if len(plans) > int(before.get("count", -1)) and any(
            p.get("title") == title for p in plans):
        return VERIFIED, f"{day} 的计划「{title}」已写入"
    return MISMATCH, f"{day} 的计划列表里找不到「{title}」"


def _observe_replace_plans(args: dict, data_dir: Path) -> dict:
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    return {"titles": [p.get("title") for p in plans]}


def _check_replace_plans(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    try:
        wanted = json.loads(args.get("plans", "[]"))
    except (TypeError, ValueError):
        return UNVERIFIED, "未验收（--plans 不是合法 JSON，无法核对）"
    if not isinstance(wanted, list):
        return UNVERIFIED, "未验收（--plans 不是数组）"
    want_titles = [str(p.get("title", "")) for p in wanted if isinstance(p, dict)]
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    got_titles = [p.get("title") for p in plans]
    if got_titles == want_titles:
        return VERIFIED, f"{day} 的计划已整体替换为 {len(got_titles)} 条"
    return MISMATCH, f"{day} 的计划是 {len(got_titles)} 条，期望 {len(want_titles)} 条"


def _observe_delete_plan(args: dict, data_dir: Path) -> dict:
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    return {"titles": [p.get("title") for p in plans]}


def _check_delete_plan(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    try:
        idx = int(args.get("index", "-1"))
    except ValueError:
        return UNVERIFIED, "未验收（index 不是整数）"
    before_titles = list(before.get("titles") or [])
    if not 0 <= idx < len(before_titles):
        return NOOP, "本来就没有这条计划"
    expected = before_titles[:idx] + before_titles[idx + 1:]
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    got = [p.get("title") for p in plans]
    if got == expected:
        return VERIFIED, f"计划「{before_titles[idx]}」已删除"
    return MISMATCH, "计划列表与预期不一致（可能删错了那条）"


# ── 记账 / 存钱 / 财务 / 位置 ────────────────────────────────

def _observe_add_expense(args: dict, data_dir: Path) -> dict:
    return {"count": len(_read(data_dir, "expenses.json").get("records") or [])}


def _check_add_expense(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    records = _read(data_dir, "expenses.json").get("records") or []
    try:
        want = float(args.get("amount", "0"))
    except ValueError:
        return UNVERIFIED, "未验收（amount 不是数字）"
    day = args.get("date") or date.today().isoformat()
    hit = any(abs(float(r.get("amount") or 0) - want) < 0.005
              and str(r.get("date") or "")[:10] == day for r in records)
    if len(records) > int(before.get("count", -1)) and hit:
        return VERIFIED, f"支出 ¥{want:.2f}（{day}）已写入"
    return MISMATCH, "支出记录里找不到这一笔"


def _observe_add_saving(args: dict, data_dir: Path) -> dict:
    day = args.get("date") or date.today().isoformat()
    savings = (_read(data_dir, "daily_logs.json").get("savings") or {}).get(day) or []
    return {"count": len(savings)}


def _check_add_saving(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    day = args.get("date") or date.today().isoformat()
    try:
        want = float(args.get("amount", "0"))
    except ValueError:
        return UNVERIFIED, "未验收（amount 不是数字）"
    savings = (_read(data_dir, "daily_logs.json").get("savings") or {}).get(day) or []
    hit = any(abs(float(s.get("amount") or 0) - want) < 0.005 for s in savings)
    if len(savings) > int(before.get("count", -1)) and hit:
        return VERIFIED, f"存钱 ¥{want:.2f}（{day}）已写入"
    return MISMATCH, "存钱记录里找不到这一笔"


def _observe_delete_expense(args: dict, data_dir: Path) -> dict:
    return {"exists": any(r.get("id") == args.get("id")
                          for r in _read(data_dir, "expenses.json").get("records") or [])}


def _check_delete_expense(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    rid = args.get("id", "")
    gone = not any(r.get("id") == rid
                   for r in _read(data_dir, "expenses.json").get("records") or [])
    if gone and before.get("exists"):
        return VERIFIED, f"支出 {rid} 已删除"
    if not gone:
        return MISMATCH, f"支出 {rid} 还在，没删掉"
    return NOOP, f"本来就没有支出 {rid}"


def _observe_finance_set(args: dict, data_dir: Path) -> dict:
    return {"finance": dict(_read(data_dir, "expenses.json").get("finance") or {})}


def _check_finance_set(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    after = _read(data_dir, "expenses.json").get("finance") or {}
    failed = []
    for field in ("balance", "monthly_income", "fixed_expenses"):
        if field not in args:
            continue
        try:
            want = float(args[field])
        except ValueError:
            continue
        if abs(float(after.get(field) or 0) - want) >= 0.005:
            failed.append(field)
    if failed:
        return MISMATCH, f"没写进去：{'、'.join(failed)}"
    return VERIFIED, "财务初始值已核对"


def _observe_add_location(args: dict, data_dir: Path) -> dict:
    return {"locations": list(_read(data_dir, "inventory.json").get("locations") or [])}


def _check_add_location(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    from src.models.inventory import canonical_location

    want = canonical_location(args.get("name", ""))
    locations = _read(data_dir, "inventory.json").get("locations") or []
    if want in locations:
        if want in (before.get("locations") or []):
            return NOOP, f"位置「{want}」本来就在清单里"
        return VERIFIED, f"位置「{want}」已加入清单"
    return MISMATCH, f"位置清单里找不到「{want}」"


def _observe_set_locations(args: dict, data_dir: Path) -> dict:
    return {"locations": list(_read(data_dir, "inventory.json").get("locations") or [])}


def _check_set_locations(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    want = [v.strip() for v in str(args.get("values", "")).split(",") if v.strip()]
    got = _read(data_dir, "inventory.json").get("locations") or []
    if got == want:
        return VERIFIED, f"位置清单已设为 {len(got)} 项"
    return MISMATCH, f"位置清单是 {got}，期望 {want}"


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


_LABELERS = {
    "consume": _label_item,
    "update_item": _label_item,
    "delete_item": _label_item,
    "update_course": _label_course,
    "add_exam": lambda args, _d: str(args.get("course") or ""),
    "add_plan": _label_title_or_date,
    "replace_plans": _label_title_or_date,
    "add_expense": _label_note,
    "add_saving": _label_note,
    "complete_plan": _label_plan_index,
    "delete_plan": _label_plan_index,
    "complete_task": _label_task,
}


_OBSERVERS = {
    "consume": _observe_consume,
    "update_item": _observe_update_item,
    "complete_plan": _observe_complete_plan,
    "add_item": _observe_add_item,
    "add_task": _observe_add_task,
    "delete_item": _observe_delete_item,
    "complete_task": _observe_complete_task,
    # 课程 / 考试 / 习惯 / 日程
    "add_course": _observe_add_course,
    "update_course": _observe_update_course,
    "delete_course": _observe_delete_course,
    "add_exam": _observe_add_exam,
    "add_habit": _observe_add_habit,
    "log_habit": _observe_log_habit,
    "add_plan": _observe_add_plan,
    "replace_plans": _observe_replace_plans,
    "delete_plan": _observe_delete_plan,
    # 记账 / 财务 / 位置
    "add_expense": _observe_add_expense,
    "add_saving": _observe_add_saving,
    "delete_expense": _observe_delete_expense,
    "finance_set": _observe_finance_set,
    "add_location": _observe_add_location,
    "set_locations": _observe_set_locations,
}


_CHECKS = {
    "consume": _check_consume,
    "complete_plan": _check_complete_plan,
    "update_item": _check_update_item,
    "add_item": _check_add_item,
    "add_task": _check_add_task,
    "delete_item": _check_delete_item,
    "complete_task": _check_complete_task,
    # 课程 / 考试 / 习惯 / 日程
    "add_course": _check_add_course,
    "update_course": _check_update_course,
    "delete_course": _check_delete_course,
    "add_exam": _check_add_exam,
    "add_habit": _check_add_habit,
    "log_habit": _check_log_habit,
    "add_plan": _check_add_plan,
    "replace_plans": _check_replace_plans,
    "delete_plan": _check_delete_plan,
    # 记账 / 财务 / 位置
    "add_expense": _check_add_expense,
    "add_saving": _check_add_saving,
    "delete_expense": _check_delete_expense,
    "finance_set": _check_finance_set,
    "add_location": _check_add_location,
    "set_locations": _check_set_locations,
}
