"""迁移与损坏数据的闭环（审查 2026-10-17 #5）。

三件事：

1. **缺迁移实现必须拒绝** —— 旧实现找不到 `_migrate_vX_to_vY` 也照样把 `_version`
   抬上去，数据"看起来迁过了"其实没有；
2. 逐步迁移（v1→v2→v3），任一步失败**不写文件**；
3. 坏 JSON **留档**（保留现场）+ 用默认值继续，既不静默当空数据，也不让应用起不来。
"""

import json
from pathlib import Path

import pytest

from src.models import semester_paths
from src.models.base import (
    BaseJsonModel,
    MigrationFailed,
    MigrationUnavailable,
)


class _V1ToV2Only(BaseJsonModel):
    """只有 v1→v2 的实现 —— 迁到 v3 必须被拒绝。"""

    def __init__(self, path: Path) -> None:
        super().__init__(path, {"_version": 1, "items": []})

    def _migrate_v1_to_v2(self) -> None:
        self._data["added_v2"] = True


class _TwoSteps(_V1ToV2Only):
    """v1→v2→v3 都有，并记录执行顺序。"""

    def __init__(self, path: Path) -> None:
        self.steps: list[int] = []
        super().__init__(path)

    def _migrate_v1_to_v2(self) -> None:
        self.steps.append(2)
        self._data["added_v2"] = True

    def _migrate_v2_to_v3(self) -> None:
        self.steps.append(3)
        self._data["added_v3"] = True


def test_missing_step_refuses_to_bump_version(tmp_path) -> None:
    """审查的复现：没有 v2→v3 实现时 `migrate(3)` 必须拒绝，且**不动文件**。"""
    path = tmp_path / "x.json"
    m = _V1ToV2Only(path)
    before = path.read_text(encoding="utf-8")

    with pytest.raises(MigrationUnavailable):
        m.migrate(3)

    assert m.version == 1, "版本不许抬"
    assert path.read_text(encoding="utf-8") == before, "文件不许改"


def test_stepwise_migration_runs_every_step(tmp_path) -> None:
    path = tmp_path / "x.json"
    m = _TwoSteps(path)

    m.migrate(3)

    assert m.steps == [2, 3], "必须逐步执行"
    assert m.version == 3
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["_version"] == 3 and on_disk["added_v3"] is True


def test_failing_step_keeps_file_untouched(tmp_path) -> None:
    class _Boom(_TwoSteps):
        def _migrate_v2_to_v3(self) -> None:
            raise RuntimeError("boom")

    path = tmp_path / "x.json"
    m = _Boom(path)
    before = path.read_text(encoding="utf-8")

    with pytest.raises(MigrationFailed):
        m.migrate(3)

    assert path.read_text(encoding="utf-8") == before, "失败时文件保持原样"
    assert json.loads(before)["_version"] == 1


def test_corrupt_file_is_quarantined_and_defaults_used(tmp_path) -> None:
    """坏 JSON：留档保留现场 + 用默认值继续（**不是**当空数据、也不是崩掉）。"""
    path = tmp_path / "habits.json"
    path.write_text("{ 这不是 JSON", encoding="utf-8")

    m = BaseJsonModel(path, {"_version": 1, "habits": []})

    kept = list(tmp_path.glob("habits.corrupt-*.json"))
    assert kept, "坏文件必须留档"
    assert kept[0].read_text(encoding="utf-8") == "{ 这不是 JSON", "现场要一字不动"
    assert m.recovered_from == kept[0]
    assert m.data.get("habits") == []
    assert path.exists(), "留档后要落一份可用的默认文件"


def test_registry_corrupt_is_quarantined(tmp_path) -> None:
    path = semester_paths.registry_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")

    assert semester_paths.read_registry(tmp_path) == {}
    assert list(tmp_path.glob("semesters.corrupt-*.json")), "注册表现场要留档"


def test_failed_step_does_not_touch_memory(tmp_path) -> None:
    """v1→v2 成功、v2→v3 失败后：**内存也不能停在半成品**（审查 #5）。

    否则磁盘还是 v1、内存已是 v2 且带部分新字段 —— 之后一次普通保存就把失败迁移的
    中间态写进文件。
    """
    class _Halfway(_TwoSteps):
        def _migrate_v2_to_v3(self) -> None:
            raise RuntimeError("boom")

    path = tmp_path / "x.json"
    m = _Halfway(path)
    before = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(MigrationFailed):
        m.migrate(3)

    assert m.version == 1, "内存版本必须回滚"
    assert "added_v2" not in m.data, "半成品字段不许留在内存里"
    assert m.data == before


def test_failed_final_save_rolls_back_memory(tmp_path) -> None:
    """审查第三轮 #3：迁移的**最终写盘**被拒时，内存也要回滚并明确报失败。

    原来 `self.save()` 在回滚边界之外、返回值也不看 → 磁盘还是 v1、内存已 v2，
    方法却正常返回。
    """
    path = tmp_path / "x.json"
    m = _TwoSteps(path)
    path.write_text(json.dumps({"_version": 1, "items": [], "外部改过": True}),
                    encoding="utf-8")           # 磁盘内容变了 → save() 会拒绝

    with pytest.raises(MigrationFailed):
        m.migrate(2)

    assert m.version == 1, "内存必须回滚到 v1"
    assert "added_v2" not in m.data, "半成品字段不许留在内存里"
