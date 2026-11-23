"""数据 schema 守卫的**合成数据版**（审计 2026-11-21 P1："本地与公仓 CI 用不同数据"）。

`tests/test_data_schema.py::test_shipped_data_files_are_versioned_and_valid` 只能校验
本机 `data/`，而 2026-10-20 拆仓库后 `data/` **不随代码仓库走** —— 在 CI 里那一条
直接 `skip`。于是"schema 合法"这件事在本地与 CI 上根本不是同一个结论。

这里用合成数据把同一份契约钉住：每个模型落盘的文件都必须
**能解析 + 带 `_version` + 是对象**，而且 `_version` 与模型的 `supported_version` 一致
（否则 `actions_core._schema_version()` 会写出一个模型认不出的版本）。
"""

import json

import pytest

from src.models import semester_paths
from src.models.course import CourseModel
from src.models.daily_log import DailyLogModel
from src.models.exam import ExamModel
from src.models.expense import ExpenseModel
from src.models.habit import HabitModel
from src.models.inventory import InventoryModel
from src.models.membership_contacts import MembershipContactsModel
from src.models.routine import RoutineModel
from src.models.semester_registry import SemesterRegistry
from src.models.study import StudyModel
from src.models.task import TaskModel

# 每个模型 → 落盘时的文件名（`_schema_version()` 按文件名查版本，口径必须一致）
MODELS = [
    (TaskModel, "tasks.json"),
    (HabitModel, "habits.json"),
    (RoutineModel, "routines.json"),
    (ExpenseModel, "expenses.json"),
    (DailyLogModel, "daily_logs.json"),
    (InventoryModel, "inventory.json"),
    (StudyModel, "study.json"),
    (ExamModel, "exams.json"),
    (CourseModel, "courses.json"),
    (MembershipContactsModel, "memberships.json"),
]


def _build(model_cls, path) -> object:
    """按模型签名构造（`CourseModel` 需要学期注册表，其余只要路径）。"""
    if model_cls is CourseModel:
        registry = SemesterRegistry(path.parent / "semesters.json")
        return model_cls(path, registry)
    return model_cls(path)


@pytest.mark.parametrize(("model_cls", "name"), MODELS, ids=lambda v: getattr(v, "__name__", v))
def test_synthetic_file_is_versioned_and_parseable(tmp_path, model_cls, name) -> None:
    """⭐ 不依赖真实 `data/`：每个模型写出来的文件都必须带 `_version` 且是 JSON 对象。"""
    target = tmp_path / (semester_paths.SEMESTER_DIR + "/sem_001" if
                         semester_paths.is_per_semester(name) else "") / name
    target.parent.mkdir(parents=True, exist_ok=True)

    model = _build(model_cls, target)
    model.save()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{name} 顶层必须是对象"
    assert "_version" in payload, f"{name} 缺少 _version"
    assert isinstance(payload["_version"], int) and payload["_version"] >= 1


@pytest.mark.parametrize(("model_cls", "name"), MODELS, ids=lambda v: getattr(v, "__name__", v))
def test_schema_version_matches_the_write_path(tmp_path, model_cls, name) -> None:
    """`actions_core._schema_version()` 写的版本必须等于模型**认识**的版本。

    两者不一致时，AI 写完的文件模型会判成"版本比本程序新"→ 拒绝保存。
    """
    import scripts.actions_core as core

    target = tmp_path / name
    model = _build(model_cls, target)

    assert core._schema_version(name) == model.supported_version, name
