"""保存冲突检测（审查 2026-10-17 #1 的核心）。

此前"整份文档写回"没有任何版本校验：两个 Model 实例（或应用 + AI / CLI / skill）先后读
同一文件、各自改、先后保存 → 后写者**静默**覆盖前写者。

现在 `save()` 写前比对**磁盘内容指纹**：

- 不用 mtime：应用自己保存也会动 mtime；
- 不用 `_rev` 号：那要求每个写入方都配合维护，而 `scripts/actions_core.py`、skill、
  手工编辑都会漏 → 冲突照样静默通过，而这三条正是真实的并发来源。
"""

import json
from datetime import date
from pathlib import Path

from src.models.inventory import InventoryModel
from src.services.data_manager import DataManager


def _names(path: Path) -> list[str]:
    return [it["name"] for it in json.loads(path.read_text(encoding="utf-8"))["items"]]


def _external_append(path: Path, name: str) -> None:
    """模拟 skill / CLI / 手工编辑直接改文件。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"].append({"id": "i_ext", "name": name, "quantity": 1})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_second_writer_is_rejected(qapp, tmp_path) -> None:
    """审查的复现：A、B 各自持有内存副本，A 先存，B 再存必须被拒。"""
    path = tmp_path / "inventory.json"
    a = InventoryModel(path)
    b = InventoryModel(path)          # 各自读同一文件 → 各自一份副本

    a.add_item({"name": "A 加的"})
    assert a.save() is True

    b.add_item({"name": "B 加的"})
    conflicts: list = []
    b.on_conflict = conflicts.append

    assert b.save() is False, "B 的保存必须被拒绝（磁盘已被 A 改过）"
    assert _names(path) == ["A 加的"], "A 的数据不能被 B 覆盖"
    assert conflicts == [b]


def test_same_instance_can_save_repeatedly(qapp, tmp_path) -> None:
    """不能误报：同一个实例"改一次存一次"必须都成功。"""
    model = InventoryModel(tmp_path / "inventory.json")
    for name in ("一", "二", "三"):
        model.add_item({"name": name})
        assert model.save() is True


def test_reformatted_file_is_not_a_conflict(qapp, tmp_path) -> None:
    """指纹与键序无关：只是被重新格式化（缩进/键序变了）不算改动。"""
    path = tmp_path / "inventory.json"
    model = InventoryModel(path)
    model.add_item({"name": "纸巾"})
    assert model.save() is True

    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")

    model.add_item({"name": "抽纸"})
    assert model.save() is True, "仅格式变化不该判成冲突"


def test_data_manager_writes_copy_and_emits_signal(qapp, tmp_path) -> None:
    """DataManager 层：冲突 → 我方版本留副本 + 发信号，磁盘上的外部改动保持原样。"""
    dm = DataManager(tmp_path)
    path = tmp_path / "inventory.json"
    dm.inventory.add_item({"name": "纸巾"})
    assert dm.inventory.save() is True

    _external_append(path, "外部加的")

    dm.inventory.add_item({"name": "我方加的"})
    conflicts: list[tuple[str, str]] = []
    dm.save_conflict.connect(lambda name, p: conflicts.append((name, p)))

    assert dm.inventory.save() is False

    assert _names(path) == ["纸巾", "外部加的"], "外部改动必须保留"
    assert conflicts and conflicts[0][0] == "inventory"
    copy = json.loads(Path(conflicts[0][1]).read_text(encoding="utf-8"))
    assert [it["name"] for it in copy["items"]] == ["纸巾", "我方加的"], "副本是我方版本"


def test_conflict_hook_survives_semester_switch(qapp, tmp_path) -> None:
    """切学期会重建 courses/tasks/exams → 回调必须重装，否则冲突又变回静默覆盖。"""
    dm = DataManager(tmp_path)
    dm.create_semester("测试学期", date(2026, 9, 21))
    for model, name in dm._models():
        assert model.on_conflict is not None, f"{name} 丢了冲突回调"
