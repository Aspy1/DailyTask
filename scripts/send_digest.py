"""Standalone daily digest email — runs on GitHub Actions at 7:55 AM Beijing time.

Reads JSON data files from the repo. No Qt dependencies.
Config via environment variables / GitHub Secrets:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
  DATA_DIR — path to data/ directory (default: ./data)
"""

import json
import os
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

PERIOD_TIMES = [
    ("08:30", "10:05"),
    ("10:25", "12:00"),
    ("13:30", "15:05"),
    ("15:25", "17:00"),
    ("18:30", "20:05"),
    ("20:10", "21:45"),
]

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_courses_for_date(courses_data: dict, target: date) -> list[dict]:
    semesters = courses_data.get("semesters", [])
    current_id = courses_data.get("current_semester", "")
    semester = None
    for s in semesters:
        if s.get("id") == current_id:
            semester = s
            break
    if not semester or "start_date" not in semester:
        return []

    start = date.fromisoformat(semester["start_date"])
    delta = (target - start).days
    if delta < 0:
        return []
    week_number = delta // 7 + 1
    total = semester.get("total_weeks", 20)
    if week_number > total:
        return []

    # Holiday check
    holidays = courses_data.get("holidays", {})
    target_str = target.isoformat()
    if target_str in holidays.get("excluded", []):
        return []
    makeup = holidays.get("makeup", {})
    day_of_week = makeup.get(target_str, target.isoweekday())

    result = []
    for c in courses_data.get("courses", []):
        if c.get("day_of_week") != day_of_week:
            continue
        weeks = c.get("weeks", {})
        if weeks:
            if week_number < weeks.get("start", 1) or week_number > weeks.get("end", 20):
                continue
        if week_number in c.get("excluded_weeks", []):
            continue
        parity = c.get("week_parity", "all")
        if parity == "odd" and week_number % 2 == 0:
            continue
        if parity == "even" and week_number % 2 == 1:
            continue
        result.append(c)

    result.sort(key=lambda c: c.get("time_slots", [{"start": 0}])[0]["start"])
    return result


def is_habit_active_today(habit: dict, today: date) -> bool:
    today_str = today.isoformat()
    pu = habit.get("postpone_until")
    if pu:
        pu_date = pu[:10]
        if pu_date == today_str:
            return True
        if pu_date > today_str:
            return False

    if today_str in habit.get("canceled_on", []):
        return False

    schedule = habit.get("schedule", {"type": "interval", "value": 1, "unit": "day"})
    if schedule.get("type") == "weekly":
        return today.isoweekday() in schedule.get("days", [])
    else:
        if "start_date" in schedule and schedule["start_date"]:
            try:
                start = date.fromisoformat(schedule["start_date"])
                delta = (today - start).days
                if delta < 0:
                    return False
                return delta % schedule.get("value", 1) == 0
            except (ValueError, TypeError):
                pass
        return True


def is_habit_done_today(habit: dict, logs: dict, today: date) -> bool:
    day_log = logs.get(today.isoformat(), {})
    entry = day_log.get(habit["id"], {})
    return entry.get("completed", False)


