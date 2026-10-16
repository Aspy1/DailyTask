"""数据操作**命令层** — AI 通过 CLI 调用，不直接写 JSON。
用法: python scripts/actions.py <action> [参数...]

分工（2026-10-16 拆分；此前单文件 1391 行，超过「单文件 ≤800 行」的规范上限）：

- `scripts/actions_core.py` —— 数据读写（**原子写入 + 写前备份**）、参数校验、
  日期解析与课程名匹配（唯一实现，命令层与校验层共用）
- **本文件** —— 命令实现 + 进程内执行器（`run_in_process`）+ CLI

设计原则: AI 只负责理解意图 + 标准化参数，脚本负责**严格校验 + 安全写文件**。
"""

import argparse
import json
import logging
import os
import re
import sys
import threading
from datetime import date
from pathlib import Path

# 直接 `python scripts/actions.py <命令>` 时 `sys.path[0]` 是 scripts/ 而不是仓库根，
# 于是 `import scripts.actions_cli` 会失败（2026-10-16 拆分后实测踩到）。
# AI 提示词宣传的正是这种调用形式，用户/外部脚本也会这么用 → 必须自举路径
# （与 `main.py` / `send_digest.py` 同一套路）。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# DATA / _path 等一并导出：测试与外部调用点用的是 `actions.DATA`、`actions.run_in_process`
from scripts.actions_cli import (
    _add_backup_parsers,
    _add_expense_parsers,
    _add_item_parsers,
    _add_routine_parsers,
    _add_task_parsers,
)
from scripts.actions_core import (  # noqa: F401
    ALLOWED_OPTIONS,
    DATA,
    MAX_NOTE,
    ActionError,
    _backup_dir,
    _backup_file,
    _fname,
    _iso_date,
    _max_backups,
    _money,
    _month,
    _normalize_due,
    _path,
    _record_id,
    _resolve_category,
    _text,
    _validate_args,
    _validate_payload,
    gen_id,
    load,
    match_course,
    now_iso,
    parse_date,
    save,
)

logger = logging.getLogger(__name__)

# run_in_process 用 redirect_stdout 捕获输出，而 sys.stdout 是进程级全局；
# 加锁串行化，避免多个线程同时执行时互相污染（见 CODE_STANDARDS Q-B4）。
_STDOUT_LOCK = threading.Lock()


    # need_restock / status 无参数


# ═══════════════════════════════════════════════════════════
# Actions
# ═══════════════════════════════════════════════════════════

def cmd_add_task(args) -> None:
    course = args.course or ""
    matched = match_course(course) or course or ""
    title = args.title
    due_raw = args.due or ""
    if not due_raw.strip():
        print("ERROR add_task requires --due (YYYY-MM-DD)")
        return
    due = _normalize_due(due_raw)
    if due is None:
        print(f"ERROR add_task 无法识别日期: {due_raw}")
        return
    priority = args.priority or "medium"

    data = load("tasks.json")
    data.setdefault("tasks", [])
    data.setdefault("archived", [])
    tid = gen_id(data["tasks"] + data["archived"], "t")

    task = {
        "id": tid, "title": title, "course_name": matched,
        "due_date": due, "status": "pending", "priority": priority,
        "tags": args.tags.split(",") if args.tags else [],
        "notes": args.notes or "", "created_at": now_iso(), "reminded": False
    }
    data["tasks"].append(task)
    save("tasks.json", data)
    print(f"OK add_task {tid} | {matched} | {title} | DDL {due[:16]}")

def cmd_complete_task(args) -> None:
    tid = args.id
    data = load("tasks.json")
    data.setdefault("tasks", [])
    data.setdefault("archived", [])
    for t in data["tasks"]:
        if t["id"] == tid:
            t["status"] = "completed"
            t["completed_at"] = now_iso()
            data["tasks"].remove(t)
            data["archived"].append(t)
            save("tasks.json", data)
            print(f"OK complete_task {tid}")
            return
    # Check archived
    for t in data["archived"]:
        if t["id"] == tid:
            print(f"ALREADY completed {tid}")
            return
    print(f"ERROR task not found: {tid}")

