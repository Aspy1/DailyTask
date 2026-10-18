"""学期管理对话框（Q-H9~Q-H14：三段式 / 尺寸 460 / 只走 token / 中文动词按钮）。

做三件事：
1. 显示**当前学期状态**与**数据检查结果**（合法性检测的用户出口）；
2. **切换**当前学期；
3. **新建**学期（默认开始日期 = 下一个周一），创建后设为当前 —— 学期过期后的主要动作。
"""

import logging
from datetime import date

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
    DEFAULT_EXAM_WEEKS,
    DEFAULT_PERIOD_COUNT,
    DEFAULT_TOTAL_WEEKS,
    MAX_EXAM_WEEKS,
    MAX_PERIOD_COUNT,
    MAX_TOTAL_WEEKS,
    MIN_PERIOD_COUNT,
    MIN_TOTAL_WEEKS,
    season_start_for,
)
from src.services.data_manager import DataManager
from src.ui.components.semester_text import issue_text, semester_state_text
from src.ui.styles.theme import FIELD_H, SIZE_BODY_L, SIZE_BODY_S, get_colors
from src.ui.widgets.dialog_shell import cap_height, dialog_qss, make_scrollable
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.rounded_input import RoundedLineEdit

logger = logging.getLogger(__name__)

WIDTH = 460


class SemesterDialog(QDialog):
    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self.setWindowTitle(tr("dialog.semester.title"))
        self.setMinimumWidth(WIDTH)
        self._build()

    # ── 结构 ────────────────────────────────────────────────
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(12)
        # 内容可滚动 + 限高（审查 U9）：屏幕不够高时按钮仍可见。
        # ⚠ 按钮行挂在 `outer` 上（不是返回的内容 layout），否则会跟着内容滚走。
        layout = make_scrollable(outer)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._issues_label = QLabel()
        self._issues_label.setWordWrap(True)
        layout.addWidget(self._issues_label)

        self._build_switch_row(layout)
        self._build_new_section(layout)
        self._build_buttons(outer)
        self.setStyleSheet(dialog_qss())
        cap_height(self)
        self._refresh()

    def _build_switch_row(self, layout: QVBoxLayout) -> None:
        self._switch_combo = QComboBox()
        self._switch_combo.setFixedHeight(FIELD_H)
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
        self._exam_input = QSpinBox()
        self._exam_input.setRange(0, MAX_EXAM_WEEKS)
        self._exam_input.setValue(DEFAULT_EXAM_WEEKS)
        for widget in (self._name_input, self._start_input, self._weeks_input,
                       self._periods_input, self._exam_input):
            widget.setFixedHeight(FIELD_H)

        for label_key, widget in (
            ("dialog.semester.label_name", self._name_input),
            ("dialog.semester.label_start", self._start_input),
            ("dialog.semester.label_weeks", self._weeks_input),
            ("dialog.semester.label_exam_weeks", self._exam_input),
            ("dialog.semester.label_periods", self._periods_input),
        ):
            layout.addLayout(self._field_row(tr(label_key), widget))

        hint = QLabel(tr("dialog.semester.hint_season"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {get_colors()['fg_hint']}; font-size: {SIZE_BODY_S}px;")
        layout.addWidget(hint)

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
        courses = self._dm.courses
        status = courses.semester_status()
        self._render_status(status, courses.validate())
        self._fill_switch_combo(courses)
        self._reset_new_fields(status)

    def _render_status(self, status: dict, report: dict) -> None:
        c = get_colors()
        text = semester_state_text(status)
        if status.get("start_date") and status.get("end_date"):
            text += "　" + tr("dialog.semester.range_hint",
                              start=status["start_date"].isoformat(),
                              end=status["end_date"].isoformat(),
                              total=status["total_weeks"],
                              exam=status.get("exam_weeks") or 0)
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {c['accent_text']}; font-size: {SIZE_BODY_S}px; font-weight: 600;")
        self._render_issues(report)

    def _render_issues(self, report: dict) -> None:
        """数据检查结果（合法性检测的用户出口）。"""
        c = get_colors()
        issues = list(report.get("model", []))
        for codes in report.get("semesters", {}).values():
            issues += codes
        issues += report.get("courses", [])
        if not issues:
            self._issues_label.setText(
                f"{tr('dialog.semester.section_issues')}：{tr('dialog.semester.issues_none')}")
            self._issues_label.setStyleSheet(
                f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px;")
            return
        lines = [f"· {issue_text(code)}" for code in dict.fromkeys(issues)]
        self._issues_label.setText(
            tr("dialog.semester.section_issues") + "\n" + "\n".join(lines))
        self._issues_label.setStyleSheet(f"color: {c['red']}; font-size: {SIZE_BODY_S}px;")

    def _fill_switch_combo(self, courses) -> None:
        self._switch_combo.clear()
        for semester in courses.semesters:
            label = semester.get("name") or semester.get("id", "")
            if semester.get("id") == courses.current_semester:
                label += tr("dialog.semester.current_marker")
            self._switch_combo.addItem(label, semester.get("id"))
        self._switch_btn.setEnabled(self._switch_combo.count() > 0)

    def _reset_new_fields(self, status: dict) -> None:
        """新建区的默认值：开始日按季节预设，周数/节次沿用当前学期。"""
        start = season_start_for(date.today())
        self._start_input.setDate(QDate(start.year, start.month, start.day))
        self._weeks_input.setValue(status.get("total_weeks") or DEFAULT_TOTAL_WEEKS)
        exam = status.get("exam_weeks")
        self._exam_input.setValue(DEFAULT_EXAM_WEEKS if exam is None else exam)
        self._periods_input.setValue(status.get("period_count") or DEFAULT_PERIOD_COUNT)

    def _on_switch(self) -> None:
        semester_id = self._switch_combo.currentData()
        # 必须走 DataManager：它还要把 courses/tasks/exams **重定向**到新学期的文件
        if not semester_id or not self._dm.switch_semester(semester_id):
            self._issues_label.setText(tr("dialog.semester.switch_failed"))
            return
        self._refresh()

    def _on_create(self) -> None:
        qdate = self._start_input.date()
        start = date(qdate.year(), qdate.month(), qdate.day())
        name = self._name_input.text().strip() or start.isoformat()
        self._dm.create_semester(
            name=name, start=start,
            total_weeks=self._weeks_input.value(),
            period_count=self._periods_input.value(),
            exam_weeks=self._exam_input.value())
        self._refresh()
        self._issues_label.setText(tr("dialog.semester.created", name=name))
        self._issues_label.setStyleSheet(
            f"color: {get_colors()['green']}; font-size: {SIZE_BODY_S}px;")
