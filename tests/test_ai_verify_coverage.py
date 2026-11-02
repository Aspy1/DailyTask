"""验收**字段覆盖**（H5/P1）：`checked/total` 必须真实，界面不能笼统说"验收通过"。

判据来自论文映射（`docs/ai-harness-audit/findings.csv` H5）：
- verifier 只核对了命令效果的一部分时，必须照实说「n/m 字段」；
- 没有验收器的命令（如 `restore`）必须显示「未核对」，不能算通过；
- `unverified` 的 checked 必须是 0（没核对就别说核对了 1 个字段）。
"""

import json

from src.services import ai_policy, ai_verify
from src.services import ai_verify_coverage as coverage


def _seed_inventory(sandbox, items: list[dict]) -> None:
    (sandbox / "inventory.json").write_text(
        json.dumps({"_version": 1, "items": items, "locations": []}, ensure_ascii=False),
        encoding="utf-8")


def test_add_item_reports_name_but_not_quantity() -> None:
    """`add_item` 只核对 name → 传了 name+quantity 时是 1/2，不是"全部通过"。"""
    checked, total, fields = coverage.coverage_of("add_item", {"name": "纸巾", "quantity": 2})
    assert (checked, total) == (1, 2), (checked, total)
    assert fields == ("name",)


def test_fields_that_were_not_passed_are_not_counted_in_the_denominator() -> None:
    """没传的字段不会被改，也就不该出现在分母里（否则覆盖率永远难看）。"""
    assert coverage.coverage_of("add_item", {"name": "纸巾"}) == (1, 1, ("name",))


def test_implicit_effects_are_counted_even_without_arguments() -> None:
    """完成/删除没有对应参数，但一定改变状态 —— 分母要算上。"""
    assert coverage.coverage_of("complete_task", {}) == (1, 1, ("status",))
    assert coverage.coverage_of("delete_item", {}) == (1, 1, ("exists",))


def test_replace_plans_counts_each_plan_subfield() -> None:
    """⭐ `--plans` 不是"1 个字段"：分母是载荷里实际出现的子字段。"""
    raw = json.dumps([{"title": "复习", "time_slot": 2, "note": ""}], ensure_ascii=False)
    checked, total, fields = coverage.coverage_of("replace_plans", {"plans": raw})
    assert (checked, total) == (3, 3), (checked, total)
    assert fields == ("note", "time_slot", "title")


def test_replace_plans_slot_mismatch_is_not_verified(sandbox) -> None:
    """⭐ 标题相同、time_slot 不同 → 不能报 VERIFIED 1/1（H5 的 false success）。"""
    (sandbox / "daily_logs.json").write_text(json.dumps({
        "_version": 4,
        "logs": {},
        "plans": {"2026-11-02": [{"title": "复习", "time_slot": 1}]},
    }, ensure_ascii=False), encoding="utf-8")
    command = ('python scripts/actions.py replace_plans --date 2026-11-02 '
               '--plans \'[{"title":"复习","time_slot":2}]\'')
    before = ai_verify.observe(command, sandbox)
    verdict = coverage.check_ex(command, before, "OK replace_plans 2026-11-02 | 1 items", sandbox)
    assert verdict.state == ai_verify.MISMATCH
    assert verdict.total == 2 and verdict.checked == 2
    assert "time_slot" in verdict.detail
    assert not verdict.resolves


def test_replace_plans_matching_subfields_is_verified(sandbox) -> None:
    (sandbox / "daily_logs.json").write_text(json.dumps({
        "_version": 4,
        "logs": {},
        "plans": {"2026-11-02": [{"title": "复习", "time_slot": 2, "type": "custom"}]},
    }, ensure_ascii=False), encoding="utf-8")
    command = ('python scripts/actions.py replace_plans --date 2026-11-02 '
               '--plans \'[{"title":"复习","time_slot":2,"type":"custom"}]\'')
    before = ai_verify.observe(command, sandbox)
    verdict = coverage.check_ex(command, before, "OK replace_plans 2026-11-02 | 1 items", sandbox)
    assert verdict.state == ai_verify.VERIFIED
    assert (verdict.checked, verdict.total) == (3, 3)
    assert "逐字段核对" in verdict.detail


def test_restore_has_no_verifier_and_no_coverage() -> None:
    """`restore` 不在 `_CHECKS` 里 → 必须显示"未核对"，而不是假装有分母。"""
    assert coverage.coverage_of("restore", {"name": "inventory.json"}) == (0, 0, ())
    verdict = coverage.check_ex(
        'python scripts/actions.py restore --name "inventory.json" --yes',
        {}, "OK restore inventory.json", None)
    assert verdict.state == ai_verify.UNVERIFIED
    assert verdict.checked == 0 and verdict.total == 0
    assert "未核对" in verdict.render()


def test_false_success_is_not_reported_as_verified(sandbox) -> None:
    """⭐ 命令回 OK 但没有真的写入 → 验收必须 MISMATCH，不能"通过"。"""
    _seed_inventory(sandbox, [])
    before = ai_verify.observe('python scripts/actions.py add_item --name "牙膏"', sandbox)
    verdict = coverage.check_ex(
        'python scripts/actions.py add_item --name "牙膏" --quantity 2',
        before, "OK add_item i_001", sandbox)
    assert verdict.state == ai_verify.MISMATCH
    assert verdict.partial and verdict.coverage_text() == "（1/2 字段）"


def test_partial_success_renders_the_real_coverage(sandbox) -> None:
    """写入成功但只核对了 name → 界面照实说 1/2。"""
    _seed_inventory(sandbox, [])
    before = ai_verify.observe('python scripts/actions.py add_item --name "牙膏"', sandbox)
    _seed_inventory(sandbox, [{"id": "i_001", "name": "牙膏", "quantity": 2}])
    verdict = coverage.check_ex(
        'python scripts/actions.py add_item --name "牙膏" --quantity 2',
        before, "OK add_item i_001", sandbox)
    assert verdict.state == ai_verify.VERIFIED
    assert (verdict.checked, verdict.total) == (1, 2)
    assert "只核对了 1/2 字段" in verdict.render()


def test_every_write_operation_has_a_coverage_denominator() -> None:
    """新增写命令必须登记"会改哪些字段"，否则覆盖度会静默变成 0/0。"""
    writes = {op for op, level in ai_policy.OP_LEVEL.items()
              if level in (ai_policy.LOW_WRITE, ai_policy.HIGH_WRITE)}
    registered = set(coverage._EFFECT_FIELDS) | set(coverage._IMPLICIT_FIELDS)
    missing = sorted(writes - registered)
    assert not missing, f"这些写命令没有覆盖度登记：{missing}"


def test_verified_fields_are_a_subset_of_effect_fields() -> None:
    """分子不能出现在命令根本不会改的字段上（否则就是虚报覆盖）。"""
    for operation, verified in coverage._VERIFIED_FIELDS.items():
        effects = set(coverage._EFFECT_FIELDS.get(operation, ()))
        effects |= set(coverage._IMPLICIT_FIELDS.get(operation, ()))
        assert set(verified) <= effects, (operation, set(verified) - effects)


def test_summary_includes_checked_over_total() -> None:
    verdicts = [coverage.Verdict(ai_verify.VERIFIED, "「牙膏」在清单里", 1, 2, ("name",))]
    text = coverage.summarize_verdicts(verdicts)
    assert "[验收]" in text and "（1/2 字段）" in text