def cmd_add_exam(args) -> None:
    course = args.course or ""
    matched = match_course(course)
    exam_date = parse_date(args.date) if args.date else ""

    data = load("exams.json")
    data.setdefault("exams", [])
    eid = gen_id(data["exams"], "e")

    exam = {
        "id": eid, "course_name": matched, "exam_date": exam_date,
        "scope": args.scope or "", "location": args.location or "",
        "notes": args.notes or "", "tags": args.tags.split(",") if args.tags else [],
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    data["exams"].append(exam)
    save("exams.json", data)
    print(f"OK add_exam {eid} | {matched} | {exam_date}")

def cmd_add_habit(args) -> None:
    name = args.name
    schedule_str = args.schedule or "daily/1"
    typ, val = schedule_str.split("/", 1) if "/" in schedule_str else ("daily", "1")

    if typ == "daily":
        schedule = {"type": "daily", "times_per_day": int(val)}
    elif typ == "weekly":
        schedule = {"type": "weekly", "days": [int(d) for d in val.split(",")]}
    elif typ == "monthly":
        schedule = {"type": "monthly", "value": int(val)}
    else:
        print(f"ERROR unknown schedule type: {typ}")
        return

    data = load("habits.json")
    data.setdefault("habits", [])
    hid = gen_id(data["habits"], "h")

    habit = {
        "id": hid, "name": name, "schedule": schedule,
        "duration_minutes": args.duration or 30,
        "reminder_time": args.reminder or "",
        "streak": 0, "longest_streak": 0, "attached_tasks": []
    }
    data["habits"].append(habit)
    save("habits.json", data)
    print(f"OK add_habit {hid} | {name} ({typ})")

def cmd_log_habit(args) -> None:
    hid = args.id
    data = load("habits.json")
    today_str = date.today().isoformat()

    for h in data.get("habits", []):
        if h["id"] == hid:
            data.setdefault("logs", {}).setdefault(today_str, {})
            data["logs"][today_str][hid] = {"completed": True, "completed_at": now_iso()}
            h["streak"] = h.get("streak", 0) + 1
            if h["streak"] > h.get("longest_streak", 0):
                h["longest_streak"] = h["streak"]
            save("habits.json", data)
            print(f"OK log_habit {hid} | {h['name']} | streak={h['streak']}")
            return
    print(f"ERROR habit not found: {hid}")

def cmd_add_plan(args) -> None:
    date_str = parse_date(args.date) if args.date else date.today().isoformat()
    plan = {
        "title": args.title,
        "time_slot": args.slot or 1,
        "type": args.type or "custom",
        "note": args.note or "",
        "course_name": args.course or "",
        "created_at": now_iso(),
    }
    data = load("daily_logs.json")
    data.setdefault("plans", {}).setdefault(date_str, [])
    data["plans"][date_str].append(plan)
    save("daily_logs.json", data)
    print(f"OK add_plan | {date_str} | slot={plan['time_slot']} | {plan['title']}")

def cmd_replace_plans(args) -> None:
    date_str = parse_date(args.date) if args.date else date.today().isoformat()
    try:
        new_plans = json.loads(args.plans)
    except json.JSONDecodeError:
        print("ERROR invalid plans JSON")
        return
    data = load("daily_logs.json")
    data.setdefault("plans", {})
    data["plans"][date_str] = []
    for p in new_plans:
        p.setdefault("type", "custom")
        data["plans"][date_str].append(p)
    save("daily_logs.json", data)
    print(f"OK replace_plans {date_str} | {len(new_plans)} items")

def cmd_delete_plan(args) -> None:
    date_str = parse_date(args.date) if args.date else date.today().isoformat()
    idx = args.index
    data = load("daily_logs.json")
    plans = data.get("plans", {}).get(date_str, [])
    if 0 <= idx < len(plans):
        removed = plans.pop(idx)
        if not plans:
            del data["plans"][date_str]
        save("daily_logs.json", data)
        print(f"OK delete_plan {date_str}[{idx}] | {removed.get('title','')}")
    else:
        print(f"ERROR plan index out of range: {date_str}[{idx}]")

def cmd_add_course(args) -> None:
    name = args.name
    day = args.day
    weeks_str = args.weeks or "1-16"
    slots_str = args.slots or "3-4"
    location = args.location or ""
    teacher = args.teacher or ""

    # Parse weeks
    m = re.match(r'(\d+)-(\d+)', weeks_str)
    if not m:
        print(f"ERROR invalid weeks: {weeks_str}")
        return
    weeks = {"start": int(m.group(1)), "end": int(m.group(2))}

    # Parse slots
    m = re.match(r'(\d+)-(\d+)', slots_str)
    if not m:
        print(f"ERROR invalid slots: {slots_str}")
        return
    time_slots = [{"start": int(m.group(1)), "end": int(m.group(2)), "location": location}]

    data = load("courses.json")
    data.setdefault("courses", [])
    cid = gen_id(data["courses"], "c")

    course = {
        "id": cid, "name": name, "teacher": teacher,
        "day_of_week": int(day), "weeks": weeks,
        "time_slots": time_slots, "notes": "",
        "week_parity": args.parity or "all",
    }
    data["courses"].append(course)
    save("courses.json", data)
    print(f"OK add_course {cid} | {name} | 周{day} 第{slots_str}节")

def cmd_delete_course(args) -> None:
    cid = args.id
    data = load("courses.json")
    courses = data.get("courses", [])
    for i, c in enumerate(courses):
        if c["id"] == cid:
            removed = courses.pop(i)
            save("courses.json", data)
            print(f"OK delete_course {cid} | {removed.get('name','')}")
            return
    print(f"ERROR course not found: {cid}")

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
    """数量/单位/状态/下限：仅当显式传值才覆盖。"""
    if args.quantity is not None:
        item["quantity"] = args.quantity
    if args.unit:
        item["unit"] = args.unit
    if args.status:
        item["status"] = args.status
    if args.min_qty is not None:
        item["min_quantity"] = args.min_qty


def _split_tag_list(tags: str) -> list[str]:
    """逗号分隔标签 → 去空白后的非空列表。"""
    return [t.strip() for t in tags.split(",") if t.strip()]


def _apply_item_updates(item: dict, args) -> None:
    """把命令行传入的非空字段写回物品条目（保持原有字段写入顺序）。"""
    if args.name:
        item["name"] = args.name
    if args.group is not None and args.group != "":
        item["group"] = args.group
    if args.category:
        item["category"] = args.category
    _apply_item_quantity_fields(item, args)
    if args.location:
        item["location"] = args.location
    if args.tags:
        item["tags"] = _split_tag_list(args.tags)


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

def cmd_status(args) -> None:
    t = load("tasks.json")
    h = load("habits.json")
    c = load("courses.json")
    e = load("exams.json")
    pending = sum(1 for x in t.get("tasks", []) if x.get("status") != "completed")
    habits = len(h.get("habits", []))
    courses = len(c.get("courses", []))
    upcoming = [x for x in e.get("exams", []) if x.get("exam_date", "") >= date.today().isoformat()]
    print(f"tasks={pending} habits={habits} courses={courses} exams={len(upcoming)}")


# ═══════════════════════════════════════════════════════════
# 记账 / 存钱（此前 AI 完全没有记账能力）
# ═══════════════════════════════════════════════════════════

def _expense_categories(data: dict) -> list[dict]:
    return data.get("categories") or []


def _category_name(data: dict, cat_id: str) -> str:
    for c in _expense_categories(data):
        if c.get("id") == cat_id:
            return str(c.get("name") or cat_id)
    return cat_id


def cmd_add_expense(args) -> None:
    amount = _money(args.amount, "amount")
    day = _iso_date(args.date, "date", default=date.today().isoformat())
    note = _text(args.note, "note", max_len=MAX_NOTE)

    data = load("expenses.json")
    if not data:
        # 文件不存在时按**模型的默认结构**建（分类/预算与界面一致），
        # 不要只写一个只有 records 的半截文件
        import copy

        from src.models.expense import DEFAULT_EXPENSES

        data = copy.deepcopy(DEFAULT_EXPENSES)
    data.setdefault("records", [])
    cat_id = _resolve_category(args.category, _expense_categories(data))
    rid = gen_id(data["records"], "e")

    data["records"].append({
        "id": rid, "amount": amount, "category": cat_id,
        "date": day, "note": note, "created_at": now_iso(),
    })
    save("expenses.json", data)
    print(f"OK add_expense {rid} | {_category_name(data, cat_id)} | ¥{amount:.2f} | {day}")


def cmd_add_saving(args) -> None:
    """存钱（与「记账」并列的另一栏，落在 daily_logs.savings）。"""
    amount = _money(args.amount, "amount")
    day = _iso_date(args.date, "date", default=date.today().isoformat())
    note = _text(args.note, "note", max_len=MAX_NOTE)

    data = load("daily_logs.json")
    if not data:
        import copy

        from src.models.daily_log import DEFAULT_DAILY_LOGS

        data = copy.deepcopy(DEFAULT_DAILY_LOGS)
    day_sav = data.setdefault("savings", {}).setdefault(day, [])
    sid = gen_id(day_sav, "s")
    day_sav.append({"id": sid, "amount": amount, "note": note, "created_at": now_iso()})
    save("daily_logs.json", data)
    print(f"OK add_saving {sid} | ¥{amount:.2f} | {day}")


def cmd_delete_expense(args) -> None:
    rid = _record_id(args.id)
    data = load("expenses.json")
    for i, r in enumerate(data.get("records", [])):
        if r.get("id") == rid:
            removed = data["records"].pop(i)
            save("expenses.json", data)
            print(f"OK delete_expense {rid} | ¥{float(removed.get('amount', 0) or 0):.2f}")
            return
    print(f"ERROR expense not found: {rid}")


def _month_totals(records: list[dict], month: str) -> tuple[float, dict[str, float], int]:
    """某月：总额 + 按分类汇总 + 笔数（纯计算，便于单测）。"""
    total = 0.0
    count = 0
    by_cat: dict[str, float] = {}
    for r in records:
        if not str(r.get("date", "")).startswith(month):
            continue
        amount = float(r.get("amount", 0) or 0)
        total += amount
        count += 1
        cid = str(r.get("category", "other"))
        by_cat[cid] = by_cat.get(cid, 0.0) + amount
    return total, by_cat, count


def cmd_expense_summary(args) -> None:
    """某月支出汇总（按分类）+ 今日支出/存钱/月预算余额。"""
    month = _month(getattr(args, "month", None))
    data = load("expenses.json")
    records = data.get("records", [])
    total, by_cat, count = _month_totals(records, month)

    print(f"{month} 合计 ¥{total:.2f}（{count} 笔）")
    for cid, amt in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {_category_name(data, cid)}: ¥{amt:.2f}")

    today = date.today().isoformat()
    today_total = sum(float(r.get("amount", 0) or 0) for r in records if r.get("date") == today)
    saved = sum(float(s.get("amount", 0) or 0)
                for s in load("daily_logs.json").get("savings", {}).get(today, []))
    budget = float((data.get("budget") or {}).get("monthly", 0) or 0)
    tail = f" | 月预算 ¥{budget:.0f}（剩余 ¥{budget - total:.2f}）" if budget else ""
    print(f"今日支出 ¥{today_total:.2f} | 今日存钱 ¥{saved:.2f}{tail}")


# ═══════════════════════════════════════════════════════════
# 备份 / 恢复（写入前已自动留存，这里是**手动回滚入口**）
# ═══════════════════════════════════════════════════════════

def cmd_list_backups(args) -> None:
    name = _text(getattr(args, "name", None), "name")
    files = sorted(_backup_dir().glob(f"{name}.*.json" if name else "*.json"))
    if not files:
        print("NO_BACKUP" + (f" for {name}" if name else ""))
        return
    for f in files[-20:]:
        print(f"  {f.name}  ({f.stat().st_size} 字节)")
    print(f"共 {len(files)} 份（每个文件保留上限 {_max_backups()} 份）")


def cmd_restore(args) -> None:
    """用备份覆盖当前文件。

    ⚠ **这是给用户的手动恢复入口**：必须显式 `--yes`；AI 不得自行调用
    （提示词里已写明）。恢复前会把"当前版本"再备份一次，避免恢复错方向。
    """
    name = _text(args.name, "name", required=True)
    if not getattr(args, "yes", False):
        print("ERROR restore 需要显式 --yes（手动恢复入口，避免误覆盖）")
        return

    candidates = sorted(_backup_dir().glob(f"{name}.*.json"))
    stamp = _text(getattr(args, "stamp", None), "stamp")
    if stamp:
        candidates = [c for c in candidates if stamp in c.name]
    if not candidates:
        print(f"ERROR 没有 {name} 的备份（先用 list_backups 查看）")
        return

    src = candidates[-1]
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR 备份本身损坏：{src.name}（{e}）")
        return
    _validate_payload(name, data)

    dest = _path(name)
    _backup_file(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"OK restore {name} ← {src.name}")


# ═══════════════════════════════════════════════════════════
# In-process executor (avoids subprocess overhead for AI calls)
# ═══════════════════════════════════════════════════════════

def _split_command_parts(cmd_str: str) -> list[str]:
    """按 shell 规则切分命令，去掉 python/py 前缀与 actions.py 脚本路径。"""
    import shlex

    parts = shlex.split(cmd_str)
    # Strip 'python' / 'python3' / 'py' prefix
    while parts and parts[0].lower() in ('python', 'python3', 'py'):
        parts.pop(0)
    # Strip script path if present
    if parts and ('actions.py' in parts[0]):
        parts.pop(0)
    return parts


def _to_int_or_str(val: str) -> int | str:
    """整数字符串转 int，否则原样返回。"""
    try:
        return int(val)
    except ValueError:
        logger.debug("run_in_process 中忽略异常", exc_info=True)
        return val


def _consume_option(ns: argparse.Namespace, parts: list[str], i: int) -> int:
    """解析 parts[i] 处的 --key [value] 写入 ns，返回下一个下标。"""
    token = parts[i]
    if not token.startswith('--'):
        return i + 1
    key = token[2:].replace('-', '_')
    if i + 1 < len(parts) and not parts[i + 1].startswith('--'):
        setattr(ns, key, _to_int_or_str(parts[i + 1]))
        return i + 2
    setattr(ns, key, True)
    return i + 1


def _build_action_namespace(parts: list[str]) -> argparse.Namespace:
    """把 --key value 参数解析为 Namespace，并补齐 argparse 默认值。"""
    ns = argparse.Namespace()
    ns.action = parts[0]
    i = 1
    while i < len(parts):
        i = _consume_option(ns, parts, i)

    # 未知参数直接拒绝：AI 拼错 --titel 时，旧实现会**静默忽略**，
    # 结果是"看起来执行成功、其实什么都没写"（或写进默认值）。
    if ns.action in ALLOWED_OPTIONS:
        allowed = ALLOWED_OPTIONS[ns.action]
        unknown = set(vars(ns)) - {"action"} - allowed
        if unknown:
            raise ActionError(
                f"未知参数 {'、'.join(sorted(_fname(u) for u in unknown))}"
                f"（{ns.action} 只接受：{'、'.join(sorted(_fname(o) for o in allowed)) or '无'}）")

    # Apply argparse defaults for all optional args (not in CLI string)
    _defaults = {
        'priority': 'medium', 'schedule': 'daily/1', 'duration': 30,
        'slot': 1, 'type': 'custom', 'weeks': '1-16', 'slots': '3-4',
        'parity': 'all', 'category': '其他', 'quantity': 1, 'min_qty': 1,
        'tags': None, 'notes': '', 'location': '', 'scope': '', 'teacher': '',
        'course': '', 'reminder': '', 'unit': '', 'status': None, 'due': '', 'note': '', 'group': '',
        'title': '', 'date': '', 'name': '', 'plans': '[]', 'index': 0,
        'day': 0,
    }
    for k, v in _defaults.items():
        if not hasattr(ns, k):
            setattr(ns, k, v)
    return ns


def run_in_process(cmd_str: str) -> str:
    """Execute an actions.py command string in-process.

    Parses the shell command string, builds an argparse Namespace,
    and calls the handler directly — no subprocess overhead.
    Thread-safe: each call gets its own stdout buffer.

    参数校验在 handler **之前**：非法输入只回 `ERROR ...`，**一个字节都不写**。
    """
    import io
    from contextlib import redirect_stdout

    parts = _split_command_parts(cmd_str)
    if not parts:
        return "ERROR: empty command"

    buf = io.StringIO()
    with _STDOUT_LOCK, redirect_stdout(buf):
        try:
            action = parts[0]
            ns = _build_action_namespace(parts)
            if action not in HANDLERS:
                print(f"ERROR unknown action: {action}")
            else:
                _validate_args(action, ns)
                HANDLERS[action](ns)
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except ActionError as e:
            print(f"ERROR {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {e}")
    return buf.getvalue().strip()


# ═══════════════════════════════════════════════════════════
# 命令表（**唯一处**）：进程内执行器与 CLI 共用，防止两处漂移
# ═══════════════════════════════════════════════════════════

HANDLERS = {
    "add_task": cmd_add_task, "complete_task": cmd_complete_task,
    "add_exam": cmd_add_exam, "add_habit": cmd_add_habit,
    "log_habit": cmd_log_habit, "add_plan": cmd_add_plan,
    "replace_plans": cmd_replace_plans, "delete_plan": cmd_delete_plan,
    "add_course": cmd_add_course, "delete_course": cmd_delete_course,
    "add_item": cmd_add_item, "update_item": cmd_update_item,
    "delete_item": cmd_delete_item,
    "need_restock": cmd_need_restock,
    "lookup_item": cmd_lookup_item,
    "status": cmd_status,
    "add_expense": cmd_add_expense, "add_saving": cmd_add_saving,
    "delete_expense": cmd_delete_expense, "expense_summary": cmd_expense_summary,
    "list_backups": cmd_list_backups, "restore": cmd_restore,
}


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 解析器。

    单独成函数（而不是塞在 `main()` 里）：`tests/test_actions_validation.py`
    会拿它与 `ALLOWED_OPTIONS` 交叉校验，防止"参数白名单"与真实 CLI 漂移。
    """
    parser = argparse.ArgumentParser(prog="actions", description="生活助手数据操作")
    sub = parser.add_subparsers(dest="action")
    _add_task_parsers(sub)
    _add_routine_parsers(sub)
    _add_item_parsers(sub)
    _add_expense_parsers(sub)
    _add_backup_parsers(sub)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        return

    try:
        _validate_args(args.action, args)
        HANDLERS[args.action](args)
    # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
    except ActionError as e:
        print(f"ERROR {e}")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
