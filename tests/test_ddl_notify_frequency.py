"""作业截止提醒的**频率**：通知 30 分钟一次、邮件每天一次（用户 2026-10-30 口径）。

回归：原实现**从不把提醒过的任务写进 `_ddl_reminded`** ✗ → 每分钟一条通知 + 一封邮件 ✗✗。
"""

from datetime import date, datetime, timedelta

from src.services import reminder_rules
from src.services import reminder_service as rs


class _Fake:
    """鸭子类型的 service：只给 `_check_ddl_reminder` 需要的属性。"""

    def __init__(self, due: str) -> None:
        self._dm = type("DM", (), {"tasks": type("T", (), {
            "pending": [{"id": "t_001", "title": "写作业", "due_date": due}]})()})()
        self._ddl_last_notified: dict[str, datetime] = {}
        self._ddl_mailed: set[str] = set()
        self.sent: list[tuple[bool, str]] = []

    def _notify(self, title: str, body: str, *, email: bool = False,
                subject: str | None = None, **_kw: object) -> None:
        self.sent.append((email, title))


def _due_in_two_days() -> str:
    return (date.today() + timedelta(days=2)).isoformat()


def test_first_call_notifies_with_email(qapp) -> None:
    fake = _Fake(_due_in_two_days())
    rs.ReminderService._check_ddl_reminder(fake)
    assert len(fake.sent) == 1 and fake.sent[0][0] is True, fake.sent


def test_second_call_within_cooldown_is_silent(qapp, monkeypatch) -> None:
    fake = _Fake(_due_in_two_days())
    rs.ReminderService._check_ddl_reminder(fake)
    rs.ReminderService._check_ddl_reminder(fake)        # 立刻再来一次
    assert len(fake.sent) == 1, f"冷却期内不该再提醒：{fake.sent}"


def test_after_cooldown_notifies_again_but_without_email(qapp) -> None:
    fake = _Fake(_due_in_two_days())
    rs.ReminderService._check_ddl_reminder(fake)
    key = next(iter(fake._ddl_last_notified))
    # 把"上次通知"往前推 31 分钟 → 冷却已过
    fake._ddl_last_notified[key] -= timedelta(
        minutes=reminder_rules.DDL_NOTIFY_COOLDOWN_MINUTES + 1)
    rs.ReminderService._check_ddl_reminder(fake)
    assert len(fake.sent) == 2, fake.sent
    assert fake.sent[1][0] is False, "同一天第二封邮件不该再发 ✗"
