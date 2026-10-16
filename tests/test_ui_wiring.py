"""界面接线守卫：导航键与面板、菜单入口。

回归：侧边栏没有"更多"入口 → `MainWindow._show_more_menu`（唯一含
「切换主题」的地方）永远不可达，README 宣称的深浅色主题切换等于没有 UI 入口。
"""

import pytest


def test_sidebar_nav_keys_are_all_routed(qapp) -> None:
    """每个导航键要么是面板、要么由 MainWindow 特判；不能有点了没反应的键。"""
    from src.ui.components.sidebar import Sidebar

    routed_by_mainwindow = {"more"}
    nav_keys = set(Sidebar()._nav_items)
    panel_keys = {"schedule", "courses", "tasks", "exams", "daily",
                  "expenses", "inventory", "meals", "settings"}

    assert nav_keys - panel_keys == routed_by_mainwindow, nav_keys


def test_mainwindow_routes_more(tmp_path, qapp, monkeypatch) -> None:
    """`more` 必须被 MainWindow 特判，不能当面板 key 丢给 switch_to。

    （`about` 已并入设置面板，不再是导航项。）处理函数会开模态菜单，测试里替换掉。
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
    monkeypatch.setattr(mw, "_show_more_menu", lambda: routed.append("more"))

    mw._sidebar._nav_items["more"].click()

    assert routed == ["more"], routed
    assert switched == [], f"more 不应触发面板切换：{switched}"
    assert "about" not in mw._sidebar._nav_items, "关于已并入设置面板"




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


def test_theme_switch_repaints_baked_styles(tmp_path, qapp, monkeypatch) -> None:
    """回归：切主题后，"颜色写死在样式表里"的部件必须重刷。

    两个真实缺陷（2026-10-16 视觉审查）：
    1. 侧边栏 / 内容区 / 顶栏都是普通 QWidget，Qt 不绘制它们的 QSS 背景，
       需要 WA_StyledBackground（否则侧边栏与内容区糊在一起、只有边框可见）；
    2. ScheduleView 的 hash 增量把卡片跳过重建，深色模式下留着**白卡片**。
    """
    from PySide6.QtCore import Qt

    from src.services.ai_service import AIService
    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager
    from src.ui.main_window import MainWindow
    from src.ui.styles.theme import TOKENS, init_theme

    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    qapp.setStyleSheet(init_theme(qapp, "light"))
    mw = MainWindow(settings, AIService(settings, dm), dm, None)
    sv = mw._workspace._schedule_view
    mw._workspace.switch_to("schedule")

    light_sidebar_qss = mw._sidebar.styleSheet()
    light_card_qss = sv._slot_cards[1].styleSheet()

    assert mw._sidebar.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert mw._workspace.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    mw._switch_theme("dark")

    dark = TOKENS["dark"]
    assert dark["sidebar_bg"] in mw._sidebar.styleSheet()
    assert mw._sidebar.styleSheet() != light_sidebar_qss
    card = sv._slot_cards[1]
    assert dark["card_bg"] in card.styleSheet() or dark["bg_card"] in card.styleSheet()
    assert card.styleSheet() != light_card_qss, "切主题后时段卡片必须重建"


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

def test_static_labels_follow_theme(tmp_path, qapp) -> None:
    """回归：构造时写死颜色的**静态**部件也要跟着主题变。

    这类部件（汇总卡片的标题/数值、面包屑、设置分组标题…）不在 `_refresh()`
    的重建范围内，靠 `theme.remap_stylesheets()` 做色值映射整体重写。
    """
    from src.services.ai_service import AIService
    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager
    from src.ui.main_window import MainWindow
    from src.ui.styles.theme import TOKENS, init_theme

    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    qapp.setStyleSheet(init_theme(qapp, "dark"))
    mw = MainWindow(settings, AIService(settings, dm), dm, None)

    expense = mw._workspace._expense_panel
    amount = expense._find_sum_label("\u672c\u6708\u652f\u51fa")
    dark_qss = amount.styleSheet()
    assert TOKENS["dark"]["fg_primary"] in dark_qss

    mw._switch_theme("light")

    assert TOKENS["light"]["fg_primary"] in amount.styleSheet()
    assert TOKENS["light"]["card_bg"] in expense._sum_month.styleSheet()
    assert TOKENS["light"]["bg_elevated"] in mw._workspace._inventory_panel._bc_cat.styleSheet()


def test_rounded_inputs_drop_native_frame(qapp) -> None:
    """回归：带 border-radius 的输入类控件必须关掉原生方框。

    `QLineEdit`/`QComboBox` 默认 `frame=True`，Windows 上原生方框是**直角**的，
    会从 QSS 圆角之外露出来 → 看起来"圆角框周围有角点"
    （R-008 记的"QComboBox 禁止 border-radius（产生角点）"就是它）。
    """
    from PySide6.QtWidgets import QComboBox, QLineEdit

    from src.ui.styles.theme import RADIUS, init_theme

    qapp.setStyleSheet(init_theme(qapp, "light"))
    combo = QComboBox()
    combo.addItem("餐饮")
    combo.setStyleSheet(f"QComboBox {{ border-radius: {RADIUS['radius_md']}px; }}")
    edit = QLineEdit()
    edit.setStyleSheet(f"QLineEdit {{ border-radius: {RADIUS['radius_md']}px; }}")
    plain = QLineEdit()                       # 没圆角 → 不该被动
    for w in (combo, edit, plain):
        w.show()
    qapp.processEvents()

    assert not combo.hasFrame()
    assert not edit.hasFrame()
    assert plain.hasFrame()
