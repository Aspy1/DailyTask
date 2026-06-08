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
from datetime import datetime, timedelta, date
from email.mime.text import MIMEText

from PySide6.QtCore import QObject, QTimer, Signal
from src.models.course import schedule_date

logger = logging.getLogger("reminder")

EARLY_NOTIFY_MINUTES = 5
CATCHUP_THRESHOLD_MINUTES = 2
LOOKAHEAD_MINUTES = 60
DDL_EMAIL_HOURS = 6          # send email when DDL is within 6 hours
EXAM_DAYS = [14, 7, 3]       # exam reminder thresholds (days before)


class ReminderService(QObject):
    reminder_notify = Signal(str, str)   # tray notification
    ddl_alert = Signal(int)             # urgent DDL count for red dot + flash

    def __init__(self, settings, data_manager, parent=None):
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

        matched: list[dict] = []
        seen: set[str] = set()
        cursor = self._last_check.replace(second=0, microsecond=0)
        while cursor <= now:
            cursor_str = cursor.strftime("%H:%M")
            for h in self._dm.habits.habits:
                rt = h.get("reminder_time", "").strip()
                if not self._dm.habits.is_active_today(h["id"]):
                    continue
                if rt and rt == cursor_str and h["id"] not in seen and h["id"] not in self._notified_today:
                    seen.add(h["id"])
                    matched.append(h)
            cursor += timedelta(minutes=1)

        if matched:
            for h in matched:
                self._notified_today.add(h["id"])
            self._send_habit_tray_batch(matched)

        self._last_check = now
        self._settings.set("Email", "last_reminder_check", now.isoformat())
        self._settings.save()

    # ── Regular check ─────────────────────────────────────

    def _check(self) -> None:
        now = datetime.now()
        now_str = now.strftime("%H:%M")
        early_str = (now + timedelta(minutes=EARLY_NOTIFY_MINUTES)).strftime("%H:%M")

        self._reset_notified_if_new_day(now)
        now_minutes = now.hour * 60 + now.minute

        # ── Habits: tray notification only ────────────────
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
                batch = [h]
                for h2 in self._dm.habits.habits:
                    if h2["id"] == h["id"]:
                        continue
                    rt2 = h2.get("reminder_time", "").strip()
                    if not rt2 or h2["id"] in self._notified_today:
                        continue
                    if not self._dm.habits.is_active_today(h2["id"]):
                        continue
                    try:
                        hh, mm = rt2.split(":")
                        rt2_minutes = int(hh) * 60 + int(mm)
                    except ValueError:
                        continue
                    if 0 <= rt2_minutes - now_minutes <= LOOKAHEAD_MINUTES:
                        batch.append(h2)

                for bh in batch:
                    self._notified_today.add(bh["id"])
                self._send_habit_tray_batch(batch)

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
        threshold = (now + timedelta(hours=DDL_EMAIL_HOURS))
        pending = self._dm.tasks.pending
        matched = []
        for t in pending:
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

        if matched:
            lines = ["以下任务将在 6 小时内截止：", ""]
            for t in matched:
                due = (t.get("due_date", "") or "")[:16]
                course = t.get("course_name", "") or ""
                c_str = f" [{course}]" if course else ""
                lines.append(f"  • {t.get('title', '')}{c_str}  截止: {due}")
            body = "\n".join(lines)
            self._send_email("DDL 紧急提醒", body)

    # ── Exam email ────────────────────────────────────────

    def _check_exam_email(self) -> None:
        """Send email for exams at 14/7/3 day thresholds."""
        today = schedule_date()
        pending = self._dm.tasks.pending
        for t in pending:
            tid = t.get("id", "")
            title = t.get("title", "") + " " + " ".join(t.get("tags", []))
            if "考试" not in title and "exam" not in title.lower():
                continue
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

            emailed = self._exam_emailed.setdefault(tid, set())
            for d in EXAM_DAYS:
                if days_left <= d and d not in emailed:
                    self._send_email(
                        f"考试提醒 - {t.get('title', '')}",
                        f"「{t.get('title', '')}」还有 {days_left} 天考试\n日期: {due_str}"
                    )
                    emailed.add(d)

    # ── DDL red dot ───────────────────────────────────────

    def _check_ddl(self) -> None:
        threshold_date = date.today() + timedelta(days=3)
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
                pass
        self.ddl_alert.emit(urgent_count)

    def _on_data_changed(self, action: str) -> None:
        """Refresh DDL count when tasks change."""
        if "task" in action:
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

        to_delete: list[str] = []
        stale_cutoff = now - timedelta(minutes=5)
        for r in reminders:
            rid = r.get("id", "")
            nt = r.get("notify_time", "")
            if not nt:
                to_delete.append(rid)
                continue
            try:
                notify_dt = datetime.fromisoformat(nt)
            except ValueError:
                to_delete.append(rid)
                continue

            # Stale reminder: notify_time is more than 5 min in the past → delete without sending
            if notify_dt < stale_cutoff:
                logger.info("Deleting stale reminder %s (notify=%s, now=%s)", rid, nt, now.isoformat())
                to_delete.append(rid)
                continue

            if now >= notify_dt and rid not in self._custom_reminded:
                logger.info("Firing custom reminder %s: %s at %s", rid, r.get("item_name", ""), nt)
                item_name = r.get("item_name", "")
                item_date = r.get("item_date", "")
                item_type = r.get("item_type", "")
                type_names = {"course": "课程", "plan": "计划", "habit": "习惯"}
                type_name = type_names.get(item_type, item_type)
                body = f"「{item_name}」\n日期: {item_date}\n类型: {type_name}"
                self._send_email(f"日程提醒 - {item_name}", body)
                self.reminder_notify.emit("日程提醒", f"「{item_name}」")
                self._custom_reminded.add(rid)
                to_delete.append(rid)

        # Cleanup: delete reminders older than 1 day
        cutoff = (now - timedelta(days=1)).isoformat()
        for r in reminders:
            rid = r.get("id", "")
            if rid in to_delete:
                continue
            nt = r.get("notify_time", "")
            if nt and nt < cutoff:
                to_delete.append(rid)

        if to_delete:
            for rid in to_delete:
                self._dm.daily_logs.delete_reminder(rid)
            self._dm.daily_logs.save()

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
        except Exception as e:
            logger.error("Failed to send email '%s': %s", subject, e)
