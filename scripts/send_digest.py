"""Standalone daily digest email — runs on GitHub Actions at 7:55 AM Beijing time.

Reads JSON data files from the repo. No Qt dependencies.
Config via environment variables / GitHub Secrets:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
  DATA_DIR — path to data/ directory (default: ./data)
"""

import json
import logging
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


logger = logging.getLogger(__name__)


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
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
        if weeks and (week_number < weeks.get("start", 1) or week_number > weeks.get("end", 20)):
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
        if schedule.get("start_date"):
            try:
                start = date.fromisoformat(schedule["start_date"])
                delta = (today - start).days
                if delta < 0:
                    return False
                return delta % schedule.get("value", 1) == 0
            except (ValueError, TypeError):
                logger.debug("is_habit_active_today 中忽略异常", exc_info=True)
        return True


def is_habit_done_today(habit: dict, logs: dict, today: date) -> bool:
    day_log = logs.get(today.isoformat(), {})
    entry = day_log.get(habit["id"], {})
    return entry.get("completed", False)


def _beijing_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def build_digest(data_dir: Path) -> str:
    """组装每日摘要文本（按分区拼接）。"""
    today = _beijing_today()
    today_str = today.isoformat()
    weekday = WEEKDAY_NAMES[today.weekday()]

    courses_data = load_json(data_dir / "courses.json")
    tasks_data = load_json(data_dir / "tasks.json")
    habits_data = load_json(data_dir / "habits.json")
    daily_data = load_json(data_dir / "daily_logs.json")
    pending = [t for t in tasks_data.get("tasks", []) if t.get("status") != "completed"]

    lines = [f"【每日日程】{today_str} {weekday}", ""]
    lines += _digest_summary(courses_data, pending, habits_data, today)
    lines += _digest_courses(courses_data, today)
    lines += _digest_plans(daily_data, today_str)
    lines += _digest_habits(habits_data, today)
    lines += _digest_urgent(pending, today)
    lines += _digest_exams(pending, today)
    lines += _digest_balance(data_dir)
    lines += _digest_expenses(data_dir, today_str)
    lines += _digest_shopping(data_dir)
    return "\n".join(lines)


def _digest_summary(courses_data: dict, pending: list, habits_data: dict, today) -> list[str]:
    threshold_3d = (today + timedelta(days=3)).isoformat()
    urgent_ddl = len([t for t in pending if t.get("due_date", "") and t["due_date"] < threshold_3d])
    logs = habits_data.get("logs", {})
    active_h = [h for h in habits_data.get("habits", []) if is_habit_active_today(h, today)]
    done_h = sum(1 for h in active_h if is_habit_done_today(h, logs, today))
    ddl_str = f" | ⚠ {urgent_ddl}项DDL" if urgent_ddl else ""
    return [
        f"📋 {len(get_courses_for_date(courses_data, today))}节课 | {done_h}/{len(active_h)}项日常{ddl_str}",
        "",
    ]


def _digest_courses(courses_data: dict, today) -> list[str]:
    lines = ["── 今日课程 ──"]
    courses = get_courses_for_date(courses_data, today)
    if not courses:
        lines.append("  （无课）")
        return lines
    for c in courses:
        time_str = ""
        slots = c.get("time_slots", [])
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
        lines.append(f"  • {c.get('name', '')}{time_str}{loc_str}")
    return lines


def _digest_plans(daily_data: dict, today_str: str) -> list[str]:
    plans = daily_data.get("plans", {}).get(today_str, [])
    if not plans:
        return []
    lines = ["", "── 今日计划 ──"]
    for p in plans:
        lines.append(f"  • 时段{p.get('time_slot', '?')}: {p.get('title', '')}")
    return lines


def _digest_habits(habits_data: dict, today) -> list[str]:
    logs = habits_data.get("logs", {})
    active = [(h, is_habit_done_today(h, logs, today))
              for h in habits_data.get("habits", []) if is_habit_active_today(h, today)]
    lines = ["", "── 今日习惯 ──"]
    if not active:
        lines.append("  （无）")
        return lines
    for h, done in active:
        rt = h.get("reminder_time", "")
        rt_str = f" ({rt})" if rt else ""
        lines.append(f"  {'✓' if done else '○'} {h.get('name', '')}{rt_str}")
    return lines


