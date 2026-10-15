"""
统一数据操作脚本 — AI 通过 CLI 调用，不直接写 JSON。
用法: python scripts/actions.py <action> [参数...]

设计原则: AI 只管理解+标准化参数，脚本管验证+写文件。
"""

import argparse
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

# run_in_process 用 redirect_stdout 捕获输出，而 sys.stdout 是进程级全局；
# 加锁串行化，避免多个线程同时执行时互相污染（见 CODE_STANDARDS Q-B4）。
_STDOUT_LOCK = threading.Lock()


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)


def load(name) -> dict:
    p = DATA / name
    if not p.exists():
        return {}
    with open(p, encoding='utf-8') as f:
        return json.load(f)

def save(name, obj) -> None:
    with open(DATA / name, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def gen_id(items, prefix) -> str:
    existing = set()
    for it in items:
        try:
            num = int(it["id"].split("_")[1])
            existing.add(num)
        except (KeyError, ValueError):
            logger.debug("gen_id 中忽略异常", exc_info=True)
    n = 1
    while n in existing:
        n += 1
    return f"{prefix}_{n:03d}"

def now_iso() -> str:
    return datetime.now().isoformat()

def _match_exact_course(courses: list, name_lower: str) -> str | None:
    """课程名精确匹配（大小写不敏感）；未命中返回 None。"""
    for c in courses:
        if c.get("name", "").lower() == name_lower:
            return c["name"]
    return None


def _find_contains_matches(courses: list, name_lower: str) -> list[str]:
    """双向包含匹配（输入包含课程名 / 课程名包含输入）。"""
    matches = []
    for c in courses:
        cn = c.get("name", "").lower()
        if name_lower in cn or cn in name_lower:
            matches.append(c["name"])
    return matches


def _find_abbr_matches(courses: list, name_lower: str) -> list[str]:
    """缩写匹配: "算法课" matches "算法设计与分析" (remove 课/程)。"""
    abbr = name_lower.replace("课", "").replace("程", "")
    if abbr == name_lower:
        return []
    matches = []
    for c in courses:
        cn = c.get("name", "").lower()
        if abbr in cn:
            matches.append(c["name"])
    return matches


def _find_word_matches(courses: list, name_lower: str) -> list[str]:
    """分词匹配：任一长度 ≥2 的词出现在课程名中即算命中。"""
    words = set(name_lower.replace("课", "").split())
    matches = []
    for c in courses:
        cn = c.get("name", "").lower()
        if any(w in cn for w in words if len(w) >= 2):
            matches.append(c["name"])
    return matches


def _find_course_matches(courses: list, name_lower: str) -> list[str]:
    """依次尝试「包含 → 缩写 → 分词」，返回首个非空的候选列表。"""
    for finder in (_find_contains_matches, _find_abbr_matches, _find_word_matches):
        matches = finder(courses, name_lower)
        if matches:
            return matches
    return []


def match_course(name: str) -> str | None:
    """Fuzzy match course name. Handles abbreviations like 算法课→算法设计与分析."""
    if not name:
        return None
    data = load("courses.json")
    courses = data.get("courses", [])
    name_lower = name.strip().lower()

    exact = _match_exact_course(courses, name_lower)
    if exact:
        return exact

    matches = _find_course_matches(courses, name_lower)
    if len(matches) == 1:
        return matches[0]
    # Return original if no match
    if not matches:
        return name.strip()
    # Multiple matches — try exact word match first
    return matches[0]

def _parse_relative_date(s: str, today: date, day_names: dict) -> str | None:
    """中文相对日期（下周X / 本周X / 明天 / N天后）→ ISO；不匹配返回 None。"""
    # "下周日"
    m = re.match(r'下周(.)', s)
    if m:
        wd = day_names.get(m.group(1))
        if wd is not None:
            days_ahead = 7 - today.weekday() + wd
            if days_ahead <= 7:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).isoformat()
    # "这周五" / "本周五" / "周五"
    m = re.match(r'(?:这|本)?周(.)', s)
    if m:
        wd = day_names.get(m.group(1))
        if wd is not None:
            days_ahead = wd - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).isoformat()
    # "明天" / "后天" / "今天"
    offsets = {"明天": 1, "后天": 2, "今天": 0}
    if s in offsets:
        return (today + timedelta(days=offsets[s])).isoformat()
    # "N天后"
    m = re.match(r'(\d+)天后', s)
    if m:
        return (today + timedelta(days=int(m.group(1)))).isoformat()
    return None


