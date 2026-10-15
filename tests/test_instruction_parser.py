"""指令执行器契约：在内存执行、逐条隔离、**不触碰 Model**（CODE_STANDARDS Q-B2）。

`execute` 现在只接受 commands（不再接收 dm/settings）：
数据重载与信号由主线程的 AIService 负责；若签名被改回，本测试会立刻失败。
"""

from src.services.ai_service import InstructionParser


def test_execute_runs_in_process(sandbox):
    out = InstructionParser.execute(["python scripts/actions.py status"])
    assert len(out) == 1
    assert "tasks=" in out[0]


def test_execute_isolates_errors_per_command(sandbox):
    out = InstructionParser.execute([
        "python scripts/actions.py definitely_not_a_command",
        "python scripts/actions.py status",
    ])
    assert len(out) == 2
    assert "unknown action" in out[0].lower()
    assert "tasks=" in out[1]          # 前一条失败不影响后一条
