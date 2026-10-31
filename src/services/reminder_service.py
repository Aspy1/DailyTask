"""Reminder service — local notifications and email alerts.

规则：

- **紧急邮件（mandatory，永远发，不受总开关影响）**：
  考试 14/7/3 天、作业 6 小时内截止
- **受 `General/reminder_enabled` 总开关控制（默认开）**：
  - **点名提醒**：`course["reminders"]["attendance"]` 为真的课，开课前 30 分钟
    （`lead_minutes` 可覆盖）→ 邮件 + 托盘
  - **作业截止前 3 天** → 邮件 + 托盘
  - **习惯**：提前 5 分钟预告 + 到点 → 托盘
  - **余额不足**：邮件 + 托盘（每天一次）
  - **自定义提醒**（用户在日程里定的）→ 邮件 + 托盘
- 托盘通知**始终**受总开关控制（关掉就不再弹窗，但上面的紧急邮件照发）

Note: the full daily digest (courses, plans, habits, DDL 3d, exams 14/7/3d)
runs via GitHub Actions at 7:55 AM. This service only handles time-sensitive
checks that need sub-day granularity.
"""

import logging
from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from src.models.billing import (
    BILLING_CATEGORY_ID,
    apply_charge,
    charge_note,
    due_today,
)
from src.models.course import schedule_date
from src.services import email_sender
from src.services.reminder_rules import (
    DDL_REMIND_DAYS,
    attendance_body,
    attendance_due,
    balance_alerts,
    ddl_email_body,
    ddl_email_due,
    ddl_notify_cooldown_due,
    ddl_reminder_body,
    ddl_reminder_due,
    expired_custom_reminder_ids,
    meal_slot_due,
    parse_hhmm,
    pending_custom_reminders,
    restock_body,
    water_quiet_window,
    water_reminder_due,
)

logger = logging.getLogger(__name__)

EARLY_NOTIFY_MINUTES = 5
CATCHUP_THRESHOLD_MINUTES = 2
# 补跑上限：应用关了一周再打开时，**不能**逐分钟扫一周（1440×N 次循环会卡死启动）。
# 12 小时前的提醒已经没意义，直接跳过并记日志。
CATCHUP_MAX_MINUTES = 720
LOOKAHEAD_MINUTES = 60
# `last_reminder_check` 只是"跨重启补跑"的锚点，不必每分钟写一次 settings.ini
SETTINGS_SAVE_INTERVAL_MINUTES = 5
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


def _persist_last_check(svc, force: bool = False) -> None:
    """把补跑锚点写回 settings.ini（默认 5 分钟一次，避免每分钟写盘）。

    放模块级：`ReminderService` 类正好卡在 400 行上限（Q-A1）。
    """
    now = datetime.now()
    if not force and (now - svc._last_persist) < timedelta(
            minutes=SETTINGS_SAVE_INTERVAL_MINUTES):
        return
    svc._settings.set("Email", "last_reminder_check", now.isoformat())
    svc._settings.save()
    svc._last_persist = now


def _check_habits(svc, now_str: str, early_str: str, now_minutes: int) -> None:
    """习惯托盘提醒：提前 5 分钟预告 + 到点合并批次通知。"""
    for habit in svc._dm.habits.habits:
        rt = habit.get("reminder_time", "").strip()
        if not rt or not svc._dm.habits.is_active_today(habit["id"]):
            continue
        if rt == early_str:
            svc._notify("即将开始",
                        f"「{habit['name']}」将在 {EARLY_NOTIFY_MINUTES} 分钟后开始")
        if rt == now_str and habit["id"] not in svc._notified_today:
            batch = _collect_habit_batch(svc, habit, now_minutes)
            for item in batch:
                svc._notified_today.add(item["id"])
            _send_habit_tray_batch(svc, batch)


def _collect_habit_batch(svc, first: dict, now_minutes: int) -> list[dict]:
    """收集 now 之后 LOOKAHEAD_MINUTES 内待提醒的习惯（含 first）。"""
    batch = [first]
    for habit in svc._dm.habits.habits:
        if habit["id"] == first["id"]:
            continue
        rt = habit.get("reminder_time", "").strip()
        if not rt or habit["id"] in svc._notified_today:
            continue
        if not svc._dm.habits.is_active_today(habit["id"]):
            continue
        minutes = parse_hhmm(rt)
        if minutes is not None and 0 <= minutes - now_minutes <= LOOKAHEAD_MINUTES:
            batch.append(habit)
    return batch


