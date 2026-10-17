"""提醒规则的**纯计算**部分：算"该提醒什么"，不负责发。

为什么单独成模块：`ReminderService` 原本既是规则又是发送，方法越堆越多
（2026-10-16 加点名/3 天两条规则时，类已 526 行，超过「单类 ≤400」）。
拆开后服务层只剩接线 —— **读数据 → 调这里 → 发提醒** —— 而"什么算命中"
成了可单测的纯函数（给定数据 + 已发送集合 → 该提醒哪些）。

约束：本模块**无 Qt、无 I/O**（`balance_alerts` 只读设置），import 它不会拉起界面依赖。
"""

from datetime import date, datetime, timedelta

from src.models.course import ATTENDANCE_LEAD_MINUTES, PERIOD_TIMES

DDL_REMIND_DAYS = 3          # 作业截止前多少天提醒
DDL_EMAIL_HOURS = 6          # 距截止多少小时内发紧急邮件


# ── 点名提醒（会点名的课）────────────────────────────────────

def course_start_time(course: dict) -> str | None:
    """课程开始时间：取最早一节的开始（`PERIOD_TIMES`）；无有效节次返回 None。"""
    slots = course.get("time_slots") or []
    starts = [s.get("start") for s in slots if isinstance(s.get("start"), int)]
    if not starts:
        return None
    idx = min(starts) - 1
    if not 0 <= idx < len(PERIOD_TIMES):
        return None
    return PERIOD_TIMES[idx][0]


def _minutes_of(value: str) -> int | None:
    """'HH:MM' → 当天分钟数；格式非法返回 None。"""
    try:
        hh, mm = value.split(":")
        return int(hh) * 60 + int(mm)
    except ValueError:
        return None


def attendance_due(courses: list[dict], now: datetime,
                   sent: set[str]) -> list[tuple[dict, str]]:
    """今天「会点名」且正处在提醒窗口内的课 → [(course, 开始时间)]。

    窗口是 `start - lead <= now < start`：课已经开始就不再提醒（迟到的点名提醒
    没有意义）；`sent` 里记过的（同一门课同一天）不再返回。
    """
    out: list[tuple[dict, str]] = []
    now_minutes = now.hour * 60 + now.minute
    for course in courses:
        conf = course.get("reminders") or {}
        if not conf.get("attendance"):
            continue
        start_str = course_start_time(course)
        start_minutes = _minutes_of(start_str) if start_str else None
        if start_minutes is None:
            continue
        lead = int(conf.get("lead_minutes") or ATTENDANCE_LEAD_MINUTES)
        key = f"{course.get('id', '')}@{now.date().isoformat()}@{start_str}"
        if key in sent:
            continue
        if 0 <= start_minutes - now_minutes <= lead:
            out.append((course, start_str))
    return out


def attendance_body(course: dict, start_str: str) -> str:
    """点名提醒正文（含地点，便于直接出门）。"""
    slots = course.get("time_slots") or []
    first = slots[0] if slots else {}
    location = str(first.get("location") or course.get("location") or "")
    loc = f"\n地点: {location}" if location else ""
    return (f"「{course.get('name', '')}」{start_str} 开始{loc}\n"
            f"这门课会点名，记得按时到、别忘了签到。")


# ── 作业截止提醒（3 天 / 6 小时两条规则）────────────────────

def ddl_reminder_due(pending: list[dict], today: date,
                     sent: set[str]) -> list[tuple[dict, int]]:
    """3 天内截止、尚未提醒过的作业 → [(task, 剩余天数)]。"""
    out: list[tuple[dict, int]] = []
    for t in pending:
        due_str = (t.get("due_date") or "")[:10]
        if not due_str:
            continue
        try:
            days_left = (date.fromisoformat(due_str) - today).days
        except ValueError:
            continue
        key = f"{t.get('id', '')}@{due_str}"
        if 0 <= days_left <= DDL_REMIND_DAYS and key not in sent:
            out.append((t, days_left))
    return out


