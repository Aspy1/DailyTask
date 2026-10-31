"""2026-10-31 审查的回归测试（核心数据 + UI 接线）。"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from src.models.task import TaskModel
from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.services.git_sync import GitSync
from src.services.settings_manager import SettingsManager
from src.ui.panels.task_panel import TaskPanel
from src.ui.widgets.schedule_slots import add_course_to_slots, add_habit_to_slots
from src.ui.widgets.schedule_view import ScheduleView, slot_content_hash

# ── 数据层 ──────────────────────────────────────────────────

def test_task_auto_archive_is_persisted(tmp_path) -> None:
    """⭐ 启动时的自动归档必须落盘。

    旧实现只改内存；退出时 `flush_on_exit()` 把差异当成"外部改动"→ 写冲突副本，
    真正的归档永远不生效（而且每次退出都多一份无用的副本）。
    """
    path = tmp_path / "tasks.json"
    old = (datetime.now() - timedelta(days=4)).isoformat()
    path.write_text(json.dumps({
        "_version": 2,
        "tasks": [{"id": "t_001", "title": "旧作业", "status": "completed",
                   "completed_at": old}],
        "archived": [],
    }, ensure_ascii=False), encoding="utf-8")

    model = TaskModel(path)
    assert model.tasks == []
    assert [t["id"] for t in model.archived] == ["t_001"]

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["tasks"] == [], "归档没有落盘"
    assert [t["id"] for t in on_disk["archived"]] == ["t_001"]


def test_model_saves_after_actions_created_the_file(sandbox: Path) -> None:
    """⭐ 回归：`actions.py` 写的文件缺 `_version`，模型补默认值后**指纹必须仍与磁盘一致**。

    走查实测：旧实现先补 `_version` 再算指纹 → 第一次 UI 保存被误判成"外部改动"，
    写了冲突副本、用户改动没落盘。
    """
    from scripts.actions import run_in_process
    from src.models.task import DEFAULT_TASKS

    assert run_in_process('add_task --title "图论作业" --due 2026-12-01').startswith("OK")
    dm = DataManager(sandbox)
    assert dm.tasks.save() is True, "actions 写的文件不能被误判为外部改动"
    on_disk = json.loads((sandbox / "semesters" / "sem_default" / "tasks.json")
                         .read_text(encoding="utf-8"))
    assert on_disk["_version"] == DEFAULT_TASKS["_version"]


def test_actions_save_writes_schema_version(sandbox: Path) -> None:
    """所有 CLI 写入都必须带 schema 版本（否则模型/备份口径不一致）。"""
    from scripts.actions import run_in_process

    run_in_process('add_expense --amount 10 --category food')
    data = json.loads((sandbox / "expenses.json").read_text(encoding="utf-8"))
    assert data["_version"] == 1


def test_flush_does_not_treat_missing_version_as_conflict(tmp_path) -> None:
    """旧文件没有 `_version`：退出时不能因此写一份无用的冲突副本。"""
    data = tmp_path / "data"
    semester = data / "semesters" / "sem_default"
    semester.mkdir(parents=True)
    (semester / "tasks.json").write_text(
        json.dumps({"tasks": [], "archived": []}), encoding="utf-8")
    dm = DataManager(data)
    dm.flush_on_exit()
    assert not list((data / "backup" / "save_conflict").glob("tasks.*.json"))


def test_gitsync_clears_finished_worker(tmp_path, qapp) -> None:
    """⭐ 同步完成后必须清 `_worker`：它同时连着 deleteLater，下次 isRunning() 会访问野指针。"""
    data = tmp_path / "data"
    data.mkdir()
    (data / ".git").mkdir()
    sync = GitSync(data, data)
    sync._worker = object()              # 模拟"上一个 worker 还在"
    sync._on_done(True, "", "pushed")
    assert sync._worker is None


def test_ai_service_rejects_concurrent_message(qapp, tmp_path) -> None:
    """⭐ 忙时拒绝第二条：旧实现直接覆盖 `_thread`，正在跑的 QThread 可能被 GC。"""
    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    svc = AIService(settings, dm)
    errors: list[str] = []
    svc.error_occurred.connect(errors.append)

    svc._busy = True
    svc.send_message("第二条")
    assert errors and "上一条" in errors[-1]
    assert svc._history == [], "忙时不该把消息写进历史"


def test_prompt_cache_invalidates_when_content_changes(qapp, tmp_path) -> None:
    """⭐ 缓存键必须是内容指纹：只改标题/金额（长度不变）也要重建提示词。"""
    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    svc = AIService(settings, dm)
    svc._weather_cache = {"value": "  晴 20°C", "fetched_at": time.time()}
    svc._ds_balance_cache = {"value": "", "fetched_at": time.time()}

    dm.habits.add_habit({"name": "跑步"})
    first = svc._build_system_prompt()
    assert "跑步" in first

    dm.habits.habits[0]["name"] = "游泳"   # 长度相同
    second = svc._build_system_prompt()
    assert second != first
    assert "游泳" in second


# ── 日程视图 ────────────────────────────────────────────────

class _FakeHabits:
    @staticmethod
    def is_done_today(_hid: str) -> bool:
        return True

    @staticmethod
    def is_active_today(_hid: str) -> bool:
        return True


class _FakeDM:
    habits = _FakeHabits()


def test_course_slot_uses_slot_location() -> None:
    """教室存在 `time_slots[].location`，日视图必须显示它（旧实现只读 course["location"]）。"""
    slots = {i: [] for i in range(1, 7)}
    add_course_to_slots(slots, {
        "name": "算法", "location": "",
        "time_slots": [{"start": 2, "end": 2, "location": "33楼310"}],
    })
    assert slots[2][0]["location"] == "33楼310"


def test_habit_slot_carries_done_status() -> None:
    slots = {i: [] for i in range(1, 7)}
    add_habit_to_slots(slots, {"id": "h_001", "name": "跑步", "reminder_time": "07:00"},
                       _FakeDM())
    assert slots[1][0]["done"] is True


def test_day_view_hash_includes_done() -> None:
    base = [{"type": "plan", "title": "复习", "done": False}]
    done = [{"type": "plan", "title": "复习", "done": True}]
    assert slot_content_hash(base, [], False) != slot_content_hash(done, [], False)


def test_schedule_fill_action_emits_prompt(qapp, tmp_path) -> None:
    """⭐ 课程右键「布置了作业」必须真的把 prompt 发出去（旧实现发的是 data_changed:fill_prompt:）。"""
    dm = DataManager(tmp_path)
    view = ScheduleView(dm)
    seen: list[str] = []
    view.fill_ai_prompt.connect(seen.append)

    view._handle_course_action("fill", "布置了作业", {
        "course": {"name": "算法", "day_of_week": 1,
                   "time_slots": [{"start": 1, "end": 2}]}})
    assert seen and "算法" in seen[0] and "布置了作业" in seen[0]


def test_task_filter_by_course_refreshes_table(qapp, tmp_path) -> None:
    """⭐ 从课程表点「查看事项」后，任务面板要真的筛过（旧实现只改了筛选状态）。"""
    dm = DataManager(tmp_path)
    dm.tasks.add({"title": "算法作业", "course_name": "算法", "due_date": "2026-12-01"})
    dm.tasks.add({"title": "物理作业", "course_name": "物理", "due_date": "2026-12-02"})
    panel = TaskPanel(dm)

    panel.filter_by_course("算法")
    assert panel._table.rowCount() == 1


def test_attached_task_dialog_no_longer_crashes(qapp) -> None:
    """⭐ 旧实现复制了父类的「关联物品」UI，却调用不存在的方法 → 打开即 AttributeError。"""
    from src.ui.panels.habit_dialogs import _AttachedTaskDialog

    dlg = _AttachedTaskDialog()
    assert dlg._save_template is False
    assert not hasattr(dlg, "_refresh_linked")
