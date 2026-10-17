"""保存冲突检测（审查 2026-10-17 #1）。

此前"整份文档写回"没有任何版本校验：两个 Model 实例（或应用 + AI / CLI / skill）先后读
同一文件、各自改、先后保存 → 后写者**静默**覆盖前写者。

现在 `save()` 写前比对**磁盘内容指纹**，并且"读指纹 → 比较 → 写"整段持 `WRITE_LOCK`：

- 不用 mtime：应用自己保存也会动 mtime；
- 不用 `_rev` 号：那要求每个写入方都配合维护，而 `scripts/actions_core.py`、skill、
  手工编辑都会漏 → 冲突照样静默通过，而这三条正是真实的并发来源；
- 加锁不保证"都写成功"，但保证**至少有一个被拒绝并告知**（审查 #1 的复现）。
"""

import json
import threading
from datetime import date
from pathlib import Path

import pytest

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
    """A、B 各自持有内存副本，A 先存，B 再存必须被拒。"""
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


def test_concurrent_saves_only_one_wins(qapp, tmp_path) -> None:
    """审查 #1 的**并发**复现：两个写入者同时保存 → 恰好一个成功、另一个被拒。

    "读指纹 → 比较 → 写"若不互斥，两边都会通过检查、后写者静默覆盖（双方都报成功）。
    """
    path = tmp_path / "inventory.json"
    a = InventoryModel(path)
    b = InventoryModel(path)
    a.add_item({"name": "A 加的"})
    b.add_item({"name": "B 加的"})

    barrier = threading.Barrier(2)
    results: list[bool] = []

    def _save(model: InventoryModel) -> None:
        barrier.wait()                 # 尽量让两次保存同时发生
        results.append(model.save())

    threads = [threading.Thread(target=_save, args=(m,)) for m in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [False, True], f"必须恰好一个成功，实际 {results}"
    assert _names(path) in (["A 加的"], ["B 加的"]), "磁盘上应是某个写入者的版本"


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


def test_save_refuses_when_disk_became_corrupt(qapp, tmp_path) -> None:
    """载入时好好的、之后文件损坏 → save() **拒绝**，不能把现场覆盖掉（审查 #3）。"""
    path = tmp_path / "inventory.json"
    model = InventoryModel(path)
    model.add_item({"name": "纸巾"})
    assert model.save() is True

    path.write_text("{ 这不是 JSON", encoding="utf-8")      # 外部把文件写坏
    model.add_item({"name": "抽纸"})

    assert model.save() is False, "读不出来的文件不许覆盖"
    assert path.read_text(encoding="utf-8") == "{ 这不是 JSON", "现场必须原样保留"


def test_quarantine_failure_blocks_writes(qapp, tmp_path, monkeypatch) -> None:
    """留档失败 → **禁止写入**（现场还在原地，写替代文件等于毁掉它，审查 #3）。"""
    path = tmp_path / "inventory.json"
    path.write_text("{ 坏的", encoding="utf-8")

    import src.models.base as base_module

    class _BoomOs:
        """只替掉 **base 模块里**的 `os`（不动全局 os，否则会踩到 pytest 自己）。"""

        @staticmethod
        def replace(*args: object, **kwargs: object) -> None:
            raise OSError("模拟：改名失败（文件被占用）")

    monkeypatch.setattr(base_module, "os", _BoomOs)

    model = InventoryModel(path)       # 构造时就会去读坏文件

    assert model.recovered_from is None, "留档失败 → 没有留档路径"
    assert model._write_blocked is True, "必须禁止写入"
    assert model.save() is False
    assert path.read_text(encoding="utf-8") == "{ 坏的", "现场必须原样保留"


def test_actions_core_refuses_stale_write(sandbox) -> None:
    """AI 那条路（`actions_core`）同样必须拒绝"用旧快照覆盖"（审查 #1）。"""
    from scripts import actions_core

    path = actions_core._path("inventory.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"_version": 1, "items": []}, ensure_ascii=False),
                    encoding="utf-8")

    data = actions_core.load("inventory.json")            # 记下读到的指纹
    _external_append(path, "外部加的")                     # 期间别人写了
    data["items"].append({"id": "i_ai", "name": "AI 加的", "quantity": 1})

    with pytest.raises(actions_core.ActionError):
        actions_core.save("inventory.json", data)

    assert _names(path) == ["外部加的"], "旧快照不许覆盖别人的改动"


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


def test_actions_core_refuses_after_semester_switch(sandbox) -> None:
    """审查第三轮 #1：读 A 学期 → 切 B → 保存必须被拒。

    原来 `save()` 会**重新解析**当前学期，于是把 A 的快照写进 B；B 若还没有指纹记录
    更是直接跳过检查。
    """
    from scripts import actions_core
    from src.models import semester_paths

    a_path = actions_core._path("tasks.json")
    a_path.parent.mkdir(parents=True, exist_ok=True)
    a_path.write_text(json.dumps({"_version": 1, "tasks": [{"id": "t_001"}]}),
                      encoding="utf-8")
    data = actions_core.load("tasks.json")            # 读 A：记下 A 的路径 + 指纹

    registry = semester_paths.registry_path(actions_core.DATA)
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({
        "_version": 1, "current_semester": "sem_B",
        "semesters": [{"id": "sem_B", "name": "B 学期", "start_date": "2026-09-21"}],
    }, ensure_ascii=False), encoding="utf-8")
    assert actions_core._path("tasks.json") != a_path, "前提：解析结果确实换了学期"

    with pytest.raises(actions_core.ActionError):
        actions_core.save("tasks.json", data)

    assert "t_001" in a_path.read_text(encoding="utf-8"), "旧学期的文件不许被动"


def test_file_lock_blocks_another_process(sandbox) -> None:
    """审查第三轮 #2：锁必须**跨进程** —— 应用关掉后两个 CLI 同时写，一个要等另一个。

    进程内的 `RLock` 挡不住独立进程；这里真起一个子进程来验。
    """
    import subprocess
    import sys
    import time

    from scripts import actions_core
    from src.models.base import file_lock

    root = Path(__file__).resolve().parent.parent
    path = actions_core._path("inventory.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"_version": 1, "items": []}), encoding="utf-8")

    code = (
        f"import sys; sys.path.insert(0, r'{root!s}');"
        "from pathlib import Path;"
        "import scripts.actions_core as c;"
        f"c.DATA = Path(r'{actions_core.DATA!s}');"
        "d = c.load('inventory.json'); d['items'].append({'id': 'i_child'});"
        "c.save('inventory.json', d); print('CHILD-DONE')"
    )

    with file_lock(path):                     # 父进程先占住文件锁
        child = subprocess.Popen([sys.executable, "-c", code],
                                 stdout=subprocess.PIPE, text=True,
                                 encoding="utf-8", errors="replace")
        time.sleep(0.6)
        assert child.poll() is None, "子进程没被挡住 —— 锁没跨进程生效"

    out, _err = child.communicate(timeout=20)
    assert "CHILD-DONE" in out, f"子进程没跑完：{out!r}"
