"""指令执行器契约：在内存执行、逐条隔离、**不触碰 Model**（CODE_STANDARDS Q-B2）。

`execute` 现在只接受 commands（不再接收 dm/settings）：
数据重载与信号由主线程的 AIService 负责；若签名被改回，本测试会立刻失败。
"""

from src.services.ai_service import InstructionParser


def test_execute_runs_in_process(sandbox) -> None:
    out = InstructionParser.execute(["python scripts/actions.py status"])
    assert len(out) == 1
    assert "tasks=" in out[0]


def test_execute_isolates_errors_per_command(sandbox) -> None:
    out = InstructionParser.execute([
        "python scripts/actions.py definitely_not_a_command",
        "python scripts/actions.py status",
    ])
    assert len(out) == 2
    assert "unknown action" in out[0].lower()
    assert "tasks=" in out[1]          # 前一条失败不影响后一条


# ── 回复解析：截断容忍（2026-10-16 实测踩到）─────────────────

def test_parse_reads_complete_block() -> None:
    text = ("好的，我来导入。\n```sh\n"
            'python scripts/actions.py add_course --name "算法" --day 1 --weeks "1-16" --slots "1-2"\n'
            "```\n")
    assert InstructionParser.parse(text) == [
        'python scripts/actions.py add_course --name "算法" --day 1 --weeks "1-16" --slots "1-2"',
    ]


def test_parse_keeps_complete_lines_when_reply_is_truncated() -> None:
    """被输出上限截断（没有收尾 ```）时，已经写完的完整命令**仍然要执行**。

    旧实现要求必须有收尾围栏 → 整段丢弃 → 用户看到"AI 没反应"、数据一条没变，
    而且没有任何提示（真实故障）。
    """
    truncated = ("```sh\n"
                 'python scripts/actions.py add_course --name "课程1" --day 1 --weeks "1-16" --slots "1-2"\n'
                 'python scripts/actions.py add_course --name "课程2" --day 2 --weeks "1-16" --slots "3-4"\n'
                 "python scripts/actions.py add_course --name \"课程3\" --day 3 --weeks \"1-16\" --slots \"5-6\"")
    cmds = InstructionParser.parse(truncated)
    assert len(cmds) == 3, cmds
    assert all("scripts/actions.py add_course" in c for c in cmds)


def test_parse_ignores_prose_without_script_call() -> None:
    assert InstructionParser.parse("请提供课程名称、时间、周次，我来帮你导入。") == []
    assert InstructionParser.parse("```sh\nls -la\n```") == []


def test_looks_truncated_detects_unclosed_fence() -> None:
    from src.services.ai_service import _looks_truncated

    assert _looks_truncated("```sh\ncmd") is True
    assert _looks_truncated("```sh\ncmd\n```") is False
    assert _looks_truncated("普通文本") is False


# ── 超时与空回复 ────────────────────────────────────────────

def test_provider_sets_request_timeout() -> None:
    """不能沿用 SDK 默认的 10 分钟：端点卡住时用户会干等且毫无提示。"""
    from src.services.ai_service import AI_REQUEST_TIMEOUT, DeepSeekProvider

    provider = DeepSeekProvider("sk-test", "https://example.invalid/v1")
    assert provider._client.timeout == AI_REQUEST_TIMEOUT
    assert AI_REQUEST_TIMEOUT <= 180


def test_empty_reply_surfaces_a_hint(qapp, tmp_path) -> None:
    """空回复不能静默（界面一片空白 = 用户以为 AI 没反应）。"""
    from src.services.ai_service import AIService
    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager

    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    svc = AIService(settings, DataManager(tmp_path))
    seen: list[str] = []
    svc.response_received.connect(seen.append)

    svc._on_response("")
    assert seen and seen[0].strip(), "空回复必须给出可读提示"
