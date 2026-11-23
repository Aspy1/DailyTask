"""P1：创建类命令必须按**显式提交的字段**回读验收（审计 2026-11-21）。

复现（静态审查）：`add_task` / `add_course` / `add_plan` 的验收只看"标题/名称在不在"，
于是 `--due` / `--slots` / `--slot` / `--priority` 写错也照样报"验收通过"。
审计原文：对接收 AI 命令的入口，用提交回执中的稳定记录 ID 回读截止时间、课程节次、
计划日期和默认字段；把提交成功、验收覆盖与可撤销性作为独立字段。

同位验收的老坑（`ERRORS #060`）：**验收与写入同一口径** —— 课程名归一化
（`match_course_from`）与日期解析（`parse_date`）必须调同一个函数。
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from helpers import run

from src.models import semester_paths
from src.services import ai_verify


def _seed_registry(sandbox) -> None:
    payload = {"_version": 1, "current_semester": "sem_001", "semesters": [
        {"id": "sem_001", "name": "本学期", "start_date": "2026-09-21",
         "total_weeks": 16, "period_count": 6, "exam_weeks": 1}]}
    (semester_paths.registry_path(sandbox)).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _run(command: str) -> str:
    out = run(command)
    assert out.startswith("OK"), out
    return out


def _check(sandbox, command: str) -> tuple[str, str]:
    before = ai_verify.observe(command, sandbox)
    out = _run(command)
    return ai_verify.check(command, before, out, sandbox)


# ── 作业：截止时间 / 课程 / 优先级 ──────────────────────────


def test_add_task_verifies_due_date(sandbox) -> None:
    """`--due` 写错了不能报"验收通过"。"""
    due = (datetime.now() + timedelta(days=3)).isoformat(timespec="minutes")
    command = f'python scripts/actions.py add_task --title 算法实验 --due {due} --course 算法'
    state, detail = _check(sandbox, command)
    assert state == ai_verify.VERIFIED, detail
    assert due[:10] in detail, detail


def test_add_task_reports_mismatch_when_due_is_wrong(sandbox) -> None:
    """命令回 OK 但落盘值对不上 → MISMATCH（不是 VERIFIED）。"""
    due = (datetime.now() + timedelta(days=3)).isoformat(timespec="minutes")
    command = f'python scripts/actions.py add_task --title 算法实验 --due {due}'
    before = ai_verify.observe(command, sandbox)
    _run(command)
    _rewrite(sandbox, "tasks.json", {"due_date": "2001-01-01T00:00:00"})

    state, detail = ai_verify.check(command, before, "OK add_task 算法实验", sandbox)

    assert state == ai_verify.MISMATCH, detail
    assert "截止" in detail


def test_add_course_verifies_slots_and_day(sandbox) -> None:
    command = ('python scripts/actions.py add_course --name 高等数学 '
               '--day 2 --slots "3-4" --location 教学楼A')
    state, detail = _check(sandbox, command)

    assert state == ai_verify.VERIFIED, detail
    assert "3-4" in detail or "节" in detail


def test_add_course_reports_mismatch_when_slots_are_wrong(sandbox) -> None:
    command = ('python scripts/actions.py add_course --name 高等数学 '
               '--day 2 --slots "3-4"')
    before = ai_verify.observe(command, sandbox)
    _run(command)
    _rewrite_course(sandbox, slots={"start": 5, "end": 6})

    state, detail = ai_verify.check(command, before, "OK add_course 高等数学", sandbox)

    assert state == ai_verify.MISMATCH, detail


def test_add_plan_verifies_the_date_it_wrote_to(sandbox) -> None:
    """计划按**日期**分组：验收必须读 `--date` 那天，而不是"任何计划列表"。"""
    tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
    command = (f'python scripts/actions.py add_plan --date {tomorrow} '
               f'--title 背单词 --slot 2')

    state, detail = _check(sandbox, command)

    assert state == ai_verify.VERIFIED, detail
    assert tomorrow in detail, detail


def test_add_plan_reports_mismatch_when_written_to_another_day(sandbox) -> None:
    tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
    command = f'python scripts/actions.py add_plan --date {tomorrow} --title 背单词 --slot 2'
    before = ai_verify.observe(command, sandbox)
    _run(command)
    _move_plans(sandbox, tomorrow, "2001-01-01")

    state, detail = ai_verify.check(command, before, "OK add_plan 背单词", sandbox)

    assert state == ai_verify.MISMATCH, detail


def test_add_habit_verifies_schedule_and_duration(sandbox) -> None:
    command = 'python scripts/actions.py add_habit --name 跑步 --schedule "daily/2" --duration 30'
    state, detail = _check(sandbox, command)

    assert state == ai_verify.VERIFIED, detail
    assert "daily" in detail and "30" in detail, detail


def test_add_habit_reports_a_wrong_schedule(sandbox) -> None:
    """周期写错必须报出来（原来只核名称）。"""
    command = 'python scripts/actions.py add_habit --name 跑步 --schedule "daily/2"'
    before = ai_verify.observe(command, sandbox)
    _run(command)
    _rewrite_habit(sandbox, {"type": "weekly", "days": [1, 3]})

    state, detail = ai_verify.check(command, before, "OK add_habit 跑步", sandbox)

    assert state == ai_verify.MISMATCH, detail


def test_add_expense_verifies_amount_before_the_write(sandbox) -> None:
    """金额是**钱**：写错就必须报出来（原来只核分类/链式比对）。"""
    command = 'python scripts/actions.py add_expense --amount 25.5 --category food'
    state, detail = _check(sandbox, command)

    assert state == ai_verify.VERIFIED, detail
    assert "25.5" in detail or "25.50" in detail


# ── 辅助：在磁盘上把刚写的值改坏，模拟"写入路径与验收口径不一致" ──


def _path(sandbox, name: str) -> Path:
    return semester_paths.resolve(sandbox, name)


def _rewrite(sandbox, name: str, changes: dict) -> None:
    path = _path(sandbox, name)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tasks"][0].update(changes)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rewrite_course(sandbox, *, slots: dict) -> None:
    path = _path(sandbox, "courses.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["courses"][0]["time_slots"] = [{"start": slots["start"], "end": slots["end"],
                                            "location": ""}]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _move_plans(sandbox, source: str, target: str) -> None:
    path = sandbox / "daily_logs.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("plans", {})[target] = payload.get("plans", {}).pop(source, [])
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rewrite_habit(sandbox, schedule: dict) -> None:
    path = sandbox / "habits.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["habits"][0]["schedule"] = schedule
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
