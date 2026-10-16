"""AIWorker 的「没反应」自愈：空回复重试、截断分批。

2026-10-16 用户报"模型连续返回空内容、没有自动分批处理"：
- 空回复（`finish_reason=length`，推理把输出预算吃光）在旧代码里等于**直接结束**，
  界面只剩空白；
- 截断检测只看代码围栏，空回复（0 个围栏）压根不算"截断" → 分批逻辑从不触发。
现在两条路都会**要求模型继续**，最多续到 5 轮上限。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import read_json

from src.services.ai_service import AIWorker, _continuation_nudge, _looks_truncated

TASK_CMD = 'python scripts/actions.py add_task --title "背包问题" --due 2026-10-20'


class _StubProvider:
    """按脚本逐轮返回文本；记录每轮收到的 max_tokens。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls: list[dict] = []

    def chat(self, system_prompt: str, messages: list[dict], model: str,
             max_tokens: int, temperature: float) -> str:
        self.calls.append({"max_tokens": max_tokens, "messages": len(messages)})
        idx = min(len(self.calls) - 1, len(self._replies) - 1)
        return self._replies[idx]


def _run(replies: list[str], settings=None) -> tuple[_StubProvider, list]:
    provider = _StubProvider(replies)
    worker = AIWorker(provider=provider, model="stub", system_prompt="s",
                      messages=[{"role": "user", "content": "记个作业"}],
                      settings=settings)
    results: list = []
    worker.finished_with_instructions.connect(lambda t, i: results.append(("instr", i)))
    worker.finished.connect(lambda t: results.append(("text", t)))
    worker.error.connect(lambda e: results.append(("error", e)))
    worker.run()
    return provider, results


# ── 续跑判定 ────────────────────────────────────────────────

def test_continuation_nudge_cases() -> None:
    assert _continuation_nudge("", False), "空回复要重来"
    assert _continuation_nudge("   \n ", False), "只有空白也算空"
    assert _continuation_nudge("```sh\ncmd", True), "截断要分批继续"
    # 正常提问（模型在要信息）**不**续跑，否则会把问题刷 5 遍
    assert _continuation_nudge("请提供课程名称与周次", False) is None


def test_looks_truncated_only_counts_fences() -> None:
    assert _looks_truncated("```sh\ncmd") is True
    assert _looks_truncated("```sh\ncmd\n```") is False
    assert _looks_truncated("") is False          # 空回复不算"截断"


# ── 空回复 → 重试 → 执行 ────────────────────────────────────

def test_worker_retries_on_empty_reply(qapp, sandbox) -> None:
    """空回复 → 要求模型继续 → 第二轮拿到命令并**真的执行**。"""
    provider, results = _run(["", f"```sh\n{TASK_CMD}\n```", "好的，已经记上了"])

    assert len(provider.calls) == 3, "空回复必须触发重试（第三轮是收尾说明）"
    assert results and results[-1][0] == "instr" and len(results[-1][1]) == 1
    assert read_json(sandbox, "tasks.json")["tasks"][0]["title"] == "背包问题"


def test_worker_stops_after_repeated_empty_replies(qapp, sandbox) -> None:
    """一直空回复也不能死循环：续到轮数上限就结束，并把空内容交给上层提示。"""
    provider, results = _run(["", "", "", "", ""])

    assert len(provider.calls) == 5, "最多 5 轮"
    assert results[-1][0] == "text" and results[-1][1].strip() == ""


# ── 截断 → 分批继续 ─────────────────────────────────────────

def test_worker_asks_to_batch_when_truncated(qapp, sandbox) -> None:
    """被截断的块：完整行先执行，然后要求模型分批继续。"""
    provider, results = _run([f"```sh\n{TASK_CMD}", f"```sh\n{TASK_CMD}\n```", "都记上了"])

    assert len(provider.calls) == 3
    assert results[-1][0] == "instr"
    assert len(read_json(sandbox, "tasks.json")["tasks"]) == 2


# ── 输出预算 ────────────────────────────────────────────────

def test_worker_reads_max_tokens_from_settings(qapp, tmp_path) -> None:
    """输出预算读设置（默认 8192，旧值 4096 会被推理吃光）。"""
    from src.services.settings_manager import SettingsManager

    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    provider, _ = _run(["你好"], settings=settings)
    assert provider.calls[0]["max_tokens"] == 8192

    settings.set("AI", "max_tokens", "2048")
    provider2, _ = _run(["你好"], settings=settings)
    assert provider2.calls[0]["max_tokens"] == 2048
