"""习惯调度判定守卫（CODE_STANDARDS Q-C3）。

`is_active_today` 决定习惯今天是否出现在待办里。此前 monthly 分支把 `logs` 的
**顶层键（日期）**当成 habit_id 比较，恒为 False，导致每月习惯永远判"未达标"
（天天出现，配额形同虚设）。这里把四种 schedule 类型全部钉住。
"""

from datetime import date, timedelta

from src.models.habit import HabitModel


def _today() -> date:
    return date.today()


def test_daily_always_active(tmp_path) -> None:
    m = HabitModel(tmp_path / "habits.json")
    hid = m.add_habit({"name": "每天", "schedule": {"type": "daily"}})
    assert m.is_active_today(hid) is True


def test_weekly_only_on_listed_weekdays(tmp_path) -> None:
    m = HabitModel(tmp_path / "habits.json")
    today_wd = _today().isoweekday()
    hit = m.add_habit({"name": "今天有", "schedule": {"type": "weekly", "days": [today_wd]}})
    miss_wd = today_wd % 7 + 1                      # 1..7 里换一个不同的
    miss = m.add_habit({"name": "今天没有", "schedule": {"type": "weekly", "days": [miss_wd]}})
    assert m.is_active_today(hit) is True
    assert m.is_active_today(miss) is False


def test_monthly_active_until_quota_met(tmp_path) -> None:
    """回归：本月完成次数达配额后应不再激活（旧实现恒激活）。"""
    m = HabitModel(tmp_path / "habits.json")
    hid = m.add_habit({"name": "每月两次", "schedule": {"type": "monthly", "value": 2}})
    this_month = _today().strftime("%Y-%m")

    assert m.is_active_today(hid) is True                    # 0/2
    m.data["logs"] = {f"{this_month}-01": {hid: {"completed": True}}}
    assert m.is_active_today(hid) is True                    # 1/2
    m.data["logs"][f"{this_month}-02"] = {hid: {"completed": True}}
    assert m.is_active_today(hid) is False                   # 2/2 → 配额达成


def test_monthly_ignores_previous_months(tmp_path) -> None:
    """上个月做满配额，不影响本月重新激活。"""
    m = HabitModel(tmp_path / "habits.json")
    hid = m.add_habit({"name": "每月两次", "schedule": {"type": "monthly", "value": 2}})
    today = _today()
    prev_month_day = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    m.data["logs"] = {
        f"{prev_month_day}-01": {hid: {"completed": True}},
        f"{prev_month_day}-02": {hid: {"completed": True}},
    }
    assert m.is_active_today(hid) is True


def test_monthly_ignores_other_habits(tmp_path) -> None:
    """别的习惯的完成记录不能算进本习惯的配额。"""
    m = HabitModel(tmp_path / "habits.json")
    hid = m.add_habit({"name": "甲", "schedule": {"type": "monthly", "value": 1}})
    other = m.add_habit({"name": "乙", "schedule": {"type": "daily"}})
    this_month = _today().strftime("%Y-%m")
    m.data["logs"] = {f"{this_month}-01": {other: {"completed": True}}}
    assert m.is_active_today(hid) is True


def test_interval_respects_start_date(tmp_path) -> None:
    m = HabitModel(tmp_path / "habits.json")
    today = _today()
    started = m.add_habit({
        "name": "从今天开始",
        "schedule": {"type": "interval", "value": 2, "start_date": today.isoformat()},
    })
    future = m.add_habit({
        "name": "明天开始",
        "schedule": {"type": "interval", "value": 2,
                     "start_date": (today + timedelta(days=1)).isoformat()},
    })
    assert m.is_active_today(started) is True
    assert m.is_active_today(future) is False


def test_canceled_today_is_inactive(tmp_path) -> None:
    m = HabitModel(tmp_path / "habits.json")
    hid = m.add_habit({"name": "每天", "schedule": {"type": "daily"}})
    assert m.cancel_today(hid) is True
    assert m.is_active_today(hid) is False


def test_postponed_to_future_is_inactive(tmp_path) -> None:
    m = HabitModel(tmp_path / "habits.json")
    hid = m.add_habit({"name": "每天", "schedule": {"type": "daily"}})
    future = (_today() + timedelta(days=2)).isoformat()
    m.postpone(hid, future)
    assert m.is_active_today(hid) is False


def test_unknown_habit_id_is_inactive(tmp_path) -> None:
    m = HabitModel(tmp_path / "habits.json")
    assert m.is_active_today("h_999") is False
