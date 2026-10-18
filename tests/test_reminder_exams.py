"""考试提醒回归测试（ReminderService）。

两个真实缺陷：

1. **考试模块的数据进不了提醒**：`_check_exam_email` 只遍历 `tasks.pending`
   （靠标题含「考试」猜），而 AI 建的考试写在 `exams.json` → 考试提醒从未触发。
2. **同一天重复轰炸**：14/7/3 三个阈值用 `days_left <= d` 各自判定，
   剩 3 天时三个阈值同时命中 → 同一场考试一次发 3 封邮件。
"""

from datetime import date, timedelta

import pytest

from src.models.course import schedule_date


@pytest.fixture
def env(tmp_path, qapp) -> tuple:
    """沙箱 DataManager + 记录型 ReminderService（不连 SMTP、不连托盘）。"""
    from src.services.data_manager import DataManager
    from src.services.reminder_service import ReminderService
    from src.services.settings_manager import SettingsManager

    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    dm = DataManager(tmp_path)
    rem = ReminderService(settings, dm)
    mails: list[tuple[str, str]] = []
    trays: list[tuple[str, str]] = []
    rem._send_email = lambda subject, body: mails.append((subject, body))
    rem.reminder_notify.connect(lambda title, body: trays.append((title, body)))
    return dm, rem, mails, trays


def _add_exam(dm, name: str, days: int) -> None:
    """⚠ 用 `schedule_date()`（**凌晨 1 点前算前一天**）—— 与生产代码同源。

    用 `date.today()` 会在刚过午夜时差一天 → "14 天提醒"算成 15 天 ✗
    （2026-10-19 00:30 实测：本地 5 个测试红，而 CI 跑 UTC 是绿的 ✗）。
    """
    dm.exams.add_exam({
        "course_name": name,
        "exam_date": (schedule_date() + timedelta(days=days)).isoformat(),
    })
    dm.exams.save()


def _run(rem) -> None:
    rem._check_exam_email()


# ── 数据来源 ────────────────────────────────────────────────

@pytest.mark.parametrize("days", [14, 7, 3, 1, 0])
def test_exam_from_exams_json_triggers(env, days) -> None:
    dm, rem, mails, trays = env
    _add_exam(dm, "高等数学", days)
    _run(rem)
    assert len(mails) == 1, mails
    assert "高等数学" in mails[0][0]
    assert trays and "高等数学" in trays[0][1]


def test_far_exam_does_not_trigger(env) -> None:
    dm, rem, mails, _ = env
    _add_exam(dm, "下学期期末", 30)
    _run(rem)
    assert mails == []


def test_past_exam_does_not_trigger(env) -> None:
    dm, rem, mails, _ = env
    _add_exam(dm, "昨天的考试", -1)
    _run(rem)
    assert mails == []


def test_legacy_task_based_exam_still_works(env) -> None:
    """旧数据把考试建成 task（标题含「考试」）时仍要提醒。"""
    dm, rem, mails, _ = env
    dm.tasks.add({"title": "期末考试", "tags": ["考试"],
                  "due_date": (date.today() + timedelta(days=5)).isoformat()})
    _run(rem)
    assert len(mails) == 1 and "期末考试" in mails[0][0]


def test_same_exam_in_both_sources_notified_once(env) -> None:
    """authored twice（exams.json + 同名 task）只提醒一次。"""
    dm, rem, mails, _ = env
    day = (date.today() + timedelta(days=4)).isoformat()
    dm.tasks.add({"title": "大学物理", "tags": ["考试"], "due_date": day})
    dm.exams.add_exam({"course_name": "大学物理", "exam_date": day})
    _run(rem)
    assert len(mails) == 1, mails


# ── 不重复轰炸 ──────────────────────────────────────────────

def test_one_exam_three_days_left_sends_single_mail(env) -> None:
    """回归：剩 3 天时以前会发 3 封（14/7/3 各一封）。"""
    dm, rem, mails, trays = env
    _add_exam(dm, "线性代数", 3)
    _run(rem)
    assert len(mails) == 1
    assert len(trays) == 1


def test_repeated_checks_do_not_resend(env) -> None:
    dm, rem, mails, _ = env
    _add_exam(dm, "概率论", 6)
    _run(rem)
    _run(rem)
    _run(rem)
    assert len(mails) == 1, mails


def test_thresholds_advance_over_days(env) -> None:
    """14 天提醒过之后，到 7 天、3 天时应各再提醒一次（每天最多一封）。"""
    dm, rem, mails, _ = env
    _add_exam(dm, "数据结构", 14)
    _run(rem)                     # 14 天
    assert len(mails) == 1
    item = rem._collect_exam_items()[0]
    for days, expect_total in ((7, 2), (3, 3)):
        item["date"] = (date.today() + timedelta(days=days)).isoformat()
        rem._check_exam_item(item, date.today())
        assert len(mails) == expect_total, (days, mails)
