"""回执 + 领域验收（专项审查 §3.2 / §3.3 第一步）的回归。

要点：`OK` 只说明 handler 没报错，**不说明用户要的状态成立了** ——
所以执行后回读数据、按确定性规则判一次，并把结论回喂给模型。
"验收器本身也要测试"（审查 §3.3 明确要求），所以这里既测验收规则，也测它接进 worker。
"""

from src.services import ai_verify
from src.services.data_manager import DataManager


def test_parse_command_handles_both_option_styles() -> None:
    op, args = ai_verify.parse_command(
        'python scripts/actions.py update_item --id i_001 --location "桌面"')
    assert op == "update_item" and args["id"] == "i_001" and args["location"] == "桌面"
    op2, args2 = ai_verify.parse_command("python scripts/actions.py consume --id=i_002 --amount=2")
    assert op2 == "consume" and args2 == {"id": "i_002", "amount": "2"}


# ── 验收规则（纯逻辑，桩数据）───────────────────────────────

def test_consume_verifies_the_exact_amount(sandbox) -> None:
    from scripts.actions import run_in_process

    dm = DataManager(sandbox)
    dm.inventory.add_item({"name": "布洛芬", "quantity": 1, "doses_per_unit": 24, "min_doses": 5})
    dm.inventory.save()
    cmd = "python scripts/actions.py consume --id i_001 --amount 1"
    was = ai_verify.observe(cmd, sandbox)
    assert was == {"remaining_doses": 24}
    result = run_in_process(cmd)
    assert ai_verify.check(cmd, was, result, sandbox)[0] == ai_verify.VERIFIED


def test_consume_mismatch_when_the_command_claimed_ok_but_nothing_changed(sandbox) -> None:
    """⭐ 命令说 OK、余量却没变 —— 这是**不一致**，不是"无变化也算成功"。"""
    dm = DataManager(sandbox)
    dm.inventory.add_item({"name": "布洛芬", "quantity": 1, "doses_per_unit": 24})
    dm.inventory.save()
    cmd = "python scripts/actions.py consume --id i_001 --amount 1"
    state, detail = ai_verify.check(cmd, {"remaining_doses": 24}, "OK consume", sandbox)
    assert state == ai_verify.MISMATCH and "没扣掉" in detail


def test_location_move_verified_then_noop(sandbox) -> None:
    from scripts.actions import run_in_process

    dm = DataManager(sandbox)
    dm.inventory.add_item({"name": "抽纸", "quantity": 2, "location": "书架3"})
    dm.inventory.save()
    cmd = 'python scripts/actions.py update_item --id i_001 --location "桌面"'
    was = ai_verify.observe(cmd, sandbox)
    result = run_in_process(cmd)
    assert ai_verify.check(cmd, was, result, sandbox)[0] == ai_verify.VERIFIED
    # 再移动一次到同一个位置 → 本来已满足（**不算失败**）
    cmd2 = 'python scripts/actions.py update_item --id i_001 --location "桌面"'
    was2 = ai_verify.observe(cmd2, sandbox)
    state, detail = ai_verify.check(cmd2, was2, run_in_process(cmd2), sandbox)
    assert state == ai_verify.NOOP and "本来就是" in detail


def test_location_mismatch_reports_the_actual_value(sandbox) -> None:
    dm = DataManager(sandbox)
    dm.inventory.add_item({"name": "抽纸", "quantity": 2, "location": "书架3"})
    dm.inventory.save()
    cmd = 'python scripts/actions.py update_item --id i_001 --location "桌面"'
    state, detail = ai_verify.check(cmd, {"location": "书架3"}, "OK", sandbox)
    assert state == ai_verify.MISMATCH and "书架3" in detail


def test_complete_plan_is_verified(sandbox) -> None:
    dm = DataManager(sandbox)
    dm.daily_logs.add_plan({"title": "复习"}, day="2026-10-19")
    dm.daily_logs.save()
    cmd = "python scripts/actions.py complete_plan --date 2026-10-19 --index 0"
    was = ai_verify.observe(cmd, sandbox)
    assert was == {"done": False}
    assert ai_verify.check(cmd, was, "OK", sandbox)[0] == ai_verify.MISMATCH, "还没标记完成"
    dm.daily_logs.set_plan_done("2026-10-19", 0, True)
    dm.daily_logs.save()
    assert ai_verify.check(cmd, was, "OK", sandbox)[0] == ai_verify.VERIFIED


def test_operations_without_a_verifier_are_not_reported_as_passed(sandbox) -> None:
    """⭐ 没有验收器 → `unverified`（**不许**当成通过）。"""
    cmd = 'python scripts/actions.py add_task --title "写作业"'
    assert ai_verify.check(cmd, {}, "OK", sandbox)[0] == ai_verify.UNVERIFIED


def test_failed_command_is_not_reported_as_mismatch(sandbox) -> None:
    """命令自己报错 → `failed`（别把"执行失败"说成"验收不通过"）。"""
    cmd = "python scripts/actions.py consume --id i_001 --amount 1"
    assert ai_verify.check(cmd, {"remaining_doses": 24}, "ERROR 参数不合法", sandbox)[0] \
        == ai_verify.FAILED


# ── 接进 worker：结论要**回喂给模型** ───────────────────────

def test_worker_feeds_the_verdict_back_to_the_model(qapp, sandbox) -> None:
    """⭐ 从 worker 的真实入口走一遍：工具结果里必须带 `[验收]` 与具体数字。"""
    from src.services.ai_service import AIWorker

    dm = DataManager(sandbox)
    dm.inventory.add_item({"name": "布洛芬", "quantity": 1, "doses_per_unit": 24, "min_doses": 5})
    dm.inventory.save()

    worker = AIWorker(None, "m", "", [], dm, None)
    text, ok, bad, off_target = worker._run_commands(
        ["python scripts/actions.py consume --id i_001 --amount 1"], {})
    assert "[验收]" in text and "24 → 23" in text, text
    assert ok == 1 and not bad and not off_target


def test_worker_reports_off_target_in_the_final_note(qapp) -> None:
    """⭐ 验收没达到预期的，要在**给用户的最终文本**里出现（汇报权归代码）。"""
    from src.services.ai_service import AIWorker

    worker = AIWorker(None, "m", "", [], None, None)
    seen: list[str] = []
    worker.finished_with_instructions.connect(lambda t, _i: seen.append(t))
    worker._finish(["python scripts/actions.py consume --id i_001 --amount 1"],
                   wrote_data=True, display="记好了", ok_count=1,
                   write_failures=["命令说成功，但余量还是 24（没扣掉）"])
    assert seen and "没有生效或没达到预期" in seen[-1]
    assert "没扣掉" in seen[-1]
