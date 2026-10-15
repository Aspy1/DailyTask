"""界面接线守卫：导航键与面板、菜单入口。

回归：侧边栏没有"更多"入口 → `MainWindow._show_more_menu`（唯一含
「切换主题」的地方）永远不可达，README 宣称的深浅色主题切换等于没有 UI 入口。
"""

import pytest


def test_sidebar_nav_keys_are_all_routed(qapp) -> None:
    """每个导航键要么是面板、要么由 MainWindow 特判；不能有点了没反应的键。"""
    from src.ui.components.sidebar import Sidebar

    routed_by_mainwindow = {"about", "more"}
    nav_keys = set(Sidebar()._nav_items)
    panel_keys = {"schedule", "courses", "tasks", "exams", "daily",
                  "expenses", "inventory", "meals", "settings"}

    assert nav_keys - panel_keys == routed_by_mainwindow, nav_keys


def test_mainwindow_routes_about_and_more(tmp_path, qapp, monkeypatch) -> None:
    """`about` / `more` 必须被 MainWindow 特判，不能当面板 key 丢给 switch_to。

    两个处理函数都会开模态对话框，测试里替换掉以记录调用（否则会一直等用户点击）。
    """
    from src.services.ai_service import AIService
    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager
    from src.ui.main_window import MainWindow

    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    mw = MainWindow(settings, AIService(settings, dm), dm, None)

    switched: list[str] = []
    routed: list[str] = []
    monkeypatch.setattr(mw._workspace, "switch_to", lambda key: switched.append(key))
    monkeypatch.setattr(mw, "_show_about", lambda: routed.append("about"))
    monkeypatch.setattr(mw, "_show_more_menu", lambda: routed.append("more"))

    for key in ("about", "more"):
        mw._sidebar._nav_items[key].click()

    assert routed == ["about", "more"], routed
    assert switched == [], f"about/more 不应触发面板切换：{switched}"




def test_theme_menu_is_reachable_from_sidebar(tmp_path, qapp, monkeypatch) -> None:
    from src.services.ai_service import AIService
    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager
    from src.ui.main_window import MainWindow

    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    mw = MainWindow(settings, AIService(settings, dm), dm, None)

    opened: list[bool] = []
    monkeypatch.setattr(mw, "_show_more_menu", lambda: opened.append(True))

    mw._sidebar._nav_items["more"].click()

    assert opened, "点侧边栏「更多」应打开含主题切换的菜单"
    assert "more" not in mw._workspace._panel_map, "more 不是面板，不该被 switch_to"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_switch_theme_updates_settings_and_qss(tmp_path, qapp, mode) -> None:
    from src.services.ai_service import AIService
    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager
    from src.ui.main_window import MainWindow

    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    mw = MainWindow(settings, AIService(settings, dm), dm, None)

    mw._switch_theme(mode)

    assert settings.get("General", "theme", "") == mode
    assert mw._workspace._task_panel is not None        # refresh_theme 未炸
