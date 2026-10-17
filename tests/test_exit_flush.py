"""退出落盘不覆盖外部改动（审查 2026-10-17 #1 的最现实路径）。

`app.py` 退出 / 重启时原来调 `save_all()`（无条件整份写回）—— 应用跑着的时候若
skill / CLI / 手工改过文件，那些改动会被整份盖掉，而且**没有任何提示**。
现在退出走 `flush_on_exit()`：磁盘内容与内存不一致时**不覆盖**，把我方版本留成
冲突副本（`data/backup/exit_conflict/`），原文件保持原样。
"""

import json
from pathlib import Path

from src.services.data_manager import DataManager


def _external_edit(path: Path, mutate) -> None:
    """模拟 skill / CLI / 手工改文件（应用还在跑）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_flush_on_exit_does_not_overwrite_external_change(qapp, tmp_path) -> None:
    dm = DataManager(tmp_path)
    path = tmp_path / "inventory.json"
    dm.inventory.add_item({"name": "纸巾", "quantity": 3})
    dm.save_all()

    _external_edit(path, lambda d: d["items"].append(
        {"id": "i_ext", "name": "外部加的", "quantity": 1}))

    dm.flush_on_exit()

    names = [it["name"] for it in json.loads(path.read_text(encoding="utf-8"))["items"]]
    assert "外部加的" in names, "外部改动被覆盖了"


def test_flush_on_exit_keeps_our_version_as_conflict_copy(qapp, tmp_path) -> None:
    dm = DataManager(tmp_path)
    path = tmp_path / "inventory.json"
    dm.inventory.add_item({"name": "纸巾", "quantity": 3})
    dm.save_all()

    conflicts: list[tuple[str, str]] = []
    dm.save_conflict.connect(lambda name, p: conflicts.append((name, p)))
    _external_edit(path, lambda d: d["items"].append(
        {"id": "i_ext", "name": "外部加的", "quantity": 1}))

    dm.flush_on_exit()

    assert conflicts and conflicts[0][0] == "inventory"
    saved = json.loads(Path(conflicts[0][1]).read_text(encoding="utf-8"))
    assert [it["name"] for it in saved["items"]] == ["纸巾"], "冲突副本应是我方版本"


def test_flush_on_exit_does_not_rewrite_unchanged_file(qapp, tmp_path) -> None:
    dm = DataManager(tmp_path)
    path = tmp_path / "inventory.json"
    dm.inventory.add_item({"name": "纸巾", "quantity": 3})
    dm.save_all()

    before = path.read_text(encoding="utf-8")
    conflicts: list[str] = []
    dm.save_conflict.connect(lambda name, p: conflicts.append(name))

    dm.flush_on_exit()

    assert not conflicts
    assert path.read_text(encoding="utf-8") == before, "没变化时不该重写文件"
