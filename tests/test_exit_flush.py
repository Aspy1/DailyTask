"""退出落盘不覆盖外部改动（审查 2026-10-17 #1 的最现实路径）。

`app.py` 退出 / 重启时原来调 `save_all()`（无条件整份写回）—— 应用跑着的时候若
skill / CLI / 手工改过文件，那些改动会被整份盖掉，而且**没有任何提示**。
现在退出走 `flush_on_exit()`：**真正的外部改动**不覆盖，把我方版本留成冲突副本
（`data/backup/save_conflict/`），原文件保持原样。

启动自愈（补默认字段 / 重算日期驱动的状态）**不算**外部改动（`ERRORS #061`）：
旧的整份内容比较把"内存已补齐、磁盘还是旧文件"误判成外部写入，于是每次
打开→退出都刷一份无意义的冲突副本并弹窗。冲突判定统一交给
`BaseJsonModel.save()` 的磁盘指纹基线。
"""

import json
import logging
from pathlib import Path

from src.services.data_manager import DataManager


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _conflict_copies(data_dir: Path) -> list[Path]:
    return sorted((data_dir / "backup" / "save_conflict").glob("*.json"))


def _collect_conflicts(dm: DataManager) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    dm.save_conflict.connect(lambda name, path: seen.append((name, path)))
    return seen


# 旧版数据：`expenses` 缺「订阅/分期」分类、`inventory` 缺 `item_seq`
LEGACY_EXPENSES = {
    "_version": 1,
    "categories": [{"id": "food", "name": "餐饮"}],
    "budget": {"monthly": 1500, "by_category": {}},
    "records": [{"id": "e_001", "amount": 12.5, "category": "food",
                 "date": "2026-11-01", "note": "午饭"}],
}
LEGACY_INVENTORY = {
    "_version": 2,
    "items": [{"id": "i_001", "name": "抽纸", "quantity": 3, "unit": "包",
               "category": "日常消耗品", "location": "学校", "status": "充足"}],
    "categories": ["日常消耗品", "数码电子", "衣物", "订阅", "其他"],
    "locations": ["学校", "家", "老家"],
}
LEGACY_STUDY = {"_version": 1, "sessions": [], "mistakes": [], "mocks": []}


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


# ── 启动自愈 ≠ 外部改动（ISSUE-0007）────────────────────────

def test_startup_self_heal_is_not_reported_as_external_change(
        qapp, tmp_path, caplog) -> None:
    """⭐ 旧 `expenses`（缺订阅分类）与旧 `inventory`（缺 item_seq）→ 退出零冲突。

    修复前：`flush_on_exit()` 用整份内容比较，把启动自愈判成"磁盘被别人改过"，
    每次都写副本、发信号、弹窗（用户日志里的 expenses / inventory 两条）。
    """
    _write(tmp_path / "expenses.json", LEGACY_EXPENSES)
    _write(tmp_path / "inventory.json", LEGACY_INVENTORY)

    dm = DataManager(tmp_path)
    conflicts = _collect_conflicts(dm)
    with caplog.at_level(logging.WARNING, logger="src.services.data_manager"):
        dm.flush_on_exit()

    assert conflicts == [], f"启动自愈被误判成外部改动：{conflicts}"
    assert _conflict_copies(tmp_path) == []
    assert not [r for r in caplog.records if "退出时" in r.getMessage()]

    expenses = _read(tmp_path / "expenses.json")
    assert [r["id"] for r in expenses["records"]] == ["e_001"]
    assert expenses["records"][0]["amount"] == 12.5
    assert any(c["id"] == "subscription" for c in expenses["categories"]), "自愈应落盘"

    inventory = _read(tmp_path / "inventory.json")
    assert [it["id"] for it in inventory["items"]] == ["i_001"]
    assert inventory["items"][0]["quantity"] == 3, "物品数量不许被自愈改掉"
    assert isinstance(inventory.get("item_seq"), int), "自愈应落盘"


def test_new_install_first_exit_has_no_conflict(qapp, tmp_path) -> None:
    """⭐ 空数据目录（新装）首次打开→退出：`study` 的默认目标日也不许误报。"""
    dm = DataManager(tmp_path)
    conflicts = _collect_conflicts(dm)

    dm.flush_on_exit()

    assert conflicts == []
    assert _conflict_copies(tmp_path) == []
    assert _read(tmp_path / "study.json")["target_date"], "默认目标日应落盘"


def test_study_defaults_self_heal_is_persisted_without_conflict(qapp, tmp_path) -> None:
    """旧 `study.json` 缺 subjects / target_date → 退出时补齐落盘，不报冲突。"""
    _write(tmp_path / "study.json", LEGACY_STUDY)
    dm = DataManager(tmp_path)
    conflicts = _collect_conflicts(dm)

    dm.flush_on_exit()

    assert conflicts == []
    assert _conflict_copies(tmp_path) == []
    study = _read(tmp_path / "study.json")
    assert [s["id"] for s in study["subjects"]] == ["math", "english", "politics", "cs408"]
    assert study["target_date"]


