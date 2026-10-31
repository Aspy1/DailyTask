"""考研备考面板的四个弹窗（学习 / 错题 / 模考 / 目标）。

全部走 `DialogShell`（Q-H9：标题区 + 可滚动内容 + 底部按钮固定）与
`form_row` / `action_row` 工厂（唯一行/按钮区实现）。
"""

from datetime import date

from PySide6.QtWidgets import QMessageBox, QSpinBox

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.styles.theme import LAYOUT, spin_qss
from src.ui.widgets.dialog_shell import DialogShell, action_row, form_row
from src.ui.widgets.rounded_input import RoundedComboBox, RoundedLineEdit


def _subject_combo(dm: DataManager, current: str | None = None) -> RoundedComboBox:
    combo = RoundedComboBox()
    for subject in dm.study.subjects:
        combo.addItem(str(subject.get("name") or subject.get("id")), str(subject.get("id")))
    if current:
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
    return combo


def _spin(low: int, high: int, value: int, suffix: str = "") -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setValue(value)
    spin.setStyleSheet(spin_qss())
    if suffix:
        spin.setSuffix(suffix)
    return spin


def _valid_date(text: str) -> bool:
    try:
        date.fromisoformat(text.strip())
        return True
    except ValueError:
        return False


def _warn_date(parent) -> None:
    QMessageBox.warning(parent, tr("study.dialog.error_title"),
                        tr("study.dialog.bad_date"))


class StudySessionDialog(DialogShell):
    """记一段学习时长。"""

    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent, tr("study.dialog.session_title"),
                         min_width=LAYOUT["dialog_width_sm"], buttons=False)
        self.result_data: dict | None = None
        body = self.body
        self._subject = _subject_combo(dm)
        self._minutes = _spin(1, 1440, 60, tr("study.unit_minutes_suffix"))
        self._date = RoundedLineEdit(date.today().isoformat())
        self._note = RoundedLineEdit()
        self._note.setPlaceholderText(tr("study.dialog.session_note"))
        body.addWidget(form_row(tr("study.dialog.subject"), self._subject))
        body.addWidget(form_row(tr("study.dialog.minutes"), self._minutes))
        body.addWidget(form_row(tr("study.dialog.date"), self._date))
        body.addWidget(form_row(tr("study.dialog.note"), self._note))
        self.add_action_row(action_row(tr("study.dialog.save"), self._ok,
                                       on_cancel=self.reject))

    def _ok(self) -> None:
        if not _valid_date(self._date.text()):
            _warn_date(self)
            return
        self.result_data = {
            "subject": self._subject.currentData(),
            "minutes": self._minutes.value(),
            "date": self._date.text().strip(),
            "note": self._note.text().strip(),
        }
        self.accept()


class MistakeDialog(DialogShell):
    """记一道错题（自动进入 1/2/4/7/15/30 天复习队列）。"""

    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent, tr("study.dialog.mistake_title"),
                         min_width=LAYOUT["dialog_width_md"], buttons=False)
        self.result_data: dict | None = None
        body = self.body
        self._subject = _subject_combo(dm)
        self._topic = RoundedLineEdit()
        self._topic.setPlaceholderText(tr("study.dialog.mistake_topic"))
        self._question = RoundedLineEdit()
        self._question.setPlaceholderText(tr("study.dialog.mistake_question"))
        self._answer = RoundedLineEdit()
        self._answer.setPlaceholderText(tr("study.dialog.mistake_answer"))
        self._note = RoundedLineEdit()
        self._note.setPlaceholderText(tr("study.dialog.note"))
        self._date = RoundedLineEdit(date.today().isoformat())
        for label, widget in (
            (tr("study.dialog.subject"), self._subject),
            (tr("study.dialog.mistake_topic_label"), self._topic),
            (tr("study.dialog.mistake_question_label"), self._question),
            (tr("study.dialog.mistake_answer_label"), self._answer),
            (tr("study.dialog.note"), self._note),
            (tr("study.dialog.date"), self._date),
        ):
            body.addWidget(form_row(label, widget))
        self.add_action_row(action_row(tr("study.dialog.save"), self._ok,
                                       on_cancel=self.reject))

    def _ok(self) -> None:
        if not self._topic.text().strip():
            QMessageBox.warning(self, tr("study.dialog.error_title"),
                                tr("study.dialog.need_topic"))
            return
        if not _valid_date(self._date.text()):
            _warn_date(self)
            return
        self.result_data = {
            "subject": self._subject.currentData(),
            "topic": self._topic.text().strip(),
            "question": self._question.text().strip(),
            "answer": self._answer.text().strip(),
            "note": self._note.text().strip(),
            "date": self._date.text().strip(),
        }
        self.accept()


class MockDialog(DialogShell):
    """记一次模拟考试。"""

    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent, tr("study.dialog.mock_title"),
                         min_width=LAYOUT["dialog_width_sm"], buttons=False)
        self.result_data: dict | None = None
        body = self.body
        self._subject = _subject_combo(dm)
        self._score = _spin(0, 1000, 100, tr("study.unit_score_suffix"))
        self._full = _spin(1, 1000, 150)
        self._duration = _spin(1, 1440, 180, tr("study.unit_minutes_suffix"))
        self._date = RoundedLineEdit(date.today().isoformat())
        self._note = RoundedLineEdit()
        self._note.setPlaceholderText(tr("study.dialog.note"))
        for label, widget in (
            (tr("study.dialog.subject"), self._subject),
            (tr("study.dialog.mock_score"), self._score),
            (tr("study.dialog.mock_full_score"), self._full),
            (tr("study.dialog.mock_duration"), self._duration),
            (tr("study.dialog.date"), self._date),
            (tr("study.dialog.note"), self._note),
        ):
            body.addWidget(form_row(label, widget))
        self.add_action_row(action_row(tr("study.dialog.save"), self._ok,
                                       on_cancel=self.reject))

    def _ok(self) -> None:
        if not _valid_date(self._date.text()):
            _warn_date(self)
            return
        if self._score.value() > self._full.value():
            QMessageBox.warning(self, tr("study.dialog.error_title"),
                                tr("study.dialog.score_over_full"))
            return
        self.result_data = {
            "subject": self._subject.currentData(),
            "score": self._score.value(),
            "full_score": self._full.value(),
            "duration_minutes": self._duration.value(),
            "date": self._date.text().strip(),
            "note": self._note.text().strip(),
        }
        self.accept()


class StudyTargetDialog(DialogShell):
    """设置目标考试日期 / 每日学习目标。"""

    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent, tr("study.dialog.target_title"),
                         min_width=LAYOUT["dialog_width_sm"], buttons=False)
        self.result_data: dict | None = None
        body = self.body
        self._date = RoundedLineEdit(dm.study.target_date)
        self._goal = _spin(1, 1440, int(dm.study.data.get("daily_goal_minutes") or 360),
                           tr("study.unit_minutes_suffix"))
        body.addWidget(form_row(tr("study.dialog.target_date"), self._date))
        body.addWidget(form_row(tr("study.dialog.daily_goal"), self._goal))
        self.add_action_row(action_row(tr("study.dialog.save"), self._ok,
                                       on_cancel=self.reject))

    def _ok(self) -> None:
        if not _valid_date(self._date.text()):
            _warn_date(self)
            return
        self.result_data = {"date": self._date.text().strip(),
                            "daily_goal": self._goal.value()}
        self.accept()
