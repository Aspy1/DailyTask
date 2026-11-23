"""方案 A-3：刷新合并（`MD-files/PERFORMANCE_WORKFLOW.md` §3.1-3）。

**验收口径**：一次操作广播 N 个事件时，面板只重画 1 次；且**语义不变**
（最终看到的是最新数据、该刷的面板一个不少、跨轮次的事件不合并）。
"""


from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager
from src.ui.components.main_workspace import MainWorkspace
from src.ui.components.refresh_coalescer import RefreshCoalescer


class _Plugins:
    def list_plugins(self) -> list:
        return []

    def is_enabled(self, _name: str) -> bool:
        return False

    def toggle(self, _name: str, _enabled: bool) -> None:
        return None


def _workspace(tmp_path) -> MainWorkspace:
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    return MainWorkspace(settings, DataManager(tmp_path), _Plugins())


def _drain(app) -> None:
    """跑到事件队列清空（`singleShot(0)` 的刷新会在这里执行）。"""
    for _ in range(6):
        app.processEvents()


# ── 合并器本身 ─────────────────────────────────────────────

def test_coalescer_batches_same_round_events(qapp) -> None:
    """⭐ 同一轮里的 3 个事件 → 只应用 1 次。"""
    seen: list[list[str]] = []
    coalescer = RefreshCoalescer(seen.append)

    for event in ("task", "task_status", "task"):
        coalescer.request(event)
    _drain(qapp)

    assert len(seen) == 1, seen
    assert seen[0] == ["task", "task_status"], "重复事件要去重，顺序保留"


def test_coalescer_keeps_separate_rounds_separate(qapp) -> None:
    """跨轮次不合并（两次独立操作必须各刷一次）。"""
    seen: list[list[str]] = []
    coalescer = RefreshCoalescer(seen.append)

    coalescer.request("task")
    _drain(qapp)
    coalescer.request("expense")
    _drain(qapp)

    assert seen == [["task"], ["expense"]], seen


def test_coalescer_survives_a_failing_apply(qapp, caplog) -> None:
    """刷新本身抛异常不能把事件循环卡死（下一条事件照常处理）。"""
    calls: list[list[str]] = []

    def boom(events: list[str]) -> None:
        calls.append(events)
        raise RuntimeError("刷新失败")

    coalescer = RefreshCoalescer(boom)
    coalescer.request("task")
    _drain(qapp)
    coalescer.request("task")
    _drain(qapp)

    assert len(calls) == 2, "失败后仍能继续接收后续事件"
    coalescer.request("expense")
    _drain(qapp)
    assert coalescer.apply_count == 3


# ── 接到工作区上：行为不变、次数下降 ────────────────────────

def test_burst_of_events_refreshes_the_panel_once(tmp_path, qapp, monkeypatch) -> None:
    """⭐ 批量事件连发（`ai_action` + `ai_undo`）→ 面板只重建 1 次。

    ⚠ 单域事件（`task`）是**同步**刷的（用户点完就要看到结果），不走合并；
    这里测的是合并器覆盖的那类批量广播。
    """
    ws = _workspace(tmp_path)
    ws.switch_to("tasks")                       # 先把面板建出来
    refreshes = {"n": 0}
    panel = ws._built["tasks"]
    original = panel._rebuild_rows

    def counting() -> None:
        refreshes["n"] += 1
        original()

    monkeypatch.setattr(panel, "_rebuild_rows", counting)

    ws._dm.data_changed.emit("ai_action")
    ws._dm.data_changed.emit("ai_action")
    ws._dm.data_changed.emit("ai_undo")
    _drain(qapp)

    assert refreshes["n"] == 1, f"同一轮被刷了 {refreshes['n']} 次"


def test_single_domain_event_refreshes_synchronously(tmp_path, qapp, monkeypatch) -> None:
    """⭐ 单域事件**当场**刷新（不推迟到下一轮）—— 用户点完就该看到结果。"""
    ws = _workspace(tmp_path)
    ws.switch_to("tasks")
    hits: list[int] = []
    panel = ws._built["tasks"]
    monkeypatch.setattr(panel, "_refresh", lambda *a, **k: hits.append(1))

    ws._dm.data_changed.emit("task")

    assert hits == [1], "同步刷新：emit 返回时就该已经刷过"


def test_coalesced_refresh_still_shows_latest_data(tmp_path, qapp) -> None:
    """合并不等于"跳过"：合并后的那次刷新必须看到**最新数据**。"""
    ws = _workspace(tmp_path)
    ws.switch_to("tasks")
    ws._dm.tasks.add({"title": "新作业"})
    ws._dm.tasks.save()

    ws._dm.data_changed.emit("task")
    _drain(qapp)

    assert ws._task_panel._table.rowCount() == 1


def test_other_domains_are_not_lost_when_merged(tmp_path, qapp, monkeypatch) -> None:
    """合并后该刷的面板一个不少（`task` + `expense` 都要刷）。"""
    ws = _workspace(tmp_path)
    ws.switch_to("tasks")
    ws.switch_to("expenses")
    hits: list[str] = []
    monkeypatch.setattr(ws._built["tasks"], "_refresh",
                        lambda *a, **k: hits.append("task"))
    monkeypatch.setattr(ws._built["expenses"], "_refresh",
                        lambda *a, **k: hits.append("expense"))

    ws._dm.data_changed.emit("task")
    ws._dm.data_changed.emit("expense")
    _drain(qapp)

    assert sorted(hits) == ["expense", "task"], hits


def test_blanket_event_still_refreshes_everything(tmp_path, qapp, monkeypatch) -> None:
    """未登记 / 全刷事件（`external`）语义不变：所有面板都要刷。"""
    ws = _workspace(tmp_path)
    for key in ("tasks", "exams", "expenses", "inventory"):
        ws.switch_to(key)
    hits: list[str] = []
    for key in ("tasks", "exams", "expenses", "inventory"):
        monkeypatch.setattr(ws._built[key], "_refresh",
                            lambda *a, _k=key, **k: hits.append(_k))

    ws._dm.data_changed.emit("external")
    _drain(qapp)

    assert sorted(hits) == ["exams", "expenses", "inventory", "tasks"], hits
