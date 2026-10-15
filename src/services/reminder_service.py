"""Reminder service — local notifications and mandatory email alerts.

Email reminders (mandatory, sent regardless of user preference):
  - DDL within 6 hours → email
  - Exam within 14/7/3 days → email + tray

Tray-only (default, user can opt into email):
  - Habit 5-min early notification → tray
  - Balance low → tray + email (once per day)
  - DDL 3-day tray notification

Note: the full daily digest (courses, plans, habits, DDL 3d, exams 14/7/3d)
runs via GitHub Actions at 7:55 AM. This service only handles time-sensitive
checks that need sub-day granularity.
"""

import logging
import smtplib
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText

from PySide6.QtCore import QObject, QTimer, Signal

from src.models.course import schedule_date

logger = logging.getLogger("reminder")

EARLY_NOTIFY_MINUTES = 5
CATCHUP_THRESHOLD_MINUTES = 2
LOOKAHEAD_MINUTES = 60
DDL_EMAIL_HOURS = 6          # send email when DDL is within 6 hours
EXAM_DAYS = [14, 7, 3]       # exam reminder thresholds (days before)


def _looks_like_exam(task: dict) -> bool:
    """旧数据的判定：标题或标签里带「考试」。"""
    text = task.get("title", "") + " " + " ".join(task.get("tags", []))
    return "考试" in text or "exam" in text.lower()


def _add_exam_item(items: dict[str, dict], name: str, date_str: str) -> None:
    """按 (名称, 日期) 归一化写入考试集合；名称/日期缺失则忽略。"""
    name = (name or "").strip()
    day = (date_str or "")[:10]
    if not name or not day:
        return
    key = f"{name}@{day}"
    items.setdefault(key, {"key": key, "name": name, "date": day})


