"""
统一数据操作脚本 — AI 通过 CLI 调用，不直接写 JSON。
用法: python scripts/actions.py <action> [参数...]

设计原则: AI 只管理解+标准化参数，脚本管验证+写文件。
"""

import argparse, json, os, re, sys
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path(r"D:\ClaudeCoding\日程规划\data")


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def load(name):
    p = DATA / name
    if not p.exists():
        return {}
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)

def save(name, obj):
    with open(DATA / name, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def gen_id(items, prefix):
    existing = set()
    for it in items:
        try:
            num = int(it["id"].split("_")[1])
            existing.add(num)
        except (KeyError, ValueError):
            pass
    n = 1
    while n in existing:
        n += 1
    return f"{prefix}_{n:03d}"

def now_iso():
    return datetime.now().isoformat()

def match_course(name: str) -> str | None:
    """Fuzzy match course name. Handles abbreviations like 算法课→算法设计与分析."""
    if not name:
        return None
    data = load("courses.json")
    courses = data.get("courses", [])
    name_lower = name.strip().lower()
    # Exact match
    for c in courses:
        if c.get("name", "").lower() == name_lower:
            return c["name"]
    # Contains match (bidirectional)
    matches = []
    for c in courses:
        cn = c.get("name", "").lower()
        if name_lower in cn or cn in name_lower:
            matches.append(c["name"])
    if len(matches) == 1:
        return matches[0]
    # Abbreviation: "算法课" matches "算法设计与分析" (remove 课/课)
    if not matches:
        abbr = name_lower.replace("课", "").replace("程", "")
        if abbr != name_lower:
            for c in courses:
                cn = c.get("name", "").lower()
                if abbr in cn:
                    matches.append(c["name"])
    if len(matches) == 1:
        return matches[0]
    # Partial word match
    if not matches:
        words = set(name_lower.replace("课","").split())
        for c in courses:
            cn = c.get("name", "").lower()
            if any(w in cn for w in words if len(w) >= 2):
                matches.append(c["name"])
    if len(matches) == 1:
        return matches[0]
    # Return original if no match
    if not matches:
        return name.strip()
    # Multiple matches — try exact word match first
    return matches[0]

def parse_date(s: str) -> str:
    """Parse date string to YYYY-MM-DD. Supports Chinese relative dates."""
    s = s.strip()
    # Already ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s[:10]
    today = date.today()
    # Chinese relative
    day_names = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}
    # "下周日"
    m = re.match(r'下周(.)', s)
    if m:
        wd = day_names.get(m.group(1))
        if wd is not None:
            days_ahead = 7 - today.weekday() + wd
            if days_ahead <= 7:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).isoformat()
    # "本周五" / "周五"
    m = re.match(r'(?:本周)?周(.)', s)
    if m:
        wd = day_names.get(m.group(1))
        if wd is not None:
            days_ahead = wd - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).isoformat()
    # "明天" / "后天" / "今天"
    if s == "明天":
        return (today + timedelta(days=1)).isoformat()
    if s == "后天":
        return (today + timedelta(days=2)).isoformat()
    if s == "今天":
        return today.isoformat()
    # "N天后"
    m = re.match(r'(\d+)天后', s)
    if m:
        return (today + timedelta(days=int(m.group(1)))).isoformat()
    # "6月20日" / "6月20号"
    m = re.match(r'(\d{1,2})月(\d{1,2})[日号]?', s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year
        if month < today.month:
            year += 1
        return f"{year}-{month:02d}-{day:02d}"
    # "6.20" / "6/20"
    m = re.match(r'(\d{1,2})[./](\d{1,2})', s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year
        if month < today.month:
            year += 1
        return f"{year}-{month:02d}-{day:02d}"
    return s

def normalize_time(due_str: str) -> str:
    """Ensure date has T23:00:00 default."""
    if not due_str:
        return ""
    if "T" not in due_str:
        due_str += "T23:00:00"
    elif len(due_str) <= 16:
        due_str += ":00"
    return due_str


# ═══════════════════════════════════════════════════════════
# Actions
# ═══════════════════════════════════════════════════════════

def cmd_add_task(args):
    course = args.course or ""
    matched = match_course(course)
    title = args.title
    due = parse_date(args.due) if args.due else ""
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

def cmd_complete_task(args):
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

def cmd_add_exam(args):
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

def cmd_add_habit(args):
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

def cmd_log_habit(args):
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

def cmd_add_plan(args):
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

def cmd_replace_plans(args):
    date_str = parse_date(args.date) if args.date else date.today().isoformat()
    try:
        new_plans = json.loads(args.plans)
    except json.JSONDecodeError:
        print(f"ERROR invalid plans JSON")
        return
    data = load("daily_logs.json")
    data.setdefault("plans", {})
    data["plans"][date_str] = []
    for p in new_plans:
        p.setdefault("type", "custom")
        data["plans"][date_str].append(p)
    save("daily_logs.json", data)
    print(f"OK replace_plans {date_str} | {len(new_plans)} items")

def cmd_delete_plan(args):
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

def cmd_add_course(args):
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

def cmd_delete_course(args):
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

def cmd_status(args):
    t = load("tasks.json")
    h = load("habits.json")
    c = load("courses.json")
    e = load("exams.json")
    pending = sum(1 for x in t.get("tasks", []) if x.get("status") != "completed")
    habits = len(h.get("habits", []))
    courses = len(c.get("courses", []))
    exams = len(e.get("exams", []))
    upcoming = [x for x in e.get("exams", []) if x.get("exam_date", "") >= date.today().isoformat()]
    print(f"tasks={pending} habits={habits} courses={courses} exams={len(upcoming)}")


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
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
        "status": cmd_status,
    }

    try:
        handlers[args.action](args)
    except Exception as e:
        print(f"ERROR {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