def test_every_model_self_heal_is_saved_without_conflict(qapp, tmp_path) -> None:
    """⭐ `_models()` 全部模型：内存领先磁盘（自愈）→ 安全落盘，零冲突。

    修复必须落在统一退出判定上，而不是只特判 expenses / inventory ——
    以后新增模型也自动享受同一语义。
    """
    dm = DataManager(tmp_path)
    conflicts = _collect_conflicts(dm)
    for model, name in dm._models():
        model.data["_exit_flush_probe"] = name

    dm.flush_on_exit()

    assert conflicts == []
    for model, name in dm._models():
        assert _read(model.file_path)["_exit_flush_probe"] == name


def test_external_change_to_healed_file_still_conflicts(qapp, tmp_path) -> None:
    """同一文件既有启动自愈、又被外部改过 → 仍按真实冲突处理，不覆盖外部内容。"""
    _write(tmp_path / "expenses.json", LEGACY_EXPENSES)
    dm = DataManager(tmp_path)
    path = tmp_path / "expenses.json"
    external = _read(path)
    external["records"].append({"id": "e_ext", "amount": 99, "category": "food",
                                "date": "2026-11-02"})
    _write(path, external)

    conflicts = _collect_conflicts(dm)
    dm.flush_on_exit()

    assert [name for name, _ in conflicts] == ["expenses"]
    on_disk = _read(path)
    assert [r["id"] for r in on_disk["records"]] == ["e_001", "e_ext"], "外部改动必须保留"
    copies = _conflict_copies(tmp_path)
    assert len(copies) == 1
    ours = _read(copies[0])
    assert [r["id"] for r in ours["records"]] == ["e_001"], "副本是我们内存里的版本"
    assert any(c["id"] == "subscription" for c in ours["categories"])


def test_corrupt_file_is_never_overwritten_on_exit(qapp, tmp_path) -> None:
    """运行期间文件被写坏 → 退出仍拒绝覆盖，现场保留并留冲突副本。"""
    dm = DataManager(tmp_path)
    path = tmp_path / "inventory.json"
    dm.inventory.add_item({"name": "纸巾", "quantity": 1})
    dm.inventory.save()
    path.write_text("{ 这不是 JSON", encoding="utf-8")

    conflicts = _collect_conflicts(dm)
    dm.flush_on_exit()

    assert path.read_text(encoding="utf-8") == "{ 这不是 JSON", "损坏现场必须保留"
    assert [name for name, _ in conflicts] == ["inventory"]
    assert _conflict_copies(tmp_path)


def test_no_disk_baseline_is_treated_as_conflict(qapp, tmp_path) -> None:
    """没有磁盘基线（`_disk_fingerprint is None`）而文件存在 → 禁止直接覆盖。"""
    dm = DataManager(tmp_path)
    path = tmp_path / "inventory.json"
    dm.inventory.add_item({"name": "纸巾"})
    dm.inventory.save()
    dm.inventory._disk_fingerprint = None          # 模拟基线丢失
    dm.inventory.add_item({"name": "我方加的"})

    conflicts = _collect_conflicts(dm)
    dm.flush_on_exit()

    assert [it["name"] for it in _read(path)["items"]] == ["纸巾"], "没有基线时禁止覆盖"
    assert [name for name, _ in conflicts] == ["inventory"]


def test_offscreen_mainwindow_quit_with_legacy_files_is_silent(
        qapp, tmp_path, monkeypatch) -> None:
    """⭐ E2E：真实 `MainWindow` 启动链 + 离屏，预置旧版文件 → 退出无提示、无副本。

    不直接用 `App`：它要求独占 `QApplication`（pytest 会话已有一个），还会写注册表
    并创建托盘 —— 离屏环境不可用。这里走与 `scripts/ui_walkthrough.py` 相同的
    `DataManager` + `SettingsManager` + `AIService` + `MainWindow` 启动链，
    并把 `save_conflict` 接到与 `App._on_save_conflict` 相同的 `QMessageBox.warning`。
    """
    from PySide6.QtWidgets import QMessageBox

    from src.services.settings_manager import SettingsManager
    from src.ui.main_window import MainWindow

    _write(tmp_path / "expenses.json", LEGACY_EXPENSES)
    _write(tmp_path / "inventory.json", LEGACY_INVENTORY)
    _write(tmp_path / "study.json", LEGACY_STUDY)

    warnings: list[tuple] = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warnings.append(a)))

    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    dm = DataManager(tmp_path)
    window = MainWindow(settings, dm, None)
    dm.save_conflict.connect(
        lambda name, path: QMessageBox.warning(window, "conflict", f"{name}:{path}"))

    window.show()
    qapp.processEvents()
    for key in list(window._workspace._panel_map):
        window._on_sidebar_nav(key)                 # 触发各面板的懒加载自愈
    qapp.processEvents()

    dm.flush_on_exit()                              # 与 `App.quit()` 相同的退出落盘
    window.shutdown()
    qapp.processEvents()

    assert warnings == []
    assert _conflict_copies(tmp_path) == []
