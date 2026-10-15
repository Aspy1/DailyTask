"""scripts/actions.py 命令层冒烟测试。

每条命令在隔离的临时数据目录中跑一遍，断言：
  1. 返回成功（"OK ..."），而不是 ERROR / 异常；
  2. JSON 文件按预期发生变化。

这是改动 actions.py / 数据模型时的安全网。测试不依赖 Qt，也不触碰真实 data/。
"""

from datetime import date

import pytest
from helpers import read_json, run

# ── 作业 ────────────────────────────────────────────────────

def test_add_task_writes_task(sandbox) -> None:
    out = run('python scripts/actions.py add_task --course "算法" '
              '--title "背包问题" --due 2026-06-20')
    assert out.startswith("OK add_task"), out
    data = read_json(sandbox, "tasks.json")
    assert data["archived"] == []
    task = data["tasks"][0]
    assert task["id"] == "t_001"
    assert task["title"] == "背包问题"
    assert task["course_name"] == "算法"
    assert task["due_date"].startswith("2026-06-20")


def test_add_task_without_due_is_rejected(sandbox) -> None:
    """回归：ERRORS #005 —— 缺可选参数不应崩溃，缺必填 due 应报 ERROR。"""
    out = run('python scripts/actions.py add_task --title "无截止"')
    assert out.startswith("ERROR"), out
    assert read_json(sandbox, "tasks.json") == {}


def test_complete_task_archives(sandbox) -> None:
    run('python scripts/actions.py add_task --title "A" --due 2026-06-20')
    out = run("python scripts/actions.py complete_task --id t_001")
    assert out.startswith("OK complete_task"), out
    data = read_json(sandbox, "tasks.json")
    assert data["tasks"] == []
    assert data["archived"][0]["status"] == "completed"


# ── 考试 ────────────────────────────────────────────────────

def test_add_exam(sandbox) -> None:
    out = run('python scripts/actions.py add_exam --course "高等数学" '
              '--date 2026-06-20 --scope "第1-8章"')
    assert out.startswith("OK add_exam"), out
    exam = read_json(sandbox, "exams.json")["exams"][0]
    assert exam["id"] == "e_001"
    assert exam["exam_date"] == "2026-06-20"
    assert exam["scope"] == "第1-8章"


# ── 习惯 ────────────────────────────────────────────────────

def test_add_habit_weekly(sandbox) -> None:
    out = run('python scripts/actions.py add_habit --name "跑步" '
              '--schedule "weekly/1,3,5" --duration 45')
    assert out.startswith("OK add_habit"), out
    h = read_json(sandbox, "habits.json")["habits"][0]
    assert h["id"] == "h_001"
    assert h["schedule"] == {"type": "weekly", "days": [1, 3, 5]}
    assert h["duration_minutes"] == 45


def test_log_habit(sandbox) -> None:
    run('python scripts/actions.py add_habit --name "跑步" --schedule "daily/1"')
    out = run("python scripts/actions.py log_habit --id h_001")
    assert out.startswith("OK log_habit"), out
    data = read_json(sandbox, "habits.json")
    assert data["habits"][0]["streak"] == 1
    assert data["logs"][date.today().isoformat()]["h_001"]["completed"] is True


# ── 日程计划 ────────────────────────────────────────────────

_TWO_PLANS = ("python scripts/actions.py replace_plans --date 2026-06-08 "
              '--plans \'[{"title":"A","time_slot":1},{"title":"B","time_slot":2}]\'')


def test_add_plan(sandbox) -> None:
    out = run('python scripts/actions.py add_plan --date 2026-06-08 '
              '--title "复习" --slot 3')
    assert out.startswith("OK add_plan"), out
    plan = read_json(sandbox, "daily_logs.json")["plans"]["2026-06-08"][0]
    assert plan["time_slot"] == 3
    assert plan["title"] == "复习"


def test_replace_plans(sandbox) -> None:
    out = run(_TWO_PLANS)
    assert out.startswith("OK replace_plans"), out
    plans = read_json(sandbox, "daily_logs.json")["plans"]["2026-06-08"]
    assert [p["title"] for p in plans] == ["A", "B"]


def test_delete_plan(sandbox) -> None:
    run(_TWO_PLANS)
    out = run("python scripts/actions.py delete_plan --date 2026-06-08 --index 0")
    assert out.startswith("OK delete_plan"), out
    plans = read_json(sandbox, "daily_logs.json")["plans"]["2026-06-08"]
    assert [p["title"] for p in plans] == ["B"]


# ── 课程 ────────────────────────────────────────────────────

def test_add_then_delete_course(sandbox) -> None:
    out = run('python scripts/actions.py add_course --name "高等数学" --day 1 '
              '--weeks 1-16 --slots 1-2 --location A201')
    assert out.startswith("OK add_course"), out
    c = read_json(sandbox, "courses.json")["courses"][0]
    assert c["id"] == "c_001"
    assert c["weeks"] == {"start": 1, "end": 16}
    assert c["time_slots"][0] == {"start": 1, "end": 2, "location": "A201"}

    out = run("python scripts/actions.py delete_course --id c_001")
    assert out.startswith("OK delete_course"), out
    assert read_json(sandbox, "courses.json")["courses"] == []


# ── 物品 ────────────────────────────────────────────────────

def test_add_update_delete_item(sandbox) -> None:
    out = run('python scripts/actions.py add_item --name "洗发水" '
              '--category 日常消耗品 --quantity 2 --location 浴室')
    assert out.startswith("OK add_item"), out
    it = read_json(sandbox, "inventory.json")["items"][0]
    assert it["id"] == "i_001"
    assert it["quantity"] == 2
    assert it["status"] == "充足"

    out = run("python scripts/actions.py update_item --id i_001 "
              "--quantity 0 --status 需购")
    assert out.startswith("OK update_item"), out
    it = read_json(sandbox, "inventory.json")["items"][0]
    assert it["quantity"] == 0
    assert it["status"] == "需购"

    out = run("python scripts/actions.py delete_item --id i_001")
    assert out.startswith("OK delete_item"), out
    assert read_json(sandbox, "inventory.json")["items"] == []


def test_add_item_quantity_zero_marks_restock(sandbox) -> None:
    """--quantity 0（已用完）应记为需购。

    已知缺陷：cmd_add_item 用 `args.quantity or 1`，把 0 当缺省值 → 记为 1 件充足。
    """
    pytest.xfail("cmd_add_item 的 `args.quantity or 1` 把 --quantity 0 当成缺省值 1（待修）")
    run('python scripts/actions.py add_item --name "洗衣液" --quantity 0')
    it = read_json(sandbox, "inventory.json")["items"][0]
    assert it["quantity"] == 0 and it["status"] == "需购"


def test_need_restock_and_lookup(sandbox) -> None:
    run('python scripts/actions.py add_item --name "洗衣液" --quantity 2')
    run("python scripts/actions.py update_item --id i_001 --status 需购")
    out = run("python scripts/actions.py need_restock")
    assert "洗衣液" in out, out
    out = run("python scripts/actions.py lookup_item --name 洗衣")
    assert "FOUND 1" in out, out


# ── 概览 / 未知命令 ─────────────────────────────────────────

def test_status(sandbox) -> None:
    run('python scripts/actions.py add_task --title "A" --due 2026-06-20')
    out = run("python scripts/actions.py status")
    assert "tasks=1" in out


def test_unknown_action_reports_error(sandbox) -> None:
    out = run("python scripts/actions.py definitely_not_a_command")
    assert out.startswith("ERROR") and "unknown action" in out.lower(), out
