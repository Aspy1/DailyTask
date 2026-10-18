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

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles.theme import get_colors

# 弹窗最高占可用屏幕高度的比例（留出标题栏与任务栏的余量）
MAX_HEIGHT_RATIO = 0.85


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

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setSpacing(8)
        self.body.setContentsMargins(0, 0, 0, 0)
        self._scroll.setWidget(content)
        outer.addWidget(self._scroll, 1)

        # `buttons=False` 给"自带按钮行"的弹窗用（比如学期弹窗只有关闭按钮）
        self.buttons: QDialogButtonBox | None = None
        if buttons:
            self.buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            self.buttons.accepted.connect(self.accept)
            self.buttons.rejected.connect(self.reject)
            outer.addWidget(self.buttons)

        self._apply_style()
        self._cap_height()

    def add_action_row(self, widget: QWidget) -> None:
        """挂一行**自定义**按钮：固定在外壳底部（不在滚动区里，永远可见）。"""
        self._outer.addWidget(widget)

    def _apply_style(self) -> None:
        """弹窗样式**只有这一处**（原来每个弹窗各写一份内联 QSS）。"""
        c = get_colors()
        self.setStyleSheet(
            f"QDialog {{ background-color: {c['card_bg']}; }}"
            f" QLabel {{ color: {c['fg_primary']}; font-size: 13px;"
            f" background: transparent; border: none; }}"
            f" QListWidget {{ background-color: {c['bg_input']}; color: {c['fg_primary']};"
            f" border: 1px solid {c['border']}; font-size: 13px; }}")

    def _cap_height(self) -> None:
        """限高：屏幕不够高时**中间滚动、按钮始终可见**（审查 U9）。"""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            self.setMaximumHeight(int(screen.availableGeometry().height() * MAX_HEIGHT_RATIO))
