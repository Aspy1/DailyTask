"""日程计划 / 考试 / 习惯 / 课程 的验收器（从 `ai_verify.py` 拆出，Q-A1 文件上限）。

`ai_verify.py` 负责调度（`observe` / `check` / 表驱动注册）与物品族；
这一族按"同一类业务对象"聚在一起：考试、习惯、日程计划、课程回读。
拆分的理由与 `ai_verify_inventory.py` 相同 —— 主文件已超过 800 行。

⚠ **验收与写入同一口径**（`ERRORS #060`）：写入端归一化过的字段
（课程名 `match_course_from`、日期 `parse_date`、周期 `daily/1`）验收端必须调
同一个函数，否则拿命令原文比对落盘值会误报"找不到"。
"""

import json
from datetime import date
from pathlib import Path

from src.services.ai_verify import (
    MISMATCH,
    NOOP,
    UNVERIFIED,
    VERIFIED,
    _courses,
    _field_problem,
    _read,
    _read_semester,
)

# ── 考试 ────────────────────────────────────────────────────

def observe_add_exam(args: dict, data_dir: Path) -> dict:
    return {"count": len(_read_semester(data_dir, "exams.json").get("exams") or [])}


def check_add_exam(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """记考试：**数量增加 + 归一化后的课程名/日期对得上**。

    ⚠ 落盘的是**写入端归一化过**的值（`cmd_add_exam` 调 `match_course` / `parse_date`）：
    课程简称 → 课程表全名，`2026-11-20T16:00` → `2026-11-20`。验收必须调**同一套**
    函数（`match_course_from` / `parse_date`），否则已写入也会报"考试列表里找不到"。
    """
    from scripts.actions_core import match_course_from, parse_date

    raw_course = str(args.get("course", ""))
    course = match_course_from(_courses(data_dir), raw_course)
    exam_date = parse_date(args["date"]) if args.get("date") else ""
    exams = _read_semester(data_dir, "exams.json").get("exams") or []
    hit = any(e.get("course_name") == course and e.get("exam_date") == exam_date
              for e in exams)
    name = course or raw_course
    if len(exams) > int(before.get("count", -1)) and hit:
        return VERIFIED, f"考试「{name}」已写入"
    return MISMATCH, f"考试列表里找不到「{name}」"


# ── 习惯 ────────────────────────────────────────────────────

def observe_add_habit(args: dict, data_dir: Path) -> dict:
    return {"count": len(_read(data_dir, "habits.json").get("habits") or [])}


def check_add_habit(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """新增习惯：数量增加 + 名称对得上 + **周期 / 时长**回读（审计 2026-11-21 P1）。"""
    name = args.get("name", "")
    habits = _read(data_dir, "habits.json").get("habits") or []
    hit = next((h for h in habits if h.get("name") == name), None)
    if len(habits) <= int(before.get("count", -1)) or hit is None:
        return MISMATCH, f"习惯列表里找不到「{name}」"
    schedule = hit.get("schedule") or {}
    problems = _habit_problems(args, hit, schedule)
    if problems:
        return MISMATCH, "；".join(problems)
    return VERIFIED, f"习惯「{name}」已写入{_habit_detail(args, hit, schedule)}"


def _habit_problems(args: dict, hit: dict, schedule: dict) -> list[str]:
    """按命令**显式传入**的字段比对落盘值。"""
    checks = (
        _field_problem("周期", _canonical_schedule(args.get("schedule")),
                       _schedule_text(schedule)),
        _field_problem("时长", args.get("duration"), hit.get("duration_minutes")),
        _field_problem("提醒时间", args.get("reminder"), hit.get("reminder_time")),
    )
    return [problem for problem in checks if problem]


def _habit_detail(args: dict, hit: dict, schedule: dict) -> str:
    """回执里附上**回读到的**周期 / 时长（用户要看"写成了什么"）。"""
    shown = []
    if args.get("schedule"):
        shown.append(f"周期 {_schedule_text(schedule)}")
    if args.get("duration"):
        shown.append(f"{hit.get('duration_minutes')} 分钟")
    return f"（{' · '.join(shown)}）" if shown else ""


def _canonical_schedule(raw: str | None) -> str | None:
    """命令里的 `--schedule` → 落盘同一口径（`daily` ≡ `daily/1`）。"""
    if not raw:
        return raw
    kind, _sep, value = str(raw).partition("/")
    return f"{kind}/{value or 1}" if kind == "daily" else str(raw)


def _schedule_text(schedule: dict) -> str:
    """落盘的 schedule 结构 → 与命令**同一套**写法（`daily/2` / `weekly/1,3` / `monthly/3`）。

    写入端（`cmd_add_habit`）把 `daily/1` 存成 `{"type": "daily", "times_per_day": 1}`，
    所以这里的 `daily` 必须带次数，否则拿 `daily` 比 `daily/1` 会误报不一致。
    """
    kind = str(schedule.get("type") or "")
    if not kind:
        return ""
    if kind == "daily":
        return f"daily/{schedule.get('times_per_day', 1)}"
    if kind == "weekly":
        days = ",".join(str(day) for day in schedule.get("days") or [])
        return f"weekly/{days}" if days else kind
    if kind == "monthly":
        return f"monthly/{schedule.get('value', '')}"
    if kind == "interval":
        return f"interval/{schedule.get('value', '')}"
    return kind


def observe_log_habit(args: dict, data_dir: Path) -> dict:
    hid = args.get("id", "")
    entry = ((_read(data_dir, "habits.json").get("logs") or {})
             .get(date.today().isoformat(), {}).get(hid) or {})
    return {"completed": bool(entry.get("completed"))}


def check_log_habit(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    hid = args.get("id", "")
    entry = ((_read(data_dir, "habits.json").get("logs") or {})
             .get(date.today().isoformat(), {}).get(hid) or {})
    if entry.get("completed"):
        if before.get("completed"):
            return NOOP, "今天本来就已经打过卡"
        return VERIFIED, "习惯已打卡"
    return MISMATCH, "习惯打卡没有生效"


# ── 日程计划 ────────────────────────────────────────────────

def observe_add_plan(args: dict, data_dir: Path) -> dict:
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    return {"count": len(plans)}


def check_add_plan(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    """新增计划：数量增加 + 标题对得上 + **写在那一天** + 节次回读（审计 P1）。"""
    day = args.get("date", "")
    title = args.get("title", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    hit = next((p for p in plans if p.get("title") == title), None)
    if len(plans) <= int(before.get("count", -1)) or hit is None:
        return MISMATCH, f"{day} 的计划列表里找不到「{title}」"
    problem = _field_problem("节次", args.get("slot"), hit.get("time_slot"))
    if problem:
        return MISMATCH, f"{day} 的「{title}」{problem}"
    extra = f"（第 {hit.get('time_slot')} 节）" if args.get("slot") else ""
    return VERIFIED, f"{day} 的计划「{title}」已写入{extra}"


# `replace_plans` 的 `--plans` 里**会写进用户数据**的字段（用户传了哪个就核哪个）。
PLAN_FIELDS = ("title", "time_slot", "type", "note", "course_name", "course")


def observe_replace_plans(args: dict, data_dir: Path) -> dict:
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    return {"titles": [p.get("title") for p in plans]}


def _plan_difference(wanted: dict, got: dict) -> str:
    """逐字段比对 `--plans` 里**显式传了**的字段；没传的字段不要求。"""
    for field in PLAN_FIELDS:
        if field in wanted and wanted[field] != got.get(field):
            return f"{field}: 期望 {wanted[field]!r}，实际 {got.get(field)!r}"
    return ""


def check_replace_plans(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    try:
        wanted = json.loads(args.get("plans", "[]"))
    except (TypeError, ValueError):
        return UNVERIFIED, "未验收（--plans 不是合法 JSON，无法核对）"
    if not isinstance(wanted, list) or not all(isinstance(p, dict) for p in wanted):
        return UNVERIFIED, "未验收（--plans 必须是对象数组）"
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    if len(plans) != len(wanted):
        return MISMATCH, f"{day} 的计划是 {len(plans)} 条，期望 {len(wanted)} 条"
    for index, (want, got) in enumerate(zip(wanted, plans, strict=False), start=1):
        difference = _plan_difference(want, got)
        if difference:
            return MISMATCH, f"{day} 第 {index} 条计划不一致（{difference}）"
    return VERIFIED, f"{day} 的计划已整体替换为 {len(plans)} 条（逐字段核对）"


def observe_delete_plan(args: dict, data_dir: Path) -> dict:
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    return {"titles": [p.get("title") for p in plans]}


def check_delete_plan(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    try:
        idx = int(args.get("index", "-1"))
    except ValueError:
        return UNVERIFIED, "未验收（index 不是整数）"
    before_titles = list(before.get("titles") or [])
    if not 0 <= idx < len(before_titles):
        return NOOP, "本来就没有这条计划"
    expected = before_titles[:idx] + before_titles[idx + 1:]
    day = args.get("date", "")
    plans = (_read(data_dir, "daily_logs.json").get("plans") or {}).get(day) or []
    got = [p.get("title") for p in plans]
    if got == expected:
        return VERIFIED, f"计划「{before_titles[idx]}」已删除"
    return MISMATCH, "计划列表与预期不一致（可能删错了那条）"
