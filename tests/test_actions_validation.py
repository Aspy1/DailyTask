"""`scripts/actions.py` 的**输入校验 / 备份 / 恢复**守卫（2026-10-16 硬化后新增）。

背景：AI 会直接调用 `scripts/actions.py`，而旧实现**完全不校验**参数 ——
`--day 9`、`--slots 3-99`、`2026-02-30`、拼错的 `--titel` 都会直接写进数据文件。
这一批测试把「非法输入绝不落盘」钉死，并保证备份/恢复真的能回滚。
"""

import argparse
from pathlib import Path

import pytest
from helpers import read_json, run

import scripts.actions as actions
import scripts.actions_core as core

# ── 1) 非法输入：拒绝，且一个字节都不改 ─────────────────────

ILLEGAL = [
    ('add_course --name 测试 --day 9 --slots "3-4"', "星期几越界"),
    ('add_course --name 测试 --day 1 --slots "3-99"', "节次越界"),
    ('add_course --name 测试 --day 1 --weeks "9-3"', "周次区间反了"),
    ("add_task --title 测试 --due 2026-02-30", "不存在的日期"),
    ("add_task --title 测试 --due 2026-10-20 --titel 打错", "参数名拼错"),
    ("add_habit --name 跑步 --schedule weekly/9", "星期几越界"),
    ("add_item --name 纸巾 --quantity -1", "负数数量"),
    ("log_habit --id 乱码", "ID 格式非法"),
    ("add_expense --amount -5 --category food", "负数金额"),
    ("add_expense --amount 12 --category 不存在的分类", "未知分类"),
    ("add_plan --date 2026-13-01 --title 测试", "月份非法"),
    ("delete_plan --date 2026-10-16 --index abc", "下标不是整数"),
]


@pytest.mark.parametrize(("cmd", "why"), ILLEGAL)
def test_illegal_input_is_refused_without_writing(sandbox, cmd, why) -> None:
    before = {p.as_posix(): p.read_bytes() for p in Path(sandbox).rglob("*.json")}
    out = run(f"python scripts/actions.py {cmd}")
    assert out.startswith("ERROR"), f"{why}：应被拒绝，实际 {out!r}"
    after = {p.as_posix(): p.read_bytes() for p in Path(sandbox).rglob("*.json")}
    assert after == before, f"{why}：非法输入不允许改动任何数据文件"


def test_unknown_action_is_refused(sandbox) -> None:
    assert run("python scripts/actions.py 不存在的命令").startswith("ERROR")


# ── 2) 备份 / 恢复 ─────────────────────────────────────────

def _backups(sandbox, name: str) -> list[Path]:
    return sorted((Path(sandbox) / "backup" / "actions").glob(f"{name}.*.json"))


def test_write_creates_backup_and_restore_rolls_back(sandbox) -> None:
    assert run('add_item --name "纸巾" --quantity 3').startswith("OK")
    assert len(read_json(sandbox, "inventory.json")["items"]) == 1

    assert run('add_item --name "牙膏" --quantity 1').startswith("OK")
    assert _backups(sandbox, "inventory.json"), "写入前应自动留存备份"
    assert len(read_json(sandbox, "inventory.json")["items"]) == 2

    out = run('restore --name "inventory.json" --yes')
    assert out.startswith("OK"), out
    assert len(read_json(sandbox, "inventory.json")["items"]) == 1, "恢复应回到上一版"
    # 恢复前会把"当前版本"再备份一次，避免恢复错方向
    assert len(_backups(sandbox, "inventory.json")) >= 2


def test_restore_requires_explicit_yes(sandbox) -> None:
    """restore 是给用户的手动入口：AI 漏了 --yes 必须被拦。"""
    run('add_item --name "纸巾" --quantity 3')
    run('add_item --name "牙膏" --quantity 1')
    out = run('restore --name "inventory.json"')
    assert out.startswith("ERROR") and "--yes" in out
    assert len(read_json(sandbox, "inventory.json")["items"]) == 2, "被拒时不得改动数据"


def test_list_backups_reports_files(sandbox) -> None:
    run('add_item --name "纸巾" --quantity 3')
    run('add_item --name "牙膏" --quantity 1')
    out = run('list_backups --name "inventory.json"')
    assert "inventory.json." in out, out


