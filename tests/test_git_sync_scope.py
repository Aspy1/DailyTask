"""Git 同步范围（审查 2026-10-17 #4）。

两件事必须钉住：

1. **同步清单不漂移**：`DATA_FILES` / `DATA_DIRS` 必须覆盖 `DataManager` 的每个模型
   文件 —— 新增数据文件时忘了加清单，数据会**悄悄**不同步（比报错更糟）。
2. **手动同步不再扫全仓**：旧实现 `git add -A` 会把开发中的源码一起提交，
   而"没东西可提交"时又直接 `return`，导致 push 根本不执行。
"""

import pytest

from src.services.data_manager import DataManager
from src.services.git_sync import (
    DATA_DIRS,
    DATA_FILES,
    build_sync_commands,
    classify_sync,
    is_nothing_to_commit,
    is_up_to_date,
)


def test_manifest_covers_every_model(tmp_path, qapp) -> None:
    """清单必须覆盖 `DataManager._models()` 的每个文件（含按学期的三个）。"""
    dm = DataManager(tmp_path)
    covered = set(DATA_FILES) | set(DATA_DIRS)
    for model, name in dm._models():
        rel = model.file_path.relative_to(tmp_path).as_posix()
        top = rel.split("/")[0]
        assert rel in covered or top in covered, (
            f"{name}（{rel}）不在同步清单里 —— 加进 `git_sync.DATA_FILES`/`DATA_DIRS`")


def test_add_is_scoped_to_explicit_data_paths() -> None:
    """`git add` 必须限定在 `data/` 下，且用 `--` 显式列路径（禁止扫全仓）。"""
    add = build_sync_commands("data", "msg")[0]
    assert add[:3] == ["git", "add", "-A"], add
    assert "--" in add, "必须用 `--` 限定显式路径"
    assert all(p.startswith("data/") for p in add[add.index("--") + 1:]), add
    # 按学期的整个目录要带上（不只当前学期）
    assert "data/semesters" in add


def test_push_stays_last() -> None:
    """push 必须留在最后：即使"没东西可提交"，之前攒下的提交也要推上去。"""
    cmds = build_sync_commands("data", "msg")
    assert " ".join(cmds[-1]) == "git push"


@pytest.mark.parametrize(("detail", "expected"), [
    ("git commit -m x: nothing to commit, working tree clean", True),
    ("git commit -m x: nothing added to commit but untracked files present", True),
    ("git commit -m x: fatal: not a git repository (or any of the parent directories)", False),
    ("git commit -m x: error: pathspec 'data/x.json' did not match any file(s)", False),
])
def test_is_nothing_to_commit(detail: str, expected: bool) -> None:
    assert is_nothing_to_commit(detail) is expected


@pytest.mark.parametrize(("output", "expected"), [
    ("Everything up-to-date\n", True),
    ("To github.com:Aspy1/DailyTask.git\n   abc..def  master -> master\n", False),
])
def test_is_up_to_date(output: str, expected: bool) -> None:
    assert is_up_to_date(output) is expected


def test_classify_sync() -> None:
    assert classify_sync(pushed=True) == "pushed"
    assert classify_sync(pushed=False) == "up-to-date"