class ReminderService(QObject):
    reminder_notify = Signal(str, str)   # tray notification
    ddl_alert = Signal(int)             # urgent DDL count for red dot + flash

    def __init__(self, settings, data_manager, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._dm = data_manager

        raw = self._settings.get("Email", "last_reminder_check", fallback="")
        self._last_check = datetime.fromisoformat(raw) if raw else datetime.now()

        self._notified_today: set[str] = set()
        self._notified_date = ""
        self._ddl_emailed: set[str] = set()       # DDL IDs already emailed (6h window)
        self._exam_emailed: dict[str, set[int]] = {}  # exam_id -> {days thresholds already sent}
        self._balance_notified_today = False
        self._custom_reminded: set[str] = set()   # custom reminder IDs already sent

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(60_000)

    def start(self) -> None:
        """Run initial checks after signals are connected."""
        self._catch_up()
        self._check_ddl()
        self._check_balances()
        # Refresh DDL count on task changes
        self._dm.data_changed.connect(self._on_data_changed)

    # ── Catch-up ──────────────────────────────────────────

    def _catch_up(self) -> None:
        now = datetime.now()
        delta = now - self._last_check
        if delta <= timedelta(minutes=CATCHUP_THRESHOLD_MINUTES):
            return

        logger.info("Catch-up: scanning from %s to %s (gap: %s)",
                     self._last_check.time(), now.time(), delta)

        self._reset_notified_if_new_day(now)

        matched = self._collect_catchup_habits(now)
        if matched:
            for h in matched:
                self._notified_today.add(h["id"])
            self._send_habit_tray_batch(matched)

        self._last_check = now
        self._settings.set("Email", "last_reminder_check", now.isoformat())
        self._settings.save()

    def _collect_catchup_habits(self, now: datetime) -> list[dict]:
        """逐分钟扫描 last_check→now，收集提醒时间命中且未通知的习惯。"""
        matched: list[dict] = []
        seen: set[str] = set()
        cursor = self._last_check.replace(second=0, microsecond=0)
        while cursor <= now:
            cursor_str = cursor.strftime("%H:%M")
            for h in self._dm.habits.habits:
                if self._is_catchup_hit(h, cursor_str, seen):
                    seen.add(h["id"])
                    matched.append(h)
            cursor += timedelta(minutes=1)
        return matched

    def _is_catchup_hit(self, habit: dict, cursor_str: str, seen: set[str]) -> bool:
        """该习惯是否在 cursor_str 这一分钟命中补发提醒。"""
        hid = habit["id"]
        rt = habit.get("reminder_time", "").strip()
        if not self._dm.habits.is_active_today(hid):
            return False
        return bool(rt and rt == cursor_str and hid not in seen and hid not in self._notified_today)

    # ── Regular check ─────────────────────────────────────

    def _check(self) -> None:
        now = datetime.now()
        now_str = now.strftime("%H:%M")
        early_str = (now + timedelta(minutes=EARLY_NOTIFY_MINUTES)).strftime("%H:%M")

        self._reset_notified_if_new_day(now)
        now_minutes = now.hour * 60 + now.minute

        # ── Habits: tray notification only ────────────────
        self._check_habits(now_str, early_str, now_minutes)

        # ── DDL email: within 6 hours ─────────────────────
        self._check_ddl_email(now)

        # ── Exam email: 14/7/3 days ───────────────────────
        self._check_exam_email()

        # ── DDL red dot ───────────────────────────────────
        self._check_ddl()

        # ── Custom email reminders ─────────────────────────
        self._check_custom_reminders(now)

        # ── Balance (daily) ───────────────────────────────
        today_str = now.strftime("%Y-%m-%d")
        if not self._balance_notified_today or \
           self._settings.get("Balance", "last_balance_notify_date", fallback="") != today_str:
            self._check_balances()

        self._last_check = now
        self._settings.set("Email", "last_reminder_check", now.isoformat())
        self._settings.save()

    def _check_habits(self, now_str: str, early_str: str, now_minutes: int) -> None:
        """习惯托盘提醒：提前 5 分钟预告 + 到点合并批次通知。"""
        for h in self._dm.habits.habits:
            rt = h.get("reminder_time", "").strip()
            if not rt or not self._dm.habits.is_active_today(h["id"]):
                continue

            if rt == early_str:
                self.reminder_notify.emit(
                    "即将开始",
                    f"「{h['name']}」将在 {EARLY_NOTIFY_MINUTES} 分钟后开始",
                )

            if rt == now_str and h["id"] not in self._notified_today:
                batch = self._collect_habit_batch(h, now_minutes)
                for bh in batch:
                    self._notified_today.add(bh["id"])
                self._send_habit_tray_batch(batch)

    def _collect_habit_batch(self, first: dict, now_minutes: int) -> list[dict]:
        """收集 now 之后 LOOKAHEAD_MINUTES 内待提醒的习惯（含 first）。"""
        batch = [first]
        for h2 in self._dm.habits.habits:
            if h2["id"] == first["id"]:
                continue
            rt2 = h2.get("reminder_time", "").strip()
            if not rt2 or h2["id"] in self._notified_today:
                continue
            if not self._dm.habits.is_active_today(h2["id"]):
                continue
            rt2_minutes = self._parse_hhmm(rt2)
            if rt2_minutes is None:
                continue
            if 0 <= rt2_minutes - now_minutes <= LOOKAHEAD_MINUTES:
                batch.append(h2)
        return batch

    @staticmethod
    def _parse_hhmm(value: str) -> int | None:
        """把 "HH:MM" 解析为当天分钟数；格式非法返回 None。"""
        try:
            hh, mm = value.split(":")
            return int(hh) * 60 + int(mm)
        except ValueError:
            return None

    def _reset_notified_if_new_day(self, now: datetime) -> None:
        today_str = now.strftime("%Y-%m-%d")
        if today_str != self._notified_date:
            self._notified_today.clear()
            self._notified_date = today_str

    # ── Habit tray (no email by default) ──────────────────

    def _send_habit_tray_batch(self, habits: list[dict]) -> None:
        for h in habits:
            self.reminder_notify.emit(
                "习惯提醒",
                f"该做「{h.get('name', '')}」了",
            )

    # ── DDL email (6 hours) ──────────────────────────────

    def _check_ddl_email(self, now: datetime) -> None:
        """Send email for DDLs due within the next 6 hours."""
        matched = self._collect_ddl_email_batch(now)
        if matched:
            self._send_email("DDL 紧急提醒", self._build_ddl_email_body(matched))

    def _collect_ddl_email_batch(self, now: datetime) -> list[dict]:
        """收集 6 小时内截止且未发过邮件的任务，并登记为已发送。"""
        threshold = (now + timedelta(hours=DDL_EMAIL_HOURS))
        matched = []
        for t in self._dm.tasks.pending:
            tid = t.get("id", "")
            due_str = t.get("due_date", "")
            if not due_str:
                continue
            try:
                due_dt = datetime.fromisoformat(due_str)
            except ValueError:
                continue
            if now <= due_dt <= threshold and tid not in self._ddl_emailed:
                matched.append(t)
                self._ddl_emailed.add(tid)
        return matched

    @staticmethod
    def _build_ddl_email_body(matched: list[dict]) -> str:
        """组装 DDL 紧急提醒邮件正文。"""
        lines = ["以下任务将在 6 小时内截止：", ""]
        for t in matched:
            due = (t.get("due_date", "") or "")[:16]
            course = t.get("course_name", "") or ""
            c_str = f" [{course}]" if course else ""
            lines.append(f"  • {t.get('title', '')}{c_str}  截止: {due}")
        return "\n".join(lines)

    # ── Exam email ────────────────────────────────────────

    def _check_exam_email(self) -> None:
        """考试提醒：14/7/3 天阈值，邮件 + 托盘。

        数据源是**合并**的：`exams.json`（权威）+ 旧数据里标题/标签含「考试」的待办任务。
        早期版本的考试是当普通任务建的，不合并会漏掉那批历史数据（ERRORS #022）。
        """
        today = schedule_date()
        for item in self._collect_exam_items():
            self._check_exam_item(item, today)

    def _collect_exam_items(self) -> list[dict]:
        """合并 exams.json 与任务里的考试，按 (名称, 日期) 去重。"""
        items: dict[str, dict] = {}
        exams_model = getattr(self._dm, "exams", None)
        for e in (exams_model.exams if exams_model is not None else []):
            _add_exam_item(items, e.get("course_name", ""), e.get("exam_date", ""))
        for t in self._dm.tasks.pending:
            if not _looks_like_exam(t):
                continue
            _add_exam_item(items, t.get("title", ""), t.get("due_date", ""))
        return list(items.values())

    def _check_exam_item(self, item: dict, today: date) -> None:
        """单个考试的阈值检查：一次检查**只发一封**，其余命中的阈值一并登记。

        历史缺陷：三个阈值用 `days_left <= d` 各自判定 → 剩 3 天时 14/7/3 一起命中，
        同一场考试当天发 3 封（ERRORS #023）。
        """
        try:
            days_left = (date.fromisoformat(item["date"]) - today).days
        except ValueError:
            logger.debug("考试日期非法，跳过: %s", item.get("date"))
            return
        if days_left < 0:
            return

        emailed = self._exam_emailed.setdefault(item["key"], set())
        hit = [d for d in EXAM_DAYS if days_left <= d and d not in emailed]
        if not hit:
            return
        emailed.update(hit)

        name = item["name"]
        self._send_email(
            f"考试提醒 - {name}",
            f"「{name}」还有 {days_left} 天考试\n日期: {item['date']}",
        )
        self.reminder_notify.emit("考试提醒", f"「{name}」还有 {days_left} 天")

    # ── DDL red dot ───────────────────────────────────────

    def _check_ddl(self) -> None:
        # 与 _check_exam_email 统一用 schedule_date()：0:00–1:00 视为前一天
        # （ARCHITECTURE §7 不变量 4）
        threshold_date = schedule_date() + timedelta(days=3)
        pending = self._dm.tasks.pending
        urgent_count = 0
        for t in pending:
            due_str = t.get("due_date", "")
            if not due_str:
                continue
            try:
                due_date = date.fromisoformat(due_str[:10])
                if due_date <= threshold_date:
                    urgent_count += 1
            except (ValueError, TypeError):
                logger.debug("ReminderService._check_ddl 中忽略异常", exc_info=True)
        self.ddl_alert.emit(urgent_count)

    def _on_data_changed(self, action: str) -> None:
        """Refresh DDL count when tasks change.

        外部写入（TG）给的是 `external`，看不出改了哪个域 → 一并重算。
        """
        if "task" in action or action in ("external", "internal"):
            self._check_ddl()

    # ── Balance ───────────────────────────────────────────

    def _check_balances(self) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        labels = {"campus_card": "校园卡", "water_card": "水卡", "electricity": "电费"}
        alerts: list[str] = []
        for key, label in labels.items():
            if not self._settings.get_bool("Balance", f"{key}_enabled"):
                continue
            bal_str = self._settings.get("Balance", f"{key}_balance")
            thr_str = self._settings.get("Balance", f"{key}_threshold")
            if not bal_str or not thr_str:
                continue
            try:
                balance = float(bal_str)
                threshold = float(thr_str)
            except ValueError:
                continue
            if balance <= threshold:
                alerts.append(f"{label}余额 ¥{balance:.1f}，已低于阈值 ¥{threshold:.0f}")

        if alerts:
            body = "\n".join(alerts)
            self.reminder_notify.emit("余额不足", body)
            self._send_email("余额不足提醒", body)
            self._balance_notified_today = True

        self._settings.set("Balance", "last_balance_notify_date", today_str)
        self._settings.save()

    # ── Custom email reminders ────────────────────────────

    def _check_custom_reminders(self, now: datetime) -> None:
        reminders = self._dm.daily_logs.get_reminders()
        if not reminders:
            return

        stale_cutoff = now - timedelta(minutes=5)
        to_delete = self._process_custom_reminders(reminders, now, stale_cutoff)
        self._collect_expired_reminders(reminders, now, to_delete)

        if to_delete:
            for rid in to_delete:
                self._dm.daily_logs.delete_reminder(rid)
            self._dm.daily_logs.save()

    def _process_custom_reminders(self, reminders: list[dict], now: datetime,
                                  stale_cutoff: datetime) -> list[str]:
        """逐条判定：失效/已触发 → 记入待删除；到点 → 发送提醒。"""
        to_delete: list[str] = []
        for r in reminders:
            rid = r.get("id", "")
            notify_dt = self._parse_notify_time(r.get("notify_time", ""))
            if notify_dt is None:
                to_delete.append(rid)
                continue

            # Stale reminder: notify_time is more than 5 min in the past → delete without sending
            if notify_dt < stale_cutoff:
                logger.info("Deleting stale reminder %s (notify=%s, now=%s)",
                            rid, r.get("notify_time", ""), now.isoformat())
                to_delete.append(rid)
                continue

            if now >= notify_dt and rid not in self._custom_reminded:
                self._fire_custom_reminder(r, rid)
                to_delete.append(rid)
        return to_delete

    @staticmethod
    def _parse_notify_time(notify_time: str) -> datetime | None:
        """解析提醒时间；缺失或非法返回 None。"""
        if not notify_time:
            return None
        try:
            return datetime.fromisoformat(notify_time)
        except ValueError:
            return None

    def _fire_custom_reminder(self, reminder: dict, rid: str) -> None:
        """发送一条自定义提醒（邮件 + 托盘）并登记为已提醒。"""
        logger.info("Firing custom reminder %s: %s at %s",
                    rid, reminder.get("item_name", ""), reminder.get("notify_time", ""))
        item_name = reminder.get("item_name", "")
        item_date = reminder.get("item_date", "")
        item_type = reminder.get("item_type", "")
        type_names = {"course": "课程", "plan": "计划", "habit": "习惯"}
        type_name = type_names.get(item_type, item_type)
        body = f"「{item_name}」\n日期: {item_date}\n类型: {type_name}"
        self._send_email(f"日程提醒 - {item_name}", body)
        self.reminder_notify.emit("日程提醒", f"「{item_name}」")
        self._custom_reminded.add(rid)

    @staticmethod
    def _collect_expired_reminders(reminders: list[dict], now: datetime,
                                   to_delete: list[str]) -> None:
        """清理：把超过 1 天的提醒 id 追加进待删除列表。"""
        cutoff = (now - timedelta(days=1)).isoformat()
        for r in reminders:
            rid = r.get("id", "")
            if rid in to_delete:
                continue
            notify_time = r.get("notify_time", "")
            if notify_time and notify_time < cutoff:
                to_delete.append(rid)

    # ── Email sender ──────────────────────────────────────

    def _send_email(self, subject: str, body: str) -> None:
        smtp_host = self._settings.get("Email", "smtp_host", fallback="smtp.qq.com")
        smtp_port = self._settings.get_int("Email", "smtp_port", fallback=587)
        smtp_user = self._settings.get("Email", "smtp_user", fallback="")
        smtp_pass = self._settings.get("Email", "smtp_pass", fallback="")
        to_email = self._settings.get("Email", "recipient", fallback="") or smtp_user

        if not smtp_user or not smtp_pass:
            logger.info("Email not configured, skipping: %s", subject)
            return

        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = to_email
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                s.starttls()
                s.login(smtp_user, smtp_pass)
                s.send_message(msg)
            logger.info("Email sent: %s", subject)
        # 边界捕获：第三方/外部（插件代码、SMTP）异常不外逃（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to send email '%s': %s", subject, e)
