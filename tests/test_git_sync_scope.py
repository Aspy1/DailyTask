"""Git 同步范围与**真实集成**（审查 2026-10-17 #4 / #2 / #6）。

四件事：

1. **同步清单不漂移**：数据文件必须都在数据目录下（目录级暂存才覆盖得到）；
2. **不夹带已暂存的源码**：普通 `commit` 会提交整个暂存区 → 必须 `commit --only`；
3. **删除也要同步**：只挑"存在的文件"会漏掉已跟踪文件的删除；
4. 状态判定（没东西可提交 / 已经是最新）是纯函数。

第 2、3 条用**真实临时仓库 + 本地裸仓库**跑 —— 纯函数测不到 git 的真实行为
（前一轮就是靠真跑才发现 `git add` 对不存在路径会 fatal、push 的 up-to-date 走 stderr）。
"""

import subprocess
from pathlib import Path

import pytest

from src.services.data_manager import DataManager
from src.services.git_sync import (
    DATA_DIRS,
    DATA_FILES,
    PRIVATE_FILES,
    _GitWorker,
    build_sync_commands,
    classify_sync,
    is_nothing_to_commit,
    is_up_to_date,
)


def test_manifest_covers_every_model(tmp_path, qapp) -> None:
    """每个模型文件要么在**同步清单**里、要么在**私有清单**里（不能"谁都没登记"）。

    漏登记比报错更糟：该同步的会**悄悄**不同步，该私有的会**悄悄**被推上 GitHub。
    """
    dm = DataManager(tmp_path)
    covered = set(DATA_FILES) | set(DATA_DIRS) | set(PRIVATE_FILES)
    for model, name in dm._models():
        rel = model.file_path.relative_to(tmp_path).as_posix()
        top = rel.split("/")[0]
        assert rel in covered or top in covered, (
            f"{name}（{rel}）不在清单里 —— 该同步的加进 `git_sync.DATA_FILES`/`DATA_DIRS`，"
            f"私有的加进 `PRIVATE_FILES`")


def test_private_files_are_gitignored() -> None:
    """私有清单里的每一项都必须被 `.gitignore` 挡住。

    否则哪天一次 `git add -A` 就把手机号这类 PII 推进仓库了。
    """
    root = Path(__file__).resolve().parent.parent
    ignored = (root / ".gitignore").read_text(encoding="utf-8")
    for rel in PRIVATE_FILES:
        top = rel.split("/")[0]
        assert f"data/{top}/" in ignored or f"data/{rel}" in ignored, (
            f"{rel} 没被 .gitignore 挡住 —— 这类私有数据会被推进仓库")


def test_add_and_commit_are_scoped_to_data_dir() -> None:
    """`add` 与 `commit` 都必须限定在数据目录下（禁止扫全仓、禁止提交整个暂存区）。"""
    add, commit, push = build_sync_commands("data", "msg")
    assert add[:4] == ["git", "add", "-A", "--"], add
    assert add[4] == "data"
    assert commit[:3] == ["git", "commit", "--only"], commit
    assert "--" in commit and commit[-1] == "data"
    assert " ".join(push) == "git push"


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


# ── 真实仓库集成（下面这些必须跑真 git）────────────────────────

def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _init_repo(tmp_path: Path) -> Path:
    """临时仓库 + 本地裸仓库当远端；`data/habits.json` 已提交并推送。"""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    repo.mkdir()
    _git(tmp_path, "init", "--bare", "-q", str(origin))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "tester")
    (repo / "data").mkdir()
    (repo / "data" / "habits.json").write_text('{"_version": 1}\n', encoding="utf-8")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "add", "-A", "--", "data")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "push", "-q", "-u", "origin", "HEAD")
    return repo


def _run_sync(repo: Path) -> tuple[bool, str, str]:
    out: list[tuple[bool, str, str]] = []
    worker = _GitWorker(repo, build_sync_commands("data", "data: auto-sync [skip ci]"))
    worker.finished.connect(lambda ok, detail, state: out.append((ok, detail, state)))
    worker.run()
    return out[-1]


def test_sync_does_not_swallow_already_staged_source(qapp, tmp_path) -> None:
    """审查 #2：开发者已 `git add` 的源码不许被同步的提交夹带进去。"""
    repo = _init_repo(tmp_path)
    (repo / "source.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "--", "source.py")                    # 开发者已暂存源码
    (repo / "data" / "habits.json").write_text('{"_version": 1, "x": 1}\n',
                                               encoding="utf-8")

    ok, detail, _state = _run_sync(repo)
    assert ok, detail

    committed = _git(repo, "show", "--name-only", "--format=", "HEAD").stdout
    assert "source.py" not in committed, f"源码被夹带进同步提交：{committed}"
    staged = _git(repo, "diff", "--cached", "--name-only").stdout
    assert "source.py" in staged, "开发者原有的暂存状态必须保留"


def test_sync_stages_deletion_of_tracked_data(qapp, tmp_path) -> None:
    """审查 #6：删掉一个已跟踪的数据文件，同步必须把"删除"也提交上去。"""
    repo = _init_repo(tmp_path)
    (repo / "data" / "inventory.json").write_text('{"_version": 1, "items": []}\n',
                                                  encoding="utf-8")
    _git(repo, "add", "-A", "--", "data")
    _git(repo, "commit", "-q", "-m", "add inv")
    _git(repo, "push", "-q")

    (repo / "data" / "inventory.json").unlink()             # 用户删了它
    ok, detail, _state = _run_sync(repo)
    assert ok, detail

    tree = _git(repo, "ls-tree", "-r", "--name-only", "origin/master").stdout
    assert "data/inventory.json" not in tree, f"远端还留着已删除的文件：{tree}"
