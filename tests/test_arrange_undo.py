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


OTHER = "2026-11-12"


def test_undo_keeps_plans_added_during_arrange(qapp, tmp_path, monkeypatch) -> None:
    """审查 #4：等待 AI 期间用户给**别的日期**加的计划，撤销不许删掉它。"""
    monkeypatch.setattr(actions_module, "QMessageBox", _StubBox)
    _StubBox.calls.clear()
    sv, dm = _view(tmp_path)
    dm.daily_logs.add_plan(dict(PLAN), day=DAY)
    sv._arrange_before = copy.deepcopy(dm.daily_logs.data.get("plans", {}))
    sv._arrange_scope = (DAY,)                 # 本次安排只覆盖 DAY
    before_day = copy.deepcopy(sv._arrange_before.get(DAY))

    # 期间：AI 重写了 DAY；用户给另一天加了计划
    dm.daily_logs.data["plans"] = {
        DAY: [{"title": "安排后", "time_slot": 2}],
        OTHER: [{"title": "用户加的", "time_slot": 1}],
    }
    dm.daily_logs.save()
    sv._arrange_after = copy.deepcopy(dm.daily_logs.data.get("plans", {}))

    sv._undo_arrange()

    plans = dm.daily_logs.data["plans"]
    assert plans.get(DAY) == before_day, "安排覆盖的那天要回滚"
    assert plans.get(OTHER), "用户自己加的（无关日期）不许被删"


def test_undo_keeps_snapshot_when_save_is_rejected(qapp, tmp_path, monkeypatch) -> None:
    """审查 #4：撤销时写盘被拒（磁盘又被改动）→ 不许清掉撤销快照，让用户能重试。"""
    monkeypatch.setattr(actions_module, "QMessageBox", _StubBox)
    _StubBox.calls.clear()
    sv, dm = _view(tmp_path)
    dm.daily_logs.add_plan(dict(PLAN), day=DAY)
    sv._arrange_before = copy.deepcopy(dm.daily_logs.data.get("plans", {}))
    sv._arrange_scope = (DAY,)
    dm.daily_logs.save()
    sv._arrange_after = copy.deepcopy(dm.daily_logs.data.get("plans", {}))

    monkeypatch.setattr(dm.daily_logs, "save", lambda: False)   # 模拟"保存被拒"

    sv._undo_arrange()

    assert sv._arrange_before is not None, "保存被拒后快照必须保留"
