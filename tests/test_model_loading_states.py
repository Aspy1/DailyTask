"""P1：模型载入的**损坏分类**与轮询探针（审计 2026-11-21）。

已复现（审计原文）：JSON 根为数组、版本为错误类型、或内容为非法 UTF-8 时，
模型**绕过**预期的损坏处理 —— `load()` 只捕获 `json.JSONDecodeError`，
上面三种会从别处炸开（`AttributeError` / `TypeError` / `UnicodeDecodeError`），
于是既没有留档，也没有"用默认值继续并留痕"，而是把异常抛给启动路径。

轮询也漏掉 mtime 只改变 50 毫秒的内容更新（`abs(mtime - last) > 0.1`，
float 精度 + 阈值双重损失）。

验收（审计原文）：统一分类缺失、不可读、编码错误、schema 不符和未来版本；
可恢复损坏保留现场，暂时不可读延迟重试；轮询用存在状态和 `st_mtime_ns` 做探针。
"""

import json

import pytest

from src.models.base import DataCorrupted, Unreadable
from src.models.task import DEFAULT_TASKS, TaskModel


def _write(path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


# ── 载入：五种状态必须分开 ─────────────────────────────────

def test_missing_file_creates_defaults(tmp_path) -> None:
    """缺失 → 建默认值（既有行为，不能被新分类改坏）。"""
    model = TaskModel(tmp_path / "tasks.json")

    assert model.tasks == []
    assert (tmp_path / "tasks.json").is_file()


def test_json_root_is_an_array_is_treated_as_corrupt(tmp_path) -> None:
    """⭐ 根是数组：`self._data` 变成 list，后续 `.setdefault` 会 AttributeError。"""
    target = tmp_path / "tasks.json"
    _write(target, b'[{"id": "t_001"}]')

    model = TaskModel(target)

    assert model.tasks == [], "应当退回默认值"
    assert model.recovered_from is not None, "现场必须留档"
    assert not target.exists() or json.loads(target.read_text(encoding="utf-8")) == DEFAULT_TASKS


def test_json_root_is_a_scalar_is_treated_as_corrupt(tmp_path) -> None:
    target = tmp_path / "tasks.json"
    _write(target, b'"just a string"')

    model = TaskModel(target)

    assert model.recovered_from is not None


def test_wrong_typed_version_is_treated_as_corrupt(tmp_path) -> None:
    """⭐ `_version` 是字符串时 `version > supported_version` 直接 TypeError。"""
    target = tmp_path / "tasks.json"
    _write(target, json.dumps({"_version": "2", "tasks": [], "archived": []}).encode())

    model = TaskModel(target)

    assert model.recovered_from is not None
    assert isinstance(model.version, int)


def test_non_integer_version_is_treated_as_corrupt(tmp_path) -> None:
    target = tmp_path / "tasks.json"
    _write(target, json.dumps({"_version": [1], "tasks": []}).encode())

    model = TaskModel(target)

    assert isinstance(model.version, int)


def test_invalid_utf8_is_treated_as_corrupt(tmp_path) -> None:
    """⭐ 非法 UTF-8：原来在 `f.read()` 就抛 `UnicodeDecodeError`，没人接。"""
    target = tmp_path / "tasks.json"
    _write(target, b'{"_version": 2, "tasks": [], "archived": [], "x": "\xff\xfe"}')

    model = TaskModel(target)

    assert model.recovered_from is not None


def test_future_version_only_warns_and_does_not_touch_the_file(tmp_path) -> None:
    """未来版本：**不算损坏**（可能是更新版应用写的）→ 只警告，不改动。"""
    target = tmp_path / "tasks.json"
    payload = {"_version": 99, "tasks": [{"id": "t_001", "title": "未来的"}], "archived": []}
    _write(target, json.dumps(payload).encode())
    before = target.read_bytes()

    model = TaskModel(target)

    assert model.recovered_from is None, "未来版本不是损坏"
    assert target.read_bytes() == before, "一个字节都不许改"
    assert model.save() is False, "也不许覆盖"


def test_schema_mismatch_is_reported_as_such(tmp_path) -> None:
    """顶层键类型不符（tasks 写成字符串）→ 也归到损坏，而不是中途崩。"""
    target = tmp_path / "tasks.json"
    _write(target, json.dumps({"_version": 2, "tasks": "不是数组"}).encode())

    model = TaskModel(target)

    assert model.recovered_from is not None


def test_quarantine_names_the_reason(tmp_path) -> None:
    """留档文件名要带**原因**，否则事后只能看到一堆 .corrupt-<时间戳>。"""
    target = tmp_path / "tasks.json"
    _write(target, b'[1, 2]')

    model = TaskModel(target)

    assert model.recovered_from is not None
    assert "corrupt" in model.recovered_from.name


def test_transiently_unreadable_is_retried_not_quarantined(tmp_path, monkeypatch) -> None:
    """⭐ 暂时不可读（占用 / 权限）**不能**留档：那是可恢复的，重试即可。"""
    target = tmp_path / "tasks.json"
    _write(target, json.dumps({"_version": 2, "tasks": [], "archived": []}).encode())
    calls = {"n": 0}
    real_read = type(target).read_text

    def flaky(self, *args: object, **kwargs: object) -> str:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("被占用")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(type(target), "read_text", flaky, raising=False)

    model = TaskModel(target)

    assert model.recovered_from is None, f"暂时不可读不该留档（{list(tmp_path.glob('*'))}）"
    assert calls["n"] >= 3, "应当重试"


def test_unreadable_forever_keeps_the_site_intact(tmp_path, monkeypatch) -> None:
    """一直读不出来 → 用默认值继续，但**必须禁止写入**（不许毁现场）。"""
    target = tmp_path / "tasks.json"
    _write(target, json.dumps({"_version": 2, "tasks": [], "archived": []}).encode())
    before = target.read_bytes()

    def always_busy(self, *args: object, **kwargs: object) -> str:
        raise PermissionError("一直被占用")

    monkeypatch.setattr(type(target), "read_text", always_busy, raising=False)

    model = TaskModel(target)

    assert model.recovered_from is None
    assert model._write_blocked is True, "读到坏现场前不许写"
    assert target.read_bytes() == before, "现场一个字节都不许动"


def test_unreadable_classifies_apart_from_corrupt() -> None:
    """`Unreadable` 与 `DataCorrupted` 是**不同**结论：前者重试，后者留档。"""
    assert issubclass(Unreadable, RuntimeError)
    assert not issubclass(Unreadable, DataCorrupted)


@pytest.mark.parametrize("payload", [
    b'[]',
    b'{}',
    b'null',
    b'{"_version": "x"}',
    b'{"_version": 2, "tasks": 5}',
])
def test_every_bad_shape_lands_in_the_same_bucket(tmp_path, payload: bytes) -> None:
    """五种坏形状都必须走同一条"留档 + 默认值"路径（不许从别处炸开）。"""
    target = tmp_path / "tasks.json"
    _write(target, payload)

    model = TaskModel(target)

    assert isinstance(model.data, dict)
    assert isinstance(model.version, int)
