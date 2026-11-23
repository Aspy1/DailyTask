"""数据模型版本与迁移守卫（CODE_STANDARDS Q-E4）。

数据可能被三个端同时读写（桌面 / TG bot / GitHub Actions），
字段结构变更必须有版本护栏，避免"旧文件按新结构解析"。
"""

import json

import pytest

from src.models.course import CourseModel
from src.models.daily_log import DailyLogModel
from src.models.exam import ExamModel
from src.models.expense import ExpenseModel
from src.models.habit import HabitModel
from src.models.inventory import InventoryModel
from src.models.task import TaskModel

MODELS = [CourseModel, TaskModel, HabitModel, ExpenseModel, ExamModel,
          DailyLogModel, InventoryModel]



@pytest.mark.parametrize("model_cls", MODELS, ids=lambda c: c.__name__)
def test_model_creates_versioned_file(tmp_path, model_cls) -> None:
    m = model_cls(tmp_path / "x.json")
    assert isinstance(m.version, int) and m.version >= 1
    on_disk = json.loads((tmp_path / "x.json").read_text(encoding="utf-8"))
    assert on_disk.get("_version") == m.version


@pytest.mark.parametrize("model_cls", MODELS, ids=lambda c: c.__name__)
def test_migrate_to_current_is_noop(tmp_path, model_cls) -> None:
    m = model_cls(tmp_path / "x.json")
    before = json.dumps(m.data, sort_keys=True)
    m.migrate(m.version)                     # 目标 == 当前 → 不应改动
    assert json.dumps(m.data, sort_keys=True) == before


def test_default_data_is_not_shared_between_instances(tmp_path) -> None:
    """回归（ERRORS #024）：DEFAULT_* 只能深拷贝。

    浅拷贝时 `self._data["items"]` 就是模块级常量的那个 list，
    一个实例 append 后，后建的实例（哪怕指向别的数据目录）会跟着多出条目。
    """
    import src.models.exam as exam_mod
    import src.models.inventory as inv_mod

    a = InventoryModel(tmp_path / "a.json")
    a.add_item({"name": "只属于 a 的东西"})
    assert inv_mod.DEFAULT_INVENTORY["items"] == [], "模块级默认值被污染"

    b = InventoryModel(tmp_path / "b.json")          # 另一个目录、另一个实例
    assert b.items == [], b.items

    e1 = ExamModel(tmp_path / "e1.json")
    e1.add_exam({"course_name": "只属于 e1", "exam_date": "2026-12-01"})
    e2 = ExamModel(tmp_path / "e2.json")
    assert e2.exams == [], e2.exams
    assert exam_mod.DEFAULT_EXAMS["exams"] == []


def test_synthetic_acceptance_data_files_are_versioned(tmp_path, monkeypatch) -> None:
    from scripts import acceptance_check

    monkeypatch.setattr(acceptance_check, "SANDBOX", tmp_path)
    acceptance_check._seed_synthetic()
    candidates = list(tmp_path.rglob("*.json"))
    assert len(candidates) >= 5
    for path in candidates:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict) and type(document.get("_version")) is int, path
