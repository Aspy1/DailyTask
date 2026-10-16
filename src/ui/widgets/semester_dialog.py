"""学期管理对话框（Q-H9~Q-H14：三段式 / 尺寸 460 / 只走 token / 中文动词按钮）。

做三件事：
1. 显示**当前学期状态**与**数据检查结果**（合法性检测的用户出口）；
2. **切换**当前学期；
3. **新建**学期（默认开始日期 = 下一个周一），创建后设为当前 —— 学期过期后的主要动作。
"""

import logging
from datetime import date, timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from src.i18n.loader import tr
from src.models.semester import (
    DEFAULT_PERIOD_COUNT,
    DEFAULT_TOTAL_WEEKS,
    MAX_PERIOD_COUNT,
    MAX_TOTAL_WEEKS,
    MIN_PERIOD_COUNT,
    MIN_TOTAL_WEEKS,
)
from src.services.data_manager import DataManager
from src.ui.components.semester_text import issue_text, semester_state_text
from src.ui.styles.theme import SIZE_BODY_L, SIZE_BODY_S, get_colors
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.rounded_input import RoundedLineEdit

logger = logging.getLogger(__name__)

WIDTH = 460


def next_monday(today: date | None = None) -> date:
    """下一个周一（默认的新学期开始日）。"""
    today = today or date.today()
    return today + timedelta(days=(8 - today.isoweekday()) % 7 or 7)


class SemesterDialog(QDialog):
    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self.setWindowTitle(tr("dialog.semester.title"))
        self.setMinimumWidth(WIDTH)
        self._build()

    # ── 结构 ────────────────────────────────────────────────
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._issues_label = QLabel()
        self._issues_label.setWordWrap(True)
        layout.addWidget(self._issues_label)

        self._build_switch_row(layout)
        self._build_new_section(layout)
        self._build_buttons(layout)
        self._refresh()

    def _build_switch_row(self, layout: QVBoxLayout) -> None:
        self._switch_combo = QComboBox()
        self._switch_combo.setFixedHeight(34)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(tr("dialog.semester.section_switch")))
        row.addWidget(self._switch_combo, stretch=1)
        self._switch_btn = RoundedButton(tr("dialog.semester.btn_switch"))
        self._switch_btn.clicked.connect(self._on_switch)
        row.addWidget(self._switch_btn)
        layout.addLayout(row)

    def _build_new_section(self, layout: QVBoxLayout) -> None:
        layout.addWidget(self._section(tr("dialog.semester.section_new")))
        self._name_input = RoundedLineEdit()
        self._name_input.setPlaceholderText(tr("dialog.semester.placeholder_name"))
        self._start_input = QDateEdit()
        self._start_input.setDisplayFormat("yyyy-MM-dd")
        self._start_input.setCalendarPopup(True)
        self._weeks_input = QSpinBox()
        self._weeks_input.setRange(MIN_TOTAL_WEEKS, MAX_TOTAL_WEEKS)
        self._weeks_input.setValue(DEFAULT_TOTAL_WEEKS)
        self._periods_input = QSpinBox()
        self._periods_input.setRange(MIN_PERIOD_COUNT, MAX_PERIOD_COUNT)
        self._periods_input.setValue(DEFAULT_PERIOD_COUNT)
        for widget in (self._name_input, self._start_input, self._weeks_input,
                       self._periods_input):
            widget.setFixedHeight(34)

        for label_key, widget in (
            ("dialog.semester.label_name", self._name_input),
            ("dialog.semester.label_start", self._start_input),
            ("dialog.semester.label_weeks", self._weeks_input),
            ("dialog.semester.label_periods", self._periods_input),
        ):
            layout.addLayout(self._field_row(tr(label_key), widget))

        row = QHBoxLayout()
        row.addStretch()
        self._create_btn = RoundedButton(tr("dialog.semester.btn_create"))
        self._create_btn.clicked.connect(self._on_create)
        row.addWidget(self._create_btn)
        layout.addLayout(row)

    def _build_buttons(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addStretch()
        close_btn = RoundedButton(tr("dialog.semester.btn_close"))
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        layout.addLayout(row)

    @staticmethod
    def _section(text: str) -> QLabel:
        """分区标题（16px，与内容同缩进）。"""
        label = QLabel(text)
        label.setStyleSheet(
            f"font-size: {SIZE_BODY_L}px; font-weight: 600; margin-top: 4px;")
        return label

    @staticmethod
    def _field_row(text: str, widget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(text)
        label.setMinimumWidth(88)
        row.addWidget(label)
        row.addWidget(widget, stretch=1)
        return row

    # ── 数据 ────────────────────────────────────────────────
    def _refresh(self) -> None:
        c = get_colors()
        courses = self._dm.courses
        status = courses.semester_status()
        report = courses.validate()

        text = semester_state_text(status)
        if status.get("start_date") and status.get("end_date"):
            text += "　" + tr("dialog.semester.range_hint",
                              start=status["start_date"].isoformat(),
                              end=status["end_date"].isoformat(),
                              total=status["total_weeks"])
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {c['accent_text']}; font-size: {SIZE_BODY_S}px; font-weight: 600;")

        issues = list(report.get("model", []))
        for codes in report.get("semesters", {}).values():
            issues += codes
        issues += report.get("courses", [])
        if issues:
            lines = [f"· {issue_text(code)}" for code in dict.fromkeys(issues)]
            self._issues_label.setText(
                tr("dialog.semester.section_issues") + "\n" + "\n".join(lines))
            self._issues_label.setStyleSheet(
                f"color: {c['red']}; font-size: {SIZE_BODY_S}px;")
        else:
            self._issues_label.setText(
                f"{tr('dialog.semester.section_issues')}：{tr('dialog.semester.issues_none')}")
            self._issues_label.setStyleSheet(
                f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px;")

        self._switch_combo.clear()
        for semester in courses.semesters:
            label = semester.get("name") or semester.get("id", "")
            if semester.get("id") == courses.current_semester:
                label += tr("dialog.semester.current_marker")
            self._switch_combo.addItem(label, semester.get("id"))
        self._switch_btn.setEnabled(self._switch_combo.count() > 0)

        self._start_input.setDate(QDate(next_monday().year, next_monday().month,
                                        next_monday().day))
        self._periods_input.setValue(status.get("period_count") or DEFAULT_PERIOD_COUNT)

    def _on_switch(self) -> None:
        semester_id = self._switch_combo.currentData()
        if not semester_id or not self._dm.courses.set_current_semester(semester_id):
            self._issues_label.setText(tr("dialog.semester.switch_failed"))
            return
        self._dm.courses.save()
        self._dm.data_changed.emit("course")
        self._refresh()

    def _on_create(self) -> None:
        qdate = self._start_input.date()
        start = date(qdate.year(), qdate.month(), qdate.day())
        name = self._name_input.text().strip() or start.isoformat()
        semester_id = self._dm.courses.create_semester(
            name=name, start=start,
            total_weeks=self._weeks_input.value(),
            period_count=self._periods_input.value())
        self._dm.courses.save()
        self._dm.data_changed.emit("course")
        self._refresh()
        self._issues_label.setText(tr("dialog.semester.created", name=name))
        self._issues_label.setStyleSheet(
            f"color: {get_colors()['green']}; font-size: {SIZE_BODY_S}px;")
        logger.info("已创建学期 %s（%s）", semester_id, start.isoformat())
