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

from helpers import read_json, run

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
    assert _continuation_nudge("", False, empty_retries=1) is None, "空回复只重试一次"
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
    """一直空回复不能空转：**只重试一次**，然后**明确报错**（不是"完成"）。

    实测教训：模型陷在思考里时，5 轮重试 = 用户白等三分半（43+41+43+44+45 秒）。
    ⚠ 报错而不是 `finished`：空回复此前会把**推理文本**当回答交给上层（含执行通道），
    现在只允许失败（2026-10-17）。
    """
    provider, results = _run(["", "", "", "", ""])

    assert len(provider.calls) == 2, "空回复只允许重试一次"
    assert results[-1][0] == "error", "连续空回复是失败，不是完成"
    assert "max_tokens" in results[-1][1], "报错要给出可操作的建议"


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


# ── update_course / update_item：只改显式传入的字段 ─────────

def test_update_course_only_changes_passed_fields(sandbox) -> None:
    """回归：`update_*` 不能被"注入的默认值"改掉没传的字段。

    2026-10-17 实测：`update_course --slots` 会把 parity 重置成 all、
    `update_item --location` 会把 quantity 重置成 1（后者是更早的隐患）。
    """
    run('add_course --name "算法" --day 1 --weeks "1-16" --slots "3-3" --parity odd')
    assert run('update_course --id "c_001" --slots "2-2"').startswith("OK")

    course = read_json(sandbox, "courses.json")["courses"][0]
    assert [(s["start"], s["end"]) for s in course["time_slots"]] == [(2, 2)]
    assert course["week_parity"] == "odd", "没传 --parity 不能重置"
    assert course["day_of_week"] == 1 and course["name"] == "算法"


def test_update_course_rejects_bad_slots_without_writing(sandbox) -> None:
    run('add_course --name "算法" --day 1 --slots "3-3"')
    out = run('update_course --id "c_001" --slots "9-9"')
    assert out.startswith("ERROR"), out
    assert read_json(sandbox, "courses.json")["courses"][0]["time_slots"][0]["start"] == 3


def test_update_item_keeps_quantity(sandbox) -> None:
    """回归：`update_item --location` 以前会把数量重置成默认的 1。"""
    run('add_item --name "纸巾" --quantity 5')
    assert run('update_item --id "i_001" --location "柜子"').startswith("OK")

    item = read_json(sandbox, "inventory.json")["items"][0]
    assert item["quantity"] == 5 and item["location"] == "柜子"


# ── Provider：推理内容抢救 / 少想多做 ───────────────────────

class _FakeMessage:
    def __init__(self, content: str, reasoning: str = "") -> None:
        self.content = content
        self.reasoning_content = reasoning


class _FakeResponse:
    def __init__(self, content: str, reasoning: str = "") -> None:
        self.choices = [type("C", (), {
            "message": _FakeMessage(content, reasoning), "finish_reason": "stop"})()]
        self.usage = None


class _FakeCompletions:
    def __init__(self, responses: list, fail_first: bool = False) -> None:
        self._responses = responses
        self._fail_first = fail_first
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self._fail_first and len(self.calls) == 1:
            raise RuntimeError("400 unsupported parameter: reasoning_effort")
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]


def _provider(responses: list, base: str = "https://opencode.ai/inference/go/openai/v1",
              fail_first: bool = False) -> tuple:
    from src.services.ai_service import DeepSeekProvider

    p = DeepSeekProvider("sk-test", base)
    fake = type("Client", (), {"chat": type("Chat", (), {
        "completions": _FakeCompletions(responses, fail_first)})()})()
    p._client = fake
    return p, fake.chat.completions


def test_content_empty_does_not_leak_reasoning() -> None:
    """content 为空时**不得**把推理当回答 —— 推理里的命令会被解析器真的执行。

    2026-10-17 之前这里是"用推理文本抢救"，等于把模型的**思考过程**（常含被否决
    或仅作举例的命令）送进 `InstructionParser` 执行。`actions.py` 只校验格式合法、
    校验不了**意图**，所以推理必须止步在显示层之外。
    """
    from src.services.ai_service import InstructionParser

    p, _calls = _provider([_FakeResponse("", f"```sh\n{TASK_CMD}\n```")])
    out = p.chat("sys", [{"role": "user", "content": "x"}], "m", 100, 0.3)
    assert out == "", "空 content 必须返回空，不得回落到推理文本"
    assert InstructionParser.parse(out) == [], "推理文本不得进入执行通道"


def test_worker_reports_empty_reply_as_error(qapp) -> None:
    """整条链路：content 空 + 推理里带命令 → 一条都不执行，且走 error 而不是"完成"。"""
    from src.services.ai_service import AIWorker

    p, _calls = _provider([_FakeResponse("", f"```sh\n{TASK_CMD}\n```")])
    worker = AIWorker(p, "m", "sys", [{"role": "user", "content": "x"}])
    errors: list[str] = []
    finished: list[str] = []
    worker.error.connect(errors.append)
    worker.finished.connect(finished.append)
    worker.finished_with_instructions.connect(lambda text, ins: finished.append(text))

    worker.run()

    assert errors, "空回复必须走 error（明确失败）"
    assert not finished, "空回复不得走 finished/finished_with_instructions"


def test_reasoning_effort_sent_to_opencode() -> None:
    from src.services.ai_service import REASONING_EFFORT

    p, calls = _provider([_FakeResponse("好的")])
    p.chat("sys", [{"role": "user", "content": "x"}], "m", 100, 0.3)
    assert calls.calls[0]["reasoning_effort"] == REASONING_EFFORT


def test_reasoning_effort_dropped_when_rejected() -> None:
    """端点不认这个参数 → 去掉重试一次（不能因此让 AI 完全不可用）。"""
    p, calls = _provider([_FakeResponse("好的")], fail_first=True)
    out = p.chat("sys", [{"role": "user", "content": "x"}], "m", 100, 0.3)
    assert out == "好的"
    assert len(calls.calls) == 2 and "reasoning_effort" not in calls.calls[1]


def test_reasoning_effort_not_sent_to_other_endpoints() -> None:
    p, calls = _provider([_FakeResponse("好的")], base="https://api.deepseek.com")
    p.chat("sys", [{"role": "user", "content": "x"}], "m", 100, 0.3)
    assert "reasoning_effort" not in calls.calls[0]
