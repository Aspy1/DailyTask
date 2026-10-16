"""弹出菜单模板集合（CODE_STANDARDS Q-H15）。

统一三件事，消灭"每种情况各写一套坐标"：

1. **外观**：`QMenu` + token 配色 + 去原生阴影（`NoDropShadowWindowHint` 会清掉
   Windows 的 `CS_DROPSHADOW`，已实测）+ 圆角
2. **定位**：三种锚点模板，覆盖所有场景
   - `show_at_cursor`：右键 / 键盘触发（跟随光标）
   - `show_at`：右键回调里带控件局部坐标（`widget.mapToGlobal(pos)`）
   - `show_below`：按钮下拉（锚在该控件左下角下方）
   贴边翻转、多屏、缩放、键盘导航（Esc / 方向键）由 Qt 负责。
3. **动作**：`add_action(menu, 文案, 回调)`。**不要再写"exec() 之后比较 last_action"**：
   那个模式依赖 `exec()` 返回，而旧自研菜单的 `exec()` 因为靠 `destroyed` 结束内嵌
   事件循环，实际**永不返回**（`close()` 不销毁控件），导致课程表 / 日程 DDL / 日程日常
   三处右键菜单点了没反应，并且每次打开都遗留一个内嵌事件循环。

旧实现 `src/ui/widgets/context_menu.py` 已删除（手搓菜单是为了去原生阴影，现在用
`NoDropShadowWindowHint` 就能达到同样效果，且定位可靠）。
"""

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QMenu, QWidget

from src.ui.styles.theme import menu_qss


def new_menu(parent: QWidget | None = None) -> QMenu:
    """建一个符合设计令牌、无原生阴影的菜单。"""
    menu = QMenu(parent)
    # 去原生阴影：Windows 上会清掉窗口类的 CS_DROPSHADOW 位。
    # ⚠ 必须用 setWindowFlags(现有 | flag)：对 QMenu 而言 setWindowFlag(flag, True)
    #   不会留在 windowFlags() 里（实测），而窗口类样式是创建原生窗口时读的。
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.NoDropShadowWindowHint)
    # 圆角需要透明底
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menu.setStyleSheet(menu_qss())
    return menu


def add_action(
    menu: QMenu,
    text: str,
    callback: Callable | None = None,
    *,
    checkable: bool = False,
    checked: bool = False,
    data: tuple | None = None,
) -> QAction:
    """加一条菜单项并返回 QAction。

    `callback` 收到 Qt 传来的 `checked` 参数（`triggered(bool)`），所以需要
    固定参数的场景请用 `lambda checked=False: ...` 包一层。
    """
    action = QAction(text, menu)
    if checkable:
        action.setCheckable(True)
        action.setChecked(checked)
    if data is not None:
        action.setData(data)
    if callback is not None:
        action.triggered.connect(callback)
    menu.addAction(action)
    return action


def add_separator(menu: QMenu) -> None:
    menu.addSeparator()


# ── 定位模板（三选一，不要自己算坐标）──────────────────────

def show_at_cursor(menu: QMenu) -> QAction | None:
    """模板 1：跟随光标（右键菜单、键盘触发）。"""
    return menu.exec(QCursor.pos())


def show_at(menu: QMenu, widget: QWidget, pos: QPoint) -> QAction | None:
    """模板 2：锚在控件内的某个点（`customContextMenuRequested` 给的局部坐标）。"""
    return menu.exec(widget.mapToGlobal(pos))


def show_below(menu: QMenu, widget: QWidget) -> QAction | None:
    """模板 3：锚在控件左下角下方（按钮下拉）。"""
    return menu.exec(widget.mapToGlobal(widget.rect().bottomLeft()))
