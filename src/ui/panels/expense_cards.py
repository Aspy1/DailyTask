"""记账面板的汇总卡片（从 `expense_panel.py` 抽出来：类的行数卡在基线上下）。

- `summary_card()`：原来面板里的私有方法，搬到模块级；
- `ForecastCard`：A4 的「预计本月支出 / 收入 / 结余」，数值**全部**来自
  `services/finance.summary()`（代码算），界面只负责显示 + 注明依据 ✗ 不算数。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.i18n.loader import tr
from src.ui.styles.theme import RADIUS, SIZE_BODY, SIZE_BODY_S, SIZE_SUBTITLE, get_colors


def summary_card(key: str, label: str) -> QWidget:
    """一张汇总卡：小标题 + 大数字（`objectName=sum_<key>` 给 `_find_sum_label` 找）。"""
    c = get_colors()
    w = QWidget()
    w.setStyleSheet(f"background-color: {c['card_bg']};"
                    f" border-radius: {RADIUS['radius_md']}px;")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(16, 8, 16, 8)
    title = QLabel(label)
    title.setStyleSheet(
        f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px; border: none;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(title)
    amount = QLabel("¥0")
    amount.setStyleSheet(
        f"color: {c['fg_primary']}; font-size: {SIZE_BODY}px;"
        " font-weight: 600; border: none;")
    amount.setAlignment(Qt.AlignmentFlag.AlignCenter)
    amount.setObjectName(f"sum_{key}")
    lay.addWidget(amount)
    return w


class ForecastCard(QWidget):
    """「预计本月支出」卡：主数字 + 收入/结余 + **依据**一行。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(0)

        self._title = QLabel(tr("panel.expense.sum_forecast"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._title)

        self._projected = QLabel("¥0")
        self._projected.setObjectName("sum_forecast")
        self._projected.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._projected)

        self._meta = QLabel("")
        self._meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._meta)

        self._basis = QLabel("")
        self._basis.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._basis)

        self.refresh_theme()

    def refresh_theme(self) -> None:
        """换主题时重上色（颜色不写死在构造里，否则深色模式下深字压深底）。"""
        c = get_colors()
        self.setStyleSheet(f"background-color: {c['card_bg']};"
                           f" border-radius: {RADIUS['radius_md']}px;")
        self._title.setStyleSheet(
            f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px; border: none;")
        self._projected.setStyleSheet(
            f"color: {c['fg_primary']}; font-size: {SIZE_SUBTITLE}px;"
            " font-weight: 600; border: none;")
        self._meta.setStyleSheet(
            f"color: {c['fg_secondary']}; font-size: {SIZE_BODY_S}px; border: none;")
        self._basis.setStyleSheet(
            f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px; border: none;")

    def update_summary(self, result: dict) -> None:
        """`result` 是 `finance.summary()` 的返回值 —— 这里**不做任何算术**。"""
        self._projected.setText(f"¥{result['projected']:.2f}")
        self._meta.setText(tr("panel.expense.forecast_meta",
                              income=f"{result['income']:.2f}",
                              left=f"{result['left']:.2f}"))
        self._basis.setText(
            tr("panel.expense.forecast_basis", n=result["basis_months"])
            if result["basis_months"]
            else tr("panel.expense.forecast_basis_short"))