def ddl_reminder_body(matched: list[tuple[dict, int]]) -> str:
    """3 天提醒正文。"""
    lines = [f"以下任务将在 {DDL_REMIND_DAYS} 天内截止：", ""]
    for t, days_left in matched:
        course = t.get("course_name", "") or ""
        c_str = f" [{course}]" if course else ""
        when = "今天" if days_left == 0 else f"{days_left} 天后"
        lines.append(f"  • {t.get('title', '')}{c_str}  截止: "
                     f"{(t.get('due_date') or '')[:16]}（{when}）")
    return "\n".join(lines)


def ddl_email_due(pending: list[dict], now: datetime, sent: set[str]) -> list[dict]:
    """6 小时内截止、尚未发过邮件的作业 → [task]。"""
    threshold = now + timedelta(hours=DDL_EMAIL_HOURS)
    out: list[dict] = []
    for t in pending:
        tid = t.get("id", "")
        due_str = t.get("due_date", "")
        if not due_str or tid in sent:
            continue
        try:
            due_dt = datetime.fromisoformat(due_str)
        except ValueError:
            continue
        if now <= due_dt <= threshold:
            out.append(t)
    return out


def ddl_email_body(matched: list[dict]) -> str:
    """6 小时紧急邮件正文。"""
    lines = [f"以下任务将在 {DDL_EMAIL_HOURS} 小时内截止：", ""]
    for t in matched:
        due = (t.get("due_date", "") or "")[:16]
        course = t.get("course_name", "") or ""
        c_str = f" [{course}]" if course else ""
        lines.append(f"  • {t.get('title', '')}{c_str}  截止: {due}")
    return "\n".join(lines)


# ── 余额 ────────────────────────────────────────────────────

def balance_alerts(settings) -> list[str]:
    """低于阈值的余额提示（每项需在设置里启用）。"""
    labels = {"campus_card": "校园卡", "water_card": "水卡", "electricity": "电费"}
    alerts: list[str] = []
    for key, label in labels.items():
        if not settings.get_bool("Balance", f"{key}_enabled"):
            continue
        bal_str = settings.get("Balance", f"{key}_balance")
        thr_str = settings.get("Balance", f"{key}_threshold")
        if not bal_str or not thr_str:
            continue
        try:
            balance = float(bal_str)
            threshold = float(thr_str)
        except ValueError:
            continue
        if balance <= threshold:
            alerts.append(f"{label}余额 ¥{balance:.1f}，已低于阈值 ¥{threshold:.0f}")
    return alerts


# ── 补货（「有什么」里需购 / 不足的物品）──────────────────────
def restock_body(items: list[dict]) -> str:
    """需要补货的物品 → 一条提醒正文。

    **选择**逻辑在 `InventoryModel.need_restock()`（已排除 `ignore_low_stock` 的物品），
    这里只管排版。
    """
    return "\n".join(
        f"· {it.get('name', '')}（剩 {it.get('quantity', 0)}{it.get('unit', '件')}"
        f" · {it.get('status', '')}）"
        for it in items)


# ── 自定义提醒（用户在日程里定的）────────────────────────────

def parse_notify_time(value: str) -> datetime | None:
    """解析提醒时间；缺失或非法返回 None。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def pending_custom_reminders(reminders: list[dict], now: datetime,
                             stale_cutoff: datetime) -> tuple[list[dict], list[str]]:
    """→ (该触发的, 该删除的)。

    失效（时间无法解析）与过期（超过 `stale_cutoff`）只进删除列表、不触发。
    """
    to_fire: list[dict] = []
    to_delete: list[str] = []
    for r in reminders:
        rid = r.get("id", "")
        notify_dt = parse_notify_time(r.get("notify_time", ""))
        if notify_dt is None or notify_dt < stale_cutoff:
            to_delete.append(rid)
            continue
        if now >= notify_dt:
            to_fire.append(r)
    return to_fire, to_delete


def expired_custom_reminder_ids(reminders: list[dict], now: datetime,
                                to_delete: list[str]) -> None:
    """把超过 1 天的提醒 id 追加进待删除列表（原地改 to_delete）。"""
    cutoff = (now - timedelta(days=1)).isoformat()
    for r in reminders:
        rid = r.get("id", "")
        notify_time = r.get("notify_time", "")
        if rid not in to_delete and notify_time and notify_time < cutoff:
            to_delete.append(rid)