def _parse_month_day(s: str, today: date) -> str:
    """月日形式（6月20日 / 6.20 / 6/20）→ ISO；不匹配则原样返回。"""
    for pattern in (r'(\d{1,2})月(\d{1,2})[日号]?', r'(\d{1,2})[./](\d{1,2})'):
        m = re.match(pattern, s)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            year = today.year
            if month < today.month:
                year += 1
            return f"{year}-{month:02d}-{day:02d}"
    return s


def parse_date(s: str) -> str:
    """Parse date string to YYYY-MM-DD. Supports Chinese relative dates."""
    s = s.strip()
    # Already ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s[:10]
    today = date.today()
    # Chinese relative
    day_names = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}
    relative = _parse_relative_date(s, today, day_names)
    if relative is not None:
        return relative
    return _parse_month_day(s, today)

def _shift_hour(period: str, hour: int) -> int:
    """中文时段 + 12 小时制小时 → 24 小时制。"""
    if period in ('下午', '晚上'):
        if hour != 12:
            hour += 12
    elif period in ('中午',) and hour < 12:  # 中午1点→13点
        hour += 12
    # 上午/早晨: keep as is (but 12→0 for midnight)
    if period == '上午' and hour == 12:
        hour = 0
    return hour


def _append_default_time(due_str: str) -> str:
    """无可识别时段时：无时间补 23:00:00；只有到分钟则补 :00。"""
    if 'T' not in due_str:
        return due_str + 'T23:00:00'
    if len(due_str) <= 16:
        return due_str + ':00'
    return due_str


