"""快速安排的撤销范围（审查 2026-10-17 #3）。

旧实现：`copy2` 备份整份 `daily_logs.json`，撤销时整份覆盖 —— 会把安排之后产生的
打卡记录（`logs`）与自定义提醒（`reminders`）一起回滚，还绕开原子写。
现在：只记 `plans` 快照；撤销只写回 `plans`，且校验"期间没人动过 plans"。
"""

import copy
from typing import ClassVar

import src.ui.widgets.schedule_actions as actions_module
from src.services.data_manager import DataManager
from src.ui.widgets.schedule_view import ScheduleView

DAY = "2026-11-11"
PLAN = {"title": "安排前", "time_slot": 1}


class _StubBox:
    """替掉 `QMessageBox`：测试里弹模态框会直接挂住。

    ⚠ 要 patch `schedule_actions` 里的那个 —— 回滚逻辑搬过去了，`schedule_view`
    自己那份只在异常分支用得到。
    """

    calls: ClassVar[list[str]] = []

    @classmethod
    def information(cls, *args: object, **kwargs: object) -> None:
        cls.calls.append("info")

    @classmethod
    def warning(cls, *args: object, **kwargs: object) -> None:
        cls.calls.append("warn")


def _view(tmp_path) -> tuple[ScheduleView, DataManager]:
    dm = DataManager(tmp_path)
    return ScheduleView(dm), dm


def test_quick_arrange_snapshots_only_plans(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(actions_module, "QMessageBox", _StubBox)
    sv, dm = _view(tmp_path)
    dm.daily_logs.add_plan(dict(PLAN), day=DAY)
    sv._build_snapshot = lambda days=3: "snapshot"     # 跳过真实快照构建

    sv._quick_arrange(days=1)

    plans = dm.daily_logs.data.get("plans", {})
    assert sv._arrange_before == plans
    assert sv._arrange_before is not plans, "必须是深拷贝，不能是引用"
    assert sv._arrange_before[DAY][0]["title"] == "安排前"
    assert sv._arrange_after is None


def test_undo_rolls_back_plans_only(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(actions_module, "QMessageBox", _StubBox)
    _StubBox.calls.clear()
    sv, dm = _view(tmp_path)
    dm.daily_logs.add_plan(dict(PLAN), day=DAY)
    before = copy.deepcopy(dm.daily_logs.data.get("plans", {}))

    # 模拟"安排"：AI 改了 plans；期间用户还打了一次卡（logs）
    dm.daily_logs.data["plans"] = {DAY: [{"title": "安排后", "time_slot": 2}]}
    dm.daily_logs.set_log(DAY, {"habits": {"h_001": True}})
    dm.daily_logs.save()

    sv._arrange_before = before
    sv._arrange_after = copy.deepcopy(dm.daily_logs.data.get("plans", {}))
    sv._undo_arrange()

    data = dm.daily_logs.data
    assert data["plans"] == before, "plans 应回滚到安排前"
    assert data["logs"].get(DAY), "打卡记录不该被回滚"


def test_undo_refuses_when_plans_changed_since_arrange(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(actions_module, "QMessageBox", _StubBox)
    _StubBox.calls.clear()
    sv, dm = _view(tmp_path)
    dm.daily_logs.add_plan(dict(PLAN), day=DAY)
    sv._arrange_before = copy.deepcopy(dm.daily_logs.data.get("plans", {}))
    dm.daily_logs.save()
    sv._arrange_after = copy.deepcopy(dm.daily_logs.data.get("plans", {}))

    # 安排之后又有人手动改了 plans
    dm.daily_logs.data["plans"] = {DAY: [{"title": "别人改的", "time_slot": 3}]}
    dm.daily_logs.save()

    sv._undo_arrange()

    assert "warn" in _StubBox.calls, "应提示并拒绝"
    assert dm.daily_logs.data["plans"] == {DAY: [{"title": "别人改的", "time_slot": 3}]}, \
        "拒绝时不得写盘"
