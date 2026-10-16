"""日程的 日/周 切换与周视图「事项行」（合并 B）。

背景：课程表原来是独立导航项，且**只有课程块** —— 没课的日子一片空白，
用户会以为"这周什么都没有"，而实际上有作业截止、考试、日程计划。
现在：课程表并入「日程」，顶部 日/周 切换；周视图末行列出每天的事项。
"""

from datetime import date, timedelta

from src.services.data_manager import DataManager
from src.ui.widgets.schedule_view import ScheduleView


def _monday() -> date:
    today = date.today()
    return today - timedelta(days=today.isoweekday() - 1)


def _view(tmp_path) -> tuple[ScheduleView, DataManager]:
    dm = DataManager(tmp_path)
    return ScheduleView(dm), dm


def test_default_mode_is_day(qapp, tmp_path) -> None:
    sv, _ = _view(tmp_path)
    assert sv.view_mode == "day"
    assert sv._stack.currentIndex() == 0


def test_switch_between_day_and_week(qapp, tmp_path) -> None:
    sv, _ = _view(tmp_path)

    sv._set_mode("week")
    assert sv.view_mode == "week"
    assert sv._stack.currentIndex() == 1
    # 日视图专属控件（日期导航 / 调整）在周视图里隐藏
    # 用 isHidden()（显式隐藏标志）而不是 isVisible()：后者要求整条祖先链都可见
    assert all(b.isHidden() for b in sv._nav_buttons)
    assert sv._arrange_btn.isHidden()

    sv._set_mode("day")
    assert sv._stack.currentIndex() == 0
    assert not sv._arrange_btn.isHidden()


def test_week_view_lists_ddl_exam_and_plan(qapp, tmp_path) -> None:
    """周视图的"事项行"必须把当天的 DDL / 考试 / 计划都列出来。"""
    monday = _monday()
    sv, dm = _view(tmp_path)
    dm.tasks.add({"title": "习题一", "due_date": monday.isoformat()})
    dm.exams.add_exam({"course_name": "高等数学",
                       "exam_date": (monday + timedelta(days=2)).isoformat()})
    dm.daily_logs.add_plan({"title": "复习", "time_slot": 3},
                           day=(monday + timedelta(days=1)).isoformat())

    panel = sv.course_panel
    sv._set_mode("week")
    markers = panel._collect_markers(panel._week_number)

    assert "习题一" in " ".join(markers[1])          # 周一：作业截止
    assert "复习" in " ".join(markers[2])            # 周二：计划
    assert "高等数学" in " ".join(markers[3])        # 周三：考试

    table = panel.table
    assert not table.isRowHidden(table._marker_row)
    assert table.rowCount() == table.period_count + 1


def test_marker_row_hidden_when_week_is_empty(qapp, tmp_path) -> None:
    sv, _ = _view(tmp_path)
    sv._set_mode("week")
    table = sv.course_panel.table
    assert table.isRowHidden(table._marker_row)


def test_week_view_survives_theme_refresh(qapp, tmp_path) -> None:
    """换主题时周视图要重建（块与事项行的颜色是写死的）。"""
    monday = _monday()
    sv, dm = _view(tmp_path)
    dm.tasks.add({"title": "习题一", "due_date": monday.isoformat()})
    sv._set_mode("week")
    sv.refresh_theme()
    table = sv.course_panel.table
    assert not table.isRowHidden(table._marker_row)


def test_course_panel_is_reachable_from_workspace(qapp, tmp_path) -> None:
    """课程表不再是独立面板，但仍要有入口（菜单/测试用）。"""
    from src.services.ai_service import AIService
    from src.services.settings_manager import SettingsManager
    from src.ui.components.main_workspace import MainWorkspace

    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    dm = DataManager(tmp_path)
    ws = MainWorkspace(settings, AIService(settings, dm), dm, None)

    assert "courses" not in ws._panel_map          # 独立面板已取消
    assert ws.course_panel is ws._schedule_view.course_panel
    assert ws.course_panel.table is not None
