"""保存路径优化：**编码更快、格式不变**（`MD-files/PERFORMANCE_WORKFLOW.md` §3.1-2）。

cProfile 证据（10k 条 × 10 次保存，`scripts/perf_profile.py`）：

    86%  json.dump(indent=2)            ← 纯 Python 编码器 + 每 token 一次 write
       9%  _read_disk_state（冲突检测读盘解析）

`json.dump(indent=2)` 走的是 `_iterencode` 的**纯 Python 分支**（缩进/非 ASCII 都必须走它），
每次 `write()` 只输出几个字符 —— 10k 条要写 54 万次。改成"先 `dumps` 成字符串再一次性写"
不改变输出字节，但把写调用从几十万次降到一次。

**必须守住的三件事**（否则优化就是改格式、破坏 git 可读性）：

1. 输出与 `json.dump(..., ensure_ascii=False, indent=2)` **逐字节相同**；
2. `_version` 等既有键的顺序不变（`sort_keys` 会破坏可读性，不许用）；
3. 原子写语义不变（`.tmp` → `os.replace`，失败不留半个文件）。
"""

import json

import pytest

from src.models.base import BaseJsonModel
from src.models.task import TaskModel


def _legacy_bytes(payload: dict) -> bytes:
    """改造前的写法：`json.dump(obj, f, ensure_ascii=False, indent=2)`。

    ⚠ 在 Windows 上，`open(..., "w")` 是**文本模式** → 换行写成 CRLF。
    这批文件进 git（`core.autocrlf` 之外还有历史提交），换行风格必须原样保留，
    否则一次"优化"会让整份文件在 diff 里重写。
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return text.replace("\n", "\r\n").encode("utf-8")


def test_saved_bytes_match_the_legacy_encoding(tmp_path) -> None:
    """⭐ 逐字节一致（含中文、长字符串、换行、特殊字符）。"""
    model = TaskModel(tmp_path / "tasks.json")
    model.add({"title": "算法实验报告\n第二行\t制表",
               "course_name": "数据结构",
               "notes": "引号\"与反斜杠\\ 与 emoji 📚"})
    model.save()

    on_disk = (tmp_path / "tasks.json").read_bytes()

    assert on_disk == _legacy_bytes(model.data)


def test_key_order_is_preserved(tmp_path) -> None:
    """键顺序按插入序（`sort_keys` 会把 `_version` 排到末尾，破坏可读性）。"""
    model = TaskModel(tmp_path / "tasks.json")
    model.save()

    text = (tmp_path / "tasks.json").read_text(encoding="utf-8")
    first_key = text.splitlines()[1].strip().split('"')[1]

    assert first_key == "_version", text[:80]


def test_non_ascii_stays_readable(tmp_path) -> None:
    """中文原样写盘（*不是* `\\uXXXX`）—— 这些文件要进 git、要能手工看。"""
    model = TaskModel(tmp_path / "tasks.json")
    model.add({"title": "高等数学作业"})
    model.save()

    text = (tmp_path / "tasks.json").read_text(encoding="utf-8")

    assert "高等数学作业" in text
    assert "\\u" not in text


def test_atomic_write_keeps_no_partial_file(tmp_path, monkeypatch) -> None:
    """写失败不留半个文件（原子语义不能因为优化而丢）。"""
    target = tmp_path / "tasks.json"
    model = TaskModel(target)
    original = target.read_bytes()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("磁盘满")

    monkeypatch.setattr("os.replace", boom)
    model.add({"title": "改了一半"})

    with pytest.raises(OSError):
        model.atomic_write()

    assert target.read_bytes() == original, "失败后原文件必须完好"
    assert not list(tmp_path.glob("*.tmp")), "临时文件必须清理"


def test_save_still_returns_true_on_success(tmp_path) -> None:
    """返回值语义不变（冲突检测仍走 `_read_disk_state`）。"""
    model = TaskModel(tmp_path / "tasks.json")

    assert model.save() is True


def test_large_document_round_trips(tmp_path) -> None:
    """大文档（2000 条）落盘再读回，内容一致。"""
    model = TaskModel(tmp_path / "tasks.json")
    for i in range(2000):
        model.add({"title": f"作业 {i}", "notes": "备注" * 20})
    model.save()

    again = TaskModel(tmp_path / "tasks.json")

    assert len(again.tasks) == 2000
    assert again.tasks[0]["title"] == "作业 0"
    assert again.tasks[-1]["title"] == "作业 1999"


@pytest.mark.parametrize("payload", [
    {},
    {"a": 1},
    {"中文": ["列表", 1, None, True, 3.5]},
    {"nested": {"deep": {"deeper": ["x"] * 50}}},
])
def test_encoding_matches_for_edge_shapes(tmp_path, payload: dict) -> None:
    """各种形状的输出都逐字节一致（优化不能只在"正常数据"上对）。"""
    path = tmp_path / "x.json"
    model = BaseJsonModel(path, payload)
    model.data.update(payload)
    model.atomic_write()

    assert path.read_bytes() == _legacy_bytes(model.data)
