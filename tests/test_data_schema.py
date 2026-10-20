"""数据模型版本与迁移守卫（CODE_STANDARDS Q-E4）。

数据可能被三个端同时读写（桌面 / TG bot / GitHub Actions），
字段结构变更必须有版本护栏，避免"旧文件按新结构解析"。
"""

import json
from pathlib import Path

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

ROOT = Path(__file__).resolve().parent.parent


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


def test_shipped_data_files_are_versioned_and_valid() -> None:
    """`data/` 里的 JSON（含按学期分的那批）必须能解析且带 `_version`（派生文件除外）。

    ⚠ 2026-10-20 拆仓库后：`data/` **不再随代码仓库走**（它是独立的私有数据仓库）→
    在 CI 里这个目录**不存在** ✓。存在就校验，不存在就跳过（不是失败 ✗）。
    """
    if not (ROOT / "data").is_dir():
        pytest.skip("data/ 不在代码仓库里（2026-10-20 已拆到私有数据仓库）")
    derived = {"weather_cache.json", "weather_stats.json", "search_index.json",
               "scenes_meta.json"}
    candidates = list((ROOT / "data").glob("*.json"))
    semester_root = ROOT / "data" / "semesters"
    if semester_root.is_dir():                      # 按学期分文件：semesters/<id>/*.json
        candidates += list(semester_root.rglob("*.json"))
    checked = 0
    for f in sorted(candidates):
        if f.name in derived:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        assert "_version" in data, f"{f.relative_to(ROOT)} 缺少 _version"
        checked += 1
    assert checked >= 5
