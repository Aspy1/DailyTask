"""`services/attachments.py` 的单元测试（沙箱目录，绝不碰真实 `data/`）。

覆盖：文件名清洗 / 路径穿越 / 目录与符号链接拒绝 / sha256 去重 /
大小与数量上限 / 缺失文件（不抛异常）/ **先提交索引再删文件** / 孤儿报告。
"""

import json
import os
from pathlib import Path

import pytest

from src.services import attachments as att


@pytest.fixture
def store(tmp_path) -> att.AttachmentStore:
    return att.AttachmentStore(tmp_path / "attachments")


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ── 文件名清洗 ──────────────────────────────────────────────

@pytest.mark.parametrize(("raw", "expected"), [
    (r"..\..\evil.txt", "evil.txt"),
    ("../../notes.pdf", "notes.pdf"),
    ("/etc/passwd", "passwd"),
    (r"C:\Users\me\report.docx", "report.docx"),
    ("CON", "_CON"),
    ("con.txt", "_con.txt"),
    ("Com1.log", "_Com1.log"),
    ("report. . ", "report"),
    ("a. ", "a"),
    ("", "file"),
    ("..", "file"),
    (".", "file"),
])
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert att.sanitize_filename(raw) == expected


def test_sanitize_filename_removes_illegal_and_control_chars() -> None:
    raw = 'a<b>:c|d?e*f"g\x00h\x1fi.txt'
    cleaned = att.sanitize_filename(raw)
    assert not set(cleaned) & set('<>:"/\\|?*')
    assert not any(ord(ch) < 32 for ch in cleaned)
    assert cleaned.endswith(".txt")


def test_sanitize_filename_truncates_but_keeps_extension() -> None:
    raw = "x" * 400 + ".pdf"
    cleaned = att.sanitize_filename(raw)
    assert len(cleaned) <= att.MAX_NAME_LEN
    assert cleaned.endswith(".pdf")


def test_task_key_is_path_safe() -> None:
    assert att.task_key("t_001") == "t_001"
    # `.` 也会被替换：目录名里不留任何点号，`..` 无从构造
    assert att.task_key("../../evil") == "______evil"
    assert "/" not in att.task_key("a/b")
    assert att.task_key("") == "unknown"


# ── 新增 / 去重 / 限额 ──────────────────────────────────────

def test_add_copies_file_and_records_relative_metadata(store, tmp_path) -> None:
    src = _write(tmp_path / "inbox" / "作业说明.txt", b"hello")
    entry = store.add("t_001", src)

    assert entry["name"] == "作业说明.txt"
    assert entry["size"] == 5
    assert entry["sha256"] == att._sha256_of(src)
    assert entry["added_at"]
    # 元数据里**不能**出现绝对路径（数据目录搬家后仍可用）
    assert str(tmp_path) not in json.dumps(entry, ensure_ascii=False)
    assert Path(entry["stored_name"]).name == entry["stored_name"]
    copied = store.resolve("t_001", entry["stored_name"])
    assert copied is not None and copied.read_bytes() == b"hello"
    assert copied.is_relative_to((tmp_path / "attachments").resolve())


def test_add_deduplicates_same_content_within_task(store, tmp_path) -> None:
    first = store.add("t_001", _write(tmp_path / "a.txt", b"same"))
    second = store.add("t_001", _write(tmp_path / "b.txt", b"same"), [first])

    assert second["stored_name"] == first["stored_name"]
    files = list((tmp_path / "attachments" / "t_001").iterdir())
    assert files == [tmp_path / "attachments" / "t_001" / first["stored_name"]]


def test_add_same_content_different_tasks_is_not_deduplicated(store, tmp_path) -> None:
    src = _write(tmp_path / "a.txt", b"same")
    store.add("t_001", src)
    store.add("t_002", src)
    assert (tmp_path / "attachments" / "t_002").is_dir()


def test_add_rejects_file_over_size_limit(tmp_path) -> None:
    store = att.AttachmentStore(tmp_path / "attachments", max_bytes=4)
    with pytest.raises(att.AttachmentTooLarge):
        store.add("t_001", _write(tmp_path / "big.bin", b"12345"))


def test_add_rejects_more_than_file_count_limit(tmp_path) -> None:
    store = att.AttachmentStore(tmp_path / "attachments", max_files=2)
    entries = []
    for i in range(2):
        entries.append(store.add("t_001", _write(tmp_path / f"f{i}.txt", bytes([i]))))
    with pytest.raises(att.AttachmentLimitReached):
        store.add("t_001", _write(tmp_path / "f2.txt", b"third"))
    assert len(list((tmp_path / "attachments" / "t_001").iterdir())) == 2