def _send_habit_tray_batch(svc, habits: list[dict]) -> None:
    for habit in habits:
        svc._notify("习惯提醒", f"该做「{habit.get('name', '')}」了")


def _ddl_reminder_notify(svc) -> None:
    """作业截止前 3 天的提醒（放模块级：`ReminderService` 正好卡在类的尺寸上限）。

    用户 2026-10-30：原实现**忘了把已提醒的任务写进集合** ✗ → 每分钟一条通知 + 一封邮件 ✗✗。
    现在：同一任务**30 分钟**才再通知一次；**邮件每天一封** ✓。
    """
    now = datetime.now()
    matched = ddl_reminder_due(svc._dm.tasks.pending, schedule_date(), set())
    fresh = ddl_notify_cooldown_due(matched, svc._ddl_last_notified, now)
    if not fresh:
        return
    for _task, _days, key in fresh:
        svc._ddl_last_notified[key] = now
    today = schedule_date().isoformat()
    email_due = any(f"{key}@{today}" not in svc._ddl_mailed for _t, _d, key in fresh)
    for _task, _days, key in fresh:
        svc._ddl_mailed.add(f"{key}@{today}")
    svc._notify("作业截止提醒", ddl_reminder_body([(t, d) for t, d, _k in fresh]),
                email=email_due, subject=f"作业截止提醒（{DDL_REMIND_DAYS} 天内）")


def _meal_reminder_notify(svc, now: datetime) -> None:
    """午饭 / 晚饭到点各提醒**一次**（用户 2026-10-30 A2：11:40 / 16:40）。

    规则在 `reminder_rules.meal_slot_due()`（纯函数）；这里只发、并记"今天这顿已提醒"。
    """
    for key, label in meal_slot_due(now, svc._meal_sent):
        svc._meal_sent.add(key)
        svc._notify(label, f"{label}时间到了 🍚 去吃点东西吧")


def _billing_charges_notify(svc) -> None:
    """月付 / 分期到期：**自动记一笔支出** + 发一封提醒邮件（用户 2026-10-31 A1）。

    ★ 只认「每月几号」；那天没开机 → 之后打开会**补扣一次**（同月只一次）。
    ★ 期数扣完 → `billing_active=False`（停用并保留，还能回查）。
    ★ 记错可改：支出就是普通的一条记录，用户在记账面板里删/改都行。
    """
    today = schedule_date()
    due = [it for it in svc._dm.inventory.items if due_today(it, today)]
    if not due:
        return
    lines = []
    for item in due:
        info = apply_charge(item, today)
        note = charge_note(info["title"], info["nth"], info["total"])
        if info["amount"] > 0:
            svc._dm.expenses.add({"amount": info["amount"], "date": today.isoformat(),
                                  "category": BILLING_CATEGORY_ID, "note": note})
        lines.append(f"{note} ¥{info['amount']:.2f}")
    svc._dm.inventory.save()
    svc._dm.expenses.save()
    svc._dm.data_changed.emit("expense")
    svc._dm.data_changed.emit("inventory")
    svc._notify("账单扣款", "今天自动记了这些支出：\n" + "\n".join(lines),
                email=True, subject="账单扣款提醒")


