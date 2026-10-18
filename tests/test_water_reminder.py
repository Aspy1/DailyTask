"""喝水 / 起身提醒（C 类第 8 项，`PLAN.md` P20）。

P20 的两条现成情况决定了做法：
1. 托盘 `showMessage` 在 Win10+ **本来就是原生 toast** ✓ → 不用另接 API，**主要是换节拍**
2. 现有提醒是**每天一次**的日检（`ReminderService` 的 60 秒 tick）→ 半小时一次**不需要**
   另开定时器：**复用那个 tick 做判定** ✓（两个节拍会互相错位 ✗）

还要考虑的三件事（P20 点名）：**免打扰时段** / 只在开机时段跑（= 服务在跑就说明开机 ✓）/
**总提醒开关**（`_notify` 统一把关 ✓）。
"""

import datetime

from src.services.reminder_rules import (
    DEFAULT_QUIET,
    WATER_INTERVAL_MIN,
    water_quiet_window,
    water_reminder_due,
)

T = datetime.datetime(2026, 10, 18, 10, 0)          # 上午 10:00（不在免打扰时段）


def test_first_time_always_due() -> None:
    assert water_reminder_due(T, None) is True


def test_not_due_until_the_interval_passes() -> None:
    assert water_reminder_due(T, T - datetime.timedelta(minutes=WATER_INTERVAL_MIN - 1)) is False
    assert water_reminder_due(T, T - datetime.timedelta(minutes=WATER_INTERVAL_MIN)) is True
    assert water_reminder_due(T, T - datetime.timedelta(hours=2)) is True


def test_quiet_hours_suppress_it() -> None:
    """免打扰时段（默认 23:00–07:00，**跨零点**）不发 ✓。"""
    for hour in (23, 0, 3, 6):
        night = T.replace(hour=hour, minute=30)
        assert water_reminder_due(night, None) is False, hour
    assert water_reminder_due(T.replace(hour=7, minute=1), None) is True, "过了 07:00 就该发"


def test_quiet_window_can_be_overridden() -> None:
    """用户把免打扰设成 12:00–13:00 → 中午不发、晚上发。"""
    assert water_reminder_due(T.replace(hour=12, minute=30), None, (12 * 60, 13 * 60)) is False
    assert water_reminder_due(T.replace(hour=22, minute=0), None, (12 * 60, 13 * 60)) is True


def test_quiet_window_reads_settings() -> None:
    class _S:
        def get(self, _sec, key, fallback="") -> str:
            return {"quiet_start": "08:00", "quiet_end": "09:00"}.get(key, fallback)

    assert water_quiet_window(_S()) == (8 * 60, 9 * 60)

    class _Empty:
        def get(self, _sec, _key, fallback="") -> str:
            return fallback

    assert water_quiet_window(_Empty()) == DEFAULT_QUIET, "没配就用默认"


def test_quiet_window_survives_garbage() -> None:
    class _Bad:
        def get(self, _sec, _key, fallback="") -> str:
            return "不是时间"

    assert water_quiet_window(_Bad()) == DEFAULT_QUIET, "解析不了退回默认，不崩"
