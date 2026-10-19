"""时段卡片的**顺序**必须始终按节次 —— 2026-10-19 审查 R5 的回归。

病根：`_refresh_day` 是 hash **增量**刷新（内容没变的时段跳过重建），但重建的卡片一律
`insertWidget(count - 1)`，也就是**插到末尾**。切分类筛选只改变其中一部分时段 →
被重建的那几张跑到时间轴后面去（原生运行实测 `[1,2,3,4,5]` 变 `[2,3,4,5,1]`，
批量截图里还出现过 `[3,4,1,2,5]`）。

所以这里断言的是**布局里控件的实际顺序**，不是"筛选后还能不能看到目标文本"。
"""

from datetime import date

from src.services.data_manager import DataManager
from src.ui.widgets.schedule_view import ScheduleView

TODAY = date.today().isoformat()


def _order(view: ScheduleView) -> list[int]:
    """按布局实际顺序列出各时段卡片的 period。"""
    out: list[int] = []
    for i in range(view._content_layout.count()):
        widget = view._content_layout.itemAt(i).widget()
        for period, card in view._slot_cards.items():
            if card is widget:
                out.append(period)
    return out


def _seeded_view(tmp_path) -> tuple[ScheduleView, DataManager]:
    dm = DataManager(tmp_path)
    # 第 1 段是学习类（带课程）、第 2 段生活类、第 3 段学习类 —— 切分类时只变一部分
    dm.daily_logs.add_plan({"title": "复习英语", "time_slot": 1, "course_name": "英语"}, TODAY)
    dm.daily_logs.add_plan({"title": "整理桌面", "time_slot": 2}, TODAY)
    dm.daily_logs.add_plan({"title": "写实验报告", "time_slot": 3, "type": "course_note"}, TODAY)
    dm.daily_logs.save()
    return ScheduleView(dm), dm


def test_slot_order_is_period_order_on_first_build(qapp, tmp_path) -> None:
    view, _ = _seeded_view(tmp_path)
    order = _order(view)
    assert order and order == sorted(order), f"初次构建就乱序：{order}"


def test_slot_order_survives_category_filter_change(qapp, tmp_path) -> None:
    """⭐ 切分类 → 只有一部分时段内容变（其余被增量保留）→ 顺序不许乱。"""
    view, _ = _seeded_view(tmp_path)
    for mode in ("life", "study", "all", "life", "all"):
        view._category_filter._pick(mode)
        order = _order(view)
        assert order == sorted(order), f"切到 {mode} 后乱序：{order}"


def test_slot_order_survives_a_single_slot_update(qapp, tmp_path) -> None:
    """⭐ 只改一个时段的内容（hash 变化 → 只重建那一张）→ 顺序不许乱。"""
    view, dm = _seeded_view(tmp_path)
    dm.daily_logs.set_plan_done(TODAY, 0, True)
    view._refresh()
    order = _order(view)
    assert order == sorted(order), f"单时段更新后乱序：{order}"


def test_slot_order_survives_current_slot_highlight_change(qapp, tmp_path) -> None:
    """⭐ 当前时段高亮变化（也是"只重建一张"）→ 顺序不许乱。"""
    view, _ = _seeded_view(tmp_path)
    view._current_period_override = 2          # 让"当前时段"从别处变到第 2 段
    view._refresh()
    order = _order(view)
    assert order == sorted(order), f"高亮变化后乱序：{order}"