class ReminderService(QObject):
    reminder_notify = Signal(str, str)   # tray notification
    ddl_alert = Signal(int)             # urgent DDL count for red dot + flash

    def __init__(self, settings, data_manager, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._dm = data_manager
        self._emailer = email_sender.get_sender()
        self._last_persist = datetime.now()

        raw = self._settings.get("Email", "last_reminder_check", fallback="")
        try:
            self._last_check = datetime.fromisoformat(raw) if raw else datetime.now()
        except (TypeError, ValueError):
            # 配置里是坏时间戳 → 当作"刚启动"，不要拿它去补跑几万分钟
            self._last_check = datetime.now()

        self._notified_today: set[str] = set()
        self._notified_date = ""
        self._ddl_emailed: set[str] = set()       # DDL IDs already emailed (6h window)
        self._ddl_reminded: set[str] = set()      # 3 天提醒已发：task@due（保留给旧调用）
        self._ddl_last_notified: dict[str, datetime] = {}   # 3 天提醒的**通知冷却**（task@due → 上次）
        self._ddl_mailed: set[str] = set()                  # 3 天提醒的**邮件**去重（task@due@今天）
        self._attendance_sent: set[str] = set()   # 点名提醒已发：course@date@start
        self._exam_emailed: dict[str, set[int]] = {}  # exam_id -> {days thresholds already sent}
        self._balance_notified_today = False
        self._custom_reminded: set[str] = set()   # custom reminder IDs already sent
        self._water_last: datetime | None = None  # 上次喝水/起身提醒（C 类第 8 项）
        self._meal_sent: set[str] = set()         # 吃饭提醒已发：slot@日期（用户 2026-10-30）

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
        if delta > timedelta(minutes=CATCHUP_MAX_MINUTES):
            # 关了很久：逐分钟扫描会卡死启动，而且 12 小时前的提醒已经没有意义
            logger.info("Catch-up skipped: gap %s > %d minutes",
                        delta, CATCHUP_MAX_MINUTES)
            self._last_check = now
            _persist_last_check(self, force=True)
            return

        logger.info("Catch-up: scanning from %s to %s (gap: %s)",
                     self._last_check.time(), now.time(), delta)

        self._reset_notified_if_new_day(now)

        matched = self._collect_catchup_habits(now)
        if matched:
            for h in matched:
                self._notified_today.add(h["id"])
            _send_habit_tray_batch(self, matched)

        self._last_check = now
        _persist_last_check(self, force=True)

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
        _check_habits(self, now_str, early_str, now_minutes)
        self._check_water(now)     # 喝水 / 起身（C 类第 8 项）：复用这个 tick，不另开定时器
        _meal_reminder_notify(self, now)     # 午饭 / 晚饭（11:40 / 16:40，A2）
        _billing_charges_notify(self)        # 月付 / 分期到期 → 自动记支出 + 邮件（A1）

        self._check_attendance(now)

        self._check_ddl_email(now)

        self._check_ddl_reminder()

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

        self._check_restock()          # 补货（每天最多一次，函数自身幂等）

        self._last_check = now
        _persist_last_check(self)

    def _check_water(self, now: datetime) -> None:
        """喝水 / 起身提醒（C 类第 8 项）：复用每分钟的 tick 只做判定，**不另开定时器** ✓。"""
        if not self._settings.get_bool("General", "water_reminder", True):
            return
        if not water_reminder_due(now, self._water_last, water_quiet_window(self._settings)):
            return
        self._water_last = now
        self._notify("喝水 & 起身", "该喝口水、起来动一动了 💧")

    def _reset_notified_if_new_day(self, now: datetime) -> None:
        today_str = now.strftime("%Y-%m-%d")
        if today_str != self._notified_date:
            self._notified_today.clear()
            self._meal_sent.clear()      # 新的日期前缀本来就不会命中，这里顺手防无限增长
            # 这些集合的键都带日期，常驻应用跨天后会无限增长；每天清一次
            self._attendance_sent.clear()
            self._ddl_emailed.clear()
            self._ddl_mailed.clear()
            self._custom_reminded.clear()
            cutoff = now - timedelta(days=1)
            self._ddl_last_notified = {
                key: when for key, when in self._ddl_last_notified.items()
                if when >= cutoff
            }
            self._notified_date = today_str

    # ── DDL email (6 hours) ──────────────────────────────

    def _check_ddl_email(self, now: datetime) -> None:
        """6 小时内截止 → 邮件（托盘留给 3 天与点名，避免同一件事响两次）。"""
        matched = ddl_email_due(self._dm.tasks.pending, now, self._ddl_emailed)
        if not matched:
            return
        for t in matched:
            self._ddl_emailed.add(t.get("id", ""))
        # 紧急邮件：mandatory → 关掉提醒开关也照发（用户明确要求）
        self._notify("DDL 紧急提醒", ddl_email_body(matched),
                     email=True, tray=False, mandatory=True)

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
        self._notify(
            "考试提醒", f"「{name}」还有 {days_left} 天",
            email=True, subject=f"考试提醒 - {name}",
            email_body=f"「{name}」还有 {days_left} 天考试\n日期: {item['date']}",
            mandatory=True,          # 紧急邮件：不受总开关影响
        )

    # ── Attendance (会点名的课) ────────────────────────────

    def _check_attendance(self, now: datetime) -> None:
        """会点名的课：开课前 30 分钟提醒（邮件 + 托盘）。规则见 `reminder_rules`。"""
        for course, start_str in attendance_due(self._dm.courses.get_today_courses(),
                                                now, self._attendance_sent):
            self._attendance_sent.add(
                f"{course.get('id', '')}@{now.date().isoformat()}@{start_str}")
            name = course.get("name", "")
            self._notify("点名提醒", attendance_body(course, start_str),
                         email=True, subject=f"点名提醒 - {name}")

    # ── DDL 3-day reminder ────────────────────────────────

    def _check_ddl_reminder(self) -> None:
        """作业截止前 3 天：通知 30 分钟一次、邮件每天一次（用户 2026-10-30 口径）。"""
        _ddl_reminder_notify(self)

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
        """余额低于阈值 → 邮件 + 托盘（每天一次）。规则见 `reminder_rules`。

        ⚠ 没告警时**不写设置**：旧实现无条件写日期并 `save()`，等于每分钟重写一次
        settings.ini（既费 IO，又放大了 ERRORS #044 的整份回滚问题）。
        """
        alerts = balance_alerts(self._settings)
        if not alerts:
            return
        self._notify("余额不足", "\n".join(alerts), email=True, subject="余额不足提醒")
        self._balance_notified_today = True
        self._settings.set("Balance", "last_balance_notify_date",
                           datetime.now().strftime("%Y-%m-%d"))
        self._settings.save()

    def _check_restock(self) -> None:
        """有"需购/不足"的物品 → 邮件 + 托盘（每天最多一次）。

        ⚠ **没缺货就不记日期**（F3）：原来无条件写，导致"先检查没缺货、稍后归零"被跳过。
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        if self._settings.get("Inventory", "last_restock_notify_date", fallback="") == today_str:
            return
        if not (items := self._dm.inventory.need_restock):
            return                                       # 没缺货 → 不消耗今天的提醒机会（F3）
        self._notify("该补货了", restock_body(items), email=True, subject="补货提醒")
        self._settings.set("Inventory", "last_restock_notify_date", today_str)
        self._settings.save()

    # ── Custom email reminders ────────────────────────────

    def _check_custom_reminders(self, now: datetime) -> None:
        """用户在日程里定的提醒：到点发（邮件 + 托盘），随后清理。规则见 `reminder_rules`。"""
        reminders = self._dm.daily_logs.get_reminders()
        if not reminders:
            return

        to_fire, to_delete = pending_custom_reminders(
            reminders, now, now - timedelta(minutes=5))
        for r in to_fire:
            rid = r.get("id", "")
            self._fire_custom_reminder(r, rid)
            to_delete.append(rid)
        expired_custom_reminder_ids(reminders, now, to_delete)

        if to_delete:
            for rid in to_delete:
                self._dm.daily_logs.delete_reminder(rid)
            self._dm.daily_logs.save()

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
        self._notify("日程提醒", f"「{item_name}」", email=True,
                     subject=f"日程提醒 - {item_name}", email_body=body)
        self._custom_reminded.add(rid)

    # ── Notifier（所有提醒的唯一出口）────────────────────

    def _notify(self, title: str, body: str, *, email: bool = False,
                subject: str | None = None, email_body: str | None = None,
                tray: bool = True, mandatory: bool = False) -> None:
        """发一条提醒。

        - `mandatory=True`（**考试 14/7/3 天、DDL 6 小时**这两类紧急邮件）：
          邮件**永远发**，不受总开关影响 —— 漏掉的代价远大于被打扰（用户明确要求）；
        - 其余提醒受 `General/reminder_enabled` 总开关控制（默认开）；
        - 托盘通知**始终**受开关控制：关掉提醒就不该再弹窗，但关键邮件照发。
        """
        enabled = self._settings.get_bool("General", "reminder_enabled", True)
        if not enabled and not mandatory:
            logger.debug("提醒总开关关闭，跳过: %s", title)
            return
        if tray and enabled:
            self.reminder_notify.emit(title, body)
        if email:
            self._send_email(subject or title, email_body or body)

    def _send_email(self, subject: str, body: str) -> None:
        """把邮件**入队**，不在主线程发 SMTP（Q-C2 / R-004）。

        测试把 `_send_email` 替换成 lambda 来断言"发了什么"，所以保留这个方法作为边界；
        真正的发送在 `services/email_sender.py` 的后台线程里。
        """
        config = email_sender.EmailConfig(
            host=self._settings.get("Email", "smtp_host", fallback="smtp.qq.com"),
            port=self._settings.get_int("Email", "smtp_port", fallback=587),
            user=self._settings.get("Email", "smtp_user", fallback=""),
            password=self._settings.get("Email", "smtp_pass", fallback=""),
            recipient=self._settings.get("Email", "recipient", fallback=""),
        )
        self._emailer.send(config, subject, body)

    def shutdown(self) -> None:
        """应用退出前尽量把队列里的邮件发完（最多等 2 秒）。"""
        self._timer.stop()
        self._emailer.shutdown()
