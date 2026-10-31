"""提醒服务的并发/性能边界。

两个真实风险：
1. 应用关了几天再打开 → `_catch_up()` 逐分钟扫几万次（启动卡死）；
2. 邮件在主线程同步 `smtplib`（UI 冻结最长 10s）。
"""

import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import ClassVar

from src.services import email_sender
from src.services.email_sender import EmailConfig, EmailSender
from src.services.reminder_service import CATCHUP_MAX_MINUTES, ReminderService
from src.services.settings_manager import SettingsManager


class _FakeHabits:
    habits: ClassVar[list] = []

    @staticmethod
    def is_active_today(_hid: str) -> bool:
        return True


class _FakeDM:
    habits = _FakeHabits()

    def __init__(self, data_dir) -> None:
        self.data_dir = data_dir
        self.tasks = SimpleNamespace(pending=[])
        self.expenses = SimpleNamespace(add=lambda *a, **k: None, save=lambda: None)
        self.inventory = SimpleNamespace(items=[], need_restock=[], save=lambda: None)
        self.daily_logs = SimpleNamespace(get_reminders=lambda: [], save=lambda: None)
        self.courses = SimpleNamespace(get_today_courses=lambda: [])
        self.exams = SimpleNamespace(exams=[])
        self.data_changed = SimpleNamespace(emit=lambda *_a: None)


def _service(tmp_path, days_ago: float = 2) -> ReminderService:
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.set("Email", "last_reminder_check",
                 (datetime.now() - timedelta(days=days_ago)).isoformat())
    settings.save()
    svc = ReminderService(settings, _FakeDM(tmp_path))
    svc._timer.stop()
    return svc


def test_catch_up_skips_huge_gap_without_minute_scan(tmp_path) -> None:
    """⭐ 关了两天再打开：不能逐分钟扫（2×1440 次 × 习惯数）。"""
    svc = _service(tmp_path, days_ago=2)
    started = time.monotonic()
    svc._catch_up()
    assert time.monotonic() - started < 1.0

    saved = datetime.fromisoformat(svc._settings.get("Email", "last_reminder_check"))
    assert abs((datetime.now() - saved).total_seconds()) < 60


def test_catch_up_window_is_capped() -> None:
    assert CATCHUP_MAX_MINUTES <= 24 * 60


def test_send_email_enqueues_instead_of_blocking(tmp_path) -> None:
    svc = _service(tmp_path)
    seen: list[tuple] = []

    class _Recorder:
        def send(self, config, subject, body) -> None:
            seen.append((config, subject, body))

        def shutdown(self, timeout: float = 2.0) -> None:
            return

    svc._emailer = _Recorder()
    svc._settings.set("Email", "smtp_user", "u@example.com")
    svc._settings.set("Email", "smtp_pass", "p")

    started = time.monotonic()
    svc._send_email("主题", "正文")
    assert time.monotonic() - started < 0.5, "入队必须立即返回（不能同步 SMTP）"
    assert seen and seen[0][1] == "主题"


def test_email_sender_worker_sends_and_survives_errors(monkeypatch) -> None:
    calls: list[str] = []

    def fake_send(config, subject, body) -> None:
        calls.append(subject)
        if subject == "bad":
            raise RuntimeError("smtp down")

    monkeypatch.setattr(email_sender, "send_email_sync", fake_send)
    sender = EmailSender()
    config = EmailConfig(user="u", password="p")  # noqa: S106 - 测试用假凭据
    sender.send(config, "ok", "body")
    sender.send(config, "bad", "body")
    sender.send(config, "ok2", "body")
    deadline = time.monotonic() + 2
    while len(calls) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    sender.shutdown()
    assert calls == ["ok", "bad", "ok2"]
