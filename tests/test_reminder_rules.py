"""点名提醒 + 作业 3 天提醒（2026-10-16 新增）。

规则本身是纯函数（`services/reminder_rules.py`）→ 主要直接测纯函数；
另加服务级用例，保证「总开关关掉就真的不发」「同一件事只发一次」。
"""

from datetime import date, datetime

from src.services import reminder_rules as rules

# ── 点名提醒（会点名的课，开课前 30 分钟）────────────────────

def _course(**kw: object) -> dict:
    base = {"id": "c_001", "name": "算法设计与分析",
            "time_slots": [{"start": 1, "end": 2, "location": "二教 301"}]}
    base.update(kw)
    return base


def test_course_start_time_uses_earliest_slot() -> None:
    assert rules.course_start_time(
        _course(time_slots=[{"start": 3, "end": 4}, {"start": 1, "end": 2}])) == "08:30"
    assert rules.course_start_time({"time_slots": []}) is None
    assert rules.course_start_time({"time_slots": [{"start": 99}]}) is None


def test_attendance_fires_only_inside_window() -> None:
    course = _course(reminders={"attendance": True, "lead_minutes": 30})
    # 08:00 = 开课前 30 分钟 → 命中
    assert rules.attendance_due([course], datetime(2026, 10, 16, 8, 0), set()) \
        == [(course, "08:30")]
    # 07:29 太早 → 不命中
    assert rules.attendance_due([course], datetime(2026, 10, 16, 7, 29), set()) == []
    # 08:31 已经上课 → 不命中（迟到的点名提醒没有意义）
    assert rules.attendance_due([course], datetime(2026, 10, 16, 8, 31), set()) == []


def test_attendance_requires_flag_and_skips_already_sent() -> None:
    assert rules.attendance_due([_course()], datetime(2026, 10, 16, 8, 0), set()) == []
    course = _course(reminders={"attendance": True})
    key = "c_001@2026-10-16@08:30"
    assert rules.attendance_due([course], datetime(2026, 10, 16, 8, 0), {key}) == []


def test_attendance_lead_minutes_override() -> None:
    course = _course(reminders={"attendance": True, "lead_minutes": 60})
    assert rules.attendance_due([course], datetime(2026, 10, 16, 7, 45), set()) != []


def test_attendance_body_carries_location() -> None:
    body = rules.attendance_body(_course(), "08:30")
    assert "算法设计与分析" in body and "08:30" in body and "二教 301" in body


# ── 作业截止前 3 天 ─────────────────────────────────────────

def _task(due: str, **kw: object) -> dict:
    base = {"id": "t_001", "title": "背包问题", "course_name": "算法",
            "due_date": due, "status": "pending"}
    base.update(kw)
    return base


def test_ddl_reminder_fires_within_three_days_once() -> None:
    today = date(2026, 10, 16)
    t = _task("2026-10-19T23:00")
    assert rules.ddl_reminder_due([t], today, set()) == [(t, 3)]
    # 已发过 → 不再命中（同一条作业只发一次）
    assert rules.ddl_reminder_due([t], today, {"t_001@2026-10-19"}) == []


def test_ddl_reminder_not_fired_four_days_out() -> None:
    assert rules.ddl_reminder_due([_task("2026-10-20")], date(2026, 10, 16), set()) == []


def test_ddl_reminder_body_mentions_days_left() -> None:
    body = rules.ddl_reminder_body([(_task("2026-10-19T23:00"), 3)])
    assert "3 天后" in body and "背包问题" in body


# ── 服务级：总开关 / 只发一次 ───────────────────────────────

def _service(tmp_path) -> tuple:
    from src.services.data_manager import DataManager
    from src.services.reminder_service import ReminderService
    from src.services.settings_manager import SettingsManager

    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    dm = DataManager(tmp_path)
    svc = ReminderService(settings, dm)
    svc._timer.stop()          # 测试里不留运行中的定时器（见 conftest 的清理说明）
    return settings, dm, svc


def test_notify_respects_global_switch(qapp, tmp_path) -> None:
    """`General/reminder_enabled=false` → 托盘与邮件都不发（默认开）。"""
    settings, _dm, svc = _service(tmp_path)
    sent: list = []
    svc.reminder_notify.connect(lambda *a: sent.append(a))

    settings.set("General", "reminder_enabled", "false")
    svc._notify("标题", "正文")
    assert sent == []

    settings.set("General", "reminder_enabled", "true")
    svc._notify("标题", "正文")
    assert sent == [("标题", "正文")]


def test_service_attendance_sends_once_per_day(qapp, tmp_path, monkeypatch) -> None:
    _settings, dm, svc = _service(tmp_path)
    course = _course(reminders={"attendance": True})
    monkeypatch.setattr(dm.courses, "get_today_courses", lambda: [course])
    sent: list = []
    mails: list = []
    svc.reminder_notify.connect(lambda *a: sent.append(a))
    monkeypatch.setattr(svc, "_send_email", lambda s, b: mails.append((s, b)))

    svc._check_attendance(datetime(2026, 10, 16, 8, 0))
    assert len(sent) == 1 and len(mails) == 1
    assert "点名" in sent[0][0]

    svc._check_attendance(datetime(2026, 10, 16, 8, 5))     # 同一天同一门课不再发
    assert len(sent) == 1 and len(mails) == 1


# ── 右键开关写入的数据结构 ─────────────────────────────────

def test_toggle_attendance_writes_schema(qapp, tmp_path) -> None:
    from src.services.data_manager import DataManager
    from src.ui.widgets.course_table import toggle_course_attendance

    dm = DataManager(tmp_path)
    dm.courses.add_course({"name": "算法", "day_of_week": 1,
                           "time_slots": [{"start": 1, "end": 2}]})
    dm.courses.save()
    cid = dm.courses.courses[0]["id"]

    assert toggle_course_attendance(dm, cid) is True
    conf = dm.courses.courses[0]["reminders"]
    assert conf["attendance"] is True and conf["lead_minutes"] == 30

    assert toggle_course_attendance(dm, cid) is False
    assert dm.courses.courses[0]["reminders"]["attendance"] is False


# ── 摘要里标注会点名的课 ───────────────────────────────────

def test_digest_marks_attendance_courses() -> None:
    from scripts.send_digest import _course_line

    assert "会点名" in _course_line({"name": "算法", "reminders": {"attendance": True}})
    assert "会点名" not in _course_line({"name": "算法"})


def test_course_panel_signal_writes_attendance(qapp, tmp_path) -> None:
    """课程表面板：右键菜单信号 → 槽 → 数据（emit → connect → slot 两端都要能追到）。"""
    from src.services.data_manager import DataManager
    from src.ui.panels.course_panel import CoursePanel

    dm = DataManager(tmp_path)
    dm.courses.add_course({"name": "算法", "day_of_week": 1,
                           "time_slots": [{"start": 1, "end": 2}]})
    dm.courses.save()
    panel = CoursePanel(dm)
    cid = dm.courses.courses[0]["id"]

    panel._table.course_attendance_toggle_requested.emit(cid)
    assert dm.courses.courses[0]["reminders"]["attendance"] is True