def normalize_time(due_str: str) -> str:
    """Ensure date has time. Extracts Chinese time expressions (中午12点, 下午3点)."""
    if not due_str:
        return ""
    # Extract Chinese time: 中午12点, 下午3点半, 上午9点, 晚上8点
    time_match = re.search(
        r'(中午|下午|上午|晚上|早晨|早上)(\d{1,2})点(半)?',
        due_str
    )
    if time_match:
        period, hour_str, half = time_match.group(1), time_match.group(2), time_match.group(3)
        hour = _shift_hour(period, int(hour_str))
        minute = '30' if half else '00'
        # Replace the time part in the string with ISO time
        due_str = re.sub(r'(中午|下午|上午|晚上|早晨|早上)\d{1,2}点(半)?', '', due_str).strip()
        if 'T' not in due_str:
            due_str += f'T{hour:02d}:{minute}:00'
        else:
            due_str = due_str[:11] + f'{hour:02d}:{minute}:00'
        return due_str
    return _append_default_time(due_str)


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
    due = parse_date(due_raw)
    due = normalize_time(due)
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
    qty = args.quantity or 1
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
    """
    import io
    from contextlib import redirect_stdout

    parts = _split_command_parts(cmd_str)
    if not parts:
        return "ERROR: empty command"

    action = parts[0]
    ns = _build_action_namespace(parts)

    handlers = {
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
    }

    if action not in handlers:
        return f"ERROR unknown action: {action}"

    buf = io.StringIO()
    with _STDOUT_LOCK, redirect_stdout(buf):
        try:
            handlers[action](ns)
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {e}")
    return buf.getvalue().strip()


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(prog="actions", description="生活助手数据操作")
    sub = parser.add_subparsers(dest="action")

    # add_task
    p = sub.add_parser("add_task", help="添加作业")
    p.add_argument("--course", help="课程名（支持模糊匹配）")
    p.add_argument("--title", required=True, help="作业标题")
    p.add_argument("--due", required=True, help="截止日期（YYYY-MM-DD / 下周日 / 6月20日）")
    p.add_argument("--priority", default="medium", choices=["high","medium","low"])
    p.add_argument("--tags")
    p.add_argument("--notes")

    # complete_task
    p = sub.add_parser("complete_task", help="标记作业完成")
    p.add_argument("--id", required=True, help="作业ID (t_001)")

    # add_exam
    p = sub.add_parser("add_exam", help="添加考试")
    p.add_argument("--course", required=True)
    p.add_argument("--date", required=True, help="考试日期")
    p.add_argument("--scope")
    p.add_argument("--location")
    p.add_argument("--notes")
    p.add_argument("--tags")

    # add_habit
    p = sub.add_parser("add_habit", help="添加习惯")
    p.add_argument("--name", required=True)
    p.add_argument("--schedule", default="daily/1", help="daily/1 weekly/1,3,5 monthly/4")
    p.add_argument("--duration", type=int, default=30)
    p.add_argument("--reminder")

    # log_habit
    p = sub.add_parser("log_habit", help="打卡习惯")
    p.add_argument("--id", required=True)

    # add_plan
    p = sub.add_parser("add_plan", help="添加日程计划")
    p.add_argument("--date", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--slot", type=int, default=1)
    p.add_argument("--type", default="custom")
    p.add_argument("--course")
    p.add_argument("--note")

    # replace_plans
    p = sub.add_parser("replace_plans", help="替换某天全部计划")
    p.add_argument("--date", required=True)
    p.add_argument("--plans", required=True, help="JSON数组")

    # delete_plan
    p = sub.add_parser("delete_plan", help="删除某天某条计划")
    p.add_argument("--date", required=True)
    p.add_argument("--index", type=int, required=True)

    # add_course
    p = sub.add_parser("add_course", help="添加课程")
    p.add_argument("--name", required=True)
    p.add_argument("--day", type=int, required=True)
    p.add_argument("--weeks", default="1-16")
    p.add_argument("--slots", default="3-4")
    p.add_argument("--location")
    p.add_argument("--teacher")
    p.add_argument("--parity", default="all", choices=["all","odd","even"])

    # delete_course
    p = sub.add_parser("delete_course", help="删除课程")
    p.add_argument("--id", required=True)

    # add_item
    p = sub.add_parser("add_item", help="添加物品")
    p.add_argument("--name", required=True)
    p.add_argument("--category", default="其他")
    p.add_argument("--quantity", type=int, default=1)
    p.add_argument("--min_qty", type=int, default=1)
    p.add_argument("--location")
    p.add_argument("--notes")
    p.add_argument("--group", default="")
    p.add_argument("--tags")
    p.add_argument("--status", default=None)  # accepted but ignored, auto-derived

    # update_item
    p = sub.add_parser("update_item", help="更新物品")
    p.add_argument("--id", required=True)
    p.add_argument("--name")
    p.add_argument("--group")
    p.add_argument("--category")
    p.add_argument("--quantity", type=int)
    p.add_argument("--status", choices=["充足","不足","需购"])
    p.add_argument("--min_qty", type=int)
    p.add_argument("--location")
    p.add_argument("--tags")

    # need_restock
    sub.add_parser("need_restock", help="查看需购物品")

    # lookup_item
    p = sub.add_parser("lookup_item", help="查找物品")
    p.add_argument("--name", required=True)

    # status
    sub.add_parser("status", help="概览")

    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        return

    handlers = {
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
    }

    try:
        handlers[args.action](args)
    # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
    except Exception as e:  # noqa: BLE001
        print(f"ERROR {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
