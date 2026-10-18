"""日程「已完成」：数据 + 卡片 + 右键菜单（用户用例表第 10 条的 UI 侧）。

背景：`complete_plan` 命令（AI 侧）先落地了，但界面**看不出**哪条做完了；
而且右键的「标记完成」以前直接**删掉**那条计划（看不出做过什么）。现在：
`done` 标记驱动卡片样式（✅ + 变灰 + 删除线），菜单给「标记完成 / 标记未完成」。
"""

from datetime import date

from PySide6.QtWidgets import QLabel

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors
from src.ui.widgets.schedule_actions import set_plan_done
from src.ui.widgets.schedule_view import ScheduleView

TODAY = date.today().isoformat()


def _view(tmp_path) -> tuple[ScheduleView, DataManager]:
    dm = DataManager(tmp_path)
    return ScheduleView(dm), dm


def _labels(widget) -> str:
    return " ".join(w.text() for w in widget.findChildren(QLabel))


def test_model_toggle_done_and_back(tmp_path) -> None:
    dm = DataManager(tmp_path)
    dm.daily_logs.add_plan({"title": "整理扑克牌", "time_slot": 2}, day=TODAY)

    assert dm.daily_logs.set_plan_done(TODAY, 0, True) is True
    plan = dm.daily_logs.get_plans(TODAY)[0]
    assert plan["done"] is True and plan["completed_at"]

    assert dm.daily_logs.set_plan_done(TODAY, 0, False) is True
    plan = dm.daily_logs.get_plans(TODAY)[0]
    assert plan["done"] is False
    assert "completed_at" not in plan, "取消完成要连完成时间一起去掉"

    assert dm.daily_logs.set_plan_done(TODAY, 9, True) is False, "越界返回 False"


def test_set_plan_done_matches_by_content(tmp_path) -> None:
    """菜单只有卡片上的 item，靠**内容**回找那一条计划（和删除同一条路）。"""
    dm = DataManager(tmp_path)
    dm.daily_logs.add_plan({"title": "整理扑克牌", "time_slot": 2}, day=TODAY)
    item = {"plan": dm.daily_logs.get_plans(TODAY)[0]}

    assert set_plan_done(dm, date.today(), item, True) is True
    assert dm.daily_logs.get_plans(TODAY)[0]["done"] is True

    assert set_plan_done(dm, date.today(), {"plan": {"title": "不存在的"}}, True) is False


def test_done_plan_card_shows_check_and_strikethrough(qapp, tmp_path) -> None:
    sv, _ = _view(tmp_path)
    c = get_colors()

    slot_data: dict[int, list[dict]] = {i: [] for i in range(1, 7)}
    sv._add_plan_to_slots(slot_data, {"title": "整理扑克牌", "time_slot": 2, "done": True})
    assert slot_data[2][0]["done"] is True, "「已完成」要跟着 item 传到卡片层"

    done_card = sv._create_plan_item(slot_data[2][0], c)
    text = _labels(done_card)
    assert "✅" in text and "整理扑克牌" in text

    title = next(w for w in done_card.findChildren(QLabel) if "整理扑克牌" in w.text())
    assert "line-through" in title.styleSheet(), "已完成要划掉"

    # 未完成的仍是原样（📅 / 🔄 前缀，不划线）
    sv._add_plan_to_slots(slot_data, {"title": "复习", "time_slot": 2})
    todo_card = sv._create_plan_item(slot_data[2][1], c)
    todo_title = next(w for w in todo_card.findChildren(QLabel) if "复习" in w.text())
    assert "line-through" not in todo_title.styleSheet()
    assert "✅" not in _labels(todo_card)
