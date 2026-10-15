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


def test_shipped_data_files_are_versioned_and_valid() -> None:
    """仓库内的 data/*.json 必须能解析且带 _version（派生文件除外）。"""
    derived = {"weather_cache.json", "weather_stats.json", "search_index.json",
               "scenes_meta.json"}
    checked = 0
    for f in sorted((ROOT / "data").glob("*.json")):
        if f.name in derived:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        assert "_version" in data, f"{f.name} 缺少 _version"
        checked += 1
    assert checked >= 5
