"""吃饭提醒（A2，用户 2026-10-30）：每天 11:40 / 16:40 一次，首页提示低频闪烁。

两个端点分开测：
- **托盘通知**：`reminder_rules.meal_slot_due()` + `ReminderService` 的发送（鸭子类型假 service）
- **首页提示**：`hints.meal_hints()` 产出一条 `blink=True` 的提示，`HintBar` 据此开闪烁定时器
"""

from datetime import datetime, timedelta

from src.services import reminder_service as rs
from src.services.hints import Hint, meal_hints, today_hints
from src.services.reminder_rules import MEAL_WINDOW_MINUTES, meal_slot_due
from src.ui.widgets.hint_bar import HintBar


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 30, hour, minute)


# ── 规则 ────────────────────────────────────────────────────

def test_not_due_before_the_slot() -> None:
    assert meal_slot_due(_at(9, 0), set()) == []
    assert meal_slot_due(_at(11, 39), set()) == []


def test_due_exactly_at_1140() -> None:
    due = meal_slot_due(_at(11, 40), set())
    assert [label for _key, label in due] == ["午饭"]


def test_still_due_inside_the_window() -> None:
    """应用 12:20 才开也要提醒（整点后 90 分钟内）。"""
    assert meal_slot_due(_at(12, 20), set())


def test_no_make_up_after_the_window() -> None:
    late = _at(11, 40) + timedelta(minutes=MEAL_WINDOW_MINUTES + 1)
    assert meal_slot_due(late, set()) == []


def test_dinner_slot() -> None:
    assert [label for _k, label in meal_slot_due(_at(16, 40), set())] == ["晚饭"]


def test_second_call_same_day_is_silent() -> None:
    """每天一次：发了就记下，同一顿不再提醒。"""
    sent: set[str] = set()
    first = meal_slot_due(_at(11, 40), sent)
    sent.update(key for key, _label in first)
    assert meal_slot_due(_at(11, 41), sent) == []


# ── 服务层：真的发一条 ──────────────────────────────────────

class _Fake:
    """只给 `_meal_reminder_notify` 需要的属性。"""

    def __init__(self) -> None:
        self._meal_sent: set[str] = set()
        self.sent: list[tuple[str, str]] = []

    def _notify(self, title: str, body: str, **_kw: object) -> None:
        self.sent.append((title, body))


def test_service_notifies_once_per_meal(qapp) -> None:
    fake = _Fake()
    rs._meal_reminder_notify(fake, _at(11, 40))
    rs._meal_reminder_notify(fake, _at(11, 45))
    assert len(fake.sent) == 1
    assert fake.sent[0][0] == "午饭"


def test_service_sends_both_meals_in_one_day(qapp) -> None:
    fake = _Fake()
    rs._meal_reminder_notify(fake, _at(11, 40))
    rs._meal_reminder_notify(fake, _at(16, 40))
    assert [title for title, _body in fake.sent] == ["午饭", "晚饭"]


# ── 首页提示 ────────────────────────────────────────────────

def test_meal_hint_blinks_inside_window() -> None:
    hints = meal_hints(_at(11, 40))
    assert len(hints) == 1
    assert hints[0].blink is True
    assert "午饭" in hints[0].text


def test_no_meal_hint_outside_window() -> None:
    assert meal_hints(_at(15, 0)) == []


def test_today_hints_includes_meal_hint(tmp_path) -> None:
    hints = today_hints(tmp_path, now=_at(16, 40))
    assert any(h.blink for h in hints), "晚饭时间应有一条会闪的提示"


def test_hint_bar_starts_and_stops_blinking(qapp) -> None:
    bar = HintBar()
    bar.show_hints([Hint("meal.lunch@2026-10-30", "午饭时间到了 🍚", "info", blink=True)])
    assert bar._blink_timer.isActive(), "有会闪的提示 → 定时器该开"
    bar._dismiss("meal.lunch@2026-10-30")
    assert not bar._blink_timer.isActive(), "点掉后没有会闪的了 → 定时器该停"