def test_backup_rotation_keeps_limit(sandbox) -> None:
    """轮转：同名文件只保留 max_backups 份（设置里的 Backup.max_backups，默认 10）。"""
    for i in range(13):
        run(f'add_item --name "物品{i}" --quantity 1')
    assert len(_backups(sandbox, "inventory.json")) <= core.DEFAULT_MAX_BACKUPS


# ── 3) 结构守卫：坏结构不许落盘 ─────────────────────────────

def test_payload_guard_rejects_broken_structure(sandbox) -> None:
    with pytest.raises(core.ActionError):
        core.save("expenses.json", {"records": "不是数组"})
    with pytest.raises(core.ActionError):
        core.save("habits.json", {"plans": []})
    assert not (Path(sandbox) / "expenses.json").exists()


def test_load_reports_corrupt_file_instead_of_emptying(sandbox) -> None:
    """文件坏了要**明说**（否则 AI 会当成空数据继续写 = 清空用户数据）。"""
    bad = Path(sandbox) / "inventory.json"
    bad.write_text('{"items": [}', encoding="utf-8")
    with pytest.raises(core.ActionError):
        core.load("inventory.json")
    out = run('add_item --name "纸巾" --quantity 1')
    assert out.startswith("ERROR") and "restore" in out
    assert bad.read_text(encoding="utf-8") == '{"items": [}', "坏文件不得被覆盖"


# ── 4) 记账 / 存钱（新增能力）──────────────────────────────

def test_add_expense_writes_expected_shape(sandbox) -> None:
    out = run('add_expense --amount 12.5 --category food --note "午饭"')
    assert out.startswith("OK add_expense"), out
    rec = read_json(sandbox, "expenses.json")["records"][-1]
    assert rec["amount"] == 12.5
    assert rec["category"] == "food"
    assert rec["note"] == "午饭"
    assert rec["id"] == "e_001"
    assert rec["date"], "应带日期（默认今天）"


def test_add_expense_accepts_chinese_category(sandbox) -> None:
    out = run('add_expense --amount 8 --category 餐饮')
    assert out.startswith("OK"), out
    assert read_json(sandbox, "expenses.json")["records"][-1]["category"] == "food"


def test_add_saving_writes_daily_logs(sandbox) -> None:
    out = run('add_saving --amount 30 --note "自带午饭"')
    assert out.startswith("OK add_saving"), out
    savings = read_json(sandbox, "daily_logs.json")["savings"]
    entries = next(iter(savings.values()))
    assert entries[0]["amount"] == 30 and entries[0]["note"] == "自带午饭"


def test_expense_summary_and_delete(sandbox) -> None:
    run("add_expense --amount 12.5 --category food")
    run("add_expense --amount 7.5 --category transport")
    run("add_saving --amount 5")

    out = run("expense_summary")
    assert "20.00" in out and "餐饮" in out, out
    assert "今日存钱 ¥5.00" in out, out

    rid = read_json(sandbox, "expenses.json")["records"][0]["id"]
    assert run(f'delete_expense --id "{rid}"').startswith("OK")
    assert len(read_json(sandbox, "expenses.json")["records"]) == 1


# ── 5) 参数白名单与 CLI 不漂移 ──────────────────────────────

def test_allowed_options_matches_cli_parser() -> None:
    """`ALLOWED_OPTIONS`（进程内执行器用）必须与 argparse 子命令完全一致。

    两边任何一处新增/改名而另一处忘了改，AI 就会遇到"能跑但参数被拒"或
    "参数被静默忽略"——都很难查。
    """
    parser = actions.build_parser()
    sub = next(a for a in parser._actions
               if isinstance(a, argparse._SubParsersAction))
    for name, sp in sub.choices.items():
        opts = {o[2:].replace("-", "_")
                for a in sp._actions for o in a.option_strings
                if o.startswith("--") and o != "--help"}
        assert opts == core.ALLOWED_OPTIONS[name], \
            f"{name} 参数漂移：{opts ^ core.ALLOWED_OPTIONS[name]}"


def test_every_handler_has_allowed_options() -> None:
    """每个命令都必须登记参数白名单（否则未知参数检查会失效）。"""
    assert set(actions.HANDLERS) <= set(core.ALLOWED_OPTIONS)