def test_add_rejects_directory_and_missing_source(store, tmp_path) -> None:
    (tmp_path / "folder").mkdir()
    with pytest.raises(att.AttachmentSourceRejected):
        store.add("t_001", tmp_path / "folder")
    with pytest.raises(att.AttachmentSourceRejected):
        store.add("t_001", tmp_path / "nope.txt")


def test_add_rejects_symlink_source(store, tmp_path) -> None:
    target = _write(tmp_path / "real.txt", b"x")
    link = tmp_path / "link.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")
    with pytest.raises(att.AttachmentSourceRejected):
        store.add("t_001", link)


# ── 缺失 / 越界 ────────────────────────────────────────────

def test_resolve_returns_none_for_missing_file_without_raising(store, tmp_path) -> None:
    entry = store.add("t_001", _write(tmp_path / "a.txt", b"x"))
    (tmp_path / "attachments" / "t_001" / entry["stored_name"]).unlink()
    assert store.resolve("t_001", entry["stored_name"]) is None


def test_resolve_rejects_names_that_escape_the_task_dir(store) -> None:
    assert store.resolve("t_001", "../secrets.txt") is None
    assert store.resolve("t_001", r"..\..\secrets.txt") is None
    assert store.resolve("t_001", "sub/dir.txt") is None
    assert store.resolve("t_001", "") is None


def test_private_target_guard_blocks_traversal(store) -> None:
    with pytest.raises(att.AttachmentPathInvalid):
        store._target("t_001", "../escape.txt")


def test_task_id_cannot_escape_root(store, tmp_path) -> None:
    entry = store.add("../../evil", _write(tmp_path / "a.txt", b"x"))
    folder = tmp_path / "attachments" / "______evil"
    assert entry["stored_name"] in [p.name for p in folder.iterdir()]
    assert not (tmp_path.parent / "evil").exists()


# ── 删除：先提交索引、再删文件 ─────────────────────────────

def test_remove_keeps_file_when_index_commit_fails(store, tmp_path) -> None:
    entry = store.add("t_001", _write(tmp_path / "a.txt", b"x"))
    assert store.remove("t_001", entry["stored_name"], commit=lambda: False) is False
    assert store.resolve("t_001", entry["stored_name"]) is not None


def test_remove_deletes_file_only_after_index_commit(store, tmp_path) -> None:
    entry = store.add("t_001", _write(tmp_path / "a.txt", b"x"))
    calls: list[str] = []

    def commit() -> bool:
        # 提交时文件必须还在（否则就是"先删文件后写索引"）
        calls.append("commit")
        return store.resolve("t_001", entry["stored_name"]) is not None

    assert store.remove("t_001", entry["stored_name"], commit=commit) is True
    assert calls == ["commit"]
    assert store.resolve("t_001", entry["stored_name"]) is None


def test_remove_requires_commit_callback(store, tmp_path) -> None:
    entry = store.add("t_001", _write(tmp_path / "a.txt", b"x"))
    with pytest.raises(TypeError):
        store.remove("t_001", entry["stored_name"])


def test_remove_task_and_orphan_report(store, tmp_path) -> None:
    entry = store.add("t_001", _write(tmp_path / "a.txt", b"x"))
    store.add("t_002", _write(tmp_path / "b.txt", b"y"))
    # 已知任务目录里的多余文件 → 记进 files；未知目录整目录记进 task_dirs
    _write(tmp_path / "attachments" / "t_001" / "stray-in-known.txt", b"z")
    (tmp_path / "attachments" / "t_999").mkdir(parents=True)

    task = {"id": "t_001", "attachments": [entry]}
    report = store.orphan_report([task])
    assert report["task_dirs"] == ["t_002", "t_999"]
    assert report["files"] == ["t_001/stray-in-known.txt"]

    assert store.remove_task("t_001") == 2
    assert not (tmp_path / "attachments" / "t_001").exists()
    assert store.remove_task("t_001") == 0


def test_human_size() -> None:
    assert att.human_size(0) == "0 B"
    assert att.human_size(1023) == "1023 B"
    assert att.human_size(1024) == "1.0 KB"
    assert att.human_size(1024 * 1024) == "1.0 MB"
    assert att.human_size(None) == "0 B"
