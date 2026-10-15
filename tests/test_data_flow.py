"""数据流回归：外部写入就地刷新 + save_all 覆盖面。

两个真实缺陷：

1. **TG/外部写入不刷新非课程面板**：`_auto_reload` 广播的是 `external`，
   而 `MainWorkspace._on_data_changed` 按域名字符串匹配（`"task" in "external"` 为假），
   于是作业/习惯/考试/记账/库存面板要等切页才更新 —— README 宣称的"TG 写入即时可见"不成立。
2. **`save_all()` 漏 exams / inventory**：退出或重启时未显式落盘的考试与库存改动会丢。
"""

import json
import time

from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager
from src.ui.components.main_workspace import MainWorkspace


def _workspace(tmp_path) -> tuple[DataManager, MainWorkspace]:
    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    return dm, MainWorkspace(settings, AIService(settings, dm), dm, None)


def _external_append(path, key, item) -> None:
    """模拟 TG bot / 其它进程直接改文件。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault(key, []).append(item)
    time.sleep(0.25)                      # 让 mtime 与 DataManager 记录的差值 > 0.1s
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_external_write_refreshes_task_panel_in_place(tmp_path, qapp) -> None:
    dm, ws = _workspace(tmp_path)
    dm.tasks.add({"title": "原有作业", "due_date": "2026-01-01T23:00:00"})
    dm.tasks.save()
    dm.reload_all()

    ws._task_panel._status_filter = "all"
    ws.switch_to("tasks")
    assert ws._task_panel._table.rowCount() == 1

    _external_append(tmp_path / "tasks.json", "tasks", {
        "id": "t_999", "title": "TG 写入的作业", "due_date": "2026-01-02T23:00:00",
        "status": "pending", "course_name": "", "tags": [],
    })
    dm._auto_reload()

    assert any(t["id"] == "t_999" for t in dm.tasks.tasks), "模型应已重载"
    assert ws._task_panel._table.rowCount() == 2, "外部写入后面板应就地刷新"


def test_external_write_refreshes_exam_and_inventory_panels(tmp_path, qapp) -> None:
    dm, ws = _workspace(tmp_path)
    fired: list[str] = []
    for panel, key in ((ws._exam_panel, "exam"), (ws._inventory_panel, "inventory")):
        original = panel._refresh
        panel._refresh = lambda _p=original, _k=key: (fired.append(_k), _p())[1]

    dm.data_changed.emit("external")

    assert sorted(fired) == ["exam", "inventory"], fired


def test_domain_change_only_refreshes_that_panel(tmp_path, qapp) -> None:
    """域名字符串的单域广播不应连带刷其它面板（保持增量刷新的意义）。"""
    dm, ws = _workspace(tmp_path)
    fired: list[str] = []
    for panel, key in ((ws._task_panel, "task"), (ws._exam_panel, "exam"),
                       (ws._habit_panel, "habit"), (ws._expense_panel, "expense"),
                       (ws._inventory_panel, "inventory")):
        original = panel._refresh
        panel._refresh = lambda _p=original, _k=key: (fired.append(_k), _p())[1]

    dm.data_changed.emit("task")

    assert fired == ["task"], fired


def test_save_all_writes_every_model(tmp_path, qapp) -> None:
    dm, _ws = _workspace(tmp_path)
    dm.exams.add_exam({"course_name": "线性代数", "exam_date": "2026-12-11"})
    dm.inventory.add_item({"name": "纸巾", "quantity": 3})
    dm.daily_logs.add_plan({"title": "复习", "time_slot": 3}, day="2026-11-11")

    dm.save_all()

    def _disk(name) -> dict:
        return json.loads((tmp_path / name).read_text(encoding="utf-8"))

    assert any(e["course_name"] == "线性代数" for e in _disk("exams.json")["exams"])
    assert any(i["name"] == "纸巾" for i in _disk("inventory.json")["items"])
    assert any(p["title"] == "复习" for p in _disk("daily_logs.json")["plans"]["2026-11-11"])


def test_auto_reload_reminder_recomputes_ddl_on_external(tmp_path, qapp) -> None:
    """外部改动后 DDL 计数也要重算（原先只认 "task" 域）。"""
    from src.services.reminder_service import ReminderService

    dm, _ws = _workspace(tmp_path)
    rem = ReminderService(SettingsManager(tmp_path / "settings.ini"), dm)
    counts: list[int] = []
    rem.ddl_alert.connect(counts.append)

    rem.start()                     # 连接 data_changed + 首轮检查
    counts.clear()

    dm.data_changed.emit("external")
    assert counts, "外部改动应触发一次 DDL 重算"
