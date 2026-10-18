"""统一的弹窗外壳：**限高 + 中间可滚动 + 底部按钮固定**。

审查 U9：长弹窗在屏幕不够高时，底部按钮会跑到屏幕外、**够不着**；各行控件的高度与
文字基线也各写一套。这里先解决"够不着"，并把弹窗样式收成一处。

用法：

    dlg = DialogShell(parent, title, min_width=360)
    dlg.body.addWidget(...)        # 内容都往 `body` 里加（超出会自动出现滚动）
    if dlg.exec():
        ...

`body` 是 `QVBoxLayout`，内容装在 `QScrollArea` 里；按钮行在外壳上，永远可见。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.ui.styles.theme import (
    btn_danger_qss,
    btn_primary_qss,
    btn_secondary_qss,
    get_colors,
)
from src.ui.widgets.rounded_button import RoundedButton

# 弹窗最高占可用屏幕高度的比例（留出标题栏与任务栏的余量）
MAX_HEIGHT_RATIO = 0.85


def cap_height(dialog: QDialog) -> None:
    """限高：屏幕不够高时**中间滚动、底部按钮始终可见**（审查 U9）。"""
    screen = dialog.screen() or QApplication.primaryScreen()
    if screen is not None:
        dialog.setMaximumHeight(int(screen.availableGeometry().height() * MAX_HEIGHT_RATIO))


def make_scrollable(outer: QVBoxLayout) -> QVBoxLayout:
    """造一个"可滚动内容区"挂到 `outer`，返回**内容 layout**。

    给 `QDialog` **子类**用 —— 它们不能继承 `DialogShell`（那本身就是个 QDialog），
    但同样需要"限高 + 中间滚动"。配套 `cap_height(self)`。

    ⚠ 按钮行要加到 `outer`（不是返回的内容 layout），否则会跟着内容滚走。
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    content = QWidget()
    body = QVBoxLayout(content)
    body.setSpacing(8)
    body.setContentsMargins(0, 0, 0, 0)
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)
    return body


def dialog_qss() -> str:
    """弹窗的标准 QSS（**只有这一处** —— 原来每个弹窗各写一份内联样式）。"""
    c = get_colors()
    return (f"QDialog {{ background-color: {c['card_bg']}; }}"
            f" QLabel {{ color: {c['fg_primary']}; font-size: 13px;"
            f" background: transparent; border: none; }}"
            f" QListWidget {{ background-color: {c['bg_input']}; color: {c['fg_primary']};"
            f" border: 1px solid {c['border']}; font-size: 13px; }}")


def form_row(label: str, field: QWidget, label_width: int = 88) -> QWidget:
    """「标签 + 控件」一行 —— **唯一**的行工厂（`Q-H9`）。

    标签在**左**、固定宽度；控件占满余下宽度。标签样式由 `dialog_qss()` 的 `QLabel`
    规则统一决定，这里**不写内联样式** —— 否则又回到"每个弹窗各写一套"。

    为什么要工厂：原来有 4 套各写各的 —— `semester_dialog._field_row`（标签左）、
    `inventory_dialogs._labeled_field`（标签**在上**）、`settings_panel._row`（固定 100 居中）、
    裸 `QFormLayout`（habit / exam / api_test）。并排看就不是一套东西（`Q-H9` 的原话）。
    """
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(8)
    lbl = QLabel(label)
    lbl.setMinimumWidth(label_width)
    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    rl.addWidget(lbl)
    rl.addWidget(field, 1)
    return row


def action_row(primary_text: str, on_primary, *, cancel_text: str = "",
               on_cancel=None, danger: bool = False) -> QWidget:
    """弹窗底部按钮行 —— **唯一**的按钮行工厂（`Q-H11`）。

    - 顺序：**取消在左、主操作在最右**；文案必须是中文动词（缺省走 i18n）
    - 主操作走 `btn_primary_qss()`；`danger=True`（删除 / 清空）走 `btn_danger_qss()`
    - `on_cancel` 缺省不接（调用方一般传 `dialog.reject`）
    """
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.addStretch()

    cancel = RoundedButton(cancel_text or tr("widget.dialog.btn_cancel"))
    cancel.setStyleSheet(btn_secondary_qss())
    if on_cancel is not None:
        cancel.clicked.connect(lambda _checked=False: on_cancel())
    rl.addWidget(cancel)

    primary = RoundedButton(primary_text)
    primary.setStyleSheet(btn_danger_qss() if danger else btn_primary_qss())
    primary.clicked.connect(lambda _checked=False: on_primary())
    rl.addWidget(primary)
    return row


class DialogShell(QDialog):
    """带滚动内容的弹窗外壳。调用方只往 `body` 加内容。"""

    def __init__(self, parent=None, title: str = "", min_width: int = 360,
                 buttons: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(min_width)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)
        self._outer = outer
        self.body = make_scrollable(outer)

        # `buttons=False` 给"自带按钮行"的弹窗用（比如学期弹窗只有关闭按钮）
        self.buttons: QWidget | None = None
        if buttons:
            # ⚠ **不用** `QDialogButtonBox`：Windows 布局把「确定」放在**左**（违反 Q-H11
            # "取消在左、主操作在最右"），而且渲染成扁平文字按钮、不走主/次按钮工厂
            # （2026-10-18 渲染截图实测）。
            self.buttons = action_row(tr("widget.dialog.btn_confirm"), self.accept,
                                      on_cancel=self.reject)
            outer.addWidget(self.buttons)

        self.setStyleSheet(dialog_qss())
        cap_height(self)

    def add_action_row(self, widget: QWidget) -> None:
        """挂一行**自定义**按钮：固定在外壳底部（不在滚动区里，永远可见）。"""
        self._outer.addWidget(widget)

    def _apply_style(self) -> None:
        """（保留给子类覆盖的钩子；标准样式见模块级 `dialog_qss()`。）"""
        self.setStyleSheet(dialog_qss())
