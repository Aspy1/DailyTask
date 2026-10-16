"""弹出菜单模板的回归测试（CODE_STANDARDS Q-H15）。

守住三件事：

1. **去原生阴影**：`NoDropShadowWindowHint`（Windows 上会清掉 `CS_DROPSHADOW`）
2. **`exec()` 必须返回**：旧自研菜单靠 `destroyed` 结束内嵌事件循环，而关闭走的是
   `close()`（不销毁控件）→ `exec()` 永不返回 → 读 `last_action` 的 5 个右键菜单
   点了没反应，并且每次打开都遗留一个内嵌事件循环
3. **动作可执行**：`add_action(..., 回调)` 触发后回调真的被调用
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from src.ui.widgets.menu import add_action, add_separator, new_menu


def test_menu_has_no_native_shadow(qapp) -> None:
    menu = new_menu()
    assert menu.windowFlags() & Qt.WindowType.NoDropShadowWindowHint
    assert menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_menu_uses_tokens(qapp) -> None:
    from src.ui.styles.theme import get_colors

    qss = new_menu().styleSheet()
    assert get_colors()["bg_elevated"] in qss
    assert get_colors()["border_strong"] in qss


def test_menu_is_stock_qmenu_and_close_only_hides(qapp) -> None:
    """回归：菜单必须是**标准 `QMenu`**，且 `close()` 只隐藏、不销毁。

    为什么这样测（而不是直接跑 `QMenu.exec()`）：旧自研菜单的 `exec()` **永不返回**，
    根因是它把"结束事件循环"的条件挂在 `destroyed` 上，而关闭走 `close()`
    —— 只隐藏、不销毁，条件永不成立。标准 `QMenu` 在隐藏时结束 `exec()`，没这个问题。

    ⚠ 不再起事件循环：整套测试累积的 Qt 状态会让任何嵌套事件循环偶发
    `access violation`（隔离跑 0/12，整套跑约 1/4～7/8 崩）。
    本测试改为确定性断言这两条性质，套件因此稳定（`ERRORS #039`）。
    """
    menu = new_menu()
    add_action(menu, "随便", lambda checked=False: None)
    assert isinstance(menu, QMenu)

    menu.close()
    assert not menu.isVisible()
    assert menu.actions(), "close() 后菜单必须仍存在（旧实现的挂死条件正相反）"


def test_action_callback_is_invoked(qapp) -> None:
    menu = new_menu()
    calls: list[str] = []
    add_action(menu, "编辑", lambda checked=False: calls.append("edit"))
    add_action(menu, "删除", lambda checked=False: calls.append("delete"))
    add_separator(menu)

    actions = menu.actions()
    assert [a.text() for a in actions] == ["编辑", "删除", ""]   # 分隔符无文案
    actions[1].trigger()
    assert calls == ["delete"]


def test_checkable_action_carries_state(qapp) -> None:
    menu = new_menu()
    add_action(menu, "全部课程", checkable=True, checked=True)
    action = menu.actions()[0]
    assert action.isCheckable() and action.isChecked()


def test_data_round_trip(qapp) -> None:
    """课程菜单靠 data() 携带动作类型与参数，必须能原样取回。"""
    menu = new_menu()
    add_action(menu, "修改课程名称", data=("rename", "c_001"))
    assert menu.actions()[0].data() == ("rename", "c_001")


def test_course_context_menu_actions(qapp) -> None:
    """课程右键菜单的条目与 data 标签（原先因为 exec 不返回而全部失效）。"""
    from src.ui.widgets.course_table import COURSE_ACTIONS, build_course_context_menu

    menu = build_course_context_menu({"id": "c_001", "name": "高等数学"})
    assert isinstance(menu, QMenu)
    texts = [a.text() for a in menu.actions()]
    assert texts[:3] == ["修改课程名称", "删除这门课", "查看关于这门课的事项"]
    # 第 4 项是「会点名」开关（默认未开启 → 显示"开启…"）
    assert texts[3] == "开启点名提醒（提前 30 分钟）"
    assert [a.text() for a in menu.actions()[4:]] == ["", *COURSE_ACTIONS]
    assert menu.actions()[0].data() == ("rename", "c_001")
    assert menu.actions()[3].data() == ("toggle_attendance", "c_001")
    assert menu.actions()[4 + len(COURSE_ACTIONS)].data() == ("fill", COURSE_ACTIONS[-1])


def test_course_context_menu_attendance_label_flips(qapp) -> None:
    """已开启点名的课 → 菜单项变成"关闭点名提醒"（标签按状态翻转）。"""
    from src.ui.widgets.course_table import build_course_context_menu

    menu = build_course_context_menu(
        {"id": "c_001", "name": "高等数学", "reminders": {"attendance": True}})
    assert menu.actions()[3].text() == "关闭点名提醒"
    assert menu.actions()[3].data() == ("toggle_attendance", "c_001")
