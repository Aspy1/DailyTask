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

# 考试提醒阈值（天）——与 src/services/reminder_service.py 的 EXAM_DAYS 保持一致
EXAM_ALERT_DAYS = (14, 7, 3)


logger = logging.getLogger(__name__)


def load_json(path: Path) -> dict:
    """读 JSON；文件不存在时返回空 dict。

    摘要脚本跑在 GitHub Actions 上，某个数据文件可能尚未生成
    （如新装的 exams.json）；缺文件不应让整封日报失败。
    """
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.info("数据文件不存在，按空数据继续: %s", path.name)
        return {}


def _find_current_semester(courses_data: dict) -> dict | None:
    """按 current_semester id 查找学期记录；未找到返回 None。"""
    current_id = courses_data.get("current_semester", "")
    for s in courses_data.get("semesters", []):
        if s.get("id") == current_id:
            return s
    return None


def _week_number_for(courses_data: dict, target: date) -> int | None:
    """目标日期属当前学期第几周；学期缺失/尚未开学/超出总周数返回 None。"""
    semester = _find_current_semester(courses_data)
    if not semester or "start_date" not in semester:
        return None

    start = date.fromisoformat(semester["start_date"])
    delta = (target - start).days
    if delta < 0:
        return None
    week_number = delta // 7 + 1
    if week_number > semester.get("total_weeks", 20):
        return None
    return week_number


def _is_off_day(courses_data: dict, target: date) -> bool:
    """目标日期是否落在假期（holidays.excluded）。"""
    holidays = courses_data.get("holidays", {})
    return target.isoformat() in holidays.get("excluded", [])


def _effective_day_of_week(courses_data: dict, target: date) -> int:
    """调休覆盖后的星期几（1=周一 … 7=周日）。"""
    makeup = courses_data.get("holidays", {}).get("makeup", {})
    return makeup.get(target.isoformat(), target.isoweekday())


def _parity_matches(parity: str, week_number: int) -> bool:
    """单双周过滤：odd 只上奇数周，even 只上偶数周，其余不限。"""
    if parity == "odd":
        return week_number % 2 == 1
    if parity == "even":
        return week_number % 2 == 0
    return True


def _course_matches_week(course: dict, week_number: int) -> bool:
    """课程在指定周是否上课（周次区间 / 排除周 / 单双周）。"""
    weeks = course.get("weeks", {})
    if weeks and (week_number < weeks.get("start", 1) or week_number > weeks.get("end", 20)):
        return False
    if week_number in course.get("excluded_weeks", []):
        return False
    return _parity_matches(course.get("week_parity", "all"), week_number)


def get_courses_for_date(courses_data: dict, target: date) -> list[dict]:
    week_number = _week_number_for(courses_data, target)
    if week_number is None or _is_off_day(courses_data, target):
        return []

    day_of_week = _effective_day_of_week(courses_data, target)
    result = [
        c for c in courses_data.get("courses", [])
        if c.get("day_of_week") == day_of_week and _course_matches_week(c, week_number)
    ]

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


def _looks_like_exam(task: dict) -> bool:
    """旧数据的判定：标题或标签里带「考试」（与 reminder_service 保持一致）。"""
    text = task.get("title", "") + " " + " ".join(task.get("tags", []))
    return "考试" in text or "exam" in text.lower()


def collect_exam_items(tasks_data: dict, exams_data: dict) -> list[dict]:
    """考试来源：`exams.json`（权威）∪ 旧数据里当任务建的考试；按 (名称, 日期) 去重。"""
    items: dict[str, dict] = {}
    for e in exams_data.get("exams", []):
        _add_exam_item(items, e.get("course_name", ""), e.get("exam_date", ""))
    for t in tasks_data.get("tasks", []):
        if t.get("status") != "completed" and _looks_like_exam(t):
            _add_exam_item(items, t.get("title", ""), t.get("due_date", ""))
    return sorted(items.values(), key=lambda i: i["date"])


def _add_exam_item(items: dict[str, dict], name: str, date_str: str) -> None:
    name = (name or "").strip()
    day = (date_str or "")[:10]
    if not name or not day:
        return
    key = f"{name}@{day}"
    items.setdefault(key, {"key": key, "name": name, "date": day})


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
    exams = collect_exam_items(tasks_data, load_json(data_dir / "exams.json"))

    lines = [f"【每日日程】{today_str} {weekday}", ""]
    lines += _digest_summary(courses_data, pending, habits_data, today)
    lines += _digest_courses(courses_data, today)
    lines += _digest_plans(daily_data, today_str)
    lines += _digest_habits(habits_data, today)
    lines += _digest_urgent(pending, today)
    lines += _digest_exams(exams, today)
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
        lines.append(_urgent_line(t, today))
    return lines


def _urgent_line(t: dict, today) -> str:
    due = (t.get("due_date", "") or "")[:10]
    try:
        due_dt = date.fromisoformat(due) if due else None
    except ValueError:
        due_dt = None
    days_left = f"（{(due_dt - today).days}天后）" if due_dt and due_dt >= today else "（已过期）"
    course = t.get("course_name", "") or ""
    c_str = f" [{course}]" if course else ""
    return f"  • {due}: {t.get('title', '')}{c_str} {days_left}"


def _digest_exams(exam_items: list[dict], today) -> list[str]:
    """考试分区：14 天内的考试按剩余天数升序列出。"""
    lines = ["", "── 考试提醒 ──"]
    alerts = []
    for e in exam_items:
        try:
            days_left = (date.fromisoformat(e["date"]) - today).days
        except ValueError:
            continue
        if 0 <= days_left <= max(EXAM_ALERT_DAYS):
            alerts.append((days_left, e))
    if not alerts:
        lines.append("  （近期无考试）")
        return lines
    for days_left, e in sorted(alerts, key=lambda x: x[0]):
        lines.append(f"  • ⚠ 距「{e['name']}」还有 {days_left} 天（{e['date']}）")
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


def _records_on(expenses: dict, day: str, prefix_len: int) -> list[dict]:
    """取 records 中 date 前缀匹配的条目（prefix_len=10 按天，=7 按月）。"""
    return [r for r in expenses.get("records", [])
            if (r.get("date", "") or "")[:prefix_len] == day[:prefix_len]]


def _expense_lines(today_records: list, month_records: list, expenses: dict) -> list[str]:
    budget = expenses.get("budget", {}).get("monthly", 0)
    budget_str = f" / 预算 ¥{budget:.0f}" if budget else ""
    return [
        "", "── 支出 ──",
        f"  今日: ¥{sum(r.get('amount', 0) for r in today_records):.1f}（{len(today_records)}笔）",
        f"  本月: ¥{sum(r.get('amount', 0) for r in month_records):.1f}{budget_str}",
    ]


def _digest_expenses(data_dir: Path, today_str: str) -> list[str]:
    try:
        expenses = load_json(data_dir / "expenses.json")
        today_records = _records_on(expenses, today_str, 10)
        if not today_records:
            return []
        return _expense_lines(today_records, _records_on(expenses, today_str, 7), expenses)
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