def _digest_urgent(pending: list, today) -> list[str]:
    threshold_3d = (today + timedelta(days=3)).isoformat()
    urgent = [t for t in pending if t.get("due_date", "") and t["due_date"] < threshold_3d]
    lines = ["", "── 即将截止的任务（3天内）──"]
    if not urgent:
        lines.append("  （无即将截止的任务）")
        return lines
    for t in sorted(urgent, key=lambda t: t.get("due_date", "")):
        due = (t.get("due_date", "") or "")[:10]
        try:
            due_dt = date.fromisoformat(due) if due else None
        except ValueError:
            due_dt = None
        days_left = f"（{(due_dt - today).days}天后）" if due_dt and due_dt >= today else "（已过期）"
        course = t.get("course_name", "") or ""
        c_str = f" [{course}]" if course else ""
        lines.append(f"  • {due}: {t.get('title', '')}{c_str} {days_left}")
    return lines


def _digest_exams(pending: list, today) -> list[str]:
    lines = ["", "── 考试提醒 ──"]
    alerts = []
    for t in pending:
        if "考试" not in (t.get("title", "") + " ".join(t.get("tags", []))):
            continue
        due_str = (t.get("due_date", "") or "")[:10]
        if not due_str:
            continue
        try:
            days_left = (date.fromisoformat(due_str) - today).days
        except ValueError:
            continue
        if days_left >= 0 and (days_left in (14, 7, 3) or days_left <= 3):
            alerts.append((days_left, t))
    if not alerts:
        lines.append("  （近期无考试）")
        return lines
    for days_left, t in sorted(alerts, key=lambda x: x[0]):
        lines.append(f"  • ⚠ 距「{t.get('title', '')}」还有 {days_left} 天（{t.get('due_date', '')[:10]}）")
    return lines


def _digest_balance(data_dir: Path) -> list[str]:
    """余额分区（读 settings.ini；缺文件/缺配置则静默跳过）。"""
    try:
        import configparser
        config = configparser.ConfigParser()
        config.read(data_dir / "settings.ini", encoding="utf-8")
        bal_lines = []
        for key, label in [("campus_card", "校园卡"), ("water_card", "水卡"), ("electricity", "电费")]:
            bal = config.get("Balance", f"{key}_balance", fallback="")
            thr = config.get("Balance", f"{key}_threshold", fallback="")
            if not bal:
                continue
            try:
                b = float(bal)
                t = float(thr) if thr else 0
            except ValueError:
                continue
            s = f"  {label}: ¥{b:.1f}"
            if b <= t:
                s += f" ⚠ 低于阈值 {t:.0f} 元"
            bal_lines.append(s)
        if not bal_lines:
            return []
        return ["", "── 余额 ──", *bal_lines]
    except Exception:
        logger.debug("_digest_balance 中忽略异常", exc_info=True)
        return []


def _digest_expenses(data_dir: Path, today_str: str) -> list[str]:
    try:
        expenses = load_json(data_dir / "expenses.json")
        records = expenses.get("records", [])
        today_records = [r for r in records if (r.get("date", "") or "")[:10] == today_str]
        if not today_records:
            return []
        month_records = [r for r in records if (r.get("date", "") or "")[:7] == today_str[:7]]
        budget = expenses.get("budget", {}).get("monthly", 0)
        budget_str = f" / 预算 ¥{budget:.0f}" if budget else ""
        return [
            "", "── 支出 ──",
            f"  今日: ¥{sum(r.get('amount', 0) for r in today_records):.1f}（{len(today_records)}笔）",
            f"  本月: ¥{sum(r.get('amount', 0) for r in month_records):.1f}{budget_str}",
        ]
    except Exception:
        logger.debug("_digest_expenses 中忽略异常", exc_info=True)
        return []


def _digest_shopping(data_dir: Path) -> list[str]:
    try:
        needs = [i for i in load_json(data_dir / "inventory.json").get("items", [])
                 if i.get("status") == "need"]
        if not needs:
            return []
        lines = ["", "── 购物需求 ──"]
        for i in needs:
            cat = i.get("category", "")
            lines.append(f"  • {i.get('name', '')}{f' [{cat}]' if cat else ''}")
        return lines
    except Exception:
        logger.debug("_digest_shopping 中忽略异常", exc_info=True)
        return []


def send_email(subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    pwd = os.environ.get("SMTP_PASS", "")

    if not user or not pwd:
        print("ERROR: SMTP_USER or SMTP_PASS not set")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = user

    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
        print(f"Email sent: {subject}")
    # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
    except Exception as e:  # noqa: BLE001
        print(f"ERROR sending email: {e}")


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