def _beijing_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def build_digest(data_dir: Path) -> str:
    today = _beijing_today()
    today_str = today.isoformat()
    weekday = WEEKDAY_NAMES[today.weekday()]

    courses_data = load_json(data_dir / "courses.json")
    tasks_data = load_json(data_dir / "tasks.json")
    habits_data = load_json(data_dir / "habits.json")
    daily_data = load_json(data_dir / "daily_logs.json")

    lines = [f"【每日日程】{today_str} {weekday}", ""]

    # ── Courses ──────────────────────────────────────────
    courses = get_courses_for_date(courses_data, today)
    lines.append("── 今日课程 ──")
    if courses:
        for c in courses:
            name = c.get("name", "")
            slots = c.get("time_slots", [])
            time_str = ""
            if slots:
                s_idx = slots[0]["start"] - 1
                try:
                    e_idx = min(max(s["end"] for s in slots) - 1, len(PERIOD_TIMES) - 1)
                except (IndexError, KeyError):
                    e_idx = s_idx
                if 0 <= s_idx < len(PERIOD_TIMES) and 0 <= e_idx < len(PERIOD_TIMES):
                    time_str = f" {PERIOD_TIMES[s_idx][0]}-{PERIOD_TIMES[e_idx][1]}"
            location = c.get("location", "")
            loc_str = f" ({location})" if location else ""
            lines.append(f"  • {name}{time_str}{loc_str}")
    else:
        lines.append("  （无课）")

    # ── Plans ────────────────────────────────────────────
    plans = daily_data.get("plans", {}).get(today_str, [])
    if plans:
        lines.append("")
        lines.append("── 今日计划 ──")
        for p in plans:
            ts = p.get("time_slot", "?")
            lines.append(f"  • 时段{ts}: {p.get('title', '')}")

    # ── Habits ───────────────────────────────────────────
    lines.append("")
    lines.append("── 今日习惯 ──")
    active_habits = []
    for h in habits_data.get("habits", []):
        if is_habit_active_today(h, today):
            done = is_habit_done_today(h, habits_data.get("logs", {}), today)
            active_habits.append((h, done))
    if active_habits:
        for h, done in active_habits:
            rt = h.get("reminder_time", "")
            rt_str = f" ({rt})" if rt else ""
            status = "✓" if done else "○"
            lines.append(f"  {status} {h.get('name', '')}{rt_str}")
    else:
        lines.append("  （无）")

    # ── Urgent DDL (within 3 days) ───────────────────────
    lines.append("")
    lines.append("── 即将截止的任务（3天内）──")
    pending_tasks = [t for t in tasks_data.get("tasks", []) if t.get("status") != "completed"]
    threshold_3d = (today + timedelta(days=3)).isoformat()
    urgent = [t for t in pending_tasks if t.get("due_date", "") and t["due_date"] < threshold_3d]
    if urgent:
        urgent.sort(key=lambda t: t.get("due_date", ""))
        for t in urgent:
            due = (t.get("due_date", "") or "")[:10]
            due_dt = date.fromisoformat(due) if due else None
            days_left = f"（{(due_dt - today).days}天后）" if due_dt and due_dt >= today else "（已过期）"
            course = t.get("course_name", "") or ""
            c_str = f" [{course}]" if course else ""
            lines.append(f"  • {due}: {t.get('title', '')}{c_str} {days_left}")
    else:
        lines.append("  （无即将截止的任务）")

    # ── Exam reminders ────────────────────────────────────
    lines.append("")
    lines.append("── 考试提醒 ──")
    exam_tasks = [t for t in pending_tasks if "考试" in (t.get("title", "") + " ".join(t.get("tags", [])))]
    exam_alerts = []
    for t in exam_tasks:
        due_str = (t.get("due_date", "") or "")[:10]
        if not due_str:
            continue
        try:
            due_dt = date.fromisoformat(due_str)
        except ValueError:
            continue
        days_left = (due_dt - today).days
        if days_left < 0:
            continue
        if days_left in (14, 7, 3) or days_left <= 3:
            exam_alerts.append((days_left, t))
    if exam_alerts:
        exam_alerts.sort(key=lambda x: x[0])
        for days_left, t in exam_alerts:
            lines.append(f"  • ⚠ 距「{t.get('title', '')}」还有 {days_left} 天（{t.get('due_date', '')[:10]}）")
    else:
        lines.append("  （近期无考试）")

    # ── Balance ──────────────────────────────────────────
    # Read settings.ini for balance info
    try:
        import configparser
        config = configparser.ConfigParser()
        config.read(data_dir / "settings.ini", encoding="utf-8")
        bal_lines = []
        for key, label in [("campus_card", "校园卡"), ("water_card", "水卡"), ("electricity", "电费")]:
            bal = config.get("Balance", f"{key}_balance", fallback="")
            thr = config.get("Balance", f"{key}_threshold", fallback="")
            if bal:
                try:
                    b = float(bal)
                    t = float(thr) if thr else 0
                    s = f"  {label}: ¥{b:.1f}"
                    if b <= t:
                        s += f" ⚠ 低于阈值 {t:.0f} 元"
                    bal_lines.append(s)
                except ValueError:
                    pass
        if bal_lines:
            lines.append("")
            lines.append("── 余额 ──")
            lines.extend(bal_lines)
    except Exception:
        pass

    return "\n".join(lines)


def send_email(subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pwd = os.environ["SMTP_PASS"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = user

    with smtplib.SMTP(host, port, timeout=15) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)

    print(f"Email sent: {subject}")


def main() -> None:
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        return

    today = _beijing_today()
    today_str = today.isoformat()
    weekday = WEEKDAY_NAMES[today.weekday()]

    body = build_digest(data_dir)
    send_email(f"每日日程 - {today_str} {weekday}", body)


if __name__ == "__main__":
    main()
