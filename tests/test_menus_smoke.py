"""菜单冒烟：把**每一个**菜单都打开一遍（`exec` 用替身，不阻塞）。

动机：迁移到 `menu.py` 模板时踩过两个坑，都是"运行到那一步才炸"的类型：

1. `Sidebar.nav_item` 被误加到 `SidebarSection` → 点「更多…」抛 `AttributeError`，菜单根本不弹
2. 考试面板的 `pos` 是**卡片**局部坐标，却按**面板**局部坐标映射 → 菜单位置偏移

这两个 bug 都能被"逐个打开菜单 + 检查锚点"的测试挡住。
"""


from collections.abc import Callable
from typing import Any

import pytest
from helpers import run

from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager

SEED = [
    'python scripts/actions.py add_course --name "高等数学" --day 1 --weeks 1-20 --slots 1-2',
    'python scripts/actions.py add_task --course "高等数学" --title "习题" --due 2026-12-01',
    'python scripts/actions.py add_exam --course "高等数学" --date 2026-12-20',
    'python scripts/actions.py add_habit --name "跑步" --schedule "daily/1"',
    'python scripts/actions.py add_item --name "洗发水" --category 日常消耗品 --quantity 2',
    'python scripts/actions.py add_plan --date 2026-12-01 --title "复习" --slot 3',
]


@pytest.fixture
def app_env(sandbox, qapp) -> tuple:
    """离屏 MainWindow + 有数据的沙箱。

    ⚠ 必须带 `sandbox`：它把 `actions.DATA` 指到临时目录，种子数据才不会写进真实 data/。
    （helpers.run 现在会硬失败来兜住这个错误。）
    """
    from src.ui.main_window import MainWindow
    from src.ui.styles.theme import init_theme

    for cmd in SEED:
        out = run(cmd)
        assert out.startswith("OK"), (cmd, out)

    qapp.setStyleSheet(init_theme(qapp, "dark"))
    settings = SettingsManager(sandbox / "settings.ini")
    settings.load()
    dm = DataManager(sandbox)
    mw = MainWindow(settings, AIService(settings, dm), dm, None)
    mw.resize(1200, 800)
    return mw, dm


@pytest.fixture
def opened(monkeypatch) -> list:
    """把三个 show_* 模板换成替身，记录 (函数名, menu, 参数)。"""
    from src.ui import main_window
    from src.ui.panels import exam_panel, expense_panel, habit_panel, inventory_panel, task_panel
    from src.ui.widgets import course_table, schedule_view

    calls: list[tuple] = []

    def recorder(name: str) -> Callable:
        def _rec(menu: Any, *args: Any) -> None:
            calls.append((name, menu, *args))
            return None
        return _rec

    for mod in (main_window, exam_panel, expense_panel, habit_panel,
                inventory_panel, task_panel, course_table, schedule_view):
        for name in ("show_at", "show_at_cursor", "show_below"):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, recorder(name))
    return calls


def test_every_menu_opens_without_error(app_env, opened) -> None:
    """逐个打开菜单：不得抛异常，且每次都要真的弹出一个菜单。"""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent

    mw, dm = app_env
    ws = mw._workspace
    ws.switch_to("schedule")
    sv = ws._schedule_view

    # 侧边栏「更多…」（曾被 AttributeError 打断）
    mw._show_more_menu()

    # 日程：课程 / 计划 / 日常卡片右键
    sv._course_menu(QPoint(5, 5), {"course": dm.courses.courses[0]}, sv)
    sv._plan_menu(QPoint(5, 5), {"plan": {"title": "复习"}, "title": "复习"}, sv)
    sv._habit_menu(QPoint(5, 5), {"habit": {"id": dm.habits.habits[0]["id"]},
                                  "name": "跑步"}, sv)

    # 课程表
    table = ws._course_panel.table
    cell = next(iter(table._cell_courses))
    table._on_context_menu(table.visualItemRect(table.item(*cell)).center())

    # 考试：锚点必须是卡片本身（曾被当成面板 → 位置偏）
    exam_panel = ws._exam_panel
    exam_panel._refresh()
    card = exam_panel._card_layout.itemAt(0).widget()
    exam_panel._context_menu(QPoint(5, 5), dm.exams.exams[0], card)

    # 库存
    inv = ws._inventory_panel
    inv._refresh()
    inv._show_cat_filter()
    inv._show_tag_filter()
    inv._context_menu(dm.inventory.items[0])

    # 记账
    ws._expense_panel._show_cat_filter()
    ws._expense_panel._show_time_filter()

    # 作业筛选
    ws._task_panel._show_course_filter()
    ws._task_panel._show_time_filter()

    # 日常卡片（contextMenuEvent 入口）
    habit_panel = ws._habit_panel
    habit_panel._refresh()
    habit_card = next(c for c in habit_panel._grid.children() if hasattr(c, "contextMenuEvent") and c.objectName() == "habitCard")
    habit_card.contextMenuEvent(
        QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(1, 1), QPoint(1, 1)))

    assert len(opened) >= 13, [c[0] for c in opened]

    # 锚点校验：按钮下拉锚在按钮上；考试菜单锚在卡片上
    anchors = {name: [c[2] for c in opened if c[0] == name] for name in
               ("show_below", "show_at")}
    assert all(hasattr(a, "text") for a in anchors["show_below"]), anchors["show_below"]
    assert card in anchors["show_at"], "考试菜单必须锚在卡片上（否则位置偏）"

    # 每个菜单都必须有内容
    for _name, menu, *_rest in opened:
        assert menu.actions(), "空菜单说明构建逻辑被改坏了"


def test_more_menu_is_anchored_to_the_more_item(app_env, opened) -> None:
    """「更多…」必须锚在侧边栏那个按钮下方（原来是写死在侧边栏右下角）。"""
    mw, _dm = app_env
    mw._show_more_menu()

    anchor = next(c[2] for c in opened if c[0] == "show_below")
    assert anchor is mw._sidebar.nav_item("more")
    assert anchor.text() == "更多…"
