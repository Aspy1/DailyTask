"""P2：Hermes 定时提醒的**投递账本**要分三态（审计 2026-11-21）。

复现：`scripts/hermes_reminders.py` 当前**先写去重账本，再由 Hermes 投递**。
两者之间失败（网关离线 / 微信故障）时，账本已经记成"发过了"→ 当天那条提醒
永远不会再来一次，而且**没有任何地方**能看出来漏发了。

验收（审计原文）：
- 状态拆成 **待投递 / 已接受 / 结果不确定**；
- 投递端有可用幂等键才自动重试不确定结果；否则**记录并提示人工核对**；
- 保留"本机进程存活"与"微信投递可用"两个诊断口径。
"""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from scripts.hermes_reminders import ledger_states, run_reminders


def _ledger(sandbox) -> Path:
    return sandbox / "ledger.sqlite"


def test_produced_message_is_pending_until_acknowledged(sandbox) -> None:
    """⭐ 产出 ≠ 投递：默认只记 `pending`，投递端确认后才变 `delivered`。"""
    ledger = _ledger(sandbox)

    assert "午饭" in run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 40))

    states = ledger_states(ledger)
    assert states["pending"], states
    assert not states["delivered"], states


def test_ack_marks_delivered_and_suppresses_repeats(sandbox) -> None:
    """Only the matched scheduler execution may confirm the generated batch."""
    ledger = _ledger(sandbox)
    scheduler = sandbox / "executions.db"
    with closing(sqlite3.connect(scheduler)) as db, db:
        db.execute("CREATE TABLE executions (id TEXT, job_id TEXT, status TEXT, delivery_outcome TEXT)")
        db.execute("INSERT INTO executions VALUES ('run1', 'job', 'running', NULL)")
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 40),
                  scheduler=(scheduler, "job"))
    with closing(sqlite3.connect(scheduler)) as db, db:
        db.execute("INSERT INTO executions VALUES ('other', 'job', 'completed', 'delivered')")
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 41),
                  scheduler=(scheduler, "job"))
    assert ledger_states(ledger)["pending"] == 1
    with closing(sqlite3.connect(scheduler)) as db, db:
        db.execute("UPDATE executions SET status='completed', delivery_outcome='delivered' WHERE id='run1'")
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 42),
                  scheduler=(scheduler, "job"))

    states = ledger_states(ledger)
    assert states["delivered"], states
    assert not states["pending"], states
    assert run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 50)) == ""


def test_failed_or_ambiguous_scheduler_runs_do_not_ack_another_batch(sandbox) -> None:
    ledger = _ledger(sandbox)
    scheduler = sandbox / "executions.db"
    with closing(sqlite3.connect(scheduler)) as db, db:
        db.execute("CREATE TABLE executions (id TEXT, job_id TEXT, status TEXT, delivery_outcome TEXT)")
        db.execute("INSERT INTO executions VALUES ('lunch', 'job', 'running', NULL)")
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 40),
                  scheduler=(scheduler, "job"))
    with closing(sqlite3.connect(scheduler)) as db, db:
        db.execute("UPDATE executions SET status='completed', delivery_outcome='failed' WHERE id='lunch'")
        db.executemany("INSERT INTO executions VALUES (?, 'job', 'running', NULL)", [("a",), ("b",)])
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 16, 40),
                  scheduler=(scheduler, "job"))
    with closing(sqlite3.connect(scheduler)) as db, db:
        db.execute("UPDATE executions SET status='completed', delivery_outcome='delivered' WHERE id != 'lunch'")
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 16, 45),
                  scheduler=(scheduler, "job"))
    assert ledger_states(ledger) == {"pending": 1, "delivered": 0, "uncertain": 1}


def test_unacknowledged_row_becomes_uncertain_after_the_window(sandbox) -> None:
    """⭐ 一直没有 ack（投递端失败）→ 过期后是 `uncertain`，**不是**静默当已发。"""
    ledger = _ledger(sandbox)
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 40))

    # 第二天再跑：昨天那条没有 ack → 结果不确定
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 22, 9, 0))

    states = ledger_states(ledger)
    assert states["uncertain"], states


def test_uncertain_is_reported_for_manual_check(sandbox, caplog) -> None:
    """没有幂等键就**不自动重试**，而是记录 + 提示人工核对（审计口径）。"""
    ledger = _ledger(sandbox)
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 40))

    with caplog.at_level("WARNING", logger="src.services.hermes_ledger"):
        caplog.clear()
        run_reminders("meal", sandbox, ledger, datetime(2026, 11, 22, 9, 0))

    assert any("人工核对" in record.getMessage() for record in caplog.records), \
        "结果不确定时必须留一条可排查的警告"


def test_uncertain_is_not_retried_without_idempotency(sandbox) -> None:
    """⭐ 我们的消息没有幂等键 → 不能自动重发（会变成重复提醒）。"""
    ledger = _ledger(sandbox)
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 40))
    run_reminders("meal", sandbox, ledger, datetime(2026, 11, 22, 9, 0))

    # 第三天：那条 uncertain 不会被当成"新的"再发一次
    third = run_reminders("meal", sandbox, ledger, datetime(2026, 11, 23, 9, 0))
    assert "午饭" not in third, third


def test_old_rows_without_state_count_as_delivered(sandbox) -> None:
    """老账本（没有 state 列）按"已接受"读：升级后不要重放历史提醒。"""
    ledger = _ledger(sandbox)
    with closing(sqlite3.connect(ledger)) as db, db:
        db.execute("CREATE TABLE emitted (namespace TEXT, key TEXT, expiry TEXT, "
                   "PRIMARY KEY(namespace, key))")
        db.execute("INSERT INTO emitted VALUES (?, ?, ?)",
                   ("meal:2026-11-21", "lunch", "2026-11-22"))

    states = ledger_states(ledger)
    assert states["delivered"] == 1, states
    assert not states["pending"] and not states["uncertain"]


def test_diagnostics_distinguish_process_and_delivery(sandbox) -> None:
    """两个诊断口径："本机进程存活"与"微信投递可用"必须分开看。"""
    from scripts.hermes_reminders import delivery_diagnostics

    report = delivery_diagnostics(_ledger(sandbox))

    assert "process_alive" in report and "delivery_available" in report
