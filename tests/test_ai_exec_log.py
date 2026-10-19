"""执行日志与聊天记录**分开**（专项审查 §2.4 / A5 / A6）。

"聊天记录不等于执行日志"：用户说"继续 / 撤销刚才那条"时，系统要知道**实际做过什么** ——
而 `_auto_compress()` 会把前文替换成一句概括 ✗，目标和约束都可能丢 ✗。

所以账本走**自己的通道**（`AIWorker.ledger_ready` → `AIService._exec_log`），
压缩历史**带不走它** ✓，并在下一次请求里作为**事实**注入提示词 ✓。
"""

from src.services.ai_service import EXEC_LOG_KEEP, AIService
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager


def _service(tmp_path) -> AIService:
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    return AIService(settings, DataManager(tmp_path))


def test_exec_log_survives_history_compression(qapp, tmp_path) -> None:
    """⭐ 压缩聊天历史之后，执行日志必须**原样还在**。"""
    svc = _service(tmp_path)
    svc._on_ledger("本次账本：验收通过 1 · 没达到预期 1")
    for i in range(20):
        svc._history.append({"role": "user", "content": f"第 {i} 句"})

    svc._auto_compress()

    assert len(svc._history) <= 17, "历史确实被压缩了（这条测试才有意义）"
    assert svc._exec_log == ["本次账本：验收通过 1 · 没达到预期 1"]


def test_exec_log_is_injected_into_the_prompt_as_fact(qapp, tmp_path) -> None:
    """⭐ 下一次请求的提示词里要有"最近实际执行过的动作"（且标明是**事实**）。"""
    svc = _service(tmp_path)
    svc._on_ledger("本次账本：验收通过 2")
    prompt = svc._build_system_prompt()
    assert "最近实际执行过的动作" in prompt
    assert "验收通过 2" in prompt
    assert "事实" in prompt, "要告诉模型这是事实，不是它的回忆"


def test_exec_log_keeps_only_the_last_few(qapp, tmp_path) -> None:
    svc = _service(tmp_path)
    for i in range(EXEC_LOG_KEEP + 4):
        svc._on_ledger(f"本次账本：第 {i} 次")
    assert len(svc._exec_log) == EXEC_LOG_KEEP
    assert svc._exec_log[-1] == f"本次账本：第 {EXEC_LOG_KEEP + 3} 次"


def test_clear_history_also_clears_the_exec_log(qapp, tmp_path) -> None:
    """用户清空对话 = 换一个话题，执行日志也该跟着清（别拿旧动作误导）。"""
    svc = _service(tmp_path)
    svc._on_ledger("本次账本：验收通过 1")
    svc.clear_history()
    assert svc._exec_log == []
    assert "最近实际执行过的动作" not in svc._build_system_prompt()


def test_worker_emits_the_ledger_on_its_own_signal(qapp, sandbox) -> None:
    """⭐ 账本走**独立信号**（不是塞进聊天文本）—— 从 worker 的真实入口验。"""
    from src.services import ai_ledger
    from src.services.ai_service import AIWorker

    dm = DataManager(sandbox)
    worker = AIWorker(None, "m", "", [], dm, None)
    seen: list[str] = []
    worker.ledger_ready.connect(seen.append)

    text, *_ = worker._run_commands([], {})
    worker._report([], False, "记好了", [], True, 0, ai_ledger.Ledger())
    assert text == "" and seen == [], "没有写命令就不发账本（别添噪）"

    worker._run_commands(['python scripts/actions.py add_item --name "抽纸" --quantity 2'], {})
    worker._report([], True, "记好了", [], True, 1, _ledger_with_one())
    assert seen and seen[-1].startswith("本次账本")


def _ledger_with_one() -> object:
    from src.services import ai_ledger

    led = ai_ledger.Ledger()
    led.record("c1", ai_ledger.VERIFIED)
    return led
