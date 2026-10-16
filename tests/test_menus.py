"""弹出菜单模板的回归测试（CODE_STANDARDS Q-H15）。

守住三件事：

1. **去原生阴影**：`NoDropShadowWindowHint`（Windows 上会清掉 `CS_DROPSHADOW`）
2. **`exec()` 必须返回**：旧自研菜单靠 `destroyed` 结束内嵌事件循环，而关闭走的是
   `close()`（不销毁控件）→ `exec()` 永不返回 → 读 `last_action` 的 5 个右键菜单
   点了没反应，并且每次打开都遗留一个内嵌事件循环
3. **动作可执行**：`add_action(..., 回调)` 触发后回调真的被调用
"""

import os

import pytest
from PySide6.QtCore import Qt, QTimer
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


@pytest.mark.skipif(
    os.environ.get("CI", "").lower() in ("true", "1", "yes"),
    reason="offscreen 平台下 QMenu.exec() 会起真正的模态循环，CI runner 上偶发 "
           "access violation（同一提交本地稳定通过）。本项由本地运行覆盖；"
           "菜单模板的其余守卫（QMenu 类型 / 令牌 / 去阴影 / 回调）在 CI 照常执行。",
)
def test_exec_returns_when_menu_closes(qapp) -> None:
    """回归：QMenu.exec() 在菜单关闭后必须返回（旧自研菜单永不返回）。"""
    menu = new_menu()
    # 不真正"上屏"：避免在无显示环境下走窗口系统（模态循环仍会跑，close() 仍能结束它）
    menu.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    add_action(menu, "随便", lambda checked=False: None)
    QTimer.singleShot(30, menu.close)
    assert menu.exec() is None            # 卡住的话这条测试会挂，CI 会超时


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
    assert [a.text() for a in menu.actions()[3:]] == ["", *COURSE_ACTIONS]
    assert menu.actions()[0].data() == ("rename", "c_001")
    assert menu.actions()[3 + len(COURSE_ACTIONS)].data() == ("fill", COURSE_ACTIONS[-1])
