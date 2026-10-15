"""日期/时间解析回归测试（scripts/actions.py）。

覆盖两个真实缺陷：

1. **具体时间被静默丢弃**：`cmd_add_task` 先调 `parse_date`（只保留年月日），
   再调 `normalize_time` 兜底 → `--due 2026-10-20T14:30` / `下午3点` 全变成 `T23:00:00`，
   连带 DDL 倒计时、"6 小时内邮件"、日程 DDL 线全部错位。
2. **"下周X" 普遍晚一周**：`_parse_relative_date` 里多余的 `days_ahead += 7`。

另外守住：只给日期补 23:00、非法日期必须报错而不是写坏数据。
"""

from datetime import date, timedelta

import pytest
from helpers import read_json, run


def _due(sandbox, arg: str) -> str:
    out = run(f'python scripts/actions.py add_task --title "T" --due {arg}')
    assert out.startswith("OK"), out
    return read_json(sandbox, "tasks.json")["tasks"][-1]["due_date"]


# ── 时间保留 ────────────────────────────────────────────────

@pytest.mark.parametrize(("arg", "expected"), [
    ("2026-10-20T14:30", "2026-10-20T14:30:00"),
    ("2026-10-20T14:30:00", "2026-10-20T14:30:00"),
    ("2026-10-20T09:05", "2026-10-20T09:05:00"),
    ('"2026-10-20 14:30"', "2026-10-20T14:30:00"),
])
def test_iso_time_is_preserved(sandbox, arg, expected) -> None:
    assert _due(sandbox, arg) == expected


@pytest.mark.parametrize(("arg", "expected"), [
    ("2026-10-20T下午3点", "2026-10-20T15:00:00"),
    ("2026-10-20T晚上8点半", "2026-10-20T20:30:00"),
    ("2026-10-20T晚上8点30", "2026-10-20T20:30:00"),
    ("2026-10-20T下午2点15分", "2026-10-20T14:15:00"),
    ("2026-10-20T中午12点", "2026-10-20T12:00:00"),
    ("2026-10-20T上午9点", "2026-10-20T09:00:00"),
])
def test_chinese_time_is_preserved(sandbox, arg, expected) -> None:
    assert _due(sandbox, arg) == expected


def test_date_only_defaults_to_end_of_day(sandbox) -> None:
    assert _due(sandbox, "2026-10-20") == "2026-10-20T23:00:00"


def test_month_day_forms_normalize_to_iso(sandbox) -> None:
    """回归：`10-25` 以前会被原样写成 `10-25T23:00:00`（非法日期）。"""
    due = _due(sandbox, "10-25")
    d = date.fromisoformat(due[:10])          # 必须能解析
    assert (d.month, d.day) == (10, 25)
    assert d >= date.today()                  # 月日形式自动补年份，取未来的一次
    assert _due(sandbox, "10.25")[:10] == due[:10]


def test_relative_dates(sandbox) -> None:
    tomorrow = date.today() + timedelta(days=1)
    assert _due(sandbox, "明天") == f"{tomorrow.isoformat()}T23:00:00"
    assert _due(sandbox, "今天") == f"{date.today().isoformat()}T23:00:00"
    n3 = date.today() + timedelta(days=3)
    assert _due(sandbox, "3天后") == f"{n3.isoformat()}T23:00:00"


# ── "下周X" ────────────────────────────────────────────────

@pytest.mark.parametrize("wd", range(7))
def test_next_week_lands_in_next_calendar_week(sandbox, wd) -> None:
    """回归：以前周一到周五的结果普遍晚一周（下周五会算成 14 天后）。"""
    name = "一二三四五六日"[wd]
    today = date.today()
    next_monday = today + timedelta(days=7 - today.weekday())
    expected = next_monday + timedelta(days=wd)
    assert _due(sandbox, f"下周{name}") == f"{expected.isoformat()}T23:00:00"


def test_this_week_weekday_is_within_seven_days(sandbox) -> None:
    """`周五`/`这周五` 指本周尚未到来的那天（已过则顺延一周内）。"""
    today = date.today()
    for wd in range(7):
        name = "一二三四五六日"[wd]
        d = date.fromisoformat(_due(sandbox, f"周{name}")[:10])
        assert 1 <= (d - today).days <= 7, (name, d)


# ── 非法输入必须报错，不得写坏数据 ──────────────────────────

@pytest.mark.parametrize("bad", ["瞎写的日期", "下下周", "2026/10/20", "13月45日"])
def test_unparsable_date_is_rejected(sandbox, bad) -> None:
    out = run(f'python scripts/actions.py add_task --title "T" --due "{bad}"')
    assert out.startswith("ERROR"), out
    assert read_json(sandbox, "tasks.json") == {}


def test_missing_due_is_rejected(sandbox) -> None:
    out = run('python scripts/actions.py add_task --title "T"')
    assert out.startswith("ERROR"), out
    assert read_json(sandbox, "tasks.json") == {}
