"""考研备考面板的离屏冒烟：构造 / 统计 / 复习按钮。"""

from datetime import date, timedelta

from src.services.data_manager import DataManager
from src.ui.panels.study_panel import StudyPanel


def _panel(tmp_path, qapp) -> tuple[StudyPanel, DataManager, str]:
    dm = DataManager(tmp_path)
    dm.study.set_target("2027-12-25")
    dm.study.set_daily_goal(200)
    today = date.today()
    dm.study.add_session("math", 100, day=today)
    dm.study.add_session("cs408", 80, day=today)
    mid = dm.study.add_mistake("math", "极限", day=today - timedelta(days=3))
    dm.study.add_mock("math", 110, day=today)
    dm.study.save()
    return StudyPanel(dm), dm, mid


def test_panel_builds_and_shows_summary(tmp_path, qapp) -> None:
    panel, _dm, _mid = _panel(tmp_path, qapp)
    assert "180" in panel._stat_labels["today"].text()
    assert "1" in panel._stat_labels["due"].text()
    assert "110/150" in panel._stat_labels["mock"].text()
    assert "2027-12-25" in panel._countdown.text()


def test_panel_review_button_advances_mistake(tmp_path, qapp) -> None:
    panel, dm, mid = _panel(tmp_path, qapp)
    panel._review(mid)
    mistake = next(m for m in dm.study.mistakes if m["id"] == mid)
    assert mistake["stage"] == 1
    assert mistake["reviewed_count"] == 1


def test_panel_refresh_theme_does_not_crash(tmp_path, qapp) -> None:
    panel, _dm, _mid = _panel(tmp_path, qapp)
    panel.refresh_theme()
    assert panel._stat_labels["today"].text()
