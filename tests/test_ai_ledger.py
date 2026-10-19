"""动作账本 + 错误分类恢复（专项审查 §3.1 / §3.4 / §2.3）的回归。

账本要回答的是"**哪些目标**达成了"，不是"成功了几条命令" ✗；
恢复要把 ERROR **分类**，连"该做什么 / 不能做什么"一起回喂模型 ——
α 测试里真实出现过三种猜法：原样重发、猜 id、自己加 `--yes` ✗。
"""

from src.services import ai_ledger, ai_verify

# ── 账本 ────────────────────────────────────────────────────

def test_ledger_counts_by_state_not_by_command_count() -> None:
    led = ai_ledger.Ledger()
    led.record("c1", ai_ledger.VERIFIED)
    led.record("c2", ai_ledger.VERIFIED)
    led.record("c3", ai_ledger.NOOP)
    led.record("c4", ai_ledger.MISMATCH)
    assert led.counts() == {ai_ledger.VERIFIED: 2, ai_ledger.NOOP: 1, ai_ledger.MISMATCH: 1}
    assert "验收通过 2" in led.summary() and "没达到预期 1" in led.summary()


def test_ledger_is_clean_only_without_mismatch_failure_or_block() -> None:
    led = ai_ledger.Ledger()
    led.record("c1", ai_ledger.VERIFIED)
    led.record("c2", ai_ledger.NOOP)
    led.record("c3", ai_ledger.UNVERIFIED)
    assert led.is_clean(), "未验收不算「出错」（它只是没验收器）"
    led.record("c4", ai_ledger.MISMATCH)
    assert not led.is_clean()


def test_ledger_summary_is_empty_without_goals() -> None:
    assert ai_ledger.Ledger().summary() == ""


# ── 分类恢复（关键词取自 scripts/ 里真实出现的 ERROR 文案）──

def test_classify_error_covers_the_real_error_texts() -> None:
    cases = {
        "ERROR 未知参数 --foo（update_item 只接受：--id）": "参数不合法",
        "ERROR item not found: i_009": "对象不存在",
        "ERROR 没有 alpha-2026 的备份（先用 list_backups 查看）": "对象不存在",
        "ERROR 已有同名同位置且无区别的物品 i_003（纸巾 @书架3）": "对象已存在",
        "ERROR 保存被拒（数据被其它程序改过）": "保存冲突",
        "ERROR restore 需要显式 --yes（手动恢复入口，避免误覆盖）": "需要用户授权",
    }
    for text, expected in cases.items():
        assert ai_ledger.classify_error(text)[0] == expected, text


def test_unknown_error_is_not_forced_into_a_class() -> None:
    name, should, _ = ai_ledger.classify_error("ERROR 某种没见过的失败")
    assert name == "未分类" and should == "", "归不到类就明说，别硬套"


def test_recovery_note_skips_ok_and_unclassified() -> None:
    assert ai_ledger.recovery_note(["OK add_item i_001"]) == ""
    assert ai_ledger.recovery_note(["ERROR 某种没见过的失败"]) == ""
    note = ai_ledger.recovery_note(["OK x", "ERROR item not found: i_009"])
    assert "对象不存在" in note and "不要" in note
    assert note.count("[对象不存在]") == 1, "同类建议去重"


# ── 接进 worker（从真实入口）────────────────────────────────

def _run_text(replies: list[str], dm=None) -> list[str]:
    from src.services.ai_service import AIWorker

    class _Stub:
        def __init__(self, script: list[str]) -> None:
            self._script, self.calls = script, 0

        def chat(self, **_kw: object) -> str:
            text = self._script[min(self.calls, len(self._script) - 1)]
            self.calls += 1
            return text

    worker = AIWorker(_Stub(replies), "stub", "s", [{"role": "user", "content": "x"}], dm, None)
    out: list[str] = []
    worker.finished_with_instructions.connect(lambda t, _i: out.append(t))
    worker.finished.connect(out.append)
    worker.error.connect(out.append)
    worker.run()
    return out


BAD = 'python scripts/actions.py add_item --name "纸巾" --quantity -1'


def test_worker_feeds_recovery_advice_back_to_the_model(qapp, sandbox) -> None:
    """⭐ 命令报错时，回喂给模型的不只是 ERROR 原文，还要有"下一步怎么办"。"""
    from src.services.ai_service import AIWorker
    from src.services.data_manager import DataManager

    dm = DataManager(sandbox)
    worker = AIWorker(None, "m", "", [], dm, None)
    text, *_ = worker._run_commands([BAD], {})
    assert "[恢复建议]" in text and "参数不合法" in text, text


def test_worker_reports_the_ledger_when_something_failed(qapp, sandbox) -> None:
    """⭐ 最终文本要带账本（按状态）—— 只有"不干净"时才给用户看。"""
    out = _run_text([f"```sh\n{BAD}\n```", "记好了"], dm=None)
    assert any("本次账本" in t for t in out), out
    assert any("执行失败" in t for t in out), out


def test_worker_stays_quiet_when_everything_is_clean(qapp, sandbox) -> None:
    """全绿时不加账本那行（别给用户添噪）。"""
    good = 'python scripts/actions.py add_item --name "抽纸" --quantity 2'
    out = _run_text([f"```sh\n{good}\n```", "记好了"], dm=None)
    assert not any("本次账本" in t for t in out), out


def test_verify_and_ledger_use_the_same_state_names() -> None:
    """⚠ 验收器与账本的状态字符串必须**同一套**（否则账本统计会漏）。"""
    assert ai_verify.VERIFIED == ai_ledger.VERIFIED
    assert ai_verify.NOOP == ai_ledger.NOOP
    assert ai_verify.MISMATCH == ai_ledger.MISMATCH
    assert ai_verify.FAILED == ai_ledger.FAILED
    assert ai_verify.UNVERIFIED == ai_ledger.UNVERIFIED
